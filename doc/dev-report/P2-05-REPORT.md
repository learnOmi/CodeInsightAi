# P2-05: 结构数据入库管道 — 统一入库编排层

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-05 |
| 任务名称 | 结构数据入库管道：统一校验 + 批量写入 + 进度回调 |
| 所属阶段 | Phase 2（第 4-6 周） |
| 优先级 | P0 |
| 预估工时 | 8h |
| 交付物 | StructureDataPipeline + 数据校验器 + 进度回调 + dry_run 模式 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P2-01 GitScanner | ✅ | `files` 表已就绪，提供 `content_hash` |
| P2-02 Tree-sitter 解析层 | ✅ | 5种语言解析器已实现，输出 ASTNode 列表 |
| P2-03 持久化存储 | ✅ | 各 DAO 已实现（AstNodeDAO, CallEdgeDAO, ModuleDependencyDAO） |
| P2-04 结构分析引擎 | ✅ | CallGraphBuilder / ModuleDependencyBuilder 已实现 |
| P1-07 DAO 层 | ✅ | DAO 模式已建立 |

---

## 二、整体架构位置

P2-05 在分析管线中作为**数据持久化编排层**，位于解析/分析层和 DAO 层之间：

```
┌──────────────────────────────────────────────────────────────────────┐
│  run_analysis 完整流程                                                │
│                                                                      │
│  Step 1: _do_analysis_setup()                                        │
│  Step 2: GitScanner.scan() → _store_files_to_db()                   │
│                                                                      │
│  Step 3: ParserFactory 解析  ←── P2-02 ✅                            │
│          → AST 节点                                                  │
│          ↓                                                           │
│          📦 StructureDataPipeline.ingest_ast_nodes()  ←── P2-05      │
│          → ast_nodes 表                                               │
│                                                                      │
│  Step 4: 结构分析                                                    │
│          CallGraphBuilder.build_data() → 调用边列表                  │
│          ModuleDependencyBuilder.build_data() → 依赖边列表            │
│          ↓                                                           │
│          📦 StructureDataPipeline.ingest_call_edges()  ←── P2-05     │
│          📦 StructureDataPipeline.ingest_module_deps()  ←── P2-05    │
│          → call_edges 表 + module_dependencies 表                     │
│                                                                      │
│  Step 5: AI 分析  ←── P3 (待接入)                                    │
│  Step 6: 完成                                                         │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 关键设计决策

- **Builder 退居数据生产者**：`CallGraphBuilder` / `ModuleDependencyBuilder` 新增 `build_data()` 方法只返回数据，由 Pipeline 接管写入
- **Pipeline 编排写入**：`StructureDataPipeline` 负责校验 → 批量写入 → 进度回调
- **progress_callback 回调**：Step 3/4 的入库进度通过回调函数实时通知 Celery 任务状态，前端可看到精确的解析/结构分析进度

---

## 三、修改模块结构

```
codeinsight-backend/
├── codeinsight/
│   ├── pipelines/              # 新增: 管道层
│   │   ├── __init__.py
│   │   ├── base.py             # 管道基类 + PipelineResult
│   │   └── validators.py       # 数据校验器（3 个）
│   ├── services/               # 新增: 服务层
│   │   ├── __init__.py
│   │   └── structure_pipeline.py  # 结构数据入库管道（核心）
│   ├── analyzers/
│   │   ├── call_graph.py       # 修改: 新增 build_data() + dry_run 模式
│   │   └── module_graph.py     # 修改: 新增 build_data() + dry_run 模式
│   └── tasks/
│       └── analysis_tasks.py   # 修改: 使用 StructureDataPipeline 接管 Step 3/4 入库
│
└── tests/
    ├── test_structure_pipeline.py  # 新增: 20 个校验器测试
    └── test_analysis_tasks.py      # 无需修改（已 mock）
