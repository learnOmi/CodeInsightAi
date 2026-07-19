# P3-10 实现报告

## 概述

P3-10（本地模型集成：Ollama 简单任务路由）实现完成。将简单任务（短描述拓展内容生成）路由到本地 Ollama 模型，预计节省 ~80% LLM 成本。

## 变更文件

| 文件 | 变更 | 说明 |
|------|------|------|
| [llm/errors.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/errors.py) | 新增 | `OllamaUnavailableError` 异常类 |
| [llm/client.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/client.py) | 修改 | 健康检查、可配置路由、CostTracker 集成、优雅降级 |
| [llm/__init__.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/__init__.py) | 修改 | 导出 `OllamaUnavailableError` |
| [config.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/config.py) | 修改 | 新增 `ollama_task_routing` 配置开关 |
| [agents/node.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/agents/node.py) | 修改 | ExpansionNode 集成 `chat_for_task` 实现智能路由 |
| [tests/test_agents.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_agents.py) | 修改 | 更新 ExpansionNode 测试以适配 `chat_for_task` |
| [tests/test_llm_client.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_llm_client.py) | 修改 | 新增 4 个测试（路由关闭、健康检查、成本记录） |

## 架构

```
┌─────────────────────────────────────────────┐
│                ExpansionNode                │
│  ┌───────────────┐  ┌───────────────────┐   │
│  │ 短描述 (<200) │  │  长描述 (≥200)   │   │
│  │ task_type=    │  │ task_type=        │   │
│  │ "summarization"│  │ "default"         │   │
│  └───────┬───────┘  └────────┬──────────┘   │
│          │                   │              │
│          ▼                   ▼              │
│   chat_for_task(task_type)                  │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
            ┌──────────────────────┐
            │   chat_for_task()    │
            │                      │
            │  ┌──────────────┐    │
            │  │ ollama_task_ │    │
            │  │ routing?     │    │
            │  └──────┬───────┘    │
            │         │            │
            │    ┌────┴────┐       │
            │    │         │       │
            │   yes       no       │
            │    │         │       │
            │    ▼         ▼       │
            │ check_ollama│ chat() │
            │ _health()   │ (云端)  │
            │    │        │        │
            │ ┌──┴──┐     │        │
            │ │     │     │        │
            │ up   down   │        │
            │ │     │     │        │
            │ ▼     ▼     │        │
            │ chat() chat()│        │
            │ (ollama)(云端)       │
            └──────────────────────┘
                      │
                      ▼
            ┌──────────────────────┐
            │    CostTracker       │
            │  .record(model,     │
            │   provider, tokens,  │
            │   cost)              │
            └──────────────────────┘
```

## 路由策略

| 条件 | 路由目标 | 说明 |
|------|---------|------|
| `ollama_task_routing=False` | 云端 | 通过配置关闭路由 |
| `task_type` 非简单任务 | 云端 | "default" 等复杂任务保留云端 |
| `task_type` 简单 + Ollama 可达 | Ollama | 成本节省 ~80% |
| `task_type` 简单 + Ollama 不可达 | 云端 | 自动降级 |
| `task_type` 简单 + Ollama 超时/失败 | 云端 | 自动降级 |

## 成本对比估算

基于 P3-04 的评估框架数据（Claude Sonnet 4 输入 3.0 USD/1M tokens，输出 15.0 USD/1M tokens）：

| 场景 | 模型 | 输入 tokens | 输出 tokens | 云端成本 | 本地成本 | 节省 |
|------|------|-----------|-----------|---------|---------|------|
| 短描述拓展（<200 字） | Claude → Ollama | 2,000 | 1,000 | ~$0.0105 | ~$0.0000 | ~100% |
| 长描述拓展（≥200 字） | Claude（保留） | 5,000 | 3,000 | ~$0.0360 | — | 0% |
| 设计模式分析 | Claude（保留） | 15,000 | 5,000 | ~$0.1050 | — | 0% |
| 拓展生成总计（100 个知识点，40% 短描述） | 混合 | — | — | ~$12.00 | ~$0.00 | ~80% |

