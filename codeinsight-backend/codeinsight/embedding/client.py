"""
嵌入客户端

统一的嵌入生成封装，内部使用 LLMClient 进行嵌入调用。
避免与 LLMClient 的 embed() 重复实现。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.llm.client import LLMClient
from codeinsight.llm.errors import LLMError
from codeinsight.models.knowledge_point import KnowledgePointModel

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """
    嵌入客户端

    使用 LLMClient 生成文本嵌入向量，支持批量、单条嵌入和向量存储。
    不重复实现 litellm 调用逻辑，全部委托给 LLMClient.embed()。
    """

    def __init__(self, llm_client: LLMClient | None = None):
        """
        初始化嵌入客户端

        Args:
            llm_client: LLM 客户端实例，如果为 None 则创建默认实例
        """
        self._llm_client = llm_client or LLMClient()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成文本嵌入向量

        委托给 LLMClient.embed() 实现。

        Args:
            texts: 需要生成嵌入的文本列表

        Returns:
            嵌入向量列表
        """
        return await self._llm_client.embed(texts)

    async def embed_single(self, text: str) -> list[float]:
        """
        生成单条文本的嵌入向量

        Args:
            text: 需要生成嵌入的单个文本

        Returns:
            嵌入向量

        Raises:
            LLMError: 当嵌入为空时抛出
        """
        embeddings = await self.embed([text])
        if not embeddings:
            raise LLMError("Empty embedding returned", provider="", model="")
        result = embeddings[0]
        # L-B9: 检查是否为空向量（所有元素为 0）
        if not any(v != 0 for v in result):
            raise LLMError("Empty embedding vector (all zeros)", provider="", model="")
        return result

    async def store(
        self,
        session: AsyncSession,
        model: KnowledgePointModel,
        vector: list[float],
    ) -> None:
        """
        将嵌入向量存储到数据库

        通过 pgvector 将向量保存到 KnowledgePointModel 的 embedding 列。
        注意：本方法不提交会话，由调用方管理事务生命周期。

        Args:
            session: 异步数据库会话
            model: 知识点对应的模型实例
            vector: 嵌入向量

        Raises:
            LLMError: 当存储失败时抛出
        """
        try:
            # L-D9: 显式类型转换，避免 type: ignore 掩盖真实类型不匹配
            # mypy 认为 Vector 列不接受 list[float]，但 pgvector 运行时支持
            model_embedding = list[float](vector)
            model.embedding = model_embedding  # type: ignore[assignment]
            session.add(model)

            logger.debug(
                "嵌入向量已添加至会话: knowledge_point_id=%s, dimension=%d",
                model.id,
                len(vector),
            )
        except Exception as exc:
            error_msg = f"Embedding storage failed: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMError(
                error_msg,
                provider="",
                model="",
            ) from exc
