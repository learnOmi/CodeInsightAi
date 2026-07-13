"""
Repository 数据访问对象

提供仓库实体的 CRUD 操作。
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import RepositoryModel, RepositoryStatus
from codeinsight.schemas import RepositoryCreate, RepositoryUpdate


class RepositoryDAO:
    """仓库数据访问对象"""

    async def create(self, db: AsyncSession, data: RepositoryCreate) -> RepositoryModel:
        """
        创建仓库

        Args:
            db: 异步数据库会话
            data: 创建请求数据

        Returns:
            创建的 RepositoryModel 实例
        """
        repo = RepositoryModel(
            name=data.name,
            path=data.path,
            status=RepositoryStatus.PENDING.value,
            current_version=None,
            file_count=0,
            line_count=0,
            knowledge_points_count=0,
            language_distribution={},
        )
        db.add(repo)
        await db.flush()
        await db.refresh(repo)
        return repo

    async def get_by_id(self, db: AsyncSession, repository_id: UUID) -> RepositoryModel | None:
        """
        根据 ID 获取仓库

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID

        Returns:
            RepositoryModel 实例，不存在则返回 None
        """
        result = await db.execute(select(RepositoryModel).where(RepositoryModel.id == repository_id))
        return result.scalar_one_or_none()

    async def list(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> list[RepositoryModel]:
        """
        分页获取仓库列表

        Args:
            db: 异步数据库会话
            skip: 跳过的记录数
            limit: 返回的记录数上限

        Returns:
            RepositoryModel 列表
        """
        result = await db.execute(
            select(RepositoryModel).offset(skip).limit(limit).order_by(RepositoryModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, db: AsyncSession, repository_id: UUID, data: RepositoryUpdate) -> RepositoryModel:
        """
        更新仓库信息

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            data: 更新数据

        Returns:
            更新后的 RepositoryModel 实例

        Raises:
            ValueError: 仓库不存在
        """
        repo = await self.get_by_id(db, repository_id)
        if repo is None:
            raise ValueError(f"Repository {repository_id} not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(repo, key, value)

        await db.flush()
        await db.refresh(repo)
        return repo

    async def delete(self, db: AsyncSession, repository_id: UUID) -> bool:
        """
        删除仓库（级联删除关联的文件和知识点）

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID

        Returns:
            是否删除成功
        """
        repo = await self.get_by_id(db, repository_id)
        if repo is None:
            return False

        await db.delete(repo)
        await db.flush()
        return True

    async def exists_by_path(self, db: AsyncSession, path: str) -> bool:
        """
        检查指定路径是否已存在仓库

        Args:
            db: 异步数据库会话
            path: 仓库路径

        Returns:
            是否存在
        """
        result = await db.execute(select(func.count(RepositoryModel.id)).where(RepositoryModel.path == path))
        return (result.scalar() or 0) > 0
