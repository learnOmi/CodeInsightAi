"""
分析图定义 (LangGraph Graph)

使用 LangGraph 定义完整的代码知识分析工作流，采用 fan-out/fan-in 并行架构：
所有分析节点并行执行，结果汇聚到合并节点进行去重和排序，
再进入 ExpansionNode 生成拓展内容。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from codeinsight.agents.node import (
    AlgorithmNode,
    ArchitectureNode,
    DesignPatternNode,
    DomainKnowledgeNode,
    EngineeringNode,
    ExpansionNode,
    MergeNode,
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

# 评估分类代码 → 图节点名称映射
CATEGORY_TO_NODE: dict[str, str] = {
    "DP": "design_pattern",
    "AD": "architecture",
    "AL": "algorithm",
    "ET": "engineering",
    "DK": "domain_knowledge",
}


def _route_to_agents(state: AnalysisState) -> list[Send]:
    """扇形分发到所有分析 Agent（并行执行）

    使用 LangGraph Send API 将当前状态复制并发送到每个分析节点，
    所有节点并行执行，结果通过 StateGraph 的 reducer 自动合并。

    如果 state 中指定了 category，只路由到对应的分析节点（评估场景优化）。

    Args:
        state: 当前分析状态

    Returns:
        Send 对象列表，每个对象包含目标节点名和状态拷贝
    """
    category = state.get("current_category", "")
    if category and category in CATEGORY_TO_NODE:
        node_name = CATEGORY_TO_NODE[category]
        return [Send(node_name, state)]

    # A-D2: category 未匹配时记录警告
    if category and category not in CATEGORY_TO_NODE:
        logger.warning("未知分类 '%s'，回退到全部分类路由", category)

    # A-E2: 从 ANALYSIS_NODES 推导，避免硬编码重复
    agent_names = [name for name, _ in ANALYSIS_NODES]
    return [Send(name, state) for name in agent_names]


def _route_to_expansion(state: AnalysisState) -> str:
    """合并节点后路由到拓展节点或结束

    如果合并后的知识点不为空，进入 ExpansionNode；
    否则直接结束。

    Args:
        state: 合并后的分析状态

    Returns:
        目标节点名
    """
    if state.get("knowledge_points"):
        return "expansion"
    return END


ANALYSIS_TIMEOUT = 300.0  # 分析图超时时间（秒）


async def _run_with_timeout(graph, state, timeout=ANALYSIS_TIMEOUT):
    """带超时的分析图执行"""
    return await asyncio.wait_for(graph.ainvoke(state), timeout=timeout)


ANALYSIS_TIMEOUT = 300.0  # 分析图执行超时时间（秒）


class AnalysisGraph:
    """
    代码知识分析图（并行版本）

    使用 LangGraph 构建的 fan-out/fan-in 有向无环图：
    1. 入口 → 扇形分发到 5 个分析节点（并行执行）
    2. 所有分析节点汇聚到合并节点（去重 + 排序）
    3. 合并后进入拓展节点（生成拓展内容）
    4. 最终结束

    相比线性版本，并行架构将分析耗时从 N 次 LLM 调用降低到 1 次。
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

        创建 fan-out/fan-in 有向无环图：
        - 并行：所有分析节点同时执行
        - 汇聚：合并节点处理并行结果
        - 串行：拓展节点在合并后执行

        Returns:
            构建完成的 StateGraph 实例
        """
        workflow = StateGraph(AnalysisState)

        # 创建节点实例
        design_pattern_node = DesignPatternNode(self._llm_client)
        architecture_node = ArchitectureNode(self._llm_client)
        algorithm_node = AlgorithmNode(self._llm_client)
        engineering_node = EngineeringNode(self._llm_client)
        domain_knowledge_node = DomainKnowledgeNode(self._llm_client)
        merge_node = MergeNode(self._llm_client)
        expansion_node = ExpansionNode(self._llm_client)

        # 注册节点
        workflow.add_node("design_pattern", design_pattern_node.execute)
        workflow.add_node("architecture", architecture_node.execute)
        workflow.add_node("algorithm", algorithm_node.execute)
        workflow.add_node("engineering", engineering_node.execute)
        workflow.add_node("domain_knowledge", domain_knowledge_node.execute)
        workflow.add_node("merge", merge_node.execute)
        workflow.add_node("expansion", expansion_node.execute)

        # 入口 → 扇形分发到所有分析 Agent
        workflow.add_conditional_edges("__start__", _route_to_agents)

        # 所有 Agent 汇聚到合并节点
        for name, _ in ANALYSIS_NODES:
            workflow.add_edge(name, "merge")

        # 合并 → 扩展 → 结束
        workflow.add_conditional_edges("merge", _route_to_expansion)
        workflow.add_edge("expansion", END)

        logger.info("并行分析图构建完成，包含 %d 个分析节点 + merge + expansion", len(ANALYSIS_NODES))
        return workflow.compile()

    async def run(self, initial_state: AnalysisState) -> AnalysisState:
        """
        运行分析图

        从入口节点开始执行整个分析工作流，所有分析节点并行执行，
        最终返回包含所有知识点的完整状态。

        Args:
            initial_state: 初始状态

        Returns:
            最终分析状态

        Raises:
            Exception: 严重错误时抛出
        """
        logger.info("开始执行并行分析图: repo_id=%s", initial_state["repo_id"])

        try:
            # A-D1: 添加超时保护，避免 LLM 卡住时无限期阻塞
            final_state = cast(
                AnalysisState,
                await asyncio.wait_for(
                    self._graph.ainvoke(initial_state),
                    timeout=ANALYSIS_TIMEOUT,
                ),
            )

            logger.info(
                "并行分析图执行完成: repo_id=%s, knowledge_points=%d, progress=%.2f",
                final_state["repo_id"],
                len(final_state["knowledge_points"]),
                final_state["progress"],
            )

            return final_state

        except TimeoutError:
            logger.error("分析图执行超时: repo_id=%s, timeout=%.0fs", initial_state["repo_id"], ANALYSIS_TIMEOUT)
            raise
        except Exception as exc:
            error_msg = f"并行分析图执行失败: {exc}"
            logger.error(error_msg, exc_info=True)
            raise

    def get_graph_info(self) -> dict[str, Any]:
        """
        获取分析图信息

        Returns:
            图信息字典
        """
        return {
            "nodes": [{"id": node_id, "name": name} for node_id, name in ANALYSIS_NODES]
            + [
                {"id": "merge", "name": "结果合并"},
                {"id": "expansion", "name": "拓展内容生成"},
            ],
            "edges": [{"from": "entry", "to": node_id, "type": "parallel"} for node_id, _ in ANALYSIS_NODES]
            + [{"from": node_id, "to": "merge", "type": "converge"} for node_id, _ in ANALYSIS_NODES]
            + [
                {"from": "merge", "to": "expansion", "type": "conditional"},
                {"from": "expansion", "to": "END", "type": "direct"},
            ],
            "entry_point": "fan-out to all agents",
            "total_nodes": len(ANALYSIS_NODES) + 2,
        }

    @staticmethod
    def create_initial_state(
        repo_id: str,
        ast_data: list[dict[str, Any]],
        code_snippets: list[dict[str, Any]],
        category: str = "",
    ) -> AnalysisState:
        """
        创建初始分析状态

        Args:
            repo_id: 仓库唯一标识符
            ast_data: AST 节点数据列表
            code_snippets: 代码片段数据列表
            category: 评估分类代码（可选），指定后只路由到对应分析节点

        Returns:
            初始分析状态
        """
        return {
            "repo_id": repo_id,
            "ast_data": ast_data,
            "code_snippets": code_snippets,
            "knowledge_points": [],
            "current_category": category,
            "progress": 0.0,
            "error": None,
            "messages": [],
        }
