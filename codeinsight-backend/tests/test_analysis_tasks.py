"""
分析任务路由单元测试

使用 mock 测试 submit_analysis、get_task_status、cancel_task 三个端点逻辑。
覆盖正常流程、仓库不存在、任务已取消等场景。
"""

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from codeinsight.schemas import AnalysisMode, TaskStatus

# ======================== 辅助数据结构 ========================


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
    last_analyzed_at: str | None = None


# ======================== submit_analysis 测试 ========================


@pytest.mark.asyncio
async def test_submit_analysis_success():
    """测试：提交分析任务成功"""
    from codeinsight.api.analysis import submit_analysis

    mock_db = AsyncMock()
    repo_uuid = str(uuid4())
    mock_repo = FakeRepo(
        id=repo_uuid,
        name="Test Repo",
        path="/tmp/test",
        file_count=150,
    )

    # mock Celery delay 返回
    mock_celery_result = MagicMock()
    mock_celery_result.id = "test-celery-task-id"

    with (
        patch("codeinsight.api.analysis.RepositoryDAO") as mock_dao,
        patch("codeinsight.api.analysis.run_analysis") as mock_run,
    ):
        dao_instance = MagicMock()
        dao_instance.get_by_id = AsyncMock(return_value=mock_repo)
        mock_dao.return_value = dao_instance
        mock_run.delay.return_value = mock_celery_result

        result = await submit_analysis(repo_uuid, None, mock_db)

        assert result.task_id == "test-celery-task-id"
        assert str(result.repository_id) == repo_uuid
        assert result.status == TaskStatus.PENDING
        assert result.progress.percent == 0.0
        assert result.progress.files_total == 150
        mock_run.delay.assert_called_once_with(
            repository_id=repo_uuid,
            mode=AnalysisMode.FULL.value,
            agents=None,
        )


@pytest.mark.asyncio
async def test_submit_analysis_with_request():
    """测试：提交分析任务时携带请求参数"""
    from codeinsight.api.analysis import submit_analysis
    from codeinsight.schemas import AnalyzeRequest

    mock_db = AsyncMock()
    repo_uuid = str(uuid4())
    mock_repo = FakeRepo(id=repo_uuid, file_count=100)

    with (
        patch("codeinsight.api.analysis.RepositoryDAO") as mock_dao,
        patch("codeinsight.api.analysis.run_analysis") as mock_run,
    ):
        dao_instance = MagicMock()
        dao_instance.get_by_id = AsyncMock(return_value=mock_repo)
        mock_dao.return_value = dao_instance

        mock_celery_result = MagicMock()
        mock_celery_result.id = "task-123"
        mock_run.delay.return_value = mock_celery_result

        req = AnalyzeRequest(mode=AnalysisMode.FULL, agents=["design_pattern"])

        result = await submit_analysis(repo_uuid, req, mock_db)

        assert result.mode == AnalysisMode.FULL
        mock_run.delay.assert_called_once_with(
            repository_id=repo_uuid,
            mode=AnalysisMode.FULL.value,
            agents=["design_pattern"],
        )


@pytest.mark.asyncio
async def test_submit_analysis_repository_not_found():
    """测试：提交分析任务时仓库不存在返回 404"""
    from fastapi import HTTPException

    from codeinsight.api.analysis import submit_analysis

    mock_db = AsyncMock()
    fake_uuid = str(uuid4())

    with patch("codeinsight.api.analysis.RepositoryDAO") as mock_dao:
        dao_instance = MagicMock()
        dao_instance.get_by_id = AsyncMock(return_value=None)
        mock_dao.return_value = dao_instance

        with pytest.raises(HTTPException) as exc_info:
            await submit_analysis(fake_uuid, None, mock_db)
        assert exc_info.value.status_code == 404


# ======================== get_task_status 测试 ========================


