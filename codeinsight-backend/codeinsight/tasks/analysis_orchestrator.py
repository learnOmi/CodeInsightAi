"""
分析任务编排器

将 run_analysis 的多职责逻辑拆分为独立方法，遵循单一职责原则。

职责划分：
- AnalysisOrchestrator: 协调整个分析流程
- AnalysisStep: 各步骤的执行逻辑
- ProgressManager: 进度管理
- CancelChecker: 取消检查

P2-FixP7（共享 Session）:
- 所有数据库方法支持可选 `db: AsyncSession | None = None` 参数
- 当 `db` 传入时，优先使用共享 session（不自行创建连接）
- 当 `db` 未传入时，方法自行创建独立 session（向后兼容）
- _run_async 中使用单一 session 上下文，减少连接池压力
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.analyzers import CallGraphBuilder, ModuleDependencyBuilder
from codeinsight.constants.redis_keys import repo_active_task_key, task_cancel_key
from codeinsight.db.redis_client import get_redis_client
from codeinsight.db.session import async_session_factory
from codeinsight.exceptions import CancelledError
from codeinsight.models import FileModel
from codeinsight.parsers import ParserFactory
from codeinsight.pipelines.structure_pipeline import StructureDataPipeline
from codeinsight.repositories import (
    AnalysisVersionDAO,
    AstNodeDAO,
    CallEdgeDAO,
    FileDAO,
    ModuleDependencyDAO,
    RepositoryDAO,
)
from codeinsight.scanners.git_scanner import GitScanner, ScanResult
from codeinsight.schemas import AnalysisMode, TaskStatus
from codeinsight.services import IncrementalAnalyzer, IncrementalDiff, SnapshotManager

logger = logging.getLogger(__name__)


class CancelChecker:
    """取消检查器"""

    def __init__(self) -> None:
        """T-6 修复：复用 Redis 客户端，避免频繁创建连接"""
        self._client = get_redis_client()

    def check(self, task_id: str | None) -> None:
        """检查是否存在取消标志"""
        if not task_id:
            return
        try:
            cancelled = self._client.get(task_cancel_key(task_id))
            if cancelled:
                self._client.delete(task_cancel_key(task_id))
                logger.info("检测到取消标志，终止任务: task_id=%s", task_id)
                raise CancelledError(f"Task {task_id} was cancelled by user")
        except Exception as exc:
            logger.warning("Redis 取消检查失败: %s", exc)


class ProgressManager:
    """进度管理器"""

    def __init__(self, task_instance: Any | None) -> None:
        self.task_instance = task_instance

    def update(
        self,
        status: TaskStatus,
        percent: float,
        files_processed: int = 0,
        files_total: int = 0,
        knowledge_points_found: int = 0,
    ) -> None:
        """更新进度"""
        if self.task_instance is None:
            return
        self.task_instance.update_state(
            state=status.value,
            meta={
                "current_step": status.value,
                "percent": percent,
                "files_processed": files_processed,
                "files_total": files_total,
                "knowledge_points_found": knowledge_points_found,
            },
        )


class AnalysisOrchestrator:
    """
    分析任务编排器

    统一协调分析流程的各个步骤，支持全量和增量模式。

    所有数据库操作方法支持可选 `db: AsyncSession | None = None` 参数：
    - 传入 db 时，使用共享 session（不自行 commit，由调用方管理）
    - 不传入时，自行创建 session 并 commit（向后兼容）
    """

    def __init__(
        self,
        repo_uuid: UUID,
        mode: str = AnalysisMode.FULL.value,
        task_instance: Any | None = None,
        repository_dao: RepositoryDAO | None = None,
        file_dao: FileDAO | None = None,
        version_dao: AnalysisVersionDAO | None = None,
        ast_node_dao: AstNodeDAO | None = None,
        call_edge_dao: CallEdgeDAO | None = None,
        module_dep_dao: ModuleDependencyDAO | None = None,
    ) -> None:
        self.repo_uuid = repo_uuid
        self.mode = mode
        self.task_instance = task_instance
        self.task_id = getattr(getattr(task_instance, "request", None), "id", None) if task_instance else None
        self.progress_manager = ProgressManager(task_instance)
        self.cancel_checker = CancelChecker()
        self.version_tag = f"v{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex}"
        self.version_id: UUID | None = None
        self.total_files = 0
        self.scan_result: ScanResult | None = None
        self.incremental_diff: IncrementalDiff | None = None
        self.files_to_parse: list[FileModel] = []

        self.repository_dao = repository_dao or RepositoryDAO()
        self.file_dao = file_dao or FileDAO()
        self.version_dao = version_dao or AnalysisVersionDAO()
        self.ast_node_dao = ast_node_dao or AstNodeDAO()
        self.call_edge_dao = call_edge_dao or CallEdgeDAO()
        self.module_dep_dao = module_dep_dao or ModuleDependencyDAO()

    # ================================================================
    # 私有数据库辅助方法（共享 session 支持）
    # ================================================================

    async def _get_repo_path(self, db: AsyncSession | None = None) -> str | None:
        """获取仓库路径"""
        if db is not None:
            repo = await self.repository_dao.get_by_id(db, self.repo_uuid)
            return repo.path if repo is not None else None
        async with async_session_factory() as db:
            repo = await self.repository_dao.get_by_id(db, self.repo_uuid)
            return repo.path if repo is not None else None

    async def _do_analysis_setup(self, db: AsyncSession | None = None) -> None:
        """创建分析版本记录"""
        if db is not None:
            await self._do_analysis_setup_inner(db)
            await db.commit()
            return

        async with async_session_factory() as db:
            await self._do_analysis_setup_inner(db)
            await db.commit()

    async def _do_analysis_setup_inner(self, db: AsyncSession) -> None:
        """_do_analysis_setup 内部逻辑（不含 commit）"""
        repo = await self.repository_dao.get_by_id(db, self.repo_uuid)
        if repo is None:
            raise ValueError(f"Repository {self.repo_uuid} not found")

        version = await self.version_dao.create(
            db,
            {
                "repository_id": self.repo_uuid,
                "version": self.version_tag,
                "status": TaskStatus.PENDING.value,
                "total_files": 0,
                "analyzed_files": 0,
                "knowledge_points_count": 0,
                "started_at": datetime.now(UTC),
            },
        )

        repo.status = "analyzing"
        await db.flush()

        self.version_id = version.id

    async def _update_analysis_version(
        self,
        db: AsyncSession | None,
        status: TaskStatus,
        total_files: int | None = None,
        analyzed_files: int | None = None,
        knowledge_points_count: int | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        version: str | None = None,
    ) -> None:
        """更新分析版本状态"""
        if self.version_id is None:
            return

        update_data: dict[str, Any] = {"status": status.value}
        if total_files is not None:
            update_data["total_files"] = total_files
        if analyzed_files is not None:
            update_data["analyzed_files"] = analyzed_files
        if knowledge_points_count is not None:
            update_data["knowledge_points_count"] = knowledge_points_count
        if completed_at is not None:
            update_data["completed_at"] = completed_at
        if error_message is not None:
            update_data["error_message"] = error_message
        if version is not None:
            update_data["version"] = version

        if db is not None:
            await self.version_dao.update(db, self.version_id, update_data)
            await db.commit()
            return

        async with async_session_factory() as db:
            await self.version_dao.update(db, self.version_id, update_data)
            await db.commit()

    async def _set_repo_status(self, db: AsyncSession | None, status: str) -> None:
        """更新仓库状态"""
        if db is not None:
            repo = await self.repository_dao.get_by_id(db, self.repo_uuid)
            if repo is not None:
                repo.status = status
                await db.commit()
            return

        async with async_session_factory() as db:
            repo = await self.repository_dao.get_by_id(db, self.repo_uuid)
            if repo is not None:
                repo.status = status
                await db.commit()

    def _cleanup_redis_task_key(self) -> None:
        """任务完成后清理 Redis 中的活跃任务标记"""
        try:
            client = get_redis_client()
            client.delete(repo_active_task_key(str(self.repo_uuid)))
            logger.debug("已清理 Redis 活跃任务标记: repo=%s", self.repo_uuid)
        except Exception as exc:
            logger.warning("清理 Redis 活跃任务标记失败: %s", exc)

    async def _update_repository_stats(
        self,
        db: AsyncSession | None,
        total_files: int,
        total_lines: int,
        language_distribution: dict[str, int],
        knowledge_points_count: int = 0,
    ) -> None:
        """更新仓库统计信息"""
        if db is not None:
            repo = await self.repository_dao.get_by_id(db, self.repo_uuid)
            if repo is not None:
                repo.file_count = total_files
                repo.line_count = total_lines
                repo.language_distribution = language_distribution
                repo.current_version = self.version_tag
                repo.knowledge_points_count = knowledge_points_count
                await db.commit()
            return

        async with async_session_factory() as db:
            repo = await self.repository_dao.get_by_id(db, self.repo_uuid)
            if repo is not None:
                repo.file_count = total_files
                repo.line_count = total_lines
                repo.language_distribution = language_distribution
                repo.current_version = self.version_tag
                repo.knowledge_points_count = knowledge_points_count
                await db.commit()

    async def _store_files_to_db(self, db: AsyncSession | None, files_data: list[dict]) -> None:
        """存储扫描结果到 files 表"""
        if db is not None:
            await self.file_dao.delete_by_repository(db, self.repo_uuid)
            if files_data:
                repo_files = await self.file_dao.create_many(db, self.repo_uuid, files_data)
                logger.info("文件存储完成: %d 个文件", len(repo_files))
            await db.commit()
            return

        async with async_session_factory() as db:
            await self.file_dao.delete_by_repository(db, self.repo_uuid)
            if files_data:
                repo_files = await self.file_dao.create_many(db, self.repo_uuid, files_data)
                logger.info("文件存储完成: %d 个文件", len(repo_files))
            await db.commit()

    async def _reconstruct_scan_result(self, db: AsyncSession | None = None) -> bool:
        """从数据库重建扫描结果（断点续跑用）"""
        if db is not None:
            files = await self.file_dao.get_by_repository(db, self.repo_uuid)
        else:
            async with async_session_factory() as db:
                files = await self.file_dao.get_by_repository(db, self.repo_uuid)

        if not files:
            return False

        self.total_files = len(files)

        class _DbScanFile:
            def __init__(self, f: FileModel) -> None:
                self.path = f.path
                self.absolute_path = f.absolute_path
                self.language = f.language
                self.line_count = f.line_count
                self.size_bytes = f.size_bytes
                self.content_hash = f.content_hash

        class _DbScanResult:
            def __init__(self, files_list: list[FileModel]) -> None:
                self.files = [_DbScanFile(f) for f in files_list]
                self.total_count = len(files_list)
                self.total_lines = sum(f.line_count for f in files_list)
                self.language_distribution: dict[str, int] = {}
                for f in files_list:
                    self.language_distribution[f.language] = self.language_distribution.get(f.language, 0) + 1
                self.skipped_count = 0
                self.errors: list[str] = []

        self.scan_result = _DbScanResult(files)  # type: ignore[assignment]
        logger.info("从数据库重建 scan_result: files=%d", self.total_files)
        return True

    # ================================================================
    # 步骤方法
    # ================================================================

    async def scan_files(self, db: AsyncSession | None = None) -> bool:
        """
        Step 2: 扫描文件列表

        Args:
            db: 可选的共享 session，不传入则自行创建

        Returns:
            True 扫描成功，False 需要从头开始
        """
        self.cancel_checker.check(self.task_id)

        repo_path = await self._get_repo_path(db)
        if repo_path is None:
            logger.error("仓库不存在，终止扫描: repo=%s", self.repo_uuid)
            return False

        scanner = GitScanner(repo_path)
        self.scan_result = scanner.scan()
        self.total_files = self.scan_result.total_count

        if self.scan_result.commit_hash:
            self.version_tag = f"v{datetime.now(UTC).strftime('%Y%m%d')}-{self.scan_result.commit_hash}"

        logger.info(
            "扫描完成: repo_path=%s, files=%d, lines=%d, version_tag=%s",
            repo_path,
            self.total_files,
            self.scan_result.total_lines,
            self.version_tag,
        )
        logger.info("语言分布: %s", self.scan_result.language_distribution)

        await self._update_analysis_version(
            db,
            TaskStatus.SCANNING,
            total_files=self.total_files,
            version=self.version_tag,
        )
        await self._update_repository_stats(
            db,
            total_files=self.total_files,
            total_lines=self.scan_result.total_lines,
            language_distribution=self.scan_result.language_distribution,
        )

        files_data = []
        for scanned_file in self.scan_result.files:
            files_data.append(
                {
                    "path": scanned_file.path,
                    "absolute_path": scanned_file.absolute_path,
                    "language": scanned_file.language,
                    "line_count": scanned_file.line_count,
                    "size_bytes": scanned_file.size_bytes,
                    "content_hash": scanned_file.content_hash,
                }
            )
        await self._store_files_to_db(db, files_data)

        return True

    async def compute_incremental_diff(self, db: AsyncSession | None = None) -> bool:
        """
        计算增量分析差异

        Args:
            db: 可选的共享 session，不传入则自行创建

        Returns:
            True 增量可用，False 需要回退为全量
        """
        if self.mode == AnalysisMode.FULL.value:
            return False

        try:
            analyzer = IncrementalAnalyzer()

            if db is not None:
                snapshot_manager = SnapshotManager(db)
                latest_version = await snapshot_manager.get_latest_version(self.repo_uuid)
                current_files = await self.file_dao.get_by_repository(db, self.repo_uuid)
                self.incremental_diff = await analyzer.compute_diff(self.repo_uuid, current_files, latest_version)
            else:
                async with async_session_factory() as db:
                    snapshot_manager = SnapshotManager(db)
                    latest_version = await snapshot_manager.get_latest_version(self.repo_uuid)
                    current_files = await self.file_dao.get_by_repository(db, self.repo_uuid)
                    self.incremental_diff = await analyzer.compute_diff(self.repo_uuid, current_files, latest_version)

            if self.incremental_diff is None:
                logger.warning("增量差异计算返回 None，回退为全量分析")
                return False

            if self.incremental_diff.needs_full_analysis:
                logger.info(
                    "增量分析触发降级: repo=%s, affected=%d/%d，切换为全量分析",
                    self.repo_uuid,
                    self.incremental_diff.total_files_to_analyze,
                    self.total_files,
                )
                self.incremental_diff = None
                return False

            affected_paths: set[str] = {c.path for c in self.incremental_diff.changed_files}
            affected_paths.update(self.incremental_diff.propagated_files)

            if db is not None:
                current_files = await self.file_dao.get_by_repository(db, self.repo_uuid)
            else:
                async with async_session_factory() as db:
                    current_files = await self.file_dao.get_by_repository(db, self.repo_uuid)

            self.files_to_parse = [f for f in current_files if f.path in affected_paths]

            logger.info(
                "增量分析: 变更 %d 文件，传播 %d 文件，共 %d 文件需分析，跳过 %d 文件",
                len(self.incremental_diff.changed_files),
                len(self.incremental_diff.propagated_files),
                self.incremental_diff.total_files_to_analyze,
                self.incremental_diff.skipped_files,
            )
            return True

        except Exception as exc:
            logger.warning("增量分析失败，回退为全量分析: %s", exc)
            self.incremental_diff = None
            return False

    async def parse_ast(
        self, db: AsyncSession | None, progress_callback: Callable[[int, int, str], None] | None = None
    ) -> None:
        """Step 3: AST 解析"""
        if self.scan_result is None:
            logger.warning("扫描结果为空，跳过 AST 解析")
            return

        if db is not None:
            await self.ast_node_dao.delete_by_repository(db, self.repo_uuid)

            repo_files = await self.file_dao.get_by_repository(db, self.repo_uuid)
            file_id_map: dict[str, UUID] = {f.path: f.id for f in repo_files}

            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)
            parsed_count = 0

            for scanned_file in self.scan_result.files:
                try:
                    parser = ParserFactory.get_parser(scanned_file.language)
                    if parser is None:
                        continue

                    ast_nodes = parser.parse_file(scanned_file.absolute_path)
                    file_id = file_id_map.get(scanned_file.path)
                    if file_id is None:
                        continue

                    # 为所有节点分配 UUID，建立父节点映射
                    node_uuids = {id(node): uuid.uuid4() for node in ast_nodes}
                    nodes_data = []
                    for node in ast_nodes:
                        parent_node_id = node_uuids.get(id(node.parent)) if node.parent else None
                        nodes_data.append(
                            {
                                "id": node_uuids[id(node)],
                                "repository_id": self.repo_uuid,
                                "file_id": file_id,
                                "node_type": node.node_type,
                                "name": node.name,
                                "start_line": node.start_line,
                                "end_line": node.end_line,
                                "start_column": node.start_column,
                                "end_column": node.end_column,
                                "parent_node_id": parent_node_id,
                                "file_path": node.file_path,
                                "language": node.language,
                                # Phase 1 新增：框架感知字段
                                "tags": getattr(node, "tags", []),
                                "annotations": getattr(node, "annotations", []),
                                "qualified_name": getattr(node, "qualified_name", None),
                            }
                        )
                    if nodes_data:
                        result = await pipeline.ingest_ast_nodes(self.repo_uuid, nodes_data)
                        parsed_count += result.inserted_count
                except Exception as exc:
                    logger.warning("AST 解析失败: file=%s, error=%s", scanned_file.absolute_path, exc)
                    continue

            logger.info("AST 解析完成: %d 个节点", parsed_count)
            await db.commit()
            return

        async with async_session_factory() as db:
            await self.ast_node_dao.delete_by_repository(db, self.repo_uuid)

            repo_files = await self.file_dao.get_by_repository(db, self.repo_uuid)
            file_id_map = {f.path: f.id for f in repo_files}

            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)
            parsed_count = 0

            for scanned_file in self.scan_result.files:
                try:
                    parser = ParserFactory.get_parser(scanned_file.language)
                    if parser is None:
                        continue

                    ast_nodes = parser.parse_file(scanned_file.absolute_path)
                    file_id = file_id_map.get(scanned_file.path)
                    if file_id is None:
                        continue

                    # 为所有节点分配 UUID，建立父节点映射
                    node_uuids = {id(node): uuid.uuid4() for node in ast_nodes}
                    nodes_data = []
                    for node in ast_nodes:
                        parent_node_id = node_uuids.get(id(node.parent)) if node.parent else None
                        nodes_data.append(
                            {
                                "id": node_uuids[id(node)],
                                "repository_id": self.repo_uuid,
                                "file_id": file_id,
                                "node_type": node.node_type,
                                "name": node.name,
                                "start_line": node.start_line,
                                "end_line": node.end_line,
                                "start_column": node.start_column,
                                "end_column": node.end_column,
                                "parent_node_id": parent_node_id,
                                "file_path": node.file_path,
                                "language": node.language,
                                # Phase 1 新增：框架感知字段
                                "tags": getattr(node, "tags", []),
                                "annotations": getattr(node, "annotations", []),
                                "qualified_name": getattr(node, "qualified_name", None),
                            }
                        )
                    if nodes_data:
                        result = await pipeline.ingest_ast_nodes(self.repo_uuid, nodes_data)
                        parsed_count += result.inserted_count
                except Exception as exc:
                    logger.warning("AST 解析失败: file=%s, error=%s", scanned_file.absolute_path, exc)
                    continue

            logger.info("AST 解析完成: %d 个节点", parsed_count)
            await db.commit()

    async def parse_ast_incremental(
        self, db: AsyncSession | None, progress_callback: Callable[[int, int, str], None] | None = None
    ) -> None:
        """增量 AST 解析"""
        if not self.files_to_parse:
            logger.info("增量 AST 解析: 无需解析的文件")
            return

        if db is not None:
            file_ids = [f.id for f in self.files_to_parse]
            deleted = await self.ast_node_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
            logger.info("增量 AST 解析: 删除旧节点 %d 条", deleted)

            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)
            parsed_count = 0

            for file_obj in self.files_to_parse:
                try:
                    parser = ParserFactory.get_parser(file_obj.language)
                    if parser is None:
                        continue

                    ast_nodes = parser.parse_file(file_obj.absolute_path)
                    # 为 parser 输出的 ASTNode 对象生成 UUID 映射（用于 parent_node_id 关联）
                    node_uuids = {id(node): uuid.uuid4() for node in ast_nodes}
                    nodes_data = []
                    for node in ast_nodes:
                        parent_node_id = node_uuids.get(id(node.parent)) if node.parent else None
                        nodes_data.append(
                            {
                                "repository_id": self.repo_uuid,
                                "file_id": file_obj.id,
                                "node_type": node.node_type,
                                "name": node.name,
                                "start_line": node.start_line,
                                "end_line": node.end_line,
                                "start_column": node.start_column,
                                "end_column": node.end_column,
                                "parent_node_id": parent_node_id,
                                "file_path": node.file_path,
                                "language": node.language,
                                # Phase 1 新增：框架感知字段
                                "tags": getattr(node, "tags", []),
                                "annotations": getattr(node, "annotations", []),
                                "qualified_name": getattr(node, "qualified_name", None),
                            }
                        )
                    if nodes_data:
                        result = await pipeline.ingest_ast_nodes(self.repo_uuid, nodes_data)
                        parsed_count += result.inserted_count
                except Exception as exc:
                    logger.warning("增量解析失败: file=%s, error=%s", file_obj.path, exc)
                    continue

            logger.info("增量 AST 解析完成: %d 个节点", parsed_count)
            await db.commit()
            return

        async with async_session_factory() as db:
            file_ids = [f.id for f in self.files_to_parse]
            deleted = await self.ast_node_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
            logger.info("增量 AST 解析: 删除旧节点 %d 条", deleted)

            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)
            parsed_count = 0

            for file_obj in self.files_to_parse:
                try:
                    parser = ParserFactory.get_parser(file_obj.language)
                    if parser is None:
                        continue

                    ast_nodes = parser.parse_file(file_obj.absolute_path)
                    nodes_data = []
                    for node in ast_nodes:
                        parent_id = getattr(node, "parent_id", None)
                        nodes_data.append(
                            {
                                "repository_id": self.repo_uuid,
                                "file_id": file_obj.id,
                                "node_type": node.node_type,
                                "name": node.name,
                                "start_line": node.start_line,
                                "end_line": node.end_line,
                                "start_column": node.start_column,
                                "end_column": node.end_column,
                                "parent_node_id": parent_id,
                                "file_path": node.file_path,
                                "language": node.language,
                                # Phase 1 新增：框架感知字段
                                "tags": getattr(node, "tags", []),
                                "annotations": getattr(node, "annotations", []),
                                "qualified_name": getattr(node, "qualified_name", None),
                            }
                        )
                    if nodes_data:
                        result = await pipeline.ingest_ast_nodes(self.repo_uuid, nodes_data)
                        parsed_count += result.inserted_count
                except Exception as exc:
                    logger.warning("增量解析失败: file=%s, error=%s", file_obj.path, exc)
                    continue

            logger.info("增量 AST 解析完成: %d 个节点", parsed_count)
            await db.commit()

    async def build_structures(
        self, db: AsyncSession | None, progress_callback: Callable[[int, int, str], None] | None = None
    ) -> None:
        """Step 4: 构建调用图和模块依赖图（全量）"""
        if db is not None:
            await self.call_edge_dao.delete_by_repository(db, self.repo_uuid)
            await self.module_dep_dao.delete_by_repository(db, self.repo_uuid)

            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

            call_graph_builder = CallGraphBuilder()
            call_edges = await call_graph_builder.build_data(self.repo_uuid, db=db)
            if call_edges:
                edge_result = await pipeline.ingest_call_edges(self.repo_uuid, call_edges)
                logger.info("调用图构建完成: edges=%d", edge_result.inserted_count)

            module_dep_builder = ModuleDependencyBuilder()
            deps = await module_dep_builder.build_data(self.repo_uuid, db=db)
            if deps:
                dep_result = await pipeline.ingest_module_deps(self.repo_uuid, deps)
                logger.info("模块依赖图构建完成: dependencies=%d", dep_result.inserted_count)

            await db.commit()
            return

        async with async_session_factory() as db:
            await self.call_edge_dao.delete_by_repository(db, self.repo_uuid)
            await self.module_dep_dao.delete_by_repository(db, self.repo_uuid)

            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

            call_graph_builder = CallGraphBuilder()
            call_edges = await call_graph_builder.build_data(self.repo_uuid, db=db)
            if call_edges:
                edge_result = await pipeline.ingest_call_edges(self.repo_uuid, call_edges)
                logger.info("调用图构建完成: edges=%d", edge_result.inserted_count)

            module_dep_builder = ModuleDependencyBuilder()
            deps = await module_dep_builder.build_data(self.repo_uuid, db=db)
            if deps:
                dep_result = await pipeline.ingest_module_deps(self.repo_uuid, deps)
                logger.info("模块依赖图构建完成: dependencies=%d", dep_result.inserted_count)

            await db.commit()

    async def build_structures_incremental(
        self, db: AsyncSession | None, progress_callback: Callable[[int, int, str], None] | None = None
    ) -> None:
        """增量结构分析"""
        if not self.files_to_parse:
            logger.info("增量结构分析: 无需分析的文件")
            return

        file_ids = [f.id for f in self.files_to_parse]
        file_paths = [f.path for f in self.files_to_parse]

        if db is not None:
            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

            deleted_edges = await self.call_edge_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
            deleted_deps = await self.module_dep_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
            logger.info("增量结构分析: 删除旧边 edges=%d, deps=%d", deleted_edges, deleted_deps)

            call_graph_builder = CallGraphBuilder()
            call_edges = await call_graph_builder.build_data_for_files(self.repo_uuid, db=db, file_ids=file_ids)
            if call_edges:
                edge_result = await pipeline.ingest_call_edges(self.repo_uuid, call_edges)
                logger.info("增量调用图构建完成: edges=%d", edge_result.inserted_count)

            module_dep_builder = ModuleDependencyBuilder()
            deps = await module_dep_builder.build_data_for_files(self.repo_uuid, file_paths=file_paths, db=db)
            if deps:
                dep_result = await pipeline.ingest_module_deps(self.repo_uuid, deps)
                logger.info("增量模块依赖图构建完成: dependencies=%d", dep_result.inserted_count)

            await db.commit()
            return

        async with async_session_factory() as db:
            pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

            deleted_edges = await self.call_edge_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
            deleted_deps = await self.module_dep_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
            logger.info("增量结构分析: 删除旧边 edges=%d, deps=%d", deleted_edges, deleted_deps)

            call_graph_builder = CallGraphBuilder()
            call_edges = await call_graph_builder.build_data_for_files(self.repo_uuid, db=db, file_ids=file_ids)
            if call_edges:
                edge_result = await pipeline.ingest_call_edges(self.repo_uuid, call_edges)
                logger.info("增量调用图构建完成: edges=%d", edge_result.inserted_count)

            module_dep_builder = ModuleDependencyBuilder()
            deps = await module_dep_builder.build_data_for_files(self.repo_uuid, file_paths=file_paths, db=db)
            if deps:
                dep_result = await pipeline.ingest_module_deps(self.repo_uuid, deps)
                logger.info("增量模块依赖图构建完成: dependencies=%d", dep_result.inserted_count)

            await db.commit()

    async def save_snapshot(self, db: AsyncSession | None = None) -> None:
        """保存分析快照"""
        if self.incremental_diff is None and self.mode != AnalysisMode.FULL.value:
            return

        try:
            if db is not None:
                files = await self.file_dao.get_by_repository(db, self.repo_uuid)
                snapshot_manager = SnapshotManager(db)
                count = await snapshot_manager.save_snapshot(self.repo_uuid, self.version_tag, files)
                await db.commit()
                logger.info("快照保存完成: repo=%s, version=%s, files=%d", self.repo_uuid, self.version_tag, count)
                return

            async with async_session_factory() as db:
                files = await self.file_dao.get_by_repository(db, self.repo_uuid)
                snapshot_manager = SnapshotManager(db)
                count = await snapshot_manager.save_snapshot(self.repo_uuid, self.version_tag, files)
                await db.commit()
                logger.info("快照保存完成: repo=%s, version=%s, files=%d", self.repo_uuid, self.version_tag, count)
        except Exception:
            logger.warning("快照保存失败", exc_info=True)
            if db is not None:
                with contextlib.suppress(Exception):
                    await db.rollback()

    async def complete(self, db: AsyncSession | None, knowledge_points_count: int = 0) -> None:
        """标记任务完成"""
        completed_at = datetime.now(UTC)

        await self._update_analysis_version(
            db,
            TaskStatus.COMPLETED,
            total_files=self.total_files,
            analyzed_files=self.total_files,
            knowledge_points_count=knowledge_points_count,
            completed_at=completed_at,
        )
        await self._set_repo_status(db, TaskStatus.COMPLETED.value)
        self._cleanup_redis_task_key()

        logger.info("分析任务完成: version=%s, mode=%s", self.version_tag, self.mode)

    async def fail(self, db: AsyncSession | None, error_message: str) -> None:
        """标记任务失败"""
        if self.version_id is not None:
            await self._update_analysis_version(
                db,
                TaskStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=error_message,
            )
        # 即使 version_id 为 None（版本记录创建前失败），也要更新仓库状态
        await self._set_repo_status(db, TaskStatus.FAILED.value)
        self._cleanup_redis_task_key()
        logger.error("分析任务失败: repo=%s, error=%s", self.repo_uuid, error_message)

    async def cancel(self, db: AsyncSession | None) -> None:
        """标记任务取消"""
        if self.version_id is None:
            return

        await self._update_analysis_version(
            db,
            TaskStatus.CANCELLED,
            completed_at=datetime.now(UTC),
        )
        await self._set_repo_status(db, TaskStatus.CANCELLED.value)

    async def get_in_progress_version(self, db: AsyncSession | None = None) -> tuple[Any, str | None]:
        """检查是否有未终态的分析版本"""
        version_dao = AnalysisVersionDAO()
        if db is not None:
            version = await version_dao.get_latest_in_progress(db, self.repo_uuid)
        else:
            async with async_session_factory() as db:
                version = await version_dao.get_latest_in_progress(db, self.repo_uuid)

        if version is None:
            return None, None

        status = version.status
        if status == TaskStatus.PENDING.value:
            return version, None
        elif status == TaskStatus.SCANNING.value:
            return version, "scan"
        elif status == TaskStatus.PARSING.value:
            return version, "ast"
        elif status == TaskStatus.ANALYZING_STRUCTURES.value:
            return version, "structures"
        elif status == TaskStatus.ANALYZING_MODULES.value:
            return version, "ai"
        elif status == TaskStatus.STORING.value:
            return version, "store"
        else:
            logger.warning("unexpected status=%s for in-progress version %s", status, version.version)
            return version, None

    async def cleanup_failed_step_data(self, db: AsyncSession | None, failed_status: str) -> None:
        """清理失败步骤的残留数据"""
        if db is not None:
            await self._cleanup_failed_step_data_inner(db, failed_status)
            await db.commit()
            return

        async with async_session_factory() as db:
            await self._cleanup_failed_step_data_inner(db, failed_status)
            await db.commit()

    async def _cleanup_failed_step_data_inner(self, db: AsyncSession, failed_status: str) -> None:
        """cleanup_failed_step_data 内部逻辑（不含 commit）"""
        if failed_status == TaskStatus.PARSING.value:
            ast_dao = AstNodeDAO()
            deleted = await ast_dao.delete_by_repository(db, self.repo_uuid)
            logger.info("清理失败 AST 数据: deleted=%d", deleted)

        elif failed_status == TaskStatus.ANALYZING_STRUCTURES.value:
            call_edge_dao = CallEdgeDAO()
            module_dep_dao = ModuleDependencyDAO()
            deleted_edges = await call_edge_dao.delete_by_repository(db, self.repo_uuid)
            deleted_deps = await module_dep_dao.delete_by_repository(db, self.repo_uuid)
            logger.info("清理失败结构数据: edges=%d, deps=%d", deleted_edges, deleted_deps)

        elif failed_status == TaskStatus.PENDING.value:
            file_dao = FileDAO()
            deleted = await file_dao.delete_by_repository(db, self.repo_uuid)
            logger.info("清理失败文件数据: deleted=%d", deleted)

        elif failed_status == TaskStatus.FAILED.value:
            # 失败状态：清理所有可能残留的数据
            ast_dao = AstNodeDAO()
            deleted_ast = await ast_dao.delete_by_repository(db, self.repo_uuid)
            call_edge_dao = CallEdgeDAO()
            module_dep_dao = ModuleDependencyDAO()
            deleted_edges = await call_edge_dao.delete_by_repository(db, self.repo_uuid)
            deleted_deps = await module_dep_dao.delete_by_repository(db, self.repo_uuid)
            file_dao = FileDAO()
            deleted_files = await file_dao.delete_by_repository(db, self.repo_uuid)
            logger.info(
                "清理失败仓库全部数据: ast=%d, edges=%d, deps=%d, files=%d",
                deleted_ast,
                deleted_edges,
                deleted_deps,
                deleted_files,
            )

    def run(self) -> dict[str, Any]:
        """执行完整分析流程（由 Celery Worker 调用）"""
        try:
            return asyncio.run(self._run_async())
        except CancelledError:
            self._cleanup_redis_task_key()
            raise
        except Exception as exc:
            asyncio.run(self.fail(None, str(exc)))
            raise

    async def _run_async(self) -> dict[str, Any]:
        """
        异步执行完整分析流程（P2-FixP7: 共享 session）

        使用单一 session 上下文贯穿整个分析流程，避免每个步骤独立创建数据库连接。
        仅在需要独立事务的边界操作（如断点续跑恢复）时使用独立 session。
        """
        existing_version, skip_to_step = await self.get_in_progress_version()

        if existing_version is not None:
            logger.info(
                "发现进行中版本: repo=%s, version=%s, status=%s, skip_to=%s",
                self.repo_uuid,
                existing_version.version,
                existing_version.status,
                skip_to_step,
            )
            self.version_id = existing_version.id
            self.version_tag = existing_version.version
            self.total_files = existing_version.total_files

            if existing_version.status == TaskStatus.FAILED.value:
                # 失败恢复：使用独立 session 清理数据
                await self.cleanup_failed_step_data(None, existing_version.status)
                await self._update_analysis_version(None, TaskStatus.SCANNING)
                skip_to_step = None
        else:
            logger.info("开始新分析任务: repo=%s, version=%s, mode=%s", self.repo_uuid, self.version_tag, self.mode)

        # P2-FixP7：使用单一共享 session 贯穿整个分析流程
        async with async_session_factory() as shared_db:
            # 初始化：创建版本记录（首次）
            if self.version_id is None:
                await self._do_analysis_setup(shared_db)

            # 断点续跑恢复
            if skip_to_step == "scan":
                logger.info("断点续跑: 跳过扫描，从 AST 解析开始")
                if not await self._reconstruct_scan_result(shared_db):
                    logger.error("断点续跑: 文件中无数据，无法跳过扫描，从头开始")
                    skip_to_step = None
            elif skip_to_step != "scan":
                # Step 2: 扫描文件
                self.progress_manager.update(TaskStatus.SCANNING, 10.0, 0, self.total_files)
                if not await self.scan_files(shared_db):
                    raise ValueError(f"Repository {self.repo_uuid} not found for scanning")

            # 增量判断
            do_full_analysis = self.mode == AnalysisMode.FULL.value
            if not do_full_analysis:
                do_full_analysis = not await self.compute_incremental_diff(shared_db)

            # Step 3: AST 解析
            if skip_to_step != "ast":
                self.progress_manager.update(TaskStatus.PARSING, 25.0, 0, self.total_files)
                await self._update_analysis_version(shared_db, TaskStatus.PARSING)

                if self.task_id:

                    def _parsing_progress(current: int, total: int, stage: str) -> None:
                        self.progress_manager.update(
                            TaskStatus.PARSING, 25.0 + (current / max(total, 1)) * 10, current, total
                        )

                    parsing_progress = _parsing_progress
                else:
                    parsing_progress = None

                if do_full_analysis:
                    await self.parse_ast(shared_db, progress_callback=parsing_progress)
                elif self.files_to_parse:
                    await self.parse_ast_incremental(shared_db, progress_callback=parsing_progress)

            # Step 4: 结构分析
            if skip_to_step != "structures":
                self.progress_manager.update(TaskStatus.ANALYZING_STRUCTURES, 50.0, self.total_files, self.total_files)
                await self._update_analysis_version(
                    shared_db, TaskStatus.ANALYZING_STRUCTURES, analyzed_files=self.total_files
                )

                if self.task_id:

                    def _structures_progress(current: int, total: int, stage: str) -> None:
                        self.progress_manager.update(
                            TaskStatus.ANALYZING_STRUCTURES,
                            50.0 + (current / max(total, 1)) * 10,
                            current,
                            total,
                        )

                    structures_progress = _structures_progress
                else:
                    structures_progress = None

                try:
                    if do_full_analysis:
                        await self.build_structures(shared_db, progress_callback=structures_progress)
                    elif self.files_to_parse:
                        await self.build_structures_incremental(shared_db, progress_callback=structures_progress)
                except Exception:
                    logger.exception("结构分析失败")
                    await shared_db.rollback()

            # Step 5: AI 分析（Phase 3）
            if skip_to_step != "ai":
                self.progress_manager.update(TaskStatus.ANALYZING_MODULES, 60.0, self.total_files, self.total_files)
                await self._update_analysis_version(
                    shared_db, TaskStatus.ANALYZING_MODULES, analyzed_files=self.total_files
                )
                knowledge_points_count = 0
            else:
                knowledge_points_count = 0

            # Step 6: 存储结果
            self.progress_manager.update(
                TaskStatus.STORING, 80.0, self.total_files, self.total_files, knowledge_points_count
            )
            await self._update_analysis_version(
                shared_db,
                TaskStatus.STORING,
                analyzed_files=self.total_files,
                knowledge_points_count=knowledge_points_count,
            )

            # 保存快照
            await self.save_snapshot(shared_db)

            # Step 7: 完成
            await self.complete(shared_db, knowledge_points_count=knowledge_points_count)

        return {
            "version_id": str(self.version_id),
            "version_tag": self.version_tag,
            "status": TaskStatus.COMPLETED.value,
        }
