"""
单独重试路由

提供单个 AI 分析类别的重试接口。适用于某个分析节点失败后，用户只需重新运行该节点，而不必重跑全部分析流程。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.repositories import AnalysisVersionDAO

# 有效的分析类别代码
VALID_CATEGORY_CODES = {"DP", "AD", "AL", "ET", "DK", "TT", "TK"}


class RetryRequest(BaseModel):
    """重试请求体（可选参数：force 强制即使已成功也重试）"""

    force: bool = False


class RetryResponse(BaseModel):
    """重试响应"""

    status: str  # "accepted" | "skipped" | "limit_exceeded"
    task_id: str | None = None  # 如果是新建任务
    category: str
    existing_status: str | None = None  # 如果已存在状态
    retry_count: int = 0  # 当前重试次数
    message: str


class BatchRetryRequest(BaseModel):
    """批量重试请求体"""

    categories: list[str]  # 要重试的类别列表
    force: bool = False


class BatchRetryResponse(BaseModel):
    """批量重试响应"""

    results: list[RetryResponse]


class FailedNodesResponse(BaseModel):
    """失败节点查询响应"""

    failed_nodes: list[dict]


router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
    tags=["单独重试"],
)


def validate_category(category: str) -> None:
    """验证分类代码是否有效"""
    if category not in VALID_CATEGORY_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的类别代码: {category}. 必须是其中之一: {sorted(VALID_CATEGORY_CODES)}",
        )


async def get_latest_completed_version(repo_uuid: UUID):
    """获取指定仓库的最新已完成分析版本"""
    from codeinsight.db.session import get_db_session

    dao = AnalysisVersionDAO()
    async for db in get_db_session():
        return await dao.get_latest_completed(db, repo_uuid)
    return None


async def _do_retry(repo_uuid: UUID, category: str, force: bool) -> RetryResponse:
    """
    执行单个类别的重试逻辑（供单点和批量端点共享）

    Args:
        repo_uuid: 仓库 UUID
        category: 分析类别代码
        force: 是否强制重试

    Returns:
        RetryResponse 响应
    """
    from codeinsight.db.redis_failed_nodes import can_retry, increment_retry_count

    # 检查重试次数上限
    retry_allowed, current_retry_count = can_retry(str(repo_uuid), category)
    if not retry_allowed and not force:
        return RetryResponse(
            status="limit_exceeded",
            category=category,
            existing_status=None,
            retry_count=current_retry_count,
            message=f"该类别（{category}）重试次数已达上限（{current_retry_count} 次）",
        )

    # 获取最新版本信息
    latest_version = await get_latest_completed_version(repo_uuid)
    if not latest_version:
        increment_retry_count(str(repo_uuid), category)
        task_id = start_retry_task(repo_uuid, category, force)
        return RetryResponse(
            status="accepted",
            task_id=task_id,
            category=category,
            existing_status=None,
            retry_count=current_retry_count + 1,
            message="已无历史版本，启动新重试任务",
        )

    # 检查该类别在历史版本中的状态
    agent_status = latest_version.agent_status or {}
    category_status = agent_status.get(category, {})
    current_status = category_status.get("status", "")

    # 如果已经成功且没有强制标志，直接跳过
    if current_status == "success" and not force:
        return RetryResponse(
            status="skipped",
            task_id=None,
            category=category,
            existing_status=current_status,
            retry_count=current_retry_count,
            message=f"该类别分析已成功（版本 {latest_version.version}），无需重试",
        )

    # 启动重试
    increment_retry_count(str(repo_uuid), category)
    task_id = start_retry_task(repo_uuid, category, force)
    return RetryResponse(
        status="accepted",
        task_id=task_id,
        category=category,
        existing_status=current_status,
        retry_count=current_retry_count + 1,
        message=f"已启动 {category} 类别的重试任务（第 {current_retry_count + 1} 次重试）",
    )


# 注意：固定路径端点（/batch, /failed-nodes）必须在 /{category} 参数化端点之前注册，
# 否则 FastAPI 会将 "batch" 或 "failed-nodes" 匹配为 category 参数。


@router.post("/retry/{repo_uuid}/batch", name="batch_retry_analysis", response_model=BatchRetryResponse)
async def batch_retry_analysis(
    repo_uuid: UUID,
    request: BatchRetryRequest,
):
    """
    批量重试多个 AI 分析类别。

    P3: 支持对多个失败的类别同时发起重试。

    行为：
    1. 验证所有类别代码
    2. 逐个检查重试次数上限
    3. 对每个类别启动重试任务
    4. 返回每个类别的重试结果
    """
    # 验证所有类别代码
    invalid_categories = [c for c in request.categories if c not in VALID_CATEGORY_CODES]
    if invalid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"无效的类别代码: {invalid_categories}. 必须是其中之一: {sorted(VALID_CATEGORY_CODES)}",
        )

    # 逐个启动重试任务
    results = []
    for category in request.categories:
        try:
            result = await _do_retry(
                repo_uuid=repo_uuid,
                category=category,
                force=request.force,
            )
            results.append(result)
        except Exception as exc:
            results.append(
                RetryResponse(
                    status="failed",
                    category=category,
                    existing_status=None,
                    retry_count=0,
                    message=str(exc),
                )
            )

    return BatchRetryResponse(results=results)


@router.get("/retry/{repo_uuid}/failed-nodes", name="list_failed_nodes", response_model=FailedNodesResponse)
async def list_failed_nodes(repo_uuid: UUID):
    """
    查询某仓库所有失败的 AI 分析节点（从 Redis 读取）。

    P2-b: 提供前端轮询接口，供 UI 实时展示失败节点状态。

    行为：
    1. 从 Redis 读取该仓库的失败节点记录
    2. 返回失败节点列表（含类别、错误信息、版本、时间戳）
    """
    from codeinsight.db.redis_failed_nodes import get_failed_nodes

    failed_nodes = get_failed_nodes(str(repo_uuid))
    return FailedNodesResponse(failed_nodes=failed_nodes)


@router.post("/retry/{repo_uuid}/{category}", name="retry_analysis_category", response_model=RetryResponse)
async def retry_analysis_category(
    repo_uuid: UUID,
    category: str,
    request: RetryRequest | None = None,
):
    """
    单独重试指定的 AI 分析类别。

    P3: 增加重试次数上限检查，防止无限重试循环。

    行为：
    1. 检查是否存在已完成的分析版本，获取已成功的其他节点结果作为上下文
    2. 检查重试次数是否超过上限（MAX_RETRY_ATTEMPTS = 3）
    3. 如果该类别已成功且未设置 force，直接返回跳过（不产生额外成本）
    4. 否则启动异步重试任务并返回 task_id
    """
    validate_category(category)
    if request is None:
        request = RetryRequest()
    return await _do_retry(repo_uuid, category, request.force)


def start_retry_task(repo_uuid: UUID, category: str, force: bool = False) -> str:
    """启动 Celery 重试任务并返回 task ID"""
    from codeinsight.tasks.retry_tasks import retry_analysis_category as retry_task

    # 立即执行或延迟执行取决于 CELERY_TASK_ALWAYS_EAGER 设置
    if settings.celery_task_always_eager:
        # 同步执行（便于调试）
        result = retry_task(str(repo_uuid), category, force)
        # 从结果中提取 task_id
        task_id = str(result.get("task_id", str(__import__("uuid").uuid4())))  # type: ignore[no-any-return]
        return task_id
    else:
        # 异步执行
        task = retry_task.delay(str(repo_uuid), category, force)
        return task.id


@router.post("/retry/{repo_uuid}/expansion", name="retry_expansion", response_model=RetryResponse)
async def retry_expansion(repo_uuid: UUID):
    """重试拓展知识生成（仅重试失败的拓展内容生成）"""
    from codeinsight.db.session import get_db_session
    from codeinsight.repositories.knowledge_point import KnowledgePointDAO

    # 获取最新版本
    latest_version = await get_latest_completed_version(repo_uuid)
    if not latest_version:
        return RetryResponse(
            status="skipped",
            category="_expansion",
            message="没有已完成的分析版本",
        )

    # 查询该版本中缺少拓展内容的知识点
    kp_dao = KnowledgePointDAO()
    async for db in get_db_session():
        all_kps = await kp_dao.list(db, repository_id=repo_uuid, version=latest_version.version, limit=1000)
        failed_kps = [kp for kp in all_kps if not kp.expansion or not kp.expansion.get("principle")]
        if not failed_kps:
            return RetryResponse(
                status="skipped",
                category="_expansion",
                message=f"版本 {latest_version.version} 中所有知识点已有拓展内容，无需重试",
            )

        # 启动后台重试任务
        from codeinsight.tasks.retry_tasks import retry_expansion_task

        if settings.celery_task_always_eager:
            retry_expansion_task(str(repo_uuid), str(latest_version.id), [str(kp.id) for kp in failed_kps])
            task_id = str(__import__("uuid").uuid4())
        else:
            task = retry_expansion_task.delay(str(repo_uuid), str(latest_version.id), [str(kp.id) for kp in failed_kps])
            task_id = task.id

        return RetryResponse(
            status="accepted",
            task_id=task_id,
            category="_expansion",
            message=f"已启动 {len(failed_kps)} 个知识点拓展内容重试",
        )
