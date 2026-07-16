"""
CodeInsight AI Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from .analysis import (
    AgentType,
    AnalysisMode,
    AnalysisProgress,
    AnalysisTask,
    AnalysisVersion,
    AnalyzeRequest,
    TaskStatus,
)
from .api_route import ApiRoute, ApiRouteCreate
from .ast_node import AstNode, AstNodeCreate
from .call_edge import CallEdge, CallEdgeCreate
from .file import File, FileCreate, FileUpdate
from .framework_pattern import FrameworkPattern, FrameworkPatternCreate
from .knowledge import (
    CallChainNode,
    CodeSnippet,
    ExpansionContent,
    KnowledgeCategory,
    KnowledgeMetadata,
    KnowledgePoint,
    KnowledgePointListRequest,
    KnowledgeStats,
    LearningResource,
    PaginatedKnowledgePoints,
)
from .module_dependency import ModuleDependency, ModuleDependencyCreate
from .repository import Repository, RepositoryCreate, RepositoryStatus, RepositoryUpdate
from .search import (
    SearchMode,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchResultType,
    SearchSuggestion,
    SearchSuggestionsResponse,
)

__all__ = [
    # file
    "File",
    "FileCreate",
    "FileUpdate",
    # ast_node
    "AstNode",
    "AstNodeCreate",
    # call_edge
    "CallEdge",
    "CallEdgeCreate",
    # api_route
    "ApiRoute",
    "ApiRouteCreate",
    # framework_pattern
    "FrameworkPattern",
    "FrameworkPatternCreate",
    # module_dependency
    "ModuleDependency",
    "ModuleDependencyCreate",
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
    "KnowledgePointListRequest",
    "KnowledgeStats",
    "PaginatedKnowledgePoints",
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
