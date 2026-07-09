"""
仓库管理 API 单元测试

使用 mock 直接测试 API 函数逻辑和 DAO 层。
覆盖 CRUD 操作、分页、错误处理等场景。
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codeinsight.repositories import RepositoryDAO
from codeinsight.schemas import RepositoryCreate, RepositoryUpdate


class MockRepositoryModel:
    """模拟 ORM 模型，兼容 Pydantic response_model"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def model_fields_set(self):
        return set()

    def __getitem__(self, key):
        """支持 dict-style 访问"""
        return getattr(self, key)

    def model_dump(self, **kwargs):
        """返回所有非私有属性作为 dict"""
        result = {}
        for attr in dir(self):
            if not attr.startswith("_"):
                val = getattr(self, attr)
                if not callable(val):
                    result[attr] = val
        return result


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
    """测试：DAO create 方法"""
    dao = RepositoryDAO()
    data = RepositoryCreate(name="Test", path="/tmp/test")

    # 模拟 db.refresh 设置 id
    async def fake_refresh(obj):
        obj.id = str(uuid4())
    mock_session.refresh = fake_refresh

    repo = await dao.create(mock_session, data)
    assert repo.name == "Test"
    assert repo.path == "/tmp/test"
    assert repo.status == "pending"
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_dao_get_by_id_found(mock_session):
    """测试：DAO get_by_id 找到记录"""
    dao = RepositoryDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MockRepositoryModel(id="repo-1", name="Found")
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = await dao.get_by_id(mock_session, "repo-1")
    assert repo is not None
    assert repo.name == "Found"


@pytest.mark.asyncio
async def test_dao_get_by_id_not_found(mock_session):
    """测试：DAO get_by_id 未找到记录"""
    dao = RepositoryDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = await dao.get_by_id(mock_session, "nonexistent")
    assert repo is None


@pytest.mark.asyncio
async def test_dao_list(mock_session):
    """测试：DAO list 分页查询"""
    dao = RepositoryDAO()
    mock_result = MagicMock()
    mock_repos = [
        MockRepositoryModel(id=f"id-{i}", name=f"Repo {i}")
        for i in range(3)
    ]
    mock_result.scalars.return_value.all.return_value = mock_repos
    mock_session.execute = AsyncMock(return_value=mock_result)

    repos = await dao.list(mock_session, skip=0, limit=10)
    assert len(repos) == 3


@pytest.mark.asyncio
async def test_dao_update(mock_session):
    """测试：DAO update 更新记录"""
    dao = RepositoryDAO()
    existing = MockRepositoryModel(id="repo-1", name="Old Name", status="pending")
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=existing)),  # get_by_id
        MagicMock(),  # flush
        MagicMock(refresh=AsyncMock()),  # refresh
    ])

    data = RepositoryUpdate(name="New Name")
    repo = await dao.update(mock_session, "repo-1", data)
    assert repo.name == "New Name"


@pytest.mark.asyncio
async def test_dao_delete_success(mock_session):
    """测试：DAO delete 成功删除"""
    dao = RepositoryDAO()
    existing = MockRepositoryModel(id="repo-1", name="To Delete")
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing)))

    result = await dao.delete(mock_session, "repo-1")
    assert result is True
    mock_session.delete.assert_called_once()


@pytest.mark.asyncio
async def test_dao_delete_not_found(mock_session):
    """测试：DAO delete 删除不存在的记录"""
    dao = RepositoryDAO()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await dao.delete(mock_session, "nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_dao_exists_by_path_true(mock_session):
    """测试：DAO exists_by_path 路径已存在"""
    dao = RepositoryDAO()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar=MagicMock(return_value=1))
    )

    exists = await dao.exists_by_path(mock_session, "/tmp/existing")
    assert exists is True


@pytest.mark.asyncio
async def test_dao_exists_by_path_false(mock_session):
    """测试：DAO exists_by_path 路径不存在"""
    dao = RepositoryDAO()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar=MagicMock(return_value=0))
    )

    exists = await dao.exists_by_path(mock_session, "/tmp/new")
    assert exists is False


