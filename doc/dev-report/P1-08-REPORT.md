# P1-08: Celery + Redis 异步任务框架搭建 - 开发报告

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P1-08 |
| 任务名称 | Celery + Redis 异步任务框架搭建 |
| 所属阶段 | Phase 1（第 2-3 周） |
| 优先级 | P0 |
| 预估工时 | 6h |
| 交付物 | 任务提交/查询/取消 API |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-05 SQLAlchemy ORM 模型 | ✅ | AnalysisVersionModel 已定义 |
| P1-07 Repository DAO | ✅ | RepositoryDAO.get_by_id 已实现 |
| P1-07 AnalysisVersion DAO | ✅ | AnalysisVersionDAO.create/update 已实现 |
| P1-03 Pydantic Schema | ✅ | AnalysisTask/AnalyzeRequest/TaskStatus/AnalysisProgress 已定义 |
| docker-compose.yml | ✅ | celery-worker 服务已定义 |
| pyproject.toml | ✅ | celery[redis] 依赖已声明 |

---

## 二、修复 API/Schemas/Models 对齐问题

在实施 P1-08 之前，`api/analysis.py` 中三个端点均为 `raise NotImplementedError("P1-08: ...")` 占位，需要替换为真实实现。

### 2.1 修复清单

| 模块 | 问题 | 修复方式 |
|------|------|---------|
| api/analysis | 3 个端点全是 NotImplementedError | 替换为真实实现 |
| config.py | 缺少 Celery 配置项 | 新增 `celery_task_always_eager` |
| pyproject.toml | ✅ | redis 包未显式声明 | 补充 `redis>=5.2.0` 依赖 |

### 2.3 修复 SQLAlchemy ORM 模型类型推断问题（mypy 12 errors → 0）

**根因**：旧式 `Column` 声明风格导致 mypy 将属性类型推断为 `Column[str]` 而非 `str`，不得不使用 `cast()` 和 `# type: ignore` 绕过。

**解决方案**：将 4 个 ORM 模型从 `Column` 风格迁移到 SQLAlchemy 2.0 `Mapped` + `mapped_column` 声明式风格，配合 SQLAlchemy 内置 mypy 插件实现正确的静态类型推断。

#### 修改清单

| 文件 | 改动 |
|------|------|
| [models/repository.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/repository.py) | `Column(...)` → `Mapped[T] = mapped_column(...)` |
| [models/analysis_version.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/analysis_version.py) | 同上 |
| [models/file.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/file.py) | 同上 |
| [models/knowledge_point.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/knowledge_point.py) | 同上 |
| [api/versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/versions.py) | 移除所有 `cast()` 和 `# type: ignore`，代码恢复自然写法 |
| [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py) | Redis 客户端缓存改用模块级变量 + `cast`，消除 `attr-defined` 错误 |
| [pyproject.toml](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/pyproject.toml) | 启用 `sqlalchemy.ext.mypy.plugin`，移除冲突的 `sqlalchemy-stubs` |

#### 示例对比

```python
# Before (Column 风格 — mypy 看到 Column[str])
class RepositoryModel(Base):
    current_version = Column(String, nullable=True)  # mypy: Column[str]

# After (Mapped 风格 — mypy 正确推断 str)
class RepositoryModel(Base):
    current_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # mypy: str
```

#### 修复前后对比

| 检查项 | 修复前 | 修复后 |
|--------|--------|--------|
| mypy 错误数 | **12 errors** in 3 files | **0 errors** |
| versions.py 中的 cast() | 9 处 `cast(str, v.version)` | 0 处 |
| versions.py 中的 type: ignore | 4 处 `# type: ignore[assignment]` | 0 处 |
| pytest | 73 passed | 87 passed |

---

## 三、创建 Celery Worker 层

### 3.1 文件结构

