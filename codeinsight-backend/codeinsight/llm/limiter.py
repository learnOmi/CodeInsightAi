"""
LLM 限流与熔断中间件

使用 Redis Token Bucket 实现全局限流，配合 Circuit Breaker 模式处理上游故障。

优势：
- Token Bucket: 精确控制 QPS，平滑突发流量
- Circuit Breaker: 上游故障时快速失败，避免无限等待
- Redis 持久化: 跨进程/多实例共享限流状态
"""

from __future__ import annotations

import asyncio
import enum
import logging
from datetime import UTC, datetime
from typing import Any

import redis
import redis.asyncio as aioredis

from codeinsight.config import settings
from codeinsight.db.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    """熔断器状态"""

    CLOSED = "closed"  # 正常，请求通过
    OPEN = "open"  # 熔断，请求快速失败
    HALF_OPEN = "half_open"  # 半开，允许少量探测请求


class LLMLimiter:
    """
    LLM 限流与熔断器

    组合使用 Token Bucket（限流）+ Circuit Breaker（故障隔离）

    Args:
        redis_client: Redis 客户端（可选，不传则从全局获取）
        rate_limit_qps: 每秒允许的请求数（0 表示不限流）
        burst_size: 突发请求上限
        circuit_breaker_threshold: 连续失败次数阈值
        circuit_breaker_timeout: 熔断恢复等待时间（秒）
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        async_redis_client: aioredis.Redis | None = None,
        rate_limit_qps: int = 0,
        burst_size: int = 5,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 30,
    ) -> None:
        self._redis = redis_client or get_redis_client()
        self._async_redis = async_redis_client
        self.rate_limit_qps = rate_limit_qps
        self.burst_size = burst_size
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_timeout = circuit_breaker_timeout

        # 熔断器状态（内存本地状态 + Redis 持久化）
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._lock = asyncio.Lock()

    def _bucket_key(self, key: str = "llm_global") -> str:
        return f"rate_limit:bucket:{key}"

    def _circuit_key(self, key: str = "llm_global") -> str:
        return f"circuit_breaker:{key}"

    async def _load_circuit_state_from_redis(self, key: str) -> None:
        """从 Redis 加载熔断器状态到本地"""
        # Determine async Redis client
        redis_client = self._async_redis
        if redis_client is None:
            try:
                redis_client = await aioredis.from_url("redis://localhost:6379")
            except Exception as e:
                logger.warning("无法创建 Redis 客户端以加载熔断器状态: %s", e)
                return
        try:
            # redis-py async stubs 将 hgetall 返回类型标记为 Any | Awaitable[dict] | dict，
            # 实际使用 decode_responses=True 时始终返回 dict
            data = await redis_client.hgetall(self._circuit_key(key))  # type: ignore[misc]
            if data:
                # Convert bytes to strings
                data_dict = {k.decode("utf-8"): v.decode("utf-8") for k, v in data.items()}
                state = data_dict.get("state", CircuitState.CLOSED.value)
                self._circuit_state = CircuitState(state)
                failure_str = data_dict.get("failure_count", "0")
                try:
                    self._failure_count = int(failure_str)
                except ValueError:
                    self._failure_count = 0
                last_ts = data_dict.get("last_failure_time")
                if last_ts and last_ts.strip():
                    self._last_failure_time = datetime.fromisoformat(last_ts)
                elif self._circuit_state == CircuitState.OPEN:
                    # 状态为 OPEN 但 last_failure_time 为空，使用当前时间
                    logger.warning("Redis 熔断器状态 OPEN 但 last_failure_time 为空，使用当前时间: key=%s", key)
                    self._last_failure_time = datetime.now(UTC)
                logger.info(
                    "已从 Redis 加载熔断器状态: %s, 状态=%s, 失败次数=%d",
                    key,
                    self._circuit_state.value,
                    self._failure_count,
                )
        except Exception as e:
            logger.warning("Redis 加载熔断器状态失败: %s", e)

    async def _save_circuit_state_to_redis(self, key: str) -> None:
        """将本地熔断器状态保存到 Redis"""
        # Determine async Redis client
        redis_client = self._async_redis
        if redis_client is None:
            try:
                redis_client = await aioredis.from_url("redis://localhost:6379")
            except Exception as e:
                logger.warning("无法创建 Redis 客户端以保存熔断器状态: %s", e)
                return
        try:
            now_str = self._last_failure_time.isoformat() if self._last_failure_time else ""
            # 如果状态为 OPEN 但 last_failure_time 为空，使用当前时间
            if self._circuit_state == CircuitState.OPEN and not self._last_failure_time:
                now_str = datetime.now(UTC).isoformat()
                self._last_failure_time = datetime.now(UTC)
            # redis-py async stubs 返回类型有误，hset 是 awaitable
            await redis_client.hset(  # type: ignore[misc]
                self._circuit_key(key),
                mapping={
                    "state": self._circuit_state.value,
                    "failure_count": str(self._failure_count),
                    "last_failure_time": now_str,
                },
            )
            await redis_client.expire(self._circuit_key(key), 3600)  # TTL 1 hour
            logger.debug("已保存熔断器状态到 Redis: %s", key)
        except Exception as e:
            logger.warning("Redis 保存熔断器状态失败: %s", e)

    async def acquire(
        self, key: str = "llm_global", skip_breaker: bool = False, skip_bucket: bool = False
    ) -> bool | float:
        """尝试获取限流令牌或检查熔断器状态。

        Args:
            key: 限流键（区分不同 API）
            skip_breaker: 如果为 True，跳过熔断器检查，仅执行 Token Bucket 限流
            skip_bucket: 如果为 True，跳过 Token Bucket 限流，仅检查熔断器状态

        Returns:
            True 表示获得令牌
            False 表示 Token Bucket 限流，需要等待重试
            浮点数（秒数）表示熔断器 OPEN 时的退避时间

        Raises:
            RuntimeError: 熔断器处于 OPEN 状态且未设置 skip_breaker
        """
        # 1. 检查熔断器状态（除非跳过）
        if not skip_breaker:
            await self._load_circuit_state_from_redis(key)
            backoff = await self._check_circuit_with_backoff(key)
            if isinstance(backoff, float):
                # 熔断器 OPEN，返回退避时间
                return backoff
        # 2. Token Bucket 限流（除非跳过）
        if not skip_bucket and self.rate_limit_qps > 0:
            try:
                granted = self._token_bucket_acquire(key)
                if not granted:
                    return False
            except redis.RedisError:
                logger.warning("Redis 限流检查失败，降级为允许请求: key=%s", key)

        return True

    async def _check_circuit_with_backoff(self, key: str) -> bool | float:
        """检查熔断器状态，若OPEN则返回退避时间，否则返回True"""
        async with self._lock:
            if self._circuit_state == CircuitState.CLOSED:
                return True

            if self._circuit_state == CircuitState.OPEN:
                # 如果 _last_failure_time 为 None（状态损坏或并发重置导致），
                # 以当前时间作为熔断起点，确保熔断器生效
                failure_time = self._last_failure_time
                if failure_time is None:
                    logger.warning("熔断器 OPEN 但 last_failure_time 为空，使用当前时间作为熔断起点: key=%s", key)
                    failure_time = datetime.now(UTC)
                    self._last_failure_time = failure_time

                elapsed = (datetime.now(UTC) - failure_time.replace(tzinfo=UTC)).total_seconds()
                if elapsed >= self.circuit_breaker_timeout:
                    self._circuit_state = CircuitState.HALF_OPEN
                    logger.info("熔断器从 OPEN → HALF_OPEN: key=%s", key)
                    return True
                # 仍在熔断期内，返回退避时间
                remaining = self.circuit_breaker_timeout - int(elapsed)
                return max(remaining, 1)  # 最少1秒

            # HALF_OPEN: 允许一次探测请求
            return True

    def _token_bucket_acquire(self, key: str) -> bool:
        """
        Redis Token Bucket 算法实现

        使用 Lua 脚本保证原子性。

        流程：
        1. 计算上次刷新到现在的时间差
        2. 按 QPS 速率补充令牌（最多到 burst_size）
        3. 如果令牌数 > 0，消耗一个令牌
        4. 返回是否成功
        """
        lua_script = """
        local key = KEYS[1]
        local qps = tonumber(ARGV[1])
        local burst = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refresh')
        local tokens = tonumber(bucket[1]) or burst
        local last_refresh = tonumber(bucket[2]) or now

        -- 计算新增令牌
        local elapsed = math.max(0, now - last_refresh)
        local new_tokens = elapsed * qps
        tokens = math.min(burst, tokens + new_tokens)

        -- 尝试消耗令牌
        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_refresh', now)
            redis.call('EXPIRE', key, 300)
            return 1
        else
            -- 更新 last_refresh 但不消耗令牌
            redis.call('HMSET', key, 'last_refresh', now)
            return 0
        end
        """
        now = datetime.now(UTC).timestamp()
        result = self._redis.eval(
            lua_script, 1, self._bucket_key(key), str(self.rate_limit_qps), str(self.burst_size), str(now)
        )
        return bool(result)

    async def _check_circuit(self, key: str) -> bool:
        """检查熔断器状态，返回是否允许请求通过"""
        async with self._lock:
            if self._circuit_state == CircuitState.CLOSED:
                return True

            if self._circuit_state == CircuitState.OPEN and self._last_failure_time:
                elapsed = (datetime.now(UTC) - self._last_failure_time.replace(tzinfo=UTC)).total_seconds()
                if elapsed >= self.circuit_breaker_timeout:
                    self._circuit_state = CircuitState.HALF_OPEN
                    logger.info("熔断器从 OPEN → HALF_OPEN: key=%s", key)
                    return True
                # 仍在熔断期内
                return False

            # HALF_OPEN: 允许一次探测请求
            return True

    async def record_success(self, key: str = "llm_global") -> None:
        """
        记录一次成功请求，重置熔断器

        Args:
            key: 限流键
        """
        async with self._lock:
            # 只在 CLOSED 或 HALF_OPEN 状态重置统计
            # 如果当前是 OPEN 状态，说明是并发请求绕过了熔断检查，
            # 此时不应重置失败计数和时间，否则会破坏熔断器的状态
            if self._circuit_state == CircuitState.HALF_OPEN:
                logger.info("熔断器 HALF_OPEN 探测成功，恢复 CLOSED: key=%s", key)
                self._circuit_state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_failure_time = None
                await self._save_circuit_state_to_redis(key)
            elif self._circuit_state == CircuitState.CLOSED:
                self._failure_count = 0
                self._last_failure_time = None
                await self._save_circuit_state_to_redis(key)
            # OPEN 状态：不做任何操作，保持熔断状态

    async def record_failure(self, key: str = "llm_global") -> None:
        """
        记录一次失败请求，可能触发熔断

        Args:
            key: 限流键
        """
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(UTC)

            if self._failure_count >= self.circuit_breaker_threshold:
                self._circuit_state = CircuitState.OPEN
                logger.warning(
                    "熔断器已打开 (连续失败 %d 次 ≥ 阈值 %d): key=%s, 将在 %ds 后尝试恢复",
                    self._failure_count,
                    self.circuit_breaker_threshold,
                    key,
                    self.circuit_breaker_timeout,
                )

            # 保存至 Redis
            await self._save_circuit_state_to_redis(key)

    async def get_status(self, key: str = "llm_global") -> dict[str, Any]:
        """获取限流器状态"""
        async with self._lock:
            return {
                "circuit_state": self._circuit_state.value,
                "failure_count": self._failure_count,
                "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
                "rate_limit_qps": self.rate_limit_qps,
            }


# 全局实例（懒初始化）
_limiter_instance: LLMLimiter | None = None


def get_llm_limiter() -> LLMLimiter:
    """
    获取全局 LLM 限流器实例

    从配置读取限流参数：
    - llm_rate_limit_qps: 3（默认 3 QPS，0 表示不限流）
    - llm_circuit_breaker_threshold: 熔断阈值
    - llm_circuit_breaker_timeout: 熔断恢复时间
    """
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = LLMLimiter(
            rate_limit_qps=getattr(settings, "llm_rate_limit_qps", 3),
            burst_size=getattr(settings, "llm_burst_size", 5),
            circuit_breaker_threshold=getattr(settings, "llm_circuit_breaker_threshold", 5),
            circuit_breaker_timeout=getattr(settings, "llm_circuit_breaker_timeout", 30),
        )
    return _limiter_instance
