"""
文件相关 Pydantic Schema

以 Pydantic 模型为单一事实来源，通过 FastAPI 的 OpenAPI 能力自动同步到前端 TypeScript 类型。
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class File(BaseModel):
    """代码文件"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: str
    repository_id: str
    path: str
    absolute_path: str
    language: str
    line_count: int
    size_bytes: int
    content_hash: str
    created_at: str
    updated_at: str


class FileCreate(BaseModel):
    """创建文件请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    path: str
    absolute_path: str
    language: str
    line_count: int = 0
    size_bytes: int = 0
    content_hash: str


class FileUpdate(BaseModel):
    """更新文件请求"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    line_count: int | None = None
    size_bytes: int | None = None
    content_hash: str | None = None
