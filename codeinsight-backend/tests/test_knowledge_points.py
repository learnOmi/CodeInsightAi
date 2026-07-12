"""
知识点管理 CRUD 单元测试

使用 mock 直接测试 KnowledgePointDAO 层方法和 API 端点逻辑。
覆盖 CRUD 操作、分页查询、筛选统计等场景。
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codeinsight.repositories.knowledge_point import KnowledgePointDAO

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
    dao = KnowledgePointDAO()
    data = {
        "title": "Factory Pattern",
        "category": "DP-",
        "version": "v1",
        "repository_id": str(uuid4()),
        "confidence": 0.92,
        "tags": ["Factory"],
        "description": "A design pattern",
        "code_snippets": [],
        "call_chain": [],
        "expansion": {},
    }

    async def fake_refresh(obj):
        obj.id = str(uuid4())

    mock_session.refresh = fake_refresh

    kp = await dao.create(mock_session, data)
    assert kp.title == "Factory Pattern"
    assert kp.category == "DP-"
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_dao_get_by_id_found(mock_session):
    """测试：DAO get_by_id 找到记录"""
    dao = KnowledgePointDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock(id=str(uuid4()), title="Found Point")
    mock_session.execute = AsyncMock(return_value=mock_result)

    kp = await dao.get_by_id(mock_session, str(uuid4()))
    assert kp is not None
    assert kp.title == "Found Point"


@pytest.mark.asyncio
async def test_dao_get_by_id_not_found(mock_session):
    """测试：DAO get_by_id 未找到记录"""
    dao = KnowledgePointDAO()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    kp = await dao.get_by_id(mock_session, "nonexistent")
    assert kp is None


@pytest.mark.asyncio
async def test_dao_list(mock_session):
    """测试：DAO list 分页查询"""
    dao = KnowledgePointDAO()
    mock_result = MagicMock()
    mock_kps = [MagicMock(id=str(uuid4()), title=f"Point {i}") for i in range(3)]
    mock_result.scalars.return_value.all.return_value = mock_kps
    mock_session.execute = AsyncMock(return_value=mock_result)

    kps = await dao.list(mock_session, repository_id=str(uuid4()), skip=0, limit=10)
    assert len(kps) == 3


@pytest.mark.asyncio
async def test_dao_list_with_filters(mock_session):
    """测试：DAO list 带版本/分类/标签筛选"""
    dao = KnowledgePointDAO()
    mock_result = MagicMock()
    mock_kps = [MagicMock(id=str(uuid4()), category="DP-")]
    mock_result.scalars.return_value.all.return_value = mock_kps
    mock_session.execute = AsyncMock(return_value=mock_result)

    kps = await dao.list(
        mock_session,
        repository_id=str(uuid4()),
        version="v1",
        category="DP-",
        tag="Factory",
        skip=0,
        limit=20,
    )
    assert isinstance(kps, list)
    assert len(kps) == 1


@pytest.mark.asyncio
async def test_dao_count(mock_session):
    """测试：DAO count 统计数量"""
    dao = KnowledgePointDAO()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=42)))

    total = await dao.count(mock_session, repository_id=str(uuid4()))
    assert total == 42


@pytest.mark.asyncio
async def test_dao_count_with_category(mock_session):
    """测试：DAO count 按分类统计"""
    dao = KnowledgePointDAO()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=5)))

    total = await dao.count(mock_session, repository_id=str(uuid4()), category="AD-")
    assert total == 5


@pytest.mark.asyncio
async def test_dao_update(mock_session):
    """测试：DAO update 更新字段"""
    dao = KnowledgePointDAO()
    existing = MagicMock(id=str(uuid4()), title="Old Title", confidence=0.5)
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing)))

    data = {"title": "New Title", "confidence": 0.95}
    kp = await dao.update(mock_session, str(uuid4()), data)
    assert kp.title == "New Title"
    assert kp.confidence == 0.95


@pytest.mark.asyncio
async def test_dao_delete_success(mock_session):
    """测试：DAO delete 成功删除"""
    dao = KnowledgePointDAO()
    existing = MagicMock(id=str(uuid4()), title="To Delete")
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing)))

    result = await dao.delete(mock_session, str(uuid4()))
    assert result is True
    mock_session.delete.assert_called_once()


@pytest.mark.asyncio
async def test_dao_delete_not_found(mock_session):
    """测试：DAO delete 删除不存在的记录"""
    dao = KnowledgePointDAO()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await dao.delete(mock_session, "nonexistent")
    assert result is False


# ======================== API 端点逻辑测试 ========================


@pytest.mark.asyncio
async def test_api_list_knowledge_points():
    """测试：API list_knowledge_points 返回分页结果"""
    from codeinsight.api.knowledge import list_knowledge_points

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    # Mock 返回 dict，包含所有 Pydantic 嵌套模型的必需字段
    mock_kps = [
        {
            "id": str(uuid4()),
            "title": f"Point {i}",
            "category": "DP-",
            "category_name": "设计模式",
            "description": "desc",
            "confidence": 0.9,
            "tags": [],
            "code_snippets": [],
            "call_chain": [],
            "expansion": {"principle": "test"},
            "repository_id": str(uuid4()),
            "version": "v1",
            "created_at": "2026-07-09T00:00:00Z",
            "updated_at": "2026-07-09T00:00:00Z",
            "knowledge_metadata": {"agent": "test", "prompt_version": "v1", "model": "claude"},
        }
        for i in range(5)
    ]
    mock_dao.list = AsyncMock(return_value=mock_kps)
    mock_dao.count = AsyncMock(return_value=5)

    result = await list_knowledge_points(
        repository_id=str(uuid4()),
        page=1,
        page_size=20,
        version=None,
        category=None,
        tag=None,
        sort_by="created_at",
        sort_order="desc",
        db=mock_db,
        dao=mock_dao,
    )
    assert result.total == 5
    assert result.page == 1
    assert result.page_size == 20
    assert result.total_pages == 1
    assert len(result.items) == 5


@pytest.mark.asyncio
async def test_api_list_knowledge_points_with_category_filter():
    """测试：API list_knowledge_points 带分类筛选"""
    from codeinsight.api.knowledge import list_knowledge_points

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.list = AsyncMock(return_value=[])
    mock_dao.count = AsyncMock(return_value=0)

    result = await list_knowledge_points(
        repository_id=str(uuid4()),
        category="AD-",
        page=1,
        page_size=20,
        version=None,
        tag=None,
        sort_by="created_at",
        sort_order="desc",
        db=mock_db,
        dao=mock_dao,
    )
    assert result.total == 0
    assert len(result.items) == 0


@pytest.mark.asyncio
async def test_api_list_knowledge_points_pagination():
    """测试：API list_knowledge_points 分页计算正确"""
    from codeinsight.api.knowledge import list_knowledge_points

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.list = AsyncMock(return_value=[])
    mock_dao.count = AsyncMock(return_value=25)

    result = await list_knowledge_points(
        repository_id=str(uuid4()),
        page=2,
        page_size=10,
        version=None,
        category=None,
        tag=None,
        sort_by="created_at",
        sort_order="desc",
        db=mock_db,
        dao=mock_dao,
    )
    assert result.total == 25
    assert result.total_pages == 3  # ceil(25/10)


@pytest.mark.asyncio
async def test_api_get_knowledge_point_found():
    """测试：API get_knowledge_point 找到记录"""
    from codeinsight.api.knowledge import get_knowledge_point

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_kp = MagicMock(
        id=str(uuid4()),
        title="Factory Pattern",
        category="DP-",
        confidence=0.92,
        version="v1",
        repository_id=str(uuid4()),
        created_at="2026-07-09T00:00:00Z",
        updated_at="2026-07-09T00:00:00Z",
    )
    mock_dao.get_by_id = AsyncMock(return_value=mock_kp)

    result = await get_knowledge_point(str(uuid4()), mock_db, mock_dao)
    assert result.title == "Factory Pattern"


@pytest.mark.asyncio
async def test_api_get_knowledge_point_not_found():
    """测试：API get_knowledge_point 未找到记录返回 404"""
    from codeinsight.api.knowledge import get_knowledge_point

    mock_db = AsyncMock()
    mock_dao = MagicMock()
    mock_dao.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(Exception) as exc_info:
        await get_knowledge_point("nonexistent", mock_db, mock_dao)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_get_knowledge_stats():
    """测试：API get_knowledge_stats 返回统计数据"""

    from codeinsight.api.knowledge import get_knowledge_stats

    mock_db = AsyncMock()
    mock_dao = MagicMock()

    # 3 次查询：
    # 1. by_category 分组查询
    # 2. total 计数查询
    # 3. by_confidence 分组查询

    # 模拟第一次查询结果（by_category 分组）
    mock_category_result = MagicMock()
    mock_category_result.tuples.return_value = [
        ("DP-", 5),
        ("AD-", 2),
        ("AL-", 1),
        ("ET-", 1),
        ("DK-", 1),
    ]

    # 模拟第二次查询结果（total 计数）
    mock_total_result = MagicMock()
    mock_total_result.scalar.return_value = 10

    # 模拟第三次查询结果（by_confidence 分组）
    mock_confidence_result = MagicMock()
    mock_confidence_result.tuples.return_value = [
        (0.9, 7),
        (0.6, 2),
        (0.3, 1),
    ]

    # 按调用顺序返回不同结果
    mock_db.execute = AsyncMock(
        side_effect=[
            mock_category_result,
            mock_total_result,
            mock_confidence_result,
        ]
    )

    result = await get_knowledge_stats(
        repository_id=str(uuid4()),
        version=None,
        db=mock_db,
        dao=mock_dao,
    )
    assert result.total_points == 10
    assert result.by_category["DP-"] == 5
    assert result.by_confidence["high"] == 7
    assert result.by_confidence["medium"] == 2
    assert result.by_confidence["low"] == 1
