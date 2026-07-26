"""
数据库会话管理

提供 AsyncSession 工厂函数，用于数据库操作。

DB-7 修复：使用 get_engine() 延迟创建，避免模块导入时触发数据库连接。
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeinsight.db.engine import get_engine

logger = logging.getLogger(__name__)


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

    手动管理事务生命周期：
    - 正常退出时自动提交事务（如果尚未提交）
    - 异常时自动回滚事务
    - 支持路由内手动 commit() 的场景（如创建仓库后需立即提交供其他 session 可见）
    """
    async with async_session_factory() as session:
        try:
            yield session
            # 仅在事务未提交时才调用 commit()，避免与端点内手动 commit() 冲突
            logger.info("get_db_session cleanup: session.in_transaction()=%s", session.in_transaction())
            if session.in_transaction():
                await session.commit()
        except Exception as exc:
            logger.warning("get_db_session: 异常发生，回滚事务: %s", exc, exc_info=True)
            await session.rollback()
            raise