```

---

## 四、核心功能实现

### 4.1 StructureDataPipeline — 统一入库管道

```
StructureDataPipeline(db, batch_size=500, progress_callback)
├── ingest_ast_nodes(repo_uuid, nodes)        # 入库 AST 节点（校验 + 去重 + 批量写入）
├── ingest_call_edges(repo_uuid, edges)       # 入库调用边（校验 + 批量写入）
└── ingest_module_deps(repo_uuid, deps)       # 入库模块依赖（校验 + 批量写入）
```

**关键特性：**

| 特性 | 实现 |
|------|------|
| **数据校验** | 入库前校验必填字段、类型白名单、外键存在性、数值合法性 |
| **去重** | AST 节点基于 `(file_id, start_line, node_type, name)` 去重 |
| **批量写入** | `batch_size=500` 分片，每批独立 `commit()` |
| **进度回调** | 每批写入后调用 `progress_callback(current, total, stage)` |
| **外键缓存** | 首次调用时加载 `files` 和 `ast_nodes` 的 ID 集合，后续复用 |

### 4.2 数据校验器

| 校验器 | 校验内容 |
|--------|---------|
| `AstNodeValidator` | 必填字段（9 个）、node_type 白名单（12 种）、行号非负、start_line <= end_line、file_id UUID 格式 |
| `CallEdgeValidator` | caller_node_id 存在且合法、callee_node_id 可选且合法、call_type 白名单（static/dynamic/unknown）、行号非负 |
| `ModuleDepValidator` | importer_file_id 存在且合法、imported_file_id 可选且合法、import_type 白名单（relative/absolute/external）、import_name 非空 |

### 4.3 dry_run 模式

Builder 新增 `dry_run=True` 参数和 `build_data()` 方法：

```python
# 旧模式：builder 直接写入数据库
call_edges_count = await CallGraphBuilder().build(repo_uuid, db=db)

