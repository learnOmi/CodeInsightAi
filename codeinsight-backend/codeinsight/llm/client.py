"""
LLM 客户端

统一的 LLM 调用封装，支持 Claude、GPT 和 Ollama 等多种提供商。
使用 litellm 进行路由，配置从全局 Settings 加载。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

import litellm
from pydantic import BaseModel, Field

from codeinsight.config import settings
from codeinsight.llm.errors import LLMError

logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    """LLM 客户端配置——从全局 Settings 读取"""

    provider: Literal["claude", "gpt", "ollama", "openai"] = Field(
        default_factory=lambda: cast(
            "Literal['claude', 'gpt', 'ollama', 'openai']",
            settings.llm_provider if settings.llm_provider in ("claude", "gpt", "ollama", "openai") else "claude",
        )
    )
    model: str = Field(default_factory=lambda: settings.llm_model or "")
    api_key: str | None = Field(default_factory=lambda: settings.llm_api_key or None)
    api_base: str | None = Field(default_factory=lambda: settings.llm_api_base or None)
    ollama_base_url: str = Field(default_factory=lambda: settings.ollama_host)
    temperature: float = Field(default_factory=lambda: settings.llm_temperature)
    max_tokens: int = 4096
    embedding_model: str = "text-embedding-3-small"
    num_retries: int = 3
    request_timeout: float = Field(default_factory=lambda: float(settings.llm_timeout))
    embedding_timeout: float = 60.0

    model_config = {"arbitrary_types_allowed": True}


class LLMClient:
    """
    统一的 LLM 客户端

    支持 Claude、GPT 和 Ollama 等多种大模型提供商，
    提供统一的对话、嵌入、流式响应、Token 计数接口。
    """

    # 成本单价 (USD / 1M tokens)，用于 CostTracker
    MODEL_COST_MAP: dict[str, dict[str, float]] = {
        "claude-3.5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "gpt-4o": {"input": 2.5, "output": 10.0},
        "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    }

    # 简单任务 → 本地模型的降级映射
    SIMPLE_TASK_MODELS: dict[str, str] = {
        "classification": "ollama/llama3.1:8b",
        "summarization": "ollama/llama3.1:8b",
        "extraction": "ollama/mistral:7b",
    }

    def __init__(self, config: LLMConfig | None = None):
        """
        初始化 LLM 客户端

        Args:
            config: LLM 配置对象，如果为 None 则从全局 Settings 加载默认配置
        """
        self.config = config or LLMConfig()
        self._model_name: str = self._resolve_model_name()
        logger.info(
            "LLMClient 初始化: provider=%s, model=%s",
            self.config.provider,
            self._model_name,
        )

    # ────────── 内部方法 ──────────

    def _resolve_model_name(self) -> str:
        """
        根据提供商和配置解析模型名称

        Returns:
            litellm 兼容的模型标识符
        """
        provider = self.config.provider.lower()
        if provider == "claude":
            model = self.config.model or "claude-3.5-sonnet-20241022"
            return model
        elif provider in ("gpt", "openai"):
            return self.config.model or "gpt-4o"
        elif provider == "ollama":
            model = self.config.model or "llama3.1:8b"
            return f"ollama/{model}"
        else:
            raise LLMError(
                f"Unsupported LLM provider: {provider}",
                provider=provider,
            )

    def _get_model_key(self) -> str:
        """返回用于成本查询的 model key（去掉 ollama/ 前缀）"""
        name = self._model_name
        if name.startswith("ollama/"):
            name = name.split("/", 1)[1]
        return name

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

        if self.config.api_base:
            kwargs["api_base"] = self.config.api_base
        elif self.config.provider.lower() == "ollama":
            kwargs["api_base"] = self.config.ollama_base_url

        return kwargs

    def _estimate_tokens(self, text: str) -> int:
        """使用 litellm 估算 Token 数，回退到粗略估算"""
        try:
            return litellm.token_counter(model=self._model_name, text=text)
        except Exception:
            return len(text) // 4

    def _get_cost_per_token(self, model_key: str) -> tuple[float, float]:
        """获取每 token 的输入/输出成本"""
        costs = self.MODEL_COST_MAP.get(model_key, {"input": 0.0, "output": 0.0})
        return costs["input"] / 1_000_000, costs["output"] / 1_000_000

    # ────────── 核心接口 ──────────

    async def chat(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None = None,
    ) -> dict | BaseModel:
        """
        发送对话请求（非流式）

        Args:
            messages: 对话消息列表
            response_model: 可选的 Pydantic 模型，用于解析响应结构

        Returns:
            如果提供 response_model，返回解析后的 BaseModel 实例；
            否则返回包含 'content' 和 token 计数的字典

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

            usage = getattr(response, "usage", None)
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0

            if response_model:
                parsed = response_model.model_validate_json(content)
                logger.debug(
                    "LLM 响应已解析: provider=%s, model=%s, tokens=%d+%d",
                    self.config.provider,
                    self._model_name,
                    prompt_tokens,
                    completion_tokens,
                )
                return parsed

            result: dict[str, Any] = {
                "content": content,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "model": self._model_name,
            }

            input_cost, output_cost = self._get_cost_per_token(self._get_model_key())
            result["cost"] = (prompt_tokens * input_cost) + (completion_tokens * output_cost)

            return result

        except Exception as exc:
            error_msg = f"LLM chat failed: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMError(
                error_msg,
                provider=self.config.provider,
                model=self._model_name,
            ) from exc

    async def chat_stream(
        self,
        messages: list[dict],
    ) -> AsyncIterator[str]:
        """
        发送对话请求（流式）

        Args:
            messages: 对话消息列表

        Yields:
            流式响应的文本片段

        Raises:
            LLMError: 当 LLM 调用失败时抛出
        """
        try:
            api_kwargs = self._get_api_kwargs()
            api_kwargs["stream"] = True

            response = await litellm.acompletion(
                messages=messages,
                **api_kwargs,
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as exc:
            error_msg = f"LLM chat stream failed: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMError(
                error_msg,
                provider=self.config.provider,
                model=self._model_name,
            ) from exc

    async def chat_with_fallback(
        self,
        messages: list[dict],
        *,
        fallback_providers: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        带 Provider 降级的对话请求

        主 provider 失败后自动尝试备用 provider。

        Args:
            messages: 对话消息列表
            fallback_providers: 备用 provider 列表，默认 ["gpt", "ollama"]

        Returns:
            包含 'content'、'provider' 和 token 计数的字典
        """
        if fallback_providers is None:
            fallback_providers = ["gpt", "ollama"]

        errors: list[str] = []
        original_provider = self.config.provider

        for _attempt, provider in enumerate([original_provider] + fallback_providers):
            try:
                self.config.provider = provider  # type: ignore[assignment]
                self._model_name = self._resolve_model_name()
                result = await self.chat(messages)
                if isinstance(result, dict):
                    result["provider"] = provider
                return result  # type: ignore[return-value]
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                logger.warning("Provider %s 失败，尝试下一个: %s", provider, exc)

        # 恢复原始配置
        self.config.provider = original_provider  # type: ignore[assignment]
        self._model_name = self._resolve_model_name()

        raise LLMError(
            f"所有 Provider 均失败: {'; '.join(errors)}",
            provider=",".join([original_provider] + fallback_providers),
            model=self._model_name,
        )

    async def chat_for_task(
        self,
        messages: list[dict],
        task_type: str = "default",
    ) -> dict[str, Any]:
        """
        按任务类型智能路由

        简单任务（分类、摘要等）自动切到本地模型以节省成本。

        Args:
            messages: 对话消息列表
            task_type: 任务类型，支持 "classification", "summarization",
                       "extraction", "default"

        Returns:
            包含 'content' 和 token 计数的字典
        """
        if task_type in self.SIMPLE_TASK_MODELS:
            local_model = self.SIMPLE_TASK_MODELS[task_type]
            if self.config.provider.lower() != "ollama":
                try:
                    old_provider = self.config.provider
                    old_model = self.config.model
                    self.config.provider = "ollama"  # type: ignore[assignment]
                    self.config.model = local_model.replace("ollama/", "")
                    self._model_name = self._resolve_model_name()

                    logger.info("任务 '%s' 路由到本地模型: %s", task_type, self._model_name)
                    result = await self.chat(messages)

                    # 恢复
                    self.config.provider = old_provider  # type: ignore[assignment]
                    self.config.model = old_model
                    self._model_name = self._resolve_model_name()

                    if isinstance(result, dict):
                        result["provider"] = "ollama"
                    return result  # type: ignore[return-value]
                except Exception as exc:
                    logger.warning("本地模型 %s 失败，回退到云端: %s", local_model, exc)
                    self.config.provider = old_provider  # type: ignore[assignment]
                    self.config.model = old_model
                    self._model_name = self._resolve_model_name()

        return await self.chat(messages)  # type: ignore[return-value]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成文本嵌入向量

        Args:
            texts: 需要生成嵌入的文本列表

        Returns:
            嵌入向量列表

        Raises:
            LLMError: 当嵌入调用失败时抛出
        """
        try:
            embedding_model = self.config.embedding_model
            if self.config.provider.lower() == "ollama":
                embedding_model = f"ollama/{self.config.embedding_model}"

            kwargs: dict[str, Any] = {
                "model": embedding_model,
                "input": texts,
                "timeout": self.config.embedding_timeout,
                "num_retries": self.config.num_retries,
            }

            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key

            if self.config.api_base:
                kwargs["api_base"] = self.config.api_base
            elif self.config.provider.lower() == "ollama":
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

    async def count_tokens(
        self,
        messages: list[dict],
    ) -> int:
        """
        计算对话消息的总 Token 数

        Args:
            messages: 对话消息列表

        Returns:
            总 Token 数
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self._estimate_tokens(part["text"])
        return total
