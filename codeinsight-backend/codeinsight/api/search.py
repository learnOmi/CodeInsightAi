"""
搜索路由

提供知识点的全文搜索、向量搜索接口。
"""

from fastapi import APIRouter, Depends

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.schemas import SearchRequest, SearchResponse, SearchSuggestionsResponse

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    搜索知识点
    """
    raise NotImplementedError("P2-03: 搜索接口待实现")


@router.get("/search/suggestions", response_model=SearchSuggestionsResponse)
async def search_suggestions(q: str):
    """
    获取搜索建议
    """
    raise NotImplementedError("P2-03: 搜索建议接口待实现")
