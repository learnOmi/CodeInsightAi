"""
Redis 客户端管理

提供线程安全的 Redis 连接池（全局共享）。

同步版本（redis.Redis）：供 Celery 任务使用
异步版本（redis.asyncio.Redis）：供 FastAPI async 端点使用
"""

import asyncio
import logging

import redis
import redis.asyncio as redis_async

from codeinsight.config import settings

logger = logging.getLogger(__name__)

# ── 同步连接池（Celery 任务）──

_sync_pool: redis.ConnectionPool | None = None
_sync_lock: asyncio.Lock = asyncio.Lock()


def get_redis_pool() -> redis.ConnectionPool:
    """
    获取全局 Redis 同步连接池（惰性初始化）

    与 db/engine.py 模式一致：模块级单例 + 工厂函数。
    注意：此处使用 asyncio.Lock 而非 threading.Lock，因为此函数只在
    Celery 同步上下文中调用，不存在 asyncio 并发冲突。
    """
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = redis.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            max_connections=settings.redis_pool_max_connections,
            socket_connect_timeout=settings.redis_pool_socket_timeout,
            socket_timeout=settings.redis_pool_socket_timeout,
            retry_on_timeout=True,
        )
    return _sync_pool


def get_redis_client() -> redis.Redis:
    """
    从连接池获取一个 Redis 客户端实例（同步）

    每次调用返回的客户端底层共享连接池，用完即放回。
    适用于 Celery 任务等同步执行环境。
    """
    return redis.Redis(connection_pool=get_redis_pool())


# ── 异步连接池（FastAPI async 端点）──

_async_pool: redis_async.ConnectionPool | None = None
_async_lock: asyncio.Lock = asyncio.Lock()


async def get_async_redis_pool() -> redis_async.ConnectionPool:
    """
    获取全局 Redis 异步连接池（惰性初始化）

    使用 asyncio.Lock 保护初始化，确保多协程并发调用时只创建一个实例。
    """
    global _async_pool
    if _async_pool is not None:
        return _async_pool

    async with _async_lock:
        if _async_pool is None:
            _async_pool = redis_async.ConnectionPool(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
                max_connections=settings.redis_pool_max_connections,
                socket_connect_timeout=settings.redis_pool_socket_timeout,
                socket_timeout=settings.redis_pool_socket_timeout,
                retry_on_timeout=True,
            )
        return _async_pool


async def get_async_redis_client() -> redis_async.Redis:
    """
    从异步连接池获取一个 Redis 客户端实例

    每次调用返回的客户端底层共享异步连接池，用完即放回。
    适用于 FastAPI async 端点等异步执行环境。
    """
    pool = await get_async_redis_pool()
    return redis_async.Redis(connection_pool=pool)


# ── 关闭 ──


def close_redis_pool() -> None:
    """关闭同步连接池，释放所有连接（测试/优雅关闭时使用）"""
    global _sync_pool
    if _sync_pool is not None:
        _sync_pool.disconnect()
        _sync_pool = None


async def close_async_redis_pool() -> None:
    """关闭异步连接池，释放所有连接（测试/优雅关闭时使用）"""
    global _async_pool
    if _async_pool is not None:
        await _async_pool.disconnect()
        _async_pool = None
