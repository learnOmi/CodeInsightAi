"""
搜索相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel


class SearchMode(str, Enum):
    """搜索模式"""

    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"


class SearchResultType(str, Enum):
    """搜索结果类型"""

    KNOWLEDGE_POINT = "knowledge_point"
    REPOSITORY = "repository"
    FILE = "file"


class SearchRequest(BaseModel):
    """搜索请求参数"""

    q: str
    repositoryId: Optional[str] = None
    category: Optional[str] = None
    mode: Optional[SearchMode] = None
    page: Optional[int] = None
    pageSize: Optional[int] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class SearchResult(BaseModel):
    """搜索结果"""

    type: SearchResultType
    score: float
    pointId: Optional[str] = None
    point: Optional[Dict] = None
    repository: Optional[Dict] = None
    matchedText: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class SearchResponse(BaseModel):
    """搜索响应"""

    query: str
    mode: SearchMode
    results: List[SearchResult] = []
    facets: Optional[Dict] = None
    durationMs: int = 0

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class SearchSuggestion(BaseModel):
    """搜索建议"""

    text: str
    type: str
    count: int

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class SearchSuggestionsResponse(BaseModel):
    """搜索建议响应"""

    query: str
    suggestions: List[SearchSuggestion] = []

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
