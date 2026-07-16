"""
RouteExtractor - API 路由提取器

从 AST 节点中提取 API 路由信息，支持多种后端框架和前端路由：
- Spring: @GetMapping, @PostMapping 等注解
- Flask/FastAPI: @app.route, @app.get 等装饰器
- Express/Koa: app.get('/path', handler) 调用模式
- Vue Router: createRouter({ routes: [...] }) / 路由配置数组
- React Router: createBrowserRouter([...]) / <Route path="..." />
- Angular: Routes 数组配置

提取的路由信息写入 api_routes 表。

架构说明：
    采用策略模式 + 注册机制。每种框架的路由提取逻辑封装为独立的
    RouteExtractionStrategy 实现，RouteExtractor 维护策略注册表，
    build_data 遍历所有已注册策略收集路由。新增框架支持只需实现
    策略接口并调用 register() 注册，无需修改 build_data。
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path as FsPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import async_session_factory
from codeinsight.models import AstNodeModel, FileModel, RepositoryModel
from codeinsight.repositories import ApiRouteDAO

logger = logging.getLogger(__name__)

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


class RouteExtractionStrategy(ABC):
    """
    路由提取策略抽象基类

    所有框架特定的路由提取逻辑实现此接口，通过 RouteExtractor.register()
    注册后即可参与路由提取流程。新增框架支持只需实现此接口并注册。

    子类需实现 extract() 方法，可复用本基类提供的共享工具方法
    （路径提取、HTTP 方法推断、路径标准化等）。
    """

    @abstractmethod
    async def extract(
        self,
        nodes: list[AstNodeModel],
        db: AsyncSession,
        repo_uuid: UUID,
    ) -> list[RouteInfo]:
        """
        从 AST 节点中提取路由信息

        Args:
            nodes: AST 节点列表（包含 function/method/call 类型），
                策略实现负责按 node_type 自行筛选所需节点
            db: 数据库会话（用于查询 files/repositories 等附加信息）
            repo_uuid: 仓库 UUID

        Returns:
            提取的路由信息列表
        """
        ...

    # ===== 共享工具方法（供各策略复用） =====

    def _build_route(self, node: AstNodeModel, *args: Any, **kwargs: Any) -> RouteInfo | None:
        """
        从 AST 节点构建路由信息（默认实现返回 None）

        各子策略可以覆盖此方法实现自己的路由构建逻辑。
        支持不同参数签名的策略扩展。

        Args:
            node: AST 节点
            *args: 附加参数
            **kwargs: 附加关键字参数

        Returns:
            路由信息，不匹配时返回 None
        """
        return None

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
        - Vue/React: :id → {id}

        Args:
            path: 原始路径

        Returns:
            标准化路径
        """
        if not path:
            return ""

        # Flask <type:name> or <name> → {name}（先处理 Flask 语法，避免 : 冲突）
        path = FLASK_PATH_PARAM.sub(r"{\1}", path)

        # Express/Koa/Vue/React :param → {param}
        path = EXPRESS_PATH_PARAM.sub(r"{\1}", path)

        return path


class SpringRouteStrategy(RouteExtractionStrategy):
    """
    Spring Boot 路由提取策略

    从 function/method 节点的注解中提取 Spring 路由信息。
    匹配 @GetMapping / @PostMapping / @PutMapping / @DeleteMapping /
    @PatchMapping / @RequestMapping 注解。
    """

    # Spring HTTP 方法映射
    SPRING_METHOD_ANNOTATIONS: dict[str, str] = {
        "@GetMapping": "GET",
        "@PostMapping": "POST",
        "@PutMapping": "PUT",
        "@DeleteMapping": "DELETE",
        "@PatchMapping": "PATCH",
        "@RequestMapping": "",  # 需从 method 参数推断
    }

    async def extract(
        self,
        nodes: list[AstNodeModel],
        db: AsyncSession,
        repo_uuid: UUID,
    ) -> list[RouteInfo]:
        """
        从 function/method 节点的 Spring 注解提取路由

        Args:
            nodes: AST 节点列表（仅处理 function/method 类型）
            db: 数据库会话（本策略未使用，保留以满足接口契约）
            repo_uuid: 仓库 UUID（本策略未使用，保留以满足接口契约）

        Returns:
            Spring 路由信息列表
        """
        routes: list[RouteInfo] = []
        for node in nodes:
            if node.node_type not in ("function", "method"):
                continue
            annotations = node.annotations or []
            for annotation in annotations:
                ann_name = annotation.get("name", "")
                ann_args = annotation.get("args", [])
                route = self._build_route(node, ann_name, ann_args)
                if route:
                    routes.append(route)
                    continue
        return routes

    def _build_route(
        self,
        node: AstNodeModel,
        ann_name: str,
        ann_args: list[Any],
    ) -> RouteInfo | None:
        """
        从 Spring 注解构建路由信息

        Args:
            node: AST 节点
            ann_name: 注解名（如 @GetMapping）
            ann_args: 注解参数列表

        Returns:
            路由信息，不匹配时返回 None
        """
        if ann_name not in self.SPRING_METHOD_ANNOTATIONS:
            return None

        http_method = self.SPRING_METHOD_ANNOTATIONS[ann_name]

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


