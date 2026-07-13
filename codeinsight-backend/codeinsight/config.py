"""
配置管理

使用 Pydantic BaseSettings 从环境变量加载配置。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # 应用
    app_name: str = "CodeInsight AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True

    # 数据库
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "codeinsight"
    postgres_user: str = "codeinsight"
    postgres_password: str = ""  # ⚠️ 必须通过 .env 配置，生产环境禁止使用默认值
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_pool_max_connections: int = 50
    redis_pool_socket_timeout: int = 2

    # Meilisearch
    meilisearch_host: str = "http://localhost:7700"
    meilisearch_master_key: str = ""

    @property
    def database_url(self) -> str:
        """构建数据库连接字符串"""
        from urllib.parse import quote

        password = quote(self.postgres_password, safe="")
        user = quote(self.postgres_user, safe="")
        return f"postgresql+asyncpg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        """构建 Redis 连接字符串"""
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # LLM
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"
    llm_temperature: float = 0.3
    llm_timeout: int = 120

    # 本地模型
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # JWT
    secret_key: str = ""  # ⚠️ 必须通过 .env 配置 32+ 字符随机值
    access_token_expire_minutes: int = 60

    # 认证
    api_key: str = ""  # ⚠️ 必须通过 .env 配置；留空时跳过认证（仅开发环境）

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_allowed_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    cors_allowed_headers: list[str] = ["Authorization", "Content-Type", "X-API-Key"]

    # 文件上传
    max_repository_path_length: int = 500

    # 增量分析
    incremental_max_change_ratio: float = 0.3
    incremental_max_propagation_depth: int = 3
    incremental_max_snapshot_versions: int = 5

    # Celery（开发环境同步执行方便调试）
    celery_task_always_eager: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
