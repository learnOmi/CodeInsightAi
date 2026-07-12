"""
数据库会话管理

提供 AsyncSession 工厂函数，用于数据库操作。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeinsight.db.engine import engine

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（FastAPI Depends 兼容）

    异常时自动回滚事务，确保数据一致性。
    注意：事务提交由业务层负责，此处仅保证异常时 rollback。
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
