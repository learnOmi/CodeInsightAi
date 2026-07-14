"""
嵌入客户端

统一的嵌入生成封装，支持 litellm 进行向量嵌入。
"""

from __future__ import annotations

import logging
from typing import Any

import litellm
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.config import settings
from codeinsight.llm.errors import LLMError
from codeinsight.models.knowledge_point import KnowledgePointModel

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """
    嵌入客户端

    使用 litellm 生成文本嵌入向量，支持批量和单条嵌入，
    以及将嵌入向量存储到 pgvector 数据库。
    """

    def __init__(self, model: str = "text-embedding-3-small"):
        """
        初始化嵌入客户端

        Args:
            model: 嵌入模型名称，默认为 "text-embedding-3-small"
        """
        self._model_name = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成文本嵌入向量

        使用 litellm.aembedding 进行异步批量嵌入调用。

        Args:
            texts: 需要生成嵌入的文本列表

        Returns:
            嵌入向量列表，每个向量对应 texts 中的文本

        Raises:
            LLMError: 当嵌入调用失败时抛出
        """
        try:
            kwargs: dict[str, Any] = {
                "model": self._model_name,
                "input": texts,
                "timeout": settings.llm_timeout or 60.0,
            }

            if settings.llm_api_key:
                kwargs["api_key"] = settings.llm_api_key

            if settings.llm_provider == "ollama":
                kwargs["api_base"] = settings.ollama_host
                kwargs["model"] = f"ollama/{self._model_name}"

            response = await litellm.aembedding(**kwargs)

            embeddings: list[list[float]] = [data.get("embedding", []) for data in response.data]

            logger.debug(
                "批量嵌入生成完成: count=%d, model=%s",
                len(texts),
                self._model_name,
            )
            return embeddings

        except Exception as exc:
            error_msg = f"Embedding failed: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMError(
                error_msg,
                provider=settings.llm_provider,
                model=self._model_name,
            ) from exc

    async def embed_single(self, text: str) -> list[float]:
        """
        生成单条文本的嵌入向量

        Args:
            text: 需要生成嵌入的单个文本

        Returns:
            嵌入向量

        Raises:
            LLMError: 当嵌入调用失败时抛出
        """
        embeddings = await self.embed([text])
        if not embeddings:
            raise LLMError("Empty embedding returned", provider="", model=self._model_name)
        return embeddings[0]

    async def store(
        self,
        session: AsyncSession,
        model: KnowledgePointModel,
        vector: list[float],
    ) -> None:
        """
        将嵌入向量存储到数据库

        通过 pgvector 将向量保存到 KnowledgePointModel 的 embedding 列。

        Args:
            session: 异步数据库会话
            model: 知识点对应的模型实例
            vector: 嵌入向量

        Raises:
            LLMError: 当存储失败时抛出
        """
        try:
            # pgvector's Vector type accepts list[float] at runtime despite type annotation mismatch
            model.embedding = vector  # type: ignore[assignment]
            session.add(model)
            await session.commit()

            logger.debug(
                "嵌入向量已存储: knowledge_point_id=%s, dimension=%d",
                model.id,
                len(vector),
            )
        except Exception as exc:
            await session.rollback()
            error_msg = f"Embedding storage failed: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMError(
                error_msg,
                provider="",
                model=self._model_name,
            ) from exc
