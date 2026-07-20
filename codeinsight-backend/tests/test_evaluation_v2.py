"""
V2 评估组件测试

测试注册表、匹配策略、评估引擎、报告输出器的新组件。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from codeinsight.evaluation.data.registry import (
    CodeSnippet,
    EvalDataset,
    ExpectedPoint,
    TestCase,
    get_dataset,
    list_datasets,
    load_dataset_from_file,
    load_datasets_from_dir,
    register_dataset,
)
from codeinsight.evaluation.engine import (
    ABTestResult,
    ABTestRunner,
    CrossLangResult,
    EvalConfig,
    EvalEngine,
    EvalReport,
    EvalSummary,
    MetricResult,
    Regression,
    Snapshot,
)
from codeinsight.evaluation.evaluator import KnowledgePointEvaluator
from codeinsight.evaluation.matcher import (
    CategoryMatcher,
    CompositeMatcher,
    ExactTitleMatcher,
    FuzzyTitleMatcher,
    LineMatchMatcher,
    SemanticMatcher,
    create_default_matcher,
)
from codeinsight.evaluation.reporters import ConsoleReporter, JsonReporter

# ============================================================
# 注册表测试
# ============================================================


class TestEvalDataset:
    """评估数据集测试"""

    def test_create_dataset(self):
        """创建完整的数据集"""
        dataset = EvalDataset(
            dataset_id="test-dp-python-v1",
            language="python",
            category="DP",
            prompt_version="1.0.0",
            test_cases=[
                TestCase(
                    case_id="DP-PY-001",
                    description="工厂方法模式",
                    language="python",
                    category="DP",
                    code_snippets=[
                        CodeSnippet(
                            file="test.py",
                            language="python",
                            start_line=1,
                            end_line=10,
                            content="class Factory: pass",
                            highlighted_lines=[1],
                        )
                    ],
                    expected_points=[
                        ExpectedPoint(
                            category="DP",
                            prefix="DP-Factory",
                            title="工厂方法模式",
                            description="使用工厂方法",
                            confidence=0.95,
                        )
                    ],
                )
            ],
        )
        assert dataset.dataset_id == "test-dp-python-v1"
        assert len(dataset.test_cases) == 1
        assert dataset.test_cases[0].case_id == "DP-PY-001"

    def test_register_and_get(self):
        """注册和获取数据集"""
        dataset = EvalDataset(
            dataset_id="test-register",
            language="python",
            category="DP",
            prompt_version="1.0.0",
            test_cases=[],
        )
        register_dataset(dataset)
        assert get_dataset("test-register") is dataset
        assert get_dataset("non-existent") is None

    def test_list_datasets_filter(self):
        """按条件筛选数据集"""
        register_dataset(
            EvalDataset(
                dataset_id="test-list-py",
                language="python",
                category="DP",
                prompt_version="1.0.0",
                test_cases=[],
            )
        )
        register_dataset(
            EvalDataset(
                dataset_id="test-list-js",
                language="javascript",
                category="DP",
                prompt_version="1.0.0",
                test_cases=[],
            )
        )
        py_datasets = list_datasets(language="python")
        assert len(py_datasets) >= 1
        assert all(d.language == "python" for d in py_datasets)

        dp_datasets = list_datasets(category="DP")
        assert len(dp_datasets) >= 2
        assert all(d.category == "DP" for d in dp_datasets)


class TestLoadDataset:
    """数据集加载测试"""

    def test_load_from_file(self):
        """从 JSON 文件加载数据集"""
        import codeinsight.evaluation.data as data_pkg

        data_dir = Path(data_pkg.__file__).parent
        dp_file = data_dir / "design_pattern.json"
        assert dp_file.exists()

        dataset = load_dataset_from_file(dp_file)
        assert dataset is not None
        assert len(dataset.test_cases) == 5
        assert dataset.language == "python"  # 新格式有 language 字段
        assert dataset.category == "DP"

    def test_load_from_dir(self):
        """从目录加载所有数据集"""
        import codeinsight.evaluation.data as data_pkg

        data_dir = Path(data_pkg.__file__).parent
        # 只加载 JSON 文件（非 registry.py）
        datasets = load_datasets_from_dir(data_dir)
        json_files = list(data_dir.rglob("*.json"))
        assert len(datasets) == len(json_files)

    def test_load_from_file_with_language(self):
        """新格式文件包含 language 字段"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(
                {
                    "language": "python",
                    "category": "AL",
                    "prompt_version": "1.0.0",
                    "test_cases": [
                        {
                            "id": "AL-001",
                            "description": "快速排序",
                            "code_snippets": [
                                {
                                    "file": "sort.py",
                                    "content": "def quicksort: pass",
                                }
                            ],
                            "expected_points": [
                                {
                                    "category": "AL",
                                    "prefix": "AL-QuickSort",
                                    "title": "快速排序",
                                    "description": "排序算法",
                                }
                            ],
                        }
                    ],
                },
                f,
            )
            temp_path = f.name

        try:
            dataset = load_dataset_from_file(temp_path)
            assert dataset is not None
            assert dataset.language == "python"
            assert dataset.category == "AL"
            assert len(dataset.test_cases) == 1
            assert dataset.test_cases[0].language == "python"
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ============================================================
# 匹配策略测试
# ============================================================


