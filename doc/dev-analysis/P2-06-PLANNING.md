# P2-06: 增量扫描 — 变更文件检测 + 依赖传播 + 增量分析

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-06 |
| 任务名称 | 增量扫描：文件变更检测 + 依赖传播 + 增量分析 |
| 所属阶段 | Phase 2（第 4-6 周） |
| 优先级 | P0 |
| 预估工时 | 10h |
| 交付物 | 增量分析服务 + 文件快照表 + 依赖传播引擎 + 增量模式集成 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P2-01 GitScanner | ✅ | 提供 `content_hash`，是增量检测的数据源 |
| P2-02 Tree-sitter 解析层 | ✅ | 5种语言解析器已实现 |
| P2-04 结构分析引擎 | ✅ | 调用图 + 模块依赖图已构建 |
| P2-05 结构数据入库管道 | ✅ | `StructureDataPipeline` 已就绪，支持校验 + 批量写入 |
| P1-07 DAO 层 | ✅ | `FileDAO` 提供 `get_by_content_hash` 等方法 |
| `AnalysisMode.INCREMENTAL` | ✅ | Schema 已定义，`run_analysis` 已接收 `mode` 参数 |

### 任务背景

当前 `run_analysis` 每次执行都是**全量分析**：扫描所有文件 → 解析所有文件 → 构建完整调用图和依赖图。对于大仓库，这导致：

1. **分析耗时过长**：每次完整跑一遍，浪费大量时间在未变更文件上
2. **资源浪费**：解析未变更文件消耗 CPU/内存，特别是大仓库（1000+ 文件）
3. **前端等待时间长**：全量分析进度从 0% 到 100% 耗时数十分钟
4. **用户重复触发成本高**：修改一个文件后重新分析，仍然全量重跑

`AnalysisMode.INCREMENTAL` 已经在 Schema 中定义，但 `run_analysis` 中尚未实际实现增量逻辑。本任务将实现完整的增量分析管线：

1. **文件变更检测** — 基于 `content_hash` 对比上次分析快照，识别新增/修改/删除的文件
2. **依赖传播引擎** — 变更文件的调用方和被调用方自动纳入重分析范围
3. **增量快照表** — 存储每次分析的文件 hash 快照，作为增量对比基准
4. **增量分析集成** — `run_analysis` 在 `INCREMENTAL` 模式下只分析变更文件及其依赖

---

## 二、整体架构位置

P2-06 在分析管线中作为**增量调度层**，位于 Step 2（扫描）和 Step 3（解析）之间：

```
┌──────────────────────────────────────────────────────────────────────┐
│  run_analysis 完整流程                                                │
│                                                                      │
│  Step 1: _do_analysis_setup()                                        │
│                                                                      │
│  Step 2: GitScanner.scan()  ←── P2-01 ✅                             │
│          → _store_files_to_db()                                       │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 📦 IncrementalAnalyzer.compute_diff()  ←── P2-06 ⬅️ 本任务  │    │
│  │   1. 加载上次快照（file_analysis_snapshots）                  │    │
│  │   2. 对比当前 files 表的 content_hash                          │    │
│  │   3. 识别 added / modified / deleted 文件                      │    │
│  │   4. 依赖传播：扩展变更集到调用方/被调用方                       │    │
│  │   → 返回需要重分析的文件路径集合                                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  Step 3: ParserFactory 解析（增量模式下只解析变更文件） ←── P2-06    │
│          → AST 节点                                                  │
│          ↓                                                           │
│          📦 StructureDataPipeline.ingest_ast_nodes()  ←── P2-05 ✅   │
│          → ast_nodes 表                                               │
│                                                                      │
│  Step 4: 结构分析（增量模式下只重建变更文件的调用边/依赖边） ←── P2-06│
│          CallGraphBuilder.build_data() → 调用边列表                  │
│          ModuleDependencyBuilder.build_data() → 依赖边列表            │
│          ↓                                                           │
│          📦 StructureDataPipeline.ingest_call_edges()  ←── P2-05 ✅  │
│          📦 StructureDataPipeline.ingest_module_deps()  ←── P2-05 ✅ │
│                                                                      │
│  Step 5: AI 分析  ←── P3 (待接入)                                    │
│                                                                      │
│  Step 6: 保存快照（file_analysis_snapshots）←── P2-06 ⬅️ 本任务     │
│          保存本次分析的文件 hash 快照                                 │
│                                                                      │
│  Step 7: 完成                                                         │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 增量模式 vs 全量模式对比

| 步骤 | 全量模式 (FULL) | 增量模式 (INCREMENTAL) |
|------|----------------|----------------------|
| Step 2: 文件扫描 | 扫描所有文件，覆盖写入 files 表 | 扫描所有文件，**更新** files 表（新增/修改/删除） |
| 变更检测 | 无需 | 加载上次快照 → 对比 hash → 计算变更集 |
| 依赖传播 | 无需 | 将变更文件的调用方/被调用方纳入重分析范围 |
| Step 3: AST 解析 | 解析所有文件 | **只解析变更文件及其依赖文件** |
| Step 3 入库 | 先全量删除 ast_nodes，再全量写入 | **先删除变更文件的旧节点**，再写入新节点 |
| Step 4: 结构分析 | 全量重建调用图和依赖图 | **只重建变更文件相关的边** |
| Step 6: 保存快照 | 无需 | 保存本次快照到 file_analysis_snapshots 表 |

### 2.2 数据流向（增量模式）

```
上次分析快照（file_analysis_snapshots）
    │
    ├── 文件 A (hash: abc123) ──┐
    ├── 文件 B (hash: def456) ──┤
    └── 文件 C (hash: ghi789) ──┘
            ↓ 对比
