"""
分析任务 — Celery Worker 执行逻辑

提供 run_analysis 任务，在后台异步执行代码仓库的分析流程。

P2-03 阶段接入：
- Step 2: 存储扫描结果到 files 表
- Step 3: AST 解析并存储到 ast_nodes 表

P2-04 阶段接入：
- Step 4: 构建调用图和模块依赖图

P2-05 阶段接入：
- 使用 StructureDataPipeline 统一管理入库（校验 + 批量 + 进度回调）

P2-06 阶段接入：
- 增量分析模式（基于 content_hash 的变更检测 + 依赖传播）

P2-FixP5 重构：
- run_analysis 委托给 AnalysisOrchestrator，消除双重实现
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import redis

from codeinsight.analyzers import CallGraphBuilder, ModuleDependencyBuilder
from codeinsight.db.redis_client import get_redis_client
from codeinsight.db.session import async_session_factory
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
from codeinsight.schemas import AnalysisMode, TaskStatus
from codeinsight.services import IncrementalAnalyzer, IncrementalDiff, SnapshotManager
from codeinsight.tasks.analysis_orchestrator import AnalysisOrchestrator

from . import celery_app

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(UTC)


# ================================================================
# 取消检查辅助
# ================================================================


def _check_cancelled(task_instance: Any, task_id: str) -> None:
    """
    检查 Redis 中是否存在取消标志，存在则抛出 CancelledError 终止任务。

    Args:
        task_instance: Celery task 实例（self）
        task_id: Celery 任务 ID

    Raises:
        CancelledError: 当检测到取消标志时
    """
    try:
        client = get_redis_client()
        cancelled = client.get(f"task:{task_id}:cancel")
        if cancelled:
            client.delete(f"task:{task_id}:cancel")
            logger.info("检测到取消标志，终止任务: task_id=%s", task_id)
            raise CancelledError(f"Task {task_id} was cancelled by user")
    except redis.RedisError as exc:
        logger.warning("Redis 取消检查失败: %s", exc)


class CancelledError(Exception):
    """用户手动取消任务的异常"""

    pass


# ================================================================
# 进度更新辅助
# ================================================================


def _update_progress(
    task_instance: Any | None,
    status: TaskStatus,
    percent: float,
    files_processed: int = 0,
    files_total: int = 0,
    knowledge_points_found: int = 0,
) -> None:
    """
    更新 Celery 任务状态并推送到 Redis

    Args:
        task_instance: Celery task 实例（self），可为 None（开发模式）
        status: 当前任务状态
        percent: 完成百分比 0.0-100.0
        files_processed: 已处理文件数
        files_total: 总文件数
        knowledge_points_found: 已发现知识点数
    """
    if task_instance is None:
        return
    task_instance.update_state(
        state=status.value,
        meta={
            "current_step": status.value,
            "percent": percent,
            "files_processed": files_processed,
            "files_total": files_total,
            "knowledge_points_found": knowledge_points_found,
        },
    )


# ================================================================
# 数据库操作封装（同步调用异步 DAO）
# ================================================================


async def _do_analysis_setup(
    repository_id: UUID,
    version_tag: str,
) -> dict[str, Any]:
    """
    一次性完成版本创建 + 仓库状态更新（共享同一个 session）

    Returns:
        {version_id, total_files}
    """
    version_dao = AnalysisVersionDAO()
    repo_dao = RepositoryDAO()

    async with async_session_factory() as db:
        repo = await repo_dao.get_by_id(db, repository_id)
        if repo is None:
            raise ValueError(f"Repository {repository_id} not found")

        # 创建分析版本记录（total_files 将在扫描步骤更新）
        total_files = 0
        version = await version_dao.create(
            db,
            {
                "repository_id": repository_id,
                "version": version_tag,
                "status": TaskStatus.PENDING.value,
                "total_files": total_files,
                "analyzed_files": 0,
                "knowledge_points_count": 0,
                "started_at": _utcnow(),
            },
        )

        # 更新仓库状态为 analyzing（使用字符串字面量，RepositoryModel.status 是 Column[str]）
        repo.status = "analyzing"
        await db.flush()
        await db.commit()

        return {"version_id": version.id, "total_files": total_files}


async def _set_repo_status(repo_uuid: UUID, status: str) -> None:
    """
    更新仓库状态为最终状态（completed / failed / cancelled）

    Args:
        repo_uuid: 仓库 UUID
        status: 新状态值
    """
    dao = RepositoryDAO()
    async with async_session_factory() as db:
        repo = await dao.get_by_id(db, repo_uuid)
        if repo is not None:
            repo.status = status
            await db.flush()
            await db.commit()


async def _update_analysis_version(
    version_id: UUID,
    status: TaskStatus,
    total_files: int | None = None,
    analyzed_files: int | None = None,
    knowledge_points_count: int | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
) -> None:
    """
    更新分析版本的状态和统计数据

    Args:
        version_id: 版本 UUID
        status: 当前任务状态
        total_files: 文件总数（可选）
        analyzed_files: 已分析文件数（可选）
        knowledge_points_count: 知识点数（可选）
        completed_at: 完成时间（可选）
        error_message: 错误信息（可选）
    """
    version_dao = AnalysisVersionDAO()
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

    async with async_session_factory() as db:
        await version_dao.update(db, version_id, update_data)
        await db.commit()


async def _update_repository_stats(
    repo_uuid: UUID,
    total_files: int,
    total_lines: int,
    language_distribution: dict[str, int],
    current_version: str,
    knowledge_points_count: int = 0,
) -> None:
    """
    更新仓库的统计信息（扫描完成后调用）

    Args:
        repo_uuid: 仓库 UUID
        total_files: 文件总数
        total_lines: 总行数
        language_distribution: 语言分布
        current_version: 当前分析版本标签
        knowledge_points_count: 知识点数
    """
    dao = RepositoryDAO()
    async with async_session_factory() as db:
        repo = await dao.get_by_id(db, repo_uuid)
        if repo is not None:
            repo.file_count = total_files
            repo.line_count = total_lines
            repo.language_distribution = language_distribution
            repo.current_version = current_version
            repo.knowledge_points_count = knowledge_points_count
            await db.flush()
            await db.commit()


async def _store_files_to_db(repo_uuid: UUID, files_data: list[dict]) -> None:
    """
    存储扫描结果到 files 表

    Args:
        repo_uuid: 仓库 UUID
        files_data: 文件数据列表
    """
    file_dao = FileDAO()
    async with async_session_factory() as db:
        # 删除旧文件记录
        await file_dao.delete_by_repository(db, repo_uuid)
        # 批量创建新文件
        if files_data:
            repo_files = await file_dao.create_many(db, repo_uuid, files_data)
            logger.info("文件存储完成: %d 个文件", len(repo_files))
            await db.commit()


async def _parse_and_store_ast(repo_uuid: UUID, scan_result: Any, progress_callback=None) -> None:
    """
    AST 解析并通过 StructureDataPipeline 入库 ast_nodes 表

    Args:
        repo_uuid: 仓库 UUID
        scan_result: 扫描结果
        progress_callback: 进度回调函数 (current, total, stage) -> None
    """
    file_dao = FileDAO()
    ast_dao = AstNodeDAO()

    async with async_session_factory() as db:
        # 删除旧 AST 节点
        await ast_dao.delete_by_repository(db, repo_uuid)

        # 构建 file_id 映射
        repo_files = await file_dao.get_by_repository(db, repo_uuid)
        file_id_map: dict[str, uuid.UUID] = {f.path: f.id for f in repo_files}

        # 创建入库管道
        pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

        parsed_count = 0
        for scanned_file in scan_result.files:
            try:
                parser = ParserFactory.get_parser(scanned_file.language)
                if parser is None:
                    logger.warning("不支持的语言: %s", scanned_file.language)
                    continue

                ast_nodes = parser.parse_file(scanned_file.absolute_path)

                file_id = file_id_map.get(scanned_file.path)
                if file_id is None:
                    logger.warning("文件未找到: %s", scanned_file.path)
                    continue

                nodes_data = []
                for node in ast_nodes:
                    parent_id = getattr(node, "parent_id", None)
                    nodes_data.append(
                        {
                            "repository_id": repo_uuid,
                            "file_id": file_id,
                            "node_type": node.node_type,
                            "name": node.name,
                            "start_line": node.start_line,
                            "end_line": node.end_line,
                            "start_column": node.start_column,
                            "end_column": node.end_column,
                            "parent_node_id": parent_id,
                            "file_path": node.file_path,
                            "language": node.language,
                        }
                    )
                if nodes_data:
                    result = await pipeline.ingest_ast_nodes(repo_uuid, nodes_data)
                    parsed_count += result.inserted_count
            except Exception as exc:
                logger.warning("AST 解析失败: file=%s, error=%s", scanned_file.absolute_path, exc)
                continue

        logger.info("AST 解析完成: %d 个节点", parsed_count)
        await db.commit()


async def _build_structures(repo_uuid: UUID, task_self: Any, progress_callback=None) -> None:
    """
    构建调用图和模块依赖图（通过 StructureDataPipeline 统一管理入库）

    修复：在构建前删除旧数据，避免重复累积（影响断点续跑的幂等性）。

    Args:
        repo_uuid: 仓库 UUID
        task_self: Celery task 实例（用于取消检查）
        progress_callback: 进度回调函数
    """
    async with async_session_factory() as db:
        # 先清理旧数据，保证幂等性（断点续跑多次执行不会重复累积）
        call_edge_dao = CallEdgeDAO()
        module_dep_dao = ModuleDependencyDAO()
        await call_edge_dao.delete_by_repository(db, repo_uuid)
        await module_dep_dao.delete_by_repository(db, repo_uuid)

        # 创建入库管道
        pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

        # 构建调用图数据（由 builder 返回数据，由 pipeline 写入）
        call_graph_builder = CallGraphBuilder()
        call_edges = await call_graph_builder.build_data(repo_uuid, db=db)
        if call_edges:
            edge_result = await pipeline.ingest_call_edges(repo_uuid, call_edges)
            logger.info("调用图构建完成: edges=%d", edge_result.inserted_count)
        else:
            logger.info("调用图构建完成: edges=0")

        # 构建模块依赖数据
        module_dep_builder = ModuleDependencyBuilder()
        deps = await module_dep_builder.build_data(repo_uuid, db=db)
        if deps:
            dep_result = await pipeline.ingest_module_deps(repo_uuid, deps)
            logger.info("模块依赖图构建完成: dependencies=%d", dep_result.inserted_count)
        else:
            logger.info("模块依赖图构建完成: dependencies=0")

        await db.commit()


# ================================================================
# 增量分析辅助（P2-06）
# ================================================================


async def _compute_incremental_diff(
    repo_uuid: UUID,
    version_tag: str,
) -> IncrementalDiff | None:
    """
    计算增量分析差异（仅在 INCREMENTAL 模式下调用）

    Args:
        repo_uuid: 仓库 UUID
        version_tag: 当前版本标签

    Returns:
        IncrementalDiff 或 None（全量模式时）
    """
    analyzer = IncrementalAnalyzer()

    # 获取最新快照版本
    async with async_session_factory() as db:
        snapshot_manager = SnapshotManager(db)
        latest_version = await snapshot_manager.get_latest_version(repo_uuid)

        # 获取当前文件列表
        file_dao = FileDAO()
        current_files = await file_dao.get_by_repository(db, repo_uuid)

        # 计算差异
        diff = await analyzer.compute_diff(repo_uuid, current_files, latest_version)
        return diff


async def _parse_and_store_ast_incremental(
    repo_uuid: UUID,
    files_to_parse: list[FileModel],
    progress_callback=None,
) -> None:
    """
    增量 AST 解析：只解析变更文件

    Args:
        repo_uuid: 仓库 UUID
        files_to_parse: 需要分析的文件列表
        progress_callback: 进度回调函数 (current, total, stage) -> None
    """
    if not files_to_parse:
        logger.info("增量 AST 解析: 无需解析的文件")
        return

    ast_dao = AstNodeDAO()

    async with async_session_factory() as db:
        # 获取需要分析的文件 ID
        file_ids = [f.id for f in files_to_parse]

        # 只删除这些文件的旧节点
        deleted = await ast_dao.delete_by_file_ids(db, repo_uuid, file_ids)
        logger.info("增量 AST 解析: 删除旧节点 %d 条", deleted)

        # 创建入库管道
        pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

        parsed_count = 0
        for file_obj in files_to_parse:
            try:
                parser = ParserFactory.get_parser(file_obj.language)
                if parser is None:
                    logger.warning("不支持的语言: %s", file_obj.language)
                    continue

                ast_nodes = parser.parse_file(file_obj.absolute_path)

                nodes_data = []
                for node in ast_nodes:
                    parent_id = getattr(node, "parent_id", None)
                    nodes_data.append(
                        {
                            "repository_id": repo_uuid,
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
                        }
                    )
                if nodes_data:
                    result = await pipeline.ingest_ast_nodes(repo_uuid, nodes_data)
                    parsed_count += result.inserted_count
            except Exception as exc:
                logger.warning("增量解析失败: file=%s, error=%s", file_obj.path, exc)
                continue

        logger.info("增量 AST 解析完成: %d 个节点", parsed_count)
        await db.commit()


async def _build_structures_incremental(
    repo_uuid: UUID,
    files_to_parse: list[FileModel],
    progress_callback=None,
) -> None:
    """
    增量结构分析：只重建变更文件相关的调用边和依赖边

    Args:
        repo_uuid: 仓库 UUID
        files_to_parse: 需要分析的文件列表
        progress_callback: 进度回调函数
    """
    if not files_to_parse:
        logger.info("增量结构分析: 无需分析的文件")
        return

    file_ids = [f.id for f in files_to_parse]
    file_paths = [f.path for f in files_to_parse]

    async with async_session_factory() as db:
        # 创建入库管道
        pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

        # 删除变更文件相关的旧边
        call_edge_dao = CallEdgeDAO()
        module_dep_dao = ModuleDependencyDAO()
        deleted_edges = await call_edge_dao.delete_by_file_ids(db, repo_uuid, file_ids)
        deleted_deps = await module_dep_dao.delete_by_file_ids(db, repo_uuid, file_ids)
        logger.info(
            "增量结构分析: 删除旧边 edges=%d, deps=%d",
            deleted_edges,
            deleted_deps,
        )

        # 重建调用图数据
        call_graph_builder = CallGraphBuilder()
        call_edges = await call_graph_builder.build_data_for_files(repo_uuid, db=db, file_ids=file_ids)
        if call_edges:
            edge_result = await pipeline.ingest_call_edges(repo_uuid, call_edges)
            logger.info("增量调用图构建完成: edges=%d", edge_result.inserted_count)

        # 重建模块依赖数据
        module_dep_builder = ModuleDependencyBuilder()
        deps = await module_dep_builder.build_data_for_files(repo_uuid, file_paths=file_paths, db=db)
        if deps:
            dep_result = await pipeline.ingest_module_deps(repo_uuid, deps)
            logger.info("增量模块依赖图构建完成: dependencies=%d", dep_result.inserted_count)

        await db.commit()


async def _save_analysis_snapshot(
    repo_uuid: UUID,
    version_tag: str,
) -> int:
    """
    保存分析快照（增量模式下调用）

    Args:
        repo_uuid: 仓库 UUID
        version_tag: 版本标签

    Returns:
        保存的快照记录数
    """
    async with async_session_factory() as db:
        file_dao = FileDAO()
        files = await file_dao.get_by_repository(db, repo_uuid)

        snapshot_manager = SnapshotManager(db)
        count = await snapshot_manager.save_snapshot(repo_uuid, version_tag, files)
        await db.commit()
        return count


# ================================================================
# 断点续跑辅助（P2-Resume）
# ================================================================


# 每个 step 对应的 status → 该 step 完成后才更新到下一个 status
# 断点续跑时，根据当前 status 判断需要执行哪些步骤
_STATUS_TO_STEP: dict[str, str] = {
    TaskStatus.PENDING.value: "setup",
    TaskStatus.SCANNING.value: "scan",
    TaskStatus.PARSING.value: "ast",
    TaskStatus.ANALYZING_STRUCTURES.value: "structures",
    TaskStatus.ANALYZING_MODULES.value: "ai",
    TaskStatus.STORING.value: "store",
}


async def _get_in_progress_version(repo_uuid: UUID) -> tuple[Any, str | None]:
    """
    检查是否有未终态的分析版本，用于断点续跑

    Returns:
        (version_model, skip_to_step) 元组
        - version_model: 当前版本（None 表示无进行中版本）
        - skip_to_step: 跳过到的步骤名
            "scan" → 跳过扫描，从 AST 解析开始
            "ast"  → 跳过解析，从结构构建开始
            "structures" → 跳过结构，从 AI 分析开始
            "ai"   → 跳过 AI，从存储开始
            "store" → 跳过存储，直接标记完成
            None → 从头开始
    """
    version_dao = AnalysisVersionDAO()
    async with async_session_factory() as db:
        version = await version_dao.get_latest_in_progress(db, repo_uuid)

    if version is None:
        return None, None

    status = version.status

    # status 表示"当前正在执行"的步骤
    # 例如 status=parsing 表示扫描已完成，当前/刚完成了 AST 解析
    # 所以应从结构的下一步开始
    if status == TaskStatus.PENDING.value:
        return version, None
    elif status == TaskStatus.SCANNING.value:
        # 扫描已完成，跳过扫描
        return version, "scan"
    elif status == TaskStatus.PARSING.value:
        # 解析已完成，跳过 AST
        return version, "ast"
    elif status == TaskStatus.ANALYZING_STRUCTURES.value:
        # 结构构建已完成
        return version, "structures"
    elif status == TaskStatus.ANALYZING_MODULES.value:
        # AI 分析已完成
        return version, "ai"
    elif status == TaskStatus.STORING.value:
        # 存储已完成
        return version, "store"
    else:
        # failed / cancelled / completed 不应出现在 in_progress 查询中
        logger.warning("unexpected status=%s for in-progress version %s", status, version.version)
        return version, None


async def _cleanup_failed_step_data(
    repo_uuid: UUID,
    failed_status: str,
) -> dict[str, int]:
    """
    清理失败步骤写入的残留数据

    根据失败时的 status，删除该步骤可能写入的部分数据：
    - parsing 失败 → 清空 ast_nodes
    - analyzing_structures 失败 → 清空 call_edges + module_dependencies
    - analyzing_modules 失败 → 无数据库写入（仅 AI 处理），无需清理
    - 其他步骤 → 无需清理或清理文件

    Args:
        repo_uuid: 仓库 UUID
        failed_status: 失败时的 status

    Returns:
        清理统计 {step: deleted_count, ...}
    """
    cleanup_stats: dict[str, int] = {}

    async with async_session_factory() as db:
        if failed_status == TaskStatus.PARSING.value:
            ast_dao = AstNodeDAO()
            deleted = await ast_dao.delete_by_repository(db, repo_uuid)
            cleanup_stats["ast_nodes"] = deleted
            logger.info("清理失败 AST 数据: deleted=%d", deleted)

        elif failed_status == TaskStatus.ANALYZING_STRUCTURES.value:
            call_edge_dao = CallEdgeDAO()
            module_dep_dao = ModuleDependencyDAO()
            deleted_edges = await call_edge_dao.delete_by_repository(db, repo_uuid)
            deleted_deps = await module_dep_dao.delete_by_repository(db, repo_uuid)
            cleanup_stats["call_edges"] = deleted_edges
            cleanup_stats["module_deps"] = deleted_deps
            logger.info(
                "清理失败结构数据: edges=%d, deps=%d",
                deleted_edges,
                deleted_deps,
            )

        elif failed_status == TaskStatus.PENDING.value:
            # pending 阶段可能已写入 files，清理文件记录
            file_dao = FileDAO()
            deleted = await file_dao.delete_by_repository(db, repo_uuid)
            cleanup_stats["files"] = deleted
            logger.info("清理失败文件数据: deleted=%d", deleted)

        await db.commit()

    return cleanup_stats


# ================================================================
# 主分析任务
# ================================================================


@celery_app.task(
    name="tasks.run_analysis",
    bind=True,
    queue="analysis",
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
)
def run_analysis(
    self,
    repository_id: str,
    mode: str = AnalysisMode.FULL.value,
    agents: list[str] | None = None,
) -> dict[str, Any]:
    """
    异步分析任务

    流程（骨架）：
    1. 创建分析版本记录 → pending
    2. 扫描文件列表 → scanning
    3. AST 解析 → parsing（Phase 2 接入）
    4. 结构分析 → analyzing_structures（调用图 + 模块依赖，P2-04 接入）
    5. AI 分析 → analyzing_modules（Phase 3 接入）
    6. 存储结果 → storing（Phase 3 接入）
    7. 标记完成 → completed

    Args:
        self: Celery task 实例
        repository_id: 仓库 UUID（字符串形式）
        mode: 分析模式（full / incremental）
        agents: 启用的 Agent 类型列表

    Returns:
        包含版本信息的字典
    """
    repo_uuid = UUID(repository_id)
    orchestrator = AnalysisOrchestrator(repo_uuid=repo_uuid, mode=mode, task_instance=self)
    return orchestrator.run()
