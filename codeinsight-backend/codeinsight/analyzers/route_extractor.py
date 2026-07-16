"""
RouteExtractor - API 路由提取器

从 AST 节点中提取 API 路由信息，支持多种后端框架：
- Spring: @GetMapping, @PostMapping 等注解
- Flask/FastAPI: @app.route, @app.get 等装饰器
- Express/Koa: app.get('/path', handler) 调用模式

提取的路由信息写入 api_routes 表。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import async_session_factory
from codeinsight.models import AstNodeModel
from codeinsight.repositories import ApiRouteDAO

logger = logging.getLogger(__name__)

# Spring HTTP 方法映射
SPRING_METHOD_ANNOTATIONS: dict[str, str] = {
    "@GetMapping": "GET",
    "@PostMapping": "POST",
    "@PutMapping": "PUT",
    "@DeleteMapping": "DELETE",
    "@PatchMapping": "PATCH",
    "@RequestMapping": "",  # 需从 method 参数推断
}

# Python 装饰器 → HTTP 方法映射
PYTHON_DECORATOR_METHODS: dict[str, str] = {
    "@app.route": "GET",
    "@bp.route": "GET",
    "@app.get": "GET",
    "@app.post": "POST",
    "@app.put": "PUT",
    "@app.delete": "DELETE",
    "@app.patch": "PATCH",
    "@router.get": "GET",
    "@router.post": "POST",
    "@router.put": "PUT",
    "@router.delete": "DELETE",
    "@router.patch": "PATCH",
    "@bp.get": "GET",
    "@bp.post": "POST",
    "@bp.put": "PUT",
    "@bp.delete": "DELETE",
    "@bp.patch": "PATCH",
}

# Express/Koa HTTP 方法调用名
EXPRESS_METHOD_CALLS: dict[str, str] = {
    "app.get": "GET",
    "app.post": "POST",
    "app.put": "PUT",
    "app.delete": "DELETE",
    "app.patch": "PATCH",
    "router.get": "GET",
    "router.post": "POST",
    "router.put": "PUT",
    "router.delete": "DELETE",
    "router.patch": "PATCH",
}

# 路径参数标准化正则
# Express/Koa: :id → {id}（仅匹配 / 后的冒号，避免误匹配端口号等）
EXPRESS_PATH_PARAM = re.compile(r"(?<=/):(\w+)")
# Flask: <int:id> 或 <id> → {id}
FLASK_PATH_PARAM = re.compile(r"<(?:\w+:)?(\w+)>")


class RouteInfo:
    """
    提取的路由信息

    Attributes:
        http_method: HTTP 方法 (GET, POST, PUT, DELETE, PATCH)
        path_pattern: 标准化路径模式 (如 /api/users/{id})
        handler_function: 处理函数名
        handler_file: 处理函数所在文件
        framework: 来源框架 (spring_boot, flask, fastapi, express, koa)
        ast_node_id: 关联的 AST 节点 ID
        middlewares: 中间件链
    """

    def __init__(
        self,
        http_method: str,
        path_pattern: str,
        handler_function: str,
        handler_file: str,
        framework: str,
        ast_node_id: UUID | None = None,
        middlewares: list[dict[str, Any]] | None = None,
    ) -> None:
        self.http_method = http_method
        self.path_pattern = path_pattern
        self.handler_function = handler_function
        self.handler_file = handler_file
        self.framework = framework
        self.ast_node_id = ast_node_id
        self.middlewares = middlewares or []

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "http_method": self.http_method,
            "path_pattern": self.path_pattern,
            "handler_function": self.handler_function,
            "handler_file": self.handler_file,
            "framework": self.framework,
            "ast_node_id": self.ast_node_id,
            "middlewares": self.middlewares,
        }


class RouteExtractor:
    """
    API 路由提取器

    从 ast_nodes 表中查询带有路由注解/装饰器的节点，
    提取路由信息并写入 api_routes 表。

    支持框架：
    - Spring Boot: @GetMapping, @PostMapping 等注解
    - Flask: @app.route("/path") 装饰器
    - FastAPI: @app.get("/path") 装饰器
    - Express: app.get("/path", handler) 调用模式
    - Koa: router.get("/path", handler) 调用模式
    """

    def __init__(self, route_dao: ApiRouteDAO | None = None) -> None:
        self.route_dao = route_dao or ApiRouteDAO()

    async def build_data(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        构建路由数据（不写入数据库）

        从 ast_nodes 表查询所有节点，根据注解/装饰器/调用模式提取路由。

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话

        Returns:
            路由数据列表，每项为可直接写入 api_routes 表的字典
        """
        routes: list[RouteInfo] = []

        # 查询所有函数/方法节点（可能带路由注解）
        result = await db.execute(
            select(AstNodeModel).where(
                AstNodeModel.repository_id == repo_uuid,
                AstNodeModel.node_type.in_(("function", "method")),
            )
        )
        func_nodes = list(result.scalars().all())

        for node in func_nodes:
            annotations = node.annotations or []
            for annotation in annotations:
                ann_name = annotation.get("name", "")
                ann_args = annotation.get("args", [])

                # Spring 路由提取
                route = self._extract_spring_route(node, ann_name, ann_args)
                if route:
                    routes.append(route)
                    continue

                # Flask/FastAPI 路由提取
                route = self._extract_python_route(node, ann_name, ann_args)
                if route:
                    routes.append(route)

        # Express/Koa 路由提取（从 call 节点提取）
        call_result = await db.execute(
            select(AstNodeModel).where(
                AstNodeModel.repository_id == repo_uuid,
                AstNodeModel.node_type == "call",
            )
        )
        call_nodes = list(call_result.scalars().all())

        for node in call_nodes:
            route = self._extract_express_route(node)
            if route:
                routes.append(route)

        logger.info("路由提取完成: repo=%s, routes=%d", repo_uuid, len(routes))

        return [r.to_dict() for r in routes]

    async def build(
        self,
        repo_uuid: UUID,
        db: AsyncSession | None = None,
    ) -> int:
        """
        构建路由并写入数据库

        Args:
            repo_uuid: 仓库 UUID
            db: 可选的数据库会话，不传入则自行创建

        Returns:
            写入的路由数量
        """
        if db is not None:
            return await self._build_inner(repo_uuid, db)

        async with async_session_factory() as db:
            return await self._build_inner(repo_uuid, db)

    async def _build_inner(self, repo_uuid: UUID, db: AsyncSession) -> int:
        """内部构建逻辑"""
        # 清理旧路由
        await self.route_dao.delete_by_repository(db, repo_uuid)

        # 提取路由
        routes_data = await self.build_data(repo_uuid, db)
        if not routes_data:
            return 0

        # 补充 repository_id
        for route in routes_data:
            route["repository_id"] = repo_uuid

        # 批量写入
        await self.route_dao.create_many(db, routes_data)
        await db.flush()

        logger.info("路由写入完成: repo=%s, count=%d", repo_uuid, len(routes_data))
        return len(routes_data)

    def _extract_spring_route(
        self,
        node: AstNodeModel,
        ann_name: str,
        ann_args: list[Any],
    ) -> RouteInfo | None:
        """
        从 Spring 注解提取路由

        Args:
            node: AST 节点
            ann_name: 注解名（如 @GetMapping）
            ann_args: 注解参数列表

        Returns:
            路由信息，不匹配时返回 None
        """
        if ann_name not in SPRING_METHOD_ANNOTATIONS:
            return None

        http_method = SPRING_METHOD_ANNOTATIONS[ann_name]

        # @RequestMapping 需从 method 参数推断
        if ann_name == "@RequestMapping":
            http_method = self._infer_method_from_args(ann_args)

        # 提取路径：注解的第一个字符串参数，或 value 属性
        path = self._extract_path_from_args(ann_args)
        if not path:
            # 类级别 @RequestMapping 可能定义基础路径，方法级别注解可能是相对路径
            path = ""

        # 标准化路径
        path = self._normalize_path(path)

        return RouteInfo(
            http_method=http_method or "GET",
            path_pattern=path or "/",
            handler_function=node.name,
            handler_file=node.file_path,
            framework="spring_boot",
            ast_node_id=node.id,
        )

    def _extract_python_route(
        self,
        node: AstNodeModel,
        ann_name: str,
        ann_args: list[Any],
    ) -> RouteInfo | None:
        """
        从 Python 装饰器提取路由（Flask/FastAPI）

        Args:
            node: AST 节点
            ann_name: 装饰器名（如 @app.get）
            ann_args: 装饰器参数列表

        Returns:
            路由信息，不匹配时返回 None
        """
        # 检查是否匹配 Flask/FastAPI 装饰器
        matched_decorator = None
        for decorator_pattern, _method in PYTHON_DECORATOR_METHODS.items():
            if ann_name.startswith(decorator_pattern):
                matched_decorator = decorator_pattern
                break

        if not matched_decorator:
            return None

        http_method = PYTHON_DECORATOR_METHODS[matched_decorator]

        # Flask @app.route 需从 methods 参数推断 HTTP 方法
        if ann_name.startswith("@app.route") or ann_name.startswith("@bp.route"):
            http_method = self._infer_method_from_args(ann_args) or "GET"

        # 提取路径
        path = self._extract_path_from_args(ann_args)
        path = self._normalize_path(path)

        # 判断框架
        framework = "flask" if ann_name.startswith("@app.route") or ann_name.startswith("@bp.route") else "fastapi"

        return RouteInfo(
            http_method=http_method,
            path_pattern=path or "/",
            handler_function=node.name,
            handler_file=node.file_path,
            framework=framework,
            ast_node_id=node.id,
        )

    def _extract_express_route(self, node: AstNodeModel) -> RouteInfo | None:
        """
        从 Express/Koa 调用模式提取路由

        匹配模式: app.get('/path', handler) 或 router.post('/path', handler)
        call 节点的 name 格式为 "*.get" / "*.post" 等（parser 统一格式）

        过滤策略：
        - 仅处理 JavaScript/TypeScript 文件
        - 必须能从 qualified_name 中提取到路径字符串，否则跳过
          （避免 obj.get('key') 等普通方法调用被误识别为路由）

        Args:
            node: call 类型的 AST 节点

        Returns:
            路由信息，不匹配时返回 None
        """
        # 仅处理 JS/TS 文件
        if node.language not in ("javascript", "typescript"):
            return None

        call_name = node.name.split("(")[0].strip()

        # 检查是否为 Express/Koa 路由注册调用
        for pattern, http_method in EXPRESS_METHOD_CALLS.items():
            method_suffix = pattern.split(".")[-1]
            # call name 格式为 "*.get" / "*.post"
            if call_name == f"*.{method_suffix}":
                # 从 qualified_name 提取路径
                path = self._extract_path_from_call_node(node)
                if not path:
                    # 无法提取路径，说明不是路由注册调用
                    return None
                path = self._normalize_path(path)

                return RouteInfo(
                    http_method=http_method,
                    path_pattern=path,
                    handler_function=call_name,
                    handler_file=node.file_path,
                    framework="express",
                    ast_node_id=node.id,
                )

        return None

    def _extract_path_from_call_node(self, node: AstNodeModel) -> str:
        """
        从 call 节点提取路径（启发式）

        Express 路由调用的路径通常在源码中作为字符串字面量出现。
        由于 AST 节点不存储完整参数列表，这里使用 qualified_name 中的信息
        或返回空字符串让后续处理补充。

        Args:
            node: call 节点

        Returns:
            路径字符串
        """
        # 如果 qualified_name 包含路径信息，尝试提取
        if node.qualified_name and "/" in node.qualified_name:
            match = re.search(r'["\'](/[^"\']*)["\']', node.qualified_name)
            if match:
                return match.group(1)
        return ""

    def _extract_path_from_args(self, args: list[Any]) -> str:
        """
        从注解/装饰器参数中提取路径

        支持以下格式：
        - @GetMapping("/api/users") → "/api/users"
        - @GetMapping(value = "/api/users") → "/api/users"
        - @app.route("/api/users") → "/api/users"
        - @app.route("/api/users", methods=["GET"]) → "/api/users"

        Args:
            args: 注解参数列表

        Returns:
            路径字符串
        """
        for arg in args:
            if isinstance(arg, str) and arg.startswith("/"):
                return arg
            # 处理 value="/path" 格式
            if isinstance(arg, dict):
                value = arg.get("value", "")
                if isinstance(value, str) and value.startswith("/"):
                    return value
                path = arg.get("path", "")
                if isinstance(path, str) and path.startswith("/"):
                    return path
        return ""

    def _infer_method_from_args(self, args: list[Any]) -> str:
        """
        从注解参数推断 HTTP 方法

        用于 @RequestMapping(method = RequestMethod.POST) 和
        @app.route("/path", methods=["POST"]) 场景。

        Args:
            args: 注解参数列表

        Returns:
            HTTP 方法，默认 GET
        """
        for arg in args:
            if isinstance(arg, dict):
                method = arg.get("method", "")
                if method and isinstance(method, str):
                    # RequestMethod.POST → POST
                    method = method.split(".")[-1].upper()
                    if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                        return str(method)
                methods = arg.get("methods", [])
                if isinstance(methods, list) and methods:
                    first = methods[0]
                    if isinstance(first, str):
                        return str(first.upper().strip("'\""))
        return "GET"

    def _normalize_path(self, path: str) -> str:
        """
        标准化路径模式

        将各框架的路径参数语法统一为 OpenAPI 风格 {param}：
        - Express/Koa: :id → {id}
        - Flask: <int:id> 或 <id> → {id}

        Args:
            path: 原始路径

        Returns:
            标准化路径
        """
        if not path:
            return ""

        # Flask <type:name> or <name> → {name}（先处理 Flask 语法，避免 : 冲突）
        path = FLASK_PATH_PARAM.sub(r"{\1}", path)

        # Express/Koa :param → {param}
        path = EXPRESS_PATH_PARAM.sub(r"{\1}", path)

        return path
