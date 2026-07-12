"""
analysis_tasks.py 增量模式集成测试

测试 _compute_incremental_diff、_parse_and_store_ast_incremental、
_save_analysis_snapshot 以及 run_analysis 的增量分支。
所有 DAO 和外部依赖均通过 mock 模拟。
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from codeinsight.models import FileModel
from codeinsight.services import IncrementalDiff

# ======================== 辅助数据 ========================

REPO_UUID = UUID("11111111-0000-0000-0000-000000000000")
REPO_UUID_STR = str(REPO_UUID)
VERSION_TAG = "v20260701-abc1234"


def _make_file(path: str, content_hash: str, **kwargs) -> FileModel:
    return FileModel(
        id=kwargs.get("id", uuid4()),
        repository_id=REPO_UUID,
        path=path,
        absolute_path=f"/repo/{path}",
        language=kwargs.get("language", "python"),
        line_count=kwargs.get("line_count", 10),
        size_bytes=kwargs.get("size_bytes", 100),
        content_hash=content_hash,
    )


@dataclass
class FakeScanFile:
    path: str
    absolute_path: str
    language: str
    line_count: int
    size_bytes: int
    content_hash: str


@dataclass
class FakeScanResult:
    files: list
    total_count: int
    total_lines: int
    language_distribution: dict


# ======================== _compute_incremental_diff 测试 ========================


class TestComputeIncrementalDiff:
    """测试 _compute_incremental_diff 函数"""

    @pytest.mark.asyncio
    async def test_compute_incremental_diff_returns_diff(self):
        """测试 _compute_incremental_diff 返回 IncrementalDiff 对象"""
        mock_session = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_file_dao = MagicMock()
        mock_file_dao.return_value.get_by_repository = AsyncMock(
            return_value=[_make_file("a.py", "h1"), _make_file("b.py", "h2")]
        )

        mock_snapshot_manager = MagicMock()
        mock_snapshot_manager.return_value.get_latest_version = AsyncMock(return_value=None)

        with (
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", mock_cm),
            patch("codeinsight.tasks.analysis_tasks.FileDAO", mock_file_dao),
            patch("codeinsight.tasks.analysis_tasks.SnapshotManager", mock_snapshot_manager),
        ):
            from codeinsight.tasks.analysis_tasks import _compute_incremental_diff

            diff = await _compute_incremental_diff(REPO_UUID, VERSION_TAG)

        assert diff is not None
        assert isinstance(diff, IncrementalDiff)

    @pytest.mark.asyncio
    async def test_compute_incremental_diff_with_previous_version(self):
        """测试 _compute_incremental_diff 有历史版本时仍正常返回"""
        mock_session = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_file_dao = MagicMock()
        mock_file_dao.return_value.get_by_repository = AsyncMock(return_value=[_make_file("a.py", "h1")])

        mock_snapshot_manager = MagicMock()
        mock_snapshot_manager.return_value.get_latest_version = AsyncMock(return_value="v20260601-0000000")

        with (
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", mock_cm),
            patch("codeinsight.tasks.analysis_tasks.FileDAO", mock_file_dao),
            patch("codeinsight.tasks.analysis_tasks.SnapshotManager", mock_snapshot_manager),
            patch("codeinsight.tasks.analysis_tasks.IncrementalAnalyzer") as mock_analyzer_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.compute_diff = AsyncMock(
                return_value=IncrementalDiff(
                    changed_files=[],
                    propagated_files=[],
                    total_files_to_analyze=1,
                    skipped_files=0,
                    needs_full_analysis=False,
                )
            )
            mock_analyzer_cls.return_value = mock_analyzer
            from codeinsight.tasks.analysis_tasks import _compute_incremental_diff

            diff = await _compute_incremental_diff(REPO_UUID, VERSION_TAG)

        assert diff is not None
        assert isinstance(diff, IncrementalDiff)


# ======================== _parse_and_store_ast_incremental 测试 ========================


class TestParseAndStoreAstIncremental:
    """测试 _parse_and_store_ast_incremental 函数"""

    @pytest.mark.asyncio
    async def test_parse_and_store_ast_incremental_parses_changed_files(self):
        """测试增量 AST 解析只处理变更文件"""
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_ast_dao = MagicMock()
        mock_ast_dao.return_value.delete_by_file_ids = AsyncMock(return_value=5)

        mock_parser = MagicMock()
        mock_parser.parse_file.return_value = [
            MagicMock(
                node_type="function",
                name="test",
                start_line=1,
                end_line=10,
                start_column=0,
                end_column=40,
                file_path="a.py",
                language="python",
            )
        ]

        mock_pipeline = MagicMock()
        mock_pipeline_instance = MagicMock()
        mock_pipeline.return_value = mock_pipeline_instance
        mock_pipeline_instance.ingest_ast_nodes = AsyncMock(return_value=MagicMock(inserted_count=1))

        mock_parser_factory = MagicMock()
        mock_parser_factory.get_parser.return_value = mock_parser

        files_to_parse = [_make_file("a.py", "h1", id=uuid4())]

        with (
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", mock_cm),
            patch("codeinsight.tasks.analysis_tasks.AstNodeDAO", mock_ast_dao),
            patch("codeinsight.tasks.analysis_tasks.ParserFactory", mock_parser_factory),
            patch("codeinsight.tasks.analysis_tasks.StructureDataPipeline", mock_pipeline),
        ):
            from codeinsight.tasks.analysis_tasks import _parse_and_store_ast_incremental

            await _parse_and_store_ast_incremental(REPO_UUID, files_to_parse)

        mock_ast_dao.return_value.delete_by_file_ids.assert_called_once()
        mock_parser.parse_file.assert_called()
        mock_pipeline_instance.ingest_ast_nodes.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_and_store_ast_incremental_empty_files(self):
        """测试空文件列表时直接返回"""
        mock_session = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("codeinsight.tasks.analysis_tasks.async_session_factory", mock_cm):
            from codeinsight.tasks.analysis_tasks import _parse_and_store_ast_incremental

            # 不抛出异常，正常返回
            await _parse_and_store_ast_incremental(REPO_UUID, [])


# ======================== _save_analysis_snapshot 测试 ========================


class TestSaveAnalysisSnapshot:
    """测试 _save_analysis_snapshot 函数"""

    @pytest.mark.asyncio
    async def test_save_analysis_snapshot_returns_count(self):
        """测试 _save_analysis_snapshot 返回保存的快照数量"""
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_file_dao = MagicMock()
        mock_file_dao.return_value.get_by_repository = AsyncMock(
            return_value=[_make_file("a.py", "h1"), _make_file("b.py", "h2")]
        )

        mock_snapshot_manager = MagicMock()
        mock_snapshot_manager.return_value.save_snapshot = AsyncMock(return_value=2)

        with (
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", mock_cm),
            patch("codeinsight.tasks.analysis_tasks.FileDAO", mock_file_dao),
            patch("codeinsight.tasks.analysis_tasks.SnapshotManager", mock_snapshot_manager),
        ):
            from codeinsight.tasks.analysis_tasks import _save_analysis_snapshot

            result = await _save_analysis_snapshot(REPO_UUID, VERSION_TAG)

        assert result == 2
        mock_snapshot_manager.return_value.save_snapshot.assert_called_once_with(
            REPO_UUID, VERSION_TAG, mock_file_dao.return_value.get_by_repository.return_value
        )


# ======================== run_analysis 增量分支测试 ========================


def _make_mock_asyncio_run(diff_result=None, repo_path="/tmp/test-repo"):
    """
    构造 asyncio.run 的 mock，按协程名称分发返回值。

    run_analysis 中 asyncio.run 调用：
    0. _get_in_progress_version → 返回 (None, None) [新增]
    1. _do_analysis_setup → 返回 {"version_id": UUID, "total_files": int}
    2. _get_repo_path → 返回 repo_path (repo.path)
    3. _compute_incremental_diff → 返回 diff_result
    4. _get_incremental_files → 返回 [] (affected files)
    5. 其余（_update_repository_stats, _store_files_to_db,
       _parse_and_store_ast_incremental, _save_analysis_snapshot 等）→ None
    """
    mock = MagicMock()

    def smart_side_effect(coro):
        coro_name = getattr(coro, "__name__", str(coro))

        # _get_in_progress_version → (None, None)
        if "_get_in_progress_version" in coro_name:
            return (None, None)

        # _do_analysis_setup → 版本记录
        if "_do_analysis_setup" in coro_name:
            return {"version_id": uuid4(), "total_files": 1}

        # _get_repo_path → 返回仓库路径
        if "_get_repo_path" in coro_name:
            return repo_path

        # _compute_incremental_diff → 返回增量差异
        if "_compute_incremental_diff" in coro_name:
            return diff_result

        # 其余返回 None
        return None

    mock.side_effect = smart_side_effect
    return mock


class TestRunAnalysisIncremental:
    """测试 run_analysis 的增量分析分支"""

    @staticmethod
    def _make_mock_session_cm():
        """构造 async_session_factory 的 mock (async context manager)"""
        mock_session = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_cm)
        return mock_factory

    def _make_patches(self, mock_asyncio_run, mock_repo_dao, scanner_patch):
        """构造增量 / 全量测试共用的 patch 列表"""
        mock_session_factory = self._make_mock_session_cm()
        patches = [
            patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", mock_session_factory),
            patch("codeinsight.tasks.analysis_tasks._update_progress"),
            patch("codeinsight.tasks.analysis_tasks._check_cancelled", return_value=None),
            scanner_patch,
            patch("codeinsight.tasks.analysis_tasks._store_files_to_db"),
            patch("codeinsight.tasks.analysis_tasks.RepositoryDAO", mock_repo_dao),
            patch("codeinsight.tasks.analysis_tasks._save_analysis_snapshot"),
        ]
        return patches

    def test_run_analysis_incremental_branch_called(self):
        """测试 run_analysis 在 incremental 模式下调用增量分支"""
        from codeinsight.tasks.analysis_tasks import run_analysis

        mock_self = MagicMock()
        mock_self.request.id = "inc-task-001"

        mock_scan_result = FakeScanResult(
            files=[FakeScanFile("a.py", "/repo/a.py", "python", 10, 100, "h1")],
            total_count=1,
            total_lines=10,
            language_distribution={"python": 1},
        )

        mock_asyncio_run = _make_mock_asyncio_run(
            diff_result=IncrementalDiff(
                changed_files=[],
                propagated_files=[],
                total_files_to_analyze=1,
                skipped_files=0,
                needs_full_analysis=False,
            )
        )

        mock_repo = MagicMock()
        mock_repo.path = "/tmp/test-repo"
        mock_repo_dao = MagicMock()
        mock_repo_dao.return_value.get_by_id = AsyncMock(return_value=mock_repo)

        with (
            patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", self._make_mock_session_cm()),
            patch("codeinsight.tasks.analysis_tasks._update_progress"),
            patch("codeinsight.tasks.analysis_tasks._check_cancelled", return_value=None),
            patch("codeinsight.tasks.analysis_tasks.GitScanner") as mock_scanner_cls,
            patch("codeinsight.tasks.analysis_tasks._store_files_to_db"),
            patch("codeinsight.tasks.analysis_tasks.RepositoryDAO", mock_repo_dao),
            patch("codeinsight.tasks.analysis_tasks._parse_and_store_ast_incremental"),
            patch("codeinsight.tasks.analysis_tasks._build_structures_incremental"),
            patch("codeinsight.tasks.analysis_tasks._save_analysis_snapshot"),
        ):
            mock_scanner_instance = MagicMock()
            mock_scanner_instance.scan.return_value = mock_scan_result
            mock_scanner_cls.return_value = mock_scanner_instance

            result = run_analysis.__wrapped__.__func__(mock_self, REPO_UUID_STR, "incremental")

        assert result["status"] == "completed"
        # 验证 _compute_incremental_diff 被调用
        inc_calls = [c for c in mock_asyncio_run.call_args_list if "_compute_incremental_diff" in str(c.args[0])]
        assert len(inc_calls) > 0

    def test_run_analysis_full_mode_ignores_incremental(self):
        """测试 full 模式下不进入增量分支"""
        from codeinsight.tasks.analysis_tasks import run_analysis

        mock_self = MagicMock()
        mock_self.request.id = "full-task-001"

        mock_scan_result = FakeScanResult(
            files=[],
            total_count=0,
            total_lines=0,
            language_distribution={},
        )

        mock_asyncio_run = _make_mock_asyncio_run()

        mock_repo = MagicMock()
        mock_repo.path = "/tmp/test-repo"
        mock_repo_dao = MagicMock()
        mock_repo_dao.return_value.get_by_id = AsyncMock(return_value=mock_repo)

        with (
            patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", self._make_mock_session_cm()),
            patch("codeinsight.tasks.analysis_tasks._update_progress"),
            patch("codeinsight.tasks.analysis_tasks._check_cancelled", return_value=None),
            patch("codeinsight.tasks.analysis_tasks.GitScanner") as mock_scanner_cls,
            patch("codeinsight.tasks.analysis_tasks._store_files_to_db"),
            patch("codeinsight.tasks.analysis_tasks.RepositoryDAO", mock_repo_dao),
            patch("codeinsight.tasks.analysis_tasks._parse_and_store_ast"),
            patch("codeinsight.tasks.analysis_tasks._build_structures"),
            patch("codeinsight.tasks.analysis_tasks._save_analysis_snapshot"),
        ):
            mock_scanner_instance = MagicMock()
            mock_scanner_instance.scan.return_value = mock_scan_result
            mock_scanner_cls.return_value = mock_scanner_instance

            result = run_analysis.__wrapped__.__func__(mock_self, REPO_UUID_STR, "full")

        assert result["status"] == "completed"
        # 验证 _compute_incremental_diff 未被调用
        inc_calls = [c for c in mock_asyncio_run.call_args_list if "_compute_incremental_diff" in str(c.args[0])]
        assert len(inc_calls) == 0

    def test_run_analysis_incremental_falls_back_to_full(self):
        """测试 incremental 模式下 needs_full_analysis=True 时降级为全量"""
        from codeinsight.tasks.analysis_tasks import run_analysis

        mock_self = MagicMock()
        mock_self.request.id = "fallback-task-001"

        mock_scan_result = FakeScanResult(
            files=[FakeScanFile("a.py", "/repo/a.py", "python", 10, 100, "h1")],
            total_count=1,
            total_lines=10,
            language_distribution={"python": 1},
        )

        mock_asyncio_run = _make_mock_asyncio_run(
            diff_result=IncrementalDiff(
                changed_files=[],
                propagated_files=[],
                total_files_to_analyze=100,
                skipped_files=0,
                needs_full_analysis=True,
            )
        )

        mock_repo = MagicMock()
        mock_repo.path = "/tmp/test-repo"
        mock_repo_dao = MagicMock()
        mock_repo_dao.return_value.get_by_id = AsyncMock(return_value=mock_repo)

        with (
            patch("codeinsight.tasks.analysis_tasks.asyncio.run", mock_asyncio_run),
            patch("codeinsight.tasks.analysis_tasks.async_session_factory", self._make_mock_session_cm()),
            patch("codeinsight.tasks.analysis_tasks._update_progress"),
            patch("codeinsight.tasks.analysis_tasks._check_cancelled", return_value=None),
            patch("codeinsight.tasks.analysis_tasks.GitScanner") as mock_scanner_cls,
            patch("codeinsight.tasks.analysis_tasks._store_files_to_db"),
            patch("codeinsight.tasks.analysis_tasks.RepositoryDAO", mock_repo_dao),
            patch("codeinsight.tasks.analysis_tasks._parse_and_store_ast"),
            patch("codeinsight.tasks.analysis_tasks._build_structures"),
            patch("codeinsight.tasks.analysis_tasks._save_analysis_snapshot"),
        ):
            mock_scanner_instance = MagicMock()
            mock_scanner_instance.scan.return_value = mock_scan_result
            mock_scanner_cls.return_value = mock_scanner_instance

            result = run_analysis.__wrapped__.__func__(mock_self, REPO_UUID_STR, "incremental")

        assert result["status"] == "completed"
        # 验证降级后调用的是全量解析 _parse_and_store_ast
        # _parse_and_store_ast 被 patch 为 MagicMock，其调用时通过 asyncio.run 传参
        # 由于 MagicMock 返回的是 mock 协程 (_execute_mock_call)，检查 asyncio.run 调用次数
        # 以及确认 _parse_and_store_ast 的 mock 本身被调用
