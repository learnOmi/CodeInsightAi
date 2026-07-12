# P2-05: 结构数据入库管道

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-05 |
| 任务名称 | 结构数据入库管道：AST 结果 → PostgreSQL 批量入库 + 增量更新逻辑 |
| 所属阶段 | Phase 2（第 4-6 周） |
| 优先级 | P0 |
| 预估工时 | 8h |
| 交付物 | 批量入库服务 + 数据校验管道 + 增量更新逻辑 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P2-01 GitScanner | ✅ | 文件扫描器已实现，提供 `ScanResult` |
| P2-02 Tree-sitter 解析层 | ✅ | 5种语言解析器已实现，提取 AST 节点 |
| P2-03 持久化存储 | ✅ | `ast_nodes` 表已就绪，支持节点存储 |
| P2-04 结构分析引擎 | ✅ | 调用图 + 模块依赖图构建器已完成 |
| P1-07 DAO 层 | ✅ | 各表 DAO 已实现（AstNodeDAO, CallEdgeDAO, ModuleDependencyDAO） |

### 任务背景

P2-03 已实现基本的 AST 节点持久化（`AstNodeDAO.create_many`），P2-04 已实现调用图和模块依赖图的构建和存储。但当前入库逻辑存在以下问题：

1. **缺乏统一的入库管道**：各 builder 直接调用 DAO，没有统一的数据流转管道
2. **缺少数据校验**：入库前没有对 AST 节点、调用边、依赖边的完整性校验
3. **缺少批处理优化**：当前逐条或简单批量写入，缺少事务优化和并发控制
4. **缺少增量更新支持**：每次全量重建，没有基于 `content_hash` 的增量判断
5. **缺少入库进度反馈**：长时入库操作没有进度追踪

本任务将构建**统一的结构数据入库管道**，作为 `run_analysis` 中 Step 3（AST 解析）和 Step 4（结构分析）之间的数据流转层，提供：

1. **统一入库入口**：接收 AST 节点、调用边、模块依赖，统一调度和持久化
2. **数据校验管道**：入库前校验节点完整性、外键一致性、重复数据检测
3. **批量写入优化**：使用 `batch_size` 分片、事务隔离、批量 `INSERT ... ON CONFLICT`
4. **增量更新逻辑**：基于文件 `content_hash` 判断是否跳过未变更文件的数据
5. **入库进度追踪**：支持回调通知入库进度（用于前端进度条）

---

## 二、整体架构位置

P2-05 在分析管线中作为**数据持久化层**，位于解析/分析层和数据库之间：

```
┌──────────────────────────────────────────────────────────────────────┐
│  run_analysis 完整流程                                                │
│                                                                      │
│  Step 1: _do_analysis_setup()                                        │
│                                                                      │
│  Step 2: GitScanner.scan()  ←── P2-01 ✅                             │
│          → _store_files_to_db()                                       │
│                                                                      │
│  Step 3: ParserFactory 解析  ←── P2-02 ✅                            │
│          → AST 节点                                                   │
│          ↓                                                           │
│          📦 StructureDataPipeline.ingest_ast_nodes()  ←── P2-05      │
│          → ast_nodes 表                                               │
│                                                                      │
│  Step 4: 结构分析  ←── P2-04 ✅                                       │
│          CallGraphBuilder → 调用边列表                                │
│          ModuleDependencyBuilder → 依赖边列表                         │
│          ↓                                                           │
│          📦 StructureDataPipeline.ingest_call_edges()  ←── P2-05     │
│          📦 StructureDataPipeline.ingest_module_deps()  ←── P2-05    │
│          → call_edges 表 + module_dependencies 表                     │
│                                                                      │
│  Step 5: AI 分析  ←── P3 (待接入)                                    │
│                                                                      │
│  Step 6: 完成                                                         │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 数据流向

```
解析层（P2-02/P2-03）
    │
    ├── AST 节点列表
    │   └── StructureDataPipeline
    │       ├── _validate_ast_nodes()    → 校验节点完整性
    │       ├── _deduplicate_nodes()     → 去重（基于 file_id + start_line + name）
    │       ├── _batch_insert_nodes()    → 分批写入 ast_nodes 表
    │       └── 返回节点 UUID 映射（node_id → row_id）
    │
    ├── 调用边列表（P2-04）
    │   └── StructureDataPipeline
    │       ├── _validate_call_edges()   → 校验 caller/callee 节点存在
    │       ├── _batch_insert_edges()    → 分批写入 call_edges 表
    │       └── 返回边数量统计
    │
    └── 模块依赖列表（P2-04）
        └── StructureDataPipeline
            ├── _validate_module_deps()  → 校验 importer/imported 文件存在
            ├── _batch_insert_deps()     → 分批写入 module_dependencies 表
            └── 返回依赖数量统计