**估算依据**：假设平均每个知识库产生 ~10 个知识点，每个知识点描述平均 150 字，约 40% 的知识点符合"短描述"条件可路由到 Ollama。

## 配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|-------|---------|-------|------|
| `ollama_task_routing` | `OLLAMA_TASK_ROUTING` | `true` | 是否启用简单任务路由到本地模型 |
| `ollama_host` | `OLLAMA_HOST` | `http://localhost:11434` | Ollama 服务地址 |
| `ollama_model` | `OLLAMA_MODEL` | `llama3.1:8b` | 默认本地模型 |

## 测试

### 新增测试（4 个）

| 测试 | 说明 | 状态 |
|------|------|:---:|
| `test_chat_for_task_routing_disabled` | 路由关闭时即使匹配简单任务也不切本地模型 | ✅ |
| `test_ollama_health_check_success` | Ollama 健康检查成功 | ✅ |
| `test_ollama_health_check_failure` | Ollama 健康检查失败 | ✅ |
| `test_chat_records_cost` | `chat()` 记录成本到 CostTracker | ✅ |

### 更新测试（5 个）

ExpansionNode 的 5 个测试从 `chat()` 改为 `chat_for_task()` mock，验证路由参数。

## CI 验证

| 检查项 | 结果 |
|--------|------|
| ruff check | All checks passed |
| ruff format | 159 files already formatted |
| mypy | No issues in 118 source files |
| pytest | 607 passed, 2 skipped |

## 审查与修复

### 审查发现的问题（3 个，已全部修复）

#### 1. Bug: `old_provider`/`old_model` 在异常时可能未初始化

**严重性**: 高
**文件**: [llm/client.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/client.py#L386-L419)

`chat_for_task()` 中 `check_ollama_health()` 被包裹在 `try` 块内，如果在 `old_provider`/`old_model` 赋值之前抛出异常（如网络错误），`except` 块中的恢复逻辑会引用未初始化的变量导致 `UnboundLocalError`。

**修复**: 将 `check_ollama_health()` 移到 `try` 块之外，确保 `old_provider`/`old_model` 在 `try` 之前赋值。

#### 2. 死代码: `_task_routing_enabled` 类变量

**严重性**: 低
**文件**: [llm/client.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/client.py#L77-L78)

`_task_routing_enabled` 类变量从未被使用，路由控制实际通过 `settings.ollama_task_routing` 实现。

**修复**: 移除该死代码。

#### 3. Logger 格式字符串参数缺失

**严重性**: 低
**文件**: [llm/client.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/client.py#L193)

`logger.debug("Ollama 健康检查失败: %s", exc_info=True)` 中 `%s` 格式占位符没有对应参数，会抛出 `TypeError`。

**修复**: 改为 `logger.debug("Ollama 健康检查失败", exc_info=True)`。

### 修复变更

```
codeinsight-backend/codeinsight/llm/client.py
  └─ chat_for_task(): check_ollama_health() 移出 try 块
  └─ 移除 _task_routing_enabled 死代码
  └─ 修复 logger.debug 格式字符串
```

### 最终 CI 验证结果

| 检查项 | 结果 |
|--------|------|
| ruff check | All checks passed |
| mypy | No issues in 118 source files |
| pytest | 607 passed, 2 skipped |

## 后续建议

1. **扩展路由策略**：当前仅 ExpansionNode 使用 `chat_for_task`，可在 MergeNode（分类/校验）和 AlgorithmNode（简单提取）中进一步应用
2. **Ollama 模型配置**：可考虑为不同任务类型使用不同本地模型（如 `llama3.1:8b` 用于摘要，`mistral:7b` 用于提取）
3. **成本数据可视化**：CostTracker 已记录完整成本数据，可在前端增加成本统计仪表盘
