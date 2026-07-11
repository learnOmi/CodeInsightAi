"""
仓库相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 OpenAPI 自动同步到前端 TypeScript 类型。

字段命名约定：
- Python 字段使用 snake_case（符合 PEP 8 与 ruff N815 规则）
- 通过 alias_generator=to_camel 在 API 序列化时自动转为 camelCase
- populate_by_name=True 允许同时使用 snake_case 和 camelCase 进行反序列化
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel


class RepositoryStatus(StrEnum):
    """仓库分析状态"""

    PENDING = "pending"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Repository(BaseModel):
    """仓库信息"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: UUID
    name: str
    path: str
    status: RepositoryStatus
    current_version: str | None = None
    file_count: int = 0
    line_count: int = 0
    knowledge_points_count: int = 0
    language_distribution: dict[str, int] = {}
    created_at: datetime
    updated_at: datetime
    last_analyzed_at: datetime | None = None

    @field_serializer("id")
    def serialize_id(self, value: UUID, _info) -> str:
        return str(value)

    @field_serializer("created_at", "updated_at", "last_analyzed_at")
    def serialize_datetime(self, value: datetime | None, _info) -> str | None:
        if value is None:
            return None
        return value.isoformat()


class RepositoryCreate(BaseModel):
    """创建仓库请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    name: str
    path: str
    auto_analyze: bool | None = None


class RepositoryUpdate(BaseModel):
    """更新仓库请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    name: str | None = None
