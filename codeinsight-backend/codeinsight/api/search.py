"""
搜索路由

提供全文搜索、向量搜索、混合搜索接口。
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/search")
async def search():
    """全文/向量/混合搜索"""
    raise NotImplementedError("P3-07: 搜索接口待实现")


@router.get("/search/suggestions")
async def search_suggestions():
    """搜索建议"""
    raise NotImplementedError("P3-07: 搜索建议接口待实现")
