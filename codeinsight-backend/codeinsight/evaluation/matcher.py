"""
匹配策略层

定义知识点匹配的多种策略，支持精确匹配、模糊匹配、语义匹配、代码行级匹配。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """匹配结果"""

    is_match: bool
    score: float = 0.0
    match_type: str = "none"
    detail: str = ""


class MatcherStrategy(ABC):
    """匹配策略基类"""

    @abstractmethod
    async def match(
        self,
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> MatchResult: ...


class ExactTitleMatcher(MatcherStrategy):
    """精确标题匹配"""

    async def match(
        self,
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> MatchResult:
        title_a = extracted.get("title", "")
        title_b = expected.get("title", "")
        is_match = title_a == title_b
        return MatchResult(
            is_match=is_match,
            score=1.0 if is_match else 0.0,
            match_type="exact",
        )


class FuzzyTitleMatcher(MatcherStrategy):
    """模糊标题匹配

    使用 difflib.SequenceMatcher 计算标题相似度，支持别名匹配。
    """

    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold

    async def match(
        self,
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> MatchResult:
        title_a = extracted.get("title", "")
        title_b = expected.get("title", "")

        if not title_a or not title_b:
            return MatchResult(is_match=False, score=0.0, match_type="fuzzy")

        # 完全匹配
        if title_a == title_b:
            return MatchResult(is_match=True, score=1.0, match_type="exact")

        # 别名匹配
        alternatives = expected.get("alternative_titles", [])
        if title_a in alternatives:
            return MatchResult(is_match=True, score=1.0, match_type="exact")

        # 模糊匹配
        ratio = SequenceMatcher(None, title_a, title_b).ratio()
        return MatchResult(
            is_match=ratio >= self.threshold,
            score=ratio,
            match_type="fuzzy",
            detail=f"similarity={ratio:.4f}",
        )


class CategoryMatcher(MatcherStrategy):
    """分类匹配器

    验证 category 字段是否匹配。
    """

    async def match(
        self,
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> MatchResult:
        cat_a = extracted.get("category", "")
        cat_b = expected.get("category", "")
        is_match = cat_a == cat_b
        return MatchResult(
            is_match=is_match,
            score=1.0 if is_match else 0.0,
            match_type="category",
            detail=f"category={cat_a} vs {cat_b}",
        )


class SemanticMatcher(MatcherStrategy):
    """语义匹配器（V2）

    使用 embedding 向量计算余弦相似度，能匹配跨语言等价概念
    （如"工厂方法" ↔ "Factory Method"）。

    需要传入 embed_fn 函数，接收文本返回 embedding 向量。
    """

    def __init__(
        self,
        embed_fn: Any | None = None,
        threshold: float = 0.85,
        llm_client: Any | None = None,
    ):
        """初始化语义匹配器

        Args:
            embed_fn: 嵌入函数，接收 (str) -> list[float]
            threshold: 匹配阈值
            llm_client: LLM 客户端（备选，有 embed() 方法时使用）
        """
        self._embed_fn = embed_fn
        self._threshold = threshold
        self._llm_client = llm_client

    async def match(
        self,
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> MatchResult:
        # 优先使用标题和描述拼接作为匹配文本
        text_a = self._build_match_text(extracted)
        text_b = self._build_match_text(expected)

        if not text_a or not text_b:
            return MatchResult(is_match=False, score=0.0, match_type="semantic")

        embedding_a = await self._get_embedding(text_a)
        embedding_b = await self._get_embedding(text_b)

        if embedding_a is None or embedding_b is None:
            logger.warning("语义匹配失败：无法获取 embedding")
            return MatchResult(is_match=False, score=0.0, match_type="semantic_error")

        similarity = self._cosine_similarity(embedding_a, embedding_b)
        return MatchResult(
            is_match=similarity >= self._threshold,
            score=similarity,
            match_type="semantic",
            detail=f"cosine_similarity={similarity:.4f}",
        )

    @staticmethod
    def _build_match_text(point: dict[str, Any]) -> str:
        """构建用于匹配的文本"""
        parts = []
        title = point.get("title", "")
        if title:
            parts.append(title)
        description = point.get("description", "")
        if description:
            parts.append(description)
        return " | ".join(parts)

    async def _get_embedding(self, text: str) -> list[float] | None:
        """获取文本的 embedding 向量"""
        if self._embed_fn:
            result = self._embed_fn(text)
            if result is not None:
                return result if isinstance(result, list) else list(result)

        if self._llm_client and hasattr(self._llm_client, "embed"):
            try:
                result = await self._llm_client.embed(text)
                return result if isinstance(result, list) else list(result)
            except Exception as exc:
                logger.warning("embedding 调用失败: %s", exc)
                return None

        return None

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b) or not a:
            return 0.0
        dot_product: float = sum(x * y for x, y in zip(a, b, strict=False))  # type: ignore[no-any-return]
        norm_a: float = sum(x * x for x in a) ** 0.5  # type: ignore[no-any-return]
        norm_b: float = sum(y * y for y in b) ** 0.5  # type: ignore[no-any-return]
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)


class LineMatchMatcher(MatcherStrategy):
    """代码行级匹配器（V2）

    计算 highlighted_lines 的交并比（IoU），衡量代码位置匹配准确度。
    此匹配器不直接判定是否匹配，而是提供细粒度评分。
    """

    def __init__(self, iou_threshold: float = 0.5):
        """初始化

        Args:
            iou_threshold: IoU 阈值，高于此值视为匹配
        """
        self.iou_threshold = iou_threshold

    async def match(
        self,
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> MatchResult:
        lines_a = set(extracted.get("code_lines_match", []) or [])
        lines_b = set(expected.get("code_lines_match", []) or [])

        if not lines_a and not lines_b:
            # 双方都没有行级标注，视为中性（不匹配也不反对）
            return MatchResult(is_match=True, score=1.0, match_type="line_match_none")

        if not lines_a or not lines_b:
            # 只有一方有标注，不匹配
            return MatchResult(
                is_match=False,
                score=0.0,
                match_type="line_match",
                detail=f"one side has no lines: extracted={len(lines_a)}, expected={len(lines_b)}",
            )

        intersection = lines_a & lines_b
        union = lines_a | lines_b
        iou = len(intersection) / len(union) if union else 0.0

        return MatchResult(
            is_match=iou >= self.iou_threshold,
            score=iou,
            match_type="line_match",
            detail=f"IoU={iou:.4f} ({len(intersection)}/{len(union)})",
        )


class CompositeMatcher(MatcherStrategy):
    """组合匹配器

    按优先级依次尝试多个匹配策略，任一匹配则返回成功。
    """

    def __init__(self, matchers: list[MatcherStrategy] | None = None):
        self.matchers = matchers or [
            CategoryMatcher(),
            ExactTitleMatcher(),
            FuzzyTitleMatcher(),
        ]

    async def match(
        self,
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> MatchResult:
        # 先检查分类是否匹配
        category_result = await CategoryMatcher().match(extracted, expected)
        if not category_result.is_match:
            return MatchResult(
                is_match=False,
                score=0.0,
                match_type="category_mismatch",
                detail=f"category mismatch: {extracted.get('category')} vs {expected.get('category')}",
            )

        # 再按优先级尝试标题匹配
        for matcher in self.matchers:
            if isinstance(matcher, CategoryMatcher):
                continue
            result = await matcher.match(extracted, expected)
            if result.is_match:
                return result

        return MatchResult(is_match=False, score=0.0, match_type="none")


def create_default_matcher() -> CompositeMatcher:
    """创建默认组合匹配器

    Returns:
        默认组合匹配器
    """
    return CompositeMatcher(
        [
            ExactTitleMatcher(),
            FuzzyTitleMatcher(threshold=0.8),
        ]
    )
