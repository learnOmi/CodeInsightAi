"""
Phase 4: 后端框架支持测试

测试内容：
1. RouteExtractor - Spring/Flask/FastAPI/Express 路由提取
2. MiddlewareAnalyzer - 中间件链分析
3. ApiRoute/FrameworkPattern Schema 序列化
4. 路径标准化
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from codeinsight.analyzers.middleware_analyzer import (
    MiddlewareAnalyzer,
    MiddlewareInfo,
)
from codeinsight.analyzers.route_extractor import (
    EXPRESS_PATH_PARAM,
    FLASK_PATH_PARAM,
    RouteExtractor,
    RouteInfo,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def route_extractor():
    """RouteExtractor 实例"""
    return RouteExtractor()


@pytest.fixture
def middleware_analyzer():
    """MiddlewareAnalyzer 实例"""
    return MiddlewareAnalyzer()


# ============================================================
# RouteExtractor 测试
# ============================================================


class TestRouteExtractor:
    """RouteExtractor 路由提取器测试"""

    def test_route_info_to_dict(self):
        """测试 RouteInfo 转字典"""
        node_id = uuid4()
        route = RouteInfo(
            http_method="GET",
            path_pattern="/api/users",
            handler_function="getUsers",
            handler_file="src/controllers/UserController.java",
            framework="spring_boot",
            ast_node_id=node_id,
            middlewares=[{"name": "authMiddleware", "order": 1}],
        )

        d = route.to_dict()
        assert d["http_method"] == "GET"
        assert d["path_pattern"] == "/api/users"
        assert d["handler_function"] == "getUsers"
        assert d["framework"] == "spring_boot"
        assert d["ast_node_id"] == node_id
        assert len(d["middlewares"]) == 1

    def test_extract_path_from_string_arg(self, route_extractor):
        """测试从字符串参数提取路径"""
        path = route_extractor._extract_path_from_args(["/api/users"])
        assert path == "/api/users"

    def test_extract_path_from_value_dict(self, route_extractor):
        """测试从 value 字典提取路径"""
        path = route_extractor._extract_path_from_args([{"value": "/api/users"}])
        assert path == "/api/users"

    def test_extract_path_from_path_dict(self, route_extractor):
        """测试从 path 字典提取路径"""
        path = route_extractor._extract_path_from_args([{"path": "/api/items"}])
        assert path == "/api/items"

    def test_extract_path_no_match(self, route_extractor):
        """测试无法匹配路径时返回空字符串"""
        path = route_extractor._extract_path_from_args(["not-a-path", {"name": "test"}])
        assert path == ""

    def test_infer_method_from_request_mapping(self, route_extractor):
        """测试从 @RequestMapping 参数推断 HTTP 方法"""
        method = route_extractor._infer_method_from_args([{"method": "RequestMethod.POST"}])
        assert method == "POST"

    def test_infer_method_from_flask_methods(self, route_extractor):
        """测试从 Flask methods 参数推断 HTTP 方法"""
        method = route_extractor._infer_method_from_args([{"methods": ["POST"]}])
        assert method == "POST"

    def test_infer_method_default_get(self, route_extractor):
        """测试无方法参数时默认返回 GET"""
        method = route_extractor._infer_method_from_args([])
        assert method == "GET"

    def test_normalize_path_express_param(self, route_extractor):
        """测试 Express 路径参数标准化 :id → {id}"""
        path = route_extractor._normalize_path("/api/users/:id")
        assert path == "/api/users/{id}"

    def test_normalize_path_flask_typed_param(self, route_extractor):
        """测试 Flask 类型化路径参数标准化 <int:id> → {id}"""
        path = route_extractor._normalize_path("/api/users/<int:id>")
        assert path == "/api/users/{id}"

    def test_normalize_path_flask_plain_param(self, route_extractor):
        """测试 Flask 普通路径参数标准化 <id> → {id}"""
        path = route_extractor._normalize_path("/api/users/<id>")
        assert path == "/api/users/{id}"

    def test_normalize_path_multiple_params(self, route_extractor):
        """测试多参数路径标准化"""
        path = route_extractor._normalize_path("/api/users/:userId/posts/:postId")
        assert path == "/api/users/{userId}/posts/{postId}"

    def test_normalize_path_empty(self, route_extractor):
        """测试空路径标准化"""
        assert route_extractor._normalize_path("") == ""

    def test_normalize_path_no_params(self, route_extractor):
        """测试无参数路径不变化"""
        path = route_extractor._normalize_path("/api/users/list")
        assert path == "/api/users/list"

    def test_express_path_param_regex(self):
        """测试 Express 路径参数正则"""
        match = EXPRESS_PATH_PARAM.search("/api/users/:id")
        assert match is not None
        assert match.group(1) == "id"

    def test_flask_path_param_regex_typed(self):
        """测试 Flask 类型化路径参数正则"""
        match = FLASK_PATH_PARAM.search("/api/users/<int:userId>")
        assert match is not None
        assert match.group(1) == "userId"

    def test_flask_path_param_regex_plain(self):
        """测试 Flask 普通路径参数正则"""
        match = FLASK_PATH_PARAM.search("/api/users/<userId>")
        assert match is not None
        assert match.group(1) == "userId"


# ============================================================
# MiddlewareAnalyzer 测试
# ============================================================


class TestMiddlewareAnalyzer:
    """MiddlewareAnalyzer 中间件链分析器测试"""

    def test_middleware_info_to_dict(self):
        """测试 MiddlewareInfo 转字典"""
        mw = MiddlewareInfo(
            name="authMiddleware",
            order=1,
            file="src/middleware/auth.ts",
            middleware_type="authentication",
        )

        d = mw.to_dict()
        assert d["name"] == "authMiddleware"
        assert d["order"] == 1
        assert d["file"] == "src/middleware/auth.ts"
        assert d["type"] == "authentication"

    def test_infer_middleware_type_auth(self, middleware_analyzer):
        """测试推断认证中间件类型"""
        assert middleware_analyzer._infer_middleware_type("authMiddleware") == "authentication"
        assert middleware_analyzer._infer_middleware_type("verifyToken") == "authentication"
        assert middleware_analyzer._infer_middleware_type("checkJwt") == "authentication"

    def test_infer_middleware_type_rate_limiting(self, middleware_analyzer):
        """测试推断限流中间件类型"""
        assert middleware_analyzer._infer_middleware_type("rateLimiter") == "rate_limiting"
        assert middleware_analyzer._infer_middleware_type("apiThrottle") == "rate_limiting"

    def test_infer_middleware_type_logging(self, middleware_analyzer):
        """测试推断日志中间件类型"""
        assert middleware_analyzer._infer_middleware_type("requestLogger") == "logging"

    def test_infer_middleware_type_cors(self, middleware_analyzer):
        """测试推断 CORS 中间件类型"""
        assert middleware_analyzer._infer_middleware_type("corsHandler") == "cors"

    def test_infer_middleware_type_security(self, middleware_analyzer):
        """测试推断安全中间件类型"""
        assert middleware_analyzer._infer_middleware_type("helmetMiddleware") == "security"
        assert middleware_analyzer._infer_middleware_type("csrfProtection") == "security"

    def test_infer_middleware_type_generic(self, middleware_analyzer):
        """测试无法匹配时返回 generic"""
        assert middleware_analyzer._infer_middleware_type("customHandler") == "generic"

    def test_infer_middleware_type_body_parser(self, middleware_analyzer):
        """测试推断 body parser 类型"""
        assert middleware_analyzer._infer_middleware_type("bodyParser") == "body_parser"
        assert middleware_analyzer._infer_middleware_type("jsonParser") == "body_parser"

    def test_infer_middleware_type_compression(self, middleware_analyzer):
        """测试推断压缩中间件类型"""
        assert middleware_analyzer._infer_middleware_type("gzipCompress") == "compression"

    def test_infer_middleware_type_cookie(self, middleware_analyzer):
        """测试推断 cookie 中间件类型"""
        assert middleware_analyzer._infer_middleware_type("cookieParser") == "cookie"


# ============================================================
# Schema 序列化测试
# ============================================================


class TestPhase4Schemas:
    """Phase 4 Schema 序列化测试"""

    def test_api_route_create_schema(self):
        """测试 ApiRouteCreate schema 创建"""
        from codeinsight.schemas import ApiRouteCreate

        repo_id = uuid4()
        route = ApiRouteCreate(
            repository_id=repo_id,
            http_method="GET",
            path_pattern="/api/users/{id}",
            handler_function="getUserById",
            handler_file="src/controllers/UserController.java",
            framework="spring_boot",
        )

        assert route.http_method == "GET"
        assert route.path_pattern == "/api/users/{id}"
        assert route.framework == "spring_boot"

    def test_framework_pattern_create_schema(self):
        """测试 FrameworkPatternCreate schema 创建"""
        from codeinsight.schemas import FrameworkPatternCreate

        repo_id = uuid4()
        pattern = FrameworkPatternCreate(
            repository_id=repo_id,
            framework="spring_boot",
            category="backend",
            confidence=0.8,
            evidence={"file_level": {"pom.xml": "spring-boot-starter"}},
        )

        assert pattern.framework == "spring_boot"
        assert pattern.category == "backend"
        assert pattern.confidence == 0.8
        assert "file_level" in pattern.evidence

    def test_api_route_schema_serialization(self):
        """测试 ApiRoute schema 序列化（UUID → string）"""
        from codeinsight.schemas import ApiRoute

        repo_id = uuid4()
        route_id = uuid4()

        # 模拟从 ORM model 转换
        class MockRouteModel:
            def __init__(self):
                self.id = route_id
                self.repository_id = repo_id
                self.analysis_version_id = None
                self.ast_node_id = None
                self.http_method = "POST"
                self.path_pattern = "/api/items"
                self.handler_function = "createItem"
                self.handler_file = "src/routes/items.ts"
                self.middlewares = []
                self.framework = "express"
                self.created_at = "2026-07-17T00:00:00+00:00"

        mock = MockRouteModel()
        route = ApiRoute.model_validate(mock, from_attributes=True)
        assert route.http_method == "POST"
        assert route.framework == "express"

    def test_framework_pattern_schema_serialization(self):
        """测试 FrameworkPattern schema 序列化"""
        from codeinsight.schemas import FrameworkPattern

        repo_id = uuid4()
        pattern_id = uuid4()

        class MockPatternModel:
            def __init__(self):
                self.id = pattern_id
                self.repository_id = repo_id
                self.analysis_version_id = None
                self.framework = "flask"
                self.category = "backend"
                self.confidence = 0.5
                self.evidence = {"file_level": {"requirements.txt": "flask"}}
                self.detected_at = "2026-07-17T00:00:00+00:00"

        mock = MockPatternModel()
        pattern = FrameworkPattern.model_validate(mock, from_attributes=True)
        assert pattern.framework == "flask"
        assert pattern.confidence == 0.5


# ============================================================
# 集成测试：Spring 注解 → 路由提取
# ============================================================


class TestSpringRouteExtraction:
    """Spring 路由提取集成测试"""

    def test_spring_get_mapping_extraction(self, route_extractor):
        """测试 Spring @GetMapping 路由提取"""

        # 模拟 AstNodeModel
        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "getUserById"
                self.file_path = "src/controller/UserController.java"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_spring_route(node, "@GetMapping", ["/api/users/{id}"])

        assert route is not None
        assert route.http_method == "GET"
        assert route.path_pattern == "/api/users/{id}"
        assert route.handler_function == "getUserById"
        assert route.framework == "spring_boot"

    def test_spring_post_mapping_extraction(self, route_extractor):
        """测试 Spring @PostMapping 路由提取"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "createUser"
                self.file_path = "src/controller/UserController.java"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_spring_route(node, "@PostMapping", ["/api/users"])

        assert route is not None
        assert route.http_method == "POST"
        assert route.path_pattern == "/api/users"

    def test_spring_delete_mapping_extraction(self, route_extractor):
        """测试 Spring @DeleteMapping 路由提取"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "deleteUser"
                self.file_path = "src/controller/UserController.java"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_spring_route(node, "@DeleteMapping", ["/api/users/{id}"])

        assert route is not None
        assert route.http_method == "DELETE"

    def test_spring_non_route_annotation(self, route_extractor):
        """测试非路由注解返回 None"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "someService"
                self.file_path = "src/service/SomeService.java"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_spring_route(node, "@Service", [])

        assert route is None

    def test_spring_request_mapping_with_method(self, route_extractor):
        """测试 @RequestMapping 从 method 参数推断 HTTP 方法"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "handleRequest"
                self.file_path = "src/controller/SomeController.java"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_spring_route(
            node, "@RequestMapping", ["/api/endpoint", {"method": "RequestMethod.PUT"}]
        )

        assert route is not None
        assert route.http_method == "PUT"
        assert route.path_pattern == "/api/endpoint"


# ============================================================
# 集成测试：Python 路由提取
# ============================================================


class TestPythonRouteExtraction:
    """Flask/FastAPI 路由提取集成测试"""

    def test_fastapi_get_route_extraction(self, route_extractor):
        """测试 FastAPI @app.get 路由提取"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "get_users"
                self.file_path = "src/api/users.py"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_python_route(node, "@app.get", ["/api/users"])

        assert route is not None
        assert route.http_method == "GET"
        assert route.path_pattern == "/api/users"
        assert route.framework == "fastapi"

    def test_fastapi_router_post_extraction(self, route_extractor):
        """测试 FastAPI @router.post 路由提取"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "create_item"
                self.file_path = "src/api/items.py"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_python_route(node, "@router.post", ["/api/items"])

        assert route is not None
        assert route.http_method == "POST"
        assert route.framework == "fastapi"

    def test_flask_route_extraction(self, route_extractor):
        """测试 Flask @app.route 路由提取"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "index"
                self.file_path = "src/app.py"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_python_route(node, "@app.route", ["/", {"methods": ["GET"]}])

        assert route is not None
        assert route.http_method == "GET"
        assert route.path_pattern == "/"
        assert route.framework == "flask"

    def test_flask_route_with_typed_param(self, route_extractor):
        """测试 Flask 路由带类型参数"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "get_user"
                self.file_path = "src/app.py"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_python_route(node, "@app.route", ["/users/<int:user_id>"])

        assert route is not None
        assert route.path_pattern == "/users/{user_id}"

    def test_non_python_route_decorator(self, route_extractor):
        """测试非路由装饰器返回 None"""

        class MockNode:
            def __init__(self):
                self.id = uuid4()
                self.name = "cached_func"
                self.file_path = "src/utils.py"
                self.qualified_name = ""

        node = MockNode()
        route = route_extractor._extract_python_route(node, "@lru_cache", ["128"])

        assert route is None
