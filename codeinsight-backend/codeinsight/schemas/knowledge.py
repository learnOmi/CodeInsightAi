"""
知识点相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。

字段命名约定：
- Python 字段使用 snake_case（符合 PEP 8 与 ruff N815 规则）
- 通过 alias_generator=to_camel 在 API 序列化时自动转为 camelCase
- populate_by_name=True 允许同时使用 snake_case 和 camelCase 进行反序列化
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class KnowledgeCategory(StrEnum):
    """
    知识点分类枚举

    DP-: 设计模式 (Design Pattern)
    AD-: 架构决策 (Architecture Decision)
    AL-: 算法实现 (Algorithm)
    ET-: 工程技巧 (Engineering Tip)
    DK-: 领域知识 (Domain Knowledge)
    """

    DESIGN_PATTERN = "DP-"
    ARCHITECTURE_DECISION = "AD-"
    ALGORITHM = "AL-"
    ENGINEERING_TIP = "ET-"
    DOMAIN_KNOWLEDGE = "DK-"


class CodeSnippet(BaseModel):
    """代码片段"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    file_path: str
    start_line: int
    end_line: int
    highlighted_lines: list[int] = []
    language: str
    signature: str


class CallChainNode(BaseModel):
    """调用链节点"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    node_id: str
    node_type: Literal[
        "function", "class", "method", "function_call", "import", "module"
    ]
    file: str
    lines: tuple[int, int]
    signature: str
    direction: Literal["entry", "call", "implementation", "export"]


class LearningResource(BaseModel):
    """学习资料"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    title: str
    url: str
    type: Literal["book", "article", "video", "course"]


class ExpansionContent(BaseModel):
    """拓展内容"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    principle: str
    applicable_scenarios: list[str] = []
    best_practices: list[str] = []
    related_patterns: list[str] = []
    learning_resources: list[LearningResource] = []


class KnowledgeMetadata(BaseModel):
    """知识点元数据"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    agent: str
    prompt_version: str
    model: str
    tokens_used: dict[str, int] = {}


class KnowledgePoint(BaseModel):
    """知识点"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: str
    category: KnowledgeCategory
    category_name: str
    title: str
    description: str
    confidence: float
    tags: list[str] = []
    code_snippets: list[CodeSnippet] = []
    call_chain: list[CallChainNode] = []
    expansion: ExpansionContent
    version: str
    repository_id: str
    embedding: list[float] | None = None  # pgvector 向量嵌入
    metadata: KnowledgeMetadata = Field(validation_alias="knowledge_metadata")
    created_at: str
    updated_at: str


class KnowledgePointListRequest(BaseModel):
    """知识点列表请求参数"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    version: str | None = None
    category: str | None = None
    tag: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedKnowledgePoints(BaseModel):
    """分页知识点列表响应"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    items: list[KnowledgePoint]
    total: int
    page: int
    page_size: int
    total_pages: int


class KnowledgeStats(BaseModel):
    """知识点统计"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    total_points: int
    by_category: dict[KnowledgeCategory, int] = {}
    by_confidence: dict[str, int] = {}
    top_tags: list[dict[str, int]] = []
    files_covered: int = 0
    total_lines_analyzed: int = 0
