# P2-03: 分析任务持久化存储 — GitScanner + AST 解析结果入库

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-03 |
| 任务名称 | 结构提取与入库：GitScanner 扫描 + AST 解析结果持久化到 PostgreSQL |
| 所属阶段 | Phase 2（第 4-6 周） |
| 优先级 | P0 |
| 预估工时 | 12h |
| 交付物 | `run_analysis` 完整持久化流程 + 单元测试 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-08 Celery 任务框架 | ✅ | `run_analysis` 骨架已就绪 |
| P2-01 GitScanner | ✅ | 文件扫描器已实现 |
| P2-02 Tree-sitter 解析层 | ✅ | 5 种语言解析器已实现 |
| P1-05 ORM 模型 | ✅ | `FileModel`, `AstNodeModel`, `AnalysisVersionModel` 已定义 |
| P1-07 DAO 层 | ✅ | `FileDAO`, `AstNodeDAO`, `AnalysisVersionDAO`, `RepositoryDAO` 已实现 |

### 与上一次 Commit 的基线

- **基线 Commit**: `076cc88 refactor(tests): reorder parser imports and add noqa comments`
- **变更文件数**: 6 个文件
- **代码变更量**: +369 行 / -40 行

---

## 二、整体架构位置

P2-03 是分析管线的**关键胶水层**，将 P2-01（扫描器）和 P2-02（解析器）的输出持久化到数据库，并实现完整的状态追踪。

```
┌──────────────────────────────────────────────────────────────────────┐
│  run_analysis 完整流程                                                │
│                                                                      │
│  Step 1: _do_analysis_setup()                                        │
│          → 创建 AnalysisVersion (status=pending, total_files=0)      │
│          → 更新 Repository (status="analyzing")                       │
│                                                                      │
│  Step 2: GitScanner.scan()  ←── P2-01                               │
│          → _update_analysis_version(status=scanning, total_files=N)  │
│          → _update_repository_stats(file_count, line_count, ...)    │
│          → _store_files_to_db() 批量写入 files 表                     │
│                                                                      │
│  Step 3: ParserFactory 解析  ←── P2-02                               │
│          → _update_analysis_version(status=parsing)                  │
│          → _parse_and_store_ast() 批量写入 ast_nodes 表              │
│                                                                      │
│  Step 4: AI 分析  ←── P3 (待接入)                                    │
│          → _update_analysis_version(status=analyzing_modules, ...)   │
│                                                                      │
│  Step 5: 存储结果 ←── P3 (待接入)                                    │
│          → _update_analysis_version(status=storing, ...)             │
│                                                                      │
│  Step 6: 完成                                                         │
│          → _update_analysis_version(status=completed, completed_at)  │
│          → _set_repo_status(status=completed)                        │
│                                                                      │
│  ✗ 错误分支 (CancelledError / Exception)                             │
│          → _update_analysis_version(status=cancelled/failed, ...)    │
│          → _set_repo_status(status=cancelled/failed)                │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 数据写入顺序

```
ScanResult ──────────────► _store_files_to_db() ────► files 表
    │
    ├── file_id map ──────► _parse_and_store_ast() ──► ast_nodes 表
    │
    └── stats ────────────► _update_repository_stats() ──► repositories 表 (统计字段)

AnalysisVersion ──────────► _update_analysis_version() ──► analysis_versions 表 (每步更新状态)
```

### 2.2 关键约束

- **事务隔离**：每次数据库写入使用独立的 `AsyncSession`（通过 `async_session_factory()`）
- **幂等写入**：每次分析前先用 `delete_by_repository()` 清空旧数据，再批量创建
- **文件 ID 映射**：`files 表 → ast_nodes 表` 通过 `file_id` 外键关联，扫描阶段建立 path→UUID 映射

---

## 三、修改模块结构

```
codeinsight-backend/
├── codeinsight/
│   ├── models/
│   │   └── __init__.py          # 新增: 导出 AstNodeModel
│   ├── repositories/
│   │   ├── __init__.py          # 新增: 导出 FileDAO
│   │   └── file.py              # 新增: FileDAO 完整实现 (84 行)
│   ├── schemas/
│   │   └── __init__.py          # 新增: 导出 AstNode, AstNodeCreate
│   └── tasks/
│       └── analysis_tasks.py    # 核心: 持久化逻辑集成 (267 行变更)
│
└── tests/
    └── test_analysis_tasks.py   # 修复: GitScanner mock 路径 (50 行变更)