当前 files 表
    │
    ├── 文件 A (hash: abc123) ──→ 未变更，跳过
    ├── 文件 B (hash: 789xyz) ──→ 已修改，纳入变更集
    ├── 文件 C (hash: ghi789) ──→ 未变更，跳过
    └── 文件 D (hash: new123) ──→ 新增，纳入变更集

变更集 = {文件 B, 文件 D}

依赖传播：
    ├── 文件 B 被文件 E 调用 → 文件 E 纳入
    ├── 文件 B 调用了文件 F → 文件 F 纳入
    └── 文件 D 被文件 G import → 文件 G 纳入

最终重分析集 = {文件 B, 文件 D, 文件 E, 文件 F, 文件 G}
```

---

## 三、修改模块结构

```
codeinsight-backend/
├── codeinsight/
│   ├── models/
│   │   └── file_analysis_snapshot.py  # 新增: 文件分析快照模型
│   ├── repositories/
│   │   └── file_analysis_snapshot.py  # 新增: 快照 DAO
│   ├── services/
│   │   ├── incremental_analyzer.py    # 新增: 增量分析服务（核心）
│   │   └── snapshot_manager.py        # 新增: 快照管理（加载/保存）
│   │   └── __init__.py                # 修改: 导出新服务
│   └── tasks/
│       └── analysis_tasks.py          # 修改: 集成增量分析到 run_analysis
│
└── tests/
    ├── test_incremental_analyzer.py   # 新增: 增量分析测试
    ├── test_snapshot_manager.py       # 新增: 快照管理测试
    └── test_analysis_tasks.py         # 修改: 增量模式集成测试
```

---

## 四、核心功能设计

### 4.1 数据模型：`FileAnalysisSnapshot`

```sql
CREATE TABLE file_analysis_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    analysis_version TEXT NOT NULL,        -- 对应 analysis_versions.version
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    content_hash VARCHAR(64) NOT NULL,     -- 分析时的文件内容哈希
    nodes_count INTEGER DEFAULT 0,         -- 分析时该文件的 AST 节点数
    edges_count INTEGER DEFAULT 0,         -- 分析时该文件相关的调用边数
    deps_count INTEGER DEFAULT 0,          -- 分析时该文件相关的依赖边数
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_file_snapshot UNIQUE (analysis_version, file_id)
);

