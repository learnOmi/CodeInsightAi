"""
分析节点定义 (LangGraph Nodes)

定义 LangGraph 工作流中的各个分析节点，每个节点负责一种类型的知识提取。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import TypeAdapter

from codeinsight.agents.state import AnalysisState
from codeinsight.llm.client import LLMClient
from codeinsight.llm.errors import LLMError
from codeinsight.prompts import (
    load_algorithm_prompt,
    load_architecture_prompt,
    load_design_pattern_prompt,
    load_domain_knowledge_prompt,
    load_engineering_prompt,
    load_expansion_prompt,
)
from codeinsight.schemas.constants import CATEGORY_NAMES
from codeinsight.schemas.knowledge import ExpansionContent, KnowledgePointExtraction

logger = logging.getLogger(__name__)

# Maximum number of code snippets to include in context for LLM analysis
MAX_CODE_SNIPPETS = 20
MAX_CODE_CHARS_PER_SNIPPET = 1000

# Pydantic TypeAdapter for validating LLM output as a list of KnowledgePointExtraction
_kp_adapter: TypeAdapter[list[KnowledgePointExtraction]] = TypeAdapter(list[KnowledgePointExtraction])


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

    def _parse_response(self, response: Any, category: str) -> list[dict[str, Any]]:
        """
        解析 LLM 响应

        使用 Pydantic TypeAdapter 对 LLM 返回的 JSON 进行结构化校验，
        确保输出符合 KnowledgePointExtraction 格式。

        Args:
            response: LLM 响应（dict 或原始字符串）
            category: 知识点分类

        Returns:
            知识点列表（dict 格式，供 state 使用）
        """
        content = response.get("content", "") if isinstance(response, dict) else str(response)

        if not content:
            return []

        try:
            parsed = json.loads(content)
            if not isinstance(parsed, list):
                # 尝试从包装对象中提取列表
                if isinstance(parsed, dict) and "knowledge_points" in parsed:
                    parsed = parsed["knowledge_points"]
                elif isinstance(parsed, dict) and "items" in parsed:
                    parsed = parsed["items"]
                else:
                    parsed = [parsed]

            # 用 Pydantic TypeAdapter 校验
            validated = _kp_adapter.validate_python(parsed)
            return self._normalize_knowledge_points(validated, category)

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("LLM 响应解析失败: %s, 原始内容: %s...", exc, content[:200])
            # Fallback: treat raw content as a single knowledge point
            return [
                {
                    "category": category,
                    "category_name": CATEGORY_NAMES.get(category, "未知"),
                    "prefix": f"{category}-Unknown",
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
    def _normalize_knowledge_points(points: list[KnowledgePointExtraction], category: str) -> list[dict[str, Any]]:
        """
        标准化知识点格式

        将 Pydantic validated 的 KnowledgePointExtraction 对象转换为 dict 格式，
        确保包含所有必需字段。

        Args:
            points: 已验证的知识点列表
            category: 知识点分类

        Returns:
            标准化后的知识点列表（dict 格式）
        """
        normalized = []
        for point in points:
            expansion = point.expansion.model_dump() if point.expansion else {}
            normalized.append(
                {
                    "category": category,
                    "category_name": CATEGORY_NAMES.get(category, "未知"),
                    "prefix": point.prefix,
                    "title": point.title or f"{CATEGORY_NAMES.get(category, '未知')}分析结果",
                    "description": point.description,
                    "confidence": point.confidence,
                    "tags": point.tags,
                    "code_snippets": [s.model_dump() for s in point.code_snippets],
                    "call_chain": [c.model_dump() for c in point.call_chain],
                    "expansion": expansion,
                    "metadata": {},
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


class MergeNode:
    """
    结果合并节点

    对并行执行的 5 个分析 Agent 的输出进行后处理：
    1. 去重（按 title 合并相似知识点）
    2. 排序（按 confidence 降序排列）
    3. 标记冲突（同一 title 对应不同 category 的冲突）

    该节点在 fan-in 阶段执行，接收所有 Agent 的累积输出。
    """

    def __init__(self, llm_client: LLMClient):
        self._llm_client = llm_client

    async def execute(self, state: AnalysisState) -> AnalysisState:
        """执行合并后处理

        Args:
            state: 当前分析状态

        Returns:
            合并后的分析状态
        """
        kps = state.get("knowledge_points", [])

        # 1. 去重（按 title，保留置信度高的）
        seen: dict[str, dict] = {}
        for kp in kps:
            title = kp.get("title", "")
            if not title:
                continue
            if title in seen:
                # 保留置信度高的
                if kp.get("confidence", 0) > seen[title].get("confidence", 0):
                    seen[title] = kp
            else:
                seen[title] = kp

        # 2. 排序（按 confidence 降序）
        merged = sorted(seen.values(), key=lambda x: x.get("confidence", 0), reverse=True)

        state["knowledge_points"] = merged
        state["progress"] = min(state.get("progress", 0) + 0.05, 1.0)

        logger.info("合并完成: %d → %d 个知识点", len(kps), len(merged))
        return state


class ExpansionNode:
    """
    拓展内容生成节点

    为每个知识点生成拓展内容，包括：
    - 原理分析（principle）
    - 适用场景（applicable_scenarios）
    - 最佳实践（best_practices）
    - 关联模式（related_patterns）
    - 学习资源（learning_resources）

    使用 LLM 并发生成，支持结构化校验和重试机制。
    """

    _expansion_adapter: TypeAdapter[ExpansionContent] = TypeAdapter(ExpansionContent)

    MAX_RETRIES = 2
    MAX_CONCURRENCY = 5

    def __init__(self, llm_client: LLMClient):
        self._llm_client = llm_client
        self._prompt_template = load_expansion_prompt()
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENCY)

    async def execute(self, state: AnalysisState) -> AnalysisState:
        """为所有知识点生成拓展内容

        Args:
            state: 当前分析状态（已合并的知识点）

        Returns:
            更新了拓展内容后的分析状态
        """
        kps = state.get("knowledge_points", [])
        if not kps:
            state["progress"] = 1.0
            return state

        logger.info("开始生成拓展内容: %d 个知识点", len(kps))

        for kp in kps:
            try:
                expansion = await self._generate_expansion(kp)
                if expansion:
                    kp["expansion"] = expansion
            except Exception as exc:
                logger.warning(
                    "知识点拓展内容生成失败: %s, title=%s",
                    exc,
                    kp.get("title", ""),
                )

        state["progress"] = 1.0
        logger.info("拓展内容生成完成")
        return state

    async def _generate_expansion(self, kp: dict) -> dict | None:
        """为单个知识点生成拓展内容，支持重试

        Args:
            kp: 知识点

        Returns:
            拓展内容 dict，失败时返回 None
        """
        try:
            title = kp.get("title", "")
            category = kp.get("category_name", kp.get("category", ""))
            description = kp.get("description", "")

            prompt = (
                self._prompt_template.replace("{title}", title)
                .replace("{category}", category)
                .replace("{description}", description[:500])
            )

            # 简单知识点（描述短）路由到本地模型以节省成本
            # 复杂知识点（描述长）留在云端以保证质量
            task_type = "summarization" if len(description) < 200 else "default"

            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    async with self._semaphore:
                        response = await self._llm_client.chat_for_task(
                            [{"role": "user", "content": prompt}],
                            task_type=task_type,
                        )
                    content = response.get("content", "") if isinstance(response, dict) else str(response)

                    # 尝试解析并校验
                    result = await self._parse_and_validate(content)
                    if result is not None:
                        return result

                    if attempt < self.MAX_RETRIES:
                        logger.debug("拓展内容 JSON 解析失败，重试: title=%s, attempt=%d", title, attempt + 1)
                        continue
                    logger.warning("拓展内容 JSON 解析失败: title=%s", title)
                    return None

                except Exception as exc:
                    if attempt < self.MAX_RETRIES:
                        logger.debug("拓展内容生成失败，重试: title=%s, attempt=%d, error=%s", title, attempt + 1, exc)
                        await asyncio.sleep(1)
                        continue
                    logger.warning("拓展内容生成失败: title=%s, error=%s", title, exc)
                    return None

            return None
        except Exception as exc:
            logger.warning("拓展内容生成异常: title=%s, error=%s", kp.get("title", ""), exc)
            return None

    async def _parse_and_validate(self, content: str) -> dict | None:
        """解析并校验 JSON 内容

        Args:
            content: LLM 响应文本

        Returns:
            校验通过的 dict，失败时返回 None
        """
        try:
            parsed = json.loads(content)
            validated = self._expansion_adapter.validate_python(parsed)
            return validated.model_dump()
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("JSON 解析/校验失败: %s", exc)
            # 尝试从代码块中提取
            import re

            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    validated = self._expansion_adapter.validate_python(parsed)
                    return validated.model_dump()
                except Exception:
                    pass
            return None