class TestExactTitleMatcher:
    """精确标题匹配器测试"""

    @pytest.fixture
    def matcher(self):
        return ExactTitleMatcher()

    async def test_exact_match(self, matcher):
        result = await matcher.match(
            {"title": "工厂方法模式"},
            {"title": "工厂方法模式"},
        )
        assert result.is_match
        assert result.score == 1.0
        assert result.match_type == "exact"

    async def test_no_match(self, matcher):
        result = await matcher.match(
            {"title": "工厂方法模式"},
            {"title": "观察者模式"},
        )
        assert not result.is_match
        assert result.score == 0.0

    async def test_case_sensitive(self, matcher):
        result = await matcher.match(
            {"title": "Factory Method"},
            {"title": "factory method"},
        )
        assert not result.is_match


class TestFuzzyTitleMatcher:
    """模糊标题匹配器测试"""

    @pytest.fixture
    def matcher(self):
        return FuzzyTitleMatcher(threshold=0.8)

    async def test_exact_match(self, matcher):
        result = await matcher.match(
            {"title": "工厂方法模式"},
            {"title": "工厂方法模式"},
        )
        assert result.is_match
        assert result.score == 1.0
        assert result.match_type == "exact"

    async def test_fuzzy_match(self, matcher):
        result = await matcher.match(
            {"title": "工厂方法"},
            {"title": "工厂方法模式"},
        )
        assert result.is_match
        assert result.match_type == "fuzzy"
        assert 0.8 <= result.score < 1.0

    async def test_alternative_titles(self, matcher):
        result = await matcher.match(
            {"title": "Factory Method"},
            {"title": "工厂方法模式", "alternative_titles": ["Factory Method", "Factory Pattern"]},
        )
        assert result.is_match
        assert result.score == 1.0
        assert result.match_type == "exact"

    async def test_below_threshold(self, matcher):
        result = await matcher.match(
            {"title": "排序"},
            {"title": "快速排序算法"},
        )
        # "排序" vs "快速排序算法" 相似度低于 0.8
        assert not result.is_match

    async def test_empty_title(self, matcher):
        result = await matcher.match(
            {"title": ""},
            {"title": "测试"},
        )
        assert not result.is_match


class TestCategoryMatcher:
    """分类匹配器测试"""

    @pytest.fixture
    def matcher(self):
        return CategoryMatcher()

    async def test_match(self, matcher):
        result = await matcher.match(
            {"category": "DP", "title": "工厂方法"},
            {"category": "DP", "title": "工厂方法"},
        )
        assert result.is_match

    async def test_mismatch(self, matcher):
        result = await matcher.match(
            {"category": "DP", "title": "工厂方法"},
            {"category": "AD", "title": "工厂方法"},
        )
        assert not result.is_match


