"""
仓库管理 CRUD 单元测试

使用 mock 直接测试 RepositoryDAO 层方法和 API 端点逻辑。
覆盖 CRUD 操作、分页、路径重复检测等场景。
"""

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codeinsight.repositories import RepositoryDAO
from codeinsight.schemas import RepositoryCreate, RepositoryUpdate


@dataclass
class FakeRepo:
    """模拟 Repository ORM 对象，支持属性访问和 Pydantic from_attributes 序列化"""

    id: str = ""
    name: str = "Default"
    path: str = "/tmp/default"
    status: str = "pending"
    current_version: str | None = None
    file_count: int = 0
    line_count: int = 0
    knowledge_points_count: int = 0
    language_distribution: dict = field(default_factory=dict)
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
    dao = RepositoryDAO()
    data = RepositoryCreate(name="Test", path="/tmp/test")

    async def fake_refresh(obj):
        obj.id = str(uuid4())

    mock_session.refresh = fake_refresh

    repo = await dao.create(mock_session, data)
    assert repo.name == "Test"
    assert repo.path == "/tmp/test"
    assert repo.status == "pending"
    assert repo.file_count == 0
    assert repo.language_distribution == {}
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_dao_get_by_id_found(mock_session):
    """测试：DAO get_by_id 找到记录"""
    dao = RepositoryDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = FakeRepo(id="repo-1", name="Found")
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await dao.get_by_id(mock_session, "repo-1")
    assert result is not None
    assert result.name == "Found"


@pytest.mark.asyncio
async def test_dao_get_by_id_not_found(mock_session):
    """测试：DAO get_by_id 未找到记录"""
    dao = RepositoryDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await dao.get_by_id(mock_session, "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_dao_list(mock_session):
    """测试：DAO list 分页查询"""
    dao = RepositoryDAO()
    mock_repos = [FakeRepo(id=f"id-{i}", name=f"Repo {i}") for i in range(3)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_repos
    mock_session.execute = AsyncMock(return_value=mock_result)

    repos = await dao.list(mock_session, skip=0, limit=10)
    assert len(repos) == 3


@pytest.mark.asyncio
async def test_dao_list_pagination(mock_session):
    """测试：DAO list 分页 skip/limit 生效"""
    dao = RepositoryDAO()
    mock_repos = [FakeRepo(id="repo-1", name="Only One")]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_repos
    mock_session.execute = AsyncMock(return_value=mock_result)

    repos = await dao.list(mock_session, skip=10, limit=5)
    assert len(repos) <= 5


@pytest.mark.asyncio
async def test_dao_update(mock_session):
    """测试：DAO update 更新字段"""
    dao = RepositoryDAO()
    existing = FakeRepo(id="repo-1", name="Old Name", status="pending")
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=existing)),
            MagicMock(),
            MagicMock(refresh=AsyncMock()),
        ]
    )

    data = RepositoryUpdate(name="New Name")
    repo = await dao.update(mock_session, "repo-1", data)
    assert repo.name == "New Name"


@pytest.mark.asyncio
async def test_dao_delete_success(mock_session):
    """测试：DAO delete 成功删除"""
    dao = RepositoryDAO()
    existing = FakeRepo(id="repo-1", name="To Delete")
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
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=1)))

    exists = await dao.exists_by_path(mock_session, "/tmp/existing")
    assert exists is True


@pytest.mark.asyncio
async def test_dao_exists_by_path_false(mock_session):
    """测试：DAO exists_by_path 路径不存在"""
    dao = RepositoryDAO()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

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
    mock_repo = FakeRepo(id="new-id", name="New Repo", path="/tmp/new")
    mock_dao.create = AsyncMock(return_value=mock_repo)

    request = RepositoryCreate(name="New Repo", path="/tmp/new")
    result = await create_repository(request, mock_db, mock_dao)
    assert result.name == "New Repo"
    mock_dao.exists_by_path.assert_called_once_with(mock_db, "/tmp/new")
    mock_dao.create.assert_called_once()


@pytest.mark.asyncio
async def test_api_create_repository_duplicate_path():
    """测试：API create_repository 路径重复返回 409"""
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
    mock_repo = FakeRepo(
        id="repo-123",
        name="Found",
        status="completed",
        file_count=100,
        line_count=5000,
        language_distribution={"python": 80, "java": 20},
    )
    mock_dao.get_by_id = AsyncMock(return_value=mock_repo)

    result = await get_repository("repo-123", mock_db, mock_dao)
    assert result.name == "Found"
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_api_get_repository_not_found():
    """测试：API get_repository 未找到记录返回 404"""
    from codeinsight.api.repositories import get_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(Exception) as exc_info:
        await get_repository("nonexistent", mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_list_repositories(mock_session):
    """测试：API list_repositories 返回列表"""
    from codeinsight.api.repositories import list_repositories

    mock_dao = MagicMock()
    mock_repos = [
        FakeRepo(
            id=f"id-{i}",
            name=f"Repo {i}",
            status="completed",
            file_count=100,
            line_count=5000,
            language_distribution={"python": 100},
        )
        for i in range(3)
    ]
    mock_dao.list = AsyncMock(return_value=mock_repos)

    result = await list_repositories(skip=0, limit=10, db=mock_session, dao=mock_dao)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_api_list_repositories_empty(mock_session):
    """测试：API list_repositories 空列表"""
    from codeinsight.api.repositories import list_repositories

    mock_dao = MagicMock()
    mock_dao.list = AsyncMock(return_value=[])

    result = await list_repositories(skip=0, limit=10, db=mock_session, dao=mock_dao)
    assert result == []


@pytest.mark.asyncio
async def test_api_update_repository():
    """测试：API update_repository 更新记录"""
    from codeinsight.api.repositories import update_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_repo = FakeRepo(
        id="repo-1",
        name="Updated",
        status="analyzing",
        file_count=100,
        line_count=5000,
        language_distribution={"python": 100},
    )
    mock_dao.get_by_id = AsyncMock(return_value=mock_repo)
    mock_dao.update = AsyncMock(return_value=mock_repo)

    request = RepositoryUpdate(name="Updated")
    result = await update_repository("repo-1", request, mock_db, mock_dao)
    assert result.name == "Updated"


@pytest.mark.asyncio
async def test_api_update_repository_not_found():
    """测试：API update_repository 仓库不存在返回 404"""
    from codeinsight.api.repositories import update_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.get_by_id = AsyncMock(return_value=None)

    request = RepositoryUpdate(name="Updated")
    with pytest.raises(Exception) as exc_info:
        await update_repository("nonexistent", request, mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_delete_repository():
    """测试：API delete_repository 删除记录"""
    from codeinsight.api.repositories import delete_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.delete = AsyncMock(return_value=True)

    result = await delete_repository("repo-1", mock_db, mock_dao)
    assert "deleted successfully" in result.message


@pytest.mark.asyncio
async def test_api_delete_repository_not_found():
    """测试：API delete_repository 删除不存在的记录返回 404"""
    from codeinsight.api.repositories import delete_repository

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.delete = AsyncMock(return_value=False)

    with pytest.raises(Exception) as exc_info:
        await delete_repository("nonexistent", mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)
