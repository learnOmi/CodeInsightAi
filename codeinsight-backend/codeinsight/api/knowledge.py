"""
知识点查询路由

提供知识点的列表、详情、统计接口。
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/knowledge-points")
async def list_knowledge_points():
    """获取知识点列表"""
    raise NotImplementedError("P3-05: 知识点列表接口待实现")


@router.get("/knowledge-points/{point_id}")
async def get_knowledge_point(point_id: str):
    """获取知识点详情"""
    raise NotImplementedError("P3-05: 知识点详情接口待实现")


@router.get("/repositories/{repository_id}/knowledge-stats")
async def get_knowledge_stats(repository_id: str):
    """获取知识点统计"""
    raise NotImplementedError("P3-05: 知识点统计接口待实现")
