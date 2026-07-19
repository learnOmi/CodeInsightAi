"""
Agent 模块单元测试（P3-02）

测试 LangGraph 工作流的状态管理、节点执行、图编排和结构化输出解析。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from codeinsight.agents.graph import AnalysisGraph
from codeinsight.agents.node import (
    AlgorithmNode,
    AnalysisNode,
    ArchitectureNode,
    DesignPatternNode,
    DomainKnowledgeNode,
    EngineeringNode,
    ExpansionNode,
    MergeNode,
    _kp_adapter,
)
from codeinsight.agents.state import (
    AnalysisState,
    _accumulate_knowledge_points,
    _keep_first,
    _keep_last,
    _merge_messages,
)
from codeinsight.llm.client import LLMClient
from codeinsight.schemas.knowledge import (
    KnowledgePointExtraction,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def llm_client() -> LLMClient:
    config = MagicMock()
    config.provider = "claude"
    config.model = "claude-3.5-sonnet-20241022"
    config.api_key = "test-key"
    config.temperature = 0.1
    config.max_tokens = 4096
    config.num_retries = 1
    config.request_timeout = 30.0
    config.embedding_timeout = 30.0
    config.embedding_model = "text-embedding-3-small"
    config.max_concurrency = 3
    client = LLMClient(config)
    return client


@pytest.fixture
def sample_state() -> AnalysisState:
    return {
        "repo_id": "test-repo-uuid",
        "ast_data": [
            {
                "id": "node-1",
                "node_type": "class",
                "name": "OrderService",
                "file_id": "file-1",
                "start_line": 1,
                "end_line": 50,
                "qualified_name": "app.services.OrderService",
            }
        ],
        "code_snippets": [
            {
                "file_path": "app/services/order.py",
                "code": "class OrderService:\n    def create_order(self):\n        pass",
            }
        ],
        "knowledge_points": [],
        "current_category": "",
        "progress": 0.0,
        "error": None,
        "messages": [],
    }


# ============================================================
# Test: State
# ============================================================


class TestAnalysisState:
    """状态管理测试"""

    def test_create_initial_state(self, sample_state):
        """创建初始状态"""
        state = AnalysisGraph.create_initial_state(
            repo_id="test-repo-uuid",
            ast_data=[{"id": "node-1"}],
            code_snippets=[{"file_path": "test.py", "code": "print('hello')"}],
        )
        assert state["repo_id"] == "test-repo-uuid"
        assert state["ast_data"] == [{"id": "node-1"}]
        assert state["code_snippets"] == [{"file_path": "test.py", "code": "print('hello')"}]
        assert state["knowledge_points"] == []
        assert state["current_category"] == ""
        assert state["progress"] == 0.0
        assert state["error"] is None
        assert state["messages"] == []

    def test_accumulate_knowledge_points_dedup(self):
        """知识点按 title 去重"""
        previous = [
            {"title": "Factory Pattern", "category": "DP"},
            {"title": "Singleton Pattern", "category": "DP"},
        ]
        new = [
            {"title": "Factory Pattern", "category": "DP"},  # 重复
            {"title": "Observer Pattern", "category": "DP"},  # 新
        ]
        result = _accumulate_knowledge_points(previous, new)
        assert len(result) == 3
        titles = [p["title"] for p in result]
        assert titles == ["Factory Pattern", "Singleton Pattern", "Observer Pattern"]

    def test_accumulate_knowledge_points_empty_previous(self):
        """空已有列表时全部追加"""
        new = [{"title": "A", "category": "DP"}, {"title": "B", "category": "DP"}]
        result = _accumulate_knowledge_points([], new)
        assert len(result) == 2

    def test_accumulate_knowledge_points_empty_new(self):
        """空新列表时返回已有列表"""
        previous = [{"title": "A", "category": "DP"}]
        result = _accumulate_knowledge_points(previous, [])
        assert len(result) == 1

    def test_keep_first_with_none_previous(self):
        """_keep_first: previous 为 None 时返回 new"""
        assert _keep_first(None, "new_value") == "new_value"

    def test_keep_first_with_value(self):
        """_keep_first: previous 有值时返回 previous"""
        assert _keep_first("old", "new") == "old"

    def test_keep_last(self):
        """_keep_last 始终返回 new"""
        assert _keep_last("old", "new") == "new"

    def test_merge_messages_empty_previous(self):
        """_merge_messages: 空已有列表时返回 new"""
        result = _merge_messages([], [{"role": "user", "content": "hi"}])
        assert len(result) == 1

    def test_merge_messages_dedup(self):
        """_merge_messages: 按 role+content 去重"""
        previous = [{"role": "user", "content": "hi"}]
        new = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = _merge_messages(previous, new)
        assert len(result) == 2


# ============================================================
# Test: KnowledgePointExtraction Schema
# ============================================================


class TestKnowledgePointExtraction:
    """结构化输出解析测试"""

    def test_valid_extraction(self):
        """有效知识点解析"""
        data = {
            "category": "DP",
            "prefix": "DP-Factory",
            "title": "工厂方法模式",
            "description": "定义创建对象的接口",
            "confidence": 0.92,
            "code_snippets": [
                {
                    "file": "app/factory.py",
                    "start_line": 1,
                    "end_line": 20,
                    "content": "class Factory:",
                    "highlighted_lines": [5],
                }
            ],
            "tags": ["factory", "creation"],
        }
        kp = KnowledgePointExtraction(**data)
        assert kp.category == "DP"
        assert kp.title == "工厂方法模式"
        assert kp.confidence == 0.92
        assert len(kp.code_snippets) == 1
        assert kp.code_snippets[0].file == "app/factory.py"

    def test_minimal_extraction(self):
        """最小字段知识点的默认值"""
        data = {"category": "DP", "prefix": "DP-Test", "title": "Test", "description": "Test"}
        kp = KnowledgePointExtraction(**data)
        assert kp.confidence == 0.8  # 默认值
        assert kp.code_snippets == []
        assert kp.tags == []

    def test_type_adapter_list(self):
        """TypeAdapter 解析列表"""
        data = [
            {"category": "DP", "prefix": "DP-A", "title": "A", "description": "Desc A"},
            {"category": "AD", "prefix": "AD-B", "title": "B", "description": "Desc B"},
        ]
        result = _kp_adapter.validate_python(data)
        assert len(result) == 2
        assert result[0].category == "DP"
        assert result[1].category == "AD"

    def test_type_adapter_invalid_missing_required(self):
        """TypeAdapter 校验缺失必填字段"""
        with pytest.raises(ValidationError):
            _kp_adapter.validate_python([{"category": "DP"}])  # 缺少 title/description/prefix

    # ============================================================
    # P3-05: 边界校验测试
    # ============================================================

    def test_invalid_confidence_above_range(self):
        """置信度超过 1.0 应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP",
                prefix="DP-Factory",
                title="Test",
                description="Test",
                confidence=1.5,
            )

    def test_invalid_confidence_below_range(self):
        """置信度低于 0.0 应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP",
                prefix="DP-Factory",
                title="Test",
                description="Test",
                confidence=-0.1,
            )

    def test_invalid_category_format(self):
        """category 格式错误应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP-",  # 不应包含 -
                prefix="DP-Factory",
                title="Test",
                description="Test",
            )

    def test_invalid_prefix_format(self):
        """prefix 格式错误应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP",
                prefix="InvalidPrefix",  # 缺少 category- 前缀
                title="Test",
                description="Test",
            )

    def test_empty_title(self):
        """空 title 应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP",
                prefix="DP-Factory",
                title="",
                description="Test",
            )

    def test_empty_description(self):
        """空 description 应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP",
                prefix="DP-Factory",
                title="Test",
                description="",
            )

    def test_code_snippet_negative_line(self):
        """负行号应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP",
                prefix="DP-Factory",
                title="Test",
                description="Test",
                code_snippets=[
                    {
                        "file": "test.py",
                        "start_line": -1,
                        "end_line": 10,
                        "content": "code",
                    }
                ],
            )

    def test_call_chain_node_type_invalid(self):
        """无效的 node_type 应拒绝"""
        with pytest.raises(ValidationError):
            KnowledgePointExtraction(
                category="DP",
                prefix="DP-Factory",
                title="Test",
                description="Test",
                call_chain=[
                    {
                        "node_id": "n1",
                        "node_type": "invalid_type",  # 不在 Literal 中
                        "file": "test.py",
                        "name": "test",
                    }
                ],
            )


