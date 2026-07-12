"""
模块依赖相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel


class ModuleDependency(BaseModel):
    """模块依赖"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: UUID
    repository_id: UUID
    importer_file_id: UUID
    imported_file_id: UUID | None = None
    import_name: str
    import_type: str
    created_at: datetime

    @field_serializer("id", "repository_id", "importer_file_id", "imported_file_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime, _info) -> str:
        return value.isoformat()


class ModuleDependencyCreate(BaseModel):
    """创建模块依赖请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    repository_id: UUID
    importer_file_id: UUID
    imported_file_id: UUID | None = None
    import_name: str
    import_type: str = "absolute"
