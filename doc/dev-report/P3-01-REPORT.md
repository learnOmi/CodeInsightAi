# P3-01: LLM 客户端封装 — LiteLLM 统一接口

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P3-01 |
| 任务名称 | LLM 客户端封装：统一接口（LiteLLM 路由） |
| 所属阶段 | Phase 3（第 7-9 周） |
| 优先级 | P0 |
| 预估工时 | 8h |
| 实际工时 | 6h |
| 交付物 | `LLMClient` 抽象 + `LLMConfig` 配置 + `CostTracker` 成本追踪 + 单元测试 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-04 `Settings` 配置管理 | ✅ | `llm_provider`/`llm_model`/`llm_api_key` 等字段已存在 |
| P2-08 分析管线骨架 | ✅ | `run_analysis` 任务中已预留 LLM 调用点 |
| `litellm` 依赖 | ✅ | `pyproject.toml` 已声明 |

---

## 二、整体架构位置

P3-01 在 CodeInsight LLM 调用栈中的位置：

```

                                  ┌──────────────┐
                                  │   Agent 节点  │
                                  │ (node.py)     │
                                  └──────┬───────┘
                                         │ chat() / chat_for_task()
                                         ▼
                          ┌──────────────────────────┐
                          │      LLMClient           │
                          │  统一封装抽象层           │
                          │                          │
                          │  chat()       非流式对话  │
                          │  chat_stream()  流式响应  │
                          │  chat_with_fallback()     │
                          │  chat_for_task() 智能路由  │
                          │  embed() 嵌入生成         │
                          │  count_tokens() 计数      │
                          └──────┬───────────────────┘
                                 │ litellm.acompletion()
                                 ▼
                    ┌─────────────────────────────┐
                    │     LiteLLM 路由层           │
                    │                             │
                    │  claude-3.5-sonnet  gpt-4o   │
                    │  ollama/llama3.1:8b  ...     │
                    └─────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
              Anthropic API              OpenAI API
                                         Ollama API

```

### 数据流向

```
调用方 (Agent/Controller)
    │
    │ LLMClient.chat(messages)
    ▼
┌───────────────────────────────────┐
│  LLMClient                        │
│                                   │
│  1. LLMConfig → 加载配置          │
│     (provider, model, api_key)    │
│                                   │
│  2. _get_api_kwargs() → 构建参数  │
│     (model, temperature, timeout) │
│                                   │
│  3. litellm.acompletion() → 调用  │
│                                   │
│  4. 解析 response → content       │
│     + 计算 cost (MODEL_COST_MAP)  │
│                                   │
│  5. 返回 result dict              │
│     {content, prompt_tokens,      │
│      completion_tokens, cost}     │
└───────────────────────────────────┘
    │
    ▼
调用方接收结果
```

---

## 三、实现模块结构

```
codeinsight/llm/
├── __init__.py              # 统一包导出
├── client.py                # LLMClient + LLMConfig（核心）
├── errors.py                # LLMError 自定义异常
└── cost.py                  # CostTracker 成本追踪器

codeinsight/embedding/
└── client.py                # EmbeddingClient（委托给 LLMClient）

codeinsight/agents/
├── node.py                  # 5 个分析 Agent 节点（已集成 LLMClient）
└── graph.py                 # 分析图编排（已集成 LLMClient）

tests/
└── test_llm_client.py       # 32 个单元测试用例
```

---

## 四、核心类设计

### 4.1 LLMConfig — 统一配置

| 字段 | 类型 | 默认值来源 | 说明 |
|------|------|-----------|------|
| `provider` | `Literal["claude", "gpt", "ollama"]` | `settings.llm_provider` | 提供商选择 |
| `model` | `str` | `settings.llm_model` | 模型名称 |
| `api_key` | `str \| None` | `settings.llm_api_key` | API 密钥 |
| `ollama_base_url` | `str` | `settings.ollama_host` | Ollama 服务地址 |
| `temperature` | `float` | `settings.llm_temperature` | 生成温度 |
| `max_tokens` | `int` | `4096` | 最大输出 Token 数 |
| `embedding_model` | `str` | `"text-embedding-3-small"` | 嵌入模型 |
| `num_retries` | `int` | `3` | 重试次数 |
| `request_timeout` | `float` | `settings.llm_timeout` | 请求超时 |
| `embedding_timeout` | `float` | `60.0` | 嵌入超时 |