class TestCompositeMatcher:
    """组合匹配器测试"""

    @pytest.fixture
    def matcher(self):
        return CompositeMatcher(
            [
                ExactTitleMatcher(),
                FuzzyTitleMatcher(threshold=0.8),
            ]
        )

    async def test_category_mismatch(self, matcher):
        """分类不同则直接不匹配"""
        result = await matcher.match(
            {"category": "DP", "title": "工厂方法"},
            {"category": "AD", "title": "工厂方法"},
        )
        assert not result.is_match
        assert result.match_type == "category_mismatch"

    async def test_exact_title_match(self, matcher):
        """精确匹配优先"""
        result = await matcher.match(
            {"category": "DP", "title": "工厂方法模式"},
            {"category": "DP", "title": "工厂方法模式"},
        )
        assert result.is_match
        assert result.match_type == "exact"

    async def test_fuzzy_title_match(self, matcher):
        """精确不匹配时降级到模糊"""
        result = await matcher.match(
            {"category": "DP", "title": "工厂方法"},
            {"category": "DP", "title": "工厂方法模式"},
        )
        assert result.is_match
        assert result.match_type == "fuzzy"


class TestCreateDefaultMatcher:
    """默认匹配器创建测试"""

    def test_creates_composite(self):
        matcher = create_default_matcher()
        assert isinstance(matcher, CompositeMatcher)

    async def test_default_works(self):
        matcher = create_default_matcher()
        result = await matcher.match(
            {"category": "DP", "title": "工厂方法模式"},
            {"category": "DP", "title": "工厂方法模式"},
        )
        assert result.is_match


# ============================================================
# 评估引擎测试
# ============================================================


class TestEvalEngine:
    """评估引擎测试"""

    @pytest.fixture
    def engine(self):
        return EvalEngine(config=EvalConfig())

    async def test_run_mock_returns_report(self, engine):
        """mock 模式返回 EvalReport"""
        report = await engine.run(categories=["DP"])
        assert isinstance(report, EvalReport)
        assert isinstance(report.summary, EvalSummary)
        assert report.summary.total_test_cases > 0
        assert report.summary.overall_f1 == 1.0  # mock 模式全匹配

    async def test_run_mock_all_categories(self, engine):
        """mock 模式运行所有分类"""
        report = await engine.run()
        assert report.summary.categories_evaluated == 5
        assert report.summary.overall_f1 == 1.0

    async def test_run_filter_by_language(self, engine):
        """按语言筛选"""
        # 现有数据有 language="python"
        report = await engine.run(languages=["python"])
        assert report.summary.total_test_cases > 0

    async def test_report_by_language(self, engine):
        """报告包含按语言分组的指标"""
        report = await engine.run()
        assert isinstance(report.by_language, dict)
        if report.by_language:
            for _lang, metrics in report.by_language.items():
                assert isinstance(metrics, MetricResult)
                assert 0 <= metrics.f1 <= 1

    async def test_report_by_category(self, engine):
        """报告包含按分类分组的指标"""
        report = await engine.run()
        assert isinstance(report.by_category, dict)
        assert len(report.by_category) == 5
        for _cat, metrics in report.by_category.items():
            assert isinstance(metrics, MetricResult)
            assert metrics.f1 == 1.0  # mock 模式

    async def test_report_by_language_category(self, engine):
        """报告包含按语言×分类的交叉指标"""
        report = await engine.run()
        assert isinstance(report.by_language_category, dict)

    async def test_custom_agent_fn(self, engine):
        """自定义 Agent 函数"""

        async def dummy_agent(code_snippets, category):
            return [{"category": category, "title": "测试", "confidence": 0.8}]

        engine._agent_fn = dummy_agent
        report = await engine.run(categories=["DP"])
        # dummy_agent 返回单条，与 expected 不匹配
        assert report.by_category["DP"].precision < 1.0

    async def test_detect_regressions(self, engine):
        """回归检测"""
        report = await engine.run()

        # 无历史时不检测回归
        regressions = engine.detect_regressions(report, [])
        assert len(regressions) == 0

        # 有历史但 F1 未下降
        history = [
            Snapshot(
                timestamp="2026-01-01T00:00:00",
                prompt_version="1.0.0",
                metrics={"overall_f1": 1.0},
            )
        ]
        regressions = engine.detect_regressions(report, history)
        # 当前 F1 也是 1.0，未下降
        assert len(regressions) == 0

        # F1 下降超过阈值
        history_with_drop = [
            Snapshot(
                timestamp="2026-01-01T00:00:00",
                prompt_version="1.0.0",
                metrics={"overall_f1": 1.0},
            )
        ]
        engine.config.threshold_f1_drop = 0.01
        # 模拟 F1 下降
        report.summary.overall_f1 = 0.9
        regressions = engine.detect_regressions(report, history_with_drop)
        assert len(regressions) >= 1
        assert regressions[0].dimension == "overall"
        assert regressions[0].drop == pytest.approx(0.1, rel=1e-6)