-- 查询优化索引
CREATE INDEX idx_snapshots_repo_version ON file_analysis_snapshots(repository_id, analysis_version);
CREATE INDEX idx_snapshots_repo_file ON file_analysis_snapshots(repository_id, file_id);
CREATE INDEX idx_snapshots_hash ON file_analysis_snapshots(content_hash);
```

### 4.2 IncrementalAnalyzer — 增量分析服务

```python
@dataclass
class FileChange:
    """单个文件变更"""
    file_id: UUID
    path: str
    change_type: ChangeType  # "added" / "modified" / "deleted"
    old_hash: str | None     # 旧 hash（deleted/modified）
    new_hash: str            # 新 hash（added/modified）


@dataclass
class IncrementalDiff:
    """增量分析结果"""
    changed_files: list[FileChange]        # 直接变更的文件
    propagated_files: list[str]            # 依赖传播后纳入的文件路径
    total_files_to_analyze: int            # 最终需要分析的文件数
    skipped_files: int                     # 跳过未变更文件数
    needs_full_analysis: bool              # 是否需要降级为全量分析


class IncrementalAnalyzer:
    """
    增量分析服务

    核心职责：
    1. 计算文件变更集（基于 content_hash 对比）
    2. 依赖传播（将变更文件的调用方/被调用方纳入重分析）
    3. 判断是否应降级为全量分析（变更过多时）
    """

    # 降级阈值：变更文件占比超过此值则降级为全量分析
    FALLBACK_THRESHOLD = 0.3  # 30%

    async def compute_diff(
        self,
        repo_uuid: UUID,
        current_files: list[FileModel],
        latest_version: str | None = None,
    ) -> IncrementalDiff:
        """
        计算增量分析差异

        Args:
            repo_uuid: 仓库 UUID
            current_files: 当前扫描到的文件列表
            latest_version: 上次分析版本标签（None 表示首次分析）

        Returns:
            IncrementalDiff 包含变更文件和传播文件
        """
        # 1. 加载上次快照
        previous_snapshot = await self._load_snapshot(repo_uuid, latest_version)

        # 2. 计算直接变更
        changes = self._compute_changes(current_files, previous_snapshot)

        # 3. 依赖传播
        propagated = await self._propagate_dependencies(repo_uuid, changes)

        # 4. 判断是否需要降级
        total_current = len(current_files)
        affected_count = len({c.path for c in changes}) + len(propagated)
        needs_full = (affected_count / max(total_current, 1)) > self.FALLBACK_THRESHOLD

        return IncrementalDiff(
            changed_files=changes,
            propagated_files=propagated,
            total_files_to_analyze=affected_count,
            skipped_files=total_current - affected_count,
            needs_full_analysis=needs_full,
        )

    async def _load_snapshot(
        self,
        repo_uuid: UUID,
        version: str | None,
    ) -> dict[str, str]:
        """
        加载上次分析的文件快照

        Returns:
            {file_path: content_hash} 映射
        """
        ...

    def _compute_changes(
        self,
        current_files: list[FileModel],
        previous_snapshot: dict[str, str],
    ) -> list[FileChange]:
        """
        计算文件变更集

        对比逻辑：
        - current_path 不在 previous 中 → added
        - previous_path 不在 current 中 → deleted
        - hash 不同 → modified
        - hash 相同 → 未变更，跳过
        """
        ...

    async def _propagate_dependencies(
        self,
        repo_uuid: UUID,
        changes: list[FileChange],
    ) -> list[str]:
        """
        依赖传播：将变更文件的调用方和被调用方纳入重分析范围

        传播规则：
        1. 变更文件被其他文件调用（call_edges.callee_node_id）→ 调用方需要重分析
        2. 变更文件调用了其他文件（call_edges.caller_node_id）→ 被调用方可能需要重分析
        3. 变更文件被其他文件 import（module_dependencies.imported_file_id）→ 导入方需要重分析

        使用 BFS 遍历，限制最大传播深度（默认 3 层），避免无限扩散。
        """
        ...

    async def get_files_to_analyze(
        self,
        diff: IncrementalDiff,
        current_files: list[FileModel],
    ) -> list[FileModel]:
        """
        根据增量差异返回需要分析的文件列表

        Args:
            diff: 增量差异结果
            current_files: 当前所有文件

        Returns:
            需要重分析的文件列表
        """
        affected_paths = {c.path for c in diff.changed_files}
        affected_paths.update(diff.propagated_files)

        return [f for f in current_files if f.path in affected_paths]