class PythonRouteStrategy(RouteExtractionStrategy):
    """
    Python (Flask/FastAPI) 路由提取策略

    从 function/method 节点的装饰器中提取 Flask/FastAPI 路由信息。
    匹配 @app.route / @bp.route / @app.get / @app.post / @router.* / @bp.* 等装饰器。
    """

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

    async def extract(
        self,
        nodes: list[AstNodeModel],
        db: AsyncSession,
        repo_uuid: UUID,
    ) -> list[RouteInfo]:
        """
        从 function/method 节点的 Python 装饰器提取路由

        Args:
            nodes: AST 节点列表（仅处理 function/method 类型）
            db: 数据库会话（本策略未使用，保留以满足接口契约）
            repo_uuid: 仓库 UUID（本策略未使用，保留以满足接口契约）

        Returns:
            Flask/FastAPI 路由信息列表
        """
        routes: list[RouteInfo] = []
        for node in nodes:
            if node.node_type not in ("function", "method"):
                continue
            annotations = node.annotations or []
            for annotation in annotations:
                ann_name = annotation.get("name", "")
                ann_args = annotation.get("args", [])
                route = self._build_route(node, ann_name, ann_args)
                if route:
                    routes.append(route)
        return routes

    def _build_route(
        self,
        node: AstNodeModel,
        ann_name: str,
        ann_args: list[Any],
    ) -> RouteInfo | None:
        """
        从 Python 装饰器构建路由信息（Flask/FastAPI）

        Args:
            node: AST 节点
            ann_name: 装饰器名（如 @app.get）
            ann_args: 装饰器参数列表

        Returns:
            路由信息，不匹配时返回 None
        """
        # 检查是否匹配 Flask/FastAPI 装饰器
        matched_decorator = None
        for decorator_pattern, _method in self.PYTHON_DECORATOR_METHODS.items():
            if ann_name.startswith(decorator_pattern):
                matched_decorator = decorator_pattern
                break

        if not matched_decorator:
            return None

        http_method = self.PYTHON_DECORATOR_METHODS[matched_decorator]

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


