"""
分析任务路由

提供分析任务的提交、查询、取消接口。

依赖 Celery 异步执行，任务状态通过 Redis result_backend 存储。
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import redis
from celery.result import AsyncResult  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.repositories import RepositoryDAO
from codeinsight.schemas import (
    AnalysisMode,
    AnalysisProgress,
    AnalysisTask,
    AnalyzeRequest,
    TaskStatus,
)
from codeinsight.tasks import celery_app
from codeinsight.tasks.analysis_tasks import run_analysis

logger = logging.getLogger(__name__)

router = APIRouter()

_MAPPING_TTL = 86400 * 7  # 映射保留 7 天


_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    """
    惰性创建并缓存 Redis 客户端（避免每次请求新建连接）

    Returns:
        Redis 客户端实例
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )
    return cast(redis.Redis, _redis_client)


def _utcnow() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(UTC)


def _lookup_repository(task_id: str) -> UUID:
    """
    根据 task_id 查找关联的 repository_id

    从 Redis 中读取 task_id → repository_id 映射。

    Args:
        task_id: Celery 任务 ID

    Returns:
        repository UUID，未找到则返回占位值
    """
    try:
        client = _get_redis_client()
        raw: Any = client.get(f"task:{task_id}:repo")
        if raw:
            return UUID(raw)
    except redis.RedisError:
        logger.warning("Redis 查询失败，使用占位 repository_id: task_id=%s", task_id)
    return UUID("00000000-0000-0000-0000-000000000000")


def _celery_result_to_task(task_id: str, repo_id: UUID, mode: AnalysisMode = AnalysisMode.FULL) -> AnalysisTask:
    """
    将 Celery AsyncResult 转换为 AnalysisTask Schema

    Args:
        task_id: Celery 任务 ID
        repo_id: 仓库 ID
        mode: 分析模式

    Returns:
        AnalysisTask 实例
    """
    result = AsyncResult(task_id, app=celery_app)

    # 确定状态映射
    if result.state == "PENDING":
        status = TaskStatus.PENDING
    elif result.state == "STARTED":
        # 从 meta 中获取实际进度
        meta = result.info or {}
        step: str | None = meta.get("current_step")
        try:
            status = TaskStatus(step) if step else TaskStatus.SCANNING
        except ValueError:
            status = TaskStatus.SCANNING
    elif result.state == "SUCCESS":
        status = TaskStatus.COMPLETED
    elif result.state == "FAILURE":
        status = TaskStatus.FAILED
    else:
        status = TaskStatus.PENDING

    # 提取进度信息（result.info 可能是 Exception 而非 dict）
    meta = result.info or {}
    if not isinstance(meta, dict):
        meta = {}
    progress = AnalysisProgress(
        current_step=status,
        percent=meta.get("percent", 0.0),
        files_processed=meta.get("files_processed", 0),
        files_total=meta.get("files_total", 0),
        knowledge_points_found=meta.get("knowledge_points_found", 0),
    )

    submitted_at = _utcnow()
    started_at_raw = meta.get("started_at") if status != TaskStatus.PENDING else None
    started_at: datetime | None = (
        datetime.fromisoformat(started_at_raw) if started_at_raw else None
    )

    error_message: str | None = None
    if result.state == "FAILURE":
        err_info = result.info
        error_message = str(err_info) if err_info else None

    return AnalysisTask(
        task_id=task_id,
        repository_id=repo_id,
        status=status,
        mode=mode,
        progress=progress,
        submitted_at=submitted_at,
        started_at=started_at,
        completed_at=_utcnow() if status == TaskStatus.COMPLETED else None,
        error_message=error_message,
    )