```

---

## 四、新增辅助函数

### 4.1 `_update_analysis_version()` — 版本状态持久化

```python
async def _update_analysis_version(
    version_id: UUID,
    status: TaskStatus,
    total_files: int | None = None,
    analyzed_files: int | None = None,
    knowledge_points_count: int | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
) -> None:
```

| 阶段 | status | 更新字段 |
|------|--------|---------|
| Step 2 扫描 | `scanning` | `total_files` |
| Step 3 解析 | `parsing` | — |
| Step 4 AI 分析 | `analyzing_modules` | `analyzed_files` |
| Step 5 存储 | `storing` | `analyzed_files`, `knowledge_points_count` |
| Step 6 完成 | `completed` | `total_files`, `analyzed_files`, `knowledge_points_count`, `completed_at` |
| 取消 | `cancelled` | `completed_at` |
| 失败 | `failed` | `completed_at`, `error_message` |

### 4.2 `_update_repository_stats()` — 仓库统计信息更新

```python
async def _update_repository_stats(
    repo_uuid: UUID,
    total_files: int,
    total_lines: int,
    language_distribution: dict[str, int],
    current_version: str,
    knowledge_points_count: int = 0,
) -> None:
```

扫描完成后一次性更新 `repositories` 表的统计字段，使 API 层可直接读取实时状态。

### 4.3 `_store_files_to_db()` — 文件数据批量入库

```python
async def _store_files_to_db(repo_uuid: UUID, files_data: list[dict]) -> None:
```

- 先 `delete_by_repository()` 清空旧记录（保证幂等）
- 再 `create_many()` 批量写入新记录

### 4.4 `_parse_and_store_ast()` — AST 节点批量入库

```python
async def _parse_and_store_ast(repo_uuid: UUID, scan_result: Any) -> None:
```

核心逻辑：
1. 清空旧 AST 节点
2. 从 `files` 表构建 `path → file_id` 映射
3. 遍历扫描结果，按语言获取解析器
4. 调用 `ParserFactory.get_parser().parse_file()` 获取 AST 节点
5. 将 `ASTNode` dataclass 转换为 ORM 兼容字典，批量写入 `ast_nodes` 表

---

## 五、核心集成：`run_analysis()` 改造

### 5.1 问题诊断（修复前）

| # | 问题 | 影响 |
|---|------|------|
| 1 | 扫描后不更新 `analysis_versions` 表状态 | 前端无法反映真实进度 |
| 2 | 不更新 `repositories` 表统计字段 | API 返回 `file_count=0` |
| 3 | 错误时不更新 `analysis_versions` 表 | 失败状态无法持久化 |
| 4 | `scan_result` 在 repo 为 None 时未定义 | 导致 `UnboundLocalError` |
| 5 | `_utcnow()` 返回 ISO 字符串而非 `datetime` | 模型字段类型不匹配 |

### 5.2 修复方案

| 修复项 | 实现 |
|--------|------|
| **版本状态追踪** | 每个阶段调用 `_update_analysis_version()` 持久化当前状态 |
| **仓库统计更新** | 扫描完成后调用 `_update_repository_stats()` |
| **文件入库** | 扫描结果序列化后调用 `_store_files_to_db()` |
| **AST 入库** | 解析结果通过 `_parse_and_store_ast()` 批量写入 |
| **错误处理增强** | `CancelledError` 和 `Exception` 分支均调用 `_update_analysis_version()` 持久化终态 |
| **`scan_result` 初始化** | 声明为 `scan_result: Any = None`，repo 为 None 时显式抛出 `ValueError` |
| **`_utcnow()` 返回值** | 改为返回 `datetime` 对象 |
| **GitScanner 导入** | 从懒加载改为模块级导入，确保测试 mock 可解析 |

---

## 六、数据写入时序图

```
run_analysis 生命周期
─────────────────────────────────────────────────────────────

T0  setup()
    ├─ INSERT analysis_versions (pending, total_files=0)
    └─ UPDATE repositories (status="analyzing")

T1  GitScanner.scan()
    ├─ UPDATE analysis_versions (scanning, total_files=N)
    ├─ UPDATE repositories (file_count=N, line_count=M, ...)
    └─ INSERT files [] (批量)

T2  parse_and_store_ast()
    ├─ UPDATE analysis_versions (parsing)
    ├─ DELETE ast_nodes (旧数据)
    └─ INSERT ast_nodes [] (批量)

T3  analyze_with_agents() [Phase 3]
    └─ UPDATE analysis_versions (analyzing_modules)

T4  store_results() [Phase 3]
    └─ UPDATE analysis_versions (storing)

T5  完成
    ├─ UPDATE analysis_versions (completed, completed_at)
    └─ UPDATE repositories (status="completed")

E1  异常
    ├─ UPDATE analysis_versions (failed, error_message)
    └─ UPDATE repositories (status="failed")

E2  取消
    ├─ UPDATE analysis_versions (cancelled, completed_at)
    └─ UPDATE repositories (status="cancelled")
