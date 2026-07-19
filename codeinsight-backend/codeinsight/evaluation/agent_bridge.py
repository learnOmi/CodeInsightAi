"""
Agent 桥接层

将评估框架与真实分析管线连接，支持以下模式：
- Mock 模式（默认）：用标准答案作为提取结果，F1 恒为 1.0
- Agent 模式：运行真实 LLM 分析，计算真实 F1

AgentBridge 将测试用例（CodeSnippet + 语言信息）转换为 AnalysisGraph 可执行的输入，
并提取结果标准化为 EvalEngine 期望的 dict 格式。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from codeinsight.agents.graph import AnalysisGraph
from codeinsight.evaluation.data.registry import CodeSnippet, TestCase
from codeinsight.evaluation.prompt_registry import PromptRegistry
from codeinsight.llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class EvalAgentConfig:
    """Agent 评估配置"""

    llm_client: LLMClient
    max_cases: int = 1  # 限制评估用例数，控制成本
    prompt_registry: PromptRegistry | None = None
    verbose: bool = False


class AgentBridge:
    """Agent 桥接器

    将 TestCase 转换为 AnalysisGraph 输入，执行 LLM 分析并返回标准化结果。

    使用方式：
        config = EvalAgentConfig(llm_client=LLMClient())
        bridge = AgentBridge(config)
        points = await bridge.extract(case)
    """

    def __init__(self, config: EvalAgentConfig) -> None:
        """初始化桥接器

        Args:
            config: 评估 Agent 配置
        """
        self._config = config
        self._llm_client = config.llm_client
        self._prompt_registry = config.prompt_registry or PromptRegistry()
        self._cases_processed = 0
        self._prompt_version = ""
        self._graph: AnalysisGraph | None = None

        # 计算 Prompt 版本
        self._prompt_registry.scan()
        self._prompt_version = self._prompt_registry.compute_version()
        logger.info("AgentBridge 初始化完成: prompt_version=%s", self._prompt_version)

    @property
    def _compiled_graph(self) -> AnalysisGraph:
        """惰性初始化 AnalysisGraph（单次 compile，复用）"""
        if self._graph is None:
            self._graph = AnalysisGraph(self._llm_client)
        return self._graph

    @property
    def prompt_version(self) -> str:
        """获取当前 Prompt 版本标识"""
        return self._prompt_version

    @property
    def cases_processed(self) -> int:
        """已处理的测试用例数"""
        return self._cases_processed

    async def extract(self, test_case: TestCase) -> list[dict[str, Any]]:
        """对单个测试用例执行 LLM 分析

        Args:
            test_case: 评估测试用例

        Returns:
            提取的知识点列表（标准化为 dict 格式）
        """
        self._cases_processed += 1

        logger.info(
            "AgentBridge.extract: case_id=%s, language=%s, category=%s, case %d",
            test_case.case_id,
            test_case.language,
            test_case.category,
            self._cases_processed,
        )

        # 检查是否超出最大用例数限制
        if self._config.max_cases > 0 and self._cases_processed > self._config.max_cases:
            logger.warning("已达到最大用例数限制 (%d)，跳过后续用例", self._config.max_cases)
            return []

        # 构建 AST 数据（从代码片段生成简化 AST）
        ast_data = self._build_ast_data(test_case.code_snippets, test_case.language)

        # 构建代码片段
        code_snippets = [{"file_path": cs.file, "code": cs.content} for cs in test_case.code_snippets]

        # 创建初始状态（传入 category 以限制只运行相关分析节点）
        initial_state = AnalysisGraph.create_initial_state(
            repo_id=test_case.case_id,
            ast_data=ast_data,
            code_snippets=code_snippets,
            category=test_case.category,
        )

        # 运行 AnalysisGraph（复用缓存的已 compile 实例）
        final_state = await self._compiled_graph.run(initial_state)

        # 提取知识点
        raw_points = final_state.get("knowledge_points", [])
        if not raw_points:
            logger.warning("AgentBridge: 未提取到知识点, case_id=%s", test_case.case_id)

        # 标准化为 EvalEngine 期望的 dict 格式
        points = []
        for kp in raw_points:
            point = {
                "category": kp.get("category", ""),
                "prefix": "",
                "title": kp.get("title", ""),
                "description": kp.get("description", ""),
                "confidence": kp.get("confidence", 0.5),
                "alternative_titles": [],
            }
            points.append(point)

        logger.info(
            "AgentBridge.extract 完成: case_id=%s, extracted_points=%d",
            test_case.case_id,
            len(points),
        )

        if self._config.verbose:
            for p in points:
                logger.info("  - [%s] %s: %s", p["category"], p["title"], p["description"][:50])

        return points

    def _build_ast_data(self, code_snippets: list[CodeSnippet], language: str) -> list[dict[str, Any]]:
        """从代码片段构建简化 AST 数据

        由于评估测试用例不包含真实仓库的完整 AST，
        这里从代码片段的文件路径和语言信息构建简化 AST 节点，
        供 LLM 参考代码结构。

        Args:
            code_snippets: 代码片段列表
            language: 编程语言

        Returns:
            AST 节点数据列表
        """
        ast_data: list[dict[str, Any]] = []

        for i, cs in enumerate(code_snippets):
            # 从文件名提取类/函数名（简化处理）
            file_name = cs.file.replace("/", "_").replace("\\", "_")
            node_type = "file" if language in ("python", "java", "go") else "script"

            ast_data.append(
                {
                    "id": str(i),
                    "node_type": node_type,
                    "name": file_name,
                    "file_id": str(i),
                    "start_line": cs.start_line,
                    "end_line": cs.end_line,
                    "qualified_name": file_name,
                    "language": language,
                }
            )

        return ast_data

    async def extract_batch(self, test_cases: list[TestCase]) -> list[tuple[TestCase, list[dict[str, Any]]]]:
        """批量处理多个测试用例

        Args:
            test_cases: 测试用例列表

        Returns:
            (TestCase, 提取知识点) 元组列表
        """
        results: list[tuple[TestCase, list[dict[str, Any]]]] = []

        for case in test_cases:
            if self._config.max_cases > 0 and self._cases_processed >= self._config.max_cases:
                logger.info("批量处理提前终止: 已达到最大用例数 (%d)", self._config.max_cases)
                break

            try:
                points = await self.extract(case)
                results.append((case, points))
            except Exception as exc:  # noqa: BLE001 - 评估时捕获所有异常继续处理
                logger.error("AgentBridge.extract 失败: case_id=%s, error=%s", case.case_id, exc)
                results.append((case, []))

        return results