# 新模式：builder 返回数据，pipeline 写入
call_edges = await CallGraphBuilder().build_data(repo_uuid, db=db)
result = await pipeline.ingest_call_edges(repo_uuid, call_edges)
```

### 4.4 进度回调集成

`run_analysis` 中 Step 3 和 Step 4 的入库进度通过回调函数映射到 Celery 任务状态：

- **Step 3 (AST 解析)**: `25.0% + (current/total) * 10%` — 进度从 25% 到 35%
- **Step 4 (结构分析)**: `50.0% + (current/total) * 10%` — 进度从 50% 到 60%

---

## 五、数据模型

无需新增数据表。P2-05 仅新增编排层，不修改已有数据模型。

---

## 六、测试覆盖

### 6.1 test_structure_pipeline.py（20 个测试用例）

| 测试类 | 用例 | 覆盖内容 |
|--------|------|---------|
| `TestAstNodeValidator` | 7 | 合法节点、缺少必填字段、非法 node_type、负数行号、start_line > end_line、非法 file_id、12 种 node_type 全通过 |
| `TestCallEdgeValidator` | 6 | 含/不含 callee 的合法边、缺少 caller、caller 不存在、非法 call_type、3 种 call_type 全通过 |
| `TestModuleDepValidator` | 7 | 含/不含 imported 的合法依赖、缺少 importer、importer 不存在、非法 import_type、3 种 import_type 全通过、空 import_name |

### 6.2 验证结果

```
$ python -m pytest tests/test_structure_pipeline.py -v
============================= 20 passed in 0.45s ==============================
```

```
$ python -m ruff check codeinsight/pipelines/ codeinsight/services/ codeinsight/tasks/analysis_tasks.py codeinsight/analyzers/call_graph.py codeinsight/analyzers/module_graph.py tests/test_structure_pipeline.py
All checks passed!
```

| 检查项 | 结果 |
|--------|------|
| `test_structure_pipeline.py` 20 用例 | ✅ 全部通过 |
| `test_call_graph.py` 12 用例 | ✅ 全部通过（无回归） |
| `test_module_graph.py` 12 用例 | ✅ 全部通过（无回归） |
| 其他 74 用例（DAO/API 测试） | ✅ 全部通过 |
| ruff check | ✅ All checks passed |
| mypy | ⚠️ 未安装（环境限制，非 P2-05 引入） |

---

## 七、设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **管道位置** | 服务层（`services/structure_pipeline.py`） | 不直接放 DAO 层，DAO 只负责单表操作；管道负责跨表编排 |
| **batch_size** | 可配置，默认 500 | 平衡内存使用和写入性能 |
| **事务边界** | 每批一个事务，Step 间独立 | 一个 Step 失败不影响其他 Step |
| **校验时机** | 入库前统一校验 | 避免无效数据写入数据库 |
| **进度回调** | 回调函数模式 | 解耦进度通知，支持 Celery 状态更新 |
| **dry_run 模式** | Builder 支持 `build_data()` 只返回数据 | 便于 Pipeline 接管写入，测试更灵活 |
| **外键 ID 缓存** | 首次调用时加载，后续复用 | 避免每次入库都全量查询 ID 集合 |

---

## 八、与 Phase 2 其他任务的关系

| 任务 | 状态 | 与 P2-05 的关系 |
|------|------|----------------|
| P2-01 GitScanner | ✅ | P2-05 使用 `files` 表的 `content_hash` 做增量判断基础 |
| P2-02 Tree-sitter 解析 | ✅ | P2-05 接收 parser 输出的 ASTNode，统一入库 |
| P2-03 持久化存储 | ✅ | P2-05 封装 P2-03 的 DAO 层，提供上层管道接口 |
| P2-04 结构分析引擎 | ✅ | P2-05 接收 P2-04 的调用边和模块依赖，统一入库 |
| P2-06 增量扫描 | ⬜ | P2-05 的校验和进度回调是 P2-06 的基础 |
| P2-07 解析结果前端预览 | ⬜ | P2-05 的 progress_callback 支持 P2-07 的实时进度展示 |

---

## 九、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 依赖传播增量分析 | P2-06 | 变更文件的调用方/被调用方自动纳入重分析 |
| 管道并行化 | P5-01 | 多 Step 并行入库提升大仓库分析速度 |
| 管道可观测性 | P3 | 入库耗时、失败率等指标上报 |
| 管道插件化 | P4 | 支持自定义入库处理器 |

---

## 十、文件变更明细

### 新增文件

| 文件 | 说明 | 行数 |
|------|------|------|
| `codeinsight/pipelines/__init__.py` | 管道层导出 | 15 |
| `codeinsight/pipelines/base.py` | 管道基类 + PipelineResult | 140 |
| `codeinsight/pipelines/validators.py` | 数据校验器（3 个） | 230 |
| `codeinsight/services/__init__.py` | 服务层导出 | 12 |
| `codeinsight/services/structure_pipeline.py` | 结构数据入库管道 | 280 |
| `tests/test_structure_pipeline.py` | 校验器测试（20 用例） | 270 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `codeinsight/tasks/analysis_tasks.py` | Step 3/4 使用 StructureDataPipeline + 进度回调 |
| `codeinsight/analyzers/call_graph.py` | 新增 `build_data()` 方法 + `dry_run` 参数 |
| `codeinsight/analyzers/module_graph.py` | 新增 `build_data()` 方法 + `dry_run` 参数 |

---

## 十一、任务完成状态

- [x] 实现数据校验器（AstNodeValidator, CallEdgeValidator, ModuleDepValidator）
- [x] 实现管道基类（BasePipeline, PipelineResult）
- [x] 实现 StructureDataPipeline（ingest_ast_nodes, ingest_call_edges, ingest_module_deps）
- [x] CallGraphBuilder 新增 `build_data()` 方法 + `dry_run` 模式
- [x] ModuleDependencyBuilder 新增 `build_data()` 方法 + `dry_run` 模式
- [x] 更新 `run_analysis` 使用 StructureDataPipeline
- [x] 新增 progress_callback 进度回调机制
- [x] 编写校验器测试（20 个用例）
- [x] ruff check 通过
- [x] 全部 118 个相关测试通过，无回归

---

## 总结

P2-05 已完成。成功构建了**结构数据入库管道**，统一编排 AST 节点、调用边、模块依赖的入库流程：

1. **数据校验** — 入库前校验必填字段、类型白名单、外键存在性、数值合法性，拒绝无效数据写入
2. **批量写入** — `batch_size=500` 分片写入，每批独立事务，大仓库分片入库避免内存峰值
3. **进度回调** — 每批写入后通过 `progress_callback(current, total, stage)` 通知进度，Step 3 从 25% 到 35%，Step 4 从 50% 到 60%
4. **Builder 分离** — CallGraphBuilder / ModuleDependencyBuilder 新增 `build_data()` 方法只返回数据，由 Pipeline 接管写入，职责更清晰
5. **测试覆盖** — 20 个新测试用例覆盖三种校验器的合法/非法场景，118 个相关测试全部通过

该管道层为后续 P2-06（增量扫描）、P2-07（前端进度条）、P3（AI 分析引擎）提供了统一的数据持久化接口和可观测的入库进度。

---

**开发日期**: 2026-07-12  
**开发人员**: Trae AI  
**任务编号**: P2-05  
**状态**: ✅ 已完成
