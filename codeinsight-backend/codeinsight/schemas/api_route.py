"""
API 路由相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel


class ApiRoute(BaseModel):
    """API 路由"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: UUID
    repository_id: UUID
    analysis_version_id: UUID | None = None
    ast_node_id: UUID | None = None
    http_method: str
    path_pattern: str
    handler_function: str
    handler_file: str
    middlewares: list = []
    framework: str
    created_at: datetime

    @field_serializer("id", "repository_id", "analysis_version_id", "ast_node_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime, _info) -> str:
        return value.isoformat()


class ApiRouteCreate(BaseModel):
    """创建 API 路由请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    repository_id: UUID
    analysis_version_id: UUID | None = None
    ast_node_id: UUID | None = None
    http_method: str
    path_pattern: str
    handler_function: str
    handler_file: str
    middlewares: list = []
    framework: str
