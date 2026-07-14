"""
分析任务 — Celery Worker 执行逻辑

提供 run_analysis 任务，在后台异步执行代码仓库的分析流程。

P2-FixP5 重构：
- run_analysis 委托给 AnalysisOrchestrator，消除双重实现

P2-FixP6 重构（D-1 修复）：
- 移除所有已被 Orchestrator 替代的死代码（辅助函数、断点续跑辅助等）
- 移除未使用的 _STATUS_TO_STEP 字典
- CancelledError 统一从 exceptions.py 导入（Q-3 修复）
"""

import logging
from typing import Any
from uuid import UUID

import redis

from codeinsight.constants.redis_keys import task_cancel_key
from codeinsight.db.redis_client import get_redis_client
from codeinsight.db.session import async_session_factory
from codeinsight.exceptions import CancelledError
from codeinsight.parsers import ParserFactory
from codeinsight.pipelines.structure_pipeline import StructureDataPipeline
from codeinsight.repositories import AstNodeDAO, FileDAO
from codeinsight.schemas import AnalysisMode, TaskStatus
from codeinsight.services import IncrementalAnalyzer, SnapshotManager
from codeinsight.tasks.analysis_orchestrator import AnalysisOrchestrator

from . import celery_app

logger = logging.getLogger(__name__)


# ================================================================
# 进度更新辅助（被 analysis_orchestrator.py 使用）
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
# 取消检查辅助（被测试使用）
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
        cancelled = client.get(task_cancel_key(task_id))
        if cancelled:
            client.delete(task_cancel_key(task_id))
            logger.info("检测到取消标志，终止任务: task_id=%s", task_id)
            raise CancelledError(f"Task {task_id} was cancelled by user")
    except redis.RedisError as exc:
        logger.warning("Redis 取消检查失败: %s", exc)


# ================================================================
# 增量分析辅助（被测试使用，生产环境由 Orchestrator 内部方法替代）
# ================================================================


async def _compute_incremental_diff(
    repo_uuid: UUID,
    version_tag: str,
) -> Any | None:
    """
    计算增量分析差异（仅在 INCREMENTAL 模式下调用）

    Args:
        repo_uuid: 仓库 UUID
        version_tag: 当前版本标签

    Returns:
        IncrementalDiff 或 None（全量模式时）
    """
    from codeinsight.models import FileModel

    analyzer = IncrementalAnalyzer()

    # 获取最新快照版本
    async with async_session_factory() as db:
        snapshot_manager = SnapshotManager(db)
        latest_version = await snapshot_manager.get_latest_version(repo_uuid)

        # 获取当前文件列表
        file_dao = FileDAO()
        current_files: list[FileModel] = await file_dao.get_by_repository(db, repo_uuid)

        # 计算差异
        diff = await analyzer.compute_diff(repo_uuid, current_files, latest_version)
        return diff


async def _parse_and_store_ast_incremental(
    repo_uuid: UUID,
    files_to_parse: list[Any],
    progress_callback: Any = None,
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
                            # Phase 1 新增：框架感知字段
                            "tags": getattr(node, "tags", []),
                            "annotations": getattr(node, "annotations", []),
                            "qualified_name": getattr(node, "qualified_name", None),
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
