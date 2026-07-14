"""
分析图定义 (LangGraph Graph)

使用 LangGraph 定义完整的代码知识分析工作流，连接各个分析节点。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from langgraph.graph import END, StateGraph

from codeinsight.agents.node import (
    AlgorithmNode,
    ArchitectureNode,
    DesignPatternNode,
    DomainKnowledgeNode,
    EngineeringNode,
)
from codeinsight.agents.state import AnalysisState
from codeinsight.llm.client import LLMClient

logger = logging.getLogger(__name__)

ANALYSIS_NODES = [
    ("design_pattern", "设计模式分析"),
    ("architecture", "架构设计分析"),
    ("algorithm", "算法实现分析"),
    ("engineering", "工程技术分析"),
    ("domain_knowledge", "领域知识分析"),
]


class AnalysisGraph:
    """
    代码知识分析图

    使用 LangGraph 构建的有向无环图，依次执行五种类型的知识分析节点，
    最终生成完整的代码知识图谱。
    """

    def __init__(self, llm_client: LLMClient):
        """
        初始化分析图

        Args:
            llm_client: LLM 客户端实例，将被注入到所有分析节点中
        """
        self._llm_client = llm_client
        self._graph: Any = self._build_graph()

    def _build_graph(self) -> Any:
        """
        构建 LangGraph 状态图

        创建一个有向无环图，按顺序连接所有分析节点：
        设计模式 -> 架构设计 -> 算法实现 -> 工程技术 -> 领域知识 -> END

        Returns:
            构建完成的 StateGraph 实例
        """
        workflow = StateGraph(AnalysisState)

        design_pattern_node = DesignPatternNode(self._llm_client)
        architecture_node = ArchitectureNode(self._llm_client)
        algorithm_node = AlgorithmNode(self._llm_client)
        engineering_node = EngineeringNode(self._llm_client)
        domain_knowledge_node = DomainKnowledgeNode(self._llm_client)

        workflow.add_node("design_pattern", design_pattern_node.execute)
        workflow.add_node("architecture", architecture_node.execute)
        workflow.add_node("algorithm", algorithm_node.execute)
        workflow.add_node("engineering", engineering_node.execute)
        workflow.add_node("domain_knowledge", domain_knowledge_node.execute)

        workflow.set_entry_point("design_pattern")

        workflow.add_edge("design_pattern", "architecture")
        workflow.add_edge("architecture", "algorithm")
        workflow.add_edge("algorithm", "engineering")
        workflow.add_edge("engineering", "domain_knowledge")
        workflow.add_edge("domain_knowledge", END)

        logger.info("分析图构建完成，包含 %d 个节点", len(ANALYSIS_NODES))
        return workflow.compile()

    async def run(self, initial_state: AnalysisState) -> AnalysisState:
        """
        运行分析图

        从入口节点开始执行整个分析工作流，依次经过所有分析节点，
        最终返回包含所有知识点的完整状态。

        Args:
            initial_state: 初始状态，包含 repo_id、ast_data 和 code_snippets

        Returns:
            最终分析状态，包含累积的知识点和进度信息

        Raises:
            Exception: 当分析过程中发生严重错误时抛出
        """
        logger.info("开始执行分析图: repo_id=%s", initial_state["repo_id"])

        try:
            final_state = cast(AnalysisState, await self._graph.ainvoke(initial_state))

            logger.info(
                "分析图执行完成: repo_id=%s, knowledge_points=%d, progress=%.2f",
                final_state["repo_id"],
                len(final_state["knowledge_points"]),
                final_state["progress"],
            )

            return final_state

        except Exception as exc:
            error_msg = f"分析图执行失败: {exc}"
            logger.error(error_msg, exc_info=True)
            raise

    def get_graph_info(self) -> dict[str, Any]:
        """
        获取分析图信息

        返回图的结构信息，包括节点列表、边关系等。

        Returns:
            图信息字典
        """
        return {
            "nodes": [{"id": node_id, "name": name} for node_id, name in ANALYSIS_NODES],
            "edges": [
                {"from": "design_pattern", "to": "architecture"},
                {"from": "architecture", "to": "algorithm"},
                {"from": "algorithm", "to": "engineering"},
                {"from": "engineering", "to": "domain_knowledge"},
                {"from": "domain_knowledge", "to": "END"},
            ],
            "entry_point": "design_pattern",
            "total_nodes": len(ANALYSIS_NODES),
        }

    @staticmethod
    def create_initial_state(
        repo_id: str,
        ast_data: list[dict[str, Any]],
        code_snippets: list[dict[str, Any]],
    ) -> AnalysisState:
        """
        创建初始分析状态

        根据仓库 ID、AST 数据和代码片段构建初始状态对象。

        Args:
            repo_id: 仓库唯一标识符
            ast_data: AST 节点数据列表
            code_snippets: 代码片段数据列表

        Returns:
            初始分析状态
        """
        return {
            "repo_id": repo_id,
            "ast_data": ast_data,
            "code_snippets": code_snippets,
            "knowledge_points": [],
            "current_category": "",
            "progress": 0.0,
            "error": None,
            "messages": [],
        }
