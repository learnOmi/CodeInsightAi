# P2-FixP7 共享 Session 审查报告

> **生成日期:** 2026-07-14
> **审查对象:** `codeinsight-backend/codeinsight/tasks/analysis_orchestrator.py`
> **审查范围:** P2-FixP7 共享 Session 重构
> **审查结论:** ✅ 通过，1 项小问题已修复

---

## 一、重构目标

解决 P2-FixP6 阶段遗留的 **P-2（共享 Session）** 问题：`AnalysisOrchestrator` 的每次任务调用中，17 处独立的 `async_session_factory()` 调用创建 17 个数据库连接，对连接池造成压力。

**目标：** 使用单一共享 session 贯穿整个分析流程，将独立连接数从 17 降至 1（主流程）。

---

## 二、实现方案

### 2.1 核心设计

所有数据库方法增加可选 `db: AsyncSession | None = None` 参数：

| 调用方式 | 行为 |
|----------|------|
| `method(self, db=shared_db)` | 使用调用方提供的共享 session |
| `method(self, db=None)` | 方法自行创建独立 session（向后兼容） |

`_run_async()` 中使用单一 `async with async_session_factory() as shared_db` 贯穿所有步骤。

### 2.2 方法签名变更

| 方法 | 原签名 | 新签名 |
|------|--------|--------|
| `_get_repo_path` | `(self)` | `(self, db: AsyncSession \| None = None)` |
| `_do_analysis_setup` | `(self)` | `(self, db: AsyncSession \| None = None)` |
| `_update_analysis_version` | `(self, ...)` | `(self, db: AsyncSession \| None, ...)` |
| `_set_repo_status` | `(self, status)` | `(self, db: AsyncSession \| None, status)` |
| `_update_repository_stats` | `(self, ...)` | `(self, db: AsyncSession \| None, ...)` |
| `_store_files_to_db` | `(self, files_data)` | `(self, db: AsyncSession \| None, files_data)` |
| `_reconstruct_scan_result` | `(self)` | `(self, db: AsyncSession \| None = None)` |
| `scan_files` | `(self)` | `(self, db: AsyncSession \| None = None)` |
| `compute_incremental_diff` | `(self)` | `(self, db: AsyncSession \| None = None)` |
| `parse_ast` | `(self, progress_callback)` | `(self, db: AsyncSession \| None, progress_callback)` |
| `parse_ast_incremental` | `(self, progress_callback)` | `(self, db: AsyncSession \| None, progress_callback)` |
| `build_structures` | `(self, progress_callback)` | `(self, db: AsyncSession \| None, progress_callback)` |
| `build_structures_incremental` | `(self, progress_callback)` | `(self, db: AsyncSession \| None, progress_callback)` |
| `save_snapshot` | `(self)` | `(self, db: AsyncSession \| None = None)` |
| `complete` | `(self, knowledge_points_count)` | `(self, db: AsyncSession \| None, knowledge_points_count)` |
| `fail` | `(self, error_message)` | `(self, db: AsyncSession \| None, error_message)` |
| `cancel` | `(self)` | `(self, db: AsyncSession \| None)` |
| `get_in_progress_version` | `(self)` | `(self, db: AsyncSession \| None = None)` |
| `cleanup_failed_step_data` | `(self, failed_status)` | `(self, db: AsyncSession \| None, failed_status)` |

### 2.3 事务策略

**多提交粒度**：共享 session 内每个步骤（扫描、AST 解析、结构分析等）独立调用 `commit()`，而非将整个分析流程包装为单一事务。

**理由：**
- 断点续跑支持：每个步骤完成后数据已持久化，重启可从中间继续
- 长事务风险：分析大型仓库可能需要数十分钟，单一事务锁表风险过高
- 失败恢复：步骤失败时仅回滚当前步骤，不影响已完成数据

---

## 三、审查发现

### 🔴 已修复

| # | 问题 | 位置 | 处理 |
|---|------|------|------|
| 1 | 死代码 `_resolve_session()` — 定义了辅助函数但从未调用 | L52-61 | ✅ 已删除 |

### 🟡 设计观察（无需修复）

| # | 观察 | 详情 |
|---|------|------|
| 1 | **代码膨胀** | 文件从 ~600 行膨胀到 ~1020 行。每个方法都有 `if db is not None / else async with` 双路径逻辑。原因是保持 `db=None` 向后兼容（测试代码调用 `fail(None, ...)` 等）。可接受。 |
| 2 | **`_do_analysis_setup` 内外部拆分为两方法** | `_do_analysis_setup_inner()` 不含 commit，由外层决定 commit 行为。这是合理的模式，避免了代码重复。 |
| 3 | **`run()` 嵌套 `asyncio.run()`** | `except Exception` 分支中调用 `asyncio.run(self.fail(None, ...))`，在共享 session 已关闭后创建新 event loop。行为正确（失败标记需要独立事务），但嵌套 `asyncio.run()` 不优雅。属于预存在代码，非本次引入。 |
| 4 | **`skip_to_step` 命名** | 变量意为"跳过的步骤"，实际含义是"已完成的步骤（从此继续）"。属于预存在代码，不影响功能。 |

---

## 四、验证结果

| 检查项 | 结果 |
|--------|------|
| `py_compile` | ✅ 通过 |
| `ruff check` | ✅ All checks passed |
| `mypy` | ✅ Success: no issues found in 69 source files |

---

## 五、性能预期

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 单次任务数据库连接数 | ~17 | 1（主流程） |
| 连接池压力 | 高（每次任务占用 17 个连接） | 低（1 个连接复用整个流程） |
| 并发任务上限 | 受连接池大小限制（如 20 连接池 → 最多 1 个并发任务） | 连接池大小 ÷ 1（如 20 连接池 → 最多 20 个并发任务） |

---

## 六、后续建议

1. **长事务监控**：共享 session 的生命周期跨越整个分析流程（可能数十分钟），建议在 session 级别增加 heartbeat 或空闲超时检查，防止连接被数据库服务器提前关闭
2. **`run()` 异常处理**：考虑将 `asyncio.run(self.fail(None, ...))` 替换为更优雅的方案（如在 `_run_async()` 顶部使用 `try/except` 统一处理）
3. **测试覆盖**：当前测试主要验证 `db=None` 路径；建议增加 `db=shared_db` 路径的集成测试

---

**审查人:** CodeInsight AI Review
**审查日期:** 2026-07-14