@pytest.mark.asyncio
async def test_get_task_status_pending():
    """测试：查询 pending 状态的任务"""
    from codeinsight.api.analysis import get_task_status

    task_id = "test-task-id"

    mock_result = MagicMock()
    mock_result.state = "PENDING"
    mock_result.info = {}

    repo_uuid = str(uuid4())
    with (
        patch("codeinsight.api.analysis.AsyncResult") as mock_async_result,
        patch("codeinsight.api.analysis._lookup_repository") as mock_lookup,
    ):
        mock_async_result.return_value = mock_result
        mock_lookup.return_value = UUID(repo_uuid)

        result = await get_task_status(task_id)

        assert result.task_id == task_id
        assert result.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_get_task_status_completed():
    """测试：查询已完成的任务"""
    from codeinsight.api.analysis import get_task_status

    task_id = "completed-task"

    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.info = {
        "current_step": "completed",
        "percent": 100.0,
        "files_processed": 500,
        "files_total": 500,
        "knowledge_points_found": 42,
    }

    repo_uuid = str(uuid4())
    with (
        patch("codeinsight.api.analysis.AsyncResult") as mock_async_result,
        patch("codeinsight.api.analysis._lookup_repository") as mock_lookup,
    ):
        mock_async_result.return_value = mock_result
        mock_lookup.return_value = UUID(repo_uuid)

        result = await get_task_status(task_id)

        assert result.status == TaskStatus.COMPLETED
        assert result.progress.percent == 100.0
        assert result.progress.knowledge_points_found == 42


@pytest.mark.asyncio
async def test_get_task_status_failure():
    """测试：查询失败的任务"""
    from codeinsight.api.analysis import get_task_status

    task_id = "failed-task"

    mock_result = MagicMock()
    mock_result.state = "FAILURE"
    mock_result.info = Exception("Connection lost")

    repo_uuid = str(uuid4())
    with (
        patch("codeinsight.api.analysis.AsyncResult") as mock_async_result,
        patch("codeinsight.api.analysis._lookup_repository") as mock_lookup,
    ):
        mock_async_result.return_value = mock_result
        mock_lookup.return_value = UUID(repo_uuid)

        result = await get_task_status(task_id)

        assert result.status == TaskStatus.FAILED
        assert result.error_message is not None


@pytest.mark.asyncio
async def test_get_task_status_not_found():
    """测试：查询不存在的任务返回 404"""
    from fastapi import HTTPException

    from codeinsight.api.analysis import get_task_status

    task_id = "nonexistent-task"

    mock_result = MagicMock()
    # state 属性抛出异常模拟任务不存在
    type(mock_result).state = property(lambda self: (_ for _ in ()).throw(Exception("Unknown")))

    with patch("codeinsight.api.analysis.AsyncResult", return_value=mock_result):
        with pytest.raises(HTTPException) as exc_info:
            await get_task_status(task_id)
        assert exc_info.value.status_code == 404


# ======================== cancel_task 测试 ========================


@pytest.mark.asyncio
async def test_cancel_task_success():
    """测试：取消正在执行的任务"""
    from codeinsight.api.analysis import cancel_task

    task_id = "running-task"

    mock_result = MagicMock()
    mock_result.state = "STARTED"

    mock_app = MagicMock()
    mock_app.control.revoke.return_value = True

    with (
        patch("codeinsight.api.analysis.AsyncResult", return_value=mock_result),
        patch("codeinsight.api.analysis.celery_app", mock_app),
    ):
        result = await cancel_task(task_id)

        assert "cancellation requested" in result["message"]
        mock_app.control.revoke.assert_called_once_with(task_id, terminate=True)


@pytest.mark.asyncio
async def test_cancel_task_already_completed():
    """测试：取消已完成的任务，直接返回无需撤销"""
    from codeinsight.api.analysis import cancel_task

    task_id = "done-task"

    mock_result = MagicMock()
    mock_result.state = "SUCCESS"

    with patch("codeinsight.api.analysis.AsyncResult", return_value=mock_result):
        result = await cancel_task(task_id)

        assert "already success" in result["message"]


@pytest.mark.asyncio
async def test_cancel_task_already_failed():
    """测试：取消已失败的任务，直接返回无需撤销"""
    from codeinsight.api.analysis import cancel_task

    task_id = "failed-task"

    mock_result = MagicMock()
    mock_result.state = "FAILURE"

    with patch("codeinsight.api.analysis.AsyncResult", return_value=mock_result):
        result = await cancel_task(task_id)

        assert "already failure" in result["message"]


@pytest.mark.asyncio
async def test_cancel_task_not_found():
    """测试：取消不存在的任务返回 404"""
    from fastapi import HTTPException

    from codeinsight.api.analysis import cancel_task

    task_id = "ghost-task"

    mock_result = MagicMock()
    type(mock_result).state = property(lambda self: (_ for _ in ()).throw(Exception("Unknown")))

    with patch("codeinsight.api.analysis.AsyncResult", return_value=mock_result):
        with pytest.raises(HTTPException) as exc_info:
            await cancel_task(task_id)
        assert exc_info.value.status_code == 404


# ======================== Redis 映射测试 ========================


