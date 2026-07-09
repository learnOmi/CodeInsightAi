"""
File 数据访问对象

提供文件实体的 CRUD 操作。
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import FileModel
from codeinsight.schemas import FileCreate, FileUpdate


class FileDAO:
    """文件数据访问对象"""

    async def create(self, db: AsyncSession, data: FileCreate) -> FileModel:
        """
        创建文件

        Args:
            db: 异步数据库会话
            data: 创建请求数据

        Returns:
            创建的 FileModel 实例
        """
        file_obj = FileModel(
            path=data.path,
            absolute_path=data.absolute_path,
            language=data.language,
            line_count=data.line_count,
            size_bytes=data.size_bytes,
            content_hash=data.content_hash,
        )
        db.add(file_obj)
        await db.flush()
        await db.refresh(file_obj)
        return file_obj

    async def get_by_id(self, db: AsyncSession, file_id: UUID) -> FileModel | None:
        """
        根据 ID 获取文件

        Args:
            db: 异步数据库会话
            file_id: 文件 ID

        Returns:
            FileModel 实例，不存在则返回 None
        """
        result = await db.execute(select(FileModel).where(FileModel.id == file_id))
        return result.scalar_one_or_none()

    async def list_by_repository(self, db: AsyncSession, repository_id: UUID, skip: int = 0, limit: int = 100) -> list[FileModel]:
        """
        分页获取指定仓库的文件列表

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            skip: 跳过的记录数
            limit: 返回的记录数上限

        Returns:
            FileModel 列表
        """
        result = await db.execute(
            select(FileModel)
            .where(FileModel.repository_id == repository_id)
            .offset(skip)
            .limit(limit)
            .order_by(FileModel.path)
        )
        return list(result.scalars().all())

    async def update(self, db: AsyncSession, file_id: UUID, data: FileUpdate) -> FileModel:
        """
        更新文件信息

        Args:
            db: 异步数据库会话
            file_id: 文件 ID
            data: 更新数据

        Returns:
            更新后的 FileModel 实例

        Raises:
            ValueError: 文件不存在
        """
        file_obj = await self.get_by_id(db, file_id)
        if file_obj is None:
            raise ValueError(f"File {file_id} not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(file_obj, key, value)

        await db.flush()
        await db.refresh(file_obj)
        return file_obj

    async def delete(self, db: AsyncSession, file_id: UUID) -> bool:
        """
        删除文件

        Args:
            db: 异步数据库会话
            file_id: 文件 ID

        Returns:
            是否删除成功
        """
        file_obj = await self.get_by_id(db, file_id)
        if file_obj is None:
            return False

        await db.delete(file_obj)
        await db.flush()
        return True

    async def get_by_content_hash(self, db: AsyncSession, repository_id: UUID, content_hash: str) -> FileModel | None:
        """
        根据内容哈希查找文件（用于增量检测）

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            content_hash: 内容哈希

        Returns:
            FileModel 实例，不存在则返回 None
        """
        result = await db.execute(
            select(FileModel)
            .where(FileModel.repository_id == repository_id, FileModel.content_hash == content_hash)
        )
        return result.scalar_one_or_none()
