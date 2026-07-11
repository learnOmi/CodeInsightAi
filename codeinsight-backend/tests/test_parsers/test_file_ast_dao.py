"""
FileDAO 和 AstNodeDAO 单元测试

测试批量创建、查询、删除等操作。
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codeinsight.repositories import AstNodeDAO, FileDAO


@dataclass
class FakeFile:
    """模拟 File ORM 对象"""
    id: str = ""
    repository_id: str = ""
    path: str = ""
    absolute_path: str = ""
    language: str = "python"
    line_count: int = 0
    size_bytes: int = 0
    content_hash: str = ""
    created_at: str = "2026-07-09T00:00:00Z"
    updated_at: str = "2026-07-09T00:00:00Z"


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


@pytest.fixture
def mock_session():
    """创建 mock AsyncSession"""
    session = AsyncMock()
    session.add = AsyncMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


# ======================== FileDAO 测试 ========================


@pytest.mark.asyncio
async def test_file_dao_create_many(mock_session):
    """测试：FileDAO create_many 批量创建"""
    dao = FileDAO()
    repo_id = str(uuid4())
    files_data = [
        {"path": "src/main.py", "absolute_path": "/tmp/src/main.py", "language": "python",
         "line_count": 100, "size_bytes": 2000, "content_hash": "hash1"},
        {"path": "src/utils.py", "absolute_path": "/tmp/src/utils.py", "language": "python",
         "line_count": 50, "size_bytes": 1000, "content_hash": "hash2"},
    ]

    mock_session.add_all = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    files = await dao.create_many(mock_session, repo_id, files_data)

    assert len(files) == 2
    mock_session.add_all.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_file_dao_get_by_repository(mock_session):
    """测试：FileDAO get_by_repository 查询仓库文件"""
    dao = FileDAO()
    repo_id = str(uuid4())
    mock_files = [FakeFile(id=str(uuid4()), repository_id=repo_id, path=f"file{i}.py") for i in range(3)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_files
    mock_session.execute = AsyncMock(return_value=mock_result)

    files = await dao.get_by_repository(mock_session, repo_id)

    assert len(files) == 3
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_file_dao_delete_by_repository(mock_session):
    """测试：FileDAO delete_by_repository 删除仓库文件"""
    dao = FileDAO()
    repo_id = str(uuid4())
    mock_files = [FakeFile(id=str(uuid4()), repository_id=repo_id) for _ in range(5)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_files
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.delete = AsyncMock()

    count = await dao.delete_by_repository(mock_session, repo_id)

    assert count == 5
    assert mock_session.delete.call_count == 5
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_file_dao_get_all(mock_session):
    """测试：FileDAO get_all 分页查询"""
    dao = FileDAO()
    repo_id = str(uuid4())
    mock_files = [FakeFile(id=str(uuid4()), repository_id=repo_id, path=f"file{i}.py") for i in range(10)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_files[:5]
    mock_session.execute = AsyncMock(return_value=mock_result)

    files = await dao.get_all(mock_session, repo_id, skip=0, limit=5)

    assert len(files) == 5
    mock_session.execute.assert_called_once()


# ======================== AstNodeDAO 测试 ========================


@pytest.mark.asyncio
async def test_ast_node_dao_create_many(mock_session):
    """测试：AstNodeDAO create_many 批量创建"""
    dao = AstNodeDAO()
    nodes_data = [
        {"repository_id": str(uuid4()), "file_id": str(uuid4()), "node_type": "function",
         "name": "main", "start_line": 1, "end_line": 10, "start_column": 0, "end_column": 50,
         "parent_node_id": None, "file_path": "src/main.py", "language": "python"},
        {"repository_id": str(uuid4()), "file_id": str(uuid4()), "node_type": "class",
         "name": "MyClass", "start_line": 15, "end_line": 100, "start_column": 0, "end_column": 50,
         "parent_node_id": None, "file_path": "src/main.py", "language": "python"},
    ]

    mock_session.add_all = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    nodes = await dao.create_many(mock_session, nodes_data)

    assert len(nodes) == 2
    mock_session.add_all.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_ast_node_dao_get_by_file(mock_session):
    """测试：AstNodeDAO get_by_file 查询文件节点"""
    dao = AstNodeDAO()
    file_id = str(uuid4())
    mock_nodes = [FakeAstNode(id=str(uuid4()), file_id=file_id, name=f"func{i}") for i in range(5)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_nodes
    mock_session.execute = AsyncMock(return_value=mock_result)

    nodes = await dao.get_by_file(mock_session, file_id)

    assert len(nodes) == 5
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_ast_node_dao_get_by_repository(mock_session):
    """测试：AstNodeDAO get_by_repository 查询仓库节点"""
    dao = AstNodeDAO()
    repo_id = str(uuid4())
    mock_nodes = [FakeAstNode(id=str(uuid4()), repository_id=repo_id, name=f"node{i}") for i in range(10)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_nodes
    mock_session.execute = AsyncMock(return_value=mock_result)

    nodes = await dao.get_by_repository(mock_session, repo_id)

    assert len(nodes) == 10
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_ast_node_dao_delete_by_repository(mock_session):
    """测试：AstNodeDAO delete_by_repository 删除仓库节点"""
    dao = AstNodeDAO()
    repo_id = str(uuid4())

    mock_result = MagicMock()
    mock_result.rowcount = 50
    mock_session.execute = AsyncMock(return_value=mock_result)

    count = await dao.delete_by_repository(mock_session, repo_id)

    assert count == 50
    mock_session.execute.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_ast_node_dao_delete_by_file(mock_session):
    """测试：AstNodeDAO delete_by_file 删除文件节点"""
    dao = AstNodeDAO()
    file_id = str(uuid4())

    mock_result = MagicMock()
    mock_result.rowcount = 20
    mock_session.execute = AsyncMock(return_value=mock_result)

    count = await dao.delete_by_file(mock_session, file_id)

    assert count == 20
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_ast_node_dao_count_by_repository(mock_session):
    """测试：AstNodeDAO count_by_repository 统计节点数量"""
    dao = AstNodeDAO()
    repo_id = str(uuid4())

    mock_result = MagicMock()
    mock_result.scalar.return_value = 100
    mock_session.execute = AsyncMock(return_value=mock_result)

    count = await dao.count_by_repository(mock_session, repo_id)

    assert count == 100
    mock_session.execute.assert_called_once()