@pytest.mark.asyncio
async def test_redis_mapping_on_submit():
    """测试：提交任务时将 task_id → repository_id 写入 Redis"""
    from codeinsight.api.analysis import submit_analysis

    mock_db = AsyncMock()
    repo_uuid = str(uuid4())
    mock_repo = FakeRepo(id=repo_uuid, file_count=10)

    mock_celery_result = MagicMock()
    mock_celery_result.id = "mapped-task-id"

    with (
        patch("codeinsight.api.analysis.RepositoryDAO") as mock_dao,
        patch("codeinsight.api.analysis.run_analysis") as mock_run,
        patch("codeinsight.api.analysis.get_redis_client") as mock_get_redis,
    ):
        dao_instance = MagicMock()
        dao_instance.get_by_id = AsyncMock(return_value=mock_repo)
        mock_dao.return_value = dao_instance
        mock_run.delay.return_value = mock_celery_result

        mock_redis = mock_get_redis.return_value
        mock_redis.get.return_value = None

        await submit_analysis(repo_uuid, None, mock_db)

        mock_get_redis.assert_called()
        assert mock_redis.set.call_count == 3
        first_call = mock_redis.set.call_args_list[0]
        assert first_call[0][0] == "task:mapped-task-id:repo"
        assert first_call[0][1] == repo_uuid
        second_call = mock_redis.set.call_args_list[1]
        assert second_call[0][0] == "task:mapped-task-id:mode"
        assert second_call[0][1] == "full"


@pytest.mark.asyncio
async def test_submit_analysis_rejects_duplicate_active_task():
    """测试：仓库已有活跃任务时重复提交返回 409"""
    from fastapi import HTTPException

    from codeinsight.api.analysis import submit_analysis

    mock_db = AsyncMock()
    repo_uuid = str(uuid4())
    mock_repo = FakeRepo(id=repo_uuid, file_count=10)

    with (
        patch("codeinsight.api.analysis.RepositoryDAO") as mock_dao,
        patch("codeinsight.api.analysis.run_analysis") as mock_run,
        patch("codeinsight.api.analysis.get_redis_client") as mock_get_redis,
    ):
        dao_instance = MagicMock()
        dao_instance.get_by_id = AsyncMock(return_value=mock_repo)
        mock_dao.return_value = dao_instance

        mock_redis = mock_get_redis.return_value
        mock_redis.get.return_value = "existing-task-id"

        with pytest.raises(HTTPException) as exc_info:
            await submit_analysis(repo_uuid, None, mock_db)
        assert exc_info.value.status_code == 409
        mock_run.delay.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_task_clears_active_task_marker():
    """测试：取消任务后清理 Redis 中的活跃任务标记"""
    from codeinsight.api.analysis import cancel_task

    task_id = "running-task"

    mock_result = MagicMock()
    mock_result.state = "STARTED"

    mock_app = MagicMock()
    mock_app.control.revoke.return_value = True

    mock_redis = MagicMock()
    mock_redis.get.return_value = "some-repo-id"

    with (
        patch("codeinsight.api.analysis.AsyncResult", return_value=mock_result),
        patch("codeinsight.api.analysis.celery_app", mock_app),
        patch("codeinsight.api.analysis.get_redis_client", return_value=mock_redis),
    ):
        result = await cancel_task(task_id)

        assert "cancellation requested" in result["message"]
        mock_redis.delete.assert_called_once_with("repo:some-repo-id:active_task")
        cancel_calls = [c for c in mock_redis.set.call_args_list if "cancel" in c[0][0]]
        assert len(cancel_calls) == 1


@pytest.mark.asyncio
async def test_lookup_repository_from_redis():
    """测试：从 Redis 查找 repository_id"""
    from codeinsight.api.analysis import _lookup_repository

    mock_redis = MagicMock()
    test_uuid = str(uuid4())
    mock_redis.get.return_value = test_uuid

    with patch("codeinsight.api.analysis.get_redis_client", return_value=mock_redis):
        result = _lookup_repository("some-task-id")
        assert str(result) == test_uuid


@pytest.mark.asyncio
async def test_lookup_repository_redis_error():
    """测试：Redis 出错时返回占位 UUID"""
    import redis as redis_lib

    from codeinsight.api.analysis import _lookup_repository

    mock_redis = MagicMock()
    mock_redis.get.side_effect = redis_lib.RedisError("connection refused")

    with patch("codeinsight.api.analysis.get_redis_client", return_value=mock_redis):
        result = _lookup_repository("some-task-id")
        assert result == UUID("00000000-0000-0000-0000-000000000000")


# ======================== 细粒度取消测试 ========================


