"""
评估引擎

协调评估流程：加载数据 → 运行评估 → 计算指标 → 生成报告。
支持历史对比、回归检测、按语言/分类筛选、跨语言评估、A/B 测试。
"""

from __future__ import annotations

import copy
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codeinsight.evaluation.data.registry import (
    TestCase,
    list_datasets,
    load_datasets_from_dir,
)
from codeinsight.evaluation.evaluator import KnowledgePointEvaluator
from codeinsight.evaluation.matcher import (
    MatcherStrategy,
    create_default_matcher,
)
from codeinsight.evaluation.metrics import EvaluationResult, MetricCalculator

if TYPE_CHECKING:
    from codeinsight.evaluation.reporters.base import Reporter

logger = logging.getLogger(__name__)


@dataclass
class EvalConfig:
    """评估配置"""

    languages: list[str] | None = None
    categories: list[str] | None = None
    matcher: MatcherStrategy = field(default_factory=create_default_matcher)
    report_format: str = "json"
    threshold_f1: float = 0.0
    threshold_f1_drop: float = 0.05
    data_dir: str | None = None
    prompt_version: str = "unknown"
    verbose: bool = False
    output: str | None = None


@dataclass
class MetricResult:
    """指标结果"""

    f1: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    extracted: int = 0
    expected: int = 0
    cases: int = 0
    avg_confidence: float = 0.0
    time_seconds: float = 0.0


@dataclass
class EvalSummary:
    """评估汇总"""

    categories_evaluated: int = 0
    total_test_cases: int = 0
    total_extracted: int = 0
    overall_f1: float = 0.0
    total_time_seconds: float = 0.0
    timestamp: str = ""


@dataclass
class Snapshot:
    """历史快照"""

    timestamp: str
    prompt_version: str
    eval_version: str = "1.0.0"
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class Regression:
    """回归检测结果"""

    dimension: str
    previous_f1: float
    current_f1: float
    drop: float
    severity: str = "warning"


@dataclass
class EvalReport:
    """评估报告"""

    summary: EvalSummary
    by_language: dict[str, MetricResult] = field(default_factory=dict)
    by_category: dict[str, MetricResult] = field(default_factory=dict)
    by_language_category: dict[str, dict[str, MetricResult]] = field(default_factory=dict)
    config: EvalConfig | None = None
    history: list[Snapshot] = field(default_factory=list)
    regressions: list[Regression] = field(default_factory=list)


@dataclass
class CrossLangResult:
    """跨语言评估结果

    对比同一分类在不同语言上的表现一致性。
    """

    category: str
    by_language: dict[str, MetricResult]
    overall: MetricResult
    std_f1: float  # F1 标准差，越大表示语言间差异越大
    min_f1: float
    max_f1: float


@dataclass
class ABTestResult:
    """A/B 测试结果

    对比两种不同配置（如不同 prompt 版本）的评估结果。
    """

    control: EvalReport
    experiment: EvalReport
    control_label: str = "control"
    experiment_label: str = "experiment"

    @property
    def f1_diff(self) -> float:
        return self.experiment.summary.overall_f1 - self.control.summary.overall_f1

    @property
    def is_improvement(self) -> bool:
        return self.f1_diff > 0


