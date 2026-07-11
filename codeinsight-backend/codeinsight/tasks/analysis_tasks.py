"""
分析任务 — Celery Worker 执行逻辑

提供 run_analysis 任务，在后台异步执行代码仓库的分析流程。

P2-03 阶段接入：
- Step 2: 存储扫描结果到 files 表
- Step 3: AST 解析并存储到 ast_nodes 表
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from codeinsight.models import AnalysisVersionModel, RepositoryModel

import redis

from codeinsight.config import settings
from codeinsight.db.session import async_session_factory
from codeinsight.parsers import ParserFactory
from codeinsight.repositories import AnalysisVersionDAO, AstNodeDAO, FileDAO, RepositoryDAO
from codeinsight.scanners.git_scanner import GitScanner
from codeinsight.schemas import AnalysisMode, TaskStatus

from . import celery_app  # type: ignore[import-untyped]

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
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )
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

        # 扫描文件列表（骨架阶段 placeholder）
        total_files = 0  # Phase 2: GitPython 扫描

        # 创建分析版本记录
        version = await version_dao.create(db, {
            "repository_id": repository_id,
            "version": version_tag,
            "status": TaskStatus.PENDING.value,
            "total_files": total_files,
            "analyzed_files": 0,
            "knowledge_points_count": 0,
            "started_at": _utcnow(),
        })

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


async def _parse_and_store_ast(repo_uuid: UUID, scan_result: Any) -> None:
    """
    AST 解析并存储到 ast_nodes 表

    Args:
        repo_uuid: 仓库 UUID
        scan_result: 扫描结果
    """
    file_dao = FileDAO()
    ast_dao = AstNodeDAO()

    async with async_session_factory() as db:
        # 删除旧 AST 节点
        await ast_dao.delete_by_repository(db, repo_uuid)

        # 构建 file_id 映射
        repo_files = await file_dao.get_by_repository(db, repo_uuid)
        file_id_map: dict[str, uuid.UUID] = {f.path: f.id for f in repo_files}

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
                    nodes_data.append({
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
                    })
                if nodes_data:
                    await ast_dao.create_many(db, nodes_data)
                    parsed_count += len(nodes_data)
            except Exception as exc:
                logger.warning("AST 解析失败: file=%s, error=%s", scanned_file.absolute_path, exc)
                continue

        logger.info("AST 解析完成: %d 个节点", parsed_count)
        await db.commit()


# ================================================================
# 主分析任务
# ================================================================


@celery_app.task(
    name="tasks.run_analysis",
    bind=True,
    queue="analysis",
    acks_late=True,
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
    4. AI 分析 → analyzing_modules（Phase 3 接入）
    5. 存储结果 → storing（Phase 3 接入）
    6. 标记完成 → completed

    Args:
        self: Celery task 实例
        repository_id: 仓库 UUID（字符串形式）
        mode: 分析模式（full / incremental）
        agents: 启用的 Agent 类型列表

    Returns:
        包含版本信息的字典
    """
    repo_uuid = UUID(repository_id)
    version_tag = f"v{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:7]}"
    task_id = self.request.id if self else None  # type: ignore[attr-defined]

    logger.info("开始分析任务: repo=%s, version=%s, mode=%s", repository_id, version_tag, mode)

    try:
        # ---- Step 1: 创建版本记录（单 session 完成） ----
        setup_result = asyncio.run(_do_analysis_setup(repo_uuid, version_tag))
        version_id = setup_result["version_id"]
        total_files = setup_result["total_files"]

        # ---- Step 2: 扫描文件 ----
        _update_progress(self, TaskStatus.SCANNING, 10.0, 0, total_files)
        if task_id:
            _check_cancelled(self, task_id)

        # Phase 2: GitPython 文件扫描
        repo_dao = RepositoryDAO()
        repo = asyncio.run(repo_dao.get_by_id(async_session_factory(), repo_uuid))
        scan_result: Any = None
        if repo is not None:
            scanner = GitScanner(repo.path)
            scan_result = scanner.scan()
            total_files = scan_result.total_count
            logger.info("扫描完成: repo=%s, files=%d, lines=%d", repo.path, total_files, scan_result.total_lines)
            logger.info("语言分布: %s", scan_result.language_distribution)

            # 更新分析版本：同步扫描后的真实文件数和状态
            asyncio.run(_update_analysis_version(
                version_id,
                TaskStatus.SCANNING,
                total_files=total_files,
            ))

            # 更新仓库统计信息
            asyncio.run(_update_repository_stats(
                repo_uuid,
                total_files=total_files,
                total_lines=scan_result.total_lines,
                language_distribution=scan_result.language_distribution,
                current_version=version_tag,
            ))
        else:
            logger.error("仓库不存在，终止扫描: repo=%s", repo_uuid)
            raise ValueError(f"Repository {repo_uuid} not found for scanning")

        # Phase 2: 存储扫描结果到 files 表
        files_data = []
        for scanned_file in scan_result.files:
            files_data.append({
                "path": scanned_file.path,
                "absolute_path": scanned_file.absolute_path,
                "language": scanned_file.language,
                "line_count": scanned_file.line_count,
                "size_bytes": scanned_file.size_bytes,
                "content_hash": scanned_file.content_hash,
            })
        asyncio.run(_store_files_to_db(repo_uuid, files_data))

        # ---- Step 3: AST 解析 ----
        _update_progress(self, TaskStatus.PARSING, 25.0, 0, total_files)
        if task_id:
            _check_cancelled(self, task_id)

        # 更新分析版本状态为 parsing
        asyncio.run(_update_analysis_version(
            version_id,
            TaskStatus.PARSING,
        ))

        # Phase 2: AST 解析并存储到 ast_nodes 表
        asyncio.run(_parse_and_store_ast(repo_uuid, scan_result))

        # ---- Step 4: AI 分析 ----
        _update_progress(self, TaskStatus.ANALYZING_MODULES, 50.0, total_files, total_files)
        if task_id:
            _check_cancelled(self, task_id)

        # 更新分析版本状态为 analyzing_modules
        asyncio.run(_update_analysis_version(
            version_id,
            TaskStatus.ANALYZING_MODULES,
            analyzed_files=total_files,
        ))

        # Phase 3: 此处接入 LangGraph Agent 分析逻辑
        # knowledge_points = analyze_with_agents(structures, agents)
        knowledge_points_count = 0

        # ---- Step 5: 存储结果 ----
        _update_progress(self, TaskStatus.STORING, 80.0, total_files, total_files, knowledge_points_count)
        if task_id:
            _check_cancelled(self, task_id)

        # 更新分析版本状态为 storing
        asyncio.run(_update_analysis_version(
            version_id,
            TaskStatus.STORING,
            analyzed_files=total_files,
            knowledge_points_count=knowledge_points_count,
        ))

        # ---- Step 6: 完成 ----
        completed_at = _utcnow()
        _update_progress(self, TaskStatus.COMPLETED, 100.0, total_files, total_files, knowledge_points_count)

        # 持久化最终状态到数据库
        asyncio.run(_update_analysis_version(
            version_id,
            TaskStatus.COMPLETED,
            total_files=total_files,
            analyzed_files=total_files,
            knowledge_points_count=knowledge_points_count,
            completed_at=completed_at,
        ))
        asyncio.run(_set_repo_status(repo_uuid, TaskStatus.COMPLETED.value))

        logger.info("分析任务完成: version=%s", version_tag)

        return {
            "version_id": str(version_id),
            "version_tag": version_tag,
            "status": TaskStatus.COMPLETED.value,
        }

    except CancelledError as exc:
        logger.info("分析任务被用户取消: version=%s, error=%s", version_tag, exc)
        # 持久化取消状态到数据库
        try:
            asyncio.run(_update_analysis_version(
                version_id,
                TaskStatus.CANCELLED,
                completed_at=_utcnow(),
            ))
        except Exception:
            pass  # version_id 可能未初始化，静默处理
        asyncio.run(_set_repo_status(repo_uuid, TaskStatus.CANCELLED.value))
        raise

    except Exception as exc:
        logger.exception("分析任务失败: repo=%s, error=%s", repository_id, exc)
        # 持久化失败状态到数据库
        try:
            asyncio.run(_update_analysis_version(
                version_id,
                TaskStatus.FAILED,
                completed_at=_utcnow(),
                error_message=str(exc),
            ))
        except Exception:
            pass  # version_id 可能未初始化，静默处理
        asyncio.run(_set_repo_status(repo_uuid, TaskStatus.FAILED.value))

        raise
