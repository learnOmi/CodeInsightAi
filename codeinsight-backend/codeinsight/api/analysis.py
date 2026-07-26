"""
分析任务路由

提供分析任务的提交、查询、取消接口，以及实时进度推送（SSE）。

依赖 Celery 异步执行，任务状态通过 Redis result_backend 存储。
Eager 模式下使用 asyncio.create_task 在后台执行，避免阻塞 HTTP 响应。
"""

import asyncio
import contextlib
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
        task_id: Celery 任务 ID 或 eager 任务 ID

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


def _is_eager_task(task_id: str) -> bool:
    """判断是否为 eager 后台任务（非 Celery 任务）"""
    return task_id.startswith("eager-")


# 跟踪正在运行的 eager 后台任务，使 cancel_task 可以主动终止它们
_active_eager_tasks: dict[str, "asyncio.Task"] = {}


async def _trigger_eager_analysis_background(
    task_id: str,
    repository_id: UUID,
    mode: AnalysisMode,
    agents: list[AgentType] | None,
) -> None:
    """
    在后台异步执行 eager 模式分析（fire-and-forget）

    使用 asyncio.create_task 在后台运行，HTTP 响应不等待其完成。
    任务进度通过 Redis 持久化，供 get_task_status 和 stream_task_progress 查询。

    任务引用存储在 _active_eager_tasks 中，cancel_task 可以通过它来取消运行中的任务。
    """
    from codeinsight.tasks.analysis_orchestrator import AnalysisOrchestrator

    async def _run() -> None:
        client = get_redis_client()
        orchestrator = AnalysisOrchestrator(
            repo_uuid=repository_id,
            mode=mode.value,
            task_instance=None,
            task_id=task_id,  # 显式传入 task_id，确保 __init__ 中正确初始化 RedisProgressManager
        )
        logger.info("eager 后台任务开始: repo=%s, task_id=%s, mode=%s", repository_id, task_id, mode.value)
        try:
            result = await asyncio.wait_for(
                orchestrator._run_async(),
                timeout=600.0,
            )
            logger.info(
                "eager 后台任务完成: repo=%s, task_id=%s, knowledge_points=%d",
                repository_id,
                task_id,
                result.get("knowledge_points_count", 0),
            )
            # 持久化完成进度到 Redis
            with contextlib.suppress(redis.RedisError):
                client.hset(
                    f"task:{task_id}:progress",
                    mapping={
                        "current_step": TaskStatus.COMPLETED.value,
                        "percent": "100.0",
                        "files_processed": str(result.get("files_processed", 0)),
                        "files_total": str(result.get("files_processed", 0)),
                        "knowledge_points_found": str(result.get("knowledge_points_count", 0)),
                        "total_lines": str(result.get("total_lines", 0)),
                    },
                )
            # 清理活跃任务标记
            with contextlib.suppress(redis.RedisError):
                client.delete(repo_active_task_key(str(repository_id)))
        except TimeoutError:
            error_msg = "Analysis timeout (600s)"
            logger.error("eager 后台任务超时: repo=%s, task_id=%s", repository_id, task_id)
            try:
                await orchestrator.fail(None, error_msg)
                with contextlib.suppress(redis.RedisError):
                    client.hset(
                        f"task:{task_id}:progress", mapping={"current_step": TaskStatus.FAILED, "error": error_msg}
                    )
            except Exception:
                logger.warning("orchestrator.fail() 失败", exc_info=True)
        except asyncio.CancelledError:
            logger.info("eager 后台任务被用户取消: repo=%s, task_id=%s", repository_id, task_id)
            try:
                await orchestrator.cancel(None)
            except Exception:
                logger.warning("orchestrator.cancel() 失败", exc_info=True)
            finally:
                with contextlib.suppress(redis.RedisError):
                    client.hset(
                        f"task:{task_id}:progress",
                        mapping={"current_step": TaskStatus.CANCELLED.value},
                    )
                with contextlib.suppress(redis.RedisError):
                    client.delete(repo_active_task_key(str(repository_id)))
            raise  # Re-raise to mark task as cancelled
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(
                "eager 后台任务失败: repo=%s, task_id=%s, error=%s", repository_id, task_id, error_msg, exc_info=True
            )
            try:
                await orchestrator.fail(None, error_msg)
                with contextlib.suppress(redis.RedisError):
                    client.hset(
                        f"task:{task_id}:progress", mapping={"current_step": TaskStatus.FAILED, "error": error_msg}
                    )
            except Exception:
                logger.warning("orchestrator.fail() 失败", exc_info=True)
        finally:
            _active_eager_tasks.pop(task_id, None)

    task = asyncio.create_task(_run())
    _active_eager_tasks[task_id] = task


