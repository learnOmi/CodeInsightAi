"""
评估模块测试

测试评估框架的评估器、指标计算、运行器、数据加载等功能。
"""

from __future__ import annotations

import json

import pytest

from codeinsight.evaluation.evaluator import (
    KnowledgePointEvaluator,
    SelfEvaluator,
)
from codeinsight.evaluation.metrics import (
    CategoryMetrics,
    EvaluationResult,
    MetricCalculator,
)
from codeinsight.evaluation.runner import (
    CATEGORY_DATA_FILES,
    DATA_DIR,
    EvaluationRunner,
    load_test_cases,
)


class TestMetricCalculator:
    """指标计算器测试"""

    def test_precision_zero_division(self):
        """精确率分母为零时返回 0.0"""
        assert MetricCalculator.calculate_precision(0, 0) == 0.0

    def test_precision_perfect(self):
        """精确率满分为 1.0"""
        assert MetricCalculator.calculate_precision(5, 0) == 1.0

    def test_precision_partial(self):
        """精确率正常计算"""
        assert MetricCalculator.calculate_precision(3, 1) == 0.75

    def test_recall_zero_division(self):
        """召回率分母为零时返回 0.0"""
        assert MetricCalculator.calculate_recall(0, 0) == 0.0

    def test_recall_perfect(self):
        """召回率满分为 1.0"""
        assert MetricCalculator.calculate_recall(5, 0) == 1.0

    def test_recall_partial(self):
        """召回率正常计算"""
        assert MetricCalculator.calculate_recall(3, 2) == 0.6

    def test_f1_zero_division(self):
        """F1 分母为零时返回 0.0"""
        assert MetricCalculator.calculate_f1(0.0, 0.0) == 0.0

    def test_f1_perfect(self):
        """F1 满分为 1.0"""
        assert MetricCalculator.calculate_f1(1.0, 1.0) == 1.0

    def test_f1_harmonic_mean(self):
        """F1 是调和平均数"""
        f1 = MetricCalculator.calculate_f1(0.8, 0.6)
        expected = 2 * 0.8 * 0.6 / (0.8 + 0.6)
        assert f1 == pytest.approx(expected, rel=1e-6)

    def test_average_confidence_empty(self):
        """空列表返回 0.0"""
        assert MetricCalculator.calculate_average_confidence([]) == 0.0

    def test_average_confidence(self):
        """平均置信度正常计算"""
        assert MetricCalculator.calculate_average_confidence([0.8, 0.9, 1.0]) == 0.9


class TestKnowledgePointEvaluator:
    """知识点评估器测试"""

    @pytest.fixture
    def evaluator(self):
        return KnowledgePointEvaluator()

    @pytest.fixture
    def sample_extracted(self):
        return [
            {"category": "DP", "title": "工厂方法模式", "confidence": 0.95},
            {"category": "DP", "title": "单例模式", "confidence": 0.9},
            {"category": "AD", "title": "MVC 架构", "confidence": 0.85},
        ]

    @pytest.fixture
    def sample_expected(self):
        return [
            {"category": "DP", "title": "工厂方法模式"},
            {"category": "DP", "title": "观察者模式"},
            {"category": "AD", "title": "MVC 架构"},
        ]

    async def test_evaluate_perfect_match(self, evaluator):
        """完全匹配时 precision/recall/F1 均为 1.0"""
        points = [{"category": "DP", "title": "测试", "confidence": 0.9}]
        result = await evaluator.evaluate("test", points, points)
        assert result.overall_precision == 1.0
        assert result.overall_recall == 1.0
        assert result.overall_f1 == 1.0

    async def test_evaluate_partial_match(self, evaluator, sample_extracted, sample_expected):
        """部分匹配时计算正确的指标"""
        result = await evaluator.evaluate("test", sample_extracted, sample_expected)
        # TP=2 (工厂方法, MVC), FP=1 (单例), FN=1 (观察者)
        assert result.overall_precision == pytest.approx(2 / 3, rel=1e-6)
        assert result.overall_recall == pytest.approx(2 / 3, rel=1e-6)
        assert result.overall_f1 == pytest.approx(2 / 3, rel=1e-6)

    async def test_evaluate_no_match(self, evaluator):
        """无匹配时所有指标为 0.0"""
        extracted = [{"category": "DP", "title": "A", "confidence": 0.9}]
        expected = [{"category": "DP", "title": "B"}]
        result = await evaluator.evaluate("test", extracted, expected)
        assert result.overall_precision == 0.0
        assert result.overall_recall == 0.0
        assert result.overall_f1 == 0.0

    async def test_evaluate_category_metrics(self, evaluator, sample_extracted, sample_expected):
        """分类指标正确计算"""
        result = await evaluator.evaluate("test", sample_extracted, sample_expected)
        assert len(result.category_metrics) == 5  # 5 个分类

        # DP: extracted=2, expected=2, TP=1, FP=1, FN=1
        dp_metrics = [m for m in result.category_metrics if m.category == "DP"][0]
        assert dp_metrics.total_extracted == 2
        assert dp_metrics.total_expected == 2
        assert dp_metrics.precision == 0.5
        assert dp_metrics.recall == 0.5

    async def test_evaluate_result_fields(self, evaluator, sample_extracted, sample_expected):
        """评估结果包含所有必要字段"""
        result = await evaluator.evaluate("test", sample_extracted, sample_expected)
        assert result.repo_id == "test"
        assert result.total_extracted == 3
        assert result.total_expected == 3
        assert result.avg_confidence == pytest.approx((0.95 + 0.9 + 0.85) / 3, rel=1e-6)
        assert result.execution_time >= 0