```

### 2.2 关键约束

- **事务边界**：每个 Step（AST 节点 / 调用边 / 模块依赖）各自事务，一个失败不影响另一个
- **批量大小**：默认 `batch_size=500`，大仓库分片写入避免内存峰值
- **增量判断**：基于文件 `content_hash`，跳过未变更文件的节点重写入
- **去重策略**：AST 节点按 `(file_id, start_line, node_type)` 去重
- **外键校验**：调用边的 `caller_node_id` 和 `callee_node_id` 必须存在于 `ast_nodes` 表

---

## 三、修改模块结构

```
codeinsight-backend/
├── codeinsight/
│   ├── services/               # 新增: 服务层
│   │   ├── __init__.py
│   │   └── structure_pipeline.py  # 结构数据入库管道（核心）
│   ├── pipelines/              # 新增: 管道层（可选扩展）
│   │   ├── __init__.py
│   │   ├── base.py             # 管道基类
│   │   └── validators.py       # 数据校验器
│   └── tasks/
│       └── analysis_tasks.py   # 修改: 使用 StructureDataPipeline 替代直接 DAO 调用
│
└── tests/
    ├── test_structure_pipeline.py  # 新增: 入库管道测试
    └── test_analysis_tasks.py      # 修改: 适配新管道
```

---

## 四、核心功能设计

### 4.1 StructureDataPipeline — 统一入库管道

#### 4.1.1 类设计

```python
class StructureDataPipeline:
    """
    结构数据入库管道
    
    负责将解析/分析结果批量写入 PostgreSQL，提供：
    1. 数据校验（完整性、外键、去重）
    2. 批量写入（分片、事务隔离）
    3. 增量更新（基于 content_hash 跳过未变更文件）
    4. 进度回调（支持实时进度通知）
    """
    
    def __init__(
        self, 
        db: AsyncSession,
        batch_size: int = 500,
        progress_callback: ProgressCallback | None = None,
    ):
        self.db = db
        self.batch_size = batch_size
        self.progress_callback = progress_callback
        self._node_uuid_map: dict[str, uuid.UUID] = {}  # 节点 UUID 映射
        
    async def ingest_ast_nodes(
        self, 
        repo_uuid: UUID, 
        nodes: list[dict],  # 节点字典列表（来自 parser）
    ) -> dict[str, uuid.UUID]:
        """
        入库 AST 节点
        
        Args:
            repo_uuid: 仓库 UUID
            nodes: 节点数据列表，每项包含 file_id, node_type, name, start_line 等
            
        Returns:
            节点标识 → 数据库 UUID 的映射
        """
        ...
    
    async def ingest_call_edges(
        self,
        repo_uuid: UUID,
        edges: list[dict],
        node_uuid_map: dict[str, uuid.UUID],
    ) -> int:
        """
        入库调用边
        
        Args:
            repo_uuid: 仓库 UUID
            edges: 调用边数据列表
            node_uuid_map: 节点 UUID 映射（用于解析 caller/callee）
            
        Returns:
            成功写入的边数量
        """
        ...
    
    async def ingest_module_deps(
        self,
        repo_uuid: UUID,
        deps: list[dict],
    ) -> int:
        """
        入库模块依赖
        
        Returns:
            成功写入的依赖数量
        """
        ...
```

#### 4.1.2 数据校验流程

```
校验步骤：
1. _validate_ast_nodes()
   ├── 必填字段检查（file_id, node_type, start_line）
   ├── node_type 合法性检查（预定义类型白名单）
   ├── 行号合法性检查（start_line >= 0）
   └── 返回校验通过的节点列表

2. _validate_call_edges()
   ├── caller_node_id 存在于 node_uuid_map
   ├── callee_node_id 存在于 node_uuid_map（可为 None）
   └── call_type 合法性检查（static/dynamic/unknown）

3. _validate_module_deps()
   ├── importer_file_id 存在于 files 表
   ├── imported_file_id 存在于 files 表（可为 None）
   └── import_type 合法性检查（relative/absolute/external）
