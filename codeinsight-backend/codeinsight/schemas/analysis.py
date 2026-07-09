"""
分析任务相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。

字段命名约定：
- Python 字段使用 snake_case（符合 PEP 8 与 ruff N815 规则）
- 通过 alias_generator=to_camel 在 API 序列化时自动转为 camelCase
- populate_by_name=True 允许同时使用 snake_case 和 camelCase 进行反序列化
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class AnalysisMode(StrEnum):
    """分析模式"""

    FULL = "full"
    INCREMENTAL = "incremental"


class TaskStatus(StrEnum):
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

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    current_step: TaskStatus
    percent: float
    files_processed: int
    files_total: int
    knowledge_points_found: int


class AnalyzeRequest(BaseModel):
    """提交分析任务请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    mode: AnalysisMode | None = None
    agents: list[AgentType] | None = None


class AnalysisTask(BaseModel):
    """分析任务"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    task_id: str
    repository_id: str
    status: TaskStatus
    mode: AnalysisMode
    progress: AnalysisProgress
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


class AnalysisVersion(BaseModel):
    """分析版本"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    version: str
    status: TaskStatus
    total_files: int
    analyzed_files: int = 0
    knowledge_points_count: int
    is_current: bool
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    created_at: str
