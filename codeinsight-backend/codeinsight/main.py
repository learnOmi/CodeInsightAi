"""
CodeInsight AI 后端服务入口

FastAPI 应用初始化，注册路由中间件和生命周期事件。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from codeinsight.api import analysis, ast_nodes, call_edges, files, knowledge, repositories, search, versions
from codeinsight.config import settings
from codeinsight.exceptions import RepositoryNotFoundError, RepositoryPathExistsError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("[STARTUP] CodeInsight AI Backend v%s", settings.app_version)
    logger.info("[STARTUP] Environment: %s", settings.app_env)

    # 生产环境配置验证（API-2/C-1, S-2 修复）
    try:
        settings.validate_production_config()
        if settings.app_env == "production":
            logger.info("[STARTUP] Production config validation passed")
    except ValueError as exc:
        logger.error("[STARTUP] Config validation FAILED: %s", exc)
        raise

    yield
    # 关闭时执行
    logger.info("[SHUTDOWN] CodeInsight AI Backend shutting down")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="CodeInsight AI API",
        description="AI 驱动的代码知识提取与可视化分析平台",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        max_body_size=settings.max_request_size,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=settings.cors_allowed_methods,
        allow_headers=settings.cors_allowed_headers,
    )

    # 注册全局异常处理器（Q-2 修复：添加通用 Exception 处理器）
    @app.exception_handler(RepositoryPathExistsError)
    async def repository_path_exists_handler(request: Request, exc: RepositoryPathExistsError):
        return JSONResponse(
            status_code=409,
            content={"detail": f"Repository path already exists: {exc.path}"},
        )

    @app.exception_handler(RepositoryNotFoundError)
    async def repository_not_found_handler(request: Request, exc: RepositoryNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": f"Repository not found: {exc.repository_id}"},
        )

    @app.exception_handler(NotImplementedError)
    async def not_implemented_handler(request: Request, exc: NotImplementedError):
        return JSONResponse(
            status_code=501,
            content={"detail": "功能尚未实现: " + str(exc) if str(exc) else "功能尚未实现"},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """全局异常处理器（Q-2 修复）

        捕获所有未处理的异常，返回统一格式的 500 响应，不暴露堆栈信息。
        """
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # 注册路由
    app.include_router(repositories.router, prefix="/api/v1/repositories", tags=["仓库管理"])
    app.include_router(analysis.router, prefix="/api/v1", tags=["分析任务"])
    app.include_router(knowledge.router, prefix="/api/v1", tags=["知识点"])
    app.include_router(search.router, prefix="/api/v1", tags=["搜索"])
    app.include_router(versions.router, prefix="/api/v1", tags=["版本管理"])
    app.include_router(files.router, prefix="/api/v1/files", tags=["文件管理"])
    app.include_router(ast_nodes.router, prefix="/api/v1/ast-nodes", tags=["AST 节点"])
    app.include_router(call_edges.router, prefix="/api/v1", tags=["调用图"])

    # 健康检查端点（S-1 修复：不返回敏感错误信息，防止信息泄露）
    # 注意：健康检查端点不加认证，因为需要被负载均衡器等基础设施访问
    @app.get("/api/v1/health", tags=["健康检查"])
    async def health_check():
        """
        健康检查端点

        S-1 修复：不返回详细错误信息，避免泄露数据库连接信息等敏感数据。
        Q-1 修复：错误状态仅返回 "unavailable"，详细信息记录到日志。
        """
        checks = {
            "service": {"status": "ok", "version": settings.app_version},
            "database": {"status": "unknown"},
            "redis": {"status": "unknown"},
        }

        # 检测数据库连接
        try:
            from codeinsight.db.session import get_db_session

            async for db in get_db_session():
                await db.execute("SELECT 1")
                checks["database"] = {"status": "ok"}
                break
        except Exception as exc:
            logger.error("Health check: database unavailable - %s", exc)
            checks["database"] = {"status": "unavailable"}

        # 检测 Redis 连接
        try:
            from codeinsight.db.redis_client import get_redis_client

            redis_client = get_redis_client()
            redis_client.ping()
            checks["redis"] = {"status": "ok"}
        except Exception as exc:
            logger.error("Health check: redis unavailable - %s", exc)
            checks["redis"] = {"status": "unavailable"}

        # 综合状态
        all_ok = all(check["status"] == "ok" for check in checks.values())
        return {"status": "ok" if all_ok else "degraded", "checks": checks}

    return app


app = create_app()
