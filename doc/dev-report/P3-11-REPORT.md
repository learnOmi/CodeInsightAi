# P3-11 报告：Prompt 回归测试框架

> 任务：Prompt 回归测试框架：自动化评估 Precision/Recall
> 优先级：P0 | 预估工时：12h | 模块：AI / Evaluation
> 日期：2026-07-20

---

## 1. 任务概述

P3-11 目标是在现有评估基础设施基础上，接入真实 Agent 分析管线，使评估框架能够运行真实 LLM 提取并计算真实 Precision/Recall/F1，同时建立 Prompt 版本基线管理，支持回归检测。

## 2. 实现内容

### 2.1 PromptRegistry（Prompt 版本注册表）

**新建文件**：`codeinsight/evaluation/prompt_registry.py`

核心功能：
- 扫描所有已知 Prompt 文件（7 个），计算 SHA256 哈希
- 生成全局版本标识（`v{base_version}-{combined_hash[:8]}`）
- 导出为字典供快照记录

关键类：
- `PromptEntry`：单个 Prompt 文件的注册信息（文件名、路径、哈希、大小）
- `PromptRegistry`：注册表，支持扫描、版本计算、导出

### 2.2 AgentBridge（Agent 桥接层）

**新建文件**：`codeinsight/evaluation/agent_bridge.py`

核心功能：
- 将评估测试用例（`TestCase`）转换为 `AnalysisGraph` 可执行的输入
- 执行真实 LLM 分析并返回标准化结果
- 支持 `max_cases` 限制，控制评估成本

关键类：
- `EvalAgentConfig`：评估 Agent 配置（LLM 客户端、最大用例数、verbose）
- `AgentBridge`：桥接器，核心方法：
  - `extract(test_case)`：对单个测试用例执行 LLM 分析
  - `extract_batch(test_cases)`：批量处理
  - `_build_ast_data()`：从代码片段构建简化 AST 数据

### 2.3 已有基础设施

P3-11 依赖的已有组件（无需修改）：

| 组件 | 文件 | 功能 |
|------|------|------|
| `EvalEngine` | `engine.py` | 评估引擎，支持 mock/agent 模式 |
| `KnowledgePointEvaluator` | `evaluator.py` | 知识点评估器，TP/FP/FN 计算 |
| `SemanticMatcher` | `matcher.py` | 语义匹配器（P3-04 Phase 4） |
| `LineMatchMatcher` | `matcher.py` | 代码行级 IoU 匹配器 |
| `SnapshotStore` | `history.py` | 快照管理，回归检测 |
| `SelfEvaluator` | `evaluator.py` | 自评估器（LLM 自评） |
| 评估数据集 | `data/*.json` | 6 语言 × 5 分类，120+ 测试用例 |
| CLI 入口 | `scripts/evaluate.py` | 评估脚本 |
| CI 工作流 | `.github/workflows/eval.yml` | 评估 CI |

## 3. 架构设计

### 3.1 评估流程

```
scripts/evaluate.py --agent
  └─> EvalEngine(agent_fn=AgentBridge.create())
        └─> AgentBridge
              └─> AnalysisGraph.run()
                    └─> _route_to_agents() 按 category 过滤
                          └─> 仅路由到匹配的 1 个 LLM 节点
              └─> KnowledgePointEvaluator(matcher=SemanticMatcher)
                    └─> MetricCalculator (Precision/Recall/F1)
        └─> SnapshotStore.save_snapshot() + detect_regressions()
```

### 3.2 AgentBridge 设计

```
TestCase (case_id, code_snippets, expected_points)
  └─> _build_ast_data() → AST 节点数据
  └─> create_initial_state() → AnalysisState
  └─> _compiled_graph.run() → FinalState
  └─> 标准化为 dict 格式
```

### 3.3 PromptRegistry 设计

```
PromptRegistry.scan()
  └─> 遍历 KNOWN_PROMPTS 文件列表
  └─> 计算每个文件的 SHA256 哈希
  └─> compute_version() → 组合哈希生成版本标识
```

## 4. 已知限制

### 4.1 Category 过滤（已修复）

**问题**：`AgentBridge.extract()` 每次调用都运行完整 `AnalysisGraph`（5 个 LLM 节点），不利用测试用例的 `category` 字段进行过滤。

