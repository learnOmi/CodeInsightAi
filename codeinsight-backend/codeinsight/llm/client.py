"""
LLM 客户端

统一的 LLM 调用封装，支持 Claude、GPT 和 Ollama 等多种提供商。
使用 litellm 进行路由，配置从全局 Settings 加载。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm
from pydantic import BaseModel, Field

from codeinsight.config import settings
from codeinsight.llm.cost import get_cost_tracker
from codeinsight.llm.errors import LLMError, OllamaUnavailableError

logger = logging.getLogger(__name__)


# L-E2: provider 从 Literal 限制改为 str + 配置驱动注册，支持动态扩展
PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "claude": {"default_model": "claude-3.5-sonnet-20241022"},
    "gpt": {"default_model": "gpt-4o"},
    "openai": {"default_model": "gpt-4o"},
    "ollama": {"default_model": "llama3.1:8b", "api_base_prefix": "ollama/"},
}


def register_provider(name: str, *, default_model: str, api_base_prefix: str | None = None) -> None:
    """注册新的 LLM provider（配置驱动扩展）"""
    PROVIDER_REGISTRY[name.lower()] = {
        "default_model": default_model,
        "api_base_prefix": api_base_prefix,
    }


class LLMConfig(BaseModel):
    """LLM 客户端配置——从全局 Settings 加载"""

    # L-E2: provider 改为 str，允许任意注册的 provider 名称
    provider: str = Field(
        default_factory=lambda: settings.llm_provider or "claude",
    )
    model: str = Field(default_factory=lambda: settings.llm_model or "")
    api_key: str | None = Field(default_factory=lambda: settings.llm_api_key or None)
    api_base: str | None = Field(default_factory=lambda: settings.llm_api_base or None)
    ollama_base_url: str = Field(default_factory=lambda: settings.ollama_host)
    temperature: float = Field(default_factory=lambda: settings.llm_temperature)
    max_tokens: int = 8192
    embedding_model: str = "text-embedding-3-small"
    ollama_embedding_model: str = "nomic-embed-text"  # Ollama 本地嵌入模型（text-embedding-3-small 在 Ollama 上不存在）
    num_retries: int = 3
    request_timeout: float = Field(default_factory=lambda: float(settings.llm_timeout))
    embedding_timeout: float = 60.0
    embedding_dimension: int = Field(default_factory=lambda: settings.embedding_dimension)  # 向量嵌入维度
    max_concurrency: int = Field(
        default_factory=lambda: settings.llm_max_concurrency, ge=1
    )  # 最大并发 LLM 调用数，超出的请求自动排队

    model_config = {"arbitrary_types_allowed": True}


class LLMClient:
    """
    统一的 LLM 客户端

    支持 Claude、GPT 和 Ollama 等多种大模型提供商，
    提供统一的对话、嵌入、流式响应、Token 计数接口。
    """

    # L-E1: 成本单价和简单任务路由从 Settings 配置加载，避免硬编码
    # 通过 _get_cost_map() / _get_task_models() 懒加载，确保使用最新配置
    _cost_map: dict[str, dict[str, float]] | None = None
    _task_models: dict[str, str] | None = None

    # 本地模型成本（近似为 0，因为本地运行不计费）
    LOCAL_MODEL_COST = 0.0

    @property
    def model_cost_map(self) -> dict[str, dict[str, float]]:
        if self._cost_map is None:
            self._cost_map = dict(settings.llm_cost_map)
        return self._cost_map

    @property
    def simple_task_models(self) -> dict[str, str]:
        if self._task_models is None:
            self._task_models = dict(settings.llm_simple_task_models)
        return self._task_models

    def __init__(self, config: LLMConfig | None = None):
        """
        初始化 LLM 客户端

        Args:
            config: LLM 配置对象，如果为 None 则从全局 Settings 加载默认配置
        """
        self.config = config or LLMConfig()
        self._model_name: str = self._resolve_model_name()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)
        self._config_lock = asyncio.Lock()
        # 全局限流退避计数器：所有并发调用共享，避免并发重试风暴
        self._rate_limit_hits: int = 0
        self._rate_limit_lock = asyncio.Lock()
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
            model = self.config.model or "gpt-4o"
            # 自定义 api_base（如 agnes 中转站）需要 openai/ 前缀才能被 litellm 识别
            if self.config.api_base:
                return f"openai/{model}"
            return model
        elif provider == "ollama":
            model = self.config.model or "llama3.1:8b"
            return f"ollama/{model}"
        elif self.config.api_base:
            # 自定义 provider 名 + 自定义 api_base（OpenAI 兼容模式）
            model = self.config.model or "gpt-4o"
            return f"openai/{model}"
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
            "num_retries": 0,  # 关闭 litellm 内部重试，由上层 _acompletion_with_retry 统一管控
        }

        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key  # noqa: S106 - 敏感信息由 litellm 内部脱敏

        if self.config.provider.lower() == "ollama":
            kwargs["api_base"] = self.config.ollama_base_url
            kwargs.pop("api_key", None)  # Ollama 不需要 API Key
        elif self.config.api_base:
            kwargs["api_base"] = self.config.api_base

        return kwargs

    async def _acompletion_with_retry(
        self,
        messages: list[dict],
        api_kwargs: dict[str, Any],
        max_retries: int = 3,
    ) -> Any:
        """
        带指数退避重试的 acompletion 调用

        所有并发调用共享限流退避计数器，避免并发重试风暴。
        免费用户限流窗口通常 60s+，退避时间 = max(2^(attempt+1), 60s) 起步。

        Args:
            messages: 对话消息列表
            api_kwargs: API 关键字参数
            max_retries: 最大重试次数（默认 3 次）

        Returns:
            litellm 响应对象

        Raises:
            RateLimitError: 重试耗尽后仍触发频率限制
            LLMError: 其他 LLM 调用错误
        """
        for attempt in range(max_retries + 1):
            # 被限流时，所有并发调用统一等待，避免并发重试风暴
            async with self._rate_limit_lock:
                if self._rate_limit_hits > 0:
                    wait = min(2**self._rate_limit_hits, 60)
                    logger.warning(
                        "LLM 全局退避，等待 %ds（rate_limit_hits=%d）",
                        wait,
                        self._rate_limit_hits,
                    )
                    await asyncio.sleep(wait)

            try:
                # 成功：降低全局限流计数器
                async with self._rate_limit_lock:
                    if self._rate_limit_hits > 0:
                        self._rate_limit_hits -= 1
                return await litellm.acompletion(messages=messages, **api_kwargs)
            except litellm.exceptions.RateLimitError as e:
                if attempt < max_retries:
                    # 累加全局限流计数器，所有并发调用统一退避
                    async with self._rate_limit_lock:
                        self._rate_limit_hits += 1
                    wait = min(2**self._rate_limit_hits, 60)
                    logger.warning(
                        "LLM 频率限制，全局限流计数器=%d，等待 %ds: %s",
                        self._rate_limit_hits,
                        wait,
                        e,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error("LLM 频率限制重试耗尽: %s", e)
                    raise
            except litellm.exceptions.InternalServerError as e:
                if attempt < max_retries:
                    async with self._rate_limit_lock:
                        self._rate_limit_hits += 1
                    wait = min(2**self._rate_limit_hits, 60)
                    logger.warning(
                        "LLM 上游内部错误，全局限流计数器=%d，等待 %ds: %s",
                        self._rate_limit_hits,
                        wait,
                        e,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error("LLM 上游内部错误重试耗尽: %s", e)
                    raise
            except Exception:
                # 非限流、非上游内部错误：不重试，直接抛出
                raise

    def _estimate_tokens(self, text: str) -> int:
        """使用 litellm 估算 Token 数，回退到粗略估算"""
        try:
            return litellm.token_counter(model=self._model_name, text=text)
        except Exception:
            return len(text) // 4

    def _get_cost_per_token(self, model_key: str) -> tuple[float, float]:
        """获取每 token 的输入/输出成本"""
        costs = self.model_cost_map.get(model_key, {"input": 0.0, "output": 0.0})
        return costs["input"] / 1_000_000, costs["output"] / 1_000_000

    # ────────── Ollama 健康检查 ──────────

    async def check_ollama_health(self) -> bool:
        """
        检查 Ollama 服务是否可用

        向 Ollama API 的 /api/tags 端点发送 GET 请求，
        验证服务是否正常运行。

        L-D8: 健康检查失败时抛出 OllamaUnavailableError，调用方可捕获并降级。

        Returns:
            True 如果 Ollama 服务可用

        Raises:
            OllamaUnavailableError: Ollama 服务不可用时抛出
        """
        if self.config.provider.lower() == "ollama":
            # 即使 provider 是 ollama，也执行实际健康检查
            pass

        try:
            import httpx

            base_url = self.config.ollama_base_url.rstrip("/")
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{base_url}/api/tags")
                if resp.status_code == 200:
                    return True
                raise OllamaUnavailableError(f"Ollama 服务返回 HTTP {resp.status_code}")
        except OllamaUnavailableError:
            raise
        except Exception as exc:
            raise OllamaUnavailableError(f"Ollama 服务不可用: {exc}") from exc

    # ────────── 核心接口 ──────────

    async def chat(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None = None,
        num_retries: int | None = None,
    ) -> dict | BaseModel:
        """
        发送对话请求（非流式）

        Args:
            messages: 对话消息列表
            response_model: 可选的 Pydantic 模型，用于解析响应结构
            num_retries: 可选的重试次数，覆盖配置中的默认值

        Returns:
            如果提供 response_model，返回解析后的 BaseModel 实例；
            否则返回包含 'content' 和 token 计数的字典

        Raises:
            LLMError: 当 LLM 调用失败时抛出
        """
        try:
            api_kwargs = self._get_api_kwargs()
            if num_retries is not None:
                api_kwargs["num_retries"] = num_retries
            async with self._semaphore:
                response = await self._acompletion_with_retry(messages, api_kwargs)
            content = response.choices[0].message.content if response.choices else None
            if content is None:
                raise LLMError(
                    "LLM 返回空响应",
                    provider=self.config.provider,
                    model=self._model_name,
                )

            usage = getattr(response, "usage", None)
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0

            if response_model:
                parsed = response_model.model_validate_json(content)

                # L-D4: response_model 路径也记录成本
                input_cost, output_cost = self._get_cost_per_token(self._get_model_key())
                call_cost = (prompt_tokens * input_cost) + (completion_tokens * output_cost)
                if prompt_tokens > 0 or completion_tokens > 0:
                    try:
                        await get_cost_tracker().record(
                            model=self._get_model_key(),
                            provider=self.config.provider,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            cost=call_cost,
                        )
                    except Exception:
                        logger.debug("成本记录失败", exc_info=True)

                logger.debug(
                    "LLM 响应已解析: provider=%s, model=%s, tokens=%d+%d",
                    self.config.provider,
                    self._model_name,
                    prompt_tokens,
                    completion_tokens,
                )
                return parsed

            # L-D3: 跳过零成本记录
            if prompt_tokens == 0 and completion_tokens == 0:
                return {"content": content, "prompt_tokens": 0, "completion_tokens": 0, "model": self._model_name}

            result: dict[str, Any] = {
                "content": content,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "model": self._model_name,
            }

            input_cost, output_cost = self._get_cost_per_token(self._get_model_key())
            call_cost = (prompt_tokens * input_cost) + (completion_tokens * output_cost)
            result["cost"] = call_cost

            # 记录成本到 CostTracker
            try:
                await get_cost_tracker().record(
                    model=self._get_model_key(),
                    provider=self.config.provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=call_cost,
                )
            except Exception:
                logger.debug("成本记录失败", exc_info=True)

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

            async with self._semaphore:
                response = await litellm.acompletion(
                    messages=messages,
                    **api_kwargs,
                )

            async for chunk in response:
                if not chunk.choices:
                    continue
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
        original_model = self.config.model

        async with self._config_lock:
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
            self.config.model = original_model  # type: ignore[assignment]
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
        路由前先检查 Ollama 服务可用性，不可用时自动回退到云端。

        Args:
            messages: 对话消息列表
            task_type: 任务类型，支持 "classification", "summarization",
                       "extraction", "default"

        Returns:
            包含 'content' 和 token 计数的字典
        """
        # 检查路由开关（默认关闭，避免无 Ollama 环境时反复超时）
        if not settings.ollama_task_routing:
            return await self.chat(messages)  # type: ignore[return-value]

        if task_type in self.simple_task_models:
            local_model = self.simple_task_models[task_type]
            if self.config.provider.lower() != "ollama":
                # L-D8: Ollama 不可用时抛出 OllamaUnavailableError，自动降级到云端
                try:
                    await self.check_ollama_health()
                except OllamaUnavailableError:
                    logger.warning(
                        "Ollama 不可用，任务 '%s' 留在云端: %s",
                        task_type,
                        self._model_name,
                    )
                    return await self.chat(messages)  # type: ignore[return-value]

                old_provider = self.config.provider
                old_model = self.config.model
                async with self._config_lock:
                    try:
                        self.config.provider = "ollama"  # type: ignore[assignment]
                        self.config.model = local_model.replace("ollama/", "")
                        self._model_name = self._resolve_model_name()

                        logger.info("任务 '%s' 路由到本地模型: %s", task_type, self._model_name)
                        result = await self.chat(messages)

                        if isinstance(result, dict):
                            result["provider"] = "ollama"
                            result["cost"] = self.LOCAL_MODEL_COST  # 本地模型不计费
                        return result  # type: ignore[return-value]
                    except Exception as exc:
                        logger.warning("本地模型 %s 失败，回退到云端: %s", local_model, exc)
                        raise
                    finally:
                        # 确保实例状态始终恢复
                        self.config.provider = old_provider  # type: ignore[assignment]
                        self.config.model = old_model
                        self._model_name = self._resolve_model_name()

        return await self.chat(messages)  # type: ignore[return-value]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        生成文本嵌入向量

        使用 Ollama 本地嵌入模型生成向量，失败时返回零向量。
        嵌入向量仅用于语义搜索，不影响分析流程。

        Args:
            texts: 需要生成嵌入的文本列表

        Returns:
            嵌入向量列表（维度与数据库 schema 一致）

        Raises:
            LLMError: 当嵌入调用失败时抛出
        """
        try:
            # 嵌入向量始终使用本地 Ollama 生成，不依赖远程 LLM 的嵌入模型
            embedding_model = f"ollama/{self.config.ollama_embedding_model}"
            embedding_api_base = self.config.ollama_base_url

            # 快速检查 Ollama 是否可用，不可用时直接返回零向量避免阻塞
            try:
                import httpx

                base_url = embedding_api_base.rstrip("/")
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{base_url}/api/tags")
                    if resp.status_code != 200:
                        raise ConnectionError(f"Ollama 返回 HTTP {resp.status_code}")
            except Exception as health_err:
                logger.warning(
                    "Ollama 不可用，使用零向量: %s",
                    health_err,
                )
                return [[0.0] * self.config.embedding_dimension for _ in texts]

            # L-P1: 复用 _get_api_kwargs() 构建基础参数，避免与 chat() 重复
            kwargs = self._get_api_kwargs(timeout=self.config.embedding_timeout)
            kwargs["model"] = embedding_model
            kwargs["api_base"] = embedding_api_base  # 强制使用本地 Ollama 的 API 地址
            kwargs["input"] = texts
            # 移除 chat 专用参数
            kwargs.pop("temperature", None)
            kwargs.pop("max_tokens", None)
            kwargs.pop("num_retries", None)

            async with self._semaphore:
                response = await litellm.aembedding(**kwargs)

            # 兼容不同 LLM 提供商的返回格式（Ollama 返回 dict/list，OpenAI 返回对象）
            raw_embeddings: list[list[float]] = []
            for item in response.data:
                if isinstance(item, list):
                    # Ollama 可能直接返回嵌套的 embedding 列表
                    raw_embeddings.append(item)
                elif isinstance(item, dict):
                    # Ollama 格式: {"embedding": [0.1, ...]} 或 {"embeddings": [0.1, ...]}
                    emb = item.get("embedding") or item.get("embeddings")
                    if emb is not None and isinstance(emb, list):
                        raw_embeddings.append(emb)
                    else:
                        logger.warning("无法从 dict 解析嵌入向量: keys=%s", list(item.keys()))
                else:
                    # OpenAI 格式: item.embedding
                    emb = getattr(item, "embedding", None)
                    if emb is not None and isinstance(emb, list):
                        raw_embeddings.append(emb)
                    else:
                        logger.warning("无法从对象解析嵌入向量: type=%s", type(item))

            if not raw_embeddings:
                logger.warning("嵌入向量解析结果为空，使用零向量")
                return [[0.0] * self.config.embedding_dimension for _ in texts]

            # 检查并修正向量维度（Ollama 模型可能与数据库 schema 不一致）
            expected_dim = self.config.embedding_dimension
            padded_embeddings: list[list[float]] = []
            for emb in raw_embeddings:
                if len(emb) == expected_dim:
                    padded_embeddings.append(emb)
                elif len(emb) < expected_dim:
                    # 维度不足时补零
                    logger.warning(
                        "嵌入向量维度不足，正在补齐: actual=%d, expected=%d, padding=%d, model=%s",
                        len(emb),
                        expected_dim,
                        expected_dim - len(emb),
                        self.config.ollama_embedding_model,
                    )
                    padded_embeddings.append(emb + [0.0] * (expected_dim - len(emb)))
                else:
                    # 维度超出时截断
                    logger.warning(
                        "嵌入向量维度超出，正在截断: actual=%d, expected=%d, model=%s",
                        len(emb),
                        expected_dim,
                        self.config.ollama_embedding_model,
                    )
                    padded_embeddings.append(emb[:expected_dim])

            logger.debug(
                "嵌入生成完成: count=%d, model=%s, dimension=%d, expected_dim=%d",
                len(texts),
                embedding_model,
                len(padded_embeddings[0]) if padded_embeddings else 0,
                expected_dim,
            )
            return padded_embeddings

        except Exception as exc:
            exc_str = str(exc).lower()
            error_msg = f"LLM embed failed: {exc}"
            logger.error(error_msg, exc_info=True)

            # 检测模型未找到的错误，给出明确提示
            if "model" in exc_str and "not found" in exc_str:
                model_name = self.config.ollama_embedding_model
                logger.warning(
                    "Ollama 模型 '%s' 未找到，使用零向量。请运行: ollama pull %s",
                    model_name,
                    model_name,
                )
            else:
                logger.warning("嵌入失败，使用零向量: %s", exc)

            # 嵌入失败时返回零向量，避免阻塞分析流程
            if texts:
                return [[0.0] * self.config.embedding_dimension for _ in texts]
            raise LLMError(
                error_msg,
                provider="ollama",
                model=self.config.ollama_embedding_model,
            ) from exc

    # ────────── 缓存与成本控制 ──────────

    @staticmethod
    def _compute_code_fingerprint(messages: list[dict]) -> str:
        """
        计算代码上下文的哈希指纹，用于缓存键

        Args:
            messages: 对话消息列表

        Returns:
            SHA256 哈希指纹
        """
        combined = ""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                combined += content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        combined += part.get("text", "")
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    async def chat_with_cache(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None = None,
        cache_ttl: int = 86400,
    ) -> dict | BaseModel:
        """
        带缓存的对话请求

        基于代码指纹的缓存，避免重复代码分析产生相同 API 调用。
        缓存存储在 Redis 中，默认 TTL 为 24 小时。

        Args:
            messages: 对话消息列表
            response_model: 可选的 Pydantic 模型
            cache_ttl: 缓存 TTL（秒），默认 86400

        Returns:
            与 chat() 相同的返回值
        """
        # 尝试从缓存读取
        try:
            from codeinsight.db.redis_client import get_async_redis_client

            fingerprint = self._compute_code_fingerprint(messages)
            redis_client = await get_async_redis_client()
            cached = await redis_client.get(f"llm_cache:{fingerprint}")
            if cached:
                cached_data = json.loads(cached)
                logger.debug("LLM 缓存命中: fingerprint=%s", fingerprint[:8])
                if response_model:
                    return response_model.model_validate_json(cached_data.get("content", ""))
                return cached_data
        except Exception:
            logger.debug("LLM 缓存读取失败，跳过缓存")

        # 缓存未命中，调用 LLM
        result = await self.chat(messages, response_model=response_model)

        # 尝试写入缓存
        try:
            from codeinsight.db.redis_client import get_async_redis_client

            fingerprint = self._compute_code_fingerprint(messages)
            redis_client = await get_async_redis_client()
            cache_data = result
            if isinstance(result, BaseModel):
                cache_data = {"content": result.model_dump_json()}
            await redis_client.setex(f"llm_cache:{fingerprint}", cache_ttl, json.dumps(cache_data))
            logger.debug("LLM 缓存写入: fingerprint=%s", fingerprint[:8])
        except Exception:
            logger.debug("LLM 缓存写入失败，跳过缓存")

        return result

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
