"""
配置管理

使用 Pydantic BaseSettings 从环境变量加载配置。
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # 应用
    app_name: str = "CodeInsight AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True

    # 数据库
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/codeinsight"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Meilisearch
    meilisearch_host: str = "http://localhost:7700"
    meilisearch_master_key: str = ""

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
    secret_key: str = "change-me-to-a-random-secret-key"
    access_token_expire_minutes: int = 60

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # 文件上传
    max_repository_path_length: int = 500

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