```
codeinsight/tasks/
├── __init__.py                      # Celery 应用工厂 + 实例导出
└── analysis_tasks.py                # run_analysis 任务 + 进度推送 + DB 操作封装
```

### 3.2 Celery 配置

**tasks/__init__.py** — Celery 实例工厂：

```python
celery_app = Celery("codeinsight.tasks")

celery_app.conf.update(
    broker_url=settings.redis_url,           # redis://localhost:6379/0
    result_backend=settings.redis_url,       # 同一 Redis 存储任务结果
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.celery_task_always_eager,  # 开发环境同步执行
    task_soft_time_limit=3600,              # 1 小时软超时
    task_time_limit=7200,                    # 2 小时硬超时
    task_acks_late=True,                     # 执行完再确认，失败可重试
    worker_prefetch_multiplier=1,            # 每个 worker 一次只取一个任务
    task_default_queue="default",
    task_queues={
        "default": {"binding_key": "default"},
        "analysis": {"binding_key": "analysis.#"},
    },
    task_routes={
        "codeinsight.tasks.analysis_tasks.*": {"queue": "analysis"},
    },
)

celery_app.autodiscover_tasks(["codeinsight.tasks"])
```

### 3.3 分析任务流程

**tasks/analysis_tasks.py** — `run_analysis` 骨架：

```
PENDING ──→ SCANNING (10%) ──→ PARSING (25%) ──→ ANALYZING_MODULES (50%)
   │              │                  │                    │
   │         Phase 2:          Phase 2:             Phase 3:
   │         GitPython         Tree-sitter          LangGraph
   │         扫描文件          AST 解析              Agent 分析
   │              │                  │                    │
   └──────────────┴──────────────────┴────────────────────┘
                                     │
                              STORING (80%) ──→ COMPLETED (100%)
                                      │
                                  Phase 3:
                                  pgvector +
                                  Meilisearch
```

每个阶段通过 `_update_progress(self, status, percent, ...)` 调用 `task_instance.update_state()` 推送进度到 Redis。

### 3.4 数据库操作封装

Celery task 运行在同步上下文中，但项目使用 `asyncpg` + `AsyncSession`。解决方案：在每个 `asyncio.run()` 调用中完成一个原子事务操作。

```python
async def _do_analysis_setup(repository_id, version_tag) -> dict:
    """一次性完成版本创建 + 仓库状态更新（共享同一个 session）"""
    async with async_session_factory() as db:
        repo = await repo_dao.get_by_id(db, repository_id)
        total_files = 0  # Phase 2: GitPython 扫描
        version = await version_dao.create(db, {...})
        repo.status = TaskStatus.ANALYZING.value
        await db.flush()
        await db.commit()
        return {"version_id": version.id, "total_files": total_files}

# Task 内部
version_id, total_files = asyncio.run(_do_analysis_setup(repo_uuid, version_tag))
...
asyncio.run(_set_repo_status(repo_uuid, TaskStatus.COMPLETED.value))
```

---

## 四、实现 API 端点

### 4.1 分析任务端点（3 个）— [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py)

| 端点 | 方法 | 路径 | 状态码 | 说明 |
|------|------|------|--------|------|
| 提交分析 | POST | `/api/v1/repositories/{repository_id}/analyze` | 202 | 验证仓库 → 提交 Celery 任务 → Redis 映射 |
| 查询状态 | GET | `/api/v1/tasks/{task_id}` | 200/404 | 从 Celery result_backend 读取进度 |
| 取消任务 | POST | `/api/v1/tasks/{task_id}/cancel` | 200/404 | Celery control.revoke(terminate=True) |

### 4.2 提交端点流程

```
POST /repositories/{id}/analyze
  ↓
1. RepositoryDAO.get_by_id(db, id) → 验证仓库存在
  ↓
2. run_analysis.delay(repository_id, mode, agents) → 提交 Celery 任务
  ↓
3. Redis SET task:{task_id}:repo {repository_id} EX 604800 → 反向映射
  ↓
4. 返回 AnalysisTask(task_id=celery_result.id, status=PENDING, ...)
```

