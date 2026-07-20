# P3-Critical-Fixes 报告：Critical 问题修复

> 任务：修复 P3 阶段综合审查发现的 9 个 Critical 问题
> 日期：2026-07-20

---

## 1. 修复清单

### 1.1 L-B1/L-B2: `choices` 空列表检查（`llm/client.py`）

**问题**：`chat()` 和 `chat_stream()` 中 `response.choices[0]` 直接取下标，未做空列表检查。若模型返回空 choices（如拒绝响应、API 超时）会抛出 `IndexError`。

**修复**：
- `chat()`: 改为 `response.choices[0] if response.choices else None`，若为 `None` 则抛出有意义的 `LLMError`
- `chat_stream()`: 循环内增加 `if not chunk.choices: continue` 跳过空 chunk

### 1.2 L-B3: `embed()` 类型错误（`llm/client.py`）

**问题**：`data.get("embedding", [])` 在 litellm 返回的对象上调用 `.get()` 方法，实际应为 `data.embedding`（属性访问），导致 `AttributeError`。

**修复**：改为 `[data.embedding for data in response.data]`

### 1.3 L-B4: `chat_with_fallback()` 并发安全（`llm/client.py`）

**问题**：方法直接修改 `self.config.provider`、`self.config.model` 和 `self._model_name`，多协程共享实例时状态互相覆盖。异常时状态恢复不完整（`asyncio.CancelledError` 跳过恢复逻辑）。

**修复**：
- 新增 `self._config_lock = asyncio.Lock()` 保护配置修改
- `chat_with_fallback()`: 整个 fallback 循环在 `async with self._config_lock` 内，同时保存和恢复 `self.config.model`
- `chat_for_task()`: 路由逻辑在 `async with self._config_lock` 内，使用 `try/finally` 确保状态始终恢复

### 1.4 A-B1: `error` 字段被覆盖（`agents/state.py`）

**问题**：`error` 字段使用 `_keep_last` reducer，并行节点中成功节点返回 `None` 覆盖了失败节点的错误信息，导致错误丢失。

**修复**：改为 `_keep_first`，保留第一个非 `None` 值

### 1.5 O-B1: 共享 Session 契约违反（`tasks/analysis_orchestrator.py`）

**问题**：12 个方法在 `db is not None`（共享 session 模式）时仍主动调用 `await db.commit()`，破坏事务完整性。可能引发脏写、部分提交无法回滚等问题。

**修复**：移除以下 12 处 `await db.commit()`：

| 方法 | 行号 |
|------|------|
| `_do_analysis_setup` | 198 |
| `_update_analysis_version` | 260 |
| `_set_repo_status` | 273 |
| `_update_repository_stats` | 308 |
| `_store_files_to_db` | 328 |
| `parse_ast` | 571 |
| `parse_ast_incremental` | 688 |
| `build_structures` | 753 |
| `build_structures_incremental` | 802 |
| `detect_frameworks_and_routes` | 839 |
| `save_snapshot` | 1144 |
| `cleanup_failed_step_data` | 1240 |

### 1.6 S-S1: `setattr` 无限制赋值（`repositories/knowledge_point.py`）

**问题**：`KnowledgePointDAO.update()` 使用 `setattr(kp, key, value)` 无限制批量赋值，调用者可以覆盖 `id`、`repository_id`、`created_at` 等敏感字段，属于安全漏洞。

**修复**：新增 `_ALLOWED_UPDATE_FIELDS` 白名单（`frozenset`），只允许更新 `title`、`description`、`confidence`、`tags`、`code_snippets`、`call_chain`、`expansion`、`knowledge_metadata`、`version`、`category`、`category_name`，其余字段跳过并记录警告。

### 1.7 E-B1: 置信度错误报告为 F1（`evaluation/evaluator.py`）

