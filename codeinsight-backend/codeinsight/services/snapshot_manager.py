"""
分析快照管理器

负责快照的保存和加载，供增量分析使用。
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.config import settings
from codeinsight.models import FileModel
from codeinsight.repositories import FileAnalysisSnapshotDAO

logger = logging.getLogger(__name__)


class SnapshotManager:
    """
    分析快照管理器

    核心职责：
    1. 保存每次分析的文件快照（content_hash）
    2. 加载最新快照供增量分析使用
    3. 清理旧快照，控制表大小
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.snapshot_dao = FileAnalysisSnapshotDAO()

    async def save_snapshot(
        self,
        repo_uuid: UUID,
        version: str,
        files: list[FileModel],
        node_counts: dict[str, int] | None = None,
    ) -> int:
        """
        保存本次分析的文件快照

        Args:
            repo_uuid: 仓库 UUID
            version: 分析版本标签（如 v20260712-abc1234）
            files: 本次分析的文件列表
            node_counts: 每个文件的 AST 节点数 {file_path: count}

        Returns:
            保存的快照记录数
        """
        node_counts = node_counts or {}
        snapshots_data = []

        for file_obj in files:
            snapshots_data.append(
                {
                    "repository_id": repo_uuid,
                    "analysis_version": version,
                    "file_id": file_obj.id,
                    "content_hash": file_obj.content_hash,
                    "nodes_count": node_counts.get(file_obj.path, 0),
                }
            )

        if not snapshots_data:
            logger.info("快照保存: repo=%s, version=%s, files=0 (跳过)", repo_uuid, version)
            return 0

        await self.snapshot_dao.create_many(self.db, snapshots_data)
        await self.db.commit()

        logger.info(
            "快照保存完成: repo=%s, version=%s, files=%d",
            repo_uuid,
            version,
            len(snapshots_data),
        )

        # 清理旧快照
        await self._cleanup_old_snapshots(repo_uuid, version)

        return len(snapshots_data)

    async def load_latest_snapshot(
        self,
        repo_uuid: UUID,
    ) -> tuple[str, dict[UUID, str]] | None:
        """
        加载最新快照

        返回 (version, {file_id: content_hash})。

        Args:
            repo_uuid: 仓库 UUID

        Returns:
            (version, hash_map) 或 None（无历史快照）
        """
        latest_version = await self.snapshot_dao.get_latest_version(self.db, repo_uuid)
        if latest_version is None:
            logger.info("无历史快照: repo=%s", repo_uuid)
            return None

        # 获取该版本的所有快照
        snapshots = await self.snapshot_dao.get_by_version(self.db, repo_uuid, latest_version)
        hash_map = {s.file_id: s.content_hash for s in snapshots}

        logger.info(
            "加载最新快照: repo=%s, version=%s, files=%d",
            repo_uuid,
            latest_version,
            len(hash_map),
        )

        return (latest_version, hash_map)

    async def load_snapshot_by_version(
        self,
        repo_uuid: UUID,
        version: str,
    ) -> dict[UUID, str] | None:
        """
        加载指定版本的快照

        Args:
            repo_uuid: 仓库 UUID
            version: 分析版本标签

        Returns:
            {file_id: content_hash} 或 None
        """
        snapshots = await self.snapshot_dao.get_by_version(self.db, repo_uuid, version)
        if not snapshots:
            logger.warning("指定版本无快照: repo=%s, version=%s", repo_uuid, version)
            return None

        return {s.file_id: s.content_hash for s in snapshots}

    async def get_latest_version(self, repo_uuid: UUID) -> str | None:
        """
        获取最新快照版本号

        Args:
            repo_uuid: 仓库 UUID

        Returns:
            最新版本标签，或 None
        """
        return await self.snapshot_dao.get_latest_version(self.db, repo_uuid)

    async def _cleanup_old_snapshots(self, repo_uuid: UUID, current_version: str) -> None:
        """
        清理旧快照，保留最近 _MAX_SNAPSHOT_VERSIONS 个版本

        Args:
            repo_uuid: 仓库 UUID
            current_version: 当前版本（保留）
        """
        # 直接查询所有版本标签
        all_versions = await self.snapshot_dao.get_all_versions(self.db, repo_uuid)
        if not all_versions:
            return

        # 保留最近 N 个版本
        keep_versions = all_versions[: settings.incremental_max_snapshot_versions]
        logger.debug("快照清理: 保留 %d 个版本: %s", len(keep_versions), keep_versions)

        deleted = await self.snapshot_dao.delete_old_versions(self.db, repo_uuid, keep_versions)
        if deleted:
            await self.db.commit()
            logger.info("快照清理完成: 删除 %d 条旧记录", deleted)

    async def delete_by_repository(self, repo_uuid: UUID) -> int:
        """
        删除指定仓库的所有快照

        Args:
            repo_uuid: 仓库 UUID

        Returns:
            删除的记录数
        """
        deleted = await self.snapshot_dao.delete_by_repository(self.db, repo_uuid)
        await self.db.commit()
        logger.info("删除仓库所有快照: repo=%s, deleted=%d", repo_uuid, deleted)
        return deleted