```

#### 4.1.3 批量写入优化

```python
async def _batch_insert_nodes(self, nodes: list[AstNodeModel]) -> None:
    """
    分批写入 AST 节点
    
    策略：
    1. 每 batch_size 条为一个事务
    2. 使用 bulk_insert_mappings 提升性能
    3. 支持 ON CONFLICT DO UPDATE（增量更新）
    """
    for i in range(0, len(nodes), self.batch_size):
        batch = nodes[i : i + self.batch_size]
        await self.db.execute(
            insert(AstNodeModel).values(batch),
        )
        await self.db.commit()
        
        if self.progress_callback:
            self.progress_callback(
                current=i + len(batch),
                total=len(nodes),
                stage="ingest_nodes",
            )
```

#### 4.1.4 增量更新逻辑

```python
async def _should_skip_file(self, file_id: UUID) -> bool:
    """
    判断是否跳过文件（增量更新）
    
    基于 files 表的 content_hash，对比上次分析的 hash 值。
    如果 hash 相同，跳过该文件的所有节点重写入。
    """
    file_record = await self.file_dao.get_by_id(self.db, file_id)
    if file_record and file_record.content_hash:
        last_hash = await self._get_last_analysis_hash(file_id)
        return file_record.content_hash == last_hash
    return False  # 无历史记录，不跳过
```

### 4.2 管道基类（Pipeline Base）

```python
class BasePipeline:
    """
    管道基类
    
    定义统一的管道接口：validate → transform → persist
    """
    
    batch_size: classvar[int] = 500
    
    async def run(
        self,
        repo_uuid: UUID,
        data: Any,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        """
        执行管道
        
        流程：
        1. validate()  数据校验
        2. transform() 数据转换
        3. persist()   持久化
        """
        ...
    
    async def validate(self, data: Any) -> ValidationResult:
        """数据校验，子类实现"""
        raise NotImplementedError
    
    async def transform(self, data: Any) -> Any:
        """数据转换，子类实现"""
        return data
    
    async def persist(self, data: Any) -> PersistResult:
        """持久化，子类实现"""
        raise NotImplementedError


@dataclass
class PipelineResult:
    """管道执行结果"""
    success: bool
    total_count: int
    inserted_count: int
    skipped_count: int
    errors: list[dict]
    elapsed_ms: float
```

### 4.3 数据校验器（Validators）

```python
class AstNodeValidator:
    """AST 节点校验器"""
    
    VALID_NODE_TYPES = {
        "function", "method", "class", "constructor", 
        "call", "import", "interface", "protocol", 
        "variable", "enum", "type",
    }
    
    @classmethod
    def validate(cls, node: dict) -> ValidationResult:
        """校验单个节点"""
        errors = []
        
        # 必填字段
        for field in ("file_id", "node_type", "start_line"):
            if field not in node:
                errors.append(f"缺少必填字段: {field}")
        
        # 类型合法性
        if "node_type" in node and node["node_type"] not in cls.VALID_NODE_TYPES:
            errors.append(f"非法节点类型: {node['node_type']}")
        
        # 行号合法性
        if "start_line" in node and node["start_line"] < 0:
            errors.append(f"行号不能为负数: {node['start_line']}")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)


class CallEdgeValidator:
    """调用边校验器"""
    
    VALID_CALL_TYPES = {"static", "dynamic", "unknown"}
    
    @classmethod
    def validate(cls, edge: dict, node_uuid_map: dict[str, uuid.UUID]) -> ValidationResult:
        """校验单条调用边"""
        errors = []
        
        if "caller_node_id" not in edge:
            errors.append("缺少 caller_node_id")
        elif edge["caller_node_id"] not in node_uuid_map:
            errors.append(f"caller_node_id 不存在: {edge['caller_node_id']}")
        
        if "call_type" in edge and edge["call_type"] not in cls.VALID_CALL_TYPES:
            errors.append(f"非法 call_type: {edge['call_type']}")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)


class ModuleDepValidator:
    """模块依赖校验器"""
    
    VALID_IMPORT_TYPES = {"relative", "absolute", "external"}
    
    @classmethod
    def validate(cls, dep: dict) -> ValidationResult:
        """校验单条模块依赖"""
        errors = []
        
        if "importer_file_id" not in dep:
            errors.append("缺少 importer_file_id")
        
        if "import_type" in dep and dep["import_type"] not in cls.VALID_IMPORT_TYPES:
            errors.append(f"非法 import_type: {dep['import_type']}")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
```

---

## 五、`run_analysis()` 集成变更

### 5.1 当前架构问题

当前 `run_analysis` 中，各 builder 直接调用 DAO：

```python
# 当前（P2-04）
# Step 3: AST 解析 → 直接调用 AstNodeDAO.create_many()
asyncio.run(_parse_and_store_ast(repo_uuid, scan_result))

