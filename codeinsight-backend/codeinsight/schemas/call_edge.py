"""
调用边相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel


class CallEdge(BaseModel):
    """调用边"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: UUID
    repository_id: UUID
    caller_node_id: UUID
    callee_node_id: UUID | None = None
    start_line: int
    start_column: int
    call_name: str
    call_type: str
    created_at: datetime

    @field_serializer("id", "repository_id", "caller_node_id", "callee_node_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime, _info) -> str:
        return value.isoformat()


class CallEdgeCreate(BaseModel):
    """创建调用边请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    repository_id: UUID
    caller_node_id: UUID
    callee_node_id: UUID | None = None
    start_line: int
    start_column: int
    call_name: str
    call_type: str = "static"