# ============================================================
# Test: Node
# ============================================================


class TestAnalysisNode:
    """节点基类测试"""

    def test_execute_not_implemented(self, llm_client):
        """基类 execute 抛出 NotImplementedError"""
        node = AnalysisNode(llm_client)
        with pytest.raises(NotImplementedError):
            import asyncio

            asyncio.run(node.execute({}))  # type: ignore[arg-type]

    def test_build_code_context(self, sample_state):
        """构建代码上下文"""
        node = AnalysisNode(MagicMock())
        context = node._build_code_context(sample_state)
        assert "app/services/order.py" in context
        assert "OrderService" in context

    def test_build_code_context_empty(self):
        """空片段时返回空字符串"""
        node = AnalysisNode(MagicMock())
        context = node._build_code_context({"code_snippets": []})  # type: ignore[typeddict-item]
        assert context == ""


class TestDesignPatternNode:
    """设计模式节点测试"""

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_state):
        """成功执行"""
        llm_client = MagicMock(spec=LLMClient)
        mock_response = {
            "content": '[{"category": "DP", "prefix": "DP-Factory", "title": "工厂模式", "description": "test", "confidence": 0.9}]'
        }
        llm_client.chat = AsyncMock(return_value=mock_response)

        node = DesignPatternNode(llm_client)
        result = await node.execute(sample_state)

        assert len(result["knowledge_points"]) == 1
        assert result["knowledge_points"][0]["title"] == "工厂模式"
        assert result["current_category"] == "DP"
        assert result["progress"] == 0.2

    @pytest.mark.asyncio
    async def test_execute_llm_error(self, sample_state):
        """LLM 错误时记录 error"""
        llm_client = MagicMock(spec=LLMClient)
        from codeinsight.llm.errors import LLMError

        llm_client.chat = AsyncMock(side_effect=LLMError("API Error"))

        node = DesignPatternNode(llm_client)
        result = await node.execute(sample_state)

        assert "API Error" in (result["error"] or "")

    @pytest.mark.asyncio
    async def test_execute_empty_response(self, sample_state):
        """空响应时返回空列表"""
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(return_value={"content": ""})
        node = DesignPatternNode(llm_client)
        result = await node.execute(sample_state)
        assert len(result["knowledge_points"]) == 0