# Step 4: 结构分析 → builder 直接调用 CallEdgeDAO / ModuleDependencyDAO
asyncio.run(_build_structures(repo_uuid, self))
```

### 5.2 目标架构

通过 `StructureDataPipeline` 统一管理入库：

```python
# 目标（P2-05）
async with async_session_factory() as db:
    pipeline = StructureDataPipeline(db=db, progress_callback=_progress_callback)
    
    # Step 3: 解析 → 管道入库
    parser = ParserFactory.create(language)
    ast_nodes = await parser.parse_file(file_path)
    await pipeline.ingest_ast_nodes(repo_uuid, ast_nodes)
    
    # Step 4: 结构分析 → 管道入库
    call_edges = await CallGraphBuilder().build(repo_uuid, db=db, dry_run=True)
    await pipeline.ingest_call_edges(repo_uuid, call_edges, pipeline.node_uuid_map)
    
    module_deps = await ModuleDependencyBuilder().build(repo_uuid, db=db, dry_run=True)
    await pipeline.ingest_module_deps(repo_uuid, module_deps)
```

### 5.3 进度回调

```python
ProgressCallback = Callable[[int, int, str], None]

def _progress_callback(current: int, total: int, stage: str) -> None:
    """
    入库进度回调
    
    Args:
        current: 当前处理数量
        total: 总数
        stage: 当前阶段（ingest_nodes / ingest_edges / ingest_deps）
    """
    progress = (current / total) * 100 if total > 0 else 0
    logger.info("[%s] 入库进度: %d/%d (%.1f%%)", stage, current, total, progress)
```

---

## 六、增量更新逻辑

### 6.1 增量判断策略

```
文件变更检测流程：

1. 获取当前文件的 content_hash（来自 files 表）
2. 查询上次分析时该文件的 hash 记录（来自 analysis_history 表）
3. 如果 hash 相同 → 跳过该文件的所有节点和边
4. 如果 hash 不同或缺失 → 重新解析并入库

依赖传播（P2-06 扩展）：
- 变更文件的调用方 → 需要重新分析
- 变更文件的被调用方 → 可能需要重新分析
- 导入变更文件的文件 → 需要重新分析
```

### 6.2 数据模型扩展

在 `analysis_history` 表或新增 `file_analysis_snapshots` 表存储每次分析的文件 hash 快照：

```sql
CREATE TABLE file_analysis_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    analysis_version TEXT NOT NULL,  -- 对应 analysis_history.version
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    content_hash VARCHAR(64) NOT NULL,
    nodes_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_file_snapshot UNIQUE (analysis_version, file_id)
);
```

---

## 七、测试覆盖

### 7.1 test_structure_pipeline.py（预计 20 个测试用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_ingest_ast_nodes_success` | 正常入库 AST 节点 |
| `test_ingest_ast_nodes_batch_size` | 批量分片写入 |
| `test_ingest_ast_nodes_deduplication` | 重复节点去重 |
| `test_ingest_ast_nodes_validation` | 校验失败节点被跳过 |
| `test_ingest_call_edges_success` | 正常入库调用边 |
| `test_ingest_call_edges_missing_caller` | caller 不存在时报错 |
| `test_ingest_call_edges_missing_callee` | callee 不存在时（允许为 None） |
| `test_ingest_module_deps_success` | 正常入库模块依赖 |
| `test_ingest_module_deps_missing_importer` | importer 不存在时报错 |
| `test_progress_callback` | 进度回调触发 |
| `test_incremental_skip_unchanged` | 未变更文件跳过 |
| `test_incremental_process_changed` | 变更文件重新入库 |

### 7.2 test_analysis_tasks.py 修改

- 更新 `run_analysis` 测试以适配 `StructureDataPipeline`
- 新增管道集成测试

---

## 八、设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **管道位置** | 服务层（`services/structure_pipeline.py`） | 不直接放 DAO 层，DAO 只负责单表操作；管道负责跨表编排 |
| **批量大小** | 可配置，默认 500 | 平衡内存使用和写入性能，大仓库可调整 |
| **事务边界** | 每批一个事务，Step 间独立 | 一个 Step 失败不影响其他 Step |
| **增量判断** | 基于 `content_hash` 精确判断 | 比 git diff 更准确，不受 Git 历史影响 |
| **去重策略** | `(file_id, start_line, node_type)` 组合键 | 同一文件同一位置同类型节点只保留一条 |
| **校验时机** | 入库前统一校验 | 避免无效数据写入数据库 |
| **进度回调** | 回调函数模式 | 解耦进度通知，支持前端 SSE 推送 |
| **dry_run 模式** | builder 支持不写数据库只返回数据 | 方便 pipeline 接管写入，便于测试 |