**设计要点**：所有配置字段均从全局 `Settings` 单例读取默认值，避免 P2-08 阶段遗留的"独立 `.env` 文件"配置源漂移问题。调用方可以传入自定义 `LLMConfig` 覆盖默认值。

### 4.2 LLMClient — 统一 LLM 客户端

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `chat(messages, response_model)` | `dict \| BaseModel` | 非流式对话，可选结构化解析 |
| `chat_stream(messages)` | `AsyncIterator[str]` | 流式响应 |
| `chat_with_fallback(messages, fallback_providers)` | `dict` | Provider 降级（主失败→备用） |
| `chat_for_task(messages, task_type)` | `dict` | 简单任务路由到本地模型 |
| `embed(texts)` | `list[list[float]]` | 批量文本嵌入 |
| `count_tokens(messages)` | `int` | 对话消息 Token 计数 |

#### 内部方法

| 方法 | 说明 |
|------|------|
| `_resolve_model_name()` | 按 provider+model 解析 litellm 兼容标识符 |
| `_get_model_key()` | 返回用于成本查询的 model key（去 `ollama/` 前缀） |
| `_get_api_kwargs(timeout)` | 构建 litellm 调用参数（api_key, api_base 等） |
| `_estimate_tokens(text)` | 委托 litellm 计数，失败回退 `len//4` |
| `_get_cost_per_token(model_key)` | 从 `MODEL_COST_MAP` 查询单价 |

#### MODEL_COST_MAP（成本单价，USD/1M tokens）

| 模型 | 输入成本 | 输出成本 |
|------|---------|---------|
| `claude-3.5-sonnet-20241022` | $3.0 | $15.0 |
| `claude-sonnet-4-20250514` | $3.0 | $15.0 |
| `gpt-4o` | $2.5 | $10.0 |
| `text-embedding-3-small` | $0.02 | $0.0 |

#### SIMPLE_TASK_MODELS（简单任务降级映射）

| 任务类型 | 本地模型 |
|---------|---------|
| `classification` | `ollama/llama3.1:8b` |
| `summarization` | `ollama/llama3.1:8b` |
| `extraction` | `ollama/mistral:7b` |

### 4.3 CostTracker — 成本追踪器

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `record(model, provider, prompt_tokens, completion_tokens, cost)` | `None` | 记录单次调用成本 |
| `get_daily_cost(days)` | `float` | 按天数汇总成本 |
| `get_cost_by_model(days)` | `dict[str, float]` | 按模型分组 |
| `get_cost_by_task(days)` | `dict[str, float]` | 按任务类型分组 |
| `get_total_stats()` | `dict` | 总统计（记录数、总 Token、总成本） |
| `clear()` | `None` | 清空记录 |

提供全局单例 `get_cost_tracker()`，支持 `max_records=10000` 上限以避免内存泄漏。

### 4.4 EmbeddingClient — Embedding 客户端

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `embed(texts)` | `list[list[float]]` | 批量嵌入（委托 LLMClient.embed()） |
| `embed_single(text)` | `list[float]` | 单条嵌入 |

**消除重复**：P2-08 阶段 EmbeddingClient 有独立的 litellm 调用逻辑，与 LLMClient.embed() 重复。本轮将 EmbeddingClient 改为委托给 LLMClient，消除代码重复。

---

## 五、测试覆盖

### test_llm_client.py（32 个测试用例）

| 测试类 | 用例数 | 覆盖内容 |
|--------|--------|---------|
| `TestLLMClientInit` | 6 | 各类 provider 初始化、默认值、模型名解析 |
| `TestLLMClientConfig` | 4 | API 参数构建、Ollama 特殊参数、model key 解析 |
| `TestLLMClientChat` | 3 | 基本对话、结构化解析、错误处理 |
| `TestLLMClientStream` | 2 | 流式对话、流式错误处理 |
| `TestLLMClientFallback` | 2 | Provider 降级成功、全部失败 |
| `TestLLMClientTaskRouting` | 1 | 默认任务路由 |
| `TestLLMClientEmbed` | 2 | 批量嵌入、嵌入错误处理 |
| `TestLLMClientTokens` | 2 | Token 计数、空文本计数 |
| `TestCostTracker` | 7 | 日成本、按模型/任务分组、总统计、上限、清空、单例 |
| `TestEmbeddingClient` | 3 | 批量嵌入、单条嵌入、空嵌入异常 |

