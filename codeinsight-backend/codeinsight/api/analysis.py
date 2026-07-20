"""
分析任务路由

提供分析任务的提交、查询、取消接口，以及实时进度推送（SSE）。

依赖 Celery 异步执行，任务状态通过 Redis result_backend 存储。
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import redis
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.constants.redis_keys import (
    repo_active_task_key,
    task_cancel_key,
    task_mode_key,
    task_repo_key,
)
from codeinsight.db.redis_client import get_redis_client
from codeinsight.db.session import get_db_session
from codeinsight.repositories import RepositoryDAO
from codeinsight.repositories.analysis_version import AnalysisVersionDAO
from codeinsight.repositories.file import FileDAO
from codeinsight.repositories.file_analysis_snapshot import FileAnalysisSnapshotDAO
from codeinsight.schemas import (
    AgentType,
    AnalysisMode,
    AnalysisProgress,
    AnalysisTask,
    AnalyzeRequest,
    TaskStatus,
)
from codeinsight.tasks import celery_app
from codeinsight.tasks.analysis_tasks import run_analysis

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_repository_dao() -> RepositoryDAO:
    """获取 RepositoryDAO 实例（依赖注入）"""
    return RepositoryDAO()


# Annotated 类型别名，消除 B008 警告
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RepoDaoDep = Annotated[RepositoryDAO, Depends(get_repository_dao)]


def _utcnow() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(UTC)


def _lookup_repository(task_id: str) -> UUID | None:
    """
    根据 task_id 查找关联的 repository_id

    从 Redis 中读取 task_id → repository_id 映射。

    API-5 修复：返回 Optional[UUID]，未找到时返回 None，调用方可以明确判断查找失败。

    Args:
        task_id: Celery 任务 ID

    Returns:
        repository UUID，未找到则返回 None
    """
    try:
        client = get_redis_client()
        raw = client.get(task_repo_key(task_id))
        if raw is not None:
            return UUID(str(raw))
        logger.debug("Redis 中未找到任务映射: task_id=%s", task_id)
    except redis.RedisError as exc:
        logger.warning("Redis 查询失败: task_id=%s, error=%s", task_id, exc)
    return None


def _lookup_task_mode(task_id: str) -> AnalysisMode:
    """
    根据 task_id 查找分析模式

    从 Redis 中读取 task_id → mode 映射。

    Args:
        task_id: Celery 任务 ID

    Returns:
        AnalysisMode，读取失败时降级为 FULL
    """
    try:
        client = get_redis_client()
        raw = client.get(task_mode_key(task_id))
        if raw is not None:
            return AnalysisMode(str(raw))
    except redis.RedisError:
        logger.warning("Redis 查询任务模式失败，使用默认 FULL: task_id=%s", task_id)
    return AnalysisMode.FULL


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
    result: AsyncResult = AsyncResult(task_id, app=celery_app)

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
    started_at: datetime | None = datetime.fromisoformat(started_at_raw) if started_at_raw else None

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


async def _trigger_analysis(
    repository_id: UUID,
    repo: Any,
    mode: AnalysisMode = AnalysisMode.FULL,
    agents: list[AgentType] | None = None,
) -> AnalysisTask:
    """
    提交分析任务的共享逻辑（供 submit_analysis 和 create_repository 复用）

    在 eager 模式下直接在当前事件循环中运行 orchestrator，避免
    ThreadPoolExecutor + asyncio.run() 破坏主事件循环的数据库连接池。
    在非 eager 模式下提交到 Celery 队列异步执行。

    Args:
        repository_id: 仓库 ID
        repo: 仓库模型实例
        mode: 分析模式
        agents: 启用的 Agent 列表

    Returns:
        AnalysisTask: 包含 task_id、初始状态的响应
    """

    # 检查是否已有正在运行的任务（防止重复提交）
    try:
        client = get_redis_client()
        existing_task_id = client.get(repo_active_task_key(str(repository_id)))
        if existing_task_id:
            if isinstance(existing_task_id, bytes):
                task_id_str = existing_task_id.decode("utf-8")
            elif isinstance(existing_task_id, str):
                task_id_str = existing_task_id
            else:
                task_id_str = str(existing_task_id)
            if not settings.celery_task_always_eager:
                # 非 eager 模式：检查 Celery 任务状态
                old_result: AsyncResult = AsyncResult(task_id_str, app=celery_app)
                if old_result.state in ("SUCCESS", "FAILURE"):
                    logger.info("旧任务已结束(%s)，清理 Redis key: repo=%s", old_result.state, repository_id)
                    client.delete(repo_active_task_key(str(repository_id)))
                else:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Repository {repository_id} already has an active task: {task_id_str}",
                    )
            else:
                # eager 模式：任务同步执行完毕，key 残留即为过期，直接清理
                logger.info("eager 模式：清理残留任务 key: repo=%s", repository_id)
                client.delete(repo_active_task_key(str(repository_id)))
    except redis.RedisError as exc:
        logger.warning("Redis 检查失败，允许继续: %s", exc)

    if settings.celery_task_always_eager:
        # Eager 模式：直接在当前事件循环中运行 orchestrator
        from codeinsight.tasks.analysis_orchestrator import AnalysisOrchestrator

        logger.info("eager 模式：直接执行分析: repo=%s, mode=%s", repository_id, mode.value)
        orchestrator = AnalysisOrchestrator(
            repo_uuid=repository_id,
            mode=mode.value,
            task_instance=None,
        )
        try:
            result = await orchestrator._run_async()
            final_status = TaskStatus.COMPLETED
            error_msg = None
        except Exception as exc:
            logger.error(
                "eager 模式分析失败: repo=%s, type=%s, error=%s",
                repository_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            final_status = TaskStatus.FAILED
            error_msg = f"{type(exc).__name__}: {exc}"
            result = {}

        return AnalysisTask(
            task_id=f"eager-{uuid.uuid4()}",
            repository_id=repository_id,
            status=final_status,
            mode=mode,
            progress=AnalysisProgress(
                current_step=final_status,
                percent=100.0 if final_status == TaskStatus.COMPLETED else 0.0,
                files_processed=result.get("files_processed", 0) if isinstance(result, dict) else 0,
                files_total=int(repo.file_count),
                knowledge_points_found=result.get("knowledge_points_count", 0) if isinstance(result, dict) else 0,
            ),
            submitted_at=_utcnow(),
            completed_at=_utcnow(),
            error_message=error_msg,
        )

    # 非 eager 模式：提交到 Celery 队列
    celery_result = run_analysis.delay(
        repository_id=str(repository_id),
        mode=mode.value,
        agents=agents,
    )

    # 存储 task_id → repository_id 和 mode 映射到 Redis
    try:
        client = get_redis_client()
        client.set(
            task_repo_key(celery_result.id),
            str(repository_id),
            ex=settings.redis_task_mapping_ttl,
        )
        client.set(
            task_mode_key(celery_result.id),
            mode.value,
            ex=settings.redis_task_mapping_ttl,
        )
        client.set(repo_active_task_key(str(repository_id)), celery_result.id, ex=settings.redis_task_mapping_ttl)
    except redis.RedisError as exc:
        logger.warning("Redis 写入映射失败: %s", exc)

    logger.info("分析任务已提交: repo=%s, celery_task=%s", repository_id, celery_result.id)

    return AnalysisTask(
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


@router.post("/repositories/{repository_id}/analyze", response_model=AnalysisTask, status_code=202)
async def submit_analysis(
    repository_id: UUID,
    db: DbSession,
    repo_dao: RepoDaoDep,
    request: AnalyzeRequest | None = None,
):
    """
    提交分析任务

    创建一个异步分析任务并提交到 Celery 队列。
    返回 202 Accepted 状态码，表示任务已接受但尚未完成。
    """
    # 验证仓库存在
    repo = await repo_dao.get_by_id(db, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    # 解析请求参数
    mode = request.mode if request and request.mode else AnalysisMode.FULL
    agents = request.agents if request and request.agents else None

    # 内容变化检测：对比最新完成版本的快照与当前文件
    version_dao = AnalysisVersionDAO()
    snapshot_dao = FileAnalysisSnapshotDAO()
    file_dao = FileDAO()

    latest_completed = await version_dao.get_latest_completed(db, repository_id)
    if latest_completed is not None:
        old_snapshots = await snapshot_dao.get_by_version(db, repository_id, latest_completed.version)
        old_hash_map = {s.file_id: s.content_hash for s in old_snapshots if s.file_id is not None}

        current_files = await file_dao.get_by_repository(db, repository_id)
        current_hash_map = {f.id: f.content_hash for f in current_files}

        if old_hash_map == current_hash_map:
            logger.info("内容无变化，跳过重复分析: repo=%s, version=%s", repository_id, latest_completed.version)
            raise HTTPException(
                status_code=304,
                detail=f"Repository {repository_id} has no content changes since version {latest_completed.version}",
            )

    return await _trigger_analysis(repository_id, repo, mode=mode, agents=agents)


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
    result: AsyncResult = AsyncResult(task_id, app=celery_app)

    # 检查任务是否存在（通过尝试获取状态）
    try:
        _ = result.state
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found") from exc

    # 查找关联的 repository_id 和分析模式
    repo_id = _lookup_repository(task_id)
    mode = _lookup_task_mode(task_id)

    if repo_id is None:
        logger.info("任务 %s 未关联仓库信息，使用占位值", task_id)
        repo_id = UUID("00000000-0000-0000-0000-000000000000")

    return _celery_result_to_task(task_id, repo_id, mode)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    取消分析任务

    通过 Celery control.revoke 终止正在执行的 Worker 任务。
    如果任务已完成或不存在（eager 模式），返回相应提示。

    Args:
        task_id: Celery 任务 ID

    Returns:
        包含成功消息的字典

    Raises:
        HTTPException 404: 任务不存在
    """
    result: AsyncResult = AsyncResult(task_id, app=celery_app)

    # 检查任务是否存在
    try:
        state = result.state
    except Exception as exc:
        logger.warning("任务不存在或无法查询: task_id=%s, error=%s", task_id, exc)
        # 尝试从 Redis 查找关联仓库，直接更新仓库状态
        try:
            client = get_redis_client()
            repo_id_raw = client.get(task_repo_key(task_id))
            if repo_id_raw:
                repo_id_str = repo_id_raw.decode("utf-8") if isinstance(repo_id_raw, bytes) else str(repo_id_raw)
                client.delete(repo_active_task_key(repo_id_str))
                logger.info("任务不存在，已清理 Redis: task_id=%s, repo=%s", task_id, repo_id_str)
        except redis.RedisError:
            pass
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found or already completed") from exc

    # 如果已经完成或失败，无需取消
    if state in ("SUCCESS", "FAILURE"):
        return {"message": f"Task {task_id} already {state.lower()}"}

    # O-B5: celery_app.control.revoke() 返回 None（fire-and-forget），始终视为成功
    celery_app.control.revoke(task_id, terminate=True)

    logger.info("任务取消请求已发送: task_id=%s", task_id)
    # 清理 Redis 中的活跃任务标记和取消标志
    try:
        client = get_redis_client()
        repo_id_raw = client.get(task_repo_key(task_id))
        if repo_id_raw:
            repo_id_str = repo_id_raw.decode("utf-8") if isinstance(repo_id_raw, bytes) else str(repo_id_raw)
            client.delete(repo_active_task_key(repo_id_str))
        client.set(task_cancel_key(task_id), "1", ex=settings.redis_cancel_flag_ttl)
    except redis.RedisError as exc:
        logger.warning("Redis 清理失败: %s", exc)
    return {"message": f"Task {task_id} cancellation requested"}


