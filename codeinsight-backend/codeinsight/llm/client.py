"""
LLM 客户端

统一的 LLM 调用封装，支持 Claude、GPT 和 Ollama 等多种提供商。
使用 litellm 进行路由，通过 Pydantic BaseSettings 从环境变量加载配置。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import litellm
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from codeinsight.llm.errors import LLMError

logger = logging.getLogger(__name__)


class LLMConfig(BaseSettings):
    """LLM 客户端配置"""

    provider: Literal["claude", "gpt", "ollama"] = "claude"
    model: str = ""
    api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 4096
    embedding_model: str = "text-embedding-3-small"
    # Retry and timeout configuration
    num_retries: int = 3
    request_timeout: float = 120.0
    embedding_timeout: float = 60.0

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


class LLMClient:
    """
    统一的 LLM 客户端

    支持 Claude、GPT 和 Ollama 等多种大模型提供商，
    提供统一的对话和嵌入接口。
    """

    def __init__(self, config: LLMConfig | None = None):
        """
        初始化 LLM 客户端

        Args:
            config: LLM 配置对象，如果为 None 则从环境变量加载默认配置
        """
        self.config = config or LLMConfig()
        self._model_name: str = self._resolve_model_name()

    def _resolve_model_name(self) -> str:
        """
        根据提供商和配置解析模型名称

        返回 litellm 兼容的模型标识符。

        Returns:
            模型名称字符串
        """
        provider = self.config.provider.lower()
        if provider == "claude":
            return "claude-3.5-sonnet-20241022"
        elif provider == "gpt":
            return "gpt-4o"
        elif provider == "ollama":
            return f"ollama/{self.config.model}"
        else:
            raise LLMError(
                f"Unsupported LLM provider: {provider}",
                provider=provider,
            )

    def _get_api_kwargs(self, *, timeout: float | None = None) -> dict[str, Any]:
        """
        构建 litellm 调用所需的 API 参数

        Args:
            timeout: 请求超时时间（秒），默认为配置中的 request_timeout

        Returns:
            API 关键字参数字典
        """
        if timeout is None:
            timeout = self.config.request_timeout

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "timeout": timeout,
            "num_retries": self.config.num_retries,
        }

        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key

        if self.config.provider.lower() == "ollama":
            kwargs["api_base"] = self.config.ollama_base_url

        return kwargs

    async def chat(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None = None,
    ) -> dict | BaseModel:
        """
        发送对话请求

        使用 litellm.acompletion 进行异步对话调用。

        Args:
            messages: 对话消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            response_model: 可选的 Pydantic 模型，用于解析响应结构

        Returns:
            如果提供 response_model，返回解析后的 BaseModel 实例；
            否则返回包含 choices 的字典

        Raises:
            LLMError: 当 LLM 调用失败时抛出
        """
        try:
            api_kwargs = self._get_api_kwargs()
            response = await litellm.acompletion(
                messages=messages,
                **api_kwargs,
            )
            content = response.choices[0].message.content

            if response_model:
                parsed = response_model.model_validate_json(content)
                logger.debug(
                    "LLM 响应已解析: provider=%s, model=%s",
                    self.config.provider,
                    self._model_name,
                )
                return parsed
            return {"content": content}

        except Exception as exc:
            error_msg = f"LLM chat failed: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMError(
                error_msg,
                provider=self.config.provider,
                model=self._model_name,
            ) from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成文本嵌入向量

        使用 litellm.aembedding 进行异步嵌入调用。

        Args:
            texts: 需要生成嵌入的文本列表

        Returns:
            嵌入向量列表，每个向量对应 texts 中的文本

        Raises:
            LLMError: 当嵌入调用失败时抛出
        """
        try:
            embedding_model = self.config.embedding_model
            if self.config.provider.lower() == "gpt":
                # OpenAI 嵌入模型使用完整标识符
                embedding_model = "text-embedding-3-small"
            elif self.config.provider.lower() == "ollama":
                embedding_model = f"ollama/{self.config.embedding_model}"

            kwargs: dict[str, Any] = {
                "model": embedding_model,
                "input": texts,
                "timeout": self.config.embedding_timeout,
                "num_retries": self.config.num_retries,
            }

            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key

            if self.config.provider.lower() == "ollama":
                kwargs["api_base"] = self.config.ollama_base_url

            response = await litellm.aembedding(**kwargs)

            embeddings: list[list[float]] = [data.get("embedding", []) for data in response.data]

            logger.debug(
                "嵌入生成完成: count=%d, model=%s",
                len(texts),
                embedding_model,
            )
            return embeddings

        except Exception as exc:
            error_msg = f"LLM embed failed: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMError(
                error_msg,
                provider=self.config.provider,
                model=self.config.embedding_model,
            ) from exc
