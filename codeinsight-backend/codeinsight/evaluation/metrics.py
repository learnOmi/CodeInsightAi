"""
评估指标定义

定义知识点提取质量的评估指标，包括精确率、召回率、F1 值等。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CategoryMetrics:
    """
    分类评估指标

    按知识点分类统计的评估指标。

    Attributes:
        category: 知识点分类（DP/AD/AL/ET/DK）
        category_name: 分类名称
        precision: 精确率
        recall: 召回率
        f1_score: F1 值
        total_extracted: 提取的知识点数量
        total_expected: 期望的知识点数量
    """

    category: str
    category_name: str
    precision: float
    recall: float
    f1_score: float
    total_extracted: int
    total_expected: int


@dataclass
class EvaluationResult:
    """
    评估结果

    包含整体评估指标和各分类的详细指标。

    Attributes:
        repo_id: 仓库 ID
        overall_f1: 整体 F1 值
        overall_precision: 整体精确率
        overall_recall: 整体召回率
        category_metrics: 各分类的评估指标列表
        total_extracted: 总提取知识点数量
        total_expected: 总期望知识点数量
        avg_confidence: 平均置信度
        execution_time: 执行时间（秒）
    """

    repo_id: str
    overall_f1: float
    overall_precision: float
    overall_recall: float
    category_metrics: list[CategoryMetrics]
    total_extracted: int
    total_expected: int
    avg_confidence: float
    execution_time: float

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典表示

        Returns:
            字典格式的评估结果
        """
        return {
            "repo_id": self.repo_id,
            "overall_f1": self.overall_f1,
            "overall_precision": self.overall_precision,
            "overall_recall": self.overall_recall,
            "category_metrics": [asdict(cm) for cm in self.category_metrics],
            "total_extracted": self.total_extracted,
            "total_expected": self.total_expected,
            "avg_confidence": self.avg_confidence,
            "execution_time": self.execution_time,
        }


class MetricCalculator:
    """
    指标计算器

    提供计算各种评估指标的方法。
    """

    @staticmethod
    def calculate_precision(tp: int, fp: int) -> float:
        """
        计算精确率

        Precision = TP / (TP + FP)

        Args:
            tp: 真阳性数量
            fp: 假阳性数量

        Returns:
            精确率（0.0 ~ 1.0）
        """
        denominator = tp + fp
        if denominator == 0:
            return 0.0
        return tp / denominator

    @staticmethod
    def calculate_recall(tp: int, fn: int) -> float:
        """
        计算召回率

        Recall = TP / (TP + FN)

        Args:
            tp: 真阳性数量
            fn: 假阴性数量

        Returns:
            召回率（0.0 ~ 1.0）
        """
        denominator = tp + fn
        if denominator == 0:
            return 0.0
        return tp / denominator

    @staticmethod
    def calculate_f1(precision: float, recall: float) -> float:
        """
        计算 F1 值

        F1 = 2 * Precision * Recall / (Precision + Recall)

        Args:
            precision: 精确率
            recall: 召回率

        Returns:
            F1 值（0.0 ~ 1.0）
        """
        denominator = precision + recall
        if denominator == 0:
            return 0.0
        return 2 * precision * recall / denominator

    @staticmethod
    def calculate_average_confidence(confidence_scores: list[float]) -> float:
        """
        计算平均置信度

        Args:
            confidence_scores: 置信度分数列表

        Returns:
            平均置信度（0.0 ~ 1.0）
        """
        if not confidence_scores:
            return 0.0
        return sum(confidence_scores) / len(confidence_scores)
