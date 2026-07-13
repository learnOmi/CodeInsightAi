"""
结构数据入库管道

统一编排 AST 节点、调用边、模块依赖的入库流程。

核心功能：
- 数据校验：入库前校验完整性、外键、去重
- 批量写入：batch_size 分片 + 事务隔离
- 进度回调：实时进度通知
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.pipelines.validators import AstNodeValidator, CallEdgeValidator, ModuleDepValidator
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO, FileDAO, ModuleDependencyDAO

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 进度回调类型：progress_callback(inserted, total, stage)
ProgressCallback = Callable[[int, int, str], None]

# 批量创建函数类型：create_many_fn(db, data_list) -> model_list
CreateManyFn = Callable[[AsyncSession, list[dict]], Awaitable[list]]


@dataclass
class IngestResult:
    """入库结果

    PL-6 修复：重新定义 skipped_count 语义，仅表示实际跳过的记录数。
    """

    total_count: int = 0
    inserted_count: int = 0
    skipped_count: int = 0
    duplicate_count: int = 0
    validation_errors: int = 0


class StructureDataPipeline:
    """
    结构数据入库管道

    统一管理 AST 节点、调用边、模块依赖的入库，提供：
    1. 数据校验（完整性、外键、去重）
    2. 批量写入（batch_size 分片 + 事务隔离）
    3. 进度回调（实时进度通知）
    """

    def __init__(
        self,
        db: AsyncSession,
        batch_size: int | None = None,
        progress_callback: ProgressCallback | None = None,
        ast_node_dao: AstNodeDAO | None = None,
        call_edge_dao: CallEdgeDAO | None = None,
        module_dep_dao: ModuleDependencyDAO | None = None,
        file_dao: FileDAO | None = None,
    ) -> None:
        # P-3 修复：batch_size 从配置读取，不再硬编码
        from codeinsight.config import settings

        self.db = db
        self.batch_size = batch_size or settings.ingest_batch_size
        self.progress_callback = progress_callback

        self.ast_node_dao = ast_node_dao or AstNodeDAO()
        self.call_edge_dao = call_edge_dao or CallEdgeDAO()
        self.module_dep_dao = module_dep_dao or ModuleDependencyDAO()
        self.file_dao = file_dao or FileDAO()

        # SV-3 修复：缓存 key 改为 (repository_id, ...) 组合，避免跨仓库缓存污染
        self._node_uuid_map: dict[tuple[UUID, UUID, int, str, str], UUID] = {}
        self._valid_node_ids: dict[UUID, set[UUID]] = {}
        self._valid_file_ids: dict[UUID, set[UUID]] = {}

    def clear_cache(self) -> None:
        """
        清空内部缓存

        SV-3 修复：跨仓库分析时必须调用，避免使用上一个仓库的缓存数据。
        """
        self._node_uuid_map.clear()
        self._valid_node_ids.clear()
        self._valid_file_ids.clear()

    # ================================================================
    # 公开 API
    # ================================================================

    async def ingest_ast_nodes(
        self,
        repo_uuid: UUID,
        nodes: list[dict],
    ) -> IngestResult:
        """
        入库 AST 节点

        Args:
            repo_uuid: 仓库 UUID
            nodes: 节点数据列表，每项包含 file_id, node_type, name, start_line 等

        Returns:
            IngestResult
        """

        def _post_insert(repo_uuid: UUID, db_nodes: list[dict]) -> None:
            for node in db_nodes:
                key = (repo_uuid, node["file_id"], node["start_line"], node["node_type"], node["name"])
                self._node_uuid_map[key] = node["node_id"]

        return await self._ingest_items(
            items=nodes,
            repo_uuid=repo_uuid,
            load_valid_ids_fn=self._load_valid_file_ids,
            validator_fn=lambda node: AstNodeValidator.validate(node, self._valid_file_ids[repo_uuid]),
            create_many_fn=self.ast_node_dao.create_many,
            stage="ingest_nodes",
            stage_name="AST 节点",
            dedup_fn=self._deduplicate_nodes,
            transform_fn=self._transform_ast_nodes,
            post_insert_fn=_post_insert,
        )

    async def ingest_call_edges(
        self,
        repo_uuid: UUID,
        edges: list[dict],
    ) -> IngestResult:
        """
        入库调用边

        Args:
            repo_uuid: 仓库 UUID
            edges: 调用边数据列表

        Returns:
            IngestResult
        """
        return await self._ingest_items(
            items=edges,
            repo_uuid=repo_uuid,
            load_valid_ids_fn=self._load_valid_node_ids,
            validator_fn=lambda edge: CallEdgeValidator.validate(edge, self._valid_node_ids[repo_uuid]),
            create_many_fn=self.call_edge_dao.create_many,
            stage="ingest_edges",
            stage_name="调用边",
        )

    async def ingest_module_deps(
        self,
        repo_uuid: UUID,
        deps: list[dict],
    ) -> IngestResult:
        """
        入库模块依赖

        Args:
            repo_uuid: 仓库 UUID
            deps: 模块依赖数据列表

        Returns:
            IngestResult
        """
        return await self._ingest_items(
            items=deps,
            repo_uuid=repo_uuid,
            load_valid_ids_fn=self._load_valid_file_ids,
            validator_fn=lambda dep: ModuleDepValidator.validate(dep, self._valid_file_ids[repo_uuid]),
            create_many_fn=self.module_dep_dao.create_many,
            stage="ingest_deps",
            stage_name="模块依赖",
        )

    async def _ingest_items(
        self,
        items: list[dict],
        repo_uuid: UUID,
        load_valid_ids_fn: Callable[[UUID], Awaitable[None]],
        validator_fn: Callable[[dict], object],
        create_many_fn: CreateManyFn,
        stage: str,
        stage_name: str,
        dedup_fn: Callable[[list[dict]], list[dict]] | None = None,
        transform_fn: Callable[[UUID, list[dict]], list[dict]] | None = None,
        post_insert_fn: Callable[[UUID, list[dict]], None] | None = None,
    ) -> IngestResult:
        """
        通用入库模板方法（SV-11 优化：提取三个 ingest_* 的公共逻辑）

        Args:
            items: 待入库数据列表
            repo_uuid: 仓库 UUID
            load_valid_ids_fn: 加载验证所需 ID 集合的方法
            validator_fn: 校验函数，返回具有 valid 属性的对象
            create_many_fn: DAO 的批量创建方法
            stage: 进度阶段名称
            stage_name: 日志显示的阶段名称
            dedup_fn: 去重函数，可选
            transform_fn: 转换函数，接收 (repo_uuid, items)，返回转换后列表，可选
            post_insert_fn: 插入后回调函数，接收 (repo_uuid, inserted_items)，可选

        Returns:
            IngestResult
        """
        result = IngestResult()

        if not items:
            return result

        await load_valid_ids_fn(repo_uuid)

        valid_items: list[dict] = []
        for item in items:
            validation = validator_fn(item)
            if getattr(validation, "valid", False):
                valid_items.append(item)
            else:
                result.validation_errors += 1
                logger.debug("%s校验失败: %s", stage_name, getattr(validation, "errors", ""))

        result.total_count = len(items)
        logger.info(
            "%s校验完成: total=%d, valid=%d, errors=%d",
            stage_name,
            len(items),
            len(valid_items),
            result.validation_errors,
        )

        if not valid_items:
            return result

        if dedup_fn:
            unique_items = dedup_fn(valid_items)
            result.duplicate_count = len(valid_items) - len(unique_items)
            if not unique_items:
                return result
            valid_items = unique_items

        if transform_fn:
            valid_items = transform_fn(repo_uuid, valid_items)
            if not valid_items:
                return result

        result.inserted_count = await self._batch_insert(
            valid_items,
            create_many_fn,
            stage=stage,
            total=len(valid_items),
        )

        if post_insert_fn:
            post_insert_fn(repo_uuid, valid_items)

        result.skipped_count = len(valid_items) - result.inserted_count
        return result

    # ================================================================
    # 内部方法
    # ================================================================

    async def _load_valid_file_ids(self, repo_uuid: UUID) -> None:
        """加载仓库的所有文件 ID（用于外键校验）"""
        if repo_uuid in self._valid_file_ids:
            return

        files = await self.file_dao.get_by_repository(self.db, repo_uuid)
        self._valid_file_ids[repo_uuid] = {f.id for f in files}
        logger.debug("加载文件 ID 集合: repo=%s, count=%d", repo_uuid, len(self._valid_file_ids[repo_uuid]))

    async def _load_valid_node_ids(self, repo_uuid: UUID) -> None:
        """加载仓库的所有 AST 节点 ID（用于外键校验）

        SV-2 优化：仅加载节点 ID，避免全量加载节点对象，减少内存占用。
        """
        if repo_uuid in self._valid_node_ids:
            return

        self._valid_node_ids[repo_uuid] = await self.ast_node_dao.get_ids_by_repository(self.db, repo_uuid)
        logger.debug("加载节点 ID 集合: repo=%s, count=%d", repo_uuid, len(self._valid_node_ids[repo_uuid]))

    def _deduplicate_nodes(self, nodes: list[dict]) -> list[dict]:
        """
        去重 AST 节点（基于 file_id + start_line + node_type + name）
        保留最后出现的记录。

        SV-10 优化：使用 tuple 作为 key，避免 O(n) 字符串拼接。
        """
        seen: dict[tuple, dict] = {}
        for node in nodes:
            key = (node["file_id"], node["start_line"], node["node_type"], node["name"])
            seen[key] = node
        return list(seen.values())

    def _transform_ast_nodes(self, repo_uuid: UUID, nodes: list[dict]) -> list[dict]:
        """
        转换 AST 节点为数据库写入格式

        - 注入 repository_id
        - 生成 node_id（由数据库默认值生成，这里传入 UUID 用于映射）
        """
        db_nodes = []
        for node in nodes:
            node_id = uuid4()
            db_node = {
                "id": node_id,
                "repository_id": repo_uuid,
                "file_id": node["file_id"],
                "node_type": node["node_type"],
                "name": node["name"],
                "start_line": node["start_line"],
                "end_line": node.get("end_line", node["start_line"]),
                "start_column": node.get("start_column", 0),
                "end_column": node.get("end_column", 0),
                "parent_node_id": node.get("parent_node_id"),
                "file_path": node["file_path"],
                "language": node["language"],
                "signature": node.get("signature"),
                "docstring": node.get("docstring"),
            }
            # 保留 node_id 用于映射
            db_node["node_id"] = node_id
            db_nodes.append(db_node)
        return db_nodes

    async def _batch_insert(
        self,
        data: list[dict],
        create_many_fn: CreateManyFn,
        stage: str,
        total: int,
    ) -> int:
        """
        批量分片写入

        每 batch_size 条为一个 flush，不直接 commit。
        由调用者统一管理事务（commit/rollback）。

        Args:
            data: 待插入数据列表
            create_many_fn: DAO 的批量创建方法
            stage: 进度阶段名称
            total: 总条数

        Returns:
            成功插入的条数

        Raises:
            Exception: 批量写入失败时，已 flush 的数据可通过外层事务 rollback
        """
        inserted = 0
        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]
            await create_many_fn(self.db, batch)
            # 仅 flush，不 commit —— 由调用者管理事务边界
            await self.db.flush()
            inserted += len(batch)

            # 进度回调
            if self.progress_callback:
                self.progress_callback(inserted, total, stage)

        return inserted
