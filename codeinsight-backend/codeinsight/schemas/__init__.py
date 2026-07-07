"""
CodeInsight AI Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from .repository import Repository, RepositoryCreate, RepositoryUpdate, RepositoryStatus
from .knowledge import (
    KnowledgeCategory,
    CodeSnippet,
    CallChainNode,
    LearningResource,
    ExpansionContent,
    KnowledgeMetadata,
    KnowledgePoint,
    KnowledgeStats,
)
from .analysis import (
    AnalysisMode,
    TaskStatus,
    AgentType,
    AnalysisProgress,
    AnalyzeRequest,
    AnalysisTask,
    AnalysisVersion,
)
from .search import (
    SearchMode,
    SearchResultType,
    SearchRequest,
    SearchResult,
    SearchResponse,
    SearchSuggestion,
    SearchSuggestionsResponse,
)

__all__ = [
    # repository
    "Repository",
    "RepositoryCreate",
    "RepositoryUpdate",
    "RepositoryStatus",
    # knowledge
    "KnowledgeCategory",
    "CodeSnippet",
    "CallChainNode",
    "LearningResource",
    "ExpansionContent",
    "KnowledgeMetadata",
    "KnowledgePoint",
    "KnowledgeStats",
    # analysis
    "AnalysisMode",
    "TaskStatus",
    "AgentType",
    "AnalysisProgress",
    "AnalyzeRequest",
    "AnalysisTask",
    "AnalysisVersion",
    # search
    "SearchMode",
    "SearchResultType",
    "SearchRequest",
    "SearchResult",
    "SearchResponse",
    "SearchSuggestion",
    "SearchSuggestionsResponse",
]
