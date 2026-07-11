"""
文件管理 CRUD 单元测试

使用 mock 直接测试 FileDAO 层方法和 API 端点逻辑。
覆盖 CRUD 操作、按仓库查询、按哈希查找等场景。
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codeinsight.repositories.file import FileDAO
from codeinsight.schemas import FileCreate, FileUpdate


@dataclass
class FakeFile:
    """模拟 File ORM 对象，支持属性访问和 Pydantic from_attributes 序列化"""

    id: str = ""
    repository_id: str = "repo-default"
    path: str = "src/default.py"
    absolute_path: str = "/tmp/src/default.py"
    language: str = "python"
    line_count: int = 0
    size_bytes: int = 0
    content_hash: str = ""
    created_at: str = "2026-07-09T00:00:00Z"
    updated_at: str = "2026-07-09T00:00:00Z"


# ======================== DAO 层测试 ========================


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
    """测试：DAO create 方法设置默认值"""
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
    assert file_obj.line_count == 100
    assert file_obj.size_bytes == 2048
    assert file_obj.content_hash == "abc123"
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_dao_get_by_id_found(mock_session):
    """测试：DAO get_by_id 找到记录"""
    dao = FileDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = FakeFile(id="file-1", path="src/main.py")
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
    """测试：DAO list_by_repository 按仓库分页查询"""
    dao = FileDAO()
    # 模拟 DAO 实际执行了 limit，只返回 3 条
    mock_files = [FakeFile(id=f"id-{i}", path=f"src/file-{i}.py") for i in range(3)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_files
    mock_session.execute = AsyncMock(return_value=mock_result)

    files = await dao.list_by_repository(mock_session, repository_id="repo-1", skip=0, limit=3)
    assert len(files) == 3


@pytest.mark.asyncio
async def test_dao_list_by_repository_empty(mock_session):
    """测试：DAO list_by_repository 空结果"""
    dao = FileDAO()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    files = await dao.list_by_repository(mock_session, repository_id="repo-999")
    assert files == []


@pytest.mark.asyncio
async def test_dao_update(mock_session):
    """测试：DAO update 更新字段"""
    dao = FileDAO()
    existing = FakeFile(id="file-1", path="src/main.py", line_count=100, size_bytes=2048)
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=existing)),
            MagicMock(),
            MagicMock(refresh=AsyncMock()),
        ]
    )

    data = FileUpdate(line_count=150, size_bytes=3000)
    file_obj = await dao.update(mock_session, "file-1", data)
    assert file_obj.line_count == 150
    assert file_obj.size_bytes == 3000


@pytest.mark.asyncio
async def test_dao_delete_success(mock_session):
    """测试：DAO delete 成功删除"""
    dao = FileDAO()
    existing = FakeFile(id="file-1", path="src/main.py")
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
    mock_result.scalar_one_or_none.return_value = FakeFile(id="file-1", content_hash="abc123")
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


# ======================== API 端点逻辑测试 ========================


@pytest.mark.asyncio
async def test_api_create_file_success():
    """测试：API create_file 成功创建"""
    from codeinsight.api.files import create_file

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_file = FakeFile(
        id="file-new",
        path="src/app.py",
        absolute_path="/tmp/src/app.py",
        language="python",
        line_count=50,
        size_bytes=1024,
        content_hash="xyz789",
    )
    mock_dao.create = AsyncMock(return_value=mock_file)

    request = FileCreate(
        path="src/app.py",
        absolute_path="/tmp/src/app.py",
        language="python",
        line_count=50,
        size_bytes=1024,
        content_hash="xyz789",
    )
    result = await create_file(request, mock_db, mock_dao)
    assert result.path == "src/app.py"
    mock_dao.create.assert_called_once()


@pytest.mark.asyncio
async def test_api_get_file_found():
    """测试：API get_file 找到记录"""
    from codeinsight.api.files import get_file

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_file = FakeFile(
        id="file-123",
        path="src/main.py",
        absolute_path="/tmp/src/main.py",
        language="python",
        line_count=100,
        size_bytes=2048,
        content_hash="abc123",
    )
    mock_dao.get_by_id = AsyncMock(return_value=mock_file)

    result = await get_file("file-123", mock_db, mock_dao)
    assert result.path == "src/main.py"
    assert result.language == "python"


@pytest.mark.asyncio
async def test_api_get_file_not_found():
    """测试：API get_file 未找到记录返回 404"""
    from codeinsight.api.files import get_file

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(Exception) as exc_info:
        await get_file("nonexistent", mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_get_files_by_hash_found(mock_session):
    """测试：API get_files_by_hash 找到记录"""
    from codeinsight.api.files import get_files_by_hash

    mock_dao = MagicMock()
    mock_file = FakeFile(id="file-1", content_hash="abc123")
    mock_dao.get_by_content_hash = AsyncMock(return_value=mock_file)

    result = await get_files_by_hash("abc123", repository_id="repo-1", db=mock_session, dao=mock_dao)
    assert len(result) == 1
    assert result[0].content_hash == "abc123"


@pytest.mark.asyncio
async def test_api_get_files_by_hash_not_found(mock_session):
    """测试：API get_files_by_hash 未找到记录返回空列表"""
    from codeinsight.api.files import get_files_by_hash

    mock_dao = MagicMock()
    mock_dao.get_by_content_hash = AsyncMock(return_value=None)

    result = await get_files_by_hash("nonexistent", repository_id="repo-1", db=mock_session, dao=mock_dao)
    assert result == []


@pytest.mark.asyncio
async def test_api_update_file():
    """测试：API update_file 更新记录"""
    from codeinsight.api.files import update_file

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_file = FakeFile(
        id="file-1",
        path="src/main.py",
        absolute_path="/tmp/src/main.py",
        language="python",
        line_count=100,
        size_bytes=2048,
        content_hash="abc123",
    )
    mock_dao.get_by_id = AsyncMock(return_value=mock_file)
    # DAO update 返回更新后的对象
    mock_updated_file = FakeFile(
        id="file-1",
        path="src/main.py",
        absolute_path="/tmp/src/main.py",
        language="python",
        line_count=200,
        size_bytes=2048,
        content_hash="abc123",
    )
    mock_dao.update = AsyncMock(return_value=mock_updated_file)

    request = FileUpdate(line_count=200)
    result = await update_file("file-1", request, mock_db, mock_dao)
    assert result.line_count == 200


@pytest.mark.asyncio
async def test_api_update_file_not_found():
    """测试：API update_file 文件不存在返回 404"""
    from codeinsight.api.files import update_file

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.get_by_id = AsyncMock(return_value=None)

    request = FileUpdate(line_count=200)
    with pytest.raises(Exception) as exc_info:
        await update_file("nonexistent", request, mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_delete_file():
    """测试：API delete_file 删除记录"""
    from codeinsight.api.files import delete_file

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.delete = AsyncMock(return_value=True)

    result = await delete_file("file-1", mock_db, mock_dao)
    assert result is not None


@pytest.mark.asyncio
async def test_api_delete_file_not_found():
    """测试：API delete_file 删除不存在的记录返回 404"""
    from codeinsight.api.files import delete_file

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.delete = AsyncMock(return_value=False)

    with pytest.raises(Exception) as exc_info:
        await delete_file("nonexistent", mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)
