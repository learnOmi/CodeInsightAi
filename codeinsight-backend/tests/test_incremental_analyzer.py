"""
IncrementalAnalyzer 单元测试

测试 compute_diff（变更检测 + 降级判断）和 _propagate_dependencies（BFS 依赖传播）。
所有 DAO 和数据库操作均通过 patch 模拟，不需要真实数据库。
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from codeinsight.models import AstNodeModel, CallEdgeModel, FileModel, ModuleDependencyModel
from codeinsight.services.incremental_analyzer import ChangeType, FileChange, IncrementalAnalyzer, IncrementalDiff

# ======================== 辅助数据 ========================

REPO_UUID = UUID("11111111-0000-0000-0000-000000000000")
VERSION_TAG = "v20260701-abc1234"


def _make_file(path: str, content_hash: str, **kwargs) -> FileModel:
    """快速构造 FileModel 实例"""
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


def _make_ast_node(file_id: UUID, file_path: str) -> AstNodeModel:
    return AstNodeModel(
        id=uuid4(),
        repository_id=REPO_UUID,
        file_id=file_id,
        node_type="function",
        name="test_func",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=40,
        file_path=file_path,
        language="python",
    )


def _make_call_edge(caller_node_id: UUID, callee_node_id: UUID, call_name: str = "func") -> CallEdgeModel:
    return CallEdgeModel(
        id=uuid4(),
        repository_id=REPO_UUID,
        caller_node_id=caller_node_id,
        callee_node_id=callee_node_id,
        start_line=1,
        start_column=0,
        call_name=call_name,
        call_type="static",
    )


def _make_module_dep(importer_file_id: UUID, imported_file_id: UUID, import_name: str = "mod") -> ModuleDependencyModel:
    return ModuleDependencyModel(
        id=uuid4(),
        repository_id=REPO_UUID,
        importer_file_id=importer_file_id,
        imported_file_id=imported_file_id,
        import_name=import_name,
        import_type="absolute",
    )


def _make_changes(
    path: str, content_hash: str, change_type: ChangeType = ChangeType.MODIFIED, file_id: UUID | None = None
) -> list[FileChange]:
    return [
        FileChange(
            file_id=file_id or uuid4(),
            path=path,
            change_type=change_type,
            old_hash=None if change_type == ChangeType.ADDED else "old_hash",
            new_hash=content_hash,
        )
    ]


def _patch_dao_results(repo_uuid: UUID, files, edges, deps, nodes=None):
    """
    统一的 DAO 模拟上下文管理器。

    在 codeinsight.services.incremental_analyzer 模块内替换 DAO 类和 async_session_factory，
    使 _propagate_dependencies 内的 DAO 实例返回预设数据。
    """
    nodes = nodes if nodes is not None else [_make_ast_node(f.id, f.path) for f in files]

    file_dao_mock = MagicMock()
    file_dao_mock.return_value.get_by_repository = AsyncMock(return_value=files)

    call_edge_dao_mock = MagicMock()
    call_edge_dao_mock.return_value.get_by_repository = AsyncMock(return_value=edges)

    module_dep_dao_mock = MagicMock()
    module_dep_dao_mock.return_value.get_by_repository = AsyncMock(return_value=deps)

    ast_dao_mock = MagicMock()
    ast_dao_mock.return_value.get_by_repository = AsyncMock(return_value=nodes)

    mock_session = MagicMock()
    mock_cm = MagicMock()
    mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

    return patch.multiple(
        "codeinsight.services.incremental_analyzer",
        FileDAO=file_dao_mock,
        CallEdgeDAO=call_edge_dao_mock,
        ModuleDependencyDAO=module_dep_dao_mock,
        AstNodeDAO=ast_dao_mock,
        async_session_factory=mock_cm,
    )


# ======================== compute_diff 测试 ========================


class TestComputeDiff:
    """测试 compute_diff 的变更检测与降级判断逻辑"""

    @pytest.mark.asyncio
    async def test_no_previous_snapshot_returns_full_analysis(self):
        """无历史快照时直接返回全量分析（needs_full_analysis=True，changed_files 为空）"""
        analyzer = IncrementalAnalyzer()
        current_files = [_make_file("a.py", "hash1"), _make_file("b.py", "hash2")]

        # latest_version=None 时不依赖 DAO
        diff = await analyzer.compute_diff(REPO_UUID, current_files, latest_version=None)

        assert diff.needs_full_analysis is True
        assert diff.total_files_to_analyze == 2
        assert diff.skipped_files == 0
        assert diff.changed_files == []
        assert diff.propagated_files == []

    @pytest.mark.asyncio
    async def test_identical_content_hash_returns_empty_diff(self):
        """所有文件 content_hash 与快照完全一致时，返回空变更、needs_full_analysis=False"""
        analyzer = IncrementalAnalyzer()
        file_a = _make_file("a.py", "same_hash")
        current_files = [file_a]
        previous_snapshot = {"a.py": "same_hash"}

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert diff.changed_files == []
        assert diff.total_files_to_analyze == 0
        assert diff.skipped_files == 1
        assert diff.needs_full_analysis is False

    @pytest.mark.asyncio
    async def test_modified_file_returns_modified_change(self):
        """单个文件 content_hash 变化时，返回 MODIFIED 变更"""
        analyzer = IncrementalAnalyzer()
        file_a = _make_file("a.py", "new_hash")
        current_files = [file_a]
        previous_snapshot = {"a.py": "old_hash"}

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert len(diff.changed_files) == 1
        change = diff.changed_files[0]
        assert change.change_type == ChangeType.MODIFIED
        assert change.path == "a.py"
        assert change.old_hash == "old_hash"
        assert change.new_hash == "new_hash"

    @pytest.mark.asyncio
    async def test_new_file_returns_added_change(self):
        """新增文件时返回 ADDED 变更"""
        analyzer = IncrementalAnalyzer()
        file_b = _make_file("new.py", "new_hash")
        current_files = [_make_file("a.py", "same"), file_b]
        previous_snapshot = {"a.py": "same"}

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert len(diff.changed_files) == 1
        change = diff.changed_files[0]
        assert change.change_type == ChangeType.ADDED
        assert change.path == "new.py"
        assert change.old_hash is None
        assert change.new_hash == "new_hash"

    @pytest.mark.asyncio
    async def test_deleted_file_returns_deleted_change(self):
        """已删除文件时返回 DELETED 变更"""
        analyzer = IncrementalAnalyzer()
        current_files = [_make_file("a.py", "same")]
        previous_snapshot = {"a.py": "same", "deleted.py": "old_hash"}

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert len(diff.changed_files) == 1
        change = diff.changed_files[0]
        assert change.change_type == ChangeType.DELETED
        assert change.path == "deleted.py"
        assert change.old_hash == "old_hash"
        assert change.new_hash == ""

    @pytest.mark.asyncio
    async def test_mixed_scenario_add_modify_delete(self):
        """混合场景：同时包含新增、修改、删除"""
        analyzer = IncrementalAnalyzer()
        current_files = [
            _make_file("a.py", "same"),  # 未变更
            _make_file("b.py", "new_hash"),  # 修改
            _make_file("c.py", "brand_new"),  # 新增
        ]
        previous_snapshot = {
            "a.py": "same",
            "b.py": "old_hash",
            "deleted.py": "old_hash",  # 已删除
        }

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        changes = diff.changed_files
        types = {c.change_type for c in changes}
        assert ChangeType.ADDED in types
        assert ChangeType.MODIFIED in types
        assert ChangeType.DELETED in types
        assert len(changes) == 3
        assert diff.total_files_to_analyze == 3

    @pytest.mark.asyncio
    async def test_no_changes_empty_diff(self):
        """多个文件但无任何变更时返回空 diff"""
        analyzer = IncrementalAnalyzer()
        current_files = [_make_file("a.py", "h1"), _make_file("b.py", "h2")]
        previous_snapshot = {"a.py": "h1", "b.py": "h2"}

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert diff.changed_files == []
        assert diff.total_files_to_analyze == 0
        assert diff.skipped_files == 2
        assert diff.needs_full_analysis is False

    @pytest.mark.asyncio
    async def test_all_files_changed_exceeds_threshold(self):
        """所有文件变更且超过阈值时 needs_full_analysis=True"""
        analyzer = IncrementalAnalyzer(fallback_threshold=0.3)
        current_files = [_make_file(f"f{i}.py", "new") for i in range(10)]
        previous_snapshot = {f"f{i}.py": "old" for i in range(10)}

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert diff.needs_full_analysis is True
        assert diff.total_files_to_analyze == 10

    @pytest.mark.asyncio
    async def test_exact_threshold_30_percent(self):
        """恰好 30% 变更时 needs_full_analysis=False（严格大于才触发降级）"""
        analyzer = IncrementalAnalyzer(fallback_threshold=0.3)
        current_files = [
            _make_file("a.py", "new"),  # modified
            _make_file("b.py", "new"),  # modified
            _make_file("c.py", "new"),  # modified
        ] + [_make_file(f"same{i}.py", "same") for i in range(7)]
        previous_snapshot = {
            "a.py": "old",
            "b.py": "old",
            "c.py": "old",
        }
        for i in range(7):
            previous_snapshot[f"same{i}.py"] = "same"

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert diff.needs_full_analysis is False
        assert diff.total_files_to_analyze == 3

    @pytest.mark.asyncio
    async def test_just_over_threshold_triggers_fallback(self):
        """刚好超过阈值（31/100）时 needs_full_analysis=True"""
        analyzer = IncrementalAnalyzer(fallback_threshold=0.3)
        current_files = [_make_file(f"f{i}.py", "new") for i in range(31)] + [
            _make_file(f"same{i}.py", "same") for i in range(69)
        ]
        previous_snapshot = {f"f{i}.py": "old" for i in range(31)}
        for i in range(69):
            previous_snapshot[f"same{i}.py"] = "same"

        with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
            with patch.object(analyzer, "_propagate_dependencies", new_callable=lambda: AsyncMock(return_value=[])):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert diff.needs_full_analysis is True
        assert diff.total_files_to_analyze == 31


# ======================== _propagate_dependencies 测试 ========================


class TestPropagateDependencies:
    """测试 _propagate_dependencies 的 BFS 依赖传播"""

    def _make_analyzer(self, max_depth: int = 3) -> IncrementalAnalyzer:
        return IncrementalAnalyzer(max_depth=max_depth)

    @pytest.mark.asyncio
    async def test_no_edges_no_propagation(self):
        """没有任何边时传播结果为空列表"""
        analyzer = self._make_analyzer()
        files = [_make_file("a.py", "h1")]
        changes = _make_changes("a.py", "h1")

        with _patch_dao_results(REPO_UUID, files, [], []):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert result == []

    @pytest.mark.asyncio
    async def test_single_level_caller_propagation(self):
        """测试单级传播：callee 变更 → caller 被纳入（通过 call_edges）"""
        analyzer = self._make_analyzer()

        file_a = _make_file("callee.py", "h1")
        file_b = _make_file("caller.py", "h2")

        node_a = _make_ast_node(file_a.id, "callee.py")
        node_b = _make_ast_node(file_b.id, "caller.py")

        edge = _make_call_edge(caller_node_id=node_b.id, callee_node_id=node_a.id)

        changes = _make_changes("callee.py", "h1")

        with _patch_dao_results(REPO_UUID, [file_a, file_b], [edge], [], [node_a, node_b]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert "caller.py" in result

    @pytest.mark.asyncio
    async def test_single_level_callee_propagation(self):
        """测试单级传播：caller 变更 → callee 被纳入"""
        analyzer = self._make_analyzer()

        file_a = _make_file("caller.py", "h1")
        file_b = _make_file("callee.py", "h2")

        node_a = _make_ast_node(file_a.id, "caller.py")
        node_b = _make_ast_node(file_b.id, "callee.py")

        edge = _make_call_edge(caller_node_id=node_a.id, callee_node_id=node_b.id)

        changes = _make_changes("caller.py", "h1")

        with _patch_dao_results(REPO_UUID, [file_a, file_b], [edge], [], [node_a, node_b]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert "callee.py" in result

    @pytest.mark.asyncio
    async def test_bfs_respects_max_depth(self):
        """测试 BFS 深度限制：传播不超过 max_depth"""
        analyzer = self._make_analyzer(max_depth=1)

        f1 = _make_file("f1.py", "h1")
        f2 = _make_file("f2.py", "h2")
        f3 = _make_file("f3.py", "h3")

        n1 = _make_ast_node(f1.id, "f1.py")
        n2 = _make_ast_node(f2.id, "f2.py")
        n3 = _make_ast_node(f3.id, "f3.py")

        edge1 = _make_call_edge(caller_node_id=n1.id, callee_node_id=n2.id, call_name="c2")
        edge2 = _make_call_edge(caller_node_id=n2.id, callee_node_id=n3.id, call_name="c3")

        changes = _make_changes("f1.py", "h1")

        with _patch_dao_results(REPO_UUID, [f1, f2, f3], [edge1, edge2], [], [n1, n2, n3]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert "f2.py" in result
        assert "f3.py" not in result

    @pytest.mark.asyncio
    async def test_propagation_stops_at_visited_files(self):
        """传播过程中已经访问过的文件不会重复加入"""
        analyzer = self._make_analyzer()

        f1 = _make_file("a.py", "h1")
        f2 = _make_file("b.py", "h2")
        f3 = _make_file("c.py", "h3")

        n1 = _make_ast_node(f1.id, "a.py")
        n2 = _make_ast_node(f2.id, "b.py")
        n3 = _make_ast_node(f3.id, "c.py")

        edge_ab = _make_call_edge(caller_node_id=n1.id, callee_node_id=n2.id, call_name="b")
        edge_ac = _make_call_edge(caller_node_id=n1.id, callee_node_id=n3.id, call_name="c")

        changes = _make_changes("a.py", "h1")

        with _patch_dao_results(REPO_UUID, [f1, f2, f3], [edge_ab, edge_ac], [], [n1, n2, n3]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert set(result) == {"b.py", "c.py"}
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_propagation_through_call_edges_only(self):
        """仅通过 call_edges 传播，不通过 module_dependencies"""
        analyzer = self._make_analyzer()

        f1 = _make_file("callee.py", "h1")
        f2 = _make_file("caller.py", "h2")
        n1 = _make_ast_node(f1.id, "callee.py")
        n2 = _make_ast_node(f2.id, "caller.py")

        edge = _make_call_edge(caller_node_id=n2.id, callee_node_id=n1.id)

        changes = _make_changes("callee.py", "h1")

        with _patch_dao_results(REPO_UUID, [f1, f2], [edge], [], [n1, n2]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert "caller.py" in result

    @pytest.mark.asyncio
    async def test_propagation_through_module_deps_only(self):
        """仅通过 module_dependencies 传播（无 call_edges）"""
        analyzer = self._make_analyzer()

        f1 = _make_file("imported.py", "h1")
        f2 = _make_file("importer.py", "h2")

        dep = _make_module_dep(importer_file_id=f2.id, imported_file_id=f1.id)

        changes = _make_changes("imported.py", "h1")

        with _patch_dao_results(
            REPO_UUID, [f1, f2], [], [dep], [_make_ast_node(f1.id, "imported.py"), _make_ast_node(f2.id, "importer.py")]
        ):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert "importer.py" in result

    @pytest.mark.asyncio
    async def test_propagation_through_both_edge_types(self):
        """同时通过 call_edges 和 module_dependencies 传播"""
        analyzer = self._make_analyzer()

        f1 = _make_file("shared.py", "h1")
        f2 = _make_file("caller.py", "h2")
        f3 = _make_file("importer.py", "h3")

        n1 = _make_ast_node(f1.id, "shared.py")
        n2 = _make_ast_node(f2.id, "caller.py")

        edge = _make_call_edge(caller_node_id=n2.id, callee_node_id=n1.id)
        dep = _make_module_dep(importer_file_id=f3.id, imported_file_id=f1.id)

        changes = _make_changes("shared.py", "h1")

        with _patch_dao_results(REPO_UUID, [f1, f2, f3], [edge], [dep], [n1, n2, _make_ast_node(f3.id, "importer.py")]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert set(result) == {"caller.py", "importer.py"}

    @pytest.mark.asyncio
    async def test_circular_dependency_no_infinite_loop(self):
        """循环依赖时 BFS 不会无限循环（有 visited 保护）"""
        analyzer = self._make_analyzer()

        f1 = _make_file("a.py", "h1")
        f2 = _make_file("b.py", "h2")

        n1 = _make_ast_node(f1.id, "a.py")
        n2 = _make_ast_node(f2.id, "b.py")

        edge_ab = _make_call_edge(caller_node_id=n1.id, callee_node_id=n2.id, call_name="b")
        edge_ba = _make_call_edge(caller_node_id=n2.id, callee_node_id=n1.id, call_name="a")

        changes = _make_changes("a.py", "h1")

        with _patch_dao_results(REPO_UUID, [f1, f2], [edge_ab, edge_ba], [], [n1, n2]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert set(result) == {"b.py"}
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_missing_node_graceful_skip(self):
        """当 file_path 在 file_path_to_id 中不存在时，传播不会崩溃"""
        analyzer = self._make_analyzer()

        f1 = _make_file("orphan.py", "h1")
        n1 = _make_ast_node(f1.id, "orphan.py")

        fake_node_id = uuid4()
        edge = _make_call_edge(caller_node_id=fake_node_id, callee_node_id=n1.id)

        changes = _make_changes("orphan.py", "h1")

        with _patch_dao_results(REPO_UUID, [f1], [edge], [], [n1]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert result == []

    @pytest.mark.asyncio
    async def test_deleted_file_not_propagated(self):
        """DELETED 类型的变更不参与传播"""
        analyzer = self._make_analyzer()

        f1 = _make_file("deleted.py", "h1")
        changes = [
            FileChange(
                file_id=UUID("00000000-0000-0000-0000-000000000000"),
                path="deleted.py",
                change_type=ChangeType.DELETED,
                old_hash="old_hash",
                new_hash="",
            )
        ]

        with _patch_dao_results(REPO_UUID, [f1], [], [], [_make_ast_node(f1.id, "deleted.py")]):
            result = await analyzer._propagate_dependencies(REPO_UUID, changes)

        assert result == []

    @pytest.mark.asyncio
    async def test_empty_changes_returns_empty(self):
        """无变更列表时直接返回空"""
        analyzer = self._make_analyzer()
        result = await analyzer._propagate_dependencies(REPO_UUID, [])
        assert result == []


# ======================== 集成测试（compute_diff + propagation combined）========================


class TestComputeDiffWithPropagation:
    """测试 compute_diff 与 propagation 的端到端组合"""

    def _make_analyzer(self, fallback_threshold: float = 0.3, max_depth: int = 3) -> IncrementalAnalyzer:
        return IncrementalAnalyzer(fallback_threshold=fallback_threshold, max_depth=max_depth)

    @pytest.mark.asyncio
    async def test_end_to_end_diff_and_propagate(self):
        """端到端：diff 计算 + 依赖传播 → 正确的 total_files_to_analyze"""
        analyzer = self._make_analyzer()

        file_a = _make_file("a.py", "new_hash")
        file_b = _make_file("b.py", "same_hash")
        current_files = [file_a, file_b]

        n_a = _make_ast_node(file_a.id, "a.py")
        n_b = _make_ast_node(file_b.id, "b.py")

        edge = _make_call_edge(caller_node_id=n_b.id, callee_node_id=n_a.id)

        previous_snapshot = {"a.py": "old_hash", "b.py": "same_hash"}

        with _patch_dao_results(REPO_UUID, current_files, [edge], [], [n_a, n_b]):
            with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
                diff = await analyzer.compute_diff(REPO_UUID, current_files, VERSION_TAG)

        assert diff.changed_files[0].change_type == ChangeType.MODIFIED
        assert "b.py" in diff.propagated_files
        assert diff.total_files_to_analyze == 2

    @pytest.mark.asyncio
    async def test_fallback_when_propagation_makes_list_too_large(self):
        """传播导致影响文件数超过阈值时触发降级"""
        analyzer = self._make_analyzer(fallback_threshold=0.3)

        # 10 个文件，1 个变更（f0），其余 9 个通过调用边直接与 f0 关联（星形拓扑，1 层即可传播全部）
        files = [_make_file(f"f{i}.py", "new" if i == 0 else "same") for i in range(10)]
        nodes = [_make_ast_node(f.id, f.path) for f in files]

        # f0 调用 f1~f9，形成星形拓扑（depth=1 即可覆盖全部）
        edges = []
        for i in range(1, 10):
            edges.append(_make_call_edge(caller_node_id=nodes[0].id, callee_node_id=nodes[i].id, call_name=f"f{i}"))

        previous_snapshot = {f.path: "old" if i == 0 else "same" for i, f in enumerate(files)}

        with _patch_dao_results(REPO_UUID, files, edges, [], nodes):
            with patch.object(analyzer, "_load_snapshot", return_value=previous_snapshot):
                diff = await analyzer.compute_diff(REPO_UUID, files, VERSION_TAG)

        assert diff.needs_full_analysis is True
        assert diff.total_files_to_analyze == 10  # f0(变更) + f1~f9(传播)

    @pytest.mark.asyncio
    async def test_integration_get_files_to_analyze(self):
        """get_files_to_analyze 正确返回受影响文件"""
        analyzer = IncrementalAnalyzer()

        file_a = _make_file("a.py", "h1")
        file_b = _make_file("b.py", "h2")
        current_files = [file_a, file_b]

        diff = IncrementalDiff(
            changed_files=[FileChange(file_a.id, "a.py", ChangeType.MODIFIED, "old", "h1")],
            propagated_files=["b.py"],
            total_files_to_analyze=2,
            skipped_files=0,
            needs_full_analysis=False,
        )

        result = await analyzer.get_files_to_analyze(diff, current_files)

        assert len(result) == 2
        assert {f.path for f in result} == {"a.py", "b.py"}
