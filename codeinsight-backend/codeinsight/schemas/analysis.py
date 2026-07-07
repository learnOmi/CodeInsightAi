"""
分析任务相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。
"""

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel


class AnalysisMode(str, Enum):
    """分析模式"""

    FULL = "full"
    INCREMENTAL = "incremental"


class TaskStatus(str, Enum):
    """分析任务状态"""

    PENDING = "pending"
    SCANNING = "scanning"
    PARSING = "parsing"
    ANALYZING_MODULES = "analyzing_modules"
    STORING = "storing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Agent 类型别名（对应 TS 中的 type alias）
AgentType = Literal[
    "design_pattern",
    "architecture",
    "algorithm",
    "engineering_tips",
    "domain_knowledge",
]


class AnalysisProgress(BaseModel):
    """分析进度信息"""

    currentStep: TaskStatus
    percent: float
    filesProcessed: int
    filesTotal: int
    knowledgePointsFound: int

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class AnalyzeRequest(BaseModel):
    """提交分析任务请求"""

    mode: Optional[AnalysisMode] = None
    agents: Optional[List[AgentType]] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class AnalysisTask(BaseModel):
    """分析任务"""

    taskId: str
    repositoryId: str
    status: TaskStatus
    mode: AnalysisMode
    progress: AnalysisProgress
    submittedAt: str
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    errorMessage: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class AnalysisVersion(BaseModel):
    """分析版本"""

    version: str
    status: TaskStatus
    totalFiles: int
    knowledgePointsCount: int
    isCurrent: bool
    createdAt: str
    completedAt: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