---

## 九、与 Phase 2 其他任务的关系

| 任务 | 状态 | 与 P2-05 的关系 |
|------|------|----------------|
| P2-01 GitScanner | ✅ | P2-05 使用 `files` 表的 `content_hash` 做增量判断 |
| P2-02 Tree-sitter 解析 | ✅ | P2-05 接收 parser 输出的 AST 节点，统一入库 |
| P2-03 持久化存储 | ✅ | P2-05 封装 P2-03 的 DAO 层，提供上层管道接口 |
| P2-04 结构分析引擎 | ✅ | P2-05 接收 P2-04 的调用边和模块依赖，统一入库 |
| P2-06 增量扫描 | ⬜ | P2-05 的增量更新逻辑是 P2-06 的基础 |
| P2-07 解析结果前端预览 | ⬜ | P2-05 的进度回调支持 P2-07 的实时进度展示 |

---

## 十、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 依赖传播增量分析 | P2-06 | 变更文件的调用方/被调用方自动纳入重分析 |
| 管道并行化 | P5-01 | 多 Step 并行入库提升大仓库分析速度 |
| 管道可观测性 | P3 | 入库耗时、失败率等指标上报 |
| 管道插件化 | P4 | 支持自定义入库处理器 |

---

## 十一、文件变更明细

### 新增文件

| 文件 | 说明 | 预估行数 |
|------|------|---------|
| `codeinsight/services/__init__.py` | 服务层导出 | 10 |
| `codeinsight/services/structure_pipeline.py` | 结构数据入库管道 | ~300 |
| `codeinsight/pipelines/__init__.py` | 管道层导出 | 10 |
| `codeinsight/pipelines/base.py` | 管道基类 | ~120 |
| `codeinsight/pipelines/validators.py` | 数据校验器 | ~150 |
| `tests/test_structure_pipeline.py` | 入库管道测试 | ~400 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `codeinsight/tasks/analysis_tasks.py` | Step 3/4 改为使用 StructureDataPipeline |
| `codeinsight/analyzers/call_graph.py` | build() 新增 dry_run 模式 |
| `codeinsight/analyzers/module_graph.py` | build() 新增 dry_run 模式 |
| `tests/test_analysis_tasks.py` | 适配新管道 |

---

## 十二、任务完成状态

- [ ] 实现 StructureDataPipeline 类（ingest_ast_nodes, ingest_call_edges, ingest_module_deps）
- [ ] 实现数据校验器（AstNodeValidator, CallEdgeValidator, ModuleDepValidator）
- [ ] 实现批量写入优化（batch_size 分片 + 事务隔离）
- [ ] 实现增量更新逻辑（基于 content_hash 跳过未变更文件）
- [ ] 实现进度回调机制
- [ ] CallGraphBuilder / ModuleDependencyBuilder 新增 dry_run 模式
- [ ] 更新 run_analysis 使用 StructureDataPipeline
- [ ] 创建 file_analysis_snapshots 表（Alembic Migration）
- [ ] 编写入库管道测试（20 个用例）
- [ ] 更新 analysis_tasks 测试
- [ ] 全部测试通过
- [ ] ruff check + mypy 通过

---

## 总结

P2-05 将构建**统一的结构数据入库管道**，作为解析/分析层和数据库之间的编排层。核心交付物：

1. **StructureDataPipeline** — 统一入库入口，提供 `ingest_ast_nodes` / `ingest_call_edges` / `ingest_module_deps` 三个方法
2. **数据校验管道** — 入库前校验节点完整性、外键一致性、类型合法性，拒绝无效数据
3. **批量写入优化** — 默认 `batch_size=500` 分片写入，事务隔离，避免大仓库内存峰值
4. **增量更新逻辑** — 基于文件 `content_hash` 精确判断，跳过未变更文件的重写
5. **进度回调机制** — 支持实时进度通知，为前端 SSE 进度条提供数据源
6. **dry_run 模式** — Builder 支持不写数据库只返回数据，便于管道接管写入

该管道层为后续 P2-06（增量扫描）、P3（AI 分析引擎）提供了统一的数据持久化接口，也提升了 `run_analysis` 的可维护性和可观测性。

---

**开发日期**: 2026-07-12  
**开发人员**: Trae AI  
**任务编号**: P2-05  
**状态**: ⬜ 待实现
