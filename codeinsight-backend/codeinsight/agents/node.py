"""
分析节点定义 (LangGraph Nodes)

定义 LangGraph 工作流中的各个分析节点，每个节点负责一种类型的知识提取。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from codeinsight.agents.state import AnalysisState
from codeinsight.llm.client import LLMClient
from codeinsight.llm.errors import LLMError
from codeinsight.prompts import (
    load_algorithm_prompt,
    load_architecture_prompt,
    load_design_pattern_prompt,
    load_domain_knowledge_prompt,
    load_engineering_prompt,
)

logger = logging.getLogger(__name__)

CATEGORY_NAMES = {
    "DP": "设计模式",
    "AD": "架构设计",
    "AL": "算法实现",
    "ET": "工程技术",
    "DK": "领域知识",
}

# Maximum number of code snippets to include in context for LLM analysis
MAX_CODE_SNIPPETS = 20
MAX_CODE_CHARS_PER_SNIPPET = 1000


class AnalysisNode:
    """
    分析节点基类

    所有具体分析节点的抽象基类，定义了节点执行的基本接口。
    """

    def __init__(self, llm_client: LLMClient):
        """
        初始化分析节点

        Args:
            llm_client: LLM 客户端实例
        """
        self._llm_client = llm_client

    async def execute(self, state: AnalysisState) -> AnalysisState:
        """
        执行分析节点

        Args:
            state: 当前分析状态

        Returns:
            更新后的分析状态
        """
        raise NotImplementedError("Subclasses must implement execute method")

    def _build_messages(self, state: AnalysisState, system_prompt: str) -> list[dict[str, Any]]:
        """
        构建 LLM 对话消息列表

        Args:
            state: 当前分析状态
            system_prompt: 系统提示词

        Returns:
            消息列表
        """
        code_context = self._build_code_context(state)
        user_message = f"""请分析以下代码，提取相关的知识点：

代码上下文：
{code_context}