class ExpressRouteStrategy(RouteExtractionStrategy):
    """
    Express/Koa 路由提取策略

    从 call 节点中提取 Express/Koa 路由注册调用。
    匹配模式: app.get('/path', handler) 或 router.post('/path', handler)。
    """

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

    async def extract(
        self,
        nodes: list[AstNodeModel],
        db: AsyncSession,
        repo_uuid: UUID,
    ) -> list[RouteInfo]:
        """
        从 call 节点提取 Express/Koa 路由

        Args:
            nodes: AST 节点列表（仅处理 call 类型）
            db: 数据库会话（本策略未使用，保留以满足接口契约）
            repo_uuid: 仓库 UUID（本策略未使用，保留以满足接口契约）

        Returns:
            Express/Koa 路由信息列表
        """
        routes: list[RouteInfo] = []
        for node in nodes:
            if node.node_type != "call":
                continue
            route = self._build_route(node)
            if route:
                routes.append(route)
        return routes

    def _build_route(self, node: AstNodeModel) -> RouteInfo | None:
        """
        从 Express/Koa 调用模式构建路由信息

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
        for pattern, http_method in self.EXPRESS_METHOD_CALLS.items():
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


class FrontendRouteStrategy(RouteExtractionStrategy):
    """
    前端路由提取策略（Vue Router / React Router / Angular）

    采用文件级正则解析策略：从 files 表中识别路由配置文件，
    直接读取源文件内容，用正则提取 path/component。

    注意：AST 的 qualified_name 对于大型对象数组通常不完整，
    因此采用文件级解析作为主要策略。
    """

    async def extract(
        self,
        nodes: list[AstNodeModel],
        db: AsyncSession,
        repo_uuid: UUID,
    ) -> list[RouteInfo]:
        """
        提取前端路由（Vue Router / React Router / Angular）

        策略：
        1. 从 files 表中识别路由配置文件（路径含 router/route/routes 等关键词）
        2. 直接读取源文件内容，用正则提取 path/component
        3. 支持 Vue Router、React Router、Angular 三种框架

        Args:
            nodes: AST 节点列表（本策略未使用，保留以满足接口契约）
            db: 数据库会话（用于查询 files 和 repositories 表）
            repo_uuid: 仓库 UUID

        Returns:
            前端路由信息列表
        """
        routes: list[RouteInfo] = []

        # 从 files 表中查找路由配置文件
        route_files = await self._find_route_config_files(db, repo_uuid)

        if not route_files:
            return routes

        logger.info("前端路由提取: 找到 %d 个路由配置文件", len(route_files))

        for file_path, language in route_files:
            file_routes = self._parse_routes_from_file(file_path, language)
            if file_routes:
                logger.info("  从 %s 提取 %d 条路由", file_path, len(file_routes))
                for route in file_routes:
                    routes.append(route)

        # 去重（相同路径 + 相同文件）
        seen: set[tuple[str, str]] = set()
        unique_routes = []
        for route in routes:
            key = (route.path_pattern, route.handler_file)
            if key not in seen:
                seen.add(key)
                unique_routes.append(route)

        return unique_routes

    async def _find_route_config_files(self, db: AsyncSession, repo_uuid: UUID) -> list[tuple[str, str]]:
        """
        从 files 表中查找前端路由配置文件

        识别规则：
        - 路径包含 router/route/routes 关键词
        - 语言为 javascript 或 typescript
        - 文件名包含 route 或 router

        Args:
            db: 数据库会话
            repo_uuid: 仓库 UUID

        Returns:
            (文件绝对路径, 语言) 列表
        """
        result = await db.execute(
            select(FileModel).where(
                FileModel.repository_id == repo_uuid,
                FileModel.language.in_(("javascript", "typescript")),
            )
        )
        files = list(result.scalars().all())

        route_files: list[tuple[str, str]] = []
        for f in files:
            path_lower = f.path.lower().replace("\\", "/")
            name_lower = FsPath(f.path).name.lower()

            # 常见路由配置文件模式
            is_route_file = (
                "/router/" in path_lower
                or "/routes/" in path_lower
                or name_lower in ("router.js", "router.ts", "routes.js", "routes.ts", "index.js", "index.ts")
                and ("router" in path_lower or "route" in path_lower)
                or name_lower.startswith("route")
            )

            if is_route_file:
                # 获取仓库路径以构建绝对路径
                repo_result = await db.execute(select(RepositoryModel).where(RepositoryModel.id == repo_uuid))
                repo = repo_result.scalar_one_or_none()
                if repo:
                    abs_path = str(FsPath(repo.path) / f.path)
                    route_files.append((abs_path, f.language))

        return route_files

    def _parse_routes_from_file(self, file_path: str, language: str) -> list[RouteInfo]:
        """
        从路由配置文件中提取路由信息

        使用正则表达式从文件内容中提取 path 和 component。
        支持 Vue Router 和 React Router 的配置格式。

        Args:
            file_path: 文件绝对路径
            language: 文件语言

        Returns:
            路由信息列表
        """
        routes: list[RouteInfo] = []

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return routes

        # 判断框架类型
        framework = self._detect_frontend_framework(content, file_path)

        # 提取路由配置中的 path 和 component
        # 匹配模式: path: '/xxx', 后面跟着 component 或 redirect
        route_entries = self._extract_route_entries(content)

        rel_path = (
            file_path.replace("\\", "/").split("/src/")[-1] if "/src/" in file_path.replace("\\", "/") else file_path
        )

        for path, component, redirect in route_entries:
            # 跳过仅含通配符的路径（如 *）
            if path == "*" or path == "/:pathMatch(.*)*":
                continue

            handler = component or redirect or "unknown"
            routes.append(
                RouteInfo(
                    http_method="GET",
                    path_pattern=self._normalize_path(path),
                    handler_function=handler,
                    handler_file=rel_path,
                    framework=framework,
                )
            )

        return routes

    def _detect_frontend_framework(self, content: str, file_path: str) -> str:
        """
        检测前端路由框架类型

        Args:
            content: 文件内容
            file_path: 文件路径

        Returns:
            框架名称（vue_router / react_router / angular / frontend）
        """
        if "vue-router" in content or "createRouter" in content or "VueRouter" in content:
            return "vue_router"
        if "react-router" in content or "createBrowserRouter" in content or "Routes" in content and "Route" in content:
            return "react_router"
        if "@angular/router" in content or "RouterModule" in content:
            return "angular"
        return "frontend"

    def _extract_route_entries(self, content: str) -> list[tuple[str, str, str]]:
        """
        从路由配置内容中提取路由条目

        提取 path、component、redirect 三个字段。
        支持各种格式：单引号、双引号、反引号、箭头函数等。

        Args:
            content: 文件内容

        Returns:
            (path, component, redirect) 元组列表
        """
        entries: list[tuple[str, str, str]] = []

        # 匹配 path: 'xxx' 或 path: "xxx" 或 path: `xxx`
        path_pattern = re.compile(r"path\s*:\s*['\"`]([^'\"`]+)['\"`]")

        # 匹配 component: xxx 或 component: () => import('xxx')
        component_pattern = re.compile(
            r"component\s*:\s*(?:\(\)\s*=>\s*import\s*\(\s*['\"`]([^'\"`]+)['\"`]\s*\)|(\w+))"
        )

        # 匹配 redirect: 'xxx'
        redirect_pattern = re.compile(r"redirect\s*:\s*['\"`]([^'\"`]+)['\"`]")

        # 先找到所有 path 的位置，然后在 path 之后的合理范围内找 component 或 redirect
        path_matches = list(path_pattern.finditer(content))

        for i, path_match in enumerate(path_matches):
            path_value = path_match.group(1)

            # 确定搜索范围：当前 path 到下一个 path 之间
            start = path_match.end()
            end = path_matches[i + 1].start() if i + 1 < len(path_matches) else min(start + 500, len(content))

            search_region = content[start:end]

            # 查找 component
            comp_match = component_pattern.search(search_region)
            component = ""
            if comp_match:
                component = comp_match.group(1) or comp_match.group(2) or ""

            # 查找 redirect
            redirect_match = redirect_pattern.search(search_region)
            redirect = redirect_match.group(1) if redirect_match else ""

            if path_value:
                entries.append((path_value, component, redirect))

        return entries


class RouteExtractor:
    """
    API 路由提取器

    从 ast_nodes 表中查询带有路由注解/装饰器的节点，
    提取路由信息并写入 api_routes 表。

    采用策略模式 + 注册机制：维护 _strategies 策略注册表，
    build_data 遍历所有已注册策略收集路由。新增框架支持只需
    实现 RouteExtractionStrategy 接口并调用 register() 注册。

    支持框架（内置策略）：
    - Spring Boot: @GetMapping, @PostMapping 等注解
    - Flask: @app.route("/path") 装饰器
    - FastAPI: @app.get("/path") 装饰器
    - Express: app.get("/path", handler) 调用模式
    - Koa: router.get("/path", handler) 调用模式
    - Vue Router: createRouter({ routes: [...] }) 配置
    - React Router: createBrowserRouter([...]) 配置
    - Angular: Routes 数组配置
    """

    def __init__(self, route_dao: ApiRouteDAO | None = None) -> None:
        self.route_dao = route_dao or ApiRouteDAO()
        # 策略注册表
        self._strategies: list[RouteExtractionStrategy] = []
        # 注册内置策略
        self._register_default_strategies()

    def _register_default_strategies(self) -> None:
        """注册内置路由提取策略"""
        self.register(SpringRouteStrategy())
        self.register(PythonRouteStrategy())
        self.register(ExpressRouteStrategy())
        self.register(FrontendRouteStrategy())

    def register(self, strategy: RouteExtractionStrategy) -> None:
        """
        注册自定义路由提取策略

        注册后该策略将参与 build_data 的路由提取流程。
        新增框架支持只需实现 RouteExtractionStrategy 接口并调用此方法注册。

        Args:
            strategy: 路由提取策略实例
        """
        self._strategies.append(strategy)

    async def build_data(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        构建路由数据（不写入数据库）

        从 ast_nodes 表查询所有 function/method/call 节点，
        遍历所有已注册策略提取路由信息。

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话

        Returns:
            路由数据列表，每项为可直接写入 api_routes 表的字典
        """
        # 查询所有 function/method/call 节点（一次性查询，供各策略按需筛选）
        result = await db.execute(
            select(AstNodeModel).where(
                AstNodeModel.repository_id == repo_uuid,
                AstNodeModel.node_type.in_(("function", "method", "call")),
            )
        )
        all_nodes = list(result.scalars().all())

        # 遍历所有已注册策略收集路由
        routes: list[RouteInfo] = []
        frontend_count = 0
        for strategy in self._strategies:
            strategy_routes = await strategy.extract(all_nodes, db, repo_uuid)
            if strategy_routes:
                # 前端策略产物计入 frontend 统计
                if isinstance(strategy, FrontendRouteStrategy):
                    frontend_count += len(strategy_routes)
                routes.extend(strategy_routes)

        logger.info(
            "路由提取完成: repo=%s, total_routes=%d (backend=%d, frontend=%d)",
            repo_uuid,
            len(routes),
            len(routes) - frontend_count,
            frontend_count,
        )

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

    # ===== 向后兼容的委托方法 =====
    # 以下方法保留以维持既有测试接口与外部调用兼容，
    # 实际逻辑已迁移至对应策略类，这里通过查找已注册策略进行委托。

    def _find_strategy(self, strategy_type: type) -> RouteExtractionStrategy | None:
        """
        从注册表中查找指定类型的策略实例

        Args:
            strategy_type: 策略类

        Returns:
            策略实例，未注册时返回 None
        """
        for strategy in self._strategies:
            if isinstance(strategy, strategy_type):
                return strategy
        return None

    def _extract_spring_route(
        self,
        node: AstNodeModel,
        ann_name: str,
        ann_args: list[Any],
    ) -> RouteInfo | None:
        """
        从 Spring 注解提取路由（向后兼容委托）

        委托至 SpringRouteStrategy._build_route。

        Args:
            node: AST 节点
            ann_name: 注解名（如 @GetMapping）
            ann_args: 注解参数列表

        Returns:
            路由信息，不匹配时返回 None
        """
        strategy = self._find_strategy(SpringRouteStrategy)
        if strategy is None:
            return None
        return strategy._build_route(node, ann_name, ann_args)

    def _extract_python_route(
        self,
        node: AstNodeModel,
        ann_name: str,
        ann_args: list[Any],
    ) -> RouteInfo | None:
        """
        从 Python 装饰器提取路由（向后兼容委托）

        委托至 PythonRouteStrategy._build_route。

        Args:
            node: AST 节点
            ann_name: 装饰器名（如 @app.get）
            ann_args: 装饰器参数列表

        Returns:
            路由信息，不匹配时返回 None
        """
        strategy = self._find_strategy(PythonRouteStrategy)
        if strategy is None:
            return None
        return strategy._build_route(node, ann_name, ann_args)

    def _extract_express_route(self, node: AstNodeModel) -> RouteInfo | None:
        """
        从 Express/Koa 调用模式提取路由（向后兼容委托）

        委托至 ExpressRouteStrategy._build_route。

        Args:
            node: call 类型的 AST 节点

        Returns:
            路由信息，不匹配时返回 None
        """
        strategy = self._find_strategy(ExpressRouteStrategy)
        if strategy is None:
            return None
        return strategy._build_route(node)

    def _extract_path_from_args(self, args: list[Any]) -> str:
        """
        从注解/装饰器参数中提取路径（向后兼容委托）

        委托至任意已注册策略的共享工具方法。
        """
        if not self._strategies:
            return ""
        return self._strategies[0]._extract_path_from_args(args)

    def _infer_method_from_args(self, args: list[Any]) -> str:
        """
        从注解参数推断 HTTP 方法（向后兼容委托）

        委托至任意已注册策略的共享工具方法。
        """
        if not self._strategies:
            return "GET"
        return self._strategies[0]._infer_method_from_args(args)

    def _normalize_path(self, path: str) -> str:
        """
        标准化路径模式（向后兼容委托）

        委托至任意已注册策略的共享工具方法。
        """
        if not self._strategies:
            return path
        return self._strategies[0]._normalize_path(path)
