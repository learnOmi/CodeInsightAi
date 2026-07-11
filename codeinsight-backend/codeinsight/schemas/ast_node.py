"""
AST 节点相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel


class AstNode(BaseModel):
    """AST 节点"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: UUID
    repository_id: UUID
    file_id: UUID
    node_type: str
    name: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    parent_node_id: UUID | None = None
    file_path: str
    language: str
    signature: str | None = None
    docstring: str | None = None
    created_at: datetime

    @field_serializer("id", "repository_id", "file_id", "parent_node_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime, _info) -> str:
        return value.isoformat()


class AstNodeCreate(BaseModel):
    """创建 AST 节点请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    repository_id: UUID
    file_id: UUID
    node_type: str
    name: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    parent_node_id: UUID | None = None
    file_path: str
    language: str
    signature: str | None = None
    docstring: str | None = None
