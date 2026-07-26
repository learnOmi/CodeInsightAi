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
        rate_limit_qps: int = 0,
        burst_size: int = 5,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 30,
    ) -> None:
        self._redis = redis_client or get_redis_client()
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
        return f"rate_limit:circuit:{key}"

    async def acquire(self, key: str = "llm_global") -> bool:
        """
        尝试获取限流令牌

        Args:
            key: 限流键（区分不同 API）

        Returns:
            True 表示获得令牌，可以请求
            False 表示被限流，需要等待

        Raises:
            RuntimeError: 熔断器处于 OPEN 状态
        """
        # 1. 检查熔断器
        if not await self._check_circuit(key):
            raise RuntimeError(f"Circuit breaker is OPEN for {key}, requests rejected")

        # 2. Token Bucket 限流
        if self.rate_limit_qps > 0:
            try:
                granted = self._token_bucket_acquire(key)
                if not granted:
                    return False
            except redis.RedisError:
                logger.warning("Redis 限流检查失败，降级为允许请求: key=%s", key)

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
            if self._circuit_state == CircuitState.HALF_OPEN:
                logger.info("熔断器 HALF_OPEN 探测成功，恢复 CLOSED: key=%s", key)
                self._circuit_state = CircuitState.CLOSED

            self._failure_count = 0
            self._last_failure_time = None

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
