"""
搜索相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。

字段命名约定：
- Python 字段使用 snake_case（符合 PEP 8 与 ruff N815 规则）
- 通过 alias_generator=to_camel 在 API 序列化时自动转为 camelCase
- populate_by_name=True 允许同时使用 snake_case 和 camelCase 进行反序列化
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class SearchMode(StrEnum):
    """搜索模式"""

    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"


class SearchResultType(StrEnum):
    """搜索结果类型"""

    KNOWLEDGE_POINT = "knowledge_point"
    REPOSITORY = "repository"
    FILE = "file"


class SearchRequest(BaseModel):
    """搜索请求参数"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    q: str
    repository_id: str | None = None
    category: str | None = None
    mode: SearchMode | None = None
    page: int | None = None
    page_size: int | None = None


class SearchResult(BaseModel):
    """搜索结果"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    type: SearchResultType
    score: float
    point_id: str | None = None
    point: dict | None = None
    repository: dict | None = None
    matched_text: str | None = None


class SearchResponse(BaseModel):
    """搜索响应"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    query: str
    mode: SearchMode
    results: list[SearchResult] = []
    facets: dict | None = None
    duration_ms: int = 0


class SearchSuggestion(BaseModel):
    """搜索建议"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    text: str
    type: str
    count: int


class SearchSuggestionsResponse(BaseModel):
    """搜索建议响应"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    query: str
    suggestions: list[SearchSuggestion] = []