### 4.3 查询端点流程

```
GET /tasks/{task_id}
  ↓
1. AsyncResult(task_id).state → 获取 Celery 状态
  ↓
2. Redis GET task:{task_id}:repo → 查找 repository_id
  ↓
3. AsyncResult.info.meta → 提取进度信息
  ↓
4. 转换为 AnalysisTask schema 返回
```

### 4.4 取消端点流程

```
POST /tasks/{task_id}/cancel
  ↓
1. AsyncResult(task_id).state → 检查是否存在
  ↓
2. 若 SUCCESS/FAILURE → 直接返回（无需取消）
  ↓
3. celery_app.control.revoke(task_id, terminate=True) → 终止 Worker
  ↓
4. 返回取消结果消息
```

### 4.5 错误处理

```python
# 仓库不存在 → 404
if repo is None:
    raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

# 任务不存在 → 404
try:
    _ = result.state
except Exception as exc:
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found") from exc

# Redis 写入失败 → 降级记录日志，不影响主流程
try:
    client.set(...)
except redis.RedisError as exc:
    logger.warning("Redis 写入映射失败: %s", exc)
```

---

## 五、技术细节

### 5.1 Redis 映射表设计

Celery `AsyncResult` 的 `meta` 字段不存储 `repository_id`，需要额外的反向查找机制。

```
Key:     task:{task_id}:repo
Value:   {repository_uuid}
TTL:     604800 (7 天)
```

**为什么不用 Celery meta？**
- Celery meta 仅包含任务进度信息（percent, files_processed 等）
- meta 在任务完成后可能被清理
- Redis 提供独立于 Celery 的生命周期管理

### 5.2 Redis 客户端缓存

```python
def _get_redis_client() -> redis.Redis:
    if not hasattr(_get_redis_client, "_cache"):
        _get_redis_client._cache = redis.Redis(host=..., port=..., decode_responses=True)
    return _get_redis_client._cache
```

避免每次请求新建 Redis 连接对象。

### 5.3 Celery 状态映射

| Celery state | TaskStatus | progress.current_step |
|--------------|-----------|----------------------|
| PENDING | PENDING | pending |
| STARTED | 从 meta.current_step 推断 | scanning/parsing/... |
| SUCCESS | COMPLETED | completed |
| FAILURE | FAILED | — |

### 5.4 容错处理

- **result.info 可能是 Exception**：Celery FAILURE 时 `info` 属性是异常对象而非 dict，代码中做了 `isinstance(meta, dict)` 检查
- **Redis 宕机降级**：`_lookup_repository()` 捕获 `redis.RedisError`，返回占位 UUID
- **_update_progress 空指针**：`task_instance` 参数允许 `None`（开发模式 `always_eager` 下可能不绑定）

---

## 六、编写单元测试

### 6.1 测试策略

- **Mock DAO 层**：使用 `unittest.mock.AsyncMock` + `MagicMock(spec=RepositoryDAO)`
- **Mock Celery**：patch `run_analysis.delay` 返回伪造的 `AsyncResult`
- **Mock Redis**：patch `_get_redis_client()` 返回 `MagicMock`
- **直接测试 API 函数**：绕过 TestClient，直接调用异步函数并传入 mock 对象

### 6.2 测试用例清单（14 → 23 个）— [tests/test_analysis_tasks.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_analysis_tasks.py)

| 类别 | 测试数 | 覆盖场景 |
|------|--------|---------|
| submit | 3 | success, with_request(mode+agents), repository_not_found(404) |
| query | 4 | pending, completed(100%+知识点数), failure(Exception info 容错), not_found(404) |
| cancel | 4 | running(revoke succeed), already_completed, already_failed, not_found(404) |
| redis | 3 | mapping_on_submit(setex), lookup_from_redis, redis_error(degrade) |
| 去重 | 2 | rejects_duplicate_active_task(409), cancel_clears_active_task_marker |
| 细粒度取消 | 7 | check_no_flag, check_with_flag_raises, check_redis_error_silenced, cancel_at_scanning/parsing/storing, no_cancellation_completes |

