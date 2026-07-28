"""
分析节点定义 (LangGraph Nodes)

定义 LangGraph 工作流中的各个分析节点，每个节点负责一种类型的知识提取。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from codeinsight.agents.state import AnalysisState
from codeinsight.db.redis_failed_nodes import record_failed_node
from codeinsight.llm.client import LLMClient
from codeinsight.llm.errors import LLMError
from codeinsight.prompts import (
    load_algorithm_prompt,
    load_architecture_prompt,
    load_design_pattern_prompt,
    load_domain_knowledge_prompt,
    load_engineering_prompt,
    load_technology_stack_prompt,
    load_template_technique_prompt,
)
from codeinsight.schemas.constants import CATEGORY_NAMES
from codeinsight.schemas.knowledge import ExpansionContent, KnowledgePointExtraction, LearningResource

logger = logging.getLogger(__name__)

# Maximum number of code snippets to include in context for LLM analysis
MAX_CODE_SNIPPETS = 50
MAX_CODE_CHARS_PER_SNIPPET = 5000

# LLM 调用自动重试配置
MAX_LLM_RETRIES = 3
MAX_BACKOFF_SECONDS = 60

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

    async def _execute_with_retry(
        self,
        state: AnalysisState,
        category: str,
        prompt: str,
        max_retries: int = MAX_LLM_RETRIES,
    ) -> tuple[list[dict[str, Any]], float, int]:
        """
        带指数退避重试的 LLM 分析执行

        对 LLM 调用进行指数退避重试，同时记录成本估算和实际重试次数。

        Args:
            state: 当前分析状态
            category: 分析类别代码（DP/AD/AL/ET/DK/TT/TK）
            prompt: 系统提示词
            max_retries: 最大重试次数

        Returns:
            三元组 (knowledge_points, cost_estimate, attempts)

        Raises:
            LLMError: 超过重试次数后仍然失败
        """
        cost_estimate = 0.0

        for attempt in range(max_retries + 1):
            try:
                messages = await self._build_messages(state, prompt)
                response = await self._llm_client.chat(messages)
                cost_estimate = float(response.get("cost", 0.0))  # type: ignore[union-attr]
                knowledge_points = self._parse_response(response, category)
                return knowledge_points, cost_estimate, attempt + 1
            except LLMError as exc:
                if attempt < max_retries:
                    backoff = min(2**attempt, MAX_BACKOFF_SECONDS)
                    logger.warning(
                        "LLM 分析失败，指数退避 %ds 后重试（%d/%d）: category=%s, error=%s",
                        backoff,
                        attempt + 1,
                        max_retries,
                        category,
                        exc,
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise
        raise LLMError("超出重试次数")

    async def _build_messages(self, state: AnalysisState, system_prompt: str) -> list[dict[str, Any]]:
        """
        构建 LLM 对话消息列表

        在构建完成后估算 Token 数，如果超过上下文窗口的 80%，记录警告。
        加入深度挖掘指令以提升分析质量。

        Args:
            state: 当前分析状态
            system_prompt: 系统提示词

        Returns:
            消息列表
        """
        code_context = await self._build_code_context(state)

        # 根据语言分布动态注入语言特定提示
        language_hints = ""
        language_dist = state.get("language_distribution", {})
        if language_dist:
            dominant_lang = max(language_dist.items(), key=lambda item: item[1])[0]
            if dominant_lang == "python":
                language_hints = "\n注意：这是 Python 代码，请特别关注 Python 特有的模式（如装饰器、context manager、元类、异步迭代器）。"
            elif dominant_lang == "typescript":
                language_hints = "\n注意：这是 TypeScript 代码，请特别关注类型系统中的模式（如泛型、interface 实现、类型守卫、装饰器）。"
            elif dominant_lang == "java":
                language_hints = "\n注意：这是 Java 代码，请特别关注面向对象设计模式、注解处理、泛型使用。"
            elif dominant_lang == "go":
                language_hints = "\n注意：这是 Go 代码，请特别关注接口隐式实现、goroutine 并发模式、error 处理模式。"

        user_message = f"""请深入分析以下代码，提取相关的知识点：

代码上下文：
{code_context}

## 分析要求

