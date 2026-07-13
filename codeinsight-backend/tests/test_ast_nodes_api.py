"""
AST 节点 API 单元测试

覆盖按文件查询、按仓库查询、节点类型过滤、单节点获取、404 场景。
"""

from dataclasses import dataclass, field
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from codeinsight.api.ast_nodes import get_ast_node, list_ast_nodes


@dataclass
class FakeAstNode:
    """模拟 AstNodeModel 对象，支持属性访问和 Pydantic from_attributes 序列化"""

    id: UUID = field(default_factory=uuid4)
    repository_id: UUID = field(default_factory=uuid4)
    file_id: UUID = field(default_factory=uuid4)
    node_type: str = "function"
    name: str = "main"
    start_line: int = 1
    end_line: int = 10
    start_column: int = 0
    end_column: int = 80
    parent_node_id: UUID | None = None
    file_path: str = "src/main.py"
    language: str = "python"
    signature: str | None = None
    docstring: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime(2026, 7, 14))


@pytest.fixture
def mock_session():
    """创建 mock AsyncSession"""
    return AsyncMock()


@pytest.fixture
def mock_dao():
    """创建 mock AstNodeDAO"""
    dao = MagicMock()
    return dao


# ======================== list_ast_nodes 测试 ========================


@pytest.mark.asyncio
async def test_list_by_file_id(mock_session, mock_dao):
    """测试：按 file_id 查询 AST 节点"""
    mock_nodes = [
        FakeAstNode(name="func_a", start_line=1),
        FakeAstNode(name="func_b", start_line=20),
    ]
    mock_dao.get_by_file = AsyncMock(return_value=mock_nodes)

    result = await list_ast_nodes(
        db=mock_session,
        dao=mock_dao,
        file_id=uuid4(),
        repository_id=None,
        node_type=None,
    )

    assert len(result) == 2
    assert result[0].name == "func_a"
    assert result[1].name == "func_b"
    mock_dao.get_by_file.assert_called_once()


@pytest.mark.asyncio
async def test_list_by_repository_id(mock_session, mock_dao):
    """测试：按 repository_id 查询 AST 节点"""
    mock_nodes = [
        FakeAstNode(name="class_a", node_type="class"),
        FakeAstNode(name="func_b", node_type="function"),
    ]
    mock_dao.get_by_repository = AsyncMock(return_value=mock_nodes)

    result = await list_ast_nodes(
        db=mock_session,
        dao=mock_dao,
        file_id=None,
        repository_id=uuid4(),
        node_type=None,
    )

    assert len(result) == 2
    mock_dao.get_by_repository.assert_called_once()


@pytest.mark.asyncio
async def test_list_without_file_or_repo_returns_empty(mock_session, mock_dao):
    """测试：不提供 file_id 和 repository_id 时返回空列表"""
    result = await list_ast_nodes(
        db=mock_session,
        dao=mock_dao,
        file_id=None,
        repository_id=None,
        node_type=None,
    )

    assert result == []
    mock_dao.get_by_file.assert_not_called()
    mock_dao.get_by_repository.assert_not_called()


@pytest.mark.asyncio
async def test_list_with_node_type_filter(mock_session, mock_dao):
    """测试：按 node_type 过滤节点"""
    mock_nodes = [
        FakeAstNode(node_type="function", name="func_a"),
        FakeAstNode(node_type="class", name="MyClass"),
        FakeAstNode(node_type="function", name="func_b"),
    ]
    mock_dao.get_by_file = AsyncMock(return_value=mock_nodes)

    result = await list_ast_nodes(
        db=mock_session,
        dao=mock_dao,
        file_id=uuid4(),
        repository_id=None,
        node_type="function",
    )

    assert len(result) == 2
    assert all(n.node_type == "function" for n in result)


@pytest.mark.asyncio
async def test_list_empty_result(mock_session, mock_dao):
    """测试：查询结果为空"""
    mock_dao.get_by_file = AsyncMock(return_value=[])

    result = await list_ast_nodes(
        db=mock_session,
        dao=mock_dao,
        file_id=uuid4(),
        repository_id=None,
        node_type=None,
    )

    assert result == []


# ======================== get_ast_node 测试 ========================


@pytest.mark.asyncio
async def test_get_ast_node_found(mock_session, mock_dao):
    """测试：获取单个 AST 节点成功"""
    node_id = uuid4()
    mock_node = FakeAstNode(id=node_id, name="my_function", node_type="function")
    mock_dao.get_by_id = AsyncMock(return_value=mock_node)

    result = await get_ast_node(node_id, mock_session, mock_dao)

    assert result.name == "my_function"
    assert result.node_type == "function"


@pytest.mark.asyncio
async def test_get_ast_node_not_found(mock_session, mock_dao):
    """测试：获取不存在的 AST 节点返回 404"""
    node_id = uuid4()
    mock_dao.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(Exception) as exc_info:
        await get_ast_node(node_id, mock_session, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)
