"""
外部依赖相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel


class ExternalDependency(BaseModel):
    """外部依赖"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: UUID
    repository_id: UUID
    analysis_version_id: UUID | None = None
    ecosystem: str
    group_name: str | None = None
    artifact_name: str
    version: str | None = None
    version_range: str | None = None
    scope: str = "compile"
    declaration_file: str | None = None
    used_by_files: list = []
    created_at: datetime

    @field_serializer("id", "repository_id", "analysis_version_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime, _info) -> str:
        return value.isoformat()


class ExternalDependencyCreate(BaseModel):
    """创建外部依赖请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    repository_id: UUID
    analysis_version_id: UUID | None = None
    ecosystem: str
    group_name: str | None = None
    artifact_name: str
    version: str | None = None
    version_range: str | None = None
    scope: str = "compile"
    declaration_file: str | None = None
    used_by_files: list = []
