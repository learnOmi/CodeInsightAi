"""
仓库相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。
"""

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel


class RepositoryStatus(str, Enum):
    """仓库分析状态"""

    PENDING = "pending"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Repository(BaseModel):
    """仓库信息"""

    id: str
    name: str
    path: str
    status: RepositoryStatus
    currentVersion: Optional[str] = None
    fileCount: int = 0
    lineCount: int = 0
    knowledgePointsCount: int = 0
    languageDistribution: Dict[str, int] = {}
    createdAt: str
    updatedAt: str
    lastAnalyzedAt: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class RepositoryCreate(BaseModel):
    """创建仓库请求"""

    name: str
    path: str
    autoAnalyze: Optional[bool] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class RepositoryUpdate(BaseModel):
    """更新仓库请求"""

    name: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
