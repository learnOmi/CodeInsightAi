"""
File DAO 单元测试

使用 mock 直接测试 FileDAO 层方法。
覆盖 CRUD 操作、按仓库查询、按哈希查找等场景。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from codeinsight.repositories.file import FileDAO
from codeinsight.schemas import FileCreate, FileUpdate


class MockFileModel:
    """模拟 ORM 模型"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


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


@pytest.mark.asyncio
async def test_dao_create(mock_session):
    """测试：DAO create 方法"""
    dao = FileDAO()
    data = FileCreate(
        path="src/main.py",
        absolute_path="/tmp/test/src/main.py",
        language="python",
        line_count=100,
        size_bytes=2048,
        content_hash="abc123",
    )

    async def fake_refresh(obj):
        obj.id = str(uuid4())
    mock_session.refresh = fake_refresh

    file_obj = await dao.create(mock_session, data)
    assert file_obj.path == "src/main.py"
    assert file_obj.language == "python"
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_dao_get_by_id_found(mock_session):
    """测试：DAO get_by_id 找到记录"""
    dao = FileDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MockFileModel(id="file-1", path="src/main.py")
    mock_session.execute = AsyncMock(return_value=mock_result)

    file_obj = await dao.get_by_id(mock_session, "file-1")
    assert file_obj is not None
    assert file_obj.path == "src/main.py"


@pytest.mark.asyncio
async def test_dao_get_by_id_not_found(mock_session):
    """测试：DAO get_by_id 未找到记录"""
    dao = FileDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    file_obj = await dao.get_by_id(mock_session, "nonexistent")
    assert file_obj is None


@pytest.mark.asyncio
async def test_dao_list_by_repository(mock_session):
    """测试：DAO list_by_repository 按仓库查询"""
    dao = FileDAO()
    mock_result = MagicMock()
    mock_files = [
        MockFileModel(id=f"id-{i}", path=f"src/file-{i}.py")
        for i in range(3)
    ]
    mock_result.scalars.return_value.all.return_value = mock_files
    mock_session.execute = AsyncMock(return_value=mock_result)

    files = await dao.list_by_repository(mock_session, "repo-1", skip=0, limit=10)
    assert len(files) == 3


@pytest.mark.asyncio
async def test_dao_update(mock_session):
    """测试：DAO update 更新记录"""
    dao = FileDAO()
    existing = MockFileModel(id="file-1", path="src/main.py", line_count=100)
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=existing)),  # get_by_id
        MagicMock(),  # flush
        MagicMock(refresh=AsyncMock()),  # refresh
    ])

    data = FileUpdate(line_count=150)
    file_obj = await dao.update(mock_session, "file-1", data)
    assert file_obj.line_count == 150


@pytest.mark.asyncio
async def test_dao_delete_success(mock_session):
    """测试：DAO delete 成功删除"""
    dao = FileDAO()
    existing = MockFileModel(id="file-1", path="src/main.py")
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing)))

    result = await dao.delete(mock_session, "file-1")
    assert result is True
    mock_session.delete.assert_called_once()


@pytest.mark.asyncio
async def test_dao_delete_not_found(mock_session):
    """测试：DAO delete 删除不存在的记录"""
    dao = FileDAO()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await dao.delete(mock_session, "nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_dao_get_by_content_hash_found(mock_session):
    """测试：DAO get_by_content_hash 找到记录"""
    dao = FileDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MockFileModel(id="file-1", content_hash="abc123")
    mock_session.execute = AsyncMock(return_value=mock_result)

    file_obj = await dao.get_by_content_hash(mock_session, "repo-1", "abc123")
    assert file_obj is not None
    assert file_obj.content_hash == "abc123"


@pytest.mark.asyncio
async def test_dao_get_by_content_hash_not_found(mock_session):
    """测试：DAO get_by_content_hash 未找到记录"""
    dao = FileDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    file_obj = await dao.get_by_content_hash(mock_session, "repo-1", "nonexistent")
    assert file_obj is None
