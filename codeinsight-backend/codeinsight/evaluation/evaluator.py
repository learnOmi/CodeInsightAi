"""
评估器实现

实现知识点提取质量的评估逻辑，支持人工标注数据和自动评估。
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

from codeinsight.evaluation.matcher import (
    MatcherStrategy,
    create_default_matcher,
)
from codeinsight.evaluation.metrics import (
    CategoryMetrics,
    EvaluationResult,
    MetricCalculator,
)
from codeinsight.schemas.constants import CATEGORY_NAMES

logger = logging.getLogger(__name__)


class KnowledgePointEvaluator:
    """
    知识点评估器

    使用人工标注的标准答案评估知识点提取的质量。
    支持可插拔的匹配策略。
    """

    def __init__(self, matcher: MatcherStrategy | None = None):
        """
        初始化评估器

        Args:
            matcher: 匹配策略，默认使用组合匹配器
        """
        self._metric_calculator = MetricCalculator()
        self._matcher = matcher or create_default_matcher()

    async def evaluate(
        self,
        repo_id: str,
        extracted_points: list[dict[str, Any]],
        expected_points: list[dict[str, Any]],
        matcher: MatcherStrategy | None = None,
    ) -> EvaluationResult:
        """
        执行评估

        比较提取的知识点和期望的知识点，计算各项评估指标。

        Args:
            repo_id: 仓库 ID
            extracted_points: 提取的知识点列表
            expected_points: 期望的知识点列表（人工标注）
            matcher: 可选，覆盖默认的匹配策略

        Returns:
            评估结果
        """
        # E-D1: 使用单调时钟，不受系统时间调整影响
        start_time = time.monotonic()
        logger.info("开始评估: repo_id=%s", repo_id)

        active_matcher = matcher or self._matcher
        category_metrics = []
        total_tp = 0
        total_fp = 0
        total_fn = 0
        total_extracted = len(extracted_points)
        total_expected = len(expected_points)

        confidence_scores = [point.get("confidence", 0.0) for point in extracted_points]

        for category in ["DP", "AD", "AL", "ET", "DK"]:
            extracted_by_category = [p for p in extracted_points if p.get("category") == category]
            expected_by_category = [p for p in expected_points if p.get("category") == category]

            tp, fp, fn = await self._calculate_confusion_matrix(
                extracted_by_category,
                expected_by_category,
                active_matcher,
            )

            total_tp += tp
            total_fp += fp
            total_fn += fn

            precision = self._metric_calculator.calculate_precision(tp, fp)
            recall = self._metric_calculator.calculate_recall(tp, fn)
            f1_score = self._metric_calculator.calculate_f1(precision, recall)

            category_metrics.append(
                CategoryMetrics(
                    category=category,
                    category_name=CATEGORY_NAMES.get(category, "未知"),
                    precision=precision,
                    recall=recall,
                    f1_score=f1_score,
                    total_extracted=len(extracted_by_category),
                    total_expected=len(expected_by_category),
                )
            )

        overall_precision = self._metric_calculator.calculate_precision(total_tp, total_fp)
        overall_recall = self._metric_calculator.calculate_recall(total_tp, total_fn)
        overall_f1 = self._metric_calculator.calculate_f1(overall_precision, overall_recall)
        avg_confidence = self._metric_calculator.calculate_average_confidence(confidence_scores)

        # E-D1: 使用单调时钟计算耗时
        execution_time = time.monotonic() - start_time

        result = EvaluationResult(
            repo_id=repo_id,
            overall_f1=overall_f1,
            overall_precision=overall_precision,
            overall_recall=overall_recall,
            category_metrics=category_metrics,
            total_extracted=total_extracted,
            total_expected=total_expected,
            avg_confidence=avg_confidence,
            execution_time=execution_time,
        )

        logger.info(
            "评估完成: repo_id=%s, f1=%.4f, precision=%.4f, recall=%.4f",
            repo_id,
            overall_f1,
            overall_precision,
            overall_recall,
        )

        return result

    async def _calculate_confusion_matrix(
        self,
        extracted: list[dict[str, Any]],
        expected: list[dict[str, Any]],
        matcher: MatcherStrategy,
    ) -> tuple[int, int, int]:
        """
        计算混淆矩阵

        使用匹配策略计算 TP、FP、FN。

        Args:
            extracted: 提取的知识点列表
            expected: 期望的知识点列表
            matcher: 匹配策略

        Returns:
            (TP, FP, FN) 三元组
        """
        tp = 0
        matched_expected = set()

        for ext in extracted:
            for idx, exp in enumerate(expected):
                if idx in matched_expected:
                    continue
                result = await matcher.match(ext, exp)
                if result.is_match:
                    tp += 1
                    matched_expected.add(idx)
                    break
            # 未匹配的 extracted 计入 FP

        fp = len(extracted) - tp
        fn = len(expected) - len(matched_expected)

        return tp, fp, fn


class SelfEvaluator:
    """
    自评估器

    使用 LLM 自身对提取结果进行评估，无需人工标注。
    """

    def __init__(self, llm_client: Any):
        """
        初始化自评估器

        Args:
            llm_client: LLM 客户端实例
        """
        self._llm_client = llm_client
        self._metric_calculator = MetricCalculator()

    async def self_evaluate(
        self,
        repo_id: str,
        extracted_points: list[dict[str, Any]],
        code_context: str,
    ) -> EvaluationResult:
        """
        执行自评估

        使用 LLM 对提取的知识点进行质量评估。

        Args:
            repo_id: 仓库 ID
            extracted_points: 提取的知识点列表
            code_context: 代码上下文

        Returns:
            自评估结果
        """
        # E-D1: 使用单调时钟
        start_time = time.monotonic()
        logger.info("开始自评估: repo_id=%s", repo_id)

        # E-D2: 复制输入避免原地修改副作用
        evaluated_points = [copy.deepcopy(point) for point in extracted_points]

        confidence_scores = []
        for point in evaluated_points:
            confidence = await self._evaluate_single_point(point, code_context)
            point["confidence"] = confidence
            confidence_scores.append(confidence)

        avg_confidence = self._metric_calculator.calculate_average_confidence(confidence_scores)

        result = EvaluationResult(
            repo_id=repo_id,
            overall_f1=0.0,
            overall_precision=0.0,
            overall_recall=0.0,
            category_metrics=[],
            total_extracted=len(extracted_points),
            total_expected=len(extracted_points),
            avg_confidence=avg_confidence,
            execution_time=time.monotonic() - start_time,
        )

        logger.info(
            "自评估完成: repo_id=%s, avg_confidence=%.4f (注意: F1/Precision/Recall 不可用，自评估仅提供置信度)",
            repo_id,
            avg_confidence,
        )

        return result

    async def _evaluate_single_point(
        self,
        point: dict[str, Any],
        code_context: str,
    ) -> float:
        """
        评估单个知识点的置信度

        使用 LLM 判断知识点的准确性。

        Args:
            point: 知识点
            code_context: 代码上下文

        Returns:
            置信度分数（0.0 ~ 1.0）
        """
        prompt = f"""
请评估以下知识点的准确性，基于提供的代码上下文。

知识点标题：{point.get("title", "")}
知识点描述：{point.get("description", "")}
知识点分类：{point.get("category", "")}

代码上下文：
{code_context[:5000]}

请返回一个 0.0 到 1.0 之间的分数，表示该知识点的置信度。
只返回数字，不要其他内容。
"""

        try:
            response = await self._llm_client.chat([{"role": "user", "content": prompt}])
            content = response.get("content", "0.5") if isinstance(response, dict) else str(response)
            confidence = float(content.strip())
            return max(0.0, min(1.0, confidence))
        except (ValueError, Exception) as exc:
            logger.warning("置信度评估失败，使用默认值: %s", exc)
            return 0.5