def _get_eager_task_progress(task_id: str) -> dict | None:
    """从 Redis 读取 eager 后台任务的进度信息"""
    try:
        client = get_redis_client()
        raw = client.hgetall(f"task:{task_id}:progress")
        # MyPy: 使用 type guard 确保 raw 是 dict（同步 Redis 客户端返回 dict）
        if isinstance(raw, dict) and raw:
            result = {}
            for k, v in raw.items():
                key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                val = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                result[key] = val
            return result
    except Exception as e:
        logger.warning("读取 eager 任务进度失败: task_id=%s, error=%s", task_id, e)
    return None


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
        total_lines=meta.get("total_lines", 0),
    )

    # O-D2: 从 Redis 读取实际提交时间（由 submit_analysis 写入），而非始终使用当前时间
    submitted_at: datetime | None = None
    try:
        client = get_redis_client()
        submitted_at_raw = client.get(f"task:{task_id}:submitted_at")
        if submitted_at_raw:
            submitted_at = datetime.fromisoformat(submitted_at_raw.decode("utf-8"))  # type: ignore[union-attr]
    except Exception:
        logger.debug("无法读取任务提交时间", exc_info=True)
    if submitted_at is None:
        submitted_at = _utcnow()
    started_at_raw = meta.get("started_at") if status != TaskStatus.PENDING else None
    started_at: datetime | None = None
    if started_at_raw:
        try:
            started_at = datetime.fromisoformat(started_at_raw)
        except (ValueError, TypeError):
            started_at = None

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
    eager_task_id: str | None = None,
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
        eager_task_id: 预先生成的 eager task_id（与 X-Task-Id 响应头一致）。
                       仅在 eager 模式且由 create_repository 触发时传入。
                       如果为 None，则自动生成。

    Returns:
        AnalysisTask: 包含 task_id、初始状态的响应
    """
    logger.info("_trigger_analysis 被调用: repo=%s, mode=%s", repository_id, mode.value)

    # 检查是否已有正在运行的任务（防止重复提交）
    # 同步 Redis 调用在事件循环线程中执行（run_in_executor），避免阻塞 asyncio
    client = get_redis_client()
    try:
        running_loop = asyncio.get_running_loop()
        existing_task_id = await asyncio.wait_for(
            running_loop.run_in_executor(None, client.get, repo_active_task_key(str(repository_id))),
            timeout=5.0,
        )
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
                # eager 模式：检查任务是否仍在运行
                progress_data = _get_eager_task_progress(task_id_str)
                if progress_data:
                    step = progress_data.get("current_step", TaskStatus.PENDING.value)
                    if step not in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
                        raise HTTPException(
                            status_code=409,
                            detail=f"Repository {repository_id} already has an active task: {task_id_str}",
                        )
                # 任务已结束或无可查进度，key 残留即为过期，直接清理
                logger.info("eager 模式：清理已结束任务 key: repo=%s", repository_id)
                client.delete(repo_active_task_key(str(repository_id)))
    except TimeoutError:
        logger.warning("Redis 检查超时(5s)，允许继续: repo=%s", repository_id)
        existing_task_id = None
    except redis.RedisError as exc:
        logger.warning("Redis 检查失败，允许继续: %s", exc)
        existing_task_id = None

    logger.info("触发分析: repo=%s, mode=%s, eager=%s", repository_id, mode.value, settings.celery_task_always_eager)

    if settings.celery_task_always_eager:
        # Eager 模式：使用后台任务执行，HTTP 立即返回
        # 避免阻塞 HTTP 响应，前端可通过 X-Task-Id 轮询进度

        eager_task_id = eager_task_id or f"eager-{uuid.uuid4()}"
        logger.info("eager 模式：提交后台分析任务: repo=%s, task_id=%s", repository_id, eager_task_id)

        # 注册到 Redis，使 get_task_status 和 stream_task_progress 能查到
        try:
            client = get_redis_client()
            client.set(task_repo_key(eager_task_id), str(repository_id), ex=settings.redis_task_mapping_ttl)
            client.set(task_mode_key(eager_task_id), mode.value, ex=settings.redis_task_mapping_ttl)
            client.set(repo_active_task_key(str(repository_id)), eager_task_id, ex=settings.redis_task_mapping_ttl)
            client.set(f"task:{eager_task_id}:submitted_at", _utcnow().isoformat(), ex=settings.redis_task_mapping_ttl)
        except redis.RedisError as exc:
            logger.warning("Redis 写入 eager 任务映射失败: %s", exc)

        # 启动后台任务（fire-and-forget）
        asyncio.create_task(_trigger_eager_analysis_background(eager_task_id, repository_id, mode, agents))

        return AnalysisTask(
            task_id=eager_task_id,
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
        # O-D2: 记录实际提交时间到 Redis
        client.set(
            f"task:{celery_result.id}:submitted_at",
            _utcnow().isoformat(),
            ex=settings.redis_task_mapping_ttl,
        )
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

    # 在 HTTP 请求中立即将仓库状态设为分析中，使前端 cache invalidation 能获得最新状态
    # 后续后台任务中的 _do_analysis_setup 也会再次设置，此处为提前更新
    repo.status = "analyzing"
    await db.flush()

    return await _trigger_analysis(repository_id, repo, mode=mode, agents=agents)


@router.get("/tasks/{task_id}", response_model=AnalysisTask)
async def get_task_status(task_id: str):
    """
    查询任务状态

    支持 Celery 任务和 eager 后台任务。
    Celery 任务从 result_backend 读取进度。
    Eager 后台任务从 Redis 读取进度。

    Args:
        task_id: Celery 任务 ID 或 eager 任务 ID

    Returns:
        AnalysisTask: 包含当前状态和进度的响应

    Raises:
        HTTPException 404: 任务不存在或无法检索
    """
    # 查找关联的 repository_id 和分析模式
    repo_id = _lookup_repository(task_id)
    mode = _lookup_task_mode(task_id)
    if repo_id is None:
        repo_id = UUID("00000000-0000-0000-0000-000000000000")

    # Eager 后台任务：从 Redis 读取进度
    if _is_eager_task(task_id):
        progress_data = _get_eager_task_progress(task_id)
        if progress_data:
            step = progress_data.get("current_step", TaskStatus.PENDING)
            status = TaskStatus(step) if step in [s.value for s in TaskStatus] else TaskStatus.PENDING
            error_msg = progress_data.get("error")
            return AnalysisTask(
                task_id=task_id,
                repository_id=repo_id,
                status=status,
                mode=mode,
                progress=AnalysisProgress(
                    current_step=status,
                    percent=float(progress_data.get("percent", 0.0)),
                    files_processed=int(progress_data.get("files_processed", 0)),
                    files_total=int(progress_data.get("files_total", 0)),
                    knowledge_points_found=int(progress_data.get("knowledge_points_found", 0)),
                ),
                submitted_at=_utcnow(),
                completed_at=_utcnow() if status == TaskStatus.COMPLETED else None,
                error_message=error_msg,
            )
        # 任务刚启动，尚未有进度
        return AnalysisTask(
            task_id=task_id,
            repository_id=repo_id,
            status=TaskStatus.PENDING,
            mode=mode,
            progress=AnalysisProgress(
                current_step=TaskStatus.PENDING,
                percent=0.0,
                files_processed=0,
                files_total=0,
                knowledge_points_found=0,
            ),
            submitted_at=_utcnow(),
        )

    # Celery 任务
    result: AsyncResult = AsyncResult(task_id, app=celery_app)
    try:
        _ = result.state
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found") from exc

    return _celery_result_to_task(task_id, repo_id, mode)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    取消分析任务

    通过 Celery control.revoke 终止正在执行的 Worker 任务。
    对于 eager 后台任务，设置取消标志并主动取消 asyncio task。
    """
    repo_id_str = None
    try:
        client = get_redis_client()
        repo_id_raw = client.get(task_repo_key(task_id))
        if repo_id_raw:
            repo_id_str = repo_id_raw.decode("utf-8") if isinstance(repo_id_raw, bytes) else str(repo_id_raw)
    except redis.RedisError:
        logger.warning("Redis 查询失败，无法获取仓库信息: task_id=%s", task_id)
        client = None

    # Eager 后台任务：设置取消标志并主动取消 asyncio task
    if _is_eager_task(task_id):
        # 从 _active_eager_tasks 中获取 asyncio task 并取消
        task = _active_eager_tasks.pop(task_id, None)
        if task:
            with contextlib.suppress(Exception):
                task.cancel()
        # 同时保留 Redis 取消标志作为兜底（检查点会读取这个标志）
        if client:
            client.set(task_cancel_key(task_id), "1", ex=settings.redis_cancel_flag_ttl)
        if repo_id_str:
            client.delete(repo_active_task_key(repo_id_str)) if client else None
        return {"message": f"Task {task_id} cancellation requested"}

    # Celery 任务
    result: AsyncResult = AsyncResult(task_id, app=celery_app)
    try:
        state = result.state
    except Exception as exc:
        logger.warning("任务不存在或无法查询: task_id=%s, error=%s", task_id, exc)
        if client and repo_id_str:
            client.delete(repo_active_task_key(repo_id_str))
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found or already completed") from exc

    if state in ("SUCCESS", "FAILURE"):
        return {"message": f"Task {task_id} already {state.lower()}"}

    celery_app.control.revoke(task_id, terminate=True)
    logger.info("任务取消请求已发送: task_id=%s", task_id)
    if client and repo_id_str:
        client.delete(repo_active_task_key(repo_id_str))
    if client:
        client.set(task_cancel_key(task_id), "1", ex=settings.redis_cancel_flag_ttl)
    return {"message": f"Task {task_id} cancellation requested"}


