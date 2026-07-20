"""
分析状态定义 (LangGraph State)

使用 LangGraph 的 TypedDict 定义知识分析工作流的状态。
所有字段均使用 Annotated reducer 以支持并行 fan-out 执行。
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


def _keep_first(previous: Any, new: Any) -> Any:
    """保留第一个值（用于并行分支中不需要更新的字段）"""
    return previous if previous is not None else new


def _keep_last(previous: Any, new: Any) -> Any:
    """保留最后一个值（用于并行分支中需要覆盖的字段）"""
    return new


def _merge_progress(previous: float, new: float) -> float:
    """合并并行分支的 progress（取最大值）"""
    return max(previous, new)


def _merge_messages(previous: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并消息列表（按 role+content 去重）"""
    if not previous:
        return new
    existing = {(m.get("role", ""), m.get("content", "") or "") for m in previous}
    merged = list(previous)
    for m in new:
        key = (m.get("role", ""), m.get("content", "") or "")
        if key not in existing:
            existing.add(key)
            merged.append(m)
    return merged


class AnalysisState(TypedDict):
    """
    代码知识分析状态

    在 LangGraph 工作流中，该状态在所有 Agent 节点之间共享和传递。
    所有字段使用 Annotated reducer 以支持并行 fan-out 执行。

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

    repo_id: Annotated[str, _keep_first]
    ast_data: Annotated[list[dict[str, Any]], _keep_first]
    code_snippets: Annotated[list[dict[str, Any]], _keep_first]
    knowledge_points: Annotated[list[dict[str, Any]], _accumulate_knowledge_points]
    current_category: Annotated[str, _keep_last]
    progress: Annotated[float, _merge_progress]
    error: Annotated[str | None, _keep_first]
    messages: Annotated[list[dict[str, Any]], _merge_messages]