```

---

## 七、测试覆盖

### 7.1 修改测试（3 个用例）

| 测试 | 修改内容 |
|------|---------|
| `test_run_analysis_cancellation_at_parsing_phase` | 修复 mock 路径：`codeinsight.scanners.git_scanner.GitScanner` → `codeinsight.tasks.analysis_tasks.GitScanner` |
| `test_run_analysis_cancellation_at_storing_phase` | 同上 + 修复缩进 |
| `test_run_analysis_no_cancellation_completes_normally` | 同上 |

### 7.2 测试验证结果

```
$ python -m pytest tests/test_analysis_tasks.py -v
======================= 23 passed, 6 warnings in 0.90s =======================
```

| 检查项 | 结果 |
|--------|------|
| `test_run_analysis_cancellation_at_scanning_phase` | ✅ |
| `test_run_analysis_cancellation_at_parsing_phase` | ✅ |
| `test_run_analysis_cancellation_at_storing_phase` | ✅ |
| `test_run_analysis_no_cancellation_completes_normally` | ✅ |
| 其余 19 个现有测试 | ✅ 全部通过 |

---

## 八、设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **事务策略** | 每个 helper 独立 session + commit | 隔离失败影响，避免级联回滚 |
| **数据清理策略** | 先 `delete_by_repository` 再 `create_many` | 保证幂等性，避免重复记录 |
| **文件 ID 映射** | 扫描后查 `files` 表构建 path→UUID map | 不依赖内存状态，支持 session 隔离 |
| **GitScanner 导入位置** | 模块级导入（非懒加载） | 解决测试 `unittest.mock.patch` 路径解析问题 |
| **`_utcnow()` 返回类型** | `datetime` 对象（非 ISO 字符串） | 匹配 SQLAlchemy `DateTime` 列类型 |
| **错误分支的 version_id 保护** | `try/except` 静默处理 | `version_id` 可能在 Step 1 之前就未初始化 |
| **`scan_result` 初始化** | 声明为 `scan_result: Any = None` | 防止 repo 为 None 时的 `UnboundLocalError` |

---

## 九、与 Phase 2 其他任务的关系

| 任务 | 状态 | 与 P2-03 的关系 |
|------|------|----------------|
| P2-01 GitScanner | ✅ 已完成 | P2-03 直接集成 `GitScanner.scan()` 并持久化结果 |
| P2-02 Tree-sitter 解析 | ✅ 已完成 | P2-03 直接集成 `ParserFactory.get_parser()` 并持久化结果 |
| P2-04 调用图构建 | ⬜ 待实现 | 依赖 P2-03 写入的 `ast_nodes` 数据 |
| P2-05 结构数据入库管道 | ⬜ 待实现 | 本任务已覆盖 `files` + `ast_nodes` 入库，后续扩展其他结构 |
| P2-06 增量扫描 | ⬜ 待实现 | 依赖 P2-03 建立的 `content_hash` 和 `analysis_versions` 状态追踪 |

---

## 十、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 调用图构建 | P2-04 | 基于 `ast_nodes` 表的 `parent_node_id` 和 `call` 节点类型 |
| 增量扫描引擎 | P2-06 | 对比新旧 `analysis_versions` 的 `content_hash` |
| AI 分析 Agent | P3-02 | 接入 `_update_analysis_version(status=analyzing_modules)` 后的真实分析逻辑 |
| 前端进度展示 | P4-06 | 前端轮询 `analysis_versions` 表的实时状态 |

---

## 十一、文件变更明细

### 修改文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `codeinsight/tasks/analysis_tasks.py` | **核心修改** | 新增 4 个 helper，集成完整持久化流程，修复 5 个 bug |
| `tests/test_analysis_tasks.py` | 修复 | GitScanner mock 路径 + 缩进修正 |
| `codeinsight/models/__init__.py` | 导出更新 | 新增 `AstNodeModel` |
| `codeinsight/repositories/__init__.py` | 导出更新 | 新增 `FileDAO` |
| `codeinsight/repositories/file.py` | 新文件 | `FileDAO` 完整实现（`create_many`, `delete_by_repository`, `get_by_repository`） |
| `codeinsight/schemas/__init__.py` | 导出更新 | 新增 `AstNode`, `AstNodeCreate` |

---

## 十二、任务完成状态

- [x] 诊断并修复 5 个持久化缺失问题
- [x] 实现 `_update_analysis_version()` 状态追踪 helper
- [x] 实现 `_update_repository_stats()` 统计更新 helper
- [x] 实现 `_store_files_to_db()` 文件批量入库
- [x] 实现 `_parse_and_store_ast()` AST 批量入库
- [x] 集成到 `run_analysis()` 完整流程
- [x] 增强错误处理（CANCELLED / FAILED 持久化）
- [x] 修复 `scan_result` 未定义问题
- [x] 修复 `_utcnow()` 返回类型
- [x] 修复 GitScanner 导入路径（测试兼容性）
- [x] 修复 3 个测试用例
- [x] 全部 23 个测试通过
- [x] 导出 `AstNodeModel`, `FileDAO`, `AstNode`, `AstNodeCreate`

---

## 总结

P2-03 任务已完成。成功将 P2-01（GitScanner）和 P2-02（Tree-sitter 解析器）的输出持久化到 PostgreSQL 数据库，实现了 `analysis_versions` 表的完整状态追踪和 `repositories` 表的统计信息实时更新。修复了 5 个核心问题（状态不持久化、统计不更新、错误不记录、变量未定义、类型不匹配），新增 4 个辅助函数，重构 `run_analysis()` 主流程，所有 23 个测试用例通过。

该持久化层为后续 P2-04（调用图构建）、P2-06（增量扫描）和 P3（AI 分析引擎）提供了完整的数据基础。

---

**开发日期**: 2026-07-12  
**开发人员**: Trae AI  
**任务编号**: P2-03  
**状态**: ✅ 已完成
