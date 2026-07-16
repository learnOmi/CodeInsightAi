"""
MiddlewareAnalyzer - 中间件链分析器

分析 Express/Koa 中间件链和 Spring 拦截器链，
构建请求处理管道的有序结构。

支持框架：
- Express: app.use(middleware) 全局中间件
- Koa: app.use(middleware) 全局中间件
- Spring: WebMvcConfigurer.addInterceptors() 拦截器注册
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import AstNodeModel

logger = logging.getLogger(__name__)

# Spring WebMvcConfigurer 方法名
SPRING_INTERCEPTOR_METHODS: set[str] = {
    "addInterceptors",
}


class MiddlewarePatternRegistry:
    """
    中间件模式注册表

    集中管理可注册的中间件识别与类型推断模式：
    1. 调用模式（call patterns）：识别中间件注册调用，如 "*.use"
    2. 类型模式（type patterns）：根据中间件名子串推断类型，如 "auth" → "authentication"

    新增中间件框架支持只需调用 register / register_call_pattern 注册新模式，
    无需修改 MiddlewareAnalyzer 内部分支逻辑。
    """

    # 默认中间件调用模式
    DEFAULT_CALL_PATTERNS: set[str] = {
        "*.use",
    }

    # 默认中间件类型推断映射
    DEFAULT_TYPE_PATTERNS: dict[str, str] = {
        "auth": "authentication",
        "login": "authentication",
        "token": "authentication",
        "jwt": "authentication",
        "session": "authentication",
        "rate": "rate_limiting",
        "limit": "rate_limiting",
        "throttle": "rate_limiting",
        "log": "logging",
        "logger": "logging",
        "cors": "cors",
        "csrf": "security",
        "security": "security",
        "helmet": "security",
        "compress": "compression",
        "gzip": "compression",
        "body": "body_parser",
        "json": "body_parser",
        "urlencoded": "body_parser",
        "static": "static_files",
        "cookie": "cookie",
    }

    def __init__(self) -> None:
        self._call_patterns: set[str] = set(self.DEFAULT_CALL_PATTERNS)
        self._type_patterns: dict[str, str] = dict(self.DEFAULT_TYPE_PATTERNS)

    def register(self, call_pattern: str, middleware_type: str) -> None:
        """
        注册中间件类型推断模式

        用于根据中间件名子串推断其类型。若 call_pattern 已存在则覆盖原映射。

        Args:
            call_pattern: 中间件名匹配模式（子串匹配，如 "auth"、"jwt"）
            middleware_type: 匹配时返回的中间件类型（如 "authentication"）
        """
        self._type_patterns[call_pattern] = middleware_type

    def register_call_pattern(self, pattern: str) -> None:
        """
        注册中间件调用识别模式

        用于识别形如 app.use(middleware) 的中间件注册调用。

        Args:
            pattern: 调用名模式（如 "*.use"）
        """
        self._call_patterns.add(pattern)

    def matches_call(self, call_name: str) -> bool:
        """
        检查调用名是否匹配已注册的中间件调用模式

        Args:
            call_name: call 节点的调用名

        Returns:
            是否为中间件注册调用
        """
        return call_name in self._call_patterns

    def infer_type(self, name: str) -> str:
        """
        根据中间件名推断类型

        遍历已注册的类型模式，返回首个匹配的类型；未匹配返回 "generic"。

        Args:
            name: 中间件函数名

        Returns:
            中间件类型
        """
        name_lower = name.lower()
        for pattern, middleware_type in self._type_patterns.items():
            if pattern in name_lower:
                return middleware_type
        return "generic"


class MiddlewareInfo:
    """
    中间件信息

    Attributes:
        name: 中间件函数名
        order: 执行顺序（按源码行号排序）
        file: 中间件所在文件
        middleware_type: 中间件类型 (authentication, rate_limiting, logging, cors, generic)
    """

    def __init__(
        self,
        name: str,
        order: int,
        file: str,
        middleware_type: str = "generic",
    ) -> None:
        self.name = name
        self.order = order
        self.file = file
        self.middleware_type = middleware_type

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "name": self.name,
            "order": self.order,
            "file": self.file,
            "type": self.middleware_type,
        }


class MiddlewareAnalyzer:
    """
    中间件链分析器

    从 ast_nodes 表查询中间件注册相关的调用节点，
    按源码行号排序构建中间件链。

    分析策略：
    1. Express/Koa: 查找 app.use(middleware) 调用，按行号排序
    2. Spring: 查找 addInterceptors 方法，提取拦截器注册
    3. 根据命名模式推断中间件类型

    通过 MiddlewarePatternRegistry 支持外部注册新的中间件模式，
    无需修改 analyze 内部分支逻辑。
    """

    def __init__(self) -> None:
        self._registry = MiddlewarePatternRegistry()

    def register(self, call_pattern: str, middleware_type: str) -> None:
        """
        注册中间件类型推断模式（委托给注册表）

        供外部注册新的中间件类型推断模式，无需修改分析器内部逻辑。

        Args:
            call_pattern: 中间件名匹配模式（子串匹配，如 "auth"）
            middleware_type: 匹配时返回的中间件类型（如 "authentication"）
        """
        self._registry.register(call_pattern, middleware_type)

    def register_call_pattern(self, pattern: str) -> None:
        """
        注册中间件调用识别模式（委托给注册表）

        供外部注册新的中间件调用识别模式（如新的框架 app.use 等价调用）。

        Args:
            pattern: 调用名模式（如 "*.use"）
        """
        self._registry.register_call_pattern(pattern)

    async def analyze(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        分析中间件链

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话

        Returns:
            中间件链列表，每项为 MiddlewareInfo 的字典表示
        """
        middlewares: list[MiddlewareInfo] = []

        # 查询所有 call 节点
        result = await db.execute(
            select(AstNodeModel).where(
                AstNodeModel.repository_id == repo_uuid,
                AstNodeModel.node_type == "call",
            )
        )
        call_nodes = list(result.scalars().all())

        # 分析 Express/Koa 中间件
        express_middlewares = self._analyze_express_middlewares(call_nodes)
        middlewares.extend(express_middlewares)

        # 分析 Spring 拦截器
        spring_middlewares = await self._analyze_spring_interceptors(repo_uuid, db)
        middlewares.extend(spring_middlewares)

        # 按执行顺序排序
        middlewares.sort(key=lambda m: m.order)

        logger.info("中间件链分析完成: repo=%s, middlewares=%d", repo_uuid, len(middlewares))

        return [m.to_dict() for m in middlewares]

    def _analyze_express_middlewares(self, call_nodes: list[AstNodeModel]) -> list[MiddlewareInfo]:
        """
        分析 Express/Koa 中间件链

        查找 app.use(middleware) 调用模式。
        call 节点 name 格式为 "*.use"。

        Args:
            call_nodes: call 类型的 AST 节点列表

        Returns:
            中间件信息列表
        """
        middlewares: list[MiddlewareInfo] = []

        for node in call_nodes:
            call_name = node.name.split("(")[0].strip()

            if self._registry.matches_call(call_name):
                # 提取中间件名：从 qualified_name 或 name 中提取
                middleware_name = self._extract_middleware_name(node)
                middleware_type = self._infer_middleware_type(middleware_name)

                middlewares.append(
                    MiddlewareInfo(
                        name=middleware_name,
                        order=node.start_line,
                        file=node.file_path,
                        middleware_type=middleware_type,
                    )
                )

        return middlewares

    async def _analyze_spring_interceptors(self, repo_uuid: UUID, db: AsyncSession) -> list[MiddlewareInfo]:
        """
        分析 Spring 拦截器链

        查找 addInterceptors 方法中的拦截器注册。

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话

        Returns:
            拦截器信息列表
        """
        middlewares: list[MiddlewareInfo] = []

        # 查找方法名为 addInterceptors 的节点
        result = await db.execute(
            select(AstNodeModel).where(
                AstNodeModel.repository_id == repo_uuid,
                AstNodeModel.node_type.in_(("method", "function")),
                AstNodeModel.name.in_(SPRING_INTERCEPTOR_METHODS),
            )
        )
        interceptor_methods = list(result.scalars().all())

        for method_node in interceptor_methods:
            # 检查是否有 @Configuration 注解（类级别）
            # 简化处理：直接将 addInterceptors 方法作为拦截器注册点
            middleware_type = self._infer_middleware_type(method_node.name)

            middlewares.append(
                MiddlewareInfo(
                    name=method_node.name,
                    order=method_node.start_line,
                    file=method_node.file_path,
                    middleware_type=middleware_type,
                )
            )

        return middlewares

    def _extract_middleware_name(self, node: AstNodeModel) -> str:
        """
        从 call 节点提取中间件名

        Express 中间件调用格式: app.use(middlewareFunction)
        call 节点的 name 格式为 "*.use"，中间件名需从上下文推断。

        Args:
            node: call 节点

        Returns:
            中间件函数名
        """
        # 如果 qualified_name 包含更多信息，尝试提取
        if node.qualified_name and node.qualified_name != "*.use":
            return node.qualified_name

        # 从 name 中提取（去掉 *.use 前缀）
        name = node.name.split("(")[0].strip()
        if name == "*.use":
            return f"middleware_at_line_{node.start_line}"

        return name

    def _infer_middleware_type(self, name: str) -> str:
        """
        根据中间件名推断类型

        委托给 MiddlewarePatternRegistry，从已注册的类型模式中查找匹配项。

        Args:
            name: 中间件函数名

        Returns:
            中间件类型
        """
        return self._registry.infer_type(name)