def test_check_cancelled_no_flag():
    """测试：Redis 中无取消标志时正常通过"""
    from codeinsight.tasks.analysis_tasks import _check_cancelled

    mock_self = MagicMock()
    mock_self.request.id = "task-123"

    with patch("codeinsight.tasks.analysis_tasks.get_redis_client") as mock_redis_cls:
        mock_redis = mock_redis_cls.return_value
        mock_redis.get.return_value = None

        _check_cancelled(mock_self, "task-123")

        mock_redis.get.assert_called_once_with("task:task-123:cancel")


def test_check_cancelled_with_flag_raises():
    """测试：Redis 中存在取消标志时抛出 CancelledError"""
    from codeinsight.tasks.analysis_tasks import CancelledError, _check_cancelled

    mock_self = MagicMock()
    mock_self.request.id = "task-456"

    with patch("codeinsight.tasks.analysis_tasks.get_redis_client") as mock_redis_cls:
        mock_redis = mock_redis_cls.return_value
        mock_redis.get.return_value = "1"

        with pytest.raises(CancelledError):
            _check_cancelled(mock_self, "task-456")

        # 取消标志应被删除
        mock_redis.delete.assert_called_once_with("task:task-456:cancel")


def test_check_cancelled_redis_error_silenced():
    """测试：Redis 出错时不影响任务执行（降级处理）"""
    import redis as redis_lib

    from codeinsight.tasks.analysis_tasks import _check_cancelled

    mock_self = MagicMock()

    with patch("codeinsight.tasks.analysis_tasks.get_redis_client") as mock_redis_cls:
        mock_redis = mock_redis_cls.return_value
        mock_redis.get.side_effect = redis_lib.RedisError("connection refused")

        # 不应抛出异常
        _check_cancelled(mock_self, "task-789")


def test_run_analysis_cancellation_at_scanning_phase():
    """测试：在 scanning 阶段检测到取消标志时终止任务"""
    from codeinsight.tasks.analysis_tasks import CancelledError, run_analysis

    repo_uuid = str(uuid4())

    mock_self = MagicMock()
    mock_self.request.id = "cancel-at-scanning"

    # asyncio.run 需要返回 (None, None) 给 _get_in_progress_version，其余返回 MagicMock
    _asyncio_run_calls = [0]  # 可变计数器（避免 closure 限制）

    def _mock_asyncio_run_impl(*args, **kwargs):
        if _asyncio_run_calls[0] == 0:
            _asyncio_run_calls[0] += 1
            return (None, None)  # _get_in_progress_version
        _asyncio_run_calls[0] += 1
        return MagicMock()  # 其余调用

    mock_asyncio_run = MagicMock(side_effect=_mock_asyncio_run_impl)

    with (
        patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
        patch("codeinsight.tasks.analysis_tasks._update_progress") as mock_progress,
        patch("codeinsight.tasks.analysis_tasks._check_cancelled") as mock_check,
        patch("codeinsight.tasks.analysis_tasks.GitScanner") as mock_scanner_cls,
    ):
        # 第一次调用 _check_cancelled (scanning 阶段) 抛出 CancelledError
        mock_check.side_effect = [CancelledError("cancelled")]

        mock_scanner_instance = MagicMock()
        mock_scanner_cls.return_value = mock_scanner_instance

        with pytest.raises(CancelledError):
            run_analysis.__wrapped__.__func__(mock_self, repo_uuid, "full")

        # 确认在 scanning 阶段之后调用了取消检查
        assert mock_check.call_count == 1
        # 确认状态更新至少到达 scanning（1 次：scanning）
        assert mock_progress.call_count >= 1


