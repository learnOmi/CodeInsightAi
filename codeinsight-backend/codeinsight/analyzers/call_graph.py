"""
调用图构建器

将 AST 中的 call 节点关联到函数定义节点，构建完整的调用图。

匹配策略：
1. 精确匹配：call_name 完全匹配函数名（function/method/constructor）
2. 方法调用：name.method 匹配同名方法
3. 构造器调用：new Class() 匹配 constructor 节点
4. 动态调用：getattr/反射等标记为 "dynamic"，不匹配目标
5. 未知调用：无法匹配，标记为 "unknown"，callee_node_id = None
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import async_session_factory
from codeinsight.models import AstNodeModel
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO

logger = logging.getLogger(__name__)

# 函数类型：可作为被调用目标
_CALLABLE_NODE_TYPES: set[str] = {"function", "method", "constructor"}

# 动态调用模式（精确匹配，不匹配 obj.getattr(x)）
_DYNAMIC_CALL_NAMES = frozenset({"getattr", "setattr", "delattr", "hasattr", "__getattr__"})


class CallGraphBuilder:
    """
    调用图构建器

    从 ast_nodes 表中的 call 节点和函数定义节点出发，构建调用边（caller → callee）。
    """

    def __init__(
        self,
        ast_dao: AstNodeDAO | None = None,
        call_edge_dao: CallEdgeDAO | None = None,
    ):
        self.ast_dao = ast_dao or AstNodeDAO()
        self.call_edge_dao = call_edge_dao or CallEdgeDAO()

    async def build(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
        dry_run: bool = False,
    ) -> int:
        """
        构建调用图

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话（由调用者管理生命周期）
            dry_run: True 时不写入数据库，只返回调用边列表长度

        Returns:
            创建的调用边数量（dry_run 时返回计算出的边数量）
        """
        edges_data = await self.build_data(repo_uuid, db=db)

        if dry_run:
            logger.info("调用图构建 (dry_run): repo=%s, edges=%d", repo_uuid, len(edges_data))
            return len(edges_data)

        await self.call_edge_dao.delete_by_repository(db, repo_uuid)
        if edges_data:
            await self.call_edge_dao.create_many(db, edges_data)
        logger.info("调用图构建完成: repo=%s, edges=%d", repo_uuid, len(edges_data))
        return len(edges_data)

    async def build_data(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
        file_ids: list[UUID] | None = None,
    ) -> list[dict]:
        """
        构建调用图数据（不写入数据库）

        A-1 修复：支持 file_ids 过滤，避免全量加载所有节点。

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话
            file_ids: 可选的文件 ID 列表，限制查询范围（增量分析用）

        Returns:
            调用边数据列表
        """
        call_nodes = await self.ast_dao.get_by_repository_and_types(db, repo_uuid, {"call"}, file_ids=file_ids)
        function_nodes = await self.ast_dao.get_by_repository_and_types(
            db, repo_uuid, _CALLABLE_NODE_TYPES, file_ids=file_ids
        )

        logger.info(
            "调用图数据构建: repo=%s, file_ids=%s, calls=%d, functions=%d",
            repo_uuid,
            len(file_ids) if file_ids else "all",
            len(call_nodes),
            len(function_nodes),
        )

        function_index = self._build_function_index(function_nodes)
        return self._match_call_edges(call_nodes, function_index, repo_uuid)

    async def build_data_for_files(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
        file_ids: list[UUID] | None = None,
    ) -> list[dict]:
        """
        为指定文件构建调用图数据（增量分析用）

        A-1 修复：已委托给 build_data，统一使用 file_ids 过滤。

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话
            file_ids: 需要构建调用图的文件 ID 列表（None 时等同于全量 build_data）

        Returns:
            调用边数据列表
        """
        if file_ids is None:
            return await self.build_data(repo_uuid, db=db)

        if not file_ids:
            logger.info("调用图增量构建: repo=%s, file_ids=0 (跳过)", repo_uuid)
            return []

        return await self.build_data(repo_uuid, db=db, file_ids=file_ids)

    @staticmethod
    def _build_function_index(function_nodes: list[AstNodeModel]) -> dict[str, list[AstNodeModel]]:
        """
        构建函数索引

        支持函数重载：name → [node] 映射。
        """
        index: dict[str, list[AstNodeModel]] = {}
        for node in function_nodes:
            index.setdefault(node.name, []).append(node)
        return index

    @staticmethod
    def _build_function_by_file_index(function_nodes: list[AstNodeModel]) -> dict[UUID, list[AstNodeModel]]:
        """
        按文件构建函数索引

        Args:
            function_nodes: 函数/方法节点列表

        Returns:
            file_id → [function_node] 映射
        """
        index: dict[UUID, list[AstNodeModel]] = {}
        for node in function_nodes:
            index.setdefault(node.file_id, []).append(node)
        # 按 start_line 排序，方便后续查找
        for file_id in index:
            index[file_id].sort(key=lambda n: n.start_line)
        return index

    @staticmethod
    def _find_enclosing_function(
        call_node: AstNodeModel,
        function_by_file_index: dict[UUID, list[AstNodeModel]],
    ) -> AstNodeModel | None:
        """
        找到包含该调用节点的函数/方法

        通过位置匹配：找到同一文件中 start_line <= call.start_line
        且 end_line >= call.start_line 的函数/方法节点。

        对于嵌套函数，选择最内层（end_line 最小）的函数。

        Args:
            call_node: call 类型节点
            function_by_file_index: 按文件组织的函数索引

        Returns:
            包含该调用的函数/方法节点，或 None
        """
        functions = function_by_file_index.get(call_node.file_id, [])
        if not functions:
            return None

        call_line = call_node.start_line
        candidates = []

        for func in functions:
            if func.start_line <= call_line <= func.end_line:
                candidates.append(func)

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        return min(candidates, key=lambda f: f.end_line)

    @staticmethod
    def _match_call_edges(
        call_nodes: list[AstNodeModel],
        function_index: dict[str, list[AstNodeModel]],
        repo_uuid: UUID,
    ) -> list[dict]:
        """
        匹配调用边

        Args:
            call_nodes: call 类型节点列表
            function_index: 函数索引（name → [node]）
            repo_uuid: 仓库 UUID

        Returns:
            调用边数据列表
        """
        edges_data = []

        function_nodes = []
        for nodes in function_index.values():
            function_nodes.extend(nodes)
        function_by_file_index = CallGraphBuilder._build_function_by_file_index(function_nodes)

        for call_node in call_nodes:
            call_name = call_node.name.strip()

            # A-6: 防御空/None 名称
            if not call_name:
                continue

            # 找到包含该调用的函数/方法节点
            enclosing_func = CallGraphBuilder._find_enclosing_function(call_node, function_by_file_index)
            caller_node_id = enclosing_func.id if enclosing_func else call_node.id

            # 动态调用：精确匹配动态模式名，不匹配 getattr.x 等对象方法
            if call_name in _DYNAMIC_CALL_NAMES:
                edges_data.append(
                    {
                        "repository_id": repo_uuid,
                        "caller_node_id": caller_node_id,
                        "callee_node_id": None,
                        "start_line": call_node.start_line,
                        "start_column": call_node.start_column,
                        "call_name": call_name,
                        "call_type": "dynamic",
                    }
                )
                continue

            # 方法调用：name.method 格式
            if call_name.startswith("*."):
                method_name = call_name[2:]  # 去掉 "*."
                candidates = function_index.get(method_name, [])
            # 构造器调用：new ClassName
            elif call_name.startswith("new "):
                class_name = call_name[4:]  # 去掉 "new "
                candidates = function_index.get(class_name, [])
            else:
                # 精确匹配
                candidates = function_index.get(call_name, [])

            if candidates:
                # 有多个重载时，创建多个调用边（指向每个可能的目标）
                for candidate in candidates:
                    edges_data.append(
                        {
                            "repository_id": repo_uuid,
                            "caller_node_id": caller_node_id,
                            "callee_node_id": candidate.id,
                            "start_line": call_node.start_line,
                            "start_column": call_node.start_column,
                            "call_name": call_name,
                            "call_type": "static",
                        }
                    )
            else:
                # 未知调用
                edges_data.append(
                    {
                        "repository_id": repo_uuid,
                        "caller_node_id": caller_node_id,
                        "callee_node_id": None,
                        "start_line": call_node.start_line,
                        "start_column": call_node.start_column,
                        "call_name": call_name,
                        "call_type": "unknown",
                    }
                )

        return edges_data


class CallGraphQuery:
    """
    调用图查询接口

    提供正向/反向查询和调用链遍历。
    """

    def __init__(
        self,
        call_edge_dao: CallEdgeDAO | None = None,
        ast_dao: AstNodeDAO | None = None,
    ):
        self.call_edge_dao = call_edge_dao or CallEdgeDAO()
        self.ast_dao = ast_dao or AstNodeDAO()

    async def _get_session(self, db: AsyncSession | None = None, method_name: str = "") -> tuple[AsyncSession, bool]:
        """
        获取数据库会话（A-11 修复：提取重复的 session 管理模板）

        Args:
            db: 可选的数据库会话
            method_name: 调用方法名，用于日志警告

        Returns:
            (session, use_context) 元组，use_context 表示是否需要手动关闭
        """
        if db is None:
            db = await async_session_factory().__aenter__()
            use_context = True
            if method_name:
                logger.warning(
                    "%s: 未传入 db session，已创建新 session。建议调用方传入共享 session 以优化资源管理",
                    method_name,
                )
        else:
            use_context = False
        return db, use_context

    async def get_callees(
        self,
        caller_node_id: UUID,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """
        获取该节点调用的所有目标（正向调用图）

        Args:
            caller_node_id: 调用节点 ID
            db: 可选的数据库会话；为 None 时创建独立会话（兼容旧调用）

        Returns:
            调用边列表（含 caller 和 callee 节点信息）
        """
        db, use_context = await self._get_session(db, "get_callees")

        try:
            edges = await self.call_edge_dao.get_callees(db, caller_node_id)

            # A-2: 批量预加载所有 callee 节点，消除 N+1
            callee_ids = [e.callee_node_id for e in edges if e.callee_node_id]
            callee_map: dict[UUID, AstNodeModel | None] = {}
            if callee_ids:
                nodes_result = await db.execute(select(AstNodeModel).where(AstNodeModel.id.in_(callee_ids)))
                for node in nodes_result.scalars().all():
                    callee_map[node.id] = node

            callees_result = []
            for edge in edges:
                callee = callee_map.get(edge.callee_node_id) if edge.callee_node_id else None
                callees_result.append(
                    {
                        "edge_id": edge.id,
                        "call_name": edge.call_name,
                        "call_type": edge.call_type,
                        "start_line": edge.start_line,
                        "start_column": edge.start_column,
                        "callee": (
                            {
                                "id": str(callee.id),
                                "name": callee.name,
                                "node_type": callee.node_type,
                            }
                            if callee
                            else None
                        ),
                    }
                )
            return callees_result
        finally:
            if use_context:
                await db.__aexit__(None, None, None)

    async def get_callers(
        self,
        callee_node_id: UUID,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """
        获取调用该节点的所有调用者（反向调用图）

        Args:
            callee_node_id: 被调用节点 ID
            db: 可选的数据库会话；为 None 时创建独立会话（兼容旧调用）

        Returns:
            调用边列表（含 caller 节点信息）
        """
        db, use_context = await self._get_session(db, "get_callers")

        try:
            edges = await self.call_edge_dao.get_callers(db, callee_node_id)

            # A-2: 批量预加载所有 caller 节点，消除 N+1
            caller_ids = [e.caller_node_id for e in edges if e.caller_node_id]
            caller_map: dict[UUID, AstNodeModel | None] = {}
            if caller_ids:
                nodes_result = await db.execute(select(AstNodeModel).where(AstNodeModel.id.in_(caller_ids)))
                for node in nodes_result.scalars().all():
                    caller_map[node.id] = node

            callers_result = []
            for edge in edges:
                caller = caller_map.get(edge.caller_node_id) if edge.caller_node_id else None
                callers_result.append(
                    {
                        "edge_id": edge.id,
                        "call_name": edge.call_name,
                        "call_type": edge.call_type,
                        "start_line": edge.start_line,
                        "start_column": edge.start_column,
                        "caller": (
                            {
                                "id": str(caller.id),
                                "name": caller.name,
                                "node_type": caller.node_type,
                                "file_path": caller.file_path,
                            }
                            if caller
                            else None
                        ),
                    }
                )
            return callers_result
        finally:
            if use_context:
                await db.__aexit__(None, None, None)

    async def get_call_chain(
        self,
        caller_node_id: UUID,
        max_depth: int = 10,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """
        获取从该节点开始的完整调用链（DFS 遍历）

        A-2 修复：使用共享 session 而非每层新建，消除 session 爆炸。

        Args:
            caller_node_id: 起始节点 ID
            max_depth: 最大遍历深度
            db: 可选的数据库会话；为 None 时创建独立会话

        Returns:
            调用链节点列表（按深度排序）
        """
        db, use_context = await self._get_session(db)

        try:
            return await self._dfs_chain(db, caller_node_id, max_depth, 0, [], set())
        finally:
            if use_context:
                await db.__aexit__(None, None, None)

    async def _dfs_chain(
        self,
        db: AsyncSession,
        node_id: UUID,
        max_depth: int,
        depth: int,
        path: list[str],
        visited: set[UUID],
    ) -> list[dict]:
        """DFS 调用链递归实现"""
        chain: list[dict] = []
        if depth > max_depth or node_id in visited:
            return chain

        visited.add(node_id)

        # 使用共享 session 获取 callees
        callees = await self.get_callees(node_id, db=db)
        for callee_info in callees:
            if callee_info["callee"]:
                callee_id = UUID(callee_info["callee"]["id"])
                new_path = path + [callee_info["call_name"]]
                chain.append(
                    {
                        "depth": depth + 1,
                        "node_id": callee_info["callee"]["id"],
                        "node_name": callee_info["callee"]["name"],
                        "node_type": callee_info["callee"]["node_type"],
                        "call_name": callee_info["call_name"],
                        "call_type": callee_info["call_type"],
                        "path": new_path,
                    }
                )
                chain.extend(await self._dfs_chain(db, callee_id, max_depth, depth + 1, new_path, visited))

        return chain
