"""
FileAnalysisProgress 数据访问对象

R-R4: 提供文件级分析进度的 CRUD 操作，支持精确的断点续跑。
"""

from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import FileAnalysisProgressModel


class FileAnalysisProgressDAO:
    """文件级分析进度数据访问对象"""

    async def upsert(
        self,
        db: AsyncSession,
        repository_id: UUID,
        version_id: UUID,
        file_path: str,
        stage: str,
        status: str,
        progress_data: dict | None = None,
    ) -> FileAnalysisProgressModel:
        """
        R-R4: 插入或更新文件级进度记录

        使用 PostgreSQL UPSERT 语义，同一 (version_id, file_path, stage) 只有一条记录。

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            version_id: 分析版本 ID
            file_path: 文件路径
            stage: 分析阶段
            status: 处理状态
            progress_data: 附加进度数据

        Returns:
            FileAnalysisProgressModel 实例
        """
        from sqlalchemy import text as sql_text

        data = {
            "repository_id": repository_id,
            "analysis_version_id": version_id,
            "file_path": file_path,
            "stage": stage,
            "status": status,
            "progress_data": progress_data or {},
        }

        stmt = (
            insert(FileAnalysisProgressModel)
            .values(**data)
            .on_conflict_do_update(
                index_elements=["analysis_version_id", "file_path", "stage"],
                index_where=text("analysis_version_id IS NOT NULL"),
                set_={
                    "status": status,
                    "progress_data": progress_data or {},
                    "updated_at": sql_text("NOW()"),
                },
            )
        )

        await db.execute(stmt)
        await db.flush()

        # 返回实际查询到的 ORM 实例
        result = await db.execute(
            select(FileAnalysisProgressModel).where(
                FileAnalysisProgressModel.analysis_version_id == version_id,
                FileAnalysisProgressModel.file_path == file_path,
                FileAnalysisProgressModel.stage == stage,
            )
        )
        return result.scalar_one()

    async def batch_upsert(self, db: AsyncSession, records: list[dict]) -> None:
        """
        R-R4: 批量插入或更新文件级进度记录

        Args:
            db: 异步数据库会话
            records: 记录列表，每项包含 repository_id, analysis_version_id, file_path, stage, status, progress_data
        """
        if not records:
            return

        stmt = insert(FileAnalysisProgressModel).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["analysis_version_id", "file_path", "stage"],
            index_where=text("analysis_version_id IS NOT NULL"),
            set_={
                "status": stmt.excluded.status,
                "progress_data": stmt.excluded.progress_data,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db.execute(stmt)
        await db.flush()

    async def get_by_file_and_stage(
        self, db: AsyncSession, version_id: UUID, file_path: str, stage: str
    ) -> FileAnalysisProgressModel | None:
        """
        获取指定版本、文件和阶段的进度记录

        Args:
            db: 异步数据库会话
            version_id: 分析版本 ID
            file_path: 文件路径
            stage: 分析阶段

        Returns:
            FileAnalysisProgressModel 或 None
        """
        result = await db.execute(
            select(FileAnalysisProgressModel).where(
                FileAnalysisProgressModel.analysis_version_id == version_id,
                FileAnalysisProgressModel.file_path == file_path,
                FileAnalysisProgressModel.stage == stage,
            )
        )
        return result.scalar_one_or_none()

    async def get_completed_file_paths(self, db: AsyncSession, version_id: UUID, stage: str) -> set[str]:
        """
        R-R4: 获取指定版本和阶段中已完成处理的所有文件路径

        用于断点续跑时跳过已成功解析的文件。

        Args:
            db: 异步数据库会话
            version_id: 分析版本 ID
            stage: 分析阶段

        Returns:
            已完成的文件路径集合
        """
        result = await db.execute(
            select(FileAnalysisProgressModel.file_path).where(
                FileAnalysisProgressModel.analysis_version_id == version_id,
                FileAnalysisProgressModel.stage == stage,
                FileAnalysisProgressModel.status == "completed",
            )
        )
        return {row[0] for row in result.all()}

    async def get_failed_file_paths(self, db: AsyncSession, version_id: UUID, stage: str) -> set[str]:
        """
        获取指定版本和阶段中失败的文件路径

        Args:
            db: 异步数据库会话
            version_id: 分析版本 ID
            stage: 分析阶段

        Returns:
            失败的文件路径集合
        """
        result = await db.execute(
            select(FileAnalysisProgressModel.file_path).where(
                FileAnalysisProgressModel.analysis_version_id == version_id,
                FileAnalysisProgressModel.stage == stage,
                FileAnalysisProgressModel.status == "failed",
            )
        )
        return {row[0] for row in result.all()}

    async def get_processing_file_paths(self, db: AsyncSession, version_id: UUID, stage: str) -> set[str]:
        """
        获取指定版本和阶段中正在处理中的文件路径（用于故障恢复）

        Args:
            db: 异步数据库会话
            version_id: 分析版本 ID
            stage: 分析阶段

        Returns:
            处理中的文件路径集合
        """
        result = await db.execute(
            select(FileAnalysisProgressModel.file_path).where(
                FileAnalysisProgressModel.analysis_version_id == version_id,
                FileAnalysisProgressModel.stage == stage,
                FileAnalysisProgressModel.status == "processing",
            )
        )
        return {row[0] for row in result.all()}

    async def count_by_stage(self, db: AsyncSession, version_id: UUID, stage: str, status: str | None = None) -> int:
        """
        统计指定版本和阶段的记录数

        Args:
            db: 异步数据库会话
            version_id: 分析版本 ID
            stage: 分析阶段
            status: 可选的状态过滤

        Returns:
            记录数
        """
        query = select(func.count()).where(
            FileAnalysisProgressModel.analysis_version_id == version_id,
            FileAnalysisProgressModel.stage == stage,
        )
        if status is not None:
            query = query.where(FileAnalysisProgressModel.status == status)
        result = await db.execute(query)
        return result.scalar() or 0

    async def delete_by_version(self, db: AsyncSession, version_id: UUID) -> int:
        """
        删除指定版本的所有进度记录

        Args:
            db: 异步数据库会话
            version_id: 分析版本 ID

        Returns:
            删除的记录数
        """
        result = await db.execute(
            delete(FileAnalysisProgressModel).where(FileAnalysisProgressModel.analysis_version_id == version_id)
        )
        await db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return cast(int, rowcount) or 0

    async def update_status(
        self,
        db: AsyncSession,
        version_id: UUID,
        file_path: str,
        stage: str,
        status: str,
        progress_data: dict | None = None,
    ) -> FileAnalysisProgressModel | None:
        """
        更新指定文件的处理状态

        Args:
            db: 异步数据库会话
            version_id: 分析版本 ID
            file_path: 文件路径
            stage: 分析阶段
            status: 新状态
            progress_data: 可选的附加数据

        Returns:
            更新后的记录或 None
        """
        if progress_data is not None:
            stmt = (
                update(FileAnalysisProgressModel)
                .where(
                    FileAnalysisProgressModel.analysis_version_id == version_id,
                    FileAnalysisProgressModel.file_path == file_path,
                    FileAnalysisProgressModel.stage == stage,
                )
                .values(status=status, progress_data=progress_data)
            )
        else:
            stmt = (
                update(FileAnalysisProgressModel)
                .where(
                    FileAnalysisProgressModel.analysis_version_id == version_id,
                    FileAnalysisProgressModel.file_path == file_path,
                    FileAnalysisProgressModel.stage == stage,
                )
                .values(status=status)
            )

        await db.execute(stmt)
        await db.flush()
        return None