def test_run_analysis_cancellation_at_parsing_phase():
    """测试：在 parsing 阶段检测到取消标志时终止任务"""
    from codeinsight.tasks.analysis_tasks import CancelledError, run_analysis

    repo_uuid = str(uuid4())

    mock_self = MagicMock()
    mock_self.request.id = "cancel-at-parsing"

    mock_scan_result = MagicMock()
    mock_scan_result.total_count = 10
    mock_scan_result.total_lines = 100
    mock_scan_result.language_distribution = {"python": 5, "typescript": 5}
    mock_scan_result.files = []

    # 复用 _mock_asyncio_run_impl：第一次返回 (None, None)
    _asyncio_run_calls = [0]

    def _mock_asyncio_run_impl(*args, **kwargs):
        if _asyncio_run_calls[0] == 0:
            _asyncio_run_calls[0] += 1
            return (None, None)
        _asyncio_run_calls[0] += 1
        return MagicMock()

    mock_asyncio_run = MagicMock(side_effect=_mock_asyncio_run_impl)

    with (
        patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
        patch("codeinsight.tasks.analysis_tasks._update_progress"),
        patch("codeinsight.tasks.analysis_tasks._check_cancelled") as mock_check,
        patch("codeinsight.tasks.analysis_tasks.GitScanner") as mock_scanner_cls,
    ):
        # scanning 通过，parsing 阶段取消
        mock_check.side_effect = [None, CancelledError("cancelled")]

        mock_scanner_instance = MagicMock()
        mock_scanner_instance.scan.return_value = mock_scan_result
        mock_scanner_cls.return_value = mock_scanner_instance

        with pytest.raises(CancelledError):
            run_analysis.__wrapped__.__func__(mock_self, repo_uuid, "full")

        # 确认在 scanning 阶段之后，parsing 阶段调用了取消检查
        assert mock_check.call_count == 2


def test_run_analysis_cancellation_at_storing_phase():
    """测试：在 storing 阶段检测到取消标志时终止任务"""
    from codeinsight.tasks.analysis_tasks import CancelledError, run_analysis

    repo_uuid = str(uuid4())

    mock_self = MagicMock()
    mock_self.request.id = "cancel-at-storing"

    mock_scan_result = MagicMock()
    mock_scan_result.total_count = 10
    mock_scan_result.total_lines = 100
    mock_scan_result.language_distribution = {"python": 5, "typescript": 5}
    mock_scan_result.files = []

    _asyncio_run_calls = [0]

    def _mock_asyncio_run_impl(*args, **kwargs):
        if _asyncio_run_calls[0] == 0:
            _asyncio_run_calls[0] += 1
            return (None, None)
        _asyncio_run_calls[0] += 1
        return MagicMock()

    mock_asyncio_run = MagicMock(side_effect=_mock_asyncio_run_impl)

    with (
        patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
        patch("codeinsight.tasks.analysis_tasks._update_progress") as mock_progress,
        patch("codeinsight.tasks.analysis_tasks._check_cancelled") as mock_check,
        patch("codeinsight.tasks.analysis_tasks.GitScanner") as mock_scanner_cls,
    ):
        # scanning, parsing, analyzing 通过，storing 阶段取消
        mock_check.side_effect = [None, None, None, CancelledError("cancelled")]

        mock_scanner_instance = MagicMock()
        mock_scanner_instance.scan.return_value = mock_scan_result
        mock_scanner_cls.return_value = mock_scanner_instance

        with pytest.raises(CancelledError):
            run_analysis.__wrapped__.__func__(mock_self, repo_uuid, "full")

        # 确认在 storing 阶段之前都通过了
        assert mock_check.call_count == 4
        assert mock_progress.call_count >= 4


def test_run_analysis_no_cancellation_completes_normally():
    """测试：无取消标志时任务正常完成"""
    from codeinsight.tasks.analysis_tasks import run_analysis

    repo_uuid = str(uuid4())

    mock_self = MagicMock()
    mock_self.request.id = "normal-task"

    mock_scan_result = MagicMock()
    mock_scan_result.total_count = 10
    mock_scan_result.total_lines = 100
    mock_scan_result.language_distribution = {"python": 5, "typescript": 5}
    mock_scan_result.files = []

    _asyncio_run_calls = [0]

    def _mock_asyncio_run_impl(*args, **kwargs):
        if _asyncio_run_calls[0] == 0:
            _asyncio_run_calls[0] += 1
            return (None, None)  # _get_in_progress_version
        _asyncio_run_calls[0] += 1
        return MagicMock()

    mock_asyncio_run = MagicMock(side_effect=_mock_asyncio_run_impl)

    with (
        patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
        patch("codeinsight.tasks.analysis_tasks._update_progress"),
        patch("codeinsight.tasks.analysis_tasks._check_cancelled") as mock_check,
        patch("codeinsight.tasks.analysis_tasks.GitScanner") as mock_scanner_cls,
    ):
        mock_check.return_value = None  # 无取消

        mock_scanner_instance = MagicMock()
        mock_scanner_instance.scan.return_value = mock_scan_result
        mock_scanner_cls.return_value = mock_scanner_instance

        result = run_analysis.__wrapped__.__func__(mock_self, repo_uuid, "full")

        assert result["status"] == "completed"
        assert "version_tag" in result
        # 5 个阶段都应检查取消（新增 Step 4: 结构分析）
        assert mock_check.call_count == 5