**问题**：`SelfEvaluator.self_evaluate()` 将 `avg_confidence` 赋值给 `overall_f1`、`overall_precision`、`overall_recall`，置信度与 F1 语义完全不等价，产生误导性报告。

**修复**：将 F1/Precision/Recall 均设为 `0.0`，日志中明确标注"自评估仅提供置信度，F1/Precision/Recall 不可用"。

### 1.8 E-B2: ABTestRunner 配置突变（`evaluation/engine.py`）

**问题**：`ABTestRunner.run()` 原地修改 `self._engine.config`，非线程安全，异常时配置无法恢复。

**修复**：使用 `copy.deepcopy()` 创建配置副本，避免修改共享引擎的配置。

### 1.9 S-B1: 单例非线程安全（`services/meilisearch_client.py`）

**问题**：`MeiliSearchClient` 单例模式在 `__new__` 中无锁保护，多协程同时通过 `if cls._instance is None` 检查时可能创建多个实例。

**修复**：新增 `threading.Lock` 保护 `__new__` 中的双检锁模式。

## 2. 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `codeinsight/llm/client.py` | choices 空列表检查（chat/chat_stream）、embed 类型修复、配置锁 + try/finally |
| `codeinsight/agents/state.py` | `error` 字段 reducer 改为 `_keep_first` |
| `codeinsight/tasks/analysis_orchestrator.py` | 移除 12 处共享 session 中的 `db.commit()` |
| `codeinsight/repositories/knowledge_point.py` | 新增 `_ALLOWED_UPDATE_FIELDS` 白名单 |
| `codeinsight/evaluation/evaluator.py` | F1/Precision/Recall 设为 0.0，日志标注不可用 |
| `codeinsight/evaluation/engine.py` | ABTestRunner 使用 `copy.deepcopy()` |
| `codeinsight/services/meilisearch_client.py` | 单例双检锁 |
| `codeinsight/evaluation/data/registry.py` | `glob` → `rglob`，递归加载子目录 JSON |
| `tests/test_evaluation_v2.py` | 同步更新测试断言 |

## 3. CI 验证

| 检查项 | 结果 |
|--------|------|
| ruff check | ✅ 0 errors |
| mypy | ✅ 0 issues in 8 files |
| pytest | ✅ 589 passed, 2 skipped |

## 4. 自回归审查

### 4.1 Critical 修复审查

修复完成后对 7 个修改文件进行了二次审查，确认：

1. **无回归**：所有测试通过，未引入新的 lint/mypy 错误
2. **修复完整性**：所有 9 个 Critical 问题均已处理
3. **边界情况**：
   - `choices` 空列表：后续 `content` 为 `None` 时也抛出 `LLMError`，覆盖了 `model_validate_json(None)` 的潜在问题
   - `_config_lock` 保护范围：`chat_with_fallback()` 整个 fallback 循环在锁内，`chat_for_task()` 仅路由部分在锁内，正常路径不受影响
   - 共享 session 修复：移除 `commit()` 后，`flush()` 调用保持不变，不影响数据可见性
   - `setattr` 白名单：`_ALLOWED_UPDATE_FIELDS` 包括 `version` 字段，P3-12 增量分析中更新版本号的操作不受影响

### 4.2 附：CI 评估回归修复

**问题**：CI 评估中 `--languages typescript` 运行时 F1=0.0000（0 用例），导致回归检测触发 F1 1.0000→0.0000 告警。

**根因**：`load_datasets_from_dir()` 使用 `glob("*.json")` 仅扫描顶层目录。TypeScript 测试用例存储在 `data/typescript/` 子目录中，未被加载。

**修复**：`registry.py` 第 212 行 `glob("*.json")` → `rglob("*.json")` 递归加载子目录 JSON 文件。修复后验证：
- 加载 30 个数据集（此前仅 5 个）
- 覆盖 6 种语言（go/java/javascript/python/typescript/vue）
- 覆盖 5 个分类（AD/AL/DK/DP/ET）
- 共 165 个测试用例