**影响**：
- 每个测试用例执行 5 次 LLM 调用（而非按需 1 次）
- 成本增加 5 倍，耗时增加约 5 倍

**原因**：`AnalysisGraph._route_to_agents()` 无条件分发到全部 5 个节点。

**修复**（3 处修改）：

| 文件 | 变更 |
|------|------|
| `graph.py` | 新增 `CATEGORY_TO_NODE` 映射，`_route_to_agents()` 按 `current_category` 过滤 |
| `graph.py` | `create_initial_state()` 新增 `category` 参数 |
| `agent_bridge.py` | `extract()` 传入 `category=test_case.category` |

**效果**：评估时每个测试用例只运行 1 个相关 LLM 节点，成本降低约 80%。

### 4.2 简化 AST 数据

**问题**：`AgentBridge._build_ast_data()` 从代码片段生成简化 AST，不包含真实仓库的完整类/函数结构信息。

**影响**：LLM 分析时缺少上下文结构，可能影响提取质量。

**修复方案**（待后续版本）：
- 为评估数据集中的每个测试用例添加预计算的 AST 数据
- 在 `ExpectedPoint` 中添加 `ast_context` 字段

### 4.3 回归检测类型不匹配（已修复）

**问题**：`SnapshotStore.detect_regressions()` 返回 `list[dict[str, Any]]`，但 `EvalReport.regressions` 类型为 `list[Regression]`。`print_summary()` 以属性访问方式（`r.severity`）访问 dict，导致 `AttributeError`。

**影响**：CI 评估流程在保存快照后崩溃，无法完成回归检测。

**修复**：在 `evaluate.py` 中将 dict 结果转换为 `Regression` 对象后再赋值，保持类型一致。

**位置**：`scripts/evaluate.py`

## 5. 测试结果

### 5.1 新增测试

| 测试文件 | 测试数 | 覆盖内容 |
|---------|--------|---------|
| `tests/test_agent_bridge.py` | 12 | AgentBridge 配置、AST 构建、max_cases 限制、异常处理 |
| `tests/test_prompt_registry.py` | 13 | PromptEntry 哈希、PromptRegistry 扫描、版本计算、导出 |
| **合计** | **25** | |

### 5.2 CI 验证

| 检查项 | 结果 |
|--------|------|
| ruff check | ✅ 0 errors |
| ruff format | ✅ 已格式化 |
| mypy | ✅ 0 issues (3 files) |
| pytest（新增测试） | ✅ 25 passed |
| pytest（全量） | ✅ 589 passed, 2 skipped |

## 6. 审查发现与修复

| # | 严重性 | 位置 | 问题 | 修复 |
|---|--------|------|------|------|
| 1 | Critical | `__init__.py` L7 | 导入不存在的 `AgentMode` | 移除错误导入 |
| 2 | High | `agent_bridge.py` L126 | 每次新建 `AnalysisGraph` | 添加 `_compiled_graph` 缓存 |
| 3 | Medium | `graph.py` L40 | `_route_to_agents` 无条件分发全部 5 个节点 | 新增 `CATEGORY_TO_NODE` 映射按分类过滤 |
| 4 | Medium | `evaluate.py` L254 | `SnapshotStore` 返回 dict，`print_summary` 按属性访问 | 转换为 `Regression` 对象后赋值 |
| 5 | Low | `prompt_registry.py` L18 | 未使用的 `field` 导入 | 移除 |

## 7. 交付物清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `codeinsight/evaluation/prompt_registry.py` | 新建 | Prompt 版本注册表 |
| `codeinsight/evaluation/agent_bridge.py` | 新建 | Agent 桥接层 |
| `tests/test_prompt_registry.py` | 新建 | PromptRegistry 单元测试 |
| `tests/test_agent_bridge.py` | 新建 | AgentBridge 单元测试 |
| `codeinsight/evaluation/__init__.py` | 修改 | 导出新组件 |
| `codeinsight/agents/graph.py` | 修改 | 新增 `CATEGORY_TO_NODE` 映射 + category 过滤 |
| `scripts/evaluate.py` | 修改 | 回归结果类型转换 + `Regression` 导入 |

## 8. 后续建议

1. **中期**：为评估数据集添加预计算 AST 上下文，提高 LLM 提取质量
2. **长期**：在 CI 中启用 `--agent` 模式评估（需配置 API key 和 `--max-cases=1`）
