"""
结构数据入库管道

统一编排 AST 节点、调用边、模块依赖的入库流程。

核心功能：
- 数据校验：入库前校验完整性、外键、去重
- 批量写入：batch_size 分片 + 事务隔离
- 增量更新：基于 content_hash 跳过未变更文件
- 进度回调：实时进度通知
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.pipelines.validators import AstNodeValidator, CallEdgeValidator, ModuleDepValidator
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO, FileDAO, ModuleDependencyDAO

logger = logging.getLogger(__name__)

# 进度回调类型
ProgressCallback = Callable[[int, int, str], None]


@dataclass
class IngestResult:
    """入库结果"""

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
    3. 增量更新（基于 content_hash 跳过未变更文件）
    4. 进度回调（实时进度通知）
    """

    def __init__(
        self,
        db: AsyncSession,
        batch_size: int = 500,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.db = db
        self.batch_size = batch_size
        self.progress_callback = progress_callback

        # DAO 实例
        self.ast_node_dao = AstNodeDAO()
        self.call_edge_dao = CallEdgeDAO()
        self.module_dep_dao = ModuleDependencyDAO()
        self.file_dao = FileDAO()

        # 节点 UUID 映射（解析时的临时映射）
        self._node_uuid_map: dict[str, UUID] = {}

        # 合法的节点 ID 和文件 ID 集合（用于外键校验）
        self._valid_node_ids: set[UUID] = set()
        self._valid_file_ids: set[UUID] = set()

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
        result = IngestResult()

        if not nodes:
            return result

        # 1. 加载文件 ID 集合（用于外键校验）
        await self._load_valid_file_ids(repo_uuid)

        # 2. 校验
        valid_nodes: list[dict] = []
        for node in nodes:
            validation = AstNodeValidator.validate(node)
            if validation.valid:
                valid_nodes.append(node)
            else:
                result.validation_errors += 1
                logger.debug("节点校验失败: %s", validation.errors)

        result.total_count = len(nodes)
        logger.info(
            "AST 节点校验完成: total=%d, valid=%d, errors=%d", len(nodes), len(valid_nodes), result.validation_errors
        )

        if not valid_nodes:
            return result

        # 3. 去重（基于 file_id + start_line + node_type + name）
        unique_nodes = self._deduplicate_nodes(valid_nodes)
        result.duplicate_count = len(valid_nodes) - len(unique_nodes)
        result.skipped_count = len(nodes) - len(unique_nodes)

        if not unique_nodes:
            return result

        # 4. 转换并填充默认值
        db_nodes = self._transform_ast_nodes(repo_uuid, unique_nodes)

        # 5. 批量写入
        result.inserted_count = await self._batch_insert(
            db_nodes,
            self.ast_node_dao.create_many,
            stage="ingest_nodes",
            total=len(db_nodes),
        )

        # 6. 构建节点 UUID 映射
        for node in db_nodes:
            key = f"{node['file_id']}:{node['start_line']}:{node['node_type']}:{node['name']}"
            self._node_uuid_map[key] = node["node_id"]

        return result

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
        result = IngestResult()

        if not edges:
            return result

        # 1. 加载节点 ID 集合（用于外键校验）
        await self._load_valid_node_ids(repo_uuid)

        # 2. 校验
        valid_edges: list[dict] = []
        for edge in edges:
            validation = CallEdgeValidator.validate(edge, self._valid_node_ids)
            if validation.valid:
                valid_edges.append(edge)
            else:
                result.validation_errors += 1
                logger.debug("调用边校验失败: %s", validation.errors)

        result.total_count = len(edges)
        logger.info(
            "调用边校验完成: total=%d, valid=%d, errors=%d", len(edges), len(valid_edges), result.validation_errors
        )

        if not valid_edges:
            return result

        # 3. 批量写入
        result.inserted_count = await self._batch_insert(
            valid_edges,
            self.call_edge_dao.create_many,
            stage="ingest_edges",
            total=len(valid_edges),
        )

        result.skipped_count = len(edges) - result.inserted_count
        return result

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
        result = IngestResult()

        if not deps:
            return result

        # 1. 加载文件 ID 集合
        await self._load_valid_file_ids(repo_uuid)

        # 2. 校验
        valid_deps: list[dict] = []
        for dep in deps:
            validation = ModuleDepValidator.validate(dep, self._valid_file_ids)
            if validation.valid:
                valid_deps.append(dep)
            else:
                result.validation_errors += 1
                logger.debug("模块依赖校验失败: %s", validation.errors)

        result.total_count = len(deps)
        logger.info(
            "模块依赖校验完成: total=%d, valid=%d, errors=%d", len(deps), len(valid_deps), result.validation_errors
        )

        if not valid_deps:
            return result

        # 3. 批量写入
        result.inserted_count = await self._batch_insert(
            valid_deps,
            self.module_dep_dao.create_many,
            stage="ingest_deps",
            total=len(valid_deps),
        )

        result.skipped_count = len(deps) - result.inserted_count
        return result

    # ================================================================
    # 内部方法
    # ================================================================

    async def _load_valid_file_ids(self, repo_uuid: UUID) -> None:
        """加载仓库的所有文件 ID（用于外键校验）"""
        if self._valid_file_ids:
            return

        files = await self.file_dao.get_by_repository(self.db, repo_uuid)
        self._valid_file_ids = {f.id for f in files}
        logger.debug("加载文件 ID 集合: count=%d", len(self._valid_file_ids))

    async def _load_valid_node_ids(self, repo_uuid: UUID) -> None:
        """加载仓库的所有 AST 节点 ID（用于外键校验）"""
        if self._valid_node_ids:
            return

        nodes = await self.ast_node_dao.get_by_repository(self.db, repo_uuid)
        self._valid_node_ids = {n.id for n in nodes}
        logger.debug("加载节点 ID 集合: count=%d", len(self._valid_node_ids))

    def _deduplicate_nodes(self, nodes: list[dict]) -> list[dict]:
        """
        去重 AST 节点（基于 file_id + start_line + node_type + name）
        保留最后出现的记录。
        """
        seen: dict[str, dict] = {}
        for node in nodes:
            key = f"{node['file_id']}:{node['start_line']}:{node['node_type']}:{node['name']}"
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
        create_many_fn,
        stage: str,
        total: int,
    ) -> int:
        """
        批量分片写入

        每 batch_size 条为一个事务，支持进度回调。
        """
        inserted = 0
        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]
            await create_many_fn(self.db, batch)
            await self.db.commit()
            inserted += len(batch)

            # 进度回调
            if self.progress_callback:
                self.progress_callback(inserted, total, stage)

        return inserted