# ============================================================
# 报告输出器测试
# ============================================================


class TestJsonReporter:
    """JSON 报告输出器测试"""

    @pytest.fixture
    def engine(self):
        return EvalEngine()

    async def test_json_reporter_output(self, engine, tmp_path):
        """JSON 报告输出到文件"""
        output_path = tmp_path / "eval_report.json"
        reporter = JsonReporter(output_path=str(output_path))
        engine._reporters = [reporter]

        await engine.run(categories=["DP"])
        assert output_path.exists()

        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "summary" in data
        assert "by_language" in data
        assert "by_category" in data
        assert data["summary"]["overall_f1"] == 1.0


class TestConsoleReporter:
    """控制台报告输出器测试"""

    async def test_console_reporter_no_error(self, engine):
        """控制台输出不报错"""
        reporter = ConsoleReporter()
        report = await engine.run(categories=["DP"])
        # 不验证输出内容，只验证不报错
        await reporter.report(report)

    @pytest.fixture
    def engine(self):
        return EvalEngine()


# ============================================================
# 指标结果测试
# ============================================================


class TestMetricResult:
    """指标结果测试"""

    def test_default_values(self):
        mr = MetricResult()
        assert mr.f1 == 0.0
        assert mr.precision == 0.0
        assert mr.recall == 0.0
        assert mr.extracted == 0
        assert mr.expected == 0
        assert mr.cases == 0
        assert mr.avg_confidence == 0.0
        assert mr.time_seconds == 0.0

    def test_custom_values(self):
        mr = MetricResult(
            f1=0.85,
            precision=0.8,
            recall=0.9,
            extracted=10,
            expected=12,
            cases=5,
            avg_confidence=0.88,
            time_seconds=3.5,
        )
        assert mr.f1 == 0.85
        assert mr.cases == 5


# ============================================================
# 回归测试
# ============================================================


class TestRegression:
    """回归检测数据类测试"""

    def test_create_regression(self):
        r = Regression(
            dimension="python.DP",
            previous_f1=0.95,
            current_f1=0.85,
            drop=0.1,
            severity="critical",
        )
        assert r.dimension == "python.DP"
        assert r.drop == 0.1
        assert r.severity == "critical"


class TestSnapshot:
    """历史快照测试"""

    def test_create_snapshot(self):
        s = Snapshot(
            timestamp="2026-01-01T00:00:00",
            prompt_version="1.0.0",
            metrics={"overall_f1": 0.95},
        )
        assert s.timestamp == "2026-01-01T00:00:00"
        assert s.metrics["overall_f1"] == 0.95


# ============================================================
# Phase 4: 高级匹配测试
# ============================================================