class TestEvaluationResult:
    """评估结果数据类测试"""

    def test_to_dict(self):
        """to_dict 返回正确格式"""
        metrics = CategoryMetrics(
            category="DP",
            category_name="设计模式",
            precision=0.8,
            recall=0.9,
            f1_score=0.85,
            total_extracted=5,
            total_expected=4,
        )
        result = EvaluationResult(
            repo_id="test",
            overall_f1=0.85,
            overall_precision=0.8,
            overall_recall=0.9,
            category_metrics=[metrics],
            total_extracted=5,
            total_expected=4,
            avg_confidence=0.85,
            execution_time=1.23,
        )
        d = result.to_dict()
        assert d["repo_id"] == "test"
        assert d["overall_f1"] == 0.85
        assert len(d["category_metrics"]) == 1
        assert d["category_metrics"][0]["category"] == "DP"


class TestDataLoader:
    """测试用例加载器测试"""

    def test_load_test_cases_all(self):
        """加载所有分类的测试用例"""
        cases = load_test_cases()
        assert len(cases) == 5
        for cat in ["DP", "AD", "AL", "ET", "DK"]:
            assert cat in cases
            assert len(cases[cat]) == 5

    def test_load_test_cases_single(self):
        """加载单个分类的测试用例"""
        cases = load_test_cases("DP")
        assert len(cases) == 1
        assert "DP" in cases
        assert len(cases["DP"]) == 5

    def test_load_test_cases_categories_present(self):
        """每个用例包含必要字段"""
        cases = load_test_cases("DP")
        for case in cases["DP"]:
            assert "id" in case
            assert "description" in case
            assert "code_snippets" in case
            assert "expected_points" in case

    def test_data_files_exist(self):
        """所有数据文件存在且合法"""
        for _cat, fname in CATEGORY_DATA_FILES.items():
            filepath = DATA_DIR / fname
            assert filepath.exists(), f"数据文件不存在: {filepath}"
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            assert "repo_id" in data
            assert "test_cases" in data
            assert len(data["test_cases"]) == 5


class TestEvaluationRunner:
    """评估运行器测试"""

    @pytest.fixture
    def runner(self):
        return EvaluationRunner()

    async def test_run_mock_returns_summary(self, runner):
        """mock 模式下返回汇总报告"""
        summary = await runner.run(category="DP")
        assert "summary" in summary
        assert "category_results" in summary
        assert summary["summary"]["categories_evaluated"] == 1
        # mock 模式返回 expected_points，precision/recall 应为 1.0
        assert summary["summary"]["overall_f1"] == 1.0

    async def test_run_mock_all_categories(self, runner):
        """mock 模式运行所有分类"""
        summary = await runner.run()
        assert summary["summary"]["categories_evaluated"] == 5
        assert summary["summary"]["overall_f1"] == 1.0

    async def test_run_with_report_file(self, runner, tmp_path):
        """运行结果写入报告文件"""
        report_file = tmp_path / "report.json"
        await runner.run(category="DP", report_file=str(report_file))
        assert report_file.exists()
        with open(report_file, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["summary"]["overall_f1"] == 1.0

    async def test_run_custom_agent(self, runner):
        """自定义 Agent 函数"""

        async def dummy_agent(code_snippets, category):
            return [{"category": category, "title": "测试", "confidence": 0.8}]

        runner._agent_fn = dummy_agent
        summary = await runner.run(category="DP")
        # dummy_agent 返回单条记录，expected_points 也是单条
        # 但 title 不同（"测试" vs "工厂方法模式"），所以 precision/recall 为 0
        assert summary["category_results"]["DP"]["precision"] == 0.0
        assert summary["category_results"]["DP"]["recall"] == 0.0


class TestSelfEvaluator:
    """自评估器测试"""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM 客户端"""
        import asyncio
        from unittest.mock import AsyncMock

        client = AsyncMock()

        async def chat(messages):
            await asyncio.sleep(0.01)
            return {"content": "0.85", "cost": 0.0}

        client.chat = chat
        return client

    async def test_self_evaluate_returns_result(self, mock_llm_client):
        """自评估返回 EvaluationResult"""
        evaluator = SelfEvaluator(mock_llm_client)
        points = [{"category": "DP", "title": "Test", "description": "desc"}]
        result = await evaluator.self_evaluate("test", points, "def foo(): pass")
        assert isinstance(result, EvaluationResult)
        assert result.avg_confidence > 0
        assert result.repo_id == "test"

    async def test_self_evaluate_confidence_range(self, mock_llm_client):
        """置信度在 0-1 范围内"""
        evaluator = SelfEvaluator(mock_llm_client)
        result = await evaluator.self_evaluate("test", [{"title": "T"}], "code")
        assert 0.0 <= result.avg_confidence <= 1.0
