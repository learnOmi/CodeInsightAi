# P3-03 交付报告：多 Agent 并行编排 + 结果合并管道

## 概述

- **阶段**: P3 (AI 分析引擎)
- **任务**: P3-03 — 多 Agent 编排 + 结果合并管道
- **优先级**: P0
- **状态**: ✅ 已完成
- **交付日期**: 2026-07-19

## 完成度

| 模块 | 完成度 | 说明 |
|------|--------|------|
| **并行图结构** | 100% | 从线性串联改为 fan-out/fan-in 并行架构，使用 `Send` API 分发到 5 个 Agent 并行执行 |
| **MergeNode** | 100% | 结果合并节点：按 title 去重 + 按 confidence 降序排列 |
| **ExpansionNode** | 100% | 拓展内容生成节点：为每个知识点生成 principle/scenarios/practices/patterns/resources |
| **KnowledgePointExtraction expansion** | 100% | 新增 `expansion: ExpansionContent \| None` 字段 |
| **State 并行兼容** | 100% | 所有字段使用 `Annotated` reducer 支持并行 fan-out |
| **测试覆盖** | 100% | 38 个测试用例（新增 11 个），覆盖并行图/MergeNode/ExpansionNode/reducer |
| **全量 CI** | 100% | 87 个测试全部通过，ruff/mypy 零错误 |

## 架构变更

### 旧架构（线性串联 — P3-02）

```
entry → DesignPattern → Architecture → Algorithm → Engineering → DomainKnowledge → END
```

串行执行，耗时 = 5 × LLM 调用延迟。

### 新架构（并行 fan-out/fan-in — P3-03）

```
          ┌→ DesignPattern ─┐
          ├→ Architecture  ─┤
entry ────┼→ Algorithm     ─┼──→ MergeNode ─→ ExpansionNode ─→ END
          ├→ Engineering   ─┤
          └→ DomainKnowledge ┘
```

并行执行，耗时 ≈ 1 × LLM 调用延迟（理论加速比 5x）。

## 详细设计

### 1. 并行图结构 (`codeinsight/agents/graph.py`)

使用 LangGraph `Send` API 实现 fan-out：

```python
def _route_to_agents(state: AnalysisState) -> list[Send]:
    agent_names = ["design_pattern", "architecture", "algorithm", "engineering", "domain_knowledge"]
    return [Send(name, state) for name in agent_names]

# 入口 → 扇形分发
workflow.add_conditional_edges("__start__", _route_to_agents)

# 所有 Agent 汇聚到合并节点
for name, _ in ANALYSIS_NODES:
    workflow.add_edge(name, "merge")

# 合并 → 扩展 → 结束
workflow.add_conditional_edges("merge", _route_to_expansion)
workflow.add_edge("expansion", END)
```

### 2. State 并行兼容 (`codeinsight/agents/state.py`)

所有字段使用 `Annotated` reducer 以支持并行分支写入：

| 字段 | Reducer | 策略 |
|------|---------|------|
| `repo_id` | `_keep_first` | 保留第一个值 |
| `ast_data` | `_keep_first` | 保留第一个值 |
| `code_snippets` | `_keep_first` | 保留第一个值 |
| `knowledge_points` | `_accumulate_knowledge_points` | 按 title 去重追加 |
| `current_category` | `_keep_last` | 保留最后一个值 |
| `progress` | `_keep_last` | 保留最后一个值 |
| `error` | `_keep_last` | 保留最后一个错误 |
| `messages` | `_merge_messages` | 按 role+content 去重合并 |

### 3. MergeNode (`codeinsight/agents/node.py`)

```python
class MergeNode:
    async def execute(self, state) -> AnalysisState:
        kps = state.get("knowledge_points", [])
        # 1. 去重（按 title，保留置信度高的）
        seen: dict[str, dict] = {}
        for kp in kps:
            if kp.get("title", "") in seen:
                if kp.get("confidence", 0) > seen[title].get("confidence", 0):
                    seen[title] = kp
            else:
                seen[title] = kp
        # 2. 排序（按 confidence 降序）
        merged = sorted(seen.values(), key=lambda x: x.get("confidence", 0), reverse=True)
        state["knowledge_points"] = merged
        return state
```