class TestSemanticMatcher:
    """语义匹配器测试"""

    @pytest.mark.asyncio
    async def test_match_with_embed_fn(self):
        """使用 embed_fn 匹配"""
        matcher = SemanticMatcher(
            embed_fn=lambda text: [1.0, 0.0, 0.0],
            threshold=0.8,
        )
        result = await matcher.match(
            {"title": "工厂方法", "description": "创建型设计模式"},
            {"title": "工厂方法", "description": "创建型设计模式"},
        )
        assert result.is_match
        assert result.match_type == "semantic"
        assert result.score >= 0.8

    @pytest.mark.asyncio
    async def test_no_embed_fn(self):
        """无 embed_fn 时不匹配"""
        matcher = SemanticMatcher()
        result = await matcher.match(
            {"title": "test"},
            {"title": "test"},
        )
        assert not result.is_match
        assert result.match_type == "semantic_error"

    @pytest.mark.asyncio
    async def test_empty_text(self):
        """空文本不匹配"""
        matcher = SemanticMatcher(
            embed_fn=lambda text: [1.0],
            threshold=0.5,
        )
        result = await matcher.match({}, {})
        assert not result.is_match


class TestLineMatchMatcher:
    """代码行级匹配器测试"""

    @pytest.mark.asyncio
    async def test_exact_match(self):
        """完全匹配"""
        matcher = LineMatchMatcher(iou_threshold=0.5)
        result = await matcher.match(
            {"code_lines_match": [10, 11, 12]},
            {"code_lines_match": [10, 11, 12]},
        )
        assert result.is_match
        assert result.score == 1.0
        assert result.match_type == "line_match"

    @pytest.mark.asyncio
    async def test_partial_match(self):
        """部分匹配"""
        matcher = LineMatchMatcher(iou_threshold=0.3)
        result = await matcher.match(
            {"code_lines_match": [10, 11, 12]},
            {"code_lines_match": [11, 12, 13]},
        )
        # IoU = 2/4 = 0.5
        assert result.is_match
        assert result.score == 0.5

    @pytest.mark.asyncio
    async def test_no_match(self):
        """不匹配"""
        matcher = LineMatchMatcher(iou_threshold=0.5)
        result = await matcher.match(
            {"code_lines_match": [10, 11]},
            {"code_lines_match": [20, 21]},
        )
        assert not result.is_match

    @pytest.mark.asyncio
    async def test_both_no_lines(self):
        """双方都没有行级标注视为中性"""
        matcher = LineMatchMatcher()
        result = await matcher.match({}, {})
        assert result.is_match
        assert result.match_type == "line_match_none"

    @pytest.mark.asyncio
    async def test_one_side_no_lines(self):
        """只有一方有标注"""
        matcher = LineMatchMatcher()
        result = await matcher.match(
            {"code_lines_match": [10]},
            {},
        )
        assert not result.is_match


# ============================================================
# Phase 4: 跨语言评估测试
# ============================================================


class TestCrossLanguage:
    """跨语言评估测试"""

    @pytest.mark.asyncio
    async def test_cross_lang_result_dataclass(self):
        """CrossLangResult 数据类"""
        result = CrossLangResult(
            category="DP",
            by_language={"python": MetricResult(f1=0.9), "java": MetricResult(f1=0.8)},
            overall=MetricResult(f1=0.85),
            std_f1=0.05,
            min_f1=0.8,
            max_f1=0.9,
        )
        assert result.category == "DP"
        assert result.std_f1 == 0.05
        assert result.min_f1 == 0.8

    @pytest.mark.asyncio
    async def test_run_cross_language(self):
        """运行跨语言评估"""
        engine = EvalEngine()

        with patch(
            "codeinsight.evaluation.engine.list_datasets",
            return_value=[
                EvalDataset(
                    dataset_id="dp-python-v1",
                    language="python",
                    category="DP",
                    prompt_version="1.0",
                    test_cases=[
                        TestCase(
                            case_id="DP-PY-001",
                            description="Factory Method",
                            language="python",
                            category="DP",
                            code_snippets=[],
                            expected_points=[],
                        )
                    ],
                ),
                EvalDataset(
                    dataset_id="dp-java-v1",
                    language="java",
                    category="DP",
                    prompt_version="1.0",
                    test_cases=[
                        TestCase(
                            case_id="DP-JA-001",
                            description="Factory Method",
                            language="java",
                            category="DP",
                            code_snippets=[],
                            expected_points=[],
                        )
                    ],
                ),
            ],
        ):
            results = await engine.run_cross_language(categories=["DP"])
            assert len(results) > 0
            dp_result = next(r for r in results if r.category == "DP")
            assert "python" in dp_result.by_language
            assert "java" in dp_result.by_language
            assert dp_result.std_f1 >= 0.0