class EvalEngine:
    """评估引擎

    协调整个评估流程，支持可配置的匹配策略、筛选条件、报告输出。
    """

    def __init__(
        self,
        config: EvalConfig | None = None,
        agent_fn: Callable | None = None,
        reporters: list[Reporter] | None = None,
    ):
        """初始化评估引擎

        Args:
            config: 评估配置
            agent_fn: Agent 函数，接收 (code_snippets, category) 返回知识点列表
            reporters: 报告输出器列表
        """
        self.config = config or EvalConfig()
        self._agent_fn = agent_fn
        self._evaluator = KnowledgePointEvaluator()
        self._reporters = reporters or []
        self._metric_calculator = MetricCalculator()

    async def run(
        self,
        languages: list[str] | None = None,
        categories: list[str] | None = None,
        data_dir: str | None = None,
        config: EvalConfig | None = None,
    ) -> EvalReport:
        """运行评估

        Args:
            languages: 筛选语言
            categories: 筛选分类
            data_dir: 数据目录，覆盖 config 中的设置
            config: 可选配置覆盖（E-B2 修复：用于不修改引擎实例配置的情况下传递替代配置）

        Returns:
            评估报告
        """
        active_config = config or self.config
        languages = languages or active_config.languages
        categories = categories or active_config.categories
        data_dir = data_dir or active_config.data_dir

        # 加载测试用例
        test_cases = self._load_test_cases(languages, categories, data_dir)

        # 按语言+分类分组执行
        by_language_category: dict[str, dict[str, list[EvaluationResult]]] = {}
        all_results: list[EvaluationResult] = []
        total_start = time.time()

        for tc in test_cases:
            lang = tc.language
            cat = tc.category

            # 提取知识点
            code_snippets = [cs.content for cs in tc.code_snippets]
            expected_points = [
                {
                    "category": ep.category,
                    "prefix": ep.prefix,
                    "title": ep.title,
                    "description": ep.description,
                    "confidence": ep.confidence,
                    "alternative_titles": ep.alternative_titles,
                }
                for ep in tc.expected_points
            ]

            if self._agent_fn:
                extracted = await self._agent_fn(code_snippets, cat)
            else:
                extracted = expected_points

            # 评估
            result = await self._evaluator.evaluate(
                repo_id=tc.case_id,
                extracted_points=extracted,
                expected_points=expected_points,
            )
            all_results.append(result)

            # 按维度聚合
            by_language_category.setdefault(lang, {}).setdefault(cat, []).append(result)

        total_time = time.time() - total_start

        # 构建报告
        report = self._build_report(by_language_category, all_results, total_time, active_config)

        # 输出报告
        for reporter in self._reporters:
            await reporter.report(report)

        return report

    def _load_test_cases(
        self,
        languages: list[str] | None,
        categories: list[str] | None,
        data_dir: str | None,
    ) -> list[TestCase]:
        """加载测试用例

        Args:
            languages: 筛选语言
            categories: 筛选分类
            data_dir: 数据目录

        Returns:
            测试用例列表
        """
        test_cases: list[TestCase] = []

        datasets = load_datasets_from_dir(data_dir) if data_dir else list_datasets()

        for ds in datasets:
            if languages and ds.language not in languages:
                continue
            if categories and ds.category not in categories:
                continue
            test_cases.extend(ds.test_cases)

        # E-D3: 空结果时添加警告和显式回退
        if not test_cases:
            if data_dir:
                logger.warning("指定目录 '%s' 中未找到匹配的测试用例", data_dir)
            elif not datasets:
                logger.warning("未找到任何数据集，尝试从默认 data/ 目录加载")
                # 兼容旧数据格式：从 data/ 目录加载
                default_dir = str(Path(__file__).parent / "data")
                datasets = load_datasets_from_dir(default_dir)
                for ds in datasets:
                    if languages and ds.language not in languages:
                        continue
                    if categories and ds.category not in categories:
                        continue
                    test_cases.extend(ds.test_cases)
                if not test_cases:
                    logger.warning("默认 data/ 目录也未找到匹配的测试用例")
            else:
                logger.warning(
                    "数据集存在但无匹配测试用例（filters: languages=%s, categories=%s）", languages, categories
                )

        return test_cases

    def _build_report(
        self,
        by_language_category: dict[str, dict[str, list[EvaluationResult]]],
        all_results: list[EvaluationResult],
        total_time: float,
        config: EvalConfig | None = None,
    ) -> EvalReport:
        """构建评估报告

        Args:
            by_language_category: 按语言×分类分组的结果
            all_results: 所有结果
            total_time: 总耗时

        Returns:
            评估报告
        """
        # 按语言聚合
        by_language: dict[str, list[EvaluationResult]] = {}
        for lang, cats in by_language_category.items():
            for cat_results in cats.values():
                by_language.setdefault(lang, []).extend(cat_results)

        # 按分类聚合
        by_category: dict[str, list[EvaluationResult]] = {}
        for _lang, cats in by_language_category.items():
            for cat, cat_results in cats.items():
                by_category.setdefault(cat, []).extend(cat_results)

        # 计算各维度指标
        lang_metrics = {lang: self._merge_metric_results(results) for lang, results in by_language.items()}
        cat_metrics = {cat: self._merge_metric_results(results) for cat, results in by_category.items()}

        # 整体汇总
        # E-D4: 使用加权 F1（按提取的知识点数量加权），而非算术平均
        # 确保大用例和小用例权重公平
        total_cases = len(all_results)
        total_extracted = sum(r.total_extracted for r in all_results)
        total_weighted_f1 = sum(r.overall_f1 * r.total_extracted for r in all_results)
        overall_f1 = (
            total_weighted_f1 / total_extracted
            if total_extracted > 0
            else (sum(r.overall_f1 for r in all_results) / total_cases if total_cases > 0 else 0.0)
        )

        summary = EvalSummary(
            categories_evaluated=len(by_category),
            total_test_cases=total_cases,
            total_extracted=total_extracted,
            overall_f1=overall_f1,
            total_time_seconds=round(total_time, 2),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        # 语言×分类的指标改为嵌套结构
        lang_cat_nested: dict[str, dict[str, MetricResult]] = {}
        for lang, cats in by_language_category.items():
            lang_cat_nested[lang] = {}
            for cat, results in cats.items():
                lang_cat_nested[lang][cat] = self._merge_metric_results(results)

        return EvalReport(
            summary=summary,
            by_language=lang_metrics,
            by_category=cat_metrics,
            by_language_category=lang_cat_nested,
            config=config,
        )

    def _merge_metric_results(self, results: list[EvaluationResult]) -> MetricResult:
        """合并多个评估结果为 MetricResult

        Args:
            results: 评估结果列表

        Returns:
            合并后的指标
        """
        if not results:
            return MetricResult()

        total_cases = len(results)
        total_extracted = sum(r.total_extracted for r in results)
        total_expected = sum(r.total_expected for r in results)

        return MetricResult(
            f1=sum(r.overall_f1 for r in results) / total_cases,
            precision=sum(r.overall_precision for r in results) / total_cases,
            recall=sum(r.overall_recall for r in results) / total_cases,
            extracted=total_extracted,
            expected=total_expected,
            cases=total_cases,
            avg_confidence=sum(r.avg_confidence for r in results) / total_cases,
            time_seconds=sum(r.execution_time for r in results),
        )

    @staticmethod
    def _merge_metric_results_from_metrics(metrics: list[MetricResult]) -> MetricResult:
        """合并多个 MetricResult 为一个

        Args:
            metrics: MetricResult 列表

        Returns:
            合并后的 MetricResult
        """
        if not metrics:
            return MetricResult()

        total = len(metrics)
        return MetricResult(
            f1=sum(m.f1 for m in metrics) / total,
            precision=sum(m.precision for m in metrics) / total,
            recall=sum(m.recall for m in metrics) / total,
            extracted=sum(m.extracted for m in metrics),
            expected=sum(m.expected for m in metrics),
            cases=sum(m.cases for m in metrics),
            avg_confidence=sum(m.avg_confidence for m in metrics) / total,
            time_seconds=sum(m.time_seconds for m in metrics),
        )

    def detect_regressions(
        self,
        report: EvalReport,
        history: list[Snapshot],
    ) -> list[Regression]:
        """检测回归

        Args:
            report: 当前报告
            history: 历史快照列表

        Returns:
            回归列表
        """
        if not history:
            return []

        regressions: list[Regression] = []
        last = history[-1]
        current_f1 = report.summary.overall_f1
        previous_f1 = last.metrics.get("overall_f1", 0.0)

        if previous_f1 > 0 and current_f1 < previous_f1:
            drop = previous_f1 - current_f1
            if drop >= self.config.threshold_f1_drop:
                regressions.append(
                    Regression(
                        dimension="overall",
                        previous_f1=previous_f1,
                        current_f1=current_f1,
                        drop=drop,
                        severity="critical" if drop >= 0.1 else "warning",
                    )
                )

        return regressions

    async def run_cross_language(
        self,
        categories: list[str] | None = None,
        data_dir: str | None = None,
    ) -> list[CrossLangResult]:
        """运行跨语言评估

        对比同一分类在不同语言上的表现一致性。
        一个健壮的 Agent 应在各语言上表现接近（低 F1 标准差）。

        Args:
            categories: 筛选分类
            data_dir: 数据目录

        Returns:
            跨语言评估结果列表
        """
        categories = categories or self.config.categories
        report = await self.run(
            languages=None,
            categories=categories,
            data_dir=data_dir,
        )

        results: list[CrossLangResult] = []
        for cat in report.by_category:
            lang_metrics: dict[str, MetricResult] = {}
            for lang, lang_cats in report.by_language_category.items():
                if cat in lang_cats:
                    lang_metrics[lang] = lang_cats[cat]

            if not lang_metrics:
                continue

            f1_values = [m.f1 for m in lang_metrics.values()]
            avg_f1 = sum(f1_values) / len(f1_values)
            variance = sum((f - avg_f1) ** 2 for f in f1_values) / len(f1_values)
            std_f1 = variance**0.5

            # 合并所有语言的指标
            merged = self._merge_metric_results_from_metrics(
                list(lang_metrics.values()),
            )

            results.append(
                CrossLangResult(
                    category=cat,
                    by_language=lang_metrics,
                    overall=merged,
                    std_f1=round(std_f1, 4),
                    min_f1=round(min(f1_values), 4),
                    max_f1=round(max(f1_values), 4),
                )
            )

        return results


def create_default_engine(
    agent_fn: Callable | None = None,
    reporters: list[Reporter] | None = None,
) -> EvalEngine:
    """创建默认评估引擎

    Args:
        agent_fn: Agent 函数
        reporters: 报告输出器列表

    Returns:
        评估引擎
    """
    config = EvalConfig()
    return EvalEngine(config=config, agent_fn=agent_fn, reporters=reporters)


class ABTestRunner:
    """A/B 测试运行器

    对比两种不同配置（如不同 prompt 版本、不同匹配策略）的评估结果。
    """

    def __init__(
        self,
        engine: EvalEngine,
        control_config: EvalConfig,
        experiment_config: EvalConfig,
        control_label: str = "control",
        experiment_label: str = "experiment",
    ):
        """初始化 A/B 测试运行器

        Args:
            engine: 评估引擎实例
            control_config: 对照组配置
            experiment_config: 实验组配置
            control_label: 对照组标签
            experiment_label: 实验组标签
        """
        self._engine = engine
        self._control_config = control_config
        self._experiment_config = experiment_config
        self._control_label = control_label
        self._experiment_label = experiment_label

    async def run(
        self,
        languages: list[str] | None = None,
        categories: list[str] | None = None,
        data_dir: str | None = None,
    ) -> ABTestResult:
        """运行 A/B 测试

        Args:
            languages: 筛选语言
            categories: 筛选分类
            data_dir: 数据目录

        Returns:
            A/B 测试结果
        """
        # E-B2: 通过 config 参数传递替代配置，不修改共享引擎实例
        # 使用深拷贝避免 report 持有被覆盖后的配置引用
        control_config = copy.deepcopy(self._control_config)
        experiment_config = copy.deepcopy(self._experiment_config)

        control_report = await self._engine.run(
            languages=languages,
            categories=categories,
            data_dir=data_dir,
            config=control_config,
        )

        experiment_report = await self._engine.run(
            languages=languages,
            categories=categories,
            data_dir=data_dir,
            config=experiment_config,
        )

        return ABTestResult(
            control=control_report,
            experiment=experiment_report,
            control_label=self._control_label,
            experiment_label=self._experiment_label,
        )