@router.get("/tasks/{task_id}/stream")
async def stream_task_progress(task_id: str):
    """
    实时推送任务进度（SSE）

    通过 Server-Sent Events 推送任务进度更新，前端可使用 EventSource 消费。
    推送事件类型：
    - progress: 进度更新，data 包含 current_step、percent 等字段
    - complete: 任务完成，data 包含 task_id、status
    - error: 任务失败，data 包含 task_id、status、error

    Args:
        task_id: Celery 任务 ID

    Returns:
        StreamingResponse (text/event-stream)
    """
    result: AsyncResult = AsyncResult(task_id, app=celery_app)

    async def event_generator():
        last_percent = -1.0
        last_step = ""
        while True:
            try:
                state = result.state
            except Exception:
                yield f"event: error\ndata: {json.dumps({'task_id': task_id, 'status': 'unknown', 'error': 'task not found'})}\n\n"
                break

            if state == "PENDING":
                if last_percent != 0.0:
                    last_percent = 0.0
                    yield f"event: progress\ndata: {json.dumps({'current_step': 'PENDING', 'percent': 0.0, 'files_processed': 0, 'files_total': 0, 'knowledge_points_found': 0})}\n\n"
                await asyncio.sleep(1)
                continue

            meta = result.info or {}
            if not isinstance(meta, dict):
                meta = {}

            if state == "FAILURE":
                yield f"event: error\ndata: {json.dumps({'task_id': task_id, 'status': 'FAILED', 'error': str(meta.get('exc_type', 'Unknown')) if isinstance(meta, dict) else str(meta)})}\n\n"
                break

            if state == "SUCCESS":
                yield f"event: complete\ndata: {json.dumps({'task_id': task_id, 'status': 'COMPLETED'})}\n\n"
                break

            # STARTED / RETRY / progress
            current_step = meta.get("current_step", "SCANNING")
            percent = meta.get("percent", 0.0)
            files_processed = meta.get("files_processed", 0)
            files_total = meta.get("files_total", 0)
            knowledge_points_found = meta.get("knowledge_points_found", 0)

            if percent != last_percent or current_step != last_step:
                last_percent = percent
                last_step = current_step
                yield f"event: progress\ndata: {json.dumps({'current_step': current_step, 'percent': percent, 'files_processed': files_processed, 'files_total': files_total, 'knowledge_points_found': knowledge_points_found})}\n\n"

            if percent >= 100.0:
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
