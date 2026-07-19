"""
评估模块

提供知识点提取质量的评估功能，包括基于人工标注的评估和基于 LLM 的自评估。
"""

from codeinsight.evaluation.engine import EvalConfig, EvalEngine, EvalReport, EvalSummary
from codeinsight.evaluation.evaluator import KnowledgePointEvaluator, SelfEvaluator
from codeinsight.evaluation.matcher import (
    CompositeMatcher,
    ExactTitleMatcher,
    FuzzyTitleMatcher,
    MatcherStrategy,
    create_default_matcher,
)
from codeinsight.evaluation.metrics import (
    CategoryMetrics,
    EvaluationResult,
    MetricCalculator,
)
from codeinsight.evaluation.reporters import ConsoleReporter, JsonReporter, Reporter
from codeinsight.evaluation.runner import EvaluationRunner, load_test_cases

__all__ = [
    "CategoryMetrics",
    "EvaluationResult",
    "MetricCalculator",
    "KnowledgePointEvaluator",
    "SelfEvaluator",
    "EvaluationRunner",
    "load_test_cases",
    "EvalConfig",
    "EvalEngine",
    "EvalReport",
    "EvalSummary",
    "MatcherStrategy",
    "ExactTitleMatcher",
    "FuzzyTitleMatcher",
    "CompositeMatcher",
    "create_default_matcher",
    "Reporter",
    "ConsoleReporter",
    "JsonReporter",
]
