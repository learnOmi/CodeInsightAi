"""
数据库会话管理

提供 AsyncSession 工厂函数，用于数据库操作。

DB-7 修复：使用 get_engine() 延迟创建，避免模块导入时触发数据库连接。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeinsight.db.engine import get_engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """延迟创建 session factory（DB-7 修复）"""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async_session_factory = _get_session_factory()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（FastAPI Depends 兼容）

    请求成功时自动提交事务，异常时自动回滚，确保数据一致性。
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
