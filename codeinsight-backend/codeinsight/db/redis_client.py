"""
Redis 客户端管理

提供线程安全的 Redis 连接池，全局共享。
"""

import redis

from codeinsight.config import settings

_redis_pool: redis.ConnectionPool | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """
    获取全局 Redis 连接池（惰性初始化）

    与 db/engine.py 模式一致：模块级单例 + 工厂函数。
    Python 的 GIL 保证简单的赋值操作原子性，单次检查无需锁。
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            max_connections=settings.redis_pool_max_connections,
            socket_connect_timeout=settings.redis_pool_socket_timeout,
            socket_timeout=settings.redis_pool_socket_timeout,
            retry_on_timeout=True,
        )
    return _redis_pool


def get_redis_client() -> redis.Redis:
    """
    从连接池获取一个 Redis 客户端实例

    每次调用返回的客户端底层共享连接池，用完即放回。
    """
    return redis.Redis(connection_pool=get_redis_pool())


def close_redis_pool() -> None:
    """关闭连接池，释放所有连接（测试/优雅关闭时使用）"""
    global _redis_pool
    if _redis_pool is not None:
        _redis_pool.disconnect()
        _redis_pool = None
