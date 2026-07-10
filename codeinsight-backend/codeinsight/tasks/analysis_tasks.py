"""
分析任务 — Celery Worker 执行逻辑

提供 run_analysis 任务，在后台异步执行代码仓库的分析流程。

P1-08 阶段为骨架实现：建立任务框架和进度推送通道，
实际扫描/解析/分析逻辑在 Phase 2/3 逐步接入。
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from codeinsight.db.session import async_session_factory
from codeinsight.repositories import AnalysisVersionDAO, RepositoryDAO
from codeinsight.schemas import AnalysisMode, TaskStatus

from . import celery_app

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    """返回当前 UTC 时间 ISO 字符串"""
    return datetime.now(UTC).isoformat()


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

        # 更新仓库状态为 analyzing
        repo.status = TaskStatus.ANALYZING.value
        await db.flush()
        await db.commit()

        return {"version_id": version.id, "total_files": total_files}


async def _set_repo_status(repo_uuid: UUID, status: str) -> None:
    """
    直接修改 ORM 对象来更新仓库状态（RepositoryUpdate Schema 不含 status 字段）

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

    logger.info("开始分析任务: repo=%s, version=%s, mode=%s", repository_id, version_tag, mode)

    try:
        # ---- Step 1: 创建版本记录（单 session 完成） ----
        setup_result = asyncio.run(_do_analysis_setup(repo_uuid, version_tag))
        version_id = setup_result["version_id"]
        total_files = setup_result["total_files"]

        # ---- Step 2: 扫描文件 ----
        _update_progress(self, TaskStatus.SCANNING, 10.0, 0, total_files)

        # Phase 2: 此处接入 GitPython 文件扫描逻辑
        # scanned_files = scan_repository(repo.path)
        # total_files = len(scanned_files)

        # ---- Step 3: AST 解析 ----
        _update_progress(self, TaskStatus.PARSING, 25.0, 0, total_files)

        # Phase 2: 此处接入 Tree-sitter 解析逻辑
        # structures = parse_all_files(scanned_files)

        # ---- Step 4: AI 分析 ----
        _update_progress(self, TaskStatus.ANALYZING_MODULES, 50.0, total_files, total_files)

        # Phase 3: 此处接入 LangGraph Agent 分析逻辑
        # knowledge_points = analyze_with_agents(structures, agents)

        # ---- Step 5: 存储结果 ----
        _update_progress(self, TaskStatus.STORING, 80.0, total_files, total_files, 0)

        # Phase 3: 此处接入向量存储和全文索引逻辑
        # await store_knowledge_points(knowledge_points)

        # ---- Step 6: 完成 ----
        _update_progress(self, TaskStatus.COMPLETED, 100.0, total_files, total_files, 0)

        asyncio.run(_set_repo_status(repo_uuid, TaskStatus.COMPLETED.value))

        logger.info("分析任务完成: version=%s", version_tag)

        return {
            "version_id": str(version_id),
            "version_tag": version_tag,
            "status": TaskStatus.COMPLETED.value,
        }

    except Exception as exc:
        logger.exception("分析任务失败: repo=%s, error=%s", repository_id, exc)

        asyncio.run(_set_repo_status(repo_uuid, TaskStatus.FAILED.value))

        raise