**测试策略**：使用 `unittest.mock.patch` 模拟 `litellm.acompletion` 和 `litellm.aembedding`，不发起真实 API 请求。

---

## 六、与现有代码的集成

### 6.1 向后兼容

| 模块 | 原有引入路径 | 兼容性 |
|------|-------------|--------|
| `codeinsight/agents/node.py` | `from codeinsight.llm.client import LLMClient` | ✅ 兼容 |
| `codeinsight/agents/graph.py` | `from codeinsight.llm.client import LLMClient` | ✅ 兼容 |
| `codeinsight/embedding/client.py` | `from codeinsight.embedding.client import EmbeddingClient` | ✅ 委托重构，接口不变 |
| `codeinsight/config.py` | 全局 `Settings` | ✅ LLMConfig 从中读取默认值 |

### 6.2 包导出

```python
# codeinsight/llm/__init__.py
from codeinsight.llm.client import LLMClient, LLMConfig
from codeinsight.llm.errors import LLMError
from codeinsight.llm.cost import CostTracker
__all__ = ["LLMClient", "LLMConfig", "LLMError", "CostTracker"]
```

---

## 七、验证结果

| 检查项 | 结果 |
|--------|------|
| `pytest tests/test_llm_client.py -v` | ✅ **32 passed** in 3.09s |
| `ruff check codeinsight/llm/` | ✅ All checks passed |
| `ruff format --check codeinsight/llm/` | ✅ 5 files already formatted |
| `mypy codeinsight/llm/` | ✅ Success: no issues found in 4 source files |
| `pytest tests/` (全量) | ✅ **348 passed** (76 parser 测试因 tree-sitter 原生模块缺失跳过，非本任务问题) |

---

## 八、设计决策

| 决策 | 方案 | 说明 |
|------|------|------|
| 配置源 | 从全局 `Settings` 读取 | 消除 P2-08 阶段独立 `.env` 文件的配置漂移 |
| Provider 降级 | 主 provider 失败后遍历 `fallback_providers` | 提高可用性，本地+云端双保险 |
| 简单任务路由 | `SIMPLE_TASK_MODELS` 映射表 | 分类/摘要等切到本地 Ollama 节省成本 |
| 成本计算 | `MODEL_COST_MAP` 硬编码单价 | 无需外部 API 调用，结果精确至 0.1 美分 |
| 成本追踪 | 内存中 `CostTracker` 环形缓冲 | 轻量实现，max_records=10000 防 OOM |
| Embedding 去重 | `EmbeddingClient` 委托 `LLMClient.embed()` | 消除 litellm 调用重复 |
| 测试策略 | `unittest.mock.patch` 模拟 litellm | 零真实 API 成本，测试运行 <4s |
| 异常体系 | `LLMError` 携带 provider+model 上下文 | 便于定位故障来源 |

---

## 九、常见问题排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| `LLMError: LLM chat failed` | API 密钥无效 / 网络不通 | 检查 `settings.llm_api_key` 和网络连接 |
| Provider 全部降级失败 | 所有备用 provider 均不可用 | 检查各 provider 的 API 密钥和端点 |
| Ollama 调用超时 | Ollama 服务未启动 / 模型未拉取 | `ollama pull llama3.1:8b` 拉取模型 |
| Token 计数不准确 | 非英文文本回退 `len//4` | 确保安装 `tiktoken` 库 |
| 成本为 0 | 模型不在 `MODEL_COST_MAP` 中 | 添加对应模型的成本条目 |

---

## 十、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| LangGraph 工作流 | P3-02 | 使用 LLMClient 构建第一个分析 Agent |
| 多 Agent 编排 | P3-03 | 在 AnalysisGraph 中集成 5 个 Agent |
| Prompt 工程 | P3-04 | 优化 System Prompt + Few-shot 示例 |
| 成本查询 API | P3-05 | 为 CostTracker 添加 REST 接口 |
| Token 使用优化 | P3-06 | 实现 Token 预算控制、上下文窗口管理 |