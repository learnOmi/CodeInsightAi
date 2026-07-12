"""
增量分析服务

核心职责：
1. 计算文件变更集（基于 content_hash 对比上次快照）
2. 依赖传播（将变更文件的调用方/被调用方纳入重分析）
3. 判断是否应降级为全量分析（变更过多时）
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.config import settings
from codeinsight.db.session import async_session_factory
from codeinsight.models import FileModel
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO, FileDAO, ModuleDependencyDAO

logger = logging.getLogger(__name__)


class ChangeType(StrEnum):
    """文件变更类型"""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class FileChange:
    """单个文件变更"""

    file_id: UUID
    path: str
    change_type: ChangeType
    old_hash: str | None  # 旧 hash（deleted/modified）
    new_hash: str  # 新 hash（added/modified）


@dataclass
class IncrementalDiff:
    """增量分析差异结果"""

    changed_files: list[FileChange]  # 直接变更的文件
    propagated_files: list[str]  # 依赖传播后纳入的文件路径
    total_files_to_analyze: int  # 最终需要分析的文件数
    skipped_files: int  # 跳过未变更文件数
    needs_full_analysis: bool  # 是否需要降级为全量分析


class IncrementalAnalyzer:
    """
    增量分析服务

    核心职责：
    1. 计算文件变更集（基于 content_hash 对比）
    2. 依赖传播（将变更文件的调用方/被调用方纳入重分析）
    3. 判断是否应降级为全量分析（变更过多时）
    """

    def __init__(
        self,
        fallback_threshold: float = settings.incremental_max_change_ratio,
        max_depth: int = settings.incremental_max_propagation_depth,
    ) -> None:
        self.fallback_threshold = fallback_threshold
        self.max_depth = max_depth

    async def compute_diff(
        self,
        repo_uuid: UUID,
        current_files: list[FileModel],
        latest_version: str | None = None,
    ) -> IncrementalDiff:
        """
        计算增量分析差异

        Args:
            repo_uuid: 仓库 UUID
            current_files: 当前扫描到的文件列表
            latest_version: 上次分析版本标签（None 表示首次分析）

        Returns:
            IncrementalDiff 包含变更文件和传播文件
        """
        # 无历史快照，需要全量分析
        if latest_version is None:
            logger.info("无历史快照，需要全量分析: repo=%s", repo_uuid)
            return IncrementalDiff(
                changed_files=[],
                propagated_files=[],
                total_files_to_analyze=len(current_files),
                skipped_files=0,
                needs_full_analysis=True,
            )

        # 1. 加载上次快照
        previous_snapshot = await self._load_snapshot(repo_uuid, latest_version)

        # 2. 计算直接变更
        changes = self._compute_changes(current_files, previous_snapshot)

        # 3. 依赖传播
        propagated = await self._propagate_dependencies(repo_uuid, changes)

        # 4. 计算最终需要分析的文件数
        changed_paths = {c.path for c in changes}
        affected_paths = changed_paths | set(propagated)
        affected_count = len(affected_paths)

        # 5. 判断是否需要降级
        total_current = len(current_files)
        needs_full = (affected_count / max(total_current, 1)) > self.fallback_threshold

        if needs_full:
            logger.info(
                "触发降级: repo=%s, affected=%d/%d (%.1f%% > %.1f%%)",
                repo_uuid,
                affected_count,
                total_current,
                (affected_count / max(total_current, 1)) * 100,
                self.fallback_threshold * 100,
            )
        else:
            logger.info(
                "增量分析: repo=%s, changed=%d, propagated=%d, total=%d, skipped=%d",
                repo_uuid,
                len(changes),
                len(propagated),
                affected_count,
                total_current - affected_count,
            )

        return IncrementalDiff(
            changed_files=changes,
            propagated_files=propagated,
            total_files_to_analyze=affected_count,
            skipped_files=total_current - affected_count,
            needs_full_analysis=needs_full,
        )

    async def get_files_to_analyze(
        self,
        diff: IncrementalDiff,
        current_files: list[FileModel],
    ) -> list[FileModel]:
        """
        根据增量差异返回需要分析的文件列表

        Args:
            diff: 增量差异结果
            current_files: 当前所有文件

        Returns:
            需要重分析的文件列表
        """
        affected_paths = {c.path for c in diff.changed_files}
        affected_paths.update(diff.propagated_files)

        return [f for f in current_files if f.path in affected_paths]

    async def _load_snapshot(
        self,
        repo_uuid: UUID,
        version: str | None,
    ) -> dict[str, str]:
        """
        加载上次分析的文件快照

        Returns:
            {file_path: content_hash} 映射
        """
        if version is None:
            return {}

        file_dao = FileDAO()
        async with async_session_factory() as db:
            # 获取该版本对应的快照
            snapshots = await self._get_snapshots_by_version(db, repo_uuid, version)
            snapshot_by_file_id = {s.file_id: s for s in snapshots}

            # 获取当前文件列表（用于 path 映射）
            files = await file_dao.get_by_repository(db, repo_uuid)
            file_path_by_id = {f.id: f.path for f in files}

            # 构建 {path: hash} 映射
            return {
                file_path_by_id[fid]: s.content_hash for fid, s in snapshot_by_file_id.items() if fid in file_path_by_id
            }

    async def _get_snapshots_by_version(self, db: AsyncSession, repo_uuid: UUID, version: str) -> list:
        """获取指定版本的快照"""
        from codeinsight.models import FileAnalysisSnapshotModel

        result = await db.execute(
            select(FileAnalysisSnapshotModel).where(
                FileAnalysisSnapshotModel.repository_id == repo_uuid,
                FileAnalysisSnapshotModel.analysis_version == version,
            )
        )
        return list(result.scalars().all())

    def _compute_changes(
        self,
        current_files: list[FileModel],
        previous_snapshot: dict[str, str],
    ) -> list[FileChange]:
        """
        计算文件变更集

        对比逻辑：
        - current_path 不在 previous 中 → added
        - previous_path 不在 current 中 → deleted
        - hash 不同 → modified
        - hash 相同 → 未变更，跳过
        """
        # 构建当前文件索引
        current_by_path: dict[str, FileModel] = {f.path: f for f in current_files}
        previous_by_path: dict[str, str] = previous_snapshot

        changes: list[FileChange] = []

        # 检查新增和修改
        for file_obj in current_files:
            path = file_obj.path
            new_hash = file_obj.content_hash

            if path not in previous_by_path:
                # 新增文件
                changes.append(
                    FileChange(
                        file_id=file_obj.id,
                        path=path,
                        change_type=ChangeType.ADDED,
                        old_hash=None,
                        new_hash=new_hash,
                    )
                )
            elif previous_by_path[path] != new_hash:
                # 修改文件
                changes.append(
                    FileChange(
                        file_id=file_obj.id,
                        path=path,
                        change_type=ChangeType.MODIFIED,
                        old_hash=previous_by_path[path],
                        new_hash=new_hash,
                    )
                )
            # 否则未变更，跳过

        # 检查删除
        for path in previous_by_path:
            if path not in current_by_path:
                # 删除文件使用哨兵 file_id（传播逻辑会跳过 DELETED 类型，不会使用该 ID）
                changes.append(
                    FileChange(
                        file_id=UUID("00000000-0000-0000-0000-000000000000"),
                        path=path,
                        change_type=ChangeType.DELETED,
                        old_hash=previous_by_path[path],
                        new_hash="",
                    )
                )

        logger.debug(
            "文件变更检测: added=%d, modified=%d, deleted=%d",
            sum(1 for c in changes if c.change_type == ChangeType.ADDED),
            sum(1 for c in changes if c.change_type == ChangeType.MODIFIED),
            sum(1 for c in changes if c.change_type == ChangeType.DELETED),
        )

        return changes

    async def _propagate_dependencies(
        self,
        repo_uuid: UUID,
        changes: list[FileChange],
        max_depth: int | None = None,
    ) -> list[str]:
        """
        BFS 依赖传播

        传播规则：
        1. 变更文件被其他文件调用（call_edges.callee_node_id）→ 调用方需要重分析
        2. 变更文件调用了其他文件（call_edges.caller_node_id）→ 被调用方可能需要重分析
        3. 变更文件被其他文件 import（module_dependencies.imported_file_id）→ 导入方需要重分析

        使用 BFS 遍历，限制最大传播深度，避免无限扩散。
        """
        if max_depth is None:
            max_depth = self.max_depth

        if not changes:
            return []

        # 只处理新增和修改的文件（删除的文件不需要传播）
        modified_changes = [c for c in changes if c.change_type != ChangeType.DELETED]
        if not modified_changes:
            return []

        visited: set[str] = set()
        propagated: set[str] = set()

        # 初始化队列
        queue: list[tuple[str, int]] = []
        for change in modified_changes:
            visited.add(change.path)
            queue.append((change.path, 0))

        async with async_session_factory() as db:
            # 加载所有文件（用于路径查找）
            file_dao = FileDAO()
            all_files = await file_dao.get_by_repository(db, repo_uuid)
            file_id_to_path: dict[UUID, str] = {f.id: f.path for f in all_files}

            while queue:
                current_path, depth = queue.pop(0)

                if depth >= max_depth:
                    continue

                # 查询 call_edges 中的关联文件
                caller_paths, callee_paths = await self._get_call_related_files(
                    db, repo_uuid, current_path, file_id_to_path
                )

                # 查询 module_dependencies 中的关联文件
                importer_paths, importee_paths = await self._get_dep_related_files(
                    db, repo_uuid, current_path, file_id_to_path
                )

                # 收集新文件
                for path in caller_paths | callee_paths | importer_paths | importee_paths:
                    if path not in visited:
                        visited.add(path)
                        propagated.add(path)
                        queue.append((path, depth + 1))

        logger.debug(
            "依赖传播完成: propagated=%d 文件",
            len(propagated),
        )

        return list(propagated)

    async def _get_call_related_files(
        self,
        db: AsyncSession,
        repo_uuid: UUID,
        file_path: str,
        file_id_to_path: dict[UUID, str],
    ) -> tuple[set[str], set[str]]:
        """
        查询调用相关文件

        Returns:
            (caller_paths, callee_paths)
        """
        # 获取该文件的所有 AST 节点
        ast_dao = AstNodeDAO()
        file_dao = FileDAO()

        # 查找该文件的 file_id
        files = await file_dao.get_by_repository(db, repo_uuid)
        file_id = next((f.id for f in files if f.path == file_path), None)
        if file_id is None:
            return set(), set()

        # 获取该文件的所有节点
        nodes = await ast_dao.get_by_file(db, file_id)
        node_ids = {n.id for n in nodes}

        call_edge_dao = CallEdgeDAO()
        all_edges = await call_edge_dao.get_by_repository(db, repo_uuid)

        caller_paths: set[str] = set()
        callee_paths: set[str] = set()

        # 收集需要查询的节点 ID（避免 N+1）
        needed_node_ids: set[UUID] = set()
        for edge in all_edges:
            if edge.caller_node_id in node_ids and edge.callee_node_id:
                needed_node_ids.add(edge.callee_node_id)
            if edge.callee_node_id in node_ids and edge.caller_node_id:
                needed_node_ids.add(edge.caller_node_id)

        # 批量加载节点
        node_path_map: dict[UUID, str] = {}
        if needed_node_ids:
            nodes = await ast_dao.get_by_ids(db, repo_uuid, list(needed_node_ids))
            node_path_map = {n.id: n.file_path for n in nodes}

        for edge in all_edges:
            # 调用方属于当前文件，且存在被调用节点
            if edge.caller_node_id in node_ids and edge.callee_node_id:
                callee_path = node_path_map.get(edge.callee_node_id)
                if callee_path and callee_path != file_path:
                    callee_paths.add(callee_path)

            # 被调用方属于当前文件，且存在调用方节点
            if edge.callee_node_id in node_ids and edge.caller_node_id:
                caller_path = node_path_map.get(edge.caller_node_id)
                if caller_path and caller_path != file_path:
                    caller_paths.add(caller_path)

        return caller_paths, callee_paths

    async def _get_dep_related_files(
        self,
        db: AsyncSession,
        repo_uuid: UUID,
        file_path: str,
        file_id_to_path: dict[UUID, str],
    ) -> tuple[set[str], set[str]]:
        """
        查询模块依赖相关文件

        Returns:
            (importer_paths, importee_paths)
        """
        file_dao = FileDAO()
        files = await file_dao.get_by_repository(db, repo_uuid)
        file_id = next((f.id for f in files if f.path == file_path), None)
        if file_id is None:
            return set(), set()

        module_dep_dao = ModuleDependencyDAO()
        all_deps = await module_dep_dao.get_by_repository(db, repo_uuid)

        importer_paths: set[str] = set()
        importee_paths: set[str] = set()

        for dep in all_deps:
            # 导入方属于当前文件，且存在被导入方
            if dep.importer_file_id == file_id and dep.imported_file_id:
                importee_path = file_id_to_path.get(dep.imported_file_id)
                if importee_path and importee_path != file_path:
                    importee_paths.add(importee_path)

            # 被导入方属于当前文件，且存在导入方
            if dep.imported_file_id == file_id and dep.importer_file_id:
                importer_path = file_id_to_path.get(dep.importer_file_id)
                if importer_path and importer_path != file_path:
                    importer_paths.add(importer_path)

        return importer_paths, importee_paths