### 6.3 测试结果

```
96 passed, 9 warnings in 1.22s
```

---

## 七、CI 验证

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Ruff lint | ✅ 通过 | UP045 `Optional[X]` → `X | None` 风格统一 |
| mypy | ✅ 通过 | **0 errors in 33 source files**（ORM 模型改用 `Mapped` 风格） |
| pytest | ✅ 通过 | **96 passed, 9 warnings**（全量 96，0 regression） |
| API 类型对齐 | ✅ 完成 | UUID 统一，response_model 正确 |
| Docker Compose | ✅ 已有 | celery-worker 服务已定义 |

---

## 八、文件变更清单

| 文件 | 操作 | 行数变化 |
|------|------|---------|
| [tasks/__init__.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/tasks/__init__.py) | 新建 | +57 |
| [tasks/analysis_tasks.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/tasks/analysis_tasks.py) | 新建 | +272 |
| [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py) | 重写 | +310 / -36 |
| [tests/test_analysis_tasks.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_analysis_tasks.py) | 新建 | +568 |
| [config.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/config.py) | 修改 | +2 |
| [pyproject.toml](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/pyproject.toml) | 修改 | +1 |

---

## 九、P1-08 优化项实现

### 9.1 细粒度取消（Redis 取消标志 + 每阶段检查）

**实现方式**：在 `run_analysis` 的 4 个关键阶段（scanning、parsing、analyzing、storing）后各插入 `_check_cancelled()` 调用，从 Redis 读取 `task:{task_id}:cancel` 标志，存在则抛出 `CancelledError` 终止任务。

| 组件 | 文件 | 说明 |
|------|------|------|
| `_check_cancelled()` | [tasks/analysis_tasks.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/tasks/analysis_tasks.py) | Redis 标志检查，Redis 异常时降级（不中断任务） |
| `CancelledError` | 同上 | 自定义异常，在 `except` 中设置仓库状态为 `cancelled` |
| `cancel_task` API | [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py) | 设置 `task:{task_id}:cancel` 标志（60s 过期）+ 清理 `active_task` 标记 |

### 9.2 重复提交去重（Redis 活跃任务标记）

**实现方式**：提交任务前检查 `repo:{repository_id}:active_task` 是否存在，存在则返回 409 Conflict；任务提交后写入该标记，取消/完成时清理。

| 组件 | 文件 | 说明 |
|------|------|------|
| `submit_analysis` 前置检查 | [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py) | `client.get(f"repo:{repo_id}:active_task")` → 存在则 409 |
| `submit_analysis` 写入标记 | 同上 | `client.setex(f"repo:{repo_id}:active_task", TTL, task_id)` |
| `cancel_task` 清理标记 | 同上 | `client.delete(f"repo:{repo_id}:active_task")` |

---

## 十、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| P2-01 代码扫描器 | Phase 2 | 接入 GitPython 扫描文件列表，回填 `total_files` |
| P2-02 Tree-sitter 解析 | Phase 2 | 接入 AST 解析管道 |
| P3-02 LangGraph Agent | Phase 3 | 接入多 Agent 分析逻辑 |
| P3-06 Embedding 向量化 | Phase 3 | 接入 pgvector 存储 |
| P3-07 Meilisearch 索引 | Phase 3 | 接入全文搜索索引 |
| 集成测试 | P5-02 | 当前为 Mock 测试，Phase 5 补充真实 Redis/Celery 容器测试 |

---

**报告生成时间**：2026-07-11
**作者**：CodeInsight AI Agent
**状态**：✅ 完成
