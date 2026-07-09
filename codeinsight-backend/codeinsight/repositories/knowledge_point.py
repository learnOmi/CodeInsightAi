"""
KnowledgePoint 数据访问对象

提供知识点实体的 CRUD 操作。
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import KnowledgePointModel


class KnowledgePointDAO:
    """知识点数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> KnowledgePointModel:
        """
        创建知识点

        Args:
            db: 异步数据库会话
            data: 包含知识点字段的字典（来自 LLM Agent 输出）

        Returns:
            创建的 KnowledgePointModel 实例
        """
        kp = KnowledgePointModel(**data)
        db.add(kp)
        await db.flush()
        await db.refresh(kp)
        return kp

    async def get_by_id(self, db: AsyncSession, point_id: UUID) -> KnowledgePointModel | None:
        """
        根据 ID 获取知识点

        Args:
            db: 异步数据库会话
            point_id: 知识点 ID

        Returns:
            KnowledgePointModel 实例，不存在则返回 None
        """
        result = await db.execute(
            select(KnowledgePointModel).where(KnowledgePointModel.id == point_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        repository_id: UUID,
        version: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[KnowledgePointModel]:
        """
        分页获取知识点列表

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID（必填）
            version: 分析版本号筛选
            category: 分类筛选（DP-/AD-/AL-/ET-/DK-）
            tag: 标签筛选
            skip: 跳过的记录数
            limit: 返回的记录数上限
            sort_by: 排序字段
            sort_order: 排序方向

        Returns:
            KnowledgePointModel 列表
        """
        query = select(KnowledgePointModel).where(
            KnowledgePointModel.repository_id == repository_id
        )

        if version is not None:
            query = query.where(KnowledgePointModel.version == version)

        if category is not None:
            query = query.where(KnowledgePointModel.category == category)

        if tag is not None:
            query = query.where(
                KnowledgePointModel.tags.contains([tag])
            )

        # 排序
        order_column = getattr(KnowledgePointModel, sort_by, KnowledgePointModel.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(order_column.asc())
        else:
            query = query.order_by(order_column.desc())

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        db: AsyncSession,
        repository_id: UUID,
        version: str | None = None,
        category: str | None = None,
    ) -> int:
        """
        统计知识点数量

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            version: 版本号筛选
            category: 分类筛选

        Returns:
            符合条件的记录数
        """
        query = select(func.count()).where(
            KnowledgePointModel.repository_id == repository_id
        )

        if version is not None:
            query = query.where(KnowledgePointModel.version == version)

        if category is not None:
            query = query.where(KnowledgePointModel.category == category)

        result = await db.execute(query)
        return result.scalar() or 0

    async def update(self, db: AsyncSession, point_id: UUID, data: dict) -> KnowledgePointModel:
        """
        更新知识点

        Args:
            db: 异步数据库会话
            point_id: 知识点 ID
            data: 要更新的字段字典

        Returns:
            更新后的 KnowledgePointModel 实例

        Raises:
            ValueError: 知识点不存在
        """
        kp = await self.get_by_id(db, point_id)
        if kp is None:
            raise ValueError(f"KnowledgePoint {point_id} not found")

        for key, value in data.items():
            setattr(kp, key, value)

        await db.flush()
        await db.refresh(kp)
        return kp

    async def delete(self, db: AsyncSession, point_id: UUID) -> bool:
        """
        删除知识点

        Args:
            db: 异步数据库会话
            point_id: 知识点 ID

        Returns:
            是否删除成功
        """
        kp = await self.get_by_id(db, point_id)
        if kp is None:
            return False

        await db.delete(kp)
        await db.flush()
        return True
