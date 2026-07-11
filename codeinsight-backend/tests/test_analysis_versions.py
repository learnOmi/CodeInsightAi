"""
分析版本管理 CRUD 单元测试

使用 mock 直接测试 AnalysisVersionDAO 层方法和 API 端点逻辑。
覆盖 CRUD、版本切换、回滚等场景。
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codeinsight.repositories.analysis_version import AnalysisVersionDAO


@dataclass
class FakeAV:
    """模拟 AnalysisVersion ORM 对象，支持属性访问和 Pydantic from_attributes 序列化"""

    id: str = ""
    version: str = "v1"
    status: str = "pending"
    total_files: int = 0
    analyzed_files: int = 0
    knowledge_points_count: int = 0
    created_at: str = "2026-07-09T00:00:00Z"
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


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
    dao = AnalysisVersionDAO()
    data = {
        "version": "v20260709-abc123",
        "repository_id": str(uuid4()),
        "status": "pending",
        "total_files": 100,
        "analyzed_files": 0,
        "knowledge_points_count": 0,
    }

    async def fake_refresh(obj):
        obj.id = str(uuid4())

    mock_session.refresh = fake_refresh

    av = await dao.create(mock_session, data)
    assert av.version == "v20260709-abc123"
    assert av.status == "pending"
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_dao_get_by_id_found(mock_session):
    """测试：DAO get_by_id 找到记录"""
    dao = AnalysisVersionDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = FakeAV(id="av-1", version="v1")
    mock_session.execute = AsyncMock(return_value=mock_result)

    av = await dao.get_by_id(mock_session, "av-1")
    assert av is not None
    assert av.version == "v1"


@pytest.mark.asyncio
async def test_dao_get_by_id_not_found(mock_session):
    """测试：DAO get_by_id 未找到记录"""
    dao = AnalysisVersionDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    av = await dao.get_by_id(mock_session, "nonexistent")
    assert av is None


@pytest.mark.asyncio
async def test_dao_list_by_repository(mock_session):
    """测试：DAO list_by_repository 按仓库查询"""
    dao = AnalysisVersionDAO()
    mock_avs = [FakeAV(id=f"id-{i}", version=f"v{i}") for i in range(3)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_avs
    mock_session.execute = AsyncMock(return_value=mock_result)

    avs = await dao.list_by_repository(mock_session, repository_id="repo-1")
    assert len(avs) == 3


@pytest.mark.asyncio
async def test_dao_list_by_repository_empty(mock_session):
    """测试：DAO list_by_repository 空结果"""
    dao = AnalysisVersionDAO()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    avs = await dao.list_by_repository(mock_session, repository_id="repo-999")
    assert avs == []


@pytest.mark.asyncio
async def test_dao_get_by_version_tag_found(mock_session):
    """测试：DAO get_by_version_tag 找到记录"""
    dao = AnalysisVersionDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = FakeAV(id="av-1", version="v20260709-abc")
    mock_session.execute = AsyncMock(return_value=mock_result)

    av = await dao.get_by_version_tag(mock_session, "repo-1", "v20260709-abc")
    assert av is not None
    assert av.version == "v20260709-abc"


@pytest.mark.asyncio
async def test_dao_get_by_version_tag_not_found(mock_session):
    """测试：DAO get_by_version_tag 未找到记录"""
    dao = AnalysisVersionDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    av = await dao.get_by_version_tag(mock_session, "repo-1", "nonexistent")
    assert av is None


@pytest.mark.asyncio
async def test_dao_update(mock_session):
    """测试：DAO update 更新字段"""
    dao = AnalysisVersionDAO()
    existing = FakeAV(id="av-1", status="pending", total_files=100)
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing)))

    data = {"status": "completed"}
    av = await dao.update(mock_session, "av-1", data)
    assert av.status == "completed"


@pytest.mark.asyncio
async def test_dao_delete_success(mock_session):
    """测试：DAO delete 成功删除"""
    dao = AnalysisVersionDAO()
    existing = FakeAV(id="av-1", version="v1")
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing)))

    result = await dao.delete(mock_session, "av-1")
    assert result is True
    mock_session.delete.assert_called_once()


@pytest.mark.asyncio
async def test_dao_delete_not_found(mock_session):
    """测试：DAO delete 删除不存在的记录"""
    dao = AnalysisVersionDAO()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await dao.delete(mock_session, "nonexistent")
    assert result is False


# ======================== API 端点逻辑测试 ========================


@pytest.mark.asyncio
async def test_api_list_versions():
    """测试：API list_versions 返回列表并标记当前版本"""
    from codeinsight.api.versions import list_versions

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    mock_avs = [
        FakeAV(
            version=f"v{i + 1}",
            status="completed",
            total_files=500,
            analyzed_files=500,
            knowledge_points_count=128,
            created_at="2026-07-09T00:00:00Z",
            started_at=None,
            completed_at="2026-07-09T01:00:00Z",
            error_message=None,
        )
        for i in range(3)
    ]
    mock_dao.list_by_repository = AsyncMock(return_value=mock_avs)

    # 模拟仓库查询（用于获取 current_version）
    mock_repo_result = MagicMock()
    mock_repo = MagicMock(current_version="v2")
    mock_repo_result.scalar_one_or_none.return_value = mock_repo
    mock_db.execute = AsyncMock(return_value=mock_repo_result)

    result = await list_versions("repo-1", db=mock_db, dao=mock_dao)
    assert len(result) == 3
    # 验证 is_current 标记正确（Pydantic 对象用属性访问）
    for item in result:
        if item.version == "v2":
            assert item.is_current is True
        else:
            assert item.is_current is False


@pytest.mark.asyncio
async def test_api_list_versions_no_current():
    """测试：API list_versions 没有当前版本时 all is_current=False"""
    from codeinsight.api.versions import list_versions

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    mock_avs = [
        FakeAV(
            version="v1",
            status="completed",
            total_files=100,
            analyzed_files=100,
            knowledge_points_count=50,
            created_at="2026-07-09T00:00:00Z",
            started_at=None,
            completed_at=None,
            error_message=None,
        )
    ]
    mock_dao.list_by_repository = AsyncMock(return_value=mock_avs)

    # 仓库不存在
    mock_repo_result = MagicMock()
    mock_repo_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_repo_result)

    result = await list_versions("repo-1", db=mock_db, dao=mock_dao)
    assert len(result) == 1
    assert result[0].is_current is False


@pytest.mark.asyncio
async def test_api_switch_version_success():
    """测试：API switch_version 切换成功"""
    from codeinsight.api.versions import switch_version

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    # 模拟仓库存在
    mock_repo_result = MagicMock()
    mock_repo = MagicMock(id="repo-1", current_version="v1")
    mock_repo_result.scalar_one_or_none.return_value = mock_repo
    mock_db.execute = AsyncMock(
        side_effect=[
            mock_repo_result,  # 查询仓库
            MagicMock(),  # flush
        ]
    )

    # 模拟目标版本存在
    mock_target_result = MagicMock()
    mock_target_result.scalar_one_or_none.return_value = FakeAV(version="v2")
    mock_dao.get_by_version_tag = AsyncMock(return_value=mock_target_result)

    result = await switch_version(
        "repo-1",
        version="v2",
        db=mock_db,
        dao=mock_dao,
    )
    assert result["current_version"] == "v2"
    assert result["previous_version"] == "v1"
    assert "已切换到版本" in result["message"]


@pytest.mark.asyncio
async def test_api_switch_version_repo_not_found():
    """测试：API switch_version 仓库不存在返回 404"""
    from codeinsight.api.versions import switch_version

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    mock_repo_result = MagicMock()
    mock_repo_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_repo_result)

    with pytest.raises(Exception) as exc_info:
        await switch_version("nonexistent", version="v1", db=mock_db, dao=mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_switch_version_target_not_found():
    """测试：API switch_version 目标版本不存在返回 404"""
    from codeinsight.api.versions import switch_version

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    mock_repo_result = MagicMock()
    mock_repo = MagicMock(id="repo-1", current_version="v1")
    mock_repo_result.scalar_one_or_none.return_value = mock_repo
    mock_db.execute = AsyncMock(return_value=mock_repo_result)

    # 目标版本不存在 — get_by_version_tag 返回 None
    mock_target_result = MagicMock()
    mock_target_result.scalar_one_or_none.return_value = None
    mock_dao.get_by_version_tag = AsyncMock(return_value=None)

    with pytest.raises(Exception) as exc_info:
        await switch_version("repo-1", version="nonexistent", db=mock_db, dao=mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_rollback_version_success():
    """测试：API rollback_version 回滚成功"""
    from codeinsight.api.versions import rollback_version

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    # 模拟仓库存在
    mock_repo_result = MagicMock()
    mock_repo = MagicMock(id="repo-1", current_version="v3")
    mock_repo_result.scalar_one_or_none.return_value = mock_repo
    mock_db.execute = AsyncMock(
        side_effect=[
            mock_repo_result,  # 查询仓库
            MagicMock(),  # flush
        ]
    )

    # 模拟目标版本存在
    mock_target_result = MagicMock()
    mock_target_result.scalar_one_or_none.return_value = FakeAV(version="v1")
    mock_dao.get_by_version_tag = AsyncMock(return_value=mock_target_result)

    result = await rollback_version(
        "repo-1",
        version="v1",
        db=mock_db,
        dao=mock_dao,
    )
    assert result["rolled_back_from"] == "v3"
    assert result["rolled_back_to"] == "v1"
    assert "rollback_record_id" in result
    assert "已回滚到版本" in result["message"]


@pytest.mark.asyncio
async def test_api_rollback_version_repo_not_found():
    """测试：API rollback_version 仓库不存在返回 404"""
    from codeinsight.api.versions import rollback_version

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    mock_repo_result = MagicMock()
    mock_repo_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_repo_result)

    with pytest.raises(Exception) as exc_info:
        await rollback_version("nonexistent", version="v1", db=mock_db, dao=mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)