### 4. ExpansionNode (`codeinsight/agents/node.py`)

为每个知识点调用 LLM 生成 5 类拓展内容：

| 字段 | 说明 |
|------|------|
| `principle` | 核心原理和技术本质（100-200 字） |
| `applicable_scenarios` | 适用场景列表（3-5 个） |
| `best_practices` | 最佳实践列表（3-5 条） |
| `related_patterns` | 关联技术/模式列表（3-5 个） |
| `learning_resources` | 学习资源推荐（3-5 个） |

空知识点列表时跳过 ExpansionNode，直接 END。

## 测试

### 测试覆盖（新增 11 个，总数 38 个）

| 测试类 | 数量 | 新增 |
|--------|------|------|
| TestAnalysisState | 9 | +5（reducer 函数测试） |
| TestKnowledgePointExtraction | 4 | - |
| TestAnalysisNode | 2 | - |
| TestDesignPatternNode | 3 | - |
| TestArchitectureNode | 1 | - |
| TestAlgorithmNode | 1 | - |
| TestEngineeringNode | 1 | - |
| TestDomainKnowledgeNode | 1 | - |
| TestAnalysisGraph | 4 | -（并行化适配） |
| **TestMergeNode** | **3** | **+3** |
| **TestExpansionNode** | **3** | **+3** |
| TestParseResponse | 4 | - |
| **合计** | **38** | **+11** |

### CI 结果

| 检查项 | 结果 |
|--------|------|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 6 files already formatted |
| mypy | ✅ Success: no issues found |
| pytest (agents) | ✅ 38 passed |
| pytest (全量) | ✅ **87 passed** |

## 变更文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `codeinsight/agents/graph.py` | **重写** | 线性 → 并行 fan-out/fan-in 架构 |
| `codeinsight/agents/state.py` | **重写** | 所有字段使用 `Annotated` reducer |
| `codeinsight/agents/node.py` | **修改** | 新增 `MergeNode`、`ExpansionNode`；修复 `import json` 位置 |
| `codeinsight/agents/__init__.py` | **修改** | 导出 `MergeNode`、`ExpansionNode` |
| `codeinsight/schemas/knowledge.py` | **修改** | `KnowledgePointExtraction` 增加 `expansion` 字段 |
| `tests/test_agents.py` | **修改** | 新增 11 个测试用例，适配并行图 |

## 设计决策

### 为什么用 `Send` 而不是 `add_conditional_edges` 分发？

`Send` 是 LangGraph 原生的并行分发 API，每个分支获得独立的状态拷贝，通过 `Annotated` reducer 自动合并。比手动路由更简洁、类型安全。

### 为什么所有字段都要 `Annotated`？

LangGraph 的 `Send` 在并行分支收敛时，会收集所有分支对每个字段的写入。非 `Annotated` 字段使用 `LastValue` 通道，只接受每个 step 一个值，并行分支写入多个值会触发 `InvalidUpdateError`。

### 为什么 ExpansionNode 单独调用 LLM 而非复用 Agent 模式？

ExpansionNode 的输入是 Agent 已提取的知识点，不是原始代码。它的 Prompt 格式完全不同（基于知识点 title/description 生成拓展，而非基于代码分析）。串行执行在 MergeNode 之后，不影响前 5 个 Agent 的并行加速。

## 修复记录

| 问题 | 位置 | 修复 |
|------|------|------|
| `import json` 在方法体内 | `node.py:512` | 已移到文件顶部（`import json` 已在第 10 行） |

## 后续任务（P3-04 起）

- **P3-04**: Prompt 工程 — 每个 Agent 的 System Prompt 调优 + 评估集
- **P3-06**: Embedding 向量化 — 代码片段 → 向量 → pgvector 存储
- **P3-08**: 拓展内容模板优化 — 更多 Few-shot 示例
- **P3-10**: 本地模型集成 — Ollama 简单任务路由
- **P3-11**: Prompt 回归测试框架