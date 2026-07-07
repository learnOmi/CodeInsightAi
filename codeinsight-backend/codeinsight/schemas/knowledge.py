"""
知识点相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。
"""

from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel


class KnowledgeCategory(str, Enum):
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

    filePath: str
    startLine: int
    endLine: int
    highlightedLines: List[int] = []
    language: str
    signature: str

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class CallChainNode(BaseModel):
    """调用链节点"""

    nodeId: str
    nodeType: Literal[
        "function", "class", "method", "function_call", "import", "module"
    ]
    file: str
    lines: tuple[int, int]
    signature: str
    direction: Literal["entry", "call", "implementation", "export"]

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class LearningResource(BaseModel):
    """学习资料"""

    title: str
    url: str
    type: Literal["book", "article", "video", "course"]

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class ExpansionContent(BaseModel):
    """拓展内容"""

    principle: str
    applicableScenarios: List[str] = []
    bestPractices: List[str] = []
    relatedPatterns: List[str] = []
    learningResources: List[LearningResource] = []

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class KnowledgeMetadata(BaseModel):
    """知识点元数据"""

    agent: str
    promptVersion: str
    model: str
    tokensUsed: Dict[str, int] = {}

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class KnowledgePoint(BaseModel):
    """知识点"""

    id: str
    category: KnowledgeCategory
    categoryName: str
    title: str
    description: str
    confidence: float
    tags: List[str] = []
    codeSnippets: List[CodeSnippet] = []
    callChain: List[CallChainNode] = []
    expansion: ExpansionContent
    version: str
    repositoryId: str
    metadata: KnowledgeMetadata
    createdAt: str
    updatedAt: str

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class KnowledgeStats(BaseModel):
    """知识点统计"""

    totalPoints: int
    byCategory: Dict[KnowledgeCategory, int] = {}
    byConfidence: Dict[str, int] = {}
    topTags: List[Dict[str, int]] = []
    filesCovered: int = 0
    totalLinesAnalyzed: int = 0

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