class TestArchitectureNode:
    """架构节点测试"""

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_state):
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(
            return_value={
                "content": '[{"category": "AD", "prefix": "AD-MVC", "title": "MVC架构", "description": "test", "confidence": 0.85}]'
            }
        )
        node = ArchitectureNode(llm_client)
        result = await node.execute(sample_state)
        assert len(result["knowledge_points"]) == 1
        assert result["progress"] == 0.4


class TestAlgorithmNode:
    """算法节点测试"""

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_state):
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(
            return_value={
                "content": '[{"category": "AL", "prefix": "AL-QuickSort", "title": "快速排序", "description": "test", "confidence": 0.9}]'
            }
        )
        node = AlgorithmNode(llm_client)
        result = await node.execute(sample_state)
        assert len(result["knowledge_points"]) == 1
        assert result["progress"] == 0.6


class TestEngineeringNode:
    """工程节点测试"""

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_state):
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(
            return_value={
                "content": '[{"category": "ET", "prefix": "ET-Retry", "title": "重试模式", "description": "test", "confidence": 0.88}]'
            }
        )
        node = EngineeringNode(llm_client)
        result = await node.execute(sample_state)
        assert len(result["knowledge_points"]) == 1
        assert result["progress"] == 0.8


class TestDomainKnowledgeNode:
    """领域知识节点测试"""

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_state):
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(
            return_value={
                "content": '[{"category": "DK", "prefix": "DK-Order", "title": "订单模型", "description": "test", "confidence": 0.9}]'
            }
        )
        node = DomainKnowledgeNode(llm_client)
        result = await node.execute(sample_state)
        assert len(result["knowledge_points"]) == 1
        assert result["progress"] == 1.0


# ============================================================
# Test: Graph
# ============================================================