# ======================== API 端点逻辑测试 ========================


@pytest.mark.asyncio
async def test_api_create_repository_success():
    """测试：API create_repository 成功创建"""
    from codeinsight.api.repositories import create_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.exists_by_path = AsyncMock(return_value=False)
    mock_repo = MockRepositoryModel(
        id="new-id", name="New Repo", path="/tmp/new",
        status="pending", file_count=0, language_distribution={},
        created_at="2026-07-09T00:00:00Z", updated_at="2026-07-09T00:00:00Z",
    )
    mock_dao.create = AsyncMock(return_value=mock_repo)

    request = RepositoryCreate(name="New Repo", path="/tmp/new")
    result = await create_repository(request, mock_db, mock_dao)
    # result 是 Pydantic model，用 .name 或 ["name"] 访问
    assert result["name"] == "New Repo"
    mock_dao.exists_by_path.assert_called_once()
    mock_dao.create.assert_called_once()


@pytest.mark.asyncio
async def test_api_create_repository_duplicate_path():
    """测试：API create_repository 路径重复"""
    from codeinsight.api.repositories import create_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.exists_by_path = AsyncMock(return_value=True)

    request = RepositoryCreate(name="Dup Repo", path="/tmp/dup")

    with pytest.raises(Exception) as exc_info:
        await create_repository(request, mock_db, mock_dao)
    assert "409" in str(exc_info.value) or "already exists" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_get_repository_found():
    """测试：API get_repository 找到记录"""
    from codeinsight.api.repositories import get_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_repo = MockRepositoryModel(
        id="repo-123", name="Found", status="completed",
        file_count=100, language_distribution={"python": 100},
        created_at="2026-07-09T00:00:00Z", updated_at="2026-07-09T00:00:00Z",
    )
    mock_dao.get_by_id = AsyncMock(return_value=mock_repo)

    result = await get_repository("repo-123", mock_db, mock_dao)
    assert result["name"] == "Found"


@pytest.mark.asyncio
async def test_api_get_repository_not_found():
    """测试：API get_repository 未找到记录"""
    from codeinsight.api.repositories import get_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(Exception) as exc_info:
        await get_repository("nonexistent", mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_list_repositories():
    """测试：API list_repositories 返回列表"""
    from codeinsight.api.repositories import list_repositories

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_repos = [
        MockRepositoryModel(id=f"id-{i}", name=f"Repo {i}", status="completed",
                           file_count=100, language_distribution={"python": 100},
                           created_at="2026-07-09T00:00:00Z", updated_at="2026-07-09T00:00:00Z")
        for i in range(3)
    ]
    mock_dao.list = AsyncMock(return_value=mock_repos)

    result = await list_repositories(skip=0, limit=10, db=mock_db, dao=mock_dao)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_api_update_repository():
    """测试：API update_repository 更新记录"""
    from codeinsight.api.repositories import update_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_repo = MockRepositoryModel(
        id="repo-1", name="Updated", status="analyzing", auto_analyze=True,
        file_count=100, language_distribution={"python": 100},
        created_at="2026-07-09T00:00:00Z", updated_at="2026-07-09T00:00:00Z",
    )
    mock_dao.get_by_id = AsyncMock(return_value=mock_repo)
    mock_dao.update = AsyncMock(return_value=mock_repo)

    request = RepositoryUpdate(name="Updated", auto_analyze=True)
    result = await update_repository("repo-1", request, mock_db, mock_dao)
    assert result["name"] == "Updated"


@pytest.mark.asyncio
async def test_api_delete_repository():
    """测试：API delete_repository 删除记录"""
    from codeinsight.api.repositories import delete_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.delete = AsyncMock(return_value=True)

    result = await delete_repository("repo-1", mock_db, mock_dao)
    assert "deleted successfully" in str(result)


@pytest.mark.asyncio
async def test_api_delete_repository_not_found():
    """测试：API delete_repository 删除不存在的记录"""
    from codeinsight.api.repositories import delete_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.delete = AsyncMock(return_value=False)

    with pytest.raises(Exception) as exc_info:
        await delete_repository("nonexistent", mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)
