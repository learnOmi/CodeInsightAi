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

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import async_session_factory
from codeinsight.models import AstNodeModel
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO

logger = logging.getLogger(__name__)

# 函数类型：可作为被调用目标
_CALLABLE_NODE_TYPES = frozenset({"function", "method", "constructor"})


class CallGraphBuilder:
    """
    调用图构建器

    从 ast_nodes 表中的 call 节点和函数定义节点出发，构建调用边（caller → callee）。
    """

    def __init__(self):
        self.ast_dao = AstNodeDAO()
        self.call_edge_dao = CallEdgeDAO()

    async def build(self, repo_uuid: UUID, db: AsyncSession | None = None) -> int:
        """
        构建调用图

        Args:
            repo_uuid: 仓库 UUID
            db: 可选的数据库会话。提供时不复用；否则创建独立会话。

        Returns:
            创建的调用边数量
        """
        use_context = db is None
        session = db
        if use_context:
            session = await async_session_factory().__aenter__()

        assert session is not None  # type narrowing for mypy

        try:
            # 1. 按需加载 call 节点和函数定义节点（避免全量加载所有 AST 节点）
            call_nodes = await self.ast_dao.get_by_repository_and_types(session, repo_uuid, {"call"})
            function_nodes = await self.ast_dao.get_by_repository_and_types(session, repo_uuid, _CALLABLE_NODE_TYPES)

            logger.info(
                "调用图构建: repo=%s, calls=%d, functions=%d",
                repo_uuid,
                len(call_nodes),
                len(function_nodes),
            )

            # 2. 构建函数索引（name → [node]）
            function_index = self._build_function_index(function_nodes)

            # 3. 匹配调用边
            edges_data = self._match_call_edges(call_nodes, function_index, repo_uuid)

            # 4. 清理旧数据并批量写入
            await self.call_edge_dao.delete_by_repository(session, repo_uuid)
            if edges_data:
                await self.call_edge_dao.create_many(session, edges_data)
            await session.commit()

            logger.info("调用图构建完成: repo=%s, edges=%d", repo_uuid, len(edges_data))
            return len(edges_data)
        finally:
            if use_context:
                await session.__aexit__(None, None, None)

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

        for call_node in call_nodes:
            call_name = call_node.name.strip()

            # 动态调用：包含 getattr/setattr 等反射模式
            if CallGraphBuilder._is_dynamic_call(call_name):
                edges_data.append(
                    {
                        "repository_id": repo_uuid,
                        "caller_node_id": call_node.id,
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
                            "caller_node_id": call_node.id,
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
                        "caller_node_id": call_node.id,
                        "callee_node_id": None,
                        "start_line": call_node.start_line,
                        "start_column": call_node.start_column,
                        "call_name": call_name,
                        "call_type": "unknown",
                    }
                )

        return edges_data

    @staticmethod
    def _is_dynamic_call(call_name: str) -> bool:
        """
        判断是否为动态调用（反射/getattr 等无法静态分析的模式）

        Args:
            call_name: 调用名称

        Returns:
            是否为动态调用
        """
        dynamic_patterns = frozenset({"getattr", "setattr", "delattr", "hasattr", "__getattr__"})
        return any(call_name == pattern or call_name.startswith(pattern + ".") for pattern in dynamic_patterns)


class CallGraphQuery:
    """
    调用图查询接口

    提供正向/反向查询和调用链遍历。
    """

    def __init__(self):
        self.call_edge_dao = CallEdgeDAO()
        self.ast_dao = AstNodeDAO()

    async def get_callees(self, caller_node_id: UUID) -> list[dict]:
        """
        获取该节点调用的所有目标（正向调用图）

        Returns:
            调用边列表（含 caller 和 callee 节点信息）
        """
        async with async_session_factory() as db:
            edges = await self.call_edge_dao.get_callees(db, caller_node_id)

            result = []
            for edge in edges:
                callee = None
                if edge.callee_node_id:
                    callee = await self.ast_dao.get_by_id(db, edge.callee_node_id)

                result.append(
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
            return result

    async def get_callers(self, callee_node_id: UUID) -> list[dict]:
        """
        获取调用该节点的所有调用者（反向调用图）

        Returns:
            调用边列表（含 caller 节点信息）
        """
        async with async_session_factory() as db:
            edges = await self.call_edge_dao.get_callers(db, callee_node_id)

            result = []
            for edge in edges:
                caller = await self.ast_dao.get_by_id(db, edge.caller_node_id)

                result.append(
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
            return result

    async def get_call_chain(self, caller_node_id: UUID, max_depth: int = 10) -> list[dict]:
        """
        获取从该节点开始的完整调用链（DFS 遍历）

        Args:
            caller_node_id: 起始节点 ID
            max_depth: 最大遍历深度

        Returns:
            调用链节点列表（按深度排序）
        """
        visited: set[UUID] = set()
        chain: list[dict] = []

        async def dfs(node_id: UUID, depth: int, path: list[str]) -> None:
            if depth > max_depth or node_id in visited:
                return

            visited.add(node_id)

            # 获取该节点的所有 callee
            callees = await self.get_callees(node_id)
            for callee_info in callees:
                if callee_info["callee"]:
                    callee_id = callee_info["callee"]["id"]
                    new_path = path + [callee_info["call_name"]]
                    chain.append(
                        {
                            "depth": depth + 1,
                            "node_id": callee_id,
                            "node_name": callee_info["callee"]["name"],
                            "node_type": callee_info["callee"]["node_type"],
                            "call_name": callee_info["call_name"],
                            "call_type": callee_info["call_type"],
                            "path": new_path,
                        }
                    )
                    await dfs(UUID(callee_id), depth + 1, new_path)

        await dfs(caller_node_id, 0, [])
        return chain
