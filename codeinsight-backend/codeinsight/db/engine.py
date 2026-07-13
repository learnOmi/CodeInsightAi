"""
数据库引擎管理

创建异步 SQLAlchemy Engine。

DB-1 修复：延迟创建 Engine，避免模块导入时触发数据库连接。
DB-4 修复：echo 仅在开发环境启用，生产环境即使 debug=True 也不输出 SQL。
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from codeinsight.config import settings


@lru_cache
def get_engine() -> AsyncEngine:
    """延迟创建数据库引擎（DB-1 修复）"""
    echo_enabled = settings.debug and settings.app_env != "production"
    return create_async_engine(
        url=settings.database_url,
        echo=echo_enabled,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


engine: AsyncEngine = get_engine()
