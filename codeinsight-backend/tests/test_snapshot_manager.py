"""
SnapshotManager 单元测试

测试 save_snapshot、_cleanup_old_snapshots、get_latest_snapshot。
所有 DAO 操作均通过 mock 模拟，不需要真实数据库。
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from codeinsight.models import FileAnalysisSnapshotModel, FileModel
from codeinsight.services.snapshot_manager import SnapshotManager

# ======================== 辅助数据 ========================

REPO_UUID = UUID("11111111-0000-0000-0000-000000000000")
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


def _make_snapshot(repo_uuid: UUID, version: str, file_id: UUID, content_hash: str) -> FileAnalysisSnapshotModel:
    return FileAnalysisSnapshotModel(
        repository_id=repo_uuid,
        analysis_version=version,
        file_id=file_id,
        content_hash=content_hash,
        nodes_count=5,
        edges_count=2,
        deps_count=1,
    )


def _patch_settings(max_snapshot_versions: int = 5):
    """patch settings.incremental_max_snapshot_versions"""
    return patch(
        "codeinsight.services.snapshot_manager.settings",
        MagicMock(incremental_max_snapshot_versions=max_snapshot_versions),
    )


# ======================== save_snapshot 测试 ========================


class TestSaveSnapshot:
    """测试 save_snapshot 的快照保存逻辑"""

    @pytest.mark.asyncio
    async def test_save_new_snapshot_with_valid_data(self):
        """测试保存新快照（有效数据）"""
        mock_db = MagicMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls, _patch_settings():
            mock_dao = mock_dao_cls.return_value
            mock_dao.create_many = AsyncMock(return_value=[])
            mock_dao.get_all_versions = AsyncMock(return_value=[VERSION_TAG])
            mock_dao.delete_old_versions = AsyncMock(return_value=0)

            manager = SnapshotManager(mock_db)
            files = [_make_file("a.py", "h1"), _make_file("b.py", "h2")]

            result = await manager.save_snapshot(REPO_UUID, VERSION_TAG, files)

            assert result == 2
            mock_dao.create_many.assert_called_once()
            # 验证传入的 snapshots_data 包含两个文件的快照数据
            call_args = mock_dao.create_many.call_args[0][1]
            assert len(call_args) == 2
            assert call_args[0]["content_hash"] == "h1"
            assert call_args[1]["content_hash"] == "h2"
            # SV-6: save_snapshot 不再调用 commit，由调用者统一管理
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_snapshot_with_zero_files_returns_zero(self):
        """测试保存空文件列表时返回 0 且不执行 DAO 操作"""
        mock_db = MagicMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls:
            mock_dao = mock_dao_cls.return_value
            mock_dao.create_many = AsyncMock()

            manager = SnapshotManager(mock_db)
            files: list[FileModel] = []

            result = await manager.save_snapshot(REPO_UUID, VERSION_TAG, files)

            assert result == 0
            mock_dao.create_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_snapshot_does_not_commit(self):
        """测试 save_snapshot 不调用 commit（SV-6：由调用者统一管理事务）"""
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls, _patch_settings():
            mock_dao = mock_dao_cls.return_value
            mock_dao.create_many = AsyncMock(return_value=[])
            mock_dao.get_all_versions = AsyncMock(return_value=[VERSION_TAG])
            mock_dao.delete_old_versions = AsyncMock(return_value=0)

            manager = SnapshotManager(mock_db)
            files = [_make_file("a.py", "h1")]

            await manager.save_snapshot(REPO_UUID, VERSION_TAG, files)

            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_snapshot_with_empty_content_hash(self):
        """测试 content_hash 为空字符串的快照仍可保存（由数据库约束校验）"""
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls, _patch_settings():
            mock_dao = mock_dao_cls.return_value
            mock_dao.create_many = AsyncMock(return_value=[])
            mock_dao.get_all_versions = AsyncMock(return_value=[VERSION_TAG])
            mock_dao.delete_old_versions = AsyncMock(return_value=0)

            manager = SnapshotManager(mock_db)
            files = [_make_file("a.py", "")]  # 空 hash

            # SnapshotManager 本身不校验空 hash，直接传递给 DAO
            result = await manager.save_snapshot(REPO_UUID, VERSION_TAG, files)

            assert result == 1
            # 验证快照数据中 content_hash 为 ""
            call_args = mock_dao.create_many.call_args[0][1]
            assert call_args[0]["content_hash"] == ""

    @pytest.mark.asyncio
    async def test_save_snapshot_with_negative_line_count(self):
        """测试 line_count 为负数时的文件仍可保存（由应用层其他地方校验）"""
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls, _patch_settings():
            mock_dao = mock_dao_cls.return_value
            mock_dao.create_many = AsyncMock(return_value=[])
            mock_dao.get_all_versions = AsyncMock(return_value=[VERSION_TAG])
            mock_dao.delete_old_versions = AsyncMock(return_value=0)

            manager = SnapshotManager(mock_db)
            files = [_make_file("a.py", "h1", line_count=-5)]

            result = await manager.save_snapshot(REPO_UUID, VERSION_TAG, files)

            assert result == 1
            # 验证快照数据中 nodes_count 来自 node_counts（默认 0）
            call_args = mock_dao.create_many.call_args[0][1]
            assert call_args[0]["nodes_count"] == 0


# ======================== _cleanup_old_snapshots 测试 ========================


class TestCleanupOldSnapshots:
    """测试 _cleanup_old_snapshots 的快照清理逻辑"""

    @pytest.mark.asyncio
    async def test_cleanup_keeps_max_versions(self):
        """测试清理后保留恰好 max_versions 个快照版本"""
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()

        with (
            patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls,
            _patch_settings(max_snapshot_versions=3),
        ):
            mock_dao = mock_dao_cls.return_value
            # 5 个版本，应保留前 3 个
            all_versions = ["v5", "v4", "v3", "v2", "v1"]
            mock_dao.get_all_versions = AsyncMock(return_value=all_versions)
            mock_dao.delete_old_versions = AsyncMock(return_value=10)

            manager = SnapshotManager(mock_db)
            await manager._cleanup_old_snapshots(REPO_UUID, "v5")

            mock_dao.delete_old_versions.assert_called_once()
            keep_versions = mock_dao.delete_old_versions.call_args[0][2]
            assert keep_versions == ["v5", "v4", "v3"]
            # SV-7: _cleanup_old_snapshots 不调用 commit，由调用者统一管理事务
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_removes_oldest_first(self):
        """测试清理优先删除最旧版本（by created_at desc，即排序最靠后的）"""
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()

        with (
            patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls,
            _patch_settings(max_snapshot_versions=2),
        ):
            mock_dao = mock_dao_cls.return_value
            all_versions = ["v3", "v2", "v1"]  # v3 最新，v1 最旧
            mock_dao.get_all_versions = AsyncMock(return_value=all_versions)
            mock_dao.delete_old_versions = AsyncMock(return_value=5)

            manager = SnapshotManager(mock_db)
            await manager._cleanup_old_snapshots(REPO_UUID, "v3")

            keep_versions = mock_dao.delete_old_versions.call_args[0][2]
            assert keep_versions == ["v3", "v2"]  # 保留最新的 2 个
            assert "v1" not in keep_versions  # 最旧的被清理

    @pytest.mark.asyncio
    async def test_cleanup_fewer_versions_than_max_no_cleanup(self):
        """测试版本数少于 max 时不清理（delete_old_versions 不被调用）"""
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()

        with (
            patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls,
            _patch_settings(max_snapshot_versions=5),
        ):
            mock_dao = mock_dao_cls.return_value
            all_versions = ["v2", "v1"]  # 只有 2 个，max=5
            mock_dao.get_all_versions = AsyncMock(return_value=all_versions)
            mock_dao.delete_old_versions = AsyncMock(return_value=0)

            manager = SnapshotManager(mock_db)
            await manager._cleanup_old_snapshots(REPO_UUID, "v2")

            # 版本数少于 max，无需清理
            mock_dao.delete_old_versions.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_no_snapshots_noop(self):
        """测试无快照时清理是 no-op"""
        mock_db = MagicMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls, _patch_settings():
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_all_versions = AsyncMock(return_value=[])

            manager = SnapshotManager(mock_db)
            await manager._cleanup_old_snapshots(REPO_UUID, VERSION_TAG)

            mock_dao.delete_old_versions.assert_not_called()


# ======================== get_latest_snapshot / load_latest_snapshot 测试 ========================


class TestGetLatestSnapshot:
    """测试 get_latest_snapshot / load_latest_snapshot 的快照加载逻辑"""

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_when_snapshots_exist(self):
        """测试有快照时正确返回最新版本和 hash_map"""
        mock_db = MagicMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls:
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_latest_version = AsyncMock(return_value=VERSION_TAG)

            file_a_id = uuid4()
            file_b_id = uuid4()
            snapshots = [
                _make_snapshot(REPO_UUID, VERSION_TAG, file_a_id, "h1"),
                _make_snapshot(REPO_UUID, VERSION_TAG, file_b_id, "h2"),
            ]
            mock_dao.get_by_version = AsyncMock(return_value=snapshots)

            manager = SnapshotManager(mock_db)
            result = await manager.load_latest_snapshot(REPO_UUID)

            assert result is not None
            version, hash_map = result
            assert version == VERSION_TAG
            assert hash_map[file_a_id] == "h1"
            assert hash_map[file_b_id] == "h2"
            assert len(hash_map) == 2

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_when_none_exist_returns_none(self):
        """测试无快照时返回 None"""
        mock_db = MagicMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls:
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_latest_version = AsyncMock(return_value=None)

            manager = SnapshotManager(mock_db)
            result = await manager.load_latest_snapshot(REPO_UUID)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_filters_by_repository_id(self):
        """测试 load_latest_snapshot 按正确的 repository_id 过滤"""
        mock_db = MagicMock()
        other_repo = UUID("22222222-0000-0000-0000-000000000000")

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls:
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_latest_version = AsyncMock(return_value=VERSION_TAG)

            file_id = uuid4()
            snapshots = [_make_snapshot(REPO_UUID, VERSION_TAG, file_id, "h1")]
            mock_dao.get_by_version = AsyncMock(return_value=snapshots)

            manager = SnapshotManager(mock_db)

            # 用 other_repo 调用
            await manager.load_latest_snapshot(other_repo)

            # 验证 DAO 被传入 other_repo
            mock_dao.get_latest_version.assert_called_with(mock_db, other_repo)
            mock_dao.get_by_version.assert_called_with(mock_db, other_repo, VERSION_TAG)

    @pytest.mark.asyncio
    async def test_get_latest_version_returns_version(self):
        """测试 get_latest_version 委托给 DAO"""
        mock_db = MagicMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls:
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_latest_version = AsyncMock(return_value=VERSION_TAG)

            manager = SnapshotManager(mock_db)
            result = await manager.get_latest_version(REPO_UUID)

            assert result == VERSION_TAG
            mock_dao.get_latest_version.assert_called_with(mock_db, REPO_UUID)

    @pytest.mark.asyncio
    async def test_delete_by_repository(self):
        """测试删除指定仓库的所有快照（SV-6 修复：不执行 commit，由调用者管理事务）"""
        mock_db = MagicMock()

        with patch("codeinsight.services.snapshot_manager.FileAnalysisSnapshotDAO") as mock_dao_cls:
            mock_dao = mock_dao_cls.return_value
            mock_dao.delete_by_repository = AsyncMock(return_value=10)

            manager = SnapshotManager(mock_db)
            result = await manager.delete_by_repository(REPO_UUID)

            assert result == 10
            mock_dao.delete_by_repository.assert_called_with(mock_db, REPO_UUID)
