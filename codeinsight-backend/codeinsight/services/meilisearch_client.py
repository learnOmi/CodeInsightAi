"""
Meilisearch 全文搜索客户端（异步版本）

使用 httpx.AsyncClient 直接调用 Meilisearch REST API，避免同步 SDK 阻塞事件循环。
S-B1 修复：单例初始化使用 asyncio.Lock 保护，确保 asyncio 环境下线程安全。
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import httpx

from codeinsight.config import settings

logger = logging.getLogger(__name__)

# 知识点索引名称
KNOWLEDGE_POINTS_INDEX = "knowledge_points"


class MeiliSearchClient:
    """
    Meilisearch 全文搜索客户端（异步）

    使用 httpx.AsyncClient 直接调用 Meilisearch REST API，
    所有方法均为 async def，不阻塞事件循环。

    S-B1 修复：单例使用 asyncio.Lock 保护初始化。
    """

    _instance: MeiliSearchClient | None = None
    _init_lock: asyncio.Lock | None = None
    _httpx_client: httpx.AsyncClient | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """获取初始化锁（惰性创建）"""
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()
        return cls._init_lock

    @classmethod
    async def create(cls) -> MeiliSearchClient:
        """
        获取单例实例（异步安全）

        使用 asyncio.Lock 保护初始化，确保多协程并发调用时
        只创建一个实例。
        """
        if cls._instance is not None:
            return cls._instance

        async with cls._get_lock():
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._httpx_client = httpx.AsyncClient(
                    base_url=settings.meilisearch_host.rstrip("/"),
                    headers={"Authorization": f"Bearer {settings.meilisearch_master_key}"},
                )
            return cls._instance

    @classmethod
    def instance(cls) -> MeiliSearchClient:
        """
        同步获取单例实例（惰性创建，仅在非异步上下文或初始化阶段使用）

        注意：在 async 上下文中应优先使用 await MeiliSearchClient.create()
        以确保线程安全。此方法仅用于同步调用场景。
        """
        if cls._instance is not None:
            return cls._instance
        # 同步场景：直接创建
        cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def client(self) -> httpx.AsyncClient:
        """获取 httpx 异步客户端实例"""
        if self._httpx_client is None:
            self._httpx_client = httpx.AsyncClient(
                base_url=settings.meilisearch_host.rstrip("/"),
                headers={"Authorization": f"Bearer {settings.meilisearch_master_key}"},
            )
        return self._httpx_client

    @property
    def index_url(self) -> str:
        """获取知识点索引的 API 基础路径"""
        return f"/indexes/{KNOWLEDGE_POINTS_INDEX}"

    # ── 索引管理 ──

    async def ensure_index(self) -> None:
        """
        确保知识点索引存在，并配置搜索属性

        幂等操作，可安全重复调用。
        """
        base = f"{self.index_url}"

        # 创建索引（如果不存在）
        try:
            resp = await self.client.get(base)
            if resp.status_code == 404:
                await self.client.post(
                    "/indexes",
                    json={"uid": KNOWLEDGE_POINTS_INDEX, "primaryKey": "id"},
                )
                logger.info("Meilisearch 索引已创建: %s", KNOWLEDGE_POINTS_INDEX)
            else:
                logger.debug("Meilisearch 索引已存在: %s", KNOWLEDGE_POINTS_INDEX)
        except Exception:
            # 404 也是预期状态，继续创建
            await self.client.post(
                "/indexes",
                json={"uid": KNOWLEDGE_POINTS_INDEX, "primaryKey": "id"},
            )

        # 配置搜索属性
        await self.client.patch(
            f"{base}/settings",
            json={
                "searchableAttributes": ["title", "description", "tags"],
                "filterableAttributes": ["category", "repository_id", "version", "tags"],
                "sortableAttributes": ["confidence", "created_at"],
                "displayedAttributes": [
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
                ],
            },
        )
        logger.info("Meilisearch 索引配置已更新: %s", KNOWLEDGE_POINTS_INDEX)

    # ── 文档操作 ──

    async def add_document(self, kp: dict) -> None:
        """
        添加或更新知识点文档到 Meilisearch 索引

        Args:
            kp: 知识点字典，必须包含 id/title/description/category 等字段
        """
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
        try:
            await self.client.post(
                f"{self.index_url}/documents",
                json=document,
            )
            logger.debug("知识点已同步到 Meilisearch: id=%s", kp["id"])
        except Exception as exc:
            logger.warning("知识点同步到 Meilisearch 失败: id=%s, error=%s", kp.get("id"), exc)

    async def add_documents(self, kps: list[dict]) -> None:
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

        if not documents:
            return

        try:
            await self.client.post(
                f"{self.index_url}/documents",
                json=documents,
            )
            logger.debug("批量知识点已同步到 Meilisearch: count=%d", len(documents))
        except Exception as exc:
            logger.warning("批量知识点同步到 Meilisearch 失败: %s", exc)

    async def delete_document(self, point_id: UUID) -> None:
        """
        从 Meilisearch 索引中删除知识点文档

        Args:
            point_id: 知识点 ID
        """
        try:
            await self.client.delete(f"{self.index_url}/documents/{point_id}")
            logger.debug("知识点已从 Meilisearch 删除: id=%s", point_id)
        except Exception as exc:
            logger.warning("知识点从 Meilisearch 删除失败: id=%s, error=%s", point_id, exc)

    # ── 搜索 ──

    async def search(
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
        search_body: dict = {
            "q": query,
            "limit": limit,
            "offset": offset,
        }
        if filter_params:
            search_body["filter"] = filter_params
        if sort:
            search_body["sort"] = sort

        try:
            resp = await self.client.post(
                f"{self.index_url}/search",
                json=search_body,
            )
            if resp.status_code >= 400:
                logger.error("Meilisearch 搜索失败: query=%s, status=%d, body=%s", query, resp.status_code, resp.text)
                return {"hits": [], "totalHits": 0}
            return resp.json()
        except Exception as exc:
            logger.error("Meilisearch 搜索失败: query=%s, error=%s", query, exc, exc_info=True)
            return {"hits": [], "totalHits": 0}
