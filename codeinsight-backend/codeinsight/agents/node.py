"""
分析节点定义 (LangGraph Nodes)

定义 LangGraph 工作流中的各个分析节点，每个节点负责一种类型的知识提取。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

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
from codeinsight.schemas.constants import CATEGORY_NAMES
from codeinsight.schemas.knowledge import ExpansionContent, KnowledgePointExtraction, LearningResource

logger = logging.getLogger(__name__)

# Maximum number of code snippets to include in context for LLM analysis
MAX_CODE_SNIPPETS = 20
MAX_CODE_CHARS_PER_SNIPPET = 1000

# Pydantic TypeAdapter for validating LLM output as a list of KnowledgePointExtraction
_kp_adapter: TypeAdapter[list[KnowledgePointExtraction]] = TypeAdapter(list[KnowledgePointExtraction])


# ── 拓展内容维度模型（每个维度独立、简单、容错） ──────────────────────────


class _DimensionPrinciple(BaseModel):
    """拓展内容 - 原理维度"""

    principle: str


class _DimensionScenarios(BaseModel):
    """拓展内容 - 场景维度"""

    applicable_scenarios: list[str]


class _DimensionPractices(BaseModel):
    """拓展内容 - 实践维度"""

    best_practices: list[str]


class _DimensionPatterns(BaseModel):
    """拓展内容 - 关联模式维度"""

    related_patterns: list[str]


class _DimensionResources(BaseModel):
    """拓展内容 - 学习资源维度"""

    learning_resources: list[LearningResource]


# ── 维度配置 ────────────────────────────────────────────────────────

_DIMENSION_CONFIG: dict[str, tuple[str, type[BaseModel]]] = {
    "principle": (
        "请为以下知识点生成核心原理说明。\n\n"
        "知识点标题：{title}\n"
        "知识点分类：{category}\n"
        "知识点描述：{description}\n\n"
        "请用100-200字解释该模式/技术的核心原理和技术本质，\n"
        '重点说明"为什么"而非"是什么"，揭示技术本质。\n\n'
        '仅返回JSON，格式：{{"principle": "..."}}',
        _DimensionPrinciple,
    ),
    "applicable_scenarios": (
        "请为以下知识点列出适用场景。\n\n"
        "知识点标题：{title}\n"
        "知识点分类：{category}\n"
        "知识点描述：{description}\n\n"
        "请列出3-5个具体的适用场景，每个场景20-50字。\n"
        "场景应具体，避免泛泛的描述。\n\n"
        '仅返回JSON，格式：{{"applicable_scenarios": ["..."]}}',
        _DimensionScenarios,
    ),
    "best_practices": (
        "请为以下知识点列出最佳实践建议。\n\n"
        "知识点标题：{title}\n"
        "知识点分类：{category}\n"
        "知识点描述：{description}\n\n"
        "请列出3-5条可操作的最佳实践建议，每条20-50字。\n"
        "建议应具体可操作，给出具体建议而非笼统原则。\n\n"
        '仅返回JSON，格式：{{"best_practices": ["..."]}}',
        _DimensionPractices,
    ),
    "related_patterns": (
        "请为以下知识点列出关联的技术或模式。\n\n"
        "知识点标题：{title}\n"
        "知识点分类：{category}\n"
        "知识点描述：{description}\n\n"
        "请列出3-5个关联的技术/模式，每个附带简要说明关联关系。\n"
        '需要说明关联关系（如"与XX的区别"或"XX的补充"）。\n\n'
        '仅返回JSON，格式：{{"related_patterns": ["..."]}}',
        _DimensionPatterns,
    ),
    "learning_resources": (
        "请为以下知识点推荐学习资源。\n\n"
        "知识点标题：{title}\n"
        "知识点分类：{category}\n"
        "知识点描述：{description}\n\n"
        "请推荐3-5个学习资源，每个包含title、url、type。\n"
        "type必须为book/article/video/course之一。\n"
        "url必须是真实有效的学习资源链接。\n\n"
        '仅返回JSON，格式：{{"learning_resources": [{{"title": "...", "url": "...", "type": "..."}}]}}',
        _DimensionResources,
    ),
}


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

    async def _build_messages(self, state: AnalysisState, system_prompt: str) -> list[dict[str, Any]]:
        """
        构建 LLM 对话消息列表

        在构建完成后估算 Token 数，如果超过上下文窗口的 80%，记录警告。

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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # A-D5: 使用 count_tokens() 估算总长度，超过 80% 时警告
        try:
            total_tokens = await self._llm_client.count_tokens(messages)
            # 保守估计常见模型上下文窗口为 128k tokens
            estimated_context_limit = 128_000
            usage_ratio = total_tokens / estimated_context_limit
            if usage_ratio > 0.8:
                logger.warning(
                    "LLM 请求 Token 数接近上下文窗口限制: ~%d/%d (%.0f%%), repo_id=%s",
                    total_tokens,
                    estimated_context_limit,
                    usage_ratio * 100,
                    state.get("repo_id", ""),
                )
        except Exception:
            # count_tokens 失败时静默继续
            pass

        return messages

    def _build_code_context(self, state: AnalysisState) -> str:
        """
        构建代码上下文字符串

        Args:
            state: 当前分析状态

        Returns:
            代码上下文字符串
        """
        snippets = state.get("code_snippets", [])
        if not snippets:
            # 如果 code_snippets 为空，尝试使用 ast_data 构建上下文
            ast_data = state.get("ast_data", [])
            if ast_data:
                logger.warning(
                    "code_snippets 为空，使用 ast_data 构建上下文: repo_id=%s, ast_nodes=%d",
                    state.get("repo_id", ""),
                    len(ast_data),
                )
                # 从 ast_data 构建基本的文件结构信息
                files_summary: dict[str, set[str]] = {}
                for node in ast_data[:500]:
                    file_id = node.get("file_id", "")
                    name = node.get("name", "")
                    node_type = node.get("node_type", "")
                    qualified_name = node.get("qualified_name", "")
                    if file_id:
                        if file_id not in files_summary:
                            files_summary[file_id] = set()
                        files_summary[file_id].add(f"{node_type}:{name} ({qualified_name})")

                context_parts = [f"AST 节点总数: {len(ast_data)}"]
                for fid, symbols in files_summary.items():
                    context_parts.append(f"文件 {fid}: {', '.join(list(symbols)[:20])}")
                return "\n\n".join(context_parts[:50])

            logger.warning("构建代码上下文时 code_snippets 和 ast_data 均为空: repo_id=%s", state.get("repo_id", ""))
            return ""
        snippets_with_code = [s for s in snippets if s.get("code", "")]
        if not snippets_with_code:
            logger.warning(
                "构建代码上下文时所有 snippets 的 code 字段为空: repo_id=%s, snippets_count=%d",
                state.get("repo_id", ""),
                len(snippets),
            )
            return ""
        snippets_list = []
        for snippet in snippets_with_code[:MAX_CODE_SNIPPETS]:
            file_path = snippet.get("file_path", "")
            code = snippet.get("code", "")
            if code:
                truncated_code = code[:MAX_CODE_CHARS_PER_SNIPPET]
                snippets_list.append(f"文件: {file_path}\n{truncated_code}...")
        return "\n\n".join(snippets_list)

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

        # 清理 markdown 代码块标记（如 ```json ... ```），只保留纯 JSON 内容
        content = content.strip()
        if content.startswith("```"):
            # 去掉开头的 ```json 或 ``` 等标记
            first_newline = content.find("\n")
            if first_newline != -1:
                content = content[first_newline + 1 :]
            # 去掉结尾的 ```
            if content.endswith("```"):
                content = content[:-3].strip()
            elif content.rstrip().endswith("```"):
                content = content.rstrip()[:-3].strip()

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

        except (json.JSONDecodeError, TypeError, ValidationError) as exc:
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
            # 将 CodeSnippetExtraction 转换为 dict，确保 content 字段传递
            snippets = []
            for s in point.code_snippets:
                snippet_dict = s.model_dump()
                # 将 extraction 的 file 字段映射为 file_path
                snippet_dict["file_path"] = snippet_dict.pop("file", "")
                snippets.append(snippet_dict)
            # 将 CallChainExtraction 转换为 dict，确保 name→signature 映射
            call_chain = []
            for c in point.call_chain:
                chain_dict = c.model_dump()
                # 将 extraction 的 name 字段映射为 signature
                chain_dict["signature"] = chain_dict.get("name", "")
                # 将 extraction 的 lines 转换为 tuple
                lines = chain_dict.get("lines", [])
                if lines and isinstance(lines, list):
                    if len(lines) >= 2:
                        chain_dict["lines"] = (lines[0], lines[1])
                    elif len(lines) == 1:
                        chain_dict["lines"] = (lines[0], lines[0])
                call_chain.append(chain_dict)
            normalized.append(
                {
                    "category": category,
                    "category_name": CATEGORY_NAMES.get(category, "未知"),
                    "prefix": point.prefix,
                    "title": point.title or f"{CATEGORY_NAMES.get(category, '未知')}分析结果",
                    "description": point.description,
                    "confidence": point.confidence,
                    "tags": point.tags,
                    "code_snippets": snippets,
                    "call_chain": call_chain,
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
            messages = await self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            logger.info(
                "设计模式分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

            # A-D4: 返回新字典而非原地 extend，让 LangGraph reducer 正确合并并行结果
            return {  # type: ignore[typeddict-item]
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.2,
            }

        except LLMError as exc:
            logger.error("设计模式分析失败: %s", exc)
            return {"error": str(exc)}  # type: ignore[typeddict-item]


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
            messages = await self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            logger.info(
                "架构设计分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

            # A-D4: 返回新字典而非原地 extend，让 LangGraph reducer 正确合并并行结果
            return {  # type: ignore[typeddict-item]
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.4,
            }

        except LLMError as exc:
            logger.error("架构设计分析失败: %s", exc)
            return {"error": str(exc)}  # type: ignore[typeddict-item]


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
            messages = await self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            logger.info(
                "算法实现分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

            # A-D4: 返回新字典而非原地 extend，让 LangGraph reducer 正确合并并行结果
            return {  # type: ignore[typeddict-item]
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.6,
            }

        except LLMError as exc:
            logger.error("算法实现分析失败: %s", exc)
            return {"error": str(exc)}  # type: ignore[typeddict-item]


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
            messages = await self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            logger.info(
                "工程技术分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

            # A-D4: 返回新字典而非原地 extend，让 LangGraph reducer 正确合并并行结果
            return {  # type: ignore[typeddict-item]
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.8,
            }

        except LLMError as exc:
            logger.error("工程技术分析失败: %s", exc)
            return {"error": str(exc)}  # type: ignore[typeddict-item]


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
            messages = await self._build_messages(state, prompt)

            response = await self._llm_client.chat(messages)
            knowledge_points = self._parse_response(response, category)

            logger.info(
                "领域知识分析完成: repo_id=%s, extracted=%d",
                state["repo_id"],
                len(knowledge_points),
            )

            # A-D4: 返回新字典而非原地 extend，让 LangGraph reducer 正确合并并行结果
            return {  # type: ignore[typeddict-item]
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 1.0,
            }

        except LLMError as exc:
            logger.error("领域知识分析失败: %s", exc)
            return {"error": str(exc)}  # type: ignore[typeddict-item]


class MergeNode:
    """
    结果合并节点

    对并行执行的 5 个分析 Agent 的输出进行后处理：
    1. 去重（按 title 合并相似知识点）
    2. 排序（按 confidence 降序排列）
    3. 标记冲突（同一 title 对应不同 category 的冲突）

    该节点在 fan-in 阶段执行，接收所有 Agent 的累积输出。
    """

    def __init__(self, llm_client: LLMClient | None = None):
        # A-D3: llm_client 参数已移除，保留签名兼容旧调用方
        pass

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

    每个维度独立调用 LLM，5 个维度并行执行。
    某个维度失败不影响其他维度，最终合并结果。
    """

    _expansion_adapter: TypeAdapter[ExpansionContent] = TypeAdapter(ExpansionContent)

    MAX_RETRIES = 2
    MAX_CONCURRENCY = 5

    # 限流状态（类级别，所有实例共享）
    _rate_limit_hits = 0
    _rate_limit_lock = asyncio.Lock()

    def __init__(self, llm_client: LLMClient):
        self._llm_client = llm_client
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENCY)

    async def execute(self, state: AnalysisState) -> AnalysisState:
        """为所有知识点生成拓展内容"""
        kps = state.get("knowledge_points", [])
        if not kps:
            state["progress"] = 1.0
            return state

        logger.info("开始生成拓展内容: %d 个知识点", len(kps))

        async def _process_expansion(kp: dict) -> dict | None:
            """生成单个知识点的拓展内容，返回更新后的副本"""
            try:
                expansion = await self._generate_expansion(kp)
                if expansion:
                    return {**kp, "expansion": expansion}
                return None
            except Exception as exc:
                logger.warning(
                    "知识点拓展内容生成失败: %s, title=%s",
                    exc,
                    kp.get("title", ""),
                )
                return None

        # 并发处理所有知识点，生成新列表而非原地修改
        results = await asyncio.gather(*[_process_expansion(kp) for kp in kps])

        # 用生成结果更新 knowledge_points（保留未变更的条目）
        updated_kps = []
        for original, result in zip(kps, results, strict=True):
            updated_kps.append(result if result is not None else original)

        state["knowledge_points"] = updated_kps
        state["progress"] = 1.0
        logger.info("拓展内容生成完成: %d 个知识点已更新", len(updated_kps))
        return state

    async def _generate_expansion(self, kp: dict) -> dict | None:
        """
        为单个知识点生成拓展内容（合并为 1 次 LLM 调用）

        将 5 个维度合并到一次调用中，大幅减少请求量。
        即使 JSON 部分字段无效，也尽量提取可用内容。
        """
        title = kp.get("title", "")
        category = kp.get("category_name", kp.get("category", ""))
        description = kp.get("description", "")[:500]

        prompt = (
            "请为以下知识点生成5个维度的拓展内容。\n\n"
            f"知识点标题：{title}\n"
            f"知识点分类：{category}\n"
            f"知识点描述：{description}\n\n"
            "请生成以下5个维度的内容：\n"
            "1. principle: 核心原理和技术本质（100-200字）\n"
            "2. applicable_scenarios: 适用场景列表（3-5个，每个20-50字）\n"
            "3. best_practices: 最佳实践建议（3-5条，每条20-50字）\n"
            "4. related_patterns: 关联的技术/模式（3-5个，附带简要说明）\n"
            "5. learning_resources: 学习资源推荐（3-5个，含title/url/type）\n\n"
            "仅返回JSON，不要包含任何Markdown标记或说明文字。\n"
            "格式：\n"
            "{\n"
            '  "principle": "...",\n'
            '  "applicable_scenarios": ["..."],\n'
            '  "best_practices": ["..."],\n'
            '  "related_patterns": ["..."],\n'
            '  "learning_resources": [{"title": "...", "url": "...", "type": "book|article|video|course"}]\n'
            "}"
        )

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # 限流：如果近期有频率限制命中，增加等待时间
                async with self._rate_limit_lock:
                    if self._rate_limit_hits > 0:
                        await asyncio.sleep(min(2**self._rate_limit_hits, 30))

                async with self._semaphore:
                    response = await self._llm_client.chat(
                        [{"role": "user", "content": prompt}],
                        num_retries=0,  # 由本方法控制重试
                    )

                # 成功：降低频率限制计数
                async with self._rate_limit_lock:
                    if self._rate_limit_hits > 0:
                        self._rate_limit_hits -= 1

                content = response.get("content", "") if isinstance(response, dict) else str(response)

                # 尝试解析（支持部分提取）
                result = self._parse_merged_expansion(content)
                if result is not None:
                    return result

                if attempt < self.MAX_RETRIES:
                    logger.debug("拓展内容解析失败，重试: title=%s, attempt=%d", title, attempt + 1)
                    continue
                logger.warning("拓展内容解析失败: title=%s", title)
                return None

            except LLMError as exc:
                exc_str = str(exc).lower()
                is_rate_limit = "rate limit" in exc_str or "请求限制" in exc_str or "429" in exc_str
                if is_rate_limit:
                    async with self._rate_limit_lock:
                        self._rate_limit_hits += 1
                    logger.warning("拓展内容触发频率限制: title=%s, hits=%d", title, self._rate_limit_hits)

                if attempt < self.MAX_RETRIES:
                    wait = 2 ** (attempt + 1) * (3 if is_rate_limit else 1)
                    logger.debug("拓展内容生成失败，重试: title=%s, attempt=%d, wait=%ds", title, attempt + 1, wait)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("拓展内容生成失败: title=%s, error=%s", title, exc)
                return None

            except Exception as exc:
                if attempt < self.MAX_RETRIES:
                    logger.debug("拓展内容生成异常，重试: title=%s, attempt=%d", title, attempt + 1)
                    await asyncio.sleep(1)
                    continue
                logger.warning("拓展内容生成异常: title=%s, error=%s", title, exc)
                return None

        return None

    def _parse_merged_expansion(self, content: str) -> dict | None:
        """解析合并的拓展内容 JSON，支持部分提取

        尝试完整解析，如果失败则尝试提取代码块。
        如果仍然失败，尝试提取每个字段的可用部分。
        """
        # 1. 尝试完整解析
        try:
            parsed = json.loads(content)
            validated = self._expansion_adapter.validate_python(parsed)
            return validated.model_dump()
        except Exception:
            pass

        # 2. 尝试从代码块中提取
        try:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if match:
                parsed = json.loads(match.group(1))
                validated = self._expansion_adapter.validate_python(parsed)
                return validated.model_dump()
        except Exception:
            pass

        # 3. 部分提取：收集所有可用字段
        try:
            parsed = json.loads(content)
            result: dict[str, Any] = {}
            for field in [
                "principle",
                "applicable_scenarios",
                "best_practices",
                "related_patterns",
                "learning_resources",
            ]:
                if field in parsed and parsed[field] is not None:
                    result[field] = parsed[field]
            if result:
                validated = self._expansion_adapter.validate_python(result)
                return validated.model_dump()
        except Exception:
            pass

        # 4. 从代码块中做部分提取
        try:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if match:
                parsed = json.loads(match.group(1))
                result = {}
                for field in [
                    "principle",
                    "applicable_scenarios",
                    "best_practices",
                    "related_patterns",
                    "learning_resources",
                ]:
                    if field in parsed and parsed[field] is not None:
                        result[field] = parsed[field]
                if result:
                    validated = self._expansion_adapter.validate_python(result)
                    return validated.model_dump()
        except Exception:
            pass

        return None
