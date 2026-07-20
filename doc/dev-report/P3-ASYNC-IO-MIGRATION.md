# P3 同步 IO 迁移至 Async 修复报告

> **修复日期**：2026-07-20
> **触发问题**：MeiliSearch 同步 SDK 和 Redis 同步客户端在 async 事件循环中阻塞
> **涉及文件**：6 个

---

## 1. 问题背景

P3 综合审查发现两个阻塞事件循环的根因：

| 组件 | 原实现 | 阻塞场景 |
|------|--------|----------|
| `MeiliSearchClient` | `meilisearch` 同步 SDK（基于 `requests`） | `api/search.py` / `api/analysis.py` / `orchestrator.py` 的 async 端点直接调同步 HTTP |
| `Redis` 客户端 | `redis.Redis`（同步） | `api/analysis.py` 的 async 端点直接调同步 Redis |

**修复目标**：所有 FastAPI async 端点不再阻塞事件循环。

---

## 2. 修复方案

### 方案选择

考虑过 `asyncio.to_thread()` 包装，但发现三个问题：
- 单例的懒初始化竞态（property 内部无锁）
- GIL 限制下 HTTP 调用并发瓶颈
- 无法优雅取消（超时后线程仍在执行）

**最终选择**：迁移到原生 async 客户端。

| 组件 | 替换为 | 理由 |
|------|--------|------|
| `meilisearch` SDK | `httpx.AsyncClient` 直接调 REST API | Meilisearch 是纯 REST API，SDK 只是薄封装 |
| `redis.Redis` | `redis.asyncio.Redis` | redis-py 自带异步客户端 |

---

## 3. 修改文件清单

### 3.1 核心客户端

#### `services/meilisearch_client.py` — 重写

| 变更 | 说明 |
|------|------|
| 移除 `import meilisearch` | 不再依赖同步 SDK |
| 新增 `import httpx` | 使用 `httpx.AsyncClient` |
| 单例模式改为 `asyncio.Lock` 保护 | 修复 S-B1（原 `threading.Lock`） |
| 新增 `MeiliSearchClient.create()` | 异步安全的单例获取方法 |
| 所有方法改为 `async def` | `ensure_index()`, `add_document()`, `add_documents()`, `delete_document()`, `search()` |
| 所有 HTTP 调用改为 `await self.client.*` | 不再阻塞事件循环 |

#### `db/redis_client.py` — 扩展

| 变更 | 说明 |
|------|------|
| 保留 `get_redis_client()`（同步） | 供 Celery 任务继续使用 |
| 保留 `get_redis_pool()`（同步） | 供 Celery 任务继续使用 |
| 新增 `get_async_redis_pool()` | 异步连接池，`asyncio.Lock` 保护初始化 |
| 新增 `get_async_redis_client()` | 异步 Redis 客户端 |
| 新增 `close_async_redis_pool()` | 异步关闭连接池 |

### 3.2 调用方适配

#### `tasks/analysis_orchestrator.py`

| 变更 | 说明 |
|------|------|
| `CancelChecker.check()` 改为 `async` | 使用 `get_async_redis_client()` |
| `self.cancel_checker.check()` → `await self.cancel_checker.check()` | 所有调用点加 await |
| `MeiliSearchClient()` → `await MeiliSearchClient.create()` | 单例获取改异步 |
| `meili_client.add_documents()` → `await meili_client.add_documents()` | 调用改异步 |
| `_cleanup_redis_task_key()` 保持同步 | 在 `run()` 同步异常路径中被调用，改为局部 import 同步 Redis |

#### `api/analysis.py`

| 变更 | 说明 |
|------|------|
| `_lookup_repository()` → `async` | 使用 `get_async_redis_client()` |
| `_lookup_task_mode()` → `async` | 使用 `get_async_redis_client()` |
| `_celery_result_to_task()` → `async` | 使用 `get_async_redis_client()` |
| `_trigger_analysis()` 中的 Redis 调用 | 全部改为 `await` |
| `submit_analysis` 端点 | 调用 `await _trigger_analysis()` |
| `get_task_status` 端点 | 调用 `await _lookup_repository()` / `await _lookup_task_mode()` |
| `cancel_task` 端点 | Redis 调用全部改为 `await` |

#### `api/search.py`

| 变更 | 说明 |
|------|------|
| `search_knowledge_points()` | `MeiliSearchClient()` → `await MeiliSearchClient.create()` |
| `client.search()` → `await client.search()` | 调用改异步 |

#### `repositories/knowledge_point.py`

| 变更 | 说明 |
|------|------|
| `update()` 方法 | `MeiliSearchClient()` → `await MeiliSearchClient.create()` |
| `update()` 方法 | `meili_client.add_document()` → `await meili_client.add_document()` |
| `delete()` 方法 | `MeiliSearchClient()` → `await MeiliSearchClient.create()` |
| `delete()` 方法 | `meili_client.delete_document()` → `await meili_client.delete_document()` |

#### `main.py`

| 变更 | 说明 |
|------|------|
| `lifespan()` 启动初始化 | `MeiliSearchClient()` → `await MeiliSearchClient.create()` |
| `lifespan()` 启动初始化 | `meili_client.ensure_index()` → `await meili_client.ensure_index()` |
| `health_check()` 端点 | `get_redis_client()` → `get_async_redis_client()` |
| `health_check()` 端点 | `redis_client.ping()` → `await redis_client.ping()` |

### 3.3 未修改文件

| 文件 | 理由 |
|------|------|
| `tasks/analysis_tasks.py` | Celery 任务在同步线程中执行，`get_redis_client()` 正确 |

---

## 4. 架构对比

### 修复前

```
FastAPI async 端点
  ├─ MeiliSearchClient()         ← 同步 SDK，阻塞事件循环
  ├─ get_redis_client()          ← 同步 Redis，阻塞事件循环
  └─ LLMClient.chat()            ← litellm.acompletion() ✅ 已异步
```

### 修复后

```
FastAPI async 端点
  ├─ await MeiliSearchClient.create()    ← httpx.AsyncClient ✅
  ├─ await get_async_redis_client()      ← redis.asyncio.Redis ✅
  └─ LLMClient.chat()                    ← litellm.acompletion() ✅ 已异步

Celery 同步 Worker
  └─ get_redis_client()                  ← redis.Redis ✅ 同步环境正确
```

---

## 5. 风险与注意事项

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| `meilisearch` SDK 导入残留 | 部分测试或旧代码可能仍在 import | 已 grep 确认无残留 |
| Celery Worker 配置 | `--pool=threads` 模式下 orchestrator 用 `run_until_complete()` 会破坏事件循环 | orchestrator 已用同步 Redis（`_cleanup_redis_task_key`），其他部分用 async |
| `decode_responses=True` 在 asyncio | redis.asyncio 的返回类型是 `str`（decode_responses 有效），与同步一致 | 已在 `_celery_result_to_task` 中增加 bytes 类型判断 |

---

## 6. 验证结果

- 所有 7 个修改文件的 Python 语法检查通过（`py_compile`）
- grep 确认无 `MeiliSearchClient()` 同步构造调用残留
- grep 确认无 `get_redis_client()` 在 async 端点的残留调用