class TestAnalysisGraph:
    """图编排测试"""

    def test_create_graph(self, llm_client):
        """创建分析图"""
        graph = AnalysisGraph(llm_client)
        assert graph._graph is not None

    def test_get_graph_info(self, llm_client):
        """获取图信息（并行版本含 7 个节点：5 分析 + merge + expansion）"""
        graph = AnalysisGraph(llm_client)
        info = graph.get_graph_info()
        assert len(info["nodes"]) == 7
        assert info["entry_point"] == "fan-out to all agents"
        assert info["edges"][0] == {"from": "entry", "to": "design_pattern", "type": "parallel"}
        assert info["edges"][-1] == {"from": "expansion", "to": "END", "type": "direct"}

    @pytest.mark.asyncio
    async def test_run_success(self, llm_client):
        """运行分析图（并行版本）"""
        # 5 个 Agent 各返回 1 个知识点
        agent_responses = [
            {"content": '[{"category": "DP", "prefix": "DP-Test", "title": "Test", "description": "test"}]'},
            {"content": '[{"category": "AD", "prefix": "AD-Test", "title": "Arch", "description": "test"}]'},
            {"content": '[{"category": "AL", "prefix": "AL-Test", "title": "Algo", "description": "test"}]'},
            {"content": '[{"category": "ET", "prefix": "ET-Test", "title": "Eng", "description": "test"}]'},
            {"content": '[{"category": "DK", "prefix": "DK-Test", "title": "Domain", "description": "test"}]'},
        ]
        # ExpansionNode 为每个知识点生成拓展内容
        expansion_response = {
            "content": '{"principle": "test", "applicable_scenarios": ["s1"], "best_practices": ["p1"], "related_patterns": ["r1"], "learning_resources": ["l1"]}'
        }

        call_count = 0

        async def mock_chat(messages, **kwargs):
            nonlocal call_count
            resp = agent_responses[call_count] if call_count < 5 else expansion_response
            call_count += 1
            return resp

        llm_client.chat = mock_chat

        graph = AnalysisGraph(llm_client)
        initial_state = AnalysisGraph.create_initial_state(
            repo_id="test-repo-uuid",
            ast_data=[{"id": "node-1", "node_type": "class", "name": "Test"}],
            code_snippets=[{"file_path": "test.py", "code": "pass"}],
        )
        result = await graph.run(initial_state)
        assert len(result["knowledge_points"]) == 5
        assert result["progress"] == 1.0

    @pytest.mark.asyncio
    async def test_run_node_error_propagates(self, llm_client):
        """节点内部异常（非 LLMError）传播到 run() 调用方"""
        call_count = 0

        async def mock_chat(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise Exception("Error")
            return {"content": "[]"}

        llm_client.chat = mock_chat

        graph = AnalysisGraph(llm_client)
        initial_state = AnalysisGraph.create_initial_state(
            repo_id="test-repo-uuid",
            ast_data=[],
            code_snippets=[],
        )
        with pytest.raises(Exception, match="Error"):
            await graph.run(initial_state)

    @pytest.mark.asyncio
    async def test_run_empty_data(self, llm_client):
        """空数据时正常运行（无知识点 → 跳过 ExpansionNode）"""
        call_count = 0

        async def mock_chat(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"content": "[]"}

        llm_client.chat = mock_chat

        graph = AnalysisGraph(llm_client)
        initial_state = AnalysisGraph.create_initial_state(repo_id="test-repo-uuid", ast_data=[], code_snippets=[])
        result = await graph.run(initial_state)
        assert len(result["knowledge_points"]) == 0
        assert result["progress"] == 1.0
        assert call_count == 5  # 5 个 Agent，无知识点 → 跳过 ExpansionNode


# ============================================================
# Test: Parse Response
# ============================================================


class TestMergeNode:
    """合并节点测试"""

    @pytest.mark.asyncio
    async def test_dedup_by_title(self):
        """按 title 去重"""
        state: AnalysisState = {
            "repo_id": "test",
            "ast_data": [],
            "code_snippets": [],
            "knowledge_points": [
                {"title": "A", "confidence": 0.9},
                {"title": "A", "confidence": 0.95},  # 重复，保留高置信度
                {"title": "B", "confidence": 0.8},
            ],
            "current_category": "",
            "progress": 0.5,
            "error": None,
            "messages": [],
        }
        node = MergeNode(MagicMock())
        result = await node.execute(state)
        assert len(result["knowledge_points"]) == 2
        assert result["knowledge_points"][0]["title"] == "A"
        assert result["knowledge_points"][0]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_sort_by_confidence(self):
        """按 confidence 降序排列"""
        state: AnalysisState = {
            "repo_id": "test",
            "ast_data": [],
            "code_snippets": [],
            "knowledge_points": [
                {"title": "B", "confidence": 0.5},
                {"title": "A", "confidence": 0.9},
                {"title": "C", "confidence": 0.7},
            ],
            "current_category": "",
            "progress": 0.5,
            "error": None,
            "messages": [],
        }
        node = MergeNode(MagicMock())
        result = await node.execute(state)
        assert result["knowledge_points"][0]["title"] == "A"
        assert result["knowledge_points"][1]["title"] == "C"
        assert result["knowledge_points"][2]["title"] == "B"

    @pytest.mark.asyncio
    async def test_empty_kps(self):
        """空知识点列表"""
        state: AnalysisState = {
            "repo_id": "test",
            "ast_data": [],
            "code_snippets": [],
            "knowledge_points": [],
            "current_category": "",
            "progress": 0.5,
            "error": None,
            "messages": [],
        }
        node = MergeNode(MagicMock())
        result = await node.execute(state)
        assert len(result["knowledge_points"]) == 0


class TestExpansionNode:
    """拓展节点测试"""

    @pytest.fixture
    def base_state(self) -> AnalysisState:
        return {
            "repo_id": "test",
            "ast_data": [],
            "code_snippets": [],
            "knowledge_points": [{"title": "Test", "category_name": "DP", "description": "desc"}],
            "current_category": "",
            "progress": 0.9,
            "error": None,
            "messages": [],
        }

    @pytest.fixture
    def valid_expansion_json(self) -> str:
        return json.dumps(
            {
                "principle": "test principle content",
                "applicable_scenarios": ["scenario 1", "scenario 2"],
                "best_practices": ["practice 1", "practice 2"],
                "related_patterns": ["Singleton pattern", "Factory pattern"],
                "learning_resources": [
                    {"title": "Refactoring Guru", "url": "https://refactoring.guru/", "type": "article"},
                    {"title": "Design Patterns Book", "url": "https://example.com/dp", "type": "book"},
                ],
            }
        )

    @pytest.mark.asyncio
    async def test_generate_expansion(self, base_state, valid_expansion_json):
        """为知识点生成拓展内容"""
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(return_value={"content": valid_expansion_json})

        state = base_state
        node = ExpansionNode(llm_client)
        result = await node.execute(state)
        assert result["progress"] == 1.0
        kp = result["knowledge_points"][0]
        assert "expansion" in kp
        assert kp["expansion"]["principle"] == "test principle content"
        assert len(kp["expansion"]["applicable_scenarios"]) == 2
        assert len(kp["expansion"]["learning_resources"]) == 2
        assert kp["expansion"]["learning_resources"][0]["type"] == "article"

    @pytest.mark.asyncio
    async def test_skip_empty_kps(self):
        """空知识点时跳过"""
        node = ExpansionNode(MagicMock())
        state: AnalysisState = {
            "repo_id": "test",
            "ast_data": [],
            "code_snippets": [],
            "knowledge_points": [],
            "current_category": "",
            "progress": 0.9,
            "error": None,
            "messages": [],
        }
        result = await node.execute(state)
        assert result["progress"] == 1.0
        assert len(result["knowledge_points"]) == 0

    @pytest.mark.asyncio
    async def test_llm_error_graceful(self, base_state):
        """LLM 错误时优雅跳过"""
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(side_effect=Exception("API Error"))

        node = ExpansionNode(llm_client)
        result = await node.execute(base_state)
        assert result["progress"] == 1.0
        assert "expansion" not in result["knowledge_points"][0]

    @pytest.mark.asyncio
    async def test_validate_expansion_content(self):
        """TypeAdapter 校验拓展内容结构"""
        node = ExpansionNode(MagicMock())

        # 有效的拓展内容
        valid = {
            "principle": "原理说明",
            "applicable_scenarios": ["场景1"],
            "best_practices": ["实践1"],
            "related_patterns": ["模式1"],
            "learning_resources": [
                {"title": "资源1", "url": "https://example.com", "type": "article"},
            ],
        }
        result = node._expansion_adapter.validate_python(valid)
        assert result.principle == "原理说明"
        assert len(result.learning_resources) == 1

    @pytest.mark.asyncio
    async def test_validate_expansion_content_invalid_learning_resource(self):
        """TypeAdapter 校验非法学习资源"""
        node = ExpansionNode(MagicMock())

        # learning_resources 缺少必要字段
        invalid = {
            "principle": "原理说明",
            "applicable_scenarios": ["场景1"],
            "best_practices": ["实践1"],
            "related_patterns": ["模式1"],
            "learning_resources": [
                {"title": "资源1"},  # 缺少 url 和 type
            ],
        }
        with pytest.raises(ValidationError):
            node._expansion_adapter.validate_python(invalid)

    @pytest.mark.asyncio
    async def test_parse_and_validate_direct(self):
        """直接解析 JSON"""
        node = ExpansionNode(MagicMock())
        content = '{"principle": "test", "applicable_scenarios": ["s1"], "best_practices": ["p1"], "related_patterns": ["r1"], "learning_resources": []}'
        result = await node._parse_and_validate(content)
        assert result is not None
        assert result["principle"] == "test"

    @pytest.mark.asyncio
    async def test_parse_and_validate_code_block(self):
        """从代码块中提取 JSON"""
        node = ExpansionNode(MagicMock())
        content = 'Some text\n```json\n{"principle": "test", "applicable_scenarios": ["s1"], "best_practices": ["p1"], "related_patterns": ["r1"], "learning_resources": []}\n```'
        result = await node._parse_and_validate(content)
        assert result is not None
        assert result["principle"] == "test"

    @pytest.mark.asyncio
    async def test_parse_and_validate_invalid(self):
        """非法 JSON 返回 None"""
        node = ExpansionNode(MagicMock())
        content = "not json at all"
        result = await node._parse_and_validate(content)
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_expansion_retry_then_succeed(self, base_state):
        """首次失败后重试成功"""
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(
            side_effect=[
                Exception("First failure"),
                {
                    "content": '{"principle": "retry success", "applicable_scenarios": ["s1"], "best_practices": ["p1"], "related_patterns": ["r1"], "learning_resources": []}'
                },
            ]
        )

        node = ExpansionNode(llm_client)
        result = await node.execute(base_state)
        assert result["progress"] == 1.0
        assert result["knowledge_points"][0]["expansion"]["principle"] == "retry success"

    @pytest.mark.asyncio
    async def test_generate_expansion_retry_exhausted(self, base_state):
        """重试耗尽后返回 None"""
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(side_effect=Exception("Persistent failure"))

        node = ExpansionNode(llm_client)
        result = await node.execute(base_state)
        assert result["progress"] == 1.0
        assert "expansion" not in result["knowledge_points"][0]

    @pytest.mark.asyncio
    async def test_generate_expansion_multiple_kps(self):
        """多个知识点并发生成"""
        llm_client = MagicMock(spec=LLMClient)
        llm_client.chat = AsyncMock(
            return_value={
                "content": '{"principle": "p", "applicable_scenarios": ["s1"], "best_practices": ["p1"], "related_patterns": ["r1"], "learning_resources": []}'
            }
        )

        state: AnalysisState = {
            "repo_id": "test",
            "ast_data": [],
            "code_snippets": [],
            "knowledge_points": [
                {"title": "KP1", "category_name": "DP", "description": "desc1"},
                {"title": "KP2", "category_name": "AD", "description": "desc2"},
                {"title": "KP3", "category_name": "AL", "description": "desc3"},
            ],
            "current_category": "",
            "progress": 0.9,
            "error": None,
            "messages": [],
        }
        node = ExpansionNode(llm_client)
        result = await node.execute(state)
        assert result["progress"] == 1.0
        for kp in result["knowledge_points"]:
            assert "expansion" in kp
            assert kp["expansion"]["principle"] == "p"


class TestParseResponse:
    """LLM 响应解析测试"""

    def test_parse_valid_json_list(self):
        """解析有效 JSON 数组"""
        node = AnalysisNode(MagicMock())
        response = {"content": '[{"category": "DP", "prefix": "DP-A", "title": "A", "description": "Desc"}]'}
        result = node._parse_response(response, "DP")
        assert len(result) == 1
        assert result[0]["title"] == "A"
        assert result[0]["category"] == "DP"

    def test_parse_wrapped_object(self):
        """解析包装对象（含 knowledge_points 字段）"""
        node = AnalysisNode(MagicMock())
        response = {
            "content": '{"knowledge_points": [{"category": "DP", "prefix": "DP-A", "title": "A", "description": "Desc"}]}'
        }
        result = node._parse_response(response, "DP")
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_parse_empty_content(self):
        """空内容返回空列表"""
        node = AnalysisNode(MagicMock())
        result = node._parse_response({"content": ""}, "DP")
        assert result == []

    def test_parse_fallback_on_invalid_json(self):
        """无效 JSON 使用 fallback"""
        node = AnalysisNode(MagicMock())
        response = {"content": "不是 JSON 数据"}
        result = node._parse_response(response, "DP")
        assert len(result) == 1
        assert "分析结果" in result[0]["title"]
        assert result[0]["confidence"] == 0.8
