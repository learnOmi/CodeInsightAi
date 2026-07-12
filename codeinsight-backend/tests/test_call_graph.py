"""
调用图构建器单元测试

测试 CallGraphBuilder 和 CallGraphQuery 的核心功能。
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from codeinsight.analyzers.call_graph import CallGraphBuilder, CallGraphQuery


@dataclass
class FakeAstNode:
    """模拟 AstNode ORM 对象"""

    id: str = ""
    repository_id: str = ""
    file_id: str = ""
    node_type: str = "function"
    name: str = ""
    start_line: int = 1
    end_line: int = 10
    start_column: int = 0
    end_column: int = 0
    parent_node_id: str | None = None
    file_path: str = ""
    language: str = "python"
    signature: str | None = None
    docstring: str | None = None
    created_at: str = "2026-07-09T00:00:00Z"


@dataclass
class FakeCallEdge:
    """模拟 CallEdge ORM 对象"""

    id: str = ""
    repository_id: str = ""
    caller_node_id: str = ""
    callee_node_id: str | None = None
    start_line: int = 1
    start_column: int = 0
    call_name: str = ""
    call_type: str = "static"
    created_at: str = "2026-07-09T00:00:00Z"


# ======================== CallGraphBuilder 测试 ========================


@pytest.fixture
def mock_session():
    """创建 mock AsyncSession"""
    session = AsyncMock()
    session.add = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def call_graph_builder():
    """创建 CallGraphBuilder 实例"""
    return CallGraphBuilder()


def test_build_function_index():
    """测试：构建函数索引"""
    nodes = [
        FakeAstNode(id="func-1", node_type="function", name="greet"),
        FakeAstNode(id="func-2", node_type="function", name="greet"),  # 重载
        FakeAstNode(id="func-3", node_type="method", name="sayHello"),
        FakeAstNode(id="func-4", node_type="constructor", name="Greeter"),
    ]
    index = CallGraphBuilder._build_function_index(nodes)
    assert len(index) == 3
    assert len(index["greet"]) == 2
    assert len(index["sayHello"]) == 1
    assert len(index["Greeter"]) == 1


def test_is_dynamic_call():
    """测试：动态调用检测"""
    assert CallGraphBuilder._is_dynamic_call("getattr") is True
    assert CallGraphBuilder._is_dynamic_call("setattr") is True
    assert CallGraphBuilder._is_dynamic_call("hasattr") is True
    assert CallGraphBuilder._is_dynamic_call("delattr") is True
    assert CallGraphBuilder._is_dynamic_call("getattr.obj") is True
    assert CallGraphBuilder._is_dynamic_call("greet") is False
    assert CallGraphBuilder._is_dynamic_call("sayHello") is False


def test_match_call_edges_exact_match():
    """测试：精确匹配调用边"""
    call_nodes = [
        FakeAstNode(id="call-1", node_type="call", name="greet", start_line=5, start_column=4),
    ]
    function_index = {"greet": [FakeAstNode(id="func-1", node_type="function", name="greet")]}
    repo_uuid = uuid4()

    edges = CallGraphBuilder._match_call_edges(call_nodes, function_index, repo_uuid)
    assert len(edges) == 1
    assert edges[0]["caller_node_id"] == "call-1"
    assert edges[0]["callee_node_id"] == "func-1"
    assert edges[0]["call_type"] == "static"


def test_match_call_edges_method_call():
    """测试：方法调用匹配（*.method 格式）"""
    call_nodes = [
        FakeAstNode(id="call-1", node_type="call", name="*.sayHello", start_line=5, start_column=4),
    ]
    function_index = {"sayHello": [FakeAstNode(id="method-1", node_type="method", name="sayHello")]}
    repo_uuid = uuid4()

    edges = CallGraphBuilder._match_call_edges(call_nodes, function_index, repo_uuid)
    assert len(edges) == 1
    assert edges[0]["callee_node_id"] == "method-1"
    assert edges[0]["call_type"] == "static"


def test_match_call_edges_constructor_call():
    """测试：构造器调用匹配（new Class 格式）"""
    call_nodes = [
        FakeAstNode(id="call-1", node_type="call", name="new Greeter", start_line=5, start_column=4),
    ]
    function_index = {"Greeter": [FakeAstNode(id="ctor-1", node_type="constructor", name="Greeter")]}
    repo_uuid = uuid4()

    edges = CallGraphBuilder._match_call_edges(call_nodes, function_index, repo_uuid)
    assert len(edges) == 1
    assert edges[0]["callee_node_id"] == "ctor-1"
    assert edges[0]["call_type"] == "static"


def test_match_call_edges_overload():
    """测试：函数重载（同名多目标）"""
    call_nodes = [
        FakeAstNode(id="call-1", node_type="call", name="process", start_line=5, start_column=4),
    ]
    function_index = {
        "process": [
            FakeAstNode(id="func-1", node_type="function", name="process"),
            FakeAstNode(id="func-2", node_type="function", name="process"),
        ]
    }
    repo_uuid = uuid4()

    edges = CallGraphBuilder._match_call_edges(call_nodes, function_index, repo_uuid)
    assert len(edges) == 2  # 两个重载各创建一条边


def test_match_call_edges_dynamic():
    """测试：动态调用标记为 dynamic"""
    call_nodes = [
        FakeAstNode(id="call-1", node_type="call", name="getattr", start_line=5, start_column=4),
    ]
    function_index = {}
    repo_uuid = uuid4()

    edges = CallGraphBuilder._match_call_edges(call_nodes, function_index, repo_uuid)
    assert len(edges) == 1
    assert edges[0]["callee_node_id"] is None
    assert edges[0]["call_type"] == "dynamic"


def test_match_call_edges_unknown():
    """测试：未知调用标记为 unknown"""
    call_nodes = [
        FakeAstNode(id="call-1", node_type="call", name="unknownFunc", start_line=5, start_column=4),
    ]
    function_index = {}  # 没有匹配的函数
    repo_uuid = uuid4()

    edges = CallGraphBuilder._match_call_edges(call_nodes, function_index, repo_uuid)
    assert len(edges) == 1
    assert edges[0]["callee_node_id"] is None
    assert edges[0]["call_type"] == "unknown"


@pytest.mark.asyncio
async def test_build_creates_edges():
    """测试：调用图构建创建边"""
    builder = CallGraphBuilder()

    # Mock AST nodes
    mock_func_nodes = [FakeAstNode(id="func-1", node_type="function", name="greet")]
    mock_call_nodes = [FakeAstNode(id="call-1", node_type="call", name="greet", start_line=5, start_column=4)]

    # Mock DAOs — get_by_repository_and_types 被调两次（分别按 {"call"} 和 _CALLABLE_NODE_TYPES 查询）
    def mock_get_by_types(*args, **kwargs):
        node_types = args[2]
        if "call" in node_types:
            return mock_call_nodes
        return mock_func_nodes

    builder.ast_dao = MagicMock()
    builder.ast_dao.get_by_repository_and_types = AsyncMock(side_effect=mock_get_by_types)
    builder.call_edge_dao = MagicMock()
    builder.call_edge_dao.delete_by_repository = AsyncMock(return_value=0)
    builder.call_edge_dao.create_many = AsyncMock(return_value=[FakeCallEdge()])

    with patch("codeinsight.analyzers.call_graph.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()
        mock_session_factory.return_value = mock_session

        count = await builder.build(uuid4())
        assert count == 1
        builder.call_edge_dao.delete_by_repository.assert_called_once()
        builder.call_edge_dao.create_many.assert_called_once()


# ======================== CallGraphQuery 测试 ========================


@pytest.fixture
def call_graph_query():
    """创建 CallGraphQuery 实例"""
    return CallGraphQuery()


@pytest.mark.asyncio
async def test_get_callees():
    """测试：获取被调用者（正向调用图）"""
    query = CallGraphQuery()
    query.call_edge_dao = MagicMock()
    query.ast_dao = MagicMock()

    mock_edges = [
        FakeCallEdge(
            id="edge-1", caller_node_id="call-1", callee_node_id="func-1", call_name="greet", call_type="static"
        ),
    ]
    query.call_edge_dao.get_callees = AsyncMock(return_value=mock_edges)
    query.ast_dao.get_by_id = AsyncMock(return_value=FakeAstNode(id="func-1", name="greet", node_type="function"))

    with patch("codeinsight.analyzers.call_graph.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = mock_session

        callees = await query.get_callees("call-1")
        assert len(callees) == 1
        assert callees[0]["callee"]["name"] == "greet"


@pytest.mark.asyncio
async def test_get_callers():
    """测试：获取调用者（反向调用图）"""
    query = CallGraphQuery()
    query.call_edge_dao = MagicMock()
    query.ast_dao = MagicMock()

    mock_edges = [
        FakeCallEdge(
            id="edge-1", caller_node_id="call-1", callee_node_id="func-1", call_name="greet", call_type="static"
        ),
    ]
    query.call_edge_dao.get_callers = AsyncMock(return_value=mock_edges)
    query.ast_dao.get_by_id = AsyncMock(
        return_value=FakeAstNode(id="call-1", name="greet", node_type="call", file_path="test.py")
    )

    with patch("codeinsight.analyzers.call_graph.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = mock_session

        callers = await query.get_callers("func-1")
        assert len(callers) == 1
        assert callers[0]["caller"]["name"] == "greet"


@pytest.mark.asyncio
async def test_get_call_chain():
    """测试：获取调用链（DFS 遍历）"""
    from uuid import UUID, uuid4

    query = CallGraphQuery()

    # 使用有效的 UUID
    node_a = uuid4()
    node_b = uuid4()
    node_c = uuid4()

    # Mock get_callees to return different results based on node_id
    async def mock_get_callees(node_id: UUID) -> list[dict]:
        if str(node_id) == str(node_a):
            return [
                {
                    "callee": {"id": str(node_b), "name": "func_b", "node_type": "function"},
                    "call_name": "func_b",
                    "call_type": "static",
                }
            ]
        elif str(node_id) == str(node_b):
            return [
                {
                    "callee": {"id": str(node_c), "name": "func_c", "node_type": "function"},
                    "call_name": "func_c",
                    "call_type": "static",
                }
            ]
        return []

    with patch.object(query, "get_callees", side_effect=mock_get_callees):
        chain = await query.get_call_chain(node_a, max_depth=5)
        assert len(chain) >= 2  # 至少有两个节点（func_b, func_c）
        # 检查调用链结构
        node_names = {item["node_name"] for item in chain}
        assert "func_b" in node_names
        assert "func_c" in node_names