@router.options("/tasks/{task_id}/stream")
@router.get("/tasks/{task_id}/stream")
async def stream_task_progress(task_id: str):
    """
    实时推送任务进度（SSE）

    通过 Server-Sent Events 推送任务进度更新，前端可使用 EventSource 消费。
    支持 Celery 任务和 eager 后台任务。

    推送事件类型：
    - progress: 进度更新，data 包含 current_step、percent 等字段
    - complete: 任务完成，data 包含 task_id、status
    - error: 任务失败，data 包含 task_id、status、error

    Args:
        task_id: Celery 任务 ID 或 eager 任务 ID

    Returns:
        StreamingResponse (text/event-stream)
    """
    # Eager 后台任务：从 Redis 读取进度
    if _is_eager_task(task_id):

        async def eager_event_generator():
            last_percent = -1.0
            last_step = ""
            has_sent_initial = False
            while True:
                progress_data = _get_eager_task_progress(task_id)
                if progress_data:
                    step = progress_data.get("current_step", TaskStatus.PENDING)
                    percent = float(progress_data.get("percent", 0.0))
                    files_processed = int(progress_data.get("files_processed", 0))
                    files_total = int(progress_data.get("files_total", 0))
                    knowledge_points_found = int(progress_data.get("knowledge_points_found", 0))
                    total_lines = int(progress_data.get("total_lines", 0))

                    # Skip duplicate events
                    if percent != last_percent or step != last_step:
                        logger.info("SSE 发送进度事件: task_id=%s, step=%s, percent=%.1f", task_id, step, percent)
                        last_percent = percent
                        last_step = step

                        # Only send initial PENDING event if we haven't sent anything yet
                        # AND there's meaningful data (files_total > 0 means scan completed)
                        if not has_sent_initial:
                            if files_total > 0:
                                # First meaningful update — skip the 0/0 placeholder
                                has_sent_initial = True
                                yield f"event: progress\ndata: {json.dumps({'current_step': step, 'percent': percent, 'files_processed': files_processed, 'files_total': files_total, 'knowledge_points_found': knowledge_points_found, 'total_lines': total_lines})}\n\n"
                            else:
                                # Still no meaningful data, don't spam 0/0
                                pass
                        else:
                            yield f"event: progress\ndata: {json.dumps({'current_step': step, 'percent': percent, 'files_processed': files_processed, 'files_total': files_total, 'knowledge_points_found': knowledge_points_found, 'total_lines': total_lines})}\n\n"

                    if step == TaskStatus.COMPLETED:
                        logger.info("SSE 发送完成事件: task_id=%s", task_id)
                        yield f"event: complete\ndata: {json.dumps({'task_id': task_id, 'status': 'COMPLETED'})}\n\n"
                        break
                    if step == TaskStatus.FAILED:
                        error = progress_data.get("error", "Unknown")
                        logger.info("SSE 发送错误事件: task_id=%s, error=%s", task_id, error)
                        yield f"event: error\ndata: {json.dumps({'task_id': task_id, 'status': 'FAILED', 'error': str(error)})}\n\n"
                        break
                else:
                    # 任务尚未有进度，初始状态
                    if last_percent != 0.0:
                        logger.info("SSE 发送初始进度事件（无进度数据）: task_id=%s", task_id)
                        last_percent = 0.0
                        yield f"event: progress\ndata: {json.dumps({'current_step': 'PENDING', 'percent': 0.0, 'files_processed': 0, 'files_total': 0, 'knowledge_points_found': 0, 'total_lines': 0})}\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            eager_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Celery 任务
    result: AsyncResult = AsyncResult(task_id, app=celery_app)

    async def celery_event_generator():
        last_percent = -1.0
        last_step = ""
        has_sent_initial = False
        while True:
            try:
                state = result.state
            except Exception:
                yield f"event: error\ndata: {json.dumps({'task_id': task_id, 'status': 'unknown', 'error': 'task not found'})}\n\n"
                break

            if state == "PENDING":
                if last_percent != 0.0 and not has_sent_initial:
                    last_percent = 0.0
                    has_sent_initial = True
                    yield f"event: progress\ndata: {json.dumps({'current_step': 'PENDING', 'percent': 0.0, 'files_processed': 0, 'files_total': 0, 'knowledge_points_found': 0, 'total_lines': 0})}\n\n"
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
            total_lines = meta.get("total_lines", 0)

            if (percent != last_percent or current_step != last_step) and (has_sent_initial or files_total > 0):
                last_percent = percent
                last_step = current_step
                has_sent_initial = True
                yield f"event: progress\ndata: {json.dumps({'current_step': current_step, 'percent': percent, 'files_processed': files_processed, 'files_total': files_total, 'knowledge_points_found': knowledge_points_found, 'total_lines': total_lines})}\n\n"

            # O-B13: 移除 percent >= 100.0 的提前退出条件，确保 SUCCESS 状态时发送 complete 事件
            await asyncio.sleep(1)

    return StreamingResponse(
        celery_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