# ============================================================
# Phase 4: A/B 测试
# ============================================================


class TestABTest:
    """A/B 测试"""

    def test_ab_test_result(self):
        """ABTestResult 数据类"""
        control = EvalReport(
            summary=EvalSummary(overall_f1=0.8, total_test_cases=1, total_extracted=1),
        )
        experiment = EvalReport(
            summary=EvalSummary(overall_f1=0.9, total_test_cases=1, total_extracted=1),
        )
        result = ABTestResult(
            control=control,
            experiment=experiment,
            control_label="v1",
            experiment_label="v2",
        )
        assert result.f1_diff == pytest.approx(0.1)
        assert result.is_improvement
        assert result.control_label == "v1"
        assert result.experiment_label == "v2"

    @pytest.mark.asyncio
    async def test_ab_test_runner(self):
        """ABTestRunner 运行"""
        engine = EvalEngine()
        control_config = EvalConfig(prompt_version="v1")
        experiment_config = EvalConfig(prompt_version="v2")

        runner = ABTestRunner(
            engine=engine,
            control_config=control_config,
            experiment_config=experiment_config,
        )

        with patch(
            "codeinsight.evaluation.engine.list_datasets",
            return_value=[
                EvalDataset(
                    dataset_id="test-v1",
                    language="python",
                    category="DP",
                    prompt_version="1.0",
                    test_cases=[
                        TestCase(
                            case_id="DP-001",
                            description="test",
                            language="python",
                            category="DP",
                            code_snippets=[],
                            expected_points=[],
                        )
                    ],
                ),
            ],
        ):
            result = await runner.run(categories=["DP"])
            assert isinstance(result, ABTestResult)
            assert result.control.summary.overall_f1 >= 0.0
            assert result.experiment.summary.overall_f1 >= 0.0


# ============================================================
# Phase 4: 评估器匹配策略测试
# ============================================================


class TestEvaluatorWithMatcher:
    """评估器使用匹配策略测试"""

    @pytest.mark.asyncio
    async def test_evaluator_with_custom_matcher(self):
        """使用自定义匹配策略"""
        evaluator = KnowledgePointEvaluator(
            matcher=FuzzyTitleMatcher(threshold=0.6),
        )
        result = await evaluator.evaluate(
            repo_id="test",
            extracted_points=[
                {"category": "DP", "title": "Factory Pattern"},
            ],
            expected_points=[
                {"category": "DP", "title": "Factory Method Pattern", "alternative_titles": []},
            ],
        )
        # FuzzyTitleMatcher with threshold 0.6 should match "Factory Pattern" ≈ "Factory Method Pattern"
        assert result.overall_f1 > 0.0

    @pytest.mark.asyncio
    async def test_evaluator_exact_matcher(self):
        """精确匹配器"""
        evaluator = KnowledgePointEvaluator(
            matcher=ExactTitleMatcher(),
        )
        result = await evaluator.evaluate(
            repo_id="test",
            extracted_points=[
                {"category": "DP", "title": "Factory Method"},
            ],
            expected_points=[
                {"category": "DP", "title": "Factory Method"},
            ],
        )
        assert result.overall_f1 == 1.0

    @pytest.mark.asyncio
    async def test_evaluator_matcher_no_match(self):
        """匹配器不匹配"""
        evaluator = KnowledgePointEvaluator(
            matcher=ExactTitleMatcher(),
        )
        result = await evaluator.evaluate(
            repo_id="test",
            extracted_points=[
                {"category": "DP", "title": "Wrong Title"},
            ],
            expected_points=[
                {"category": "DP", "title": "Expected Title"},
            ],
        )
        assert result.overall_f1 == 0.0
