# CodeInsight AI 开发报告 — LLM 调用稳定性与数据库事务修复

> **日期**: 2026-07-26
> **版本**: v1.0
> **相关文档**: [KNOWLEDGE-ANALYSIS-OPTIMIZATION.md](../dev-analysis/KNOWLEDGE-ANALYSIS-OPTIMIZATION.md)

---

## 一、本次修复概述

本次修复解决了代码库中暴露的三个关键缺陷：数据库二次提交冲突、LLM 双重重试叠加、并发限流重试风暴。这些问题均属于文档第 7 章（LLM 调用成本与速率控制）和基础设施稳定性范畴，修复后系统可正常处理仓库创建和知识分析流程。

---

## 二、缺陷分析与修复

### 2.1 数据库二次提交冲突（Double Commit）

**现象**：

创建仓库后 `get_db_session` 抛出 `sqlalchemy.exc.PendingRollbackError`，错误堆栈指向 `session.py:36` 的 `await session.commit()`。

**根因**：

`create_repository` 在 [repositories.py:72](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/repositories.py#L72) 手动调用 `await db.commit()`，确保分析任务能查到仓库记录。随后 `get_db_session` 退出时再次调用 `await session.commit()`，导致 **二次提交** 异常。

```python
# 旧代码 — get_db_session()
async with async_session_factory() as session:
    try:
        yield session
        await session.commit()  # 二次提交，与路由内 commit 冲突
    except Exception:
        await session.rollback()
        raise
```

**修复**：改用 `session.begin()` 上下文管理器。

```python
# 新代码
async with async_session_factory() as session:
    async with session.begin():
        yield session
```

`session.begin()` 的优势：路由内已 `commit()` 时，上下文退出时提交的是新开始的空事务（无操作），不会报错。

---

### 2.2 LLM 双重重试叠加（Double Retry）

**现象**：

日志显示同一秒内出现多条"第 2 次重试"、"第 3 次重试"，且每次重试都等待 2s→4s→8s，感觉像无限重试。

**根因**：

存在 **两层独立重试机制** 叠加：

| 层 | 位置 | 重试次数 | 单次退避 |
|---|---|---|---|
| litellm 内部 | `_get_api_kwargs` 传入 `num_retries=3` | 3 次 | 2s→4s→8s |
| `_acompletion_with_retry` | 外层循环 | 3 次 | 2s→4s→8s |

每次外层循环实际消耗 litellm 内部 3 次重试（14s），外层最多 3 轮 = 42s+。

**修复**：将 `_get_api_kwargs` 中的 `num_retries` 设为 `0`，关闭 litellm 内部重试。

```python
# 旧代码
kwargs = {
    "num_retries": self.config.num_retries,  # 3，litellm 内部重试
}

# 新代码
kwargs = {
    "num_retries": 0,  # 关闭 litellm 内部重试，由上层 _acompletion_with_retry 统一管控
}
```

---

### 2.3 并发限流重试风暴（Rate Limit Storm）

**现象**：

日志同一秒出现多条"第 2 次重试等待 4s"，多条"第 3 次重试等待 8s"。

**根因**：

Orchestrator 并发发起 N 个文件分析请求，全部被限流，**每个请求独立重试**。每个请求各自执行 2s→4s→8s 退避，叠加后感觉像无限重试。

**修复**：在 `LLMClient` 中加入**全局限流退避计数器**，所有并发调用共享等待时间。

```python
# LLMClient.__init__ 新增
self._rate_limit_hits: int = 0      # 全局限流计数器
self._rate_limit_lock = asyncio.Lock()  # 保护计数器

# _acompletion_with_retry 中的退避逻辑
# 任意调用触发限流 → 计数器 +1，所有并发调用统一等待 min(2^hits, 60s)
# 调用成功 → 计数器 -1
# 退避时间上限 60s，匹配免费用户限流窗口
```

同时清理了 `node.py`（`ExpansionNode`）中的冗余独立限流逻辑，改为依赖 `LLMClient` 的统一退避机制。

---

## 三、涉及文件

| 文件 | 修改内容 | 对应文档章节 |
|------|----------|--------------|
| [session.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/db/session.py) | `get_db_session` 改用 `session.begin()` 管理事务 | 基础设施稳定性 |
| [client.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/client.py#L172) | 关闭 litellm 内部重试（`num_retries=0`） | 第 7 章 |
| [client.py:110](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/client.py#L110) | 新增全局限流退避计数器 | 第 7 章 |
| [client.py:221](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/llm/client.py#L221) | `_acompletion_with_retry` 增加 `InternalServerError` 重试 | 第 7 章 |
| [node.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/agents/node.py) | 移除 `ExpansionNode` 冗余限流逻辑 | 第 7 章 |

---

## 四、与优化方案的对照

| 文档章节 | 修复覆盖 | 说明 |
|----------|----------|------|
| 第 7 章：LLM 调用成本与速率控制 | **已实现核心内容** | 全局限流退避、统一重试管控、Provider 降级（`InternalServerError` 重试） |
| 第 3 章：仓库创建后自动分析流程优化 | **间接修复** | 数据库二次提交修复后，`create_repository` 可正常触发分析并返回 task_id |
| 附录：系统架构中的"限流"环节 | **已优化** | 从分散的独立退避 → LLMClient 集中式全局限流管控 |

---

## 五、尚未解决的问题（待后续实施）

以下问题来自优化文档，本次未涉及：

| 优先级 | 问题 | 文档章节 |
|--------|------|----------|
| P0 | 前端 SSE 集成 — 创建仓库后未自动连接 SSE 监听进度 | 第 9 章 |
| P1 | 上下文增强 — `MAX_CODE_SNIPPETS=20` 和 `MAX_CODE_CHARS_PER_SNIPPET=1000` 瓶颈 | 第 1 章 |
| P1 | 新增 TT/TK 分类 | 第 4、5 章 |
| P1 | Prompt 模板质量提升（Few-shot + 负向约束） | 第 8 章 |
| P2 | 增量分析知识点保留策略优化 | 第 6 章 |
| P2 | LLM 成本预算控制（CostBudget 类） | 第 7 章 |

---

## 六、测试验证

1. **数据库事务**：创建仓库（勾选自动分析）应正常返回 201 + task_id，不抛 `PendingRollbackError`
2. **LLM 限流**：并发发起多个文件分析请求时，限流日志应显示"全局限流计数器=N"，所有请求统一退避，而非各自独立重试
3. **内部错误恢复**：Provider 返回 500 时，应自动重试而非直接失败
