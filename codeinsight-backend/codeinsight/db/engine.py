"""
数据库引擎管理

创建异步 SQLAlchemy Engine。
"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from codeinsight.config import settings

engine: AsyncEngine = create_async_engine(
    url=settings.database_url,
    echo=settings.debug,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)
