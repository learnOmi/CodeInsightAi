"""
增量分析服务

核心职责：
1. 计算文件变更集（基于 content_hash 对比上次快照）
2. 依赖传播（将变更文件的调用方/被调用方纳入重分析）
3. 判断是否应降级为全量分析（变更过多时）
"""

import logging
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.config import settings
from codeinsight.db.session import async_session_factory
from codeinsight.models import FileModel
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO, FileDAO, ModuleDependencyDAO


@asynccontextmanager
async def get_session(db: AsyncSession | None = None) -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话上下文管理器。

    如果传入了 db，则直接使用；否则创建新会话并在退出时关闭。

    Args:
        db: 可选的数据库会话；为 None 时创建独立会话

    Yields:
        AsyncSession 对象
    """
    if db is not None:
        yield db
    else:
        async with async_session_factory() as session:
            yield session


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
        file_dao: FileDAO | None = None,
        ast_node_dao: AstNodeDAO | None = None,
        call_edge_dao: CallEdgeDAO | None = None,
        module_dep_dao: ModuleDependencyDAO | None = None,
    ) -> None:
        self.fallback_threshold = fallback_threshold
        self.max_depth = max_depth

        # DAO 实例（支持依赖注入，便于测试 mock；延迟初始化保持向后兼容）
        self._file_dao = file_dao
        self._ast_node_dao = ast_node_dao
        self._call_edge_dao = call_edge_dao
        self._module_dep_dao = module_dep_dao

    @property
    def file_dao(self) -> FileDAO:
        if self._file_dao is None:
            self._file_dao = FileDAO()
        return self._file_dao

    @property
    def ast_node_dao(self) -> AstNodeDAO:
        if self._ast_node_dao is None:
            self._ast_node_dao = AstNodeDAO()
        return self._ast_node_dao

    @property
    def call_edge_dao(self) -> CallEdgeDAO:
        if self._call_edge_dao is None:
            self._call_edge_dao = CallEdgeDAO()
        return self._call_edge_dao

    @property
    def module_dep_dao(self) -> ModuleDependencyDAO:
        if self._module_dep_dao is None:
            self._module_dep_dao = ModuleDependencyDAO()
        return self._module_dep_dao

    async def compute_diff(
        self,
        repo_uuid: UUID,
        current_files: list[FileModel],
        latest_version: str | None = None,
        db: AsyncSession | None = None,
    ) -> IncrementalDiff:
        """
        计算增量分析差异

        A-7 修复：支持传入共享 db session，避免方法内直接创建新 session。

        Args:
            repo_uuid: 仓库 UUID
            current_files: 当前扫描到的文件列表
            latest_version: 上次分析版本标签（None 表示首次分析）
            db: 可选的数据库会话；为 None 时创建独立会话（兼容旧调用）

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
        previous_snapshot = await self._load_snapshot(repo_uuid, latest_version, db=db)

        # 2. 计算直接变更
        changes = self._compute_changes(current_files, previous_snapshot)

        # 3. 依赖传播
        propagated = await self._propagate_dependencies(repo_uuid, changes, db=db)

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
        db: AsyncSession | None = None,
    ) -> dict[str, str]:
        """
        加载上次分析的文件快照

        A-7 修复：支持传入共享 db session。

        Returns:
            {file_path: content_hash} 映射
        """
        if version is None:
            return {}

        async with get_session(db) as session:
            snapshots = await self._get_snapshots_by_version(session, repo_uuid, version)
            snapshot_by_file_id = {s.file_id: s for s in snapshots}

            files = await self.file_dao.get_by_repository(session, repo_uuid)
            file_path_by_id = {f.id: f.path for f in files}

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
        db: AsyncSession | None = None,
    ) -> list[str]:
        """
        BFS 依赖传播

        A-7 修复：支持传入共享 db session。

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

        modified_changes = [c for c in changes if c.change_type != ChangeType.DELETED]
        if not modified_changes:
            return []

        visited: set[str] = set()
        propagated: set[str] = set()

        queue: deque[tuple[str, int]] = deque()
        for change in modified_changes:
            visited.add(change.path)
            queue.append((change.path, 0))

        async with get_session(db) as session:
            all_files = await self.file_dao.get_by_repository(session, repo_uuid)
            file_id_to_path: dict[UUID, str] = {f.id: f.path for f in all_files}

            all_edges = await self.call_edge_dao.get_by_repository(session, repo_uuid)
            all_deps = await self.module_dep_dao.get_by_repository(session, repo_uuid)
            all_nodes = await self.ast_node_dao.get_by_repository(session, repo_uuid)

            file_id_to_node_ids: dict[UUID, set[UUID]] = {}
            for node in all_nodes:
                file_id_to_node_ids.setdefault(node.file_id, set()).add(node.id)

            node_id_to_path: dict[UUID, str] = {}
            for node in all_nodes:
                node_id_to_path[node.id] = node.file_path

            file_path_to_id: dict[str, UUID] = {f.path: f.id for f in all_files}

            while queue:
                current_path, depth = queue.popleft()

                if depth >= max_depth:
                    continue

                current_file_id = file_path_to_id.get(current_path)
                if current_file_id is None:
                    continue

                current_node_ids = file_id_to_node_ids.get(current_file_id, set())

                caller_paths: set[str] = set()
                callee_paths: set[str] = set()
                for edge in all_edges:
                    if edge.caller_node_id in current_node_ids and edge.callee_node_id:
                        callee_path = node_id_to_path.get(edge.callee_node_id)
                        if callee_path and callee_path != current_path:
                            callee_paths.add(callee_path)
                    if edge.callee_node_id in current_node_ids and edge.caller_node_id:
                        caller_path = node_id_to_path.get(edge.caller_node_id)
                        if caller_path and caller_path != current_path:
                            caller_paths.add(caller_path)

                importer_paths: set[str] = set()
                importee_paths: set[str] = set()
                for dep in all_deps:
                    if dep.importer_file_id == current_file_id and dep.imported_file_id:
                        importee_path = file_id_to_path.get(dep.imported_file_id)
                        if importee_path and importee_path != current_path:
                            importee_paths.add(importee_path)
                    if dep.imported_file_id == current_file_id and dep.importer_file_id:
                        importer_path = file_id_to_path.get(dep.importer_file_id)
                        if importer_path and importer_path != current_path:
                            importer_paths.add(importer_path)

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
