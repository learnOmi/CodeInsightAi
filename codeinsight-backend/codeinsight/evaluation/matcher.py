"""
匹配策略层

定义知识点匹配的多种策略，支持精确匹配、模糊匹配、组合匹配。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


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
    """精确标题匹配（当前实现）"""

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
