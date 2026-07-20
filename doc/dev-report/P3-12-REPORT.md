# P3-12 报告：增量分析 Agent

> 任务：增量分析 Agent：仅分析变更文件的知识点
> 优先级：P1 | 预估工时：10h | 模块：AI / Analysis
> 日期：2026-07-20

---

## 1. 任务概述

P3-12 目标是将增量分析策略扩展到 AI Agent 阶段。此前增量分析仅覆盖结构分析阶段（AST 解析、调用图、模块依赖），AI Agent 阶段始终对所有文件运行全量 LLM 分析。P3-12 使 AI Agent 仅分析变更文件，并保留未变更文件的已有知识点。

## 2. 实现内容

### 2.1 修改文件

| 文件 | 变更 | 说明 |
|------|------|------|
| `tasks/analysis_orchestrator.py` | 修改 | Step 5 新增增量 AI Agent 分支 |

### 2.2 核心逻辑：增量 AI Agent 模式

在 `AnalysisOrchestrator._run_async()` Step 5 中，当 `do_full_analysis=False` 且 `incremental_diff` 可用时，执行以下步骤：

```
1. 从 incremental_diff 获取 affected_paths (变更 + 传播)
2. 构建 file_path → file_id 映射
3. 过滤 ast_data 和 code_snippets → 只保留变更文件
4. 加载上一版本的知识点
5. 遍历每个知识点：
   - code_snippets.file_path 与 affected_paths 有交集 → 删除（后续由 LLM 重新生成）
   - 无交集 → 保留，更新 version 到当前版本
6. 运行 AnalysisGraph（仅处理变更文件的少量数据）
7. 新知识点正常保存入库
8. 保留的知识点已在步骤 5 中更新版本号
```

## 3. 架构设计

### 3.1 增量分析管线（完整）

```
scan_files() → compute_diff()
  → parse_ast_incremental()        [仅变更文件]
  → build_structures_incremental()  [仅变更文件]
  → Agent AI (INCREMENTAL)          [新增: 仅变更文件]
      → 过滤 ast_data/code_snippets
      → 加载上一版本 KPs
      → 拆分保留/受影响
      → 删除受影响 KPs
      → 运行 AnalysisGraph
      → 保留 KPs 更新版本号
  → save_snapshot()
```

### 3.2 知识点合并策略

```
上一版本 KPs (version=v1)
  ├─ code_snippets 涉及变更文件 → 删除 (LLM 重新生成)
  └─ code_snippets 不涉及变更文件 → 保留，version 更新为 v2

AnalysisGraph 输出 (仅变更文件)
  └─ 新生成的 KPs → 保存为 version=v2

最终 DB 状态 (version=v2)
  = 保留的 KPs (原 v1, 现 v2) + 新生成的 KPs (v2)
```

## 4. 变更详情

### 4.1 `AnalysisOrchestrator` Step 5 增量分支

**位置**：`codeinsight/tasks/analysis_orchestrator.py` 第 1453-1487 行

**关键代码段**：

```python
# P3-12: 增量 AI Agent 模式
if not do_full_analysis and self.incremental_diff is not None:
    affected_paths = {c.path for c in self.incremental_diff.changed_files}
    affected_paths.update(self.incremental_diff.propagated_files)

    # 过滤 ast_data 和 code_snippets
    file_path_to_id = {f.path: f.id for f in files}
    affected_file_ids = {file_path_to_id[p] for p in affected_paths if p in file_path_to_id}
    ast_data = [a for a in ast_data if a["file_id"] in affected_file_ids]
    code_snippets = [s for s in code_snippets if s["file_path"] in affected_paths]

    # 加载上一版本知识点，拆分保留/受影响
    prev_version = await self.version_dao.get_latest_completed(...)
    if prev_version and prev_version.version != self.version_tag:
        existing_kps = await kp_dao.list(..., version=prev_version.version)
        for existing_kp in existing_kps:
            kp_file_paths = {s.get("file_path") for s in (existing_kp.code_snippets or [])}
            if kp_file_paths & affected_paths:
                await kp_dao.delete(db, existing_kp.id)       # 受影响 → 删除
            else:
                await kp_dao.update(db, existing_kp.id, ...)  # 未受影响 → 保留
```

## 5. CI 验证

| 检查项 | 结果 |
|--------|------|
| ruff check | ✅ 0 errors |
| ruff format | ✅ 已格式化 |
| mypy | ✅ 0 issues (2 files) |
| pytest | ✅ 589 passed, 2 skipped |

## 6. 交付物清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `codeinsight/tasks/analysis_orchestrator.py` | 修改 | Step 5 新增增量 AI Agent 分支 |

## 7. 已知限制

1. **知识点无 file_id 外键**：知识点与文件的关联通过 `code_snippets` JSONB 字段的 `file_path` 间接实现，而非直接的 `file_id` 外键。这导致：
   - 需要额外构建 `file_path → file_id` 映射
   - 无法通过 DB 索引快速查询"某个文件关联的所有知识点"

2. **全量 VS 增量边界**：当变更文件比例超过 `incremental_max_change_ratio`（默认 30%）时，`IncrementalAnalyzer` 会降级为全量分析，此时增量 AI Agent 分支不会触发。

## 8. 后续建议

1. **短期**：在 `KnowledgePointModel` 中增加 `file_ids` JSONB 字段，直接存储关联的文件 UUID，避免通过 `code_snippets.file_path` 间接匹配。
2. **长期**：评估在 AI Agent 完全不需要运行时（如仅修改了注释/文档），跳过 AnalysisGraph 调用以节省成本。