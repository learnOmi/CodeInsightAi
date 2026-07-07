"""
分析任务路由

提供分析任务的提交、查询、取消接口。
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/repositories/{repository_id}/analyze", status_code=202)
async def submit_analysis(repository_id: str):
    """
    提交分析任务
    """
    # TODO: P1-08 实现
    raise NotImplementedError("P1-08: 分析任务提交接口待实现")


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """
    查询任务状态
    """
    # TODO: P1-08 实现
    raise NotImplementedError("P1-08: 任务状态查询接口待实现")


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    取消分析任务
    """
    # TODO: P1-08 实现
    raise NotImplementedError("P1-08: 任务取消接口待实现")
