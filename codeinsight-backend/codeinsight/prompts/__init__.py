"""
Prompt 库模块

提供加载各种分析提示词的函数。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

PROMPT_DIR = os.path.dirname(__file__)


def _load_prompt(file_name: str) -> str:
    """
    从文件加载提示词

    Args:
        file_name: 提示词文件名

    Returns:
        提示词内容

    Raises:
        FileNotFoundError: 当提示词文件不存在时抛出
    """
    file_path = os.path.join(PROMPT_DIR, file_name)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Prompt file not found: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        return f.read()


def load_base_prompt() -> str:
    """
    加载基础提示词

    Returns:
        基础提示词内容
    """
    return _load_prompt("base.md")


def load_design_pattern_prompt() -> str:
    """
    加载设计模式分析提示词

    Returns:
        设计模式分析提示词内容
    """
    return _load_prompt("design_pattern.md")


def load_architecture_prompt() -> str:
    """
    加载架构设计分析提示词

    Returns:
        架构设计分析提示词内容
    """
    return _load_prompt("architecture.md")


def load_algorithm_prompt() -> str:
    """
    加载算法实现分析提示词

    Returns:
        算法实现分析提示词内容
    """
    return _load_prompt("algorithm.md")


def load_engineering_prompt() -> str:
    """
    加载工程技术分析提示词

    Returns:
        工程技术分析提示词内容
    """
    return _load_prompt("engineering.md")


def load_domain_knowledge_prompt() -> str:
    """
    加载领域知识分析提示词

    Returns:
        领域知识分析提示词内容
    """
    return _load_prompt("domain.md")


def load_expansion_prompt() -> str:
    """
    加载拓展内容生成提示词

    Returns:
        拓展内容生成提示词内容
    """
    return _load_prompt("expansion.md")


__all__ = [
    "load_base_prompt",
    "load_design_pattern_prompt",
    "load_architecture_prompt",
    "load_algorithm_prompt",
    "load_engineering_prompt",
    "load_domain_knowledge_prompt",
    "load_expansion_prompt",
]