```

### 4.3 SnapshotManager — 快照管理服务

```python
class SnapshotManager:
    """
    分析快照管理器

    负责快照的保存和加载，供增量分析使用。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.snapshot_dao = FileAnalysisSnapshotDAO()

    async def save_snapshot(
        self,
        repo_uuid: UUID,
        version: str,
        files: list[FileModel],
        node_counts: dict[str, int] | None = None,
    ) -> int:
        """
        保存本次分析的文件快照

        Args:
            repo_uuid: 仓库 UUID
            version: 分析版本标签
            files: 文件列表
            node_counts: 每个文件的 AST 节点数（可选）

        Returns:
            保存的快照记录数
        """
        ...

    async def load_latest_snapshot(
        self,
        repo_uuid: UUID,
    ) -> tuple[str, dict[str, str]] | None:
        """
        加载最新的文件快照

        Returns:
            (version, {file_path: content_hash}) 或 None（无历史快照）
        """
        ...

    async def load_snapshot_by_version(
        self,
        repo_uuid: UUID,
        version: str,
    ) -> dict[str, str] | None:
        """
        加载指定版本的文件快照

        Returns:
            {file_path: content_hash} 或 None
        """
        ...

    async def delete_snapshots_before(
        self,
        repo_uuid: UUID,
        version: str,
    ) -> int:
        """
        删除旧快照（保留最近 N 个版本）

        Args:
            repo_uuid: 仓库 UUID
            version: 当前版本

        Returns:
            删除的记录数
        """
        ...
```

### 4.4 run_analysis 增量模式集成

```python
# 修改 run_analysis，在 Step 2 和 Step 3 之间增加增量判断

@celery_app.task(...)
def run_analysis(self, repository_id: str, mode: str = AnalysisMode.FULL.value, ...):
    ...
    # ---- Step 2: 扫描文件 ----
    scan_result = scanner.scan()
    asyncio.run(_store_files_to_db(repo_uuid, files_data))

    # ---- 增量判断（P2-06 新增） ----
    should_do_full = mode == AnalysisMode.FULL.value
    files_to_parse = scan_result.files  # 默认全量

    if mode == AnalysisMode.INCREMENTAL.value and not should_do_full:
        # 加载上次分析版本
        repo = asyncio.run(repo_dao.get_by_id(..., repo_uuid))
        latest_version = repo.current_version if repo else None

        # 获取当前 files 列表
        current_files = asyncio.run(file_dao.get_by_repository(..., repo_uuid))

        # 计算增量差异
        async def _compute_incremental():
            analyzer = IncrementalAnalyzer()
            diff = await analyzer.compute_diff(repo_uuid, current_files, latest_version)

            # 如果变更过多，降级为全量分析
            if diff.needs_full_analysis:
                logger.info(
                    "变更文件过多 (%d/%d)，降级为全量分析",
                    diff.total_files_to_analyze, len(current_files),
                )
                should_do_full = True
                files_to_parse = scan_result.files
            else:
                logger.info(
                    "增量分析: 变更 %d 文件，传播 %d 文件，共 %d 文件需分析",
                    len(diff.changed_files),
                    len(diff.propagated_files),
                    diff.total_files_to_analyze,
                )
                # 只获取需要分析的文件
                files_to_parse = await analyzer.get_files_to_analyze(diff, current_files)

            return diff, files_to_parse, should_do_full

        diff, files_to_parse, should_do_full = asyncio.run(_compute_incremental())
        incremental_diff = diff
    else:
        incremental_diff = None

    # ---- Step 3: AST 解析（增量/全量） ----
    if should_do_full:
        # 全量：先删除所有旧节点，再全量写入
        asyncio.run(_parse_and_store_ast(repo_uuid, scan_result, ...))
    else:
        # 增量：只删除变更文件的旧节点，再写入新节点
        asyncio.run(
            _parse_and_store_ast_incremental(
                repo_uuid, files_to_parse, incremental_diff, ...
            )
        )

    # ---- Step 4: 结构分析（增量/全量） ----
    if should_do_full:
        asyncio.run(_build_structures(repo_uuid, self, ...))
    else:
        asyncio.run(
            _build_structures_incremental(
                repo_uuid, files_to_parse, incremental_diff, self, ...
            )
        )

    # ---- Step 6: 保存快照（增量模式下） ----
    if incremental_diff is not None:
        asyncio.run(
            _save_analysis_snapshot(repo_uuid, version_tag, current_files)
        )
```

### 4.5 增量模式下的 DAO 操作变更

```python
# 增量模式下需要新增的 DAO 操作：

# 1. 只删除指定文件的 AST 节点（而非全量删除）
async def delete_ast_nodes_by_files(
    self, db: AsyncSession, repository_id: UUID, file_ids: list[UUID]
) -> int:
    """删除指定文件的 AST 节点"""
    ...

# 2. 只删除指定文件的调用边
async def delete_call_edges_by_files(
    self, db: AsyncSession, repository_id: UUID, file_ids: list[UUID]
) -> int:
    """删除指定文件相关的调用边（caller 或 callee 属于指定文件）"""
    ...

# 3. 只删除指定文件的模块依赖
async def delete_module_deps_by_files(
    self, db: AsyncSession, repository_id: UUID, file_ids: list[UUID]
) -> int:
    """删除指定文件相关的模块依赖"""
    ...
```

---

## 五、增量模式下的 Step 3/4 修改

### 5.1 _parse_and_store_ast_incremental

```python
async def _parse_and_store_ast_incremental(
    repo_uuid: UUID,
    files_to_parse: list[FileModel],
    incremental_diff: IncrementalDiff | None,
    progress_callback=None,
) -> None:
    """
    增量 AST 解析：只解析变更文件

    与全量模式的差异：
    - 不删除所有旧节点，只删除变更文件的旧节点
    - 只解析 files_to_parse 中的文件
    - 文件列表来自 scan_result 而非全量
    """
    file_dao = FileDAO()
    ast_dao = AstNodeDAO()

    async with async_session_factory() as db:
        # 获取需要分析的文件 ID
        file_ids = [f.id for f in files_to_parse]

        # 只删除这些文件的旧节点
        if file_ids:
            await ast_dao.delete_by_file_ids(db, repo_uuid, file_ids)

        # 只解析变更文件
        pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)
        parsed_count = 0

        for file_obj in files_to_parse:
            try:
                parser = ParserFactory.get_parser(file_obj.language)
                if parser is None:
                    continue

                ast_nodes = parser.parse_file(file_obj.absolute_path)
                nodes_data = [...]
                result = await pipeline.ingest_ast_nodes(repo_uuid, nodes_data)
                parsed_count += result.inserted_count
            except Exception as exc:
                logger.warning("增量解析失败: file=%s, error=%s", file_obj.path, exc)
                continue

        logger.info("增量 AST 解析完成: %d 个节点", parsed_count)
        await db.commit()
```

### 5.2 _build_structures_incremental

```python
async def _build_structures_incremental(
    repo_uuid: UUID,
    files_to_parse: list[FileModel],
    incremental_diff: IncrementalDiff | None,
    task_self: Any,
    progress_callback=None,
) -> None:
    """
    增量结构分析：只重建变更文件相关的调用边和依赖边

    策略：
    - 先删除变更文件相关的所有边
    - 重新构建这些文件的调用图和依赖图
    - 使用 StructureDataPipeline 入库
    """
    file_ids = [f.id for f in files_to_parse]

    async with async_session_factory() as db:
        pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)

        # 删除变更文件相关的旧边
        call_edge_dao = CallEdgeDAO()
        module_dep_dao = ModuleDependencyDAO()
        await call_edge_dao.delete_by_file_ids(db, repo_uuid, file_ids)
        await module_dep_dao.delete_by_file_ids(db, repo_uuid, file_ids)

        # 重建调用图数据
        call_graph_builder = CallGraphBuilder()
        call_edges = await call_graph_builder.build_data_for_files(repo_uuid, db=db, file_ids=file_ids)
        if call_edges:
            edge_result = await pipeline.ingest_call_edges(repo_uuid, call_edges)
            logger.info("增量调用图构建完成: edges=%d", edge_result.inserted_count)

        # 重建模块依赖数据
        module_dep_builder = ModuleDependencyBuilder()
        deps = await module_dep_builder.build_data_for_files(repo_uuid, db=db, file_ids=file_ids)
        if deps:
            dep_result = await pipeline.ingest_module_deps(repo_uuid, deps)
            logger.info("增量模块依赖图构建完成: dependencies=%d", dep_result.inserted_count)
```

---

## 六、依赖传播引擎

### 6.1 传播规则

```
变更文件 X 的依赖传播：

1. 调用传播（基于 call_edges）：
   ┌─────────────────────────────────────────────────┐
   │ call_edges 中 caller_node_id 属于 X             │
   │ → X 调用了其他函数                                │
   │ → 被调用函数所在的文件可能依赖 X 的行为          │
   │ → 纳入传播集（标记为 "callee_dependent"）        │
   ├─────────────────────────────────────────────────┤
   │ call_edges 中 callee_node_id 属于 X             │
   │ → 其他文件调用了 X 的函数                        │
   │ → 调用方需要重分析以获取最新调用信息             │
   │ → 纳入传播集（标记为 "caller_dependent"）        │
   └─────────────────────────────────────────────────┘

2. 导入传播（基于 module_dependencies）：
   ┌─────────────────────────────────────────────────┐
   │ module_dependencies 中 imported_file_id = X      │
   │ → 其他文件 import 了 X                          │
   │ → 导入方需要重分析以获取最新依赖信息             │
   │ → 纳入传播集（标记为 "importer_dependent"）      │
   ├─────────────────────────────────────────────────┤
   │ module_dependencies 中 importer_file_id = X      │
   │ → X import 了其他文件                            │
   │ → 被导入方可能不受影响（保守策略：纳入）          │
   │ → 纳入传播集（标记为 "importee_dependent"）      │
   └─────────────────────────────────────────────────┘
```

### 6.2 BFS 传播算法

```python
async def _propagate_dependencies(
    self,
    repo_uuid: UUID,
    changes: list[FileChange],
    max_depth: int = 3,
) -> list[str]:
    """
    BFS 依赖传播

    1. 初始队列 = 直接变更的文件路径
    2. 每层遍历：
       - 查询 call_edges 找到调用方和被调用方
       - 查询 module_dependencies 找到导入方和被导入方
       - 将新发现的文件加入下一层
    3. 限制传播深度（max_depth），避免无限扩散
    4. 去重（已访问的文件不再传播）
    """
    visited: set[str] = set()
    propagated: set[str] = set()

    # 初始化队列
    queue: list[tuple[str, int]] = [(c.path, 0) for c in changes]
    for c in changes:
        visited.add(c.path)

    while queue:
        current_path, depth = queue.pop(0)

        if depth >= max_depth:
            continue

        # 查询 call_edges 中的关联文件
        caller_files = await self._get_caller_files(repo_uuid, current_path)
        callee_files = await self._get_callee_files(repo_uuid, current_path)

        # 查询 module_dependencies 中的关联文件
        importer_files = await self._get_importer_files(repo_uuid, current_path)
        importee_files = await self._get_importee_files(repo_uuid, current_path)

        # 收集新文件
        for path in caller_files | callee_files | importer_files | importee_files:
            if path not in visited:
                visited.add(path)
                propagated.add(path)
                queue.append((path, depth + 1))

    return list(propagated)
```

---

## 七、降级策略

### 7.1 何时降级为全量分析

| 条件 | 阈值 | 说明 |
|------|------|------|
| 变更文件占比 | > 30% | 变更文件过多时，增量分析收益不高 |
| 传播文件占比 | > 50% | 依赖传播导致扩散范围过大 |
| 无历史快照 | - | 首次分析或快照丢失时，降级为全量 |
| 变更包含核心文件 | - | 配置文件中列出的关键文件变更时，全量分析 |

### 7.2 降级实现

```python
# 在 compute_diff 中自动判断
if needs_full_analysis:
    logger.info("触发降级: 变更占比 %.1f%%，降级为全量分析", ratio)
    # 返回 needs_full_analysis=True，由 run_analysis 决定是否降级
```

---

## 八、测试覆盖

### 8.1 test_incremental_analyzer.py（预计 18 个测试用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_compute_diff_no_changes` | 无变更文件时，返回空变更集 |
| `test_compute_diff_added_file` | 新增文件被正确识别 |
| `test_compute_diff_modified_file` | 修改文件被正确识别 |
| `test_compute_diff_deleted_file` | 删除文件被正确识别 |
| `test_compute_diff_mixed_changes` | 混合变更（新增+修改+删除） |
| `test_propagate_caller_dependency` | 调用方被纳入传播集 |
| `test_propagate_callee_dependency` | 被调用方被纳入传播集 |
| `test_propagate_importer_dependency` | 导入方被纳入传播集 |
| `test_propagate_max_depth` | 传播深度限制生效 |
| `test_propagate_no_cycles` | 循环依赖不会导致无限扩散 |
| `test_fallback_to_full_analysis` | 变更过多时触发降级 |
| `test_no_fallback_for_small_changes` | 变更较少时不降级 |
| `test_get_files_to_analyze` | 正确返回需要分析的文件列表 |
| `test_empty_repo` | 空仓库时不报错 |

### 8.2 test_snapshot_manager.py（预计 10 个测试用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_save_snapshot` | 正常保存快照 |
| `test_load_latest_snapshot` | 加载最新快照 |
| `test_load_snapshot_by_version` | 按版本加载快照 |
| `test_load_snapshot_no_history` | 无历史快照时返回 None |
| `test_delete_old_snapshots` | 删除旧快照 |
| `test_save_snapshot_empty_files` | 空文件列表不报错 |

### 8.3 test_analysis_tasks.py 修改

| 测试 | 覆盖内容 |
|------|---------|
| `test_run_analysis_incremental_mode` | 增量模式正常执行 |
| `test_run_analysis_incremental_fallback` | 增量模式降级为全量 |
| `test_run_analysis_incremental_no_changes` | 增量模式无变更时跳过 |
| `test_run_analysis_full_mode_unchanged` | 全量模式行为不变 |

---

## 九、设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **增量基准** | `file_analysis_snapshots` 表存储每次分析的文件 hash | 比 git diff 更准确，不受 Git 历史影响；与 P2-05 的 content_hash 方案一致 |
| **变更检测时机** | Step 2 扫描完成后，Step 3 解析前 | 确保 files 表已更新，content_hash 已就绪 |
| **增量删除策略** | 只删除变更文件的节点/边，保留未变更的 | 避免全量删除的性能开销 |
| **依赖传播深度** | 默认 3 层，可配置 | 平衡准确性和性能，防止无限扩散 |
| **降级阈值** | 变更占比 > 30% 降级为全量 | 变更过多时增量分析收益不高，全量更简单可靠 |
| **快照保留策略** | 保留最近 5 个版本，自动清理旧快照 | 避免快照表无限增长 |
| **传播算法** | BFS + 深度限制 | 简单高效，避免循环依赖导致无限扩散 |
| **首次分析** | 自动降级为全量 | 无历史快照，必须全量建立基准 |
| **Builder 增量接口** | `build_data_for_files()` 只构建指定文件的边 | 复用现有 builder 逻辑，减少代码重复 |
| **进度映射** | 增量模式下总进度按变更文件数计算 | 进度条更准确反映实际工作量 |

---

## 十、与 Phase 2 其他任务的关系

| 任务 | 状态 | 与 P2-06 的关系 |
|------|------|----------------|
| P2-01 GitScanner | ✅ | P2-06 使用 `content_hash` 做变更检测 |
| P2-04 结构分析引擎 | ✅ | P2-06 的依赖传播基于调用图和模块依赖图 |
| P2-05 结构数据入库管道 | ✅ | P2-06 的增量写入通过 `StructureDataPipeline` 完成 |
| P2-07 解析结果前端预览 | ⬜ | P2-06 的增量进度支持 P2-07 的实时状态展示 |
| P3 AI 分析引擎 | ⬜ | P2-06 的增量快照为 AI 分析提供变更上下文 |

---

## 十一、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 增量 AI 分析 | P3 | 只分析变更文件的知识点变更 |
| 增量 Webhook 通知 | P4 | 变更分析完成后通知前端增量结果 |
| 增量分析统计 | P5 | 追踪增量/全量分析的性能对比指标 |
| 分布式增量分析 | P5-01 | 多 Worker 并行处理不同文件的增量分析 |

---

## 十二、文件变更明细

### 新增文件

| 文件 | 说明 | 预估行数 |
|------|------|---------|
| `codeinsight/models/file_analysis_snapshot.py` | 文件分析快照 ORM 模型 | ~40 |
| `codeinsight/repositories/file_analysis_snapshot.py` | 快照 DAO | ~120 |
| `codeinsight/services/incremental_analyzer.py` | 增量分析服务 | ~300 |
| `codeinsight/services/snapshot_manager.py` | 快照管理服务 | ~150 |
| `tests/test_incremental_analyzer.py` | 增量分析测试 | ~400 |
| `tests/test_snapshot_manager.py` | 快照管理测试 | ~200 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `codeinsight/tasks/analysis_tasks.py` | 集成增量分析到 run_analysis（Step 2/3/4/6） |
| `codeinsight/services/__init__.py` | 导出 IncrementalAnalyzer 和 SnapshotManager |
| `codeinsight/repositories/__init__.py` | 导出 FileAnalysisSnapshotDAO |
| `codeinsight/models/__init__.py` | 导出 FileAnalysisSnapshotModel |
| `codeinsight/repositories/ast_node.py` | 新增 `delete_by_file_ids` 方法 |
| `codeinsight/repositories/call_edge.py` | 新增 `delete_by_file_ids` 方法 |
| `codeinsight/repositories/module_dependency.py` | 新增 `delete_by_file_ids` 方法 |
| `codeinsight/analyzers/call_graph.py` | 新增 `build_data_for_files` 方法 |
| `codeinsight/analyzers/module_graph.py` | 新增 `build_data_for_files` 方法 |
| `tests/test_analysis_tasks.py` | 新增增量模式集成测试 |

---

## 十三、任务完成状态

- [ ] 创建 `file_analysis_snapshots` 表（Alembic Migration）
- [ ] 实现 FileAnalysisSnapshotModel ORM 模型
- [ ] 实现 FileAnalysisSnapshotDAO 数据访问对象
- [ ] 实现 SnapshotManager 快照管理服务
- [ ] 实现 IncrementalAnalyzer 增量分析服务
- [ ] 实现依赖传播引擎（BFS + 深度限制）
- [ ] 实现降级策略（变更占比 > 30%）
- [ ] 新增 `delete_by_file_ids` 到 AstNodeDAO / CallEdgeDAO / ModuleDependencyDAO
- [ ] 新增 `build_data_for_files` 到 CallGraphBuilder / ModuleDependencyBuilder
- [ ] 更新 `run_analysis` 集成增量模式
- [ ] 编写增量分析测试（18 个用例）
- [ ] 编写快照管理测试（10 个用例）
- [ ] 编写增量模式集成测试（4 个用例）
- [ ] 全部测试通过
- [ ] ruff check 通过

---

## 总结

P2-06 将实现完整的**增量扫描与分析**能力，解决全量分析在大仓库场景下的性能问题。核心交付物：

1. **文件变更检测** — 基于 `content_hash` 对比上次快照，精确识别新增/修改/删除文件
2. **依赖传播引擎** — BFS 算法将变更文件的调用方/被调用方自动纳入重分析范围，支持深度限制防止无限扩散
3. **快照管理机制** — 存储和加载每次分析的文件 hash 快照，支持多版本历史
4. **增量 DAO 操作** — 支持只删除/写入指定文件的数据，而非全量操作
5. **降级策略** — 变更过多或无历史快照时自动降级为全量分析，确保可靠性
6. **Builder 增量接口** — `build_data_for_files()` 方法支持只构建指定文件的调用边和依赖边

该增量分析能力为后续 P3（AI 分析引擎）提供了变更上下文，也为 P4（前端增量结果展示）提供了数据基础。

---

**开发日期**: 2026-07-12  
**开发人员**: Trae AI  
**任务编号**: P2-06  
**状态**: ⬜ 待实现
