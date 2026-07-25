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

    处理两种场景：
    1. 并行 fan-out：多个 Agent 节点返回各自的知识点，需要合并去重
    2. 串行更新：ExpansionNode 为已有知识点添加 expansion 字段，
       此时 new 中所有条目的 title 都已存在于 previous 中，
       应返回 new（包含更新后的数据）而不是 previous。

    Args:
        previous: 已有的知识点列表
        new: 本轮分析新提取的知识点列表

    Returns:
        合并后的知识点列表
    """
    if not new:
        return previous
    if not previous:
        return new

    existing_titles = {p.get("title") for p in previous if p.get("title")}

    # 分离出真正新增的条目（与已有条目不重复的）
    truly_new = [n for n in new if n.get("title") not in existing_titles]

    if not truly_new:
        # 所有条目都已存在 -> 这是更新操作（如 ExpansionNode 添加 expansion 字段）
        # 返回 new 以保留更新后的数据
        return new

    # 有真正新增的条目 -> 这是并行 fan-out 合并场景
    return previous + truly_new


def _keep_first(previous: Any, new: Any) -> Any:
    """保留第一个值（用于并行分支中不需要更新的字段）

    注意：TypedDict 默认空值（""、[]、{}）会被视为"未设置"，
    此时使用新值而不是默认值，确保 initial_state 传入的数据被正确保留。
    """
    # 空值（TypedDict 默认值）视为未设置，使用新值
    if previous in (None, "", [], {}, ()):
        return new
    return previous


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
        language_distribution: 语言分布信息
        file_dependencies: 文件依赖关系
        file_structure: 文件结构信息
        enable_chunking: 是否启用分片模式（用于超大代码库）
        chunk_progress: 分片处理进度（仅 enable_chunking=True 时使用）
        chunk_results: 分片处理结果（仅 enable_chunking=True 时使用）
    """

    repo_id: Annotated[str, _keep_first]
    ast_data: Annotated[list[dict[str, Any]], _keep_first]
    code_snippets: Annotated[list[dict[str, Any]], _keep_first]

    # 累积字段：使用专用 reducer
    knowledge_points: Annotated[list[dict[str, Any]], _accumulate_knowledge_points]
    current_category: Annotated[str, _keep_last]
    progress: Annotated[float, _merge_progress]
    error: Annotated[str | None, _keep_first]
    messages: Annotated[list[dict[str, Any]], _merge_messages]

    # 增强上下文字段
    language_distribution: Annotated[dict[str, int], _keep_first]
    file_dependencies: Annotated[dict[str, list[str]], _keep_first]
    file_structure: Annotated[dict[str, list[str]], _keep_first]

    # 分片模式字段（仅用于超大代码库）
    enable_chunking: Annotated[bool, _keep_first]
    chunk_progress: Annotated[dict[str, Any], _keep_first]
    chunk_results: Annotated[list[dict[str, Any]], _accumulate_knowledge_points]
