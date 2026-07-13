"""
FileAnalysisSnapshot 数据访问对象

提供文件分析快照实体的 CRUD 操作，支持增量分析的快照管理。
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import FileAnalysisSnapshotModel


class FileAnalysisSnapshotDAO:
    """文件分析快照数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> FileAnalysisSnapshotModel:
        """
        创建快照记录

        Args:
            db: 异步数据库会话
            data: 包含快照字段的字典

        Returns:
            创建的 FileAnalysisSnapshotModel 实例
        """
        snapshot = FileAnalysisSnapshotModel(**data)
        db.add(snapshot)
        await db.flush()
        await db.refresh(snapshot)
        return snapshot

    async def create_many(self, db: AsyncSession, snapshots_data: list[dict]) -> list[FileAnalysisSnapshotModel]:
        """
        批量创建快照记录

        Args:
            db: 异步数据库会话
            snapshots_data: 快照数据列表

        Returns:
            创建的 FileAnalysisSnapshotModel 列表
        """
        snapshot_objects = [FileAnalysisSnapshotModel(**data) for data in snapshots_data]
        db.add_all(snapshot_objects)
        await db.flush()
        # R-1 修复：UUID 由应用层生成，flush 后对象状态已完整，无需逐行 refresh
        return snapshot_objects

    async def get_by_version(
        self, db: AsyncSession, repository_id: UUID, analysis_version: str
    ) -> list[FileAnalysisSnapshotModel]:
        """
        获取指定仓库和版本的所有快照

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            analysis_version: 分析版本标签

        Returns:
            FileAnalysisSnapshotModel 列表
        """
        result = await db.execute(
            select(FileAnalysisSnapshotModel).where(
                FileAnalysisSnapshotModel.repository_id == repository_id,
                FileAnalysisSnapshotModel.analysis_version == analysis_version,
            )
        )
        return list(result.scalars().all())

    async def get_latest_version(self, db: AsyncSession, repository_id: UUID) -> str | None:
        """
        获取指定仓库最新的分析版本标签

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID

        Returns:
            最新的分析版本标签，无快照时返回 None
        """
        from sqlalchemy import func as sa_func

        result = await db.execute(
            select(sa_func.max(FileAnalysisSnapshotModel.analysis_version)).where(
                FileAnalysisSnapshotModel.repository_id == repository_id
            )
        )
        return result.scalar()

    async def get_all_versions(
        self,
        db: AsyncSession,
        repository_id: UUID,
        order_by_created: bool = False,
    ) -> list[str]:
        """
        获取指定仓库的所有分析版本标签（按创建时间降序）

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            order_by_created: True 时按 created_at 排序（更准确）

        Returns:
            版本标签列表（降序）
        """
        query = select(FileAnalysisSnapshotModel.analysis_version).where(
            FileAnalysisSnapshotModel.repository_id == repository_id
        )

        if order_by_created:
            query = query.order_by(FileAnalysisSnapshotModel.created_at.desc())
        else:
            query = query.order_by(FileAnalysisSnapshotModel.analysis_version.desc())

        result = await db.execute(query.distinct())
        return list(result.scalars().all())

    async def get_by_repository(
        self,
        db: AsyncSession,
        repository_id: UUID,
        analysis_version: str,
    ) -> dict[UUID, FileAnalysisSnapshotModel]:
        """
        获取指定仓库和版本的快照，按 file_id 索引

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            analysis_version: 分析版本标签

        Returns:
            {file_id: FileAnalysisSnapshotModel} 字典（仅含非空 file_id）
        """
        snapshots = await self.get_by_version(db, repository_id, analysis_version)
        # file_id 可为 NULL，过滤掉后再构建字典
        return {s.file_id: s for s in snapshots if s.file_id is not None}

    async def delete_by_version(self, db: AsyncSession, repository_id: UUID, analysis_version: str) -> int:
        """
        删除指定版本的所有快照

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            analysis_version: 分析版本标签

        Returns:
            删除的记录数
        """
        result = await db.execute(
            delete(FileAnalysisSnapshotModel).where(
                FileAnalysisSnapshotModel.repository_id == repository_id,
                FileAnalysisSnapshotModel.analysis_version == analysis_version,
            )
        )
        await db.flush()
        return result.rowcount if hasattr(result, "rowcount") and result.rowcount else 0

    async def delete_old_versions(self, db: AsyncSession, repository_id: UUID, keep_versions: list[str]) -> int:
        """
        删除旧版本快照，保留指定版本

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            keep_versions: 需要保留的版本标签列表

        Returns:
            删除的记录数
        """
        if not keep_versions:
            return await self.delete_by_repository(db, repository_id)

        result = await db.execute(
            delete(FileAnalysisSnapshotModel).where(
                FileAnalysisSnapshotModel.repository_id == repository_id,
                FileAnalysisSnapshotModel.analysis_version.notin_(keep_versions),
            )
        )
        await db.flush()
        return result.rowcount if hasattr(result, "rowcount") and result.rowcount else 0

    async def delete_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """
        删除指定仓库的所有快照

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID

        Returns:
            删除的记录数
        """
        result = await db.execute(
            delete(FileAnalysisSnapshotModel).where(FileAnalysisSnapshotModel.repository_id == repository_id)
        )
        await db.flush()
        return result.rowcount if hasattr(result, "rowcount") and result.rowcount else 0

    async def count_by_version(self, db: AsyncSession, repository_id: UUID, analysis_version: str) -> int:
        """
        统计指定仓库和版本的快照数量

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            analysis_version: 分析版本标签

        Returns:
            快照数量
        """
        from sqlalchemy import func

        result = await db.execute(
            select(func.count()).where(
                FileAnalysisSnapshotModel.repository_id == repository_id,
                FileAnalysisSnapshotModel.analysis_version == analysis_version,
            )
        )
        return result.scalar() or 0
