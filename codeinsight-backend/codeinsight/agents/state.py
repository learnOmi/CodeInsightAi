"""
分析状态定义 (LangGraph State)

使用 LangGraph 的 TypedDict 定义知识分析工作流的状态，
支持在多个 Agent 节点之间传递和累积分析结果。
"""

from __future__ import annotations

from typing import Any

try:
    from typing import Annotated, TypedDict
except ImportError:  # pragma: no cover - Python < 3.9 compatibility shim
    from typing import Annotated  # noqa: F401

    from typing_extensions import TypedDict


def _accumulate_knowledge_points(previous: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    知识点累积函数：将新提取的知识点追加到已有结果中，按 title 去重。

    用于 LangGraph Annotated 状态字段，确保知识点在多个 Agent 节点
    之间累积而不是被覆盖。

    Args:
        previous: 已有的知识点列表
        new: 本轮分析新提取的知识点列表

    Returns:
        合并后的知识点列表
    """
    existing_titles = {p.get("title") for p in previous if p.get("title")}
    return previous + [n for n in new if n.get("title") not in existing_titles]


class AnalysisState(TypedDict):
    """
    代码知识分析状态

    在 LangGraph 工作流中，该状态在所有 Agent 节点之间共享和传递。
    每个节点读取当前状态，进行分析，并返回更新后的状态。

    Attributes:
        repo_id: 仓库唯一标识符
        ast_data: 从 Tree-sitter 解析得到的 AST 节点数据
        code_snippets: 代码片段数据，用于辅助 LLM 分析
        knowledge_points: 累积提取的知识点结果（使用 Annotated 实现追加）
        current_category: 当前分析的知识点分类（DP/AD/AL/ET/DK）
        progress: 分析进度（0.0 ~ 1.0）
        error: 分析过程中遇到的错误信息
        messages: LLM 对话历史（用于上下文记忆）
    """

    repo_id: str
    ast_data: list[dict[str, Any]]
    code_snippets: list[dict[str, Any]]
    knowledge_points: Annotated[list[dict[str, Any]], _accumulate_knowledge_points]
    current_category: str  # DP, AD, AL, ET, DK
    progress: float  # 0.0 to 1.0
    error: str | None
    messages: list[dict[str, Any]]
