"""
CodeInsight AI 后端服务入口

FastAPI 应用初始化，注册路由中间件和生命周期事件。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from codeinsight.api import analysis, files, knowledge, repositories, search, versions
from codeinsight.config import settings
from codeinsight.exceptions import RepositoryNotFoundError, RepositoryPathExistsError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"[STARTUP] CodeInsight AI Backend v{settings.app_version}")
    print(f"[STARTUP] Environment: {settings.app_env}")
    yield
    # 关闭时执行
    print("[SHUTDOWN] CodeInsight AI Backend shutting down")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="CodeInsight AI API",
        description="AI 驱动的代码知识提取与可视化分析平台",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=settings.cors_allowed_methods,
        allow_headers=settings.cors_allowed_headers,
    )

    # 注册全局异常处理器
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

    # 注册路由
    app.include_router(repositories.router, prefix="/api/v1/repositories", tags=["仓库管理"])
    app.include_router(analysis.router, prefix="/api/v1", tags=["分析任务"])
    app.include_router(knowledge.router, prefix="/api/v1", tags=["知识点"])
    app.include_router(search.router, prefix="/api/v1", tags=["搜索"])
    app.include_router(versions.router, prefix="/api/v1", tags=["版本管理"])
    app.include_router(files.router, prefix="/api/v1/files", tags=["文件管理"])

    @app.get("/api/v1/health", tags=["健康检查"])
    async def health_check():
        """健康检查端点"""
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