1. **深度挖掘**：请深入分析代码结构，识别隐藏的复用模式、隐含的设计意图、以及代码中体现的架构思想。
2. **反例思考**：对每个知识点，考虑并说明"什么时候不应该使用"此模式/方法。
3. **改进建议**：如果发现代码可以改进的地方，请在知识点的描述中包含改进建议。
4. **代码关联**：每个知识点必须有具体的代码引用，不能凭空臆断。{language_hints}

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

    async def _estimate_prompt_tokens(self, system_prompt: str, state: AnalysisState) -> int:
        """
        估算 prompt 模板的 token 数（不含代码上下文）

        用于动态上下文窗口计算，提前估算 prompt 模板的 token 消耗。

        Args:
            system_prompt: 系统提示词
            state: 当前分析状态

        Returns:
            估算的 token 数
        """
        dummy_messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请深入分析以下代码，提取相关的知识点：\n\n代码上下文：\n[PLACEHOLDER]\n\n## 分析要求\n\n1. **深度挖掘**：请深入分析代码结构...\n\n请按照指定的输出格式返回分析结果。",
            },
        ]
        try:
            return await self._llm_client.count_tokens(dummy_messages)
        except Exception:
            # 估算失败时返回保守估计值
            return 3000

    async def _build_code_context(self, state: AnalysisState) -> str:
        """
        构建代码上下文字符串

        根据代码片段数量动态调整上下文大小，优先保留完整定义。
        增强内容包括文件结构信息和依赖关系。
        支持动态 token 感知裁剪，避免超出上下文窗口。

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
                # 动态 AST 节点上限，取 min(len(ast_data), 2000) 而非固定 500
                ast_limit = min(len(ast_data), 2000)
                for node in ast_data[:ast_limit]:
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

        # 构建文件依赖信息
        file_deps = state.get("file_dependencies", {})
        deps_info = ""
        if file_deps:
            dep_lines = []
            for file_path, imports in list(file_deps.items())[:20]:
                dep_lines.append(f"{file_path} 依赖: {', '.join(imports[:10])}")
            if dep_lines:
                deps_info = "文件依赖关系:\n" + "\n".join(dep_lines) + "\n\n"

        # 构建文件结构信息
        file_structure = state.get("file_structure", {})
        structure_info = ""
        if file_structure:
            structure_lines = ["项目文件结构:"]
            for root, files in list(file_structure.items())[:15]:
                structure_lines.append(f"  {root}/: {', '.join(files[:10])}")
            structure_info = "\n".join(structure_lines) + "\n\n"

        # 动态 token 感知裁剪：根据可用 token 预算动态调整 snippet 数量和大小
        max_snippets = MAX_CODE_SNIPPETS
        max_chars = MAX_CODE_CHARS_PER_SNIPPET

        # 仅在 state 中有 enable_chunking 标志时启用动态裁剪
        if state.get("enable_chunking", False):
            try:
                # 估算 prompt 模板 token 数（不含代码上下文）
                prompt_tokens = await self._estimate_prompt_tokens("", state)
                # 计算剩余可用 token（保守估计，保留 40% 给输出）
                context_window = 128_000
                available_tokens = int(context_window * 0.6) - prompt_tokens
                if available_tokens > 0:
                    # 平均每字符约 0.25 token，每个 snippet 开销约 50 token（文件名等元数据）
                    avg_chars_per_token = 4
                    snippet_overhead_tokens = 50
                    chars_budget = available_tokens * avg_chars_per_token
                    # 动态计算每个 snippet 的最大字符数
                    estimated_count = len(snippets_with_code)
                    dynamic_chars = min(
                        MAX_CODE_CHARS_PER_SNIPPET,
                        max(
                            1000,
                            chars_budget // max(estimated_count, 1) - snippet_overhead_tokens * avg_chars_per_token,
                        ),
                    )
                    max_chars = dynamic_chars
                    logger.debug(
                        "动态上下文裁剪: prompt_tokens=%d, available_tokens=%d, dynamic_chars=%d",
                        prompt_tokens,
                        available_tokens,
                        dynamic_chars,
                    )
            except Exception:
                # 动态裁剪失败时使用默认值
                pass

        snippets_list = []
        for snippet in snippets_with_code[:max_snippets]:
            file_path = snippet.get("file_path", "")
            code = snippet.get("code", "")
            if code:
                # 智能截断：优先保留 def/class/async def 的完整定义
                truncated_code = code[:max_chars]
                # 如果截断位置在函数/类定义中间，回退到上一个完整行
                last_newline = truncated_code.rfind("\n")
                if last_newline > 0:
                    truncated_code = truncated_code[:last_newline]
                snippets_list.append(f"文件: {file_path}\n{truncated_code}")

        context_parts = []
        if deps_info:
            context_parts.append(deps_info)
        if structure_info:
            context_parts.append(structure_info)
        context_parts.append("\n\n".join(snippets_list))
        return "\n\n".join(context_parts)

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

        parsed = None  # 初始化为 None，避免在 except 块中引用未赋值变量
        try:
            # 尝试修复常见 JSON 格式问题
            content = self._repair_json(content)
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
            logger.warning(
                "LLM 响应解析失败，类别=%s，错误类型：%s，内容长度=%d，前200字符: %s...",
                category,
                type(exc).__name__,
                len(content),
                content[:200],
            )

            # 只有当解析成功得到 parsed 对象时，才尝试过滤无效项目
            # 尝试逐个验证知识点（更宽松的恢复策略）：即使 JSON 解码失败但解析到部分列表也尝试
            if isinstance(parsed, list):
                valid_items = []
                valid_categories = {"DP", "AD", "AL", "ET", "DK", "TT", "TK"}
                category_mapping = {
                    "DS": "AL",
                    "SE": "ET",
                    "UI": "AD",
                    "DB": "DK",
                    "NET": "ET",
                    "SEC": "ET",
                    "PERF": "ET",
                    "OOP": "DP",
                    "ARCH": "AD",
                    "TEST": "TT",
                    "TOOL": "TK",
                    "CONFIG": "ET",
                }
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    item_copy = item.copy()
                    cat = item_copy.get("category", "")
                    if cat not in valid_categories and cat in category_mapping:
                        item_copy["category"] = category_mapping[cat]
                        cat = category_mapping[cat]
                    prefix = item_copy.get("prefix", "")
                    if prefix and not prefix.startswith(f"{cat}-"):
                        item_copy["prefix"] = f"{cat}-{prefix}"
                    try:
                        validated_item = _kp_adapter.validate_python(item_copy)
                        valid_items.append(validated_item)
                    except Exception:
                        continue
                if valid_items:
                    logger.info(
                        "LLM 响应逐项验证成功: %d/%d 个知识点通过校验",
                        len(valid_items),
                        len(parsed),
                    )
                    return self._normalize_knowledge_points(valid_items, category)  # type: ignore[arg-type]

            if parsed is not None and isinstance(parsed, list) and isinstance(exc, ValidationError):
                try:
                    valid_items = []
                    valid_categories = {"DP", "AD", "AL", "ET", "DK", "TT", "TK"}
                    # 类别码映射：将 LLM 可能返回的变体映射到有效类别
                    category_mapping = {
                        "DS": "AL",  # Data Structure → Algorithm
                        "SE": "ET",  # Software Engineering → Engineering/Tech
                        "UI": "AD",  # UI/UX → Architecture Design
                        "DB": "DK",  # Database → Domain Knowledge
                        "NET": "ET",  # Network → Engineering/Tech
                        "SEC": "ET",  # Security → Engineering/Tech
                        "PERF": "ET",  # Performance → Engineering/Tech
                        "OOP": "DP",  # OOP → Design Patterns
                        "ARCH": "AD",  # Architecture → Architecture Design
                        "TEST": "TT",  # Testing → Testing Tech
                        "TOOL": "TK",  # Tools → Technology Stack
                        "CONFIG": "ET",  # Configuration → Engineering/Tech
                    }
                    for item in parsed:
                        if isinstance(item, dict):
                            cat = item.get("category", "")
                            # 如果类别码无效，尝试映射
                            if cat not in valid_categories and cat in category_mapping:
                                item["category"] = category_mapping[cat]
                                # 同步更新 prefix
                                prefix = item.get("prefix", "")
                                if prefix and prefix.startswith(cat):
                                    item["prefix"] = prefix.replace(cat, category_mapping[cat], 1)
                                cat = category_mapping[cat]
                            if cat in valid_categories:
                                # 确保 prefix 也有效
                                prefix = item.get("prefix", "")
                                if prefix and not prefix.startswith(cat):
                                    item["prefix"] = f"{cat}-{prefix}" if not prefix.startswith(f"{cat}-") else prefix
                                valid_items.append(item)  # type: ignore[arg-type]
                    if valid_items:
                        validated = _kp_adapter.validate_python(valid_items)
                        logger.info("LLM 响应过滤后校验成功: %d/%d 个有效知识点", len(valid_items), len(parsed))
                        return self._normalize_knowledge_points(validated, category)
                except Exception:
                    pass

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
    def _repair_json(content: str) -> str:
        """修复常见 JSON 格式问题，提高 LLM 响应解析成功率"""
        try:
            # 尝试先直接解析，如果成功则无需修复
            json.loads(content)
            return content
        except json.JSONDecodeError:
            logger.debug("原始 JSON 解析失败，开始修复: %s", content[:200])
            pass

        # 0. 处理 Extra data 错误（LLM 在 JSON 对象后附加了额外文本）
        # 例如: {"a":1,"b":2}extra text → 提取 {"a":1,"b":2}
        try:
            # 找第一个 { 或 [ 和对应的最后一个 } 或 ]
            first_brace = content.find("{")
            first_bracket = content.find("[")
            start_idx = -1
            if first_brace != -1 and first_bracket != -1:
                start_idx = min(first_brace, first_bracket)
            elif first_brace != -1:
                start_idx = first_brace
            elif first_bracket != -1:
                start_idx = first_bracket

            if start_idx != -1:
                # 跳过起始符前的所有内容
                after_start = content[start_idx:]
                # 找匹配的结束符
                open_depth = 0
                end_idx = -1
                for i, ch in enumerate(after_start):
                    if ch in ("{", "["):
                        open_depth += 1
                    elif ch in ("}", "]"):
                        open_depth -= 1
                        if open_depth == 0:
                            end_idx = start_idx + i + 1
                            break
                if end_idx != -1:
                    candidate = content[start_idx:end_idx]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        # 1. 修复缺失逗号（LLM 常见问题：} { 或 ] [ 之间缺少逗号）
        try:
            # 在 } 和 { 之间、} 和 [ 之间、] 和 { 之间、] 和 [ 之间插入逗号
            fixed = re.sub(r"(\]|\})(\s*)(\[|\{)", r"\1,\2\3", content)
            json.loads(fixed)
            return fixed
        except (json.JSONDecodeError, Exception):
            pass

        # 2. 修复字符串值中未转义的双引号（LLM 最常见的问题）
        # 使用逐字符解析的方式修复
        repaired = []
        in_string = False
        i = 0
        while i < len(content):
            ch = content[i]
            if ch == "\\":
                repaired.append(ch)
                if i + 1 < len(content):
                    i += 1
                    repaired.append(content[i])
                i += 1
                continue
            if ch == '"':
                if in_string:
                    # 在字符串内部，检查是否真的是结束引号
                    # 查看前后的字符上下文
                    if i + 1 < len(content) and content[i + 1] in " \t\n\r,]}":
                        # 后面是合法的结束符，视为结束引号
                        in_string = False
                        repaired.append(ch)
                    elif i + 1 < len(content) and content[i + 1] == ":":
                        # 这是 key 的结束引号
                        in_string = False
                        repaired.append(ch)
                    else:
                        # 字符串内容中的未转义引号，转义
                        repaired.append('\\"')
                else:
                    in_string = True
                    repaired.append(ch)
            else:
                repaired.append(ch)
            i += 1

        content = "".join(repaired)

        # 2. 如果响应被截断，尝试找到最后一个完整 JSON 对象
        stripped = content.rstrip()
        open_brackets = stripped.count("[") - stripped.count("]")
        open_braces = stripped.count("{") - stripped.count("}")
        if open_brackets > 0:
            stripped += "]" * open_brackets
        if open_braces > 0:
            stripped += "}" * open_braces

        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            content = stripped

        # 3. 提取最后一个完整 JSON 对象（支持 { 和 [ 两种格式）
        try:
            brace_idx = content.rfind("}")
            bracket_idx = content.rfind("]")
            # 优先取更靠后的结束符
            end_idx = max(brace_idx, bracket_idx)
            if end_idx != -1:
                candidate = content[: end_idx + 1]
                # 找到对应的起始符
                start_char = "{" if end_idx == brace_idx else "["
                start_idx = candidate.rfind(start_char)
                if start_idx != -1:
                    candidate = candidate[start_idx : end_idx + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        # 4. 尝试提取 JSON 数组（找到第一个 [ 和最后一个 ]）
        try:
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1 and end > start:
                candidate = content[start : end + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

        # 5. 最后手段：尝试去掉所有非 JSON 字符前后的内容
        try:
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1 and end > start:
                candidate = content[start : end + 1]
                # 使用正则替换所有非 JSON 兼容的字符
                # 移除控制字符（除了 \t \n）
                candidate = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", candidate)
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

        return content

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
            knowledge_points, cost_estimate, attempts = await self._execute_with_retry(state, category, prompt)

            logger.info(
                "设计模式分析完成: repo_id=%s, extracted=%d, cost=%.4f, attempts=%d",
                state["repo_id"],
                len(knowledge_points),
                cost_estimate,
                attempts,
            )

            result = {
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.2,
                "agent_results": {
                    category: {
                        "status": "success",
                        "attempts": attempts,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "knowledge_points_count": len(knowledge_points),
                        "cost_estimate": cost_estimate,
                    }
                },
            }
            return result  # type: ignore[return-value]

        except LLMError as exc:
            repo_id = state.get("repo_id", "unknown")
            logger.error("设计模式分析失败: %s", exc)
            # 将失败节点记录到 Redis，供前端轮询显示
            try:
                record_failed_node(repo_id, category, str(exc))
            except Exception as rec_exc:
                logger.warning("记录失败节点到 Redis 失败: %s", rec_exc)
            return {  # type: ignore[typeddict-item]
                "error": str(exc),
                "agent_results": {
                    category: {
                        "status": "failed",
                        "attempts": MAX_LLM_RETRIES + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                    }
                },
            }


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
            knowledge_points, cost_estimate, attempts = await self._execute_with_retry(state, category, prompt)

            logger.info(
                "架构设计分析完成: repo_id=%s, extracted=%d, cost=%.4f, attempts=%d",
                state["repo_id"],
                len(knowledge_points),
                cost_estimate,
                attempts,
            )

            result = {
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.4,
                "agent_results": {
                    category: {
                        "status": "success",
                        "attempts": attempts,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "knowledge_points_count": len(knowledge_points),
                        "cost_estimate": cost_estimate,
                    }
                },
            }
            return result  # type: ignore[return-value]

        except LLMError as exc:
            repo_id = state.get("repo_id", "unknown")
            logger.error("架构设计分析失败: %s", exc)
            # 将失败节点记录到 Redis，供前端轮询显示
            try:
                record_failed_node(repo_id, category, str(exc))
            except Exception as rec_exc:
                logger.warning("记录失败节点到 Redis 失败: %s", rec_exc)
            return {  # type: ignore[typeddict-item]
                "error": str(exc),
                "agent_results": {
                    category: {
                        "status": "failed",
                        "attempts": MAX_LLM_RETRIES + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                    }
                },
            }


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
            knowledge_points, cost_estimate, attempts = await self._execute_with_retry(state, category, prompt)

            logger.info(
                "算法实现分析完成: repo_id=%s, extracted=%d, cost=%.4f, attempts=%d",
                state["repo_id"],
                len(knowledge_points),
                cost_estimate,
                attempts,
            )

            result = {
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.6,
                "agent_results": {
                    category: {
                        "status": "success",
                        "attempts": attempts,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "knowledge_points_count": len(knowledge_points),
                        "cost_estimate": cost_estimate,
                    }
                },
            }
            return result  # type: ignore[return-value]

        except LLMError as exc:
            repo_id = state.get("repo_id", "unknown")
            logger.error("算法实现分析失败: %s", exc)
            # 将失败节点记录到 Redis，供前端轮询显示
            try:
                record_failed_node(repo_id, category, str(exc))
            except Exception as rec_exc:
                logger.warning("记录失败节点到 Redis 失败: %s", rec_exc)
            return {  # type: ignore[typeddict-item]
                "error": str(exc),
                "agent_results": {
                    category: {
                        "status": "failed",
                        "attempts": MAX_LLM_RETRIES + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                    }
                },
            }


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
            knowledge_points, cost_estimate, attempts = await self._execute_with_retry(state, category, prompt)

            logger.info(
                "工程技术分析完成: repo_id=%s, extracted=%d, cost=%.4f, attempts=%d",
                state["repo_id"],
                len(knowledge_points),
                cost_estimate,
                attempts,
            )

            result = {
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.8,
                "agent_results": {
                    category: {
                        "status": "success",
                        "attempts": attempts,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "knowledge_points_count": len(knowledge_points),
                        "cost_estimate": cost_estimate,
                    }
                },
            }
            return result  # type: ignore[return-value]

        except LLMError as exc:
            repo_id = state.get("repo_id", "unknown")
            logger.error("工程技术分析失败: %s", exc)
            # 将失败节点记录到 Redis，供前端轮询显示
            try:
                record_failed_node(repo_id, category, str(exc))
            except Exception as rec_exc:
                logger.warning("记录失败节点到 Redis 失败: %s", rec_exc)
            return {  # type: ignore[typeddict-item]
                "error": str(exc),
                "agent_results": {
                    category: {
                        "status": "failed",
                        "attempts": MAX_LLM_RETRIES + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                    }
                },
            }


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
            knowledge_points, cost_estimate, attempts = await self._execute_with_retry(state, category, prompt)

            logger.info(
                "领域知识分析完成: repo_id=%s, extracted=%d, cost=%.4f, attempts=%d",
                state["repo_id"],
                len(knowledge_points),
                cost_estimate,
                attempts,
            )

            result = {
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 1.0,
                "agent_results": {
                    category: {
                        "status": "success",
                        "attempts": attempts,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "knowledge_points_count": len(knowledge_points),
                        "cost_estimate": cost_estimate,
                    }
                },
            }
            return result  # type: ignore[return-value]

        except LLMError as exc:
            repo_id = state.get("repo_id", "unknown")
            logger.error("领域知识分析失败: %s", exc)
            # 将失败节点记录到 Redis，供前端轮询显示
            try:
                record_failed_node(repo_id, category, str(exc))
            except Exception as rec_exc:
                logger.warning("记录失败节点到 Redis 失败: %s", rec_exc)
            return {  # type: ignore[typeddict-item]
                "error": str(exc),
                "agent_results": {
                    category: {
                        "status": "failed",
                        "attempts": MAX_LLM_RETRIES + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                    }
                },
            }


class TemplateTechniqueNode(AnalysisNode):
    """
    开发模板分析节点

    识别代码中的 CRUD 模板、API 模板、测试模板、配置模板等可复用的代码骨架模式。
    """

    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "TT"
        logger.info("开始开发模板分析: repo_id=%s", state["repo_id"])

        try:
            prompt = load_template_technique_prompt()
            knowledge_points, cost_estimate, attempts = await self._execute_with_retry(state, category, prompt)

            logger.info(
                "开发模板分析完成: repo_id=%s, extracted=%d, cost=%.4f, attempts=%d",
                state["repo_id"],
                len(knowledge_points),
                cost_estimate,
                attempts,
            )

            return {  # type: ignore[typeddict-item]
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 1.0,
                "agent_results": {
                    category: {
                        "status": "success",
                        "attempts": attempts,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "knowledge_points_count": len(knowledge_points),
                        "cost_estimate": cost_estimate,
                    }
                },
            }

        except LLMError as exc:
            repo_id = state.get("repo_id", "unknown")
            logger.error("开发模板分析失败: %s", exc)
            # 将失败节点记录到 Redis，供前端轮询显示
            try:
                record_failed_node(repo_id, category, str(exc))
            except Exception as rec_exc:
                logger.warning("记录失败节点到 Redis 失败: %s", rec_exc)
            return {  # type: ignore[typeddict-item]
                "error": str(exc),
                "agent_results": {
                    category: {
                        "status": "failed",
                        "attempts": MAX_LLM_RETRIES + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                    }
                },
            }


class TechnologyStackNode(AnalysisNode):
    """
    技术栈分析节点

    识别项目中使用的第三方库、框架、中间件及其使用方式，形成技术栈文档。
    """

    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "TK"
        logger.info("开始技术栈分析: repo_id=%s", state["repo_id"])

        try:
            prompt = load_technology_stack_prompt()
            knowledge_points, cost_estimate, attempts = await self._execute_with_retry(state, category, prompt)

            logger.info(
                "技术栈分析完成: repo_id=%s, extracted=%d, cost=%.4f, attempts=%d",
                state["repo_id"],
                len(knowledge_points),
                cost_estimate,
                attempts,
            )

            return {  # type: ignore[typeddict-item]
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 1.0,
                "agent_results": {
                    category: {
                        "status": "success",
                        "attempts": attempts,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "knowledge_points_count": len(knowledge_points),
                        "cost_estimate": cost_estimate,
                    }
                },
            }

        except LLMError as exc:
            repo_id = state.get("repo_id", "unknown")
            logger.error("技术栈分析失败: %s", exc)
            # 将失败节点记录到 Redis，供前端轮询显示
            try:
                record_failed_node(repo_id, category, str(exc))
            except Exception as rec_exc:
                logger.warning("记录失败节点到 Redis 失败: %s", rec_exc)
            return {  # type: ignore[typeddict-item]
                "error": str(exc),
                "agent_results": {
                    category: {
                        "status": "failed",
                        "attempts": MAX_LLM_RETRIES + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                    }
                },
            }


class MergeNode:
    """
    结果合并节点

    对并行执行的多个分析 Agent 的输出进行后处理：
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

        # 低置信度过滤：confidence < 0.7 的知识点跳过拓展生成
        filtered_kps = []
        skipped_count = 0
        for kp in kps:
            confidence = kp.get("confidence", 0.5)
            if confidence < 0.7:
                skipped_count += 1
                # 保留知识点但不生成拓展内容
                filtered_kps.append(kp)
            else:
                filtered_kps.append(kp)

        if skipped_count > 0:
            logger.info("低置信度知识点跳过拓展生成: %d 个 (confidence < 0.7)", skipped_count)

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
        results = await asyncio.gather(*[_process_expansion(kp) for kp in filtered_kps])

        # 用生成结果更新 knowledge_points（保留未变更的条目）
        updated_kps = []
        expansion_failed_titles = []
        for original, result in zip(filtered_kps, results, strict=True):
            if result is not None:
                updated_kps.append(result)
            else:
                updated_kps.append(original)
                expansion_failed_titles.append(original.get("title", ""))

        state["knowledge_points"] = updated_kps
        state["expansion_failures"] = expansion_failed_titles  # type: ignore[typeddict-unknown-key]
        state["progress"] = 1.0
        if expansion_failed_titles:
            logger.warning(
                "拓展内容生成完成: %d 个知识点已更新, %d 个失败: %s",
                len(updated_kps) - len(expansion_failed_titles),
                len(expansion_failed_titles),
                expansion_failed_titles[:3],
            )
        else:
            logger.info("拓展内容生成完成: %d 个知识点已更新", len(updated_kps))
        return state

    async def _generate_expansion(self, kp: dict) -> dict | None:
        """
        为单个知识点生成拓展内容（合并为 1 次 LLM 调用）

        将 5 个维度合并到一次调用中，大幅减少请求量。
        即使 JSON 部分字段无效，也尽量提取可用内容。
        """
        title = kp.get("title", "")
        # 移除 HTML 标签和特殊字符（如 <T>、<S> 等泛型标记），避免混淆 LLM
        sanitized_title = re.sub(r"<[^>]+>", "", title).strip()
        # 如果移除了泛型标记后 title 为空，保留原始 title 但转义尖括号
        if not sanitized_title:
            sanitized_title = title.replace("<", "&lt;").replace(">", "&gt;")
        category = kp.get("category_name", kp.get("category", ""))
        description = kp.get("description", "")[:500]

        prompt = (
            "请为以下知识点生成5个维度的拓展内容。\n\n"
            f"知识点标题：{sanitized_title}\n"
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
                async with self._semaphore:
                    response = await self._llm_client.chat(
                        [{"role": "user", "content": prompt}],
                        num_retries=0,  # 由本方法控制重试
                    )

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
                is_rate_limit = (
                    "rate limit" in exc_str
                    or "请求限制" in exc_str
                    or "429" in exc_str
                    or "circuit breaker" in exc_str
                    or "熔断" in exc_str
                )
                if is_rate_limit:
                    if attempt < self.MAX_RETRIES:
                        wait = 30  # 等待熔断器恢复（circuit_breaker_timeout = 30s）
                        logger.warning(
                            "拓展内容频率限制，等待 %ds 后重试: title=%s, attempt=%d",
                            wait,
                            title,
                            attempt + 1,
                        )
                        await asyncio.sleep(wait)
                        continue
                else:
                    if attempt < self.MAX_RETRIES:
                        logger.debug("拓展内容生成失败，重试: title=%s, attempt=%d", title, attempt + 1)
                        await asyncio.sleep(1)
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
        """解析合并的拓展内容 JSON，支持部分提取（处理中文标点、截断和尾随文本）

        尝试完整解析，如果失败则尝试从代码块中提取。
        如果仍然失败，手动提取可用字段，忽略非标准 JSON（如中文冒号）。
        """
        parsed: Any = None  # 缓存 json.loads 结果

        # 预处理：将中文全角冒号替换为半角冒号，修复 {"name：\"value\"} 格式
        clean_content = content.replace("：", ":").replace("\n", "")

        # 步骤 1：尝试在原始内容中匹配最外层的 JSON {}
        # 使用递归函数平衡计数法查找最外层大括号对
        outer_brace_match = self._find_outer_json_braces(clean_content)
        if outer_brace_match:
            try:
                parsed = json.loads(outer_brace_match)
                validated = self._expansion_adapter.validate_python(parsed)
                return validated.model_dump()
            except Exception:
                pass

        # 步骤 2：尝试从 Markdown 代码块中提取
        if parsed is None:
            try:
                match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", clean_content)
                if match:
                    block_content = match.group(1).strip()
                    # 去除尾注文字或冗余内容
                    json_candidate = self._extract_outer_json(block_content)
                    if json_candidate:
                        parsed = json.loads(json_candidate)
                        validated = self._expansion_adapter.validate_python(parsed)
                        return validated.model_dump()
            except Exception:
                pass

        # 步骤 3：备用方案——尝试直接从原始内容提取最外层 JSON
        if parsed is None:
            json_candidate = self._extract_outer_json(clean_content)
            if json_candidate:
                try:
                    parsed = json.loads(json_candidate)
                    validated = self._expansion_adapter.validate_python(parsed)
                    return validated.model_dump()
                except Exception:
                    pass

        # 步骤 4：手动部分提取：不依赖 Pydantic 校验，逐字段提取
        # 直接操作 cleaned_content，不再先完整解析
        try:
            result = self._manual_extract_expansion(clean_content)
            if result:
                return result
        except Exception:
            pass

        # 所有策略都失败
        logger.warning("拓展内容JSON解析全部失败，记录原始响应前2000字符: %s", content[:2000])
        return None

    def _find_outer_json_braces(self, content: str) -> str | None:
        """使用平衡计数法寻找 JSON 对象最外层的 { ... }"""
        if not content or content[0] != "{":
            return None
        depth = 0
        start = None
        for i, ch in enumerate(content):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    return content[start : i + 1]
        return None

    def _extract_outer_json(self, content: str) -> str | None:
        """从字符串中提取最外层的 JSON 对象（支持嵌套、尾部有文本的情况）"""
        content = content.strip()
        if not content.startswith("{"):
            candidate = self._find_outer_json_braces(content)
            if candidate:
                return candidate
            return None

        # 尝试直接解析（可能已经是纯净的 JSON）
        try:
            json.loads(content)
            return content
        except json.JSONDecodeError:
            pass

        # 从第一个 { 开始找到匹配的 }（考虑嵌套）
        depth = 0
        for i, ch in enumerate(content):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    return content[start : i + 1]
        return None

    def _manual_extract_expansion(self, content: str) -> dict | None:
        """从已清洗的内容中手动提取扩展内容（不依赖完整 JSON 解析）"""
        # 原则原则
        principle_match = re.search(r'"principle"\s*:\s*"((?:\\.|[^"])*)"', content, re.DOTALL)
        if principle_match:
            principle = principle_match.group(1).replace('\\"', '"')
        else:
            principle_match = re.search(r'"principle"[^:]+:\s*"([^"]+)"', content)
            principle = principle_match.group(1) if principle_match else ""

        # 适用场景列表
        applicable_scenarios = []
        scenarios_match = re.findall(r'"applicable_scenarios"\s*:\s*\[([^\]]+)\]', content)
        if scenarios_match:
            inner = scenarios_match[0].strip()
            if inner:
                # 提取每个字符串项
                scenario_items = re.findall(r'"([^"]+)"', inner)
                applicable_scenarios = [s for s in scenario_items if s]

        # 最佳实践
        best_practices = []
        practices_match = re.findall(r'"best_practices"\s*:\s*\[([^\]]+)\]', content)
        if practices_match:
            inner = practices_match[0].strip()
            if inner:
                practice_items = re.findall(r'"([^"]+)"', inner)
                best_practices = [p for p in practice_items if p]

        # 关联模式
        related_patterns = []
        patterns_match = re.findall(r'"related_patterns"\s*:\s*\[[^\]]*\]', content)
        if patterns_match:
            patterns_str = patterns_match[0]
            # 手动提取名称描述对（支持中文冒号）
            item_matches = re.findall(r"\{[^{}]*?\}", patterns_str)
            for item in item_matches:
                name_match = re.search(r'"[^"]*"[^:]*:\s*([^"]+)', item)
                if name_match:
                    related_patterns.append(name_match.group(1))
            if not related_patterns:
                # 扁平提取相关模式
                related_patterns = re.findall(r'"related_patterns"\s*:\s*\[([\s\S]*?)\]', content)
                # 这里简化处理，返回空数组（实际提取更复杂）

        # 学习资料
        learning_resources = []
        resources_match = re.findall(r'"learning_resources"\s*:\s*\[([^\]]+)\]', content)
        if resources_match:
            inner = resources_match[0].strip()
            # 提取每个资源条目（标题和URL）
            title_url_pairs = re.findall(r'"title"\s*:\s*"([^"]+)",\s*"url"\s*:\s*"([^"]+)"', inner)
            for title, url in title_url_pairs:
                learning_resources.append({"title": title, "url": url, "type": "article"})

        if principle or applicable_scenarios or best_practices or learning_resources:
            result = {}
            if principle:
                result["principle"] = principle
            if applicable_scenarios:
                result["applicable_scenarios"] = applicable_scenarios
            if best_practices:
                result["best_practices"] = best_practices
            if related_patterns:
                result["related_patterns"] = related_patterns
            if learning_resources:
                result["learning_resources"] = learning_resources

            # 验证后返回
            try:
                validated = self._expansion_adapter.validate_python(result)
                return validated.model_dump()
            except Exception:
                # Pydantic 校验失败，手动构建并返回（跳过严格检查）
                manual_result = {}
                if principle:
                    manual_result["principle"] = principle
                if applicable_scenarios:
                    manual_result["applicable_scenarios"] = applicable_scenarios
                if best_practices:
                    manual_result["best_practices"] = best_practices
                if related_patterns:
                    manual_result["related_patterns"] = related_patterns
                if learning_resources:
                    manual_result["learning_resources"] = learning_resources
                if manual_result:
                    logger.warning("扩展内容部分提取 Pydantic 校验失败，返回手动构建结果")
                    return manual_result

        return None
