"""
评估模块

提供知识点提取质量的评估功能，包括基于人工标注的评估和基于 LLM 的自评估。
"""

from codeinsight.evaluation.evaluator import KnowledgePointEvaluator, SelfEvaluator
from codeinsight.evaluation.metrics import (
    CategoryMetrics,
    EvaluationResult,
    MetricCalculator,
)
from codeinsight.evaluation.runner import EvaluationRunner, load_test_cases

__all__ = [
    "CategoryMetrics",
    "EvaluationResult",
    "MetricCalculator",
    "KnowledgePointEvaluator",
    "SelfEvaluator",
    "EvaluationRunner",
    "load_test_cases",
]
