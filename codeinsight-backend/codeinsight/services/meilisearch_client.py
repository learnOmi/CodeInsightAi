"""
Meilisearch 全文搜索客户端

封装 Meilisearch 索引创建、文档同步、搜索操作。
知识点创建/更新/删除时同步到 Meilisearch 索引。
"""

from __future__ import annotations

import logging
import threading
from uuid import UUID

import meilisearch
from meilisearch.index import Index

from codeinsight.config import settings

logger = logging.getLogger(__name__)

# 知识点索引名称
KNOWLEDGE_POINTS_INDEX = "knowledge_points"


class MeiliSearchClient:
    """
    Meilisearch 全文搜索客户端

    提供索引管理、文档同步、搜索的基础封装。
    使用单例模式，确保整个应用共用同一个客户端实例。
    """

    _instance: MeiliSearchClient | None = None
    _client: meilisearch.Client | None = None
    _init_lock: threading.Lock | None = None

    def __new__(cls) -> MeiliSearchClient:
        if cls._instance is None:
            if cls._init_lock is None:
                cls._init_lock = threading.Lock()
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def client(self) -> meilisearch.Client:
        """获取 Meilisearch 客户端实例（懒初始化）"""
        if self._client is None:
            self._client = meilisearch.Client(
                settings.meilisearch_host,
                settings.meilisearch_master_key,
            )
        return self._client

    def get_index(self) -> Index:
        """获取知识点索引"""
        return self.client.index(KNOWLEDGE_POINTS_INDEX)

    def ensure_index(self) -> None:
        """
        确保知识点索引存在，并配置搜索属性

        幂等操作，可安全重复调用。
        """
        try:
            # 获取或创建索引
            try:
                self.client.get_index(KNOWLEDGE_POINTS_INDEX)
                logger.debug("Meilisearch 索引已存在: %s", KNOWLEDGE_POINTS_INDEX)
            except meilisearch.errors.MeilisearchApiError:
                self.client.create_index(KNOWLEDGE_POINTS_INDEX, {"primaryKey": "id"})
                logger.info("Meilisearch 索引已创建: %s", KNOWLEDGE_POINTS_INDEX)

            # 配置搜索属性
            index = self.client.index(KNOWLEDGE_POINTS_INDEX)
            index.update_searchable_attributes(["title", "description", "tags"])
            index.update_filterable_attributes(["category", "repository_id", "version", "tags"])
            index.update_sortable_attributes(["confidence", "created_at"])
            index.update_displayed_attributes(
                [
                    "id",
                    "title",
                    "description",
                    "category",
                    "category_name",
                    "tags",
                    "confidence",
                    "repository_id",
                    "version",
                    "created_at",
                ]
            )
            logger.info("Meilisearch 索引配置已更新: %s", KNOWLEDGE_POINTS_INDEX)
        except Exception as exc:
            logger.error("Meilisearch 索引初始化失败: %s", exc, exc_info=True)
            raise

    def add_document(self, kp: dict) -> None:
        """
        添加或更新知识点文档到 Meilisearch 索引

        Args:
            kp: 知识点字典，必须包含 id/title/description/category 等字段
        """
        try:
            document = {
                "id": str(kp["id"]),
                "title": kp.get("title", ""),
                "description": kp.get("description", ""),
                "category": kp.get("category", ""),
                "category_name": kp.get("category_name", ""),
                "tags": kp.get("tags", []),
                "confidence": kp.get("confidence", 0.0),
                "repository_id": str(kp.get("repository_id", "")),
                "version": kp.get("version", ""),
                "created_at": kp.get("created_at", ""),
            }
            self.get_index().add_documents([document])
            logger.debug("知识点已同步到 Meilisearch: id=%s", kp["id"])
        except Exception as exc:
            logger.warning("知识点同步到 Meilisearch 失败: id=%s, error=%s", kp.get("id"), exc)

    def add_documents(self, kps: list[dict]) -> None:
        """
        批量添加知识点文档到 Meilisearch 索引

        Args:
            kps: 知识点字典列表
        """
        documents = []
        for kp in kps:
            documents.append(
                {
                    "id": str(kp["id"]),
                    "title": kp.get("title", ""),
                    "description": kp.get("description", ""),
                    "category": kp.get("category", ""),
                    "category_name": kp.get("category_name", ""),
                    "tags": kp.get("tags", []),
                    "confidence": kp.get("confidence", 0.0),
                    "repository_id": str(kp.get("repository_id", "")),
                    "version": kp.get("version", ""),
                    "created_at": kp.get("created_at", ""),
                }
            )
        if documents:
            try:
                self.get_index().add_documents(documents)
                logger.debug("批量知识点已同步到 Meilisearch: count=%d", len(documents))
            except Exception as exc:
                logger.warning("批量知识点同步到 Meilisearch 失败: %s", exc)

    def delete_document(self, point_id: UUID) -> None:
        """
        从 Meilisearch 索引中删除知识点文档

        Args:
            point_id: 知识点 ID
        """
        try:
            self.get_index().delete_document(str(point_id))
            logger.debug("知识点已从 Meilisearch 删除: id=%s", point_id)
        except Exception as exc:
            logger.warning("知识点从 Meilisearch 删除失败: id=%s, error=%s", point_id, exc)

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        filter_params: list[str] | None = None,
        sort: list[str] | None = None,
    ) -> dict:
        """
        搜索知识点

        Args:
            query: 搜索关键词
            limit: 返回条数上限
            offset: 偏移量
            filter_params: 筛选条件列表，如 ["category = DP", "confidence > 0.8"]
            sort: 排序条件，如 ["confidence:desc"]

        Returns:
            Meilisearch 搜索结果字典
        """
        search_params: dict = {
            "limit": limit,
            "offset": offset,
        }
        if filter_params:
            search_params["filter"] = filter_params
        if sort:
            search_params["sort"] = sort

        try:
            result = self.get_index().search(query, search_params)
            return result  # type: ignore[no-any-return]
        except Exception as exc:
            logger.error("Meilisearch 搜索失败: query=%s, error=%s", query, exc)
            return {"hits": [], "totalHits": 0, "estimatedTotalHits": 0}