@router.post("/repositories/{repository_id}/analyze", response_model=AnalysisTask, status_code=202)
async def submit_analysis(
    repository_id: UUID,
    request: AnalyzeRequest | None = None,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
):
    """
    提交分析任务

    创建一个异步分析任务并提交到 Celery 队列。
    返回 202 Accepted 状态码，表示任务已接受但尚未完成。

    Args:
        repository_id: 目标仓库 ID
        request: 可选的分析参数（模式、启用的 Agent 列表）
        db: 数据库会话

    Returns:
        AnalysisTask: 包含 task_id、初始状态的响应
    """
    # 验证仓库存在
    dao = RepositoryDAO()
    repo = await dao.get_by_id(db, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    # 解析请求参数
    mode = request.mode if request and request.mode else AnalysisMode.FULL
    agents = request.agents if request and request.agents else None

    # 检查是否已有正在运行的任务（防止重复提交）
    try:
        client = _get_redis_client()
        existing_task_id = client.get(f"repo:{repository_id}:active_task")
        if existing_task_id:
            logger.warning("仓库已有活跃任务，拒绝重复提交: repo=%s, existing_task=%s", repository_id, existing_task_id)
            raise HTTPException(
                status_code=409,
                detail=f"Repository {repository_id} already has an active task: {existing_task_id}",
            )
    except redis.RedisError as exc:
        logger.warning("Redis 检查失败，允许继续: %s", exc)

    # 提交 Celery 任务
    celery_result = run_analysis.delay(
        repository_id=str(repository_id),
        mode=mode.value,
        agents=agents,
    )

    # 存储 task_id → repository_id 映射到 Redis
    try:
        client = _get_redis_client()
        client.set(
            f"task:{celery_result.id}:repo",
            str(repository_id),
            ex=_MAPPING_TTL,
        )
        # 记录仓库的活跃任务 ID（用于去重）
        client.set(f"repo:{repository_id}:active_task", celery_result.id, ex=_MAPPING_TTL)
    except redis.RedisError as exc:
        logger.warning("Redis 写入映射失败: %s", exc)

    logger.info("分析任务已提交: repo=%s, celery_task=%s", repository_id, celery_result.id)

    # 立即返回初始任务信息
    task = AnalysisTask(
        task_id=celery_result.id,
        repository_id=repository_id,
        status=TaskStatus.PENDING,
        mode=mode,
        progress=AnalysisProgress(
            current_step=TaskStatus.PENDING,
            percent=0.0,
            files_processed=0,
            files_total=int(repo.file_count),
            knowledge_points_found=0,
        ),
        submitted_at=_utcnow(),
    )

    return task


@router.get("/tasks/{task_id}", response_model=AnalysisTask)
async def get_task_status(task_id: str):
    """
    查询任务状态

    从 Celery result_backend 读取任务进度。

    Args:
        task_id: Celery 任务 ID

    Returns:
        AnalysisTask: 包含当前状态和进度的响应

    Raises:
        HTTPException 404: 任务不存在或无法检索
    """
    result = AsyncResult(task_id, app=celery_app)

    # 检查任务是否存在（通过尝试获取状态）
    try:
        _ = result.state
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found") from exc

    # 查找关联的 repository_id
    repo_id = _lookup_repository(task_id)

    return _celery_result_to_task(task_id, repo_id)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    取消分析任务

    通过 Celery control.revoke 终止正在执行的 Worker 任务。

    Args:
        task_id: Celery 任务 ID

    Returns:
        包含成功消息的字典

    Raises:
        HTTPException 404: 任务不存在
    """
    result = AsyncResult(task_id, app=celery_app)

    # 检查任务是否存在
    try:
        _ = result.state
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found") from exc

    # 如果已经完成或失败，无需取消
    if result.state in ("SUCCESS", "FAILURE"):
        return {"message": f"Task {task_id} already {result.state.lower()}"}

    # 撤销任务（terminate=True 杀死正在执行的工作进程）
    revoked = celery_app.control.revoke(task_id, terminate=True)

    if revoked:
        logger.info("任务已取消: task_id=%s", task_id)
        # 清理 Redis 中的活跃任务标记和取消标志
        try:
            client = _get_redis_client()
            repo_id_raw = client.get(f"task:{task_id}:repo")
            if repo_id_raw:
                client.delete(f"repo:{repo_id_raw}:active_task")
            client.set(f"task:{task_id}:cancel", "1", ex=60)  # 1 分钟过期
        except redis.RedisError as exc:
            logger.warning("Redis 清理失败: %s", exc)
        return {"message": f"Task {task_id} cancellation requested"}
    else:
        logger.warning("任务取消请求失败: task_id=%s", task_id)
        return {"message": f"Task {task_id} could not be cancelled (may have already finished)"}
