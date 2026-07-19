"""
AgentBridge 单元测试

测试 AgentBridge 的 mock 模式和配置功能。
由于真实 LLM 调用需要网络，使用 mock LLMClient。
"""

from __future__ import annotations

import asyncio

import pytest

from codeinsight.evaluation.agent_bridge import AgentBridge, EvalAgentConfig
from codeinsight.evaluation.data.registry import CodeSnippet, ExpectedPoint, TestCase


class MockLLMClient:
    """Mock LLM 客户端，不发起真实调用"""

    def __init__(self):
        self.chat_calls = 0

    async def chat(self, messages, **kwargs):
        """Mock chat 返回空响应"""
        self.chat_calls += 1
        return {"content": "", "model": "mock"}


class TestEvalAgentConfig:
    """EvalAgentConfig 测试"""

    def test_default_max_cases(self):
        """默认 max_cases=1"""
        llm = MockLLMClient()
        config = EvalAgentConfig(llm_client=llm)
        assert config.max_cases == 1

    def test_custom_max_cases(self):
        """自定义 max_cases"""
        llm = MockLLMClient()
        config = EvalAgentConfig(llm_client=llm, max_cases=5)
        assert config.max_cases == 5

    def test_verbose_config(self):
        """verbose 配置"""
        llm = MockLLMClient()
        config = EvalAgentConfig(llm_client=llm, verbose=True)
        assert config.verbose is True


class TestAgentBridge:
    """AgentBridge 测试"""

    @pytest.fixture
    def llm_client(self):
        return MockLLMClient()

    @pytest.fixture
    def test_case(self):
        """创建标准测试用例"""
        return TestCase(
            case_id="DP-PY-TEST-001",
            description="测试用例",
            language="python",
            category="DP",
            code_snippets=[
                CodeSnippet(
                    file="test.py",
                    language="python",
                    start_line=1,
                    end_line=10,
                    content="def hello(): pass",
                    highlighted_lines=[1],
                )
            ],
            expected_points=[
                ExpectedPoint(
                    category="DP",
                    prefix="DP-Test",
                    title="测试模式",
                    description="测试描述",
                    confidence=0.9,
                )
            ],
        )

    def test_prompt_version(self, llm_client):
        """prompt_version 正确计算"""
        config = EvalAgentConfig(llm_client=llm_client)
        bridge = AgentBridge(config)
        assert bridge.prompt_version.startswith("v1.0.0-")

    def test_cases_processed_initial(self, llm_client):
        """初始 cases_processed 为 0"""
        config = EvalAgentConfig(llm_client=llm_client)
        bridge = AgentBridge(config)
        assert bridge.cases_processed == 0

    def test_max_cases_limit(self, llm_client, test_case):
        """max_cases 限制"""
        config = EvalAgentConfig(llm_client=llm_client, max_cases=1)
        bridge = AgentBridge(config)

        async def run():
            # 第 1 个用例正常执行
            await bridge.extract(test_case)
            assert bridge.cases_processed == 1

            # 第 2 个用例应被跳过
            result2 = await bridge.extract(test_case)
            assert len(result2) == 0  # 超出限制返回空列表

        asyncio.run(run())

    def test_build_ast_data(self, llm_client):
        """AST 数据构建"""
        config = EvalAgentConfig(llm_client=llm_client)
        bridge = AgentBridge(config)

        snippets = [
            CodeSnippet(
                file="src/main.py",
                language="python",
                start_line=1,
                end_line=10,
                content="def func(): pass",
                highlighted_lines=[1],
            )
        ]

        ast_data = bridge._build_ast_data(snippets, "python")
        assert len(ast_data) == 1
        assert ast_data[0]["node_type"] == "file"
        assert ast_data[0]["language"] == "python"
        assert ast_data[0]["start_line"] == 1

    def test_build_ast_data_go_language(self, llm_client):
        """Go 语言 AST 数据构建"""
        config = EvalAgentConfig(llm_client=llm_client)
        bridge = AgentBridge(config)

        snippets = [
            CodeSnippet(
                file="main.go",
                language="go",
                start_line=1,
                end_line=20,
                content="func main() {}",
                highlighted_lines=[1],
            )
        ]

        ast_data = bridge._build_ast_data(snippets, "go")
        assert ast_data[0]["node_type"] == "file"

    def test_build_ast_data_java_script(self, llm_client):
        """JavaScript 语言 AST 数据构建"""
        config = EvalAgentConfig(llm_client=llm_client)
        bridge = AgentBridge(config)

        snippets = [
            CodeSnippet(
                file="app.js",
                language="javascript",
                start_line=1,
                end_line=10,
                content="function hello() {}",
                highlighted_lines=[1],
            )
        ]

        ast_data = bridge._build_ast_data(snippets, "javascript")
        assert ast_data[0]["node_type"] == "script"

    async def test_extract_batch_respects_max_cases(self, llm_client, test_case):
        """extract_batch 尊重 max_cases 限制"""
        config = EvalAgentConfig(llm_client=llm_client, max_cases=1)
        bridge = AgentBridge(config)

        cases = [test_case, test_case, test_case]
        results = await bridge.extract_batch(cases)
        # 只处理 1 个用例
        assert len(results) == 1
        assert bridge.cases_processed == 1

    async def test_extract_batch_exception_handling(self, llm_client, test_case):
        """extract_batch 异常处理"""
        config = EvalAgentConfig(llm_client=llm_client, max_cases=1)
        bridge = AgentBridge(config)

        async def failing_extract(case):
            raise RuntimeError("Mock failure")

        bridge.extract = failing_extract

        results = await bridge.extract_batch([test_case])
        # 异常被捕获，返回空列表
        assert len(results) == 1
        assert results[0][1] == []  # 空知识点列表


class TestPromptRegistryIntegration:
    """PromptRegistry 与 AgentBridge 集成测试"""

    @pytest.fixture
    def llm_client(self):
        return MockLLMClient()

    def test_registry_scan_on_init(self, llm_client):
        """初始化时自动扫描 PromptRegistry"""
        config = EvalAgentConfig(llm_client=llm_client)
        bridge = AgentBridge(config)

        # prompt_version 应包含哈希
        assert "-" in bridge.prompt_version
        assert len(bridge.prompt_version) > 5