请按照指定的输出格式返回分析结果。"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    def _build_code_context(self, state: AnalysisState) -> str:
        """
        构建代码上下文字符串

        Args:
            state: 当前分析状态

        Returns:
            代码上下文字符串
        """
        snippets = []
        for snippet in state["code_snippets"][:MAX_CODE_SNIPPETS]:
            file_path = snippet.get("file_path", "")
            code = snippet.get("code", "")
            if code:
                truncated_code = code[:MAX_CODE_CHARS_PER_SNIPPET]
                snippets.append(f"文件: {file_path}\n{truncated_code}...")
        return "\n\n".join(snippets)

    def _parse_response(self, response: dict | Any, category: str) -> list[dict[str, Any]]:
        """
        解析 LLM 响应

        尝试将 LLM 返回的内容解析为 JSON 数组，每个元素对应一个知识点。
        如果解析失败，将原始内容作为单个知识点返回。

        Args:
            response: LLM 响应
            category: 知识点分类

        Returns:
            知识点列表
        """
        content = response.get("content", "") if isinstance(response, dict) else str(response)

        if not content:
            return []

        # Try to parse as JSON array first
        try:
            parsed_points = json.loads(content)
            if isinstance(parsed_points, list):
                return self._normalize_knowledge_points(parsed_points, category)
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: treat raw content as a single knowledge point
        return [
            {
                "category": category,
                "category_name": CATEGORY_NAMES.get(category, "未知"),
                "title": f"{CATEGORY_NAMES.get(category, '未知')}分析结果",
                "description": content,
                "confidence": 0.8,
                "tags": [],
                "code_snippets": [],
                "call_chain": [],
                "expansion": {},
                "metadata": {},
            }
        ]

    @staticmethod
    def _normalize_knowledge_points(points: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
        """
        标准化知识点格式

        确保每个知识点包含所有必需字段。

        Args:
            points: 原始知识点列表
            category: 知识点分类

        Returns:
            标准化后的知识点列表
        """
        normalized = []
        for point in points:
            if not isinstance(point, dict):
                continue
            title = point.get("title", "")
            if not title:
                title = f"{CATEGORY_NAMES.get(category, '未知')}分析结果"
            normalized.append(
                {
                    "category": category,
                    "category_name": CATEGORY_NAMES.get(category, "未知"),
                    "title": title,
                    "description": point.get("description", ""),
                    "confidence": float(point.get("confidence", 0.8)),
                    "tags": point.get("tags", []),
                    "code_snippets": point.get("code_snippets", []),
                    "call_chain": point.get("call_chain", []),
                    "expansion": point.get("expansion", {}),
                    "metadata": point.get("metadata", {}),
                }
            )
        return normalized


class DesignPatternNode(AnalysisNode):
    """
    设计模式分析节点

    从代码中识别和提取设计模式相关知识，包括模式名称、实现方式、适用场景等。
    """

    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "DP"
        logger.info("开始设计模式分析: repo_id=%s", state["repo_id"])

        try:
            prompt = load_design_pattern_prompt()
            messages = self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            state["knowledge_points"].extend(knowledge_points)
            state["current_category"] = category
            state["progress"] = 0.2

            logger.info(
                "设计模式分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

        except LLMError as exc:
            logger.error("设计模式分析失败: %s", exc)
            state["error"] = str(exc)

        return state


class ArchitectureNode(AnalysisNode):
    """
    架构设计分析节点

    分析代码的整体架构，提取架构风格、模块划分、关键组件交互等知识。
    """

    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "AD"
        logger.info("开始架构设计分析: repo_id=%s", state["repo_id"])

        try:
            prompt = load_architecture_prompt()
            messages = self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            state["knowledge_points"].extend(knowledge_points)
            state["current_category"] = category
            state["progress"] = 0.4

            logger.info(
                "架构设计分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

        except LLMError as exc:
            logger.error("架构设计分析失败: %s", exc)
            state["error"] = str(exc)

        return state


class AlgorithmNode(AnalysisNode):
    """
    算法实现分析节点

    识别代码中的算法实现，提取算法名称、时间复杂度、空间复杂度、关键逻辑等。
    """

    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "AL"
        logger.info("开始算法实现分析: repo_id=%s", state["repo_id"])

        try:
            prompt = load_algorithm_prompt()
            messages = self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            state["knowledge_points"].extend(knowledge_points)
            state["current_category"] = category
            state["progress"] = 0.6

            logger.info(
                "算法实现分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

        except LLMError as exc:
            logger.error("算法实现分析失败: %s", exc)
            state["error"] = str(exc)

        return state


class EngineeringNode(AnalysisNode):
    """
    工程技术分析节点

    分析代码的工程实践，提取代码规范、性能优化、错误处理、安全性等知识。
    """

    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "ET"
        logger.info("开始工程技术分析: repo_id=%s", state["repo_id"])

        try:
            prompt = load_engineering_prompt()
            messages = self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            state["knowledge_points"].extend(knowledge_points)
            state["current_category"] = category
            state["progress"] = 0.8

            logger.info(
                "工程技术分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

        except LLMError as exc:
            logger.error("工程技术分析失败: %s", exc)
            state["error"] = str(exc)

        return state


class DomainKnowledgeNode(AnalysisNode):
    """
    领域知识分析节点

    提取代码中的业务领域知识，包括业务规则、领域模型、业务流程等。
    """

    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "DK"
        logger.info("开始领域知识分析: repo_id=%s", state["repo_id"])

        try:
            prompt = load_domain_knowledge_prompt()
            messages = self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            state["knowledge_points"].extend(knowledge_points)
            state["current_category"] = category
            state["progress"] = 1.0

            logger.info(
                "领域知识分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

        except LLMError as exc:
            logger.error("领域知识分析失败: %s", exc)
            state["error"] = str(exc)

        return state
