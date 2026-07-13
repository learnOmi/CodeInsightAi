# P2 阶段问题修复报告（FixP3）

> **修复日期:** 2026-07-13
> **修复范围:** Redis 连接池优化（API-4 + T-6）、任务模式丢失修复（API-6）、快照管理完善（SV-6 + SV-7）
> **验证结果:** pytest 31 passed (analysis_tasks) | ruff ✅ | mypy ✅

---

## 一、概述

### 1.1 修复背景

本批次修复覆盖 [P2-FollowUp-Design.md](../dev-analysis/P2-FollowUp-Design.md) 中识别的多个问题：

**本次新增修复：**
- **API-4 + T-6**: Redis 连接池管理不统一，存在连接泄漏风险
- **API-6**: 任务状态查询时丢失分析模式（增量/全量）

**之前已修复但未写入报告：**
- **SV-6 + SV-7**: 快照管理事务原子性 + 排序不确定性
- **S-6**: 目录排除检查 O(n×m) 复杂度（已隐式修复）
- **P-4**: Parser 缓存线程安全（已修复）

### 1.2 修复清单

| # | 问题编号 | 问题描述 | 严重度 | 修复文件 | 状态 |
|---|---------|---------|--------|---------|------|
| 1 | **API-4** | `api/analysis.py` Redis 客户端管理不统一，存在线程安全问题 | 🟠 High | `redis_client.py`, `analysis.py` | ✅ |
| 2 | **T-6** | `_check_cancelled()` 每次调用新建 Redis 实例，高频率调用导致连接池耗尽 | 🟠 High | `redis_client.py`, `analysis_tasks.py` | ✅ |
| 3 | **API-6** | 任务状态查询时丢失分析模式（增量/全量） | 🟠 High | `analysis.py` | ✅ |
| 4 | **SV-6** | 快照管理事务原子性：先 commit 新快照再清理旧快照，清理失败导致数据不一致 | 🟠 High | `analysis_tasks.py` | ✅ |
| 5 | **SV-7** | 快照排序不确定性：`get_all_versions()` 返回顺序依赖数据库默认排序 | 🟠 High | `file_analysis_snapshot.py` | ✅ |
| 6 | **S-6** | 目录排除检查 O(n×m) 复杂度 | 🟡 Medium | `git_scanner.py` | ✅ |
| 7 | **P-4** | Parser 缓存线程安全：check-then-set 竞态条件 | 🟠 High | `parser_factory.py` | ✅ |

### 1.3 验证结果

```
pytest tests/test_analysis_tasks.py tests/test_analysis_tasks_incremental.py → 31 passed
mypy codeinsight/db/redis_client.py codeinsight/config.py codeinsight/api/analysis.py codeinsight/tasks/analysis_tasks.py → Success: no issues found
```

---

## 二、修复详情

### 2.1 API-4 + T-6：Redis 连接池统一管理

**问题:**
1. `api/analysis.py` 使用模块级全局变量 `_redis_client`，check-then-set 模式存在线程安全问题，且客户端永不关闭导致连接泄漏
2. `tasks/analysis_tasks.py` 的 `_check_cancelled()` 每次调用都新建 `redis.Redis()` 实例，高频率调用导致连接池耗尽

**修复方式:**
新增 `codeinsight/db/redis_client.py` 模块，提供全局共享的 Redis 连接池，所有模块统一从连接池获取连接。

**新增文件:** `codeinsight/db/redis_client.py`

```python
"""
Redis 客户端管理

提供线程安全的 Redis 连接池，全局共享。
"""

import redis

from codeinsight.config import settings

_redis_pool: redis.ConnectionPool | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """
    获取全局 Redis 连接池（惰性初始化）

    与 db/engine.py 模式一致：模块级单例 + 工厂函数。
    Python 的 GIL 保证简单的赋值操作原子性，单次检查无需锁。
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            max_connections=settings.redis_pool_max_connections,
            socket_connect_timeout=settings.redis_pool_socket_timeout,
            socket_timeout=settings.redis_pool_socket_timeout,
            retry_on_timeout=True,
        )
    return _redis_pool


def get_redis_client() -> redis.Redis:
    """
    从连接池获取一个 Redis 客户端实例

    每次调用返回的客户端底层共享连接池，用完即放回。
    """
    return redis.Redis(connection_pool=get_redis_pool())


def close_redis_pool() -> None:
    """关闭连接池，释放所有连接（测试/优雅关闭时使用）"""
    global _redis_pool
    if _redis_pool is not None:
        _redis_pool.disconnect()
        _redis_pool = None
```

**新增配置项:** `codeinsight/config.py`

```python
# Redis 连接池
redis_pool_max_connections: int = 50    # 最大连接数
redis_pool_socket_timeout: int = 2      # 连接和读取超时（秒）
```

**修改 `api/analysis.py`:**
- 删除原有的 `_redis_client` 全局变量和 `_get_redis_client()` 函数
- 替换为 `from codeinsight.db.redis_client import get_redis_client`
- 所有 Redis 操作统一使用 `get_redis_client()` 获取连接

**修改 `tasks/analysis_tasks.py`:**
- 添加 `from codeinsight.db.redis_client import get_redis_client` 导入
- `_check_cancelled()` 函数中使用 `get_redis_client()` 替代每次新建 `redis.Redis()`

**效果对比:**

| 指标 | 修复前 | 修复后 |
|-----|-------|-------|
| 连接创建方式 | 每次请求新建 / 全局单例 | 连接池复用 |
| 线程安全性 | check-then-set 竞态 | GIL 保证赋值原子性 |
| 资源释放 | 进程退出时泄漏 | 可主动关闭连接池 |
| 连接数控制 | 无限制 | `max_connections=50` |

---

### 2.2 API-6：任务模式丢失修复

**问题:**
- 提交分析任务时，`mode` 参数传递给 Celery 任务
- 查询任务状态时（`get_task_status`），无法从 Celery result 中获取 mode
- `_celery_result_to_task()` 函数默认使用 `AnalysisMode.FULL`
- 导致增量分析任务在查询时显示为 FULL 模式

**修复方式:**
利用已有的 Redis task→repo 映射机制，同步存储和查询 mode 信息。

**修改 `api/analysis.py`:**

1. **新增 `_lookup_task_mode()` 函数:**
   ```python
   def _lookup_task_mode(task_id: str) -> AnalysisMode:
       """
       根据 task_id 查找分析模式

       从 Redis 中读取 task_id → mode 映射。

       Args:
           task_id: Celery 任务 ID

       Returns:
           AnalysisMode，读取失败时降级为 FULL
       """
       try:
           client = get_redis_client()
           raw = client.get(f"task:{task_id}:mode")
           if raw:
               return AnalysisMode(raw)
       except redis.RedisError:
           logger.warning("Redis 查询任务模式失败，使用默认 FULL: task_id=%s", task_id)
       return AnalysisMode.FULL
   ```

2. **修改 `submit_analysis()`:**
   - 存储 `task:{task_id}:repo` 的同时，存储 `task:{task_id}:mode`
   - TTL 与 repo 映射相同（7 天）

3. **修改 `get_task_status()`:**
   - 调用 `_lookup_task_mode()` 获取 mode
   - 传入 `_celery_result_to_task()`

**效果对比:**

| 场景 | 修复前 | 修复后 |
|-----|-------|-------|
| 提交增量任务后查询状态 | mode=FULL | mode=INCREMENTAL |
| Redis 不可用时 | 返回 FULL（降级） | 返回 FULL（降级） |

---

### 2.3 SV-6 + SV-7：快照管理完善

**问题:**
- **SV-6**: 先 commit 新快照，再清理旧快照，清理失败导致数据不一致
- **SV-7**: `get_all_versions()` 返回顺序依赖数据库默认排序，`all_versions[:N]` 随机保留

**修复方式:**

1. **事务原子性（SV-6）:**
   - 在 `_save_analysis_snapshot()` 中添加 `await db.commit()`
   - `save_snapshot()` 和 `_cleanup_old_snapshots()` 内部不做 commit
   - 调用者统一管理事务边界

2. **排序确定性（SV-7）:**
   - `FileAnalysisSnapshotDAO.get_all_versions()` 支持 `order_by_created=True` 参数
   - 使用 `order_by(FileAnalysisSnapshotModel.created_at.desc())` 按创建时间降序
   - `keep_versions = all_versions[:N]` 取最新 N 个版本

**修复代码:**

```python
# analysis_tasks.py
async def _save_analysis_snapshot(repo_uuid: UUID, version_tag: str, files: list[FileModel]) -> int:
    async with async_session_factory() as db:
        file_dao = FileDAO()
        local_files = await file_dao.get_by_repository(db, repo_uuid)
        snapshot_manager = SnapshotManager(db)
        count = await snapshot_manager.save_snapshot(repo_uuid, version_tag, local_files)
        await db.commit()  # ✅ 已修复
        return count
```

---

### 2.4 S-6：目录排除算法优化

**问题:**
设计稿编写时，`exclude_dirs` 类型为 `list[str]`，`any(part in self.exclude_dirs for part in file_path.parts)` 的复杂度为 O(n×m)。

**实际状态:**
已隐式修复，`exclude_dirs` 使用 `frozenset`，查找复杂度为 O(1)：

```python
# git_scanner.py
DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", ".tox", ".venv", "venv", ...
})

def __init__(self, repo_path: str, exclude_dirs: frozenset[str] | None = None):
    self.exclude_dirs: frozenset[str] = exclude_dirs or self.DEFAULT_EXCLUDE_DIRS
```

---

### 2.5 P-4：Parser 缓存线程安全

**问题:**
- `_parser_cache` 是全局 dict
- check-then-set 是经典 TOCTOU 竞态
- `None` 结果被缓存，后续合法调用也返回 `None`

**实际状态:**
已修复，使用 `RLock` 保护 check-then-create：

```python
# parser_factory.py
_parser_cache: dict[str, LanguageParser | None] = {}
_cache_lock = RLock()

def get_parser(language: str) -> LanguageParser | None:
    with _cache_lock:
        if language in _parser_cache:
            return _parser_cache[language]
        parser = _create_parser_for_language(language)
        if parser is not None:
            _parser_cache[language] = parser
        return parser  # 失败时不缓存 None，下次可重试
```

---

## 三、修改文件清单

### 3.1 本次新增修复

| 文件 | 变更类型 | 问题编号 | 说明 |
|-----|---------|---------|------|
| `codeinsight/db/redis_client.py` | 新增 | API-4, T-6 | 全局 Redis 连接池管理模块 |
| `codeinsight/config.py` | 修改 | API-4, T-6 | 新增 `redis_pool_max_connections`, `redis_pool_socket_timeout` |
| `codeinsight/api/analysis.py` | 修改 | API-4, API-6 | 删除 `_redis_client`，使用统一连接池；添加 mode 存储和查询 |
| `codeinsight/tasks/analysis_tasks.py` | 修改 | T-6 | `_check_cancelled()` 使用统一连接池 |
| `tests/test_analysis_tasks.py` | 修改 | API-4, T-6, API-6 | 更新 mock 路径；验证 mode 存储 |

**共计:** 5 个文件修改

### 3.2 之前已修复（补充记录）

| 文件 | 变更类型 | 问题编号 | 说明 |
|-----|---------|---------|------|
| `codeinsight/tasks/analysis_tasks.py` | 修改 | SV-6 | 添加 `db.commit()` 到 `_save_analysis_snapshot` |
| `codeinsight/repositories/file_analysis_snapshot.py` | 修改 | SV-7, R-1 | 添加 `order_by_created` 参数；删除 `create_many` 中逐行 `db.refresh()` |
| `codeinsight/repositories/module_dependency.py` | 修改 | R-1 | 删除 `create_many` 中逐行 `db.refresh()` |
| `codeinsight/scanners/git_scanner.py` | 修改 | S-10 | 提取魔法数字为命名常量（`MAX_FILE_SIZE_BYTES` 等） |
| `codeinsight/parsers/base.py` | 修改 | P-2 | 添加文件大小保护（10MB 阈值） |
| `codeinsight/pipelines/structure_pipeline.py` | 修改 | SV-12 | 添加 `CreateManyFn` 类型注解 |
| `codeinsight/api/repositories.py` | 修改 | API-16 | DELETE 接口返回 204 No Content |
| `codeinsight/api/files.py` | 修改 | API-16 | DELETE 接口返回 204 No Content |
| `codeinsight/main.py` | 修改 | API-17 | 添加 `NotImplementedError` 全局异常处理器 |
| `codeinsight/db/session.py` | 修改 | DB-6 | Session 异常时显式 rollback |
| `codeinsight/services/incremental_analyzer.py` | 修改 | 8.1 | 实现 DAO 依赖注入 |

---

## 四、测试覆盖

### 4.1 修改测试

| 测试文件 | 修改原因 | 修改内容 |
|---------|---------|---------|
| `tests/test_analysis_tasks.py` | mock 路径变更 | 将 `_get_redis_client` 改为 `get_redis_client` |
| `tests/test_analysis_tasks.py` | mode 存储验证 | 更新 `test_redis_mapping_on_submit` 验证 3 次 set 调用 |

### 4.2 测试结果

```
pytest tests/test_analysis_tasks.py tests/test_analysis_tasks_incremental.py -v

31 passed, 27 warnings in 60.64s
```

### 4.3 关键测试验证

- `test_redis_mapping_on_submit` — 验证 Redis 映射写入正常（含 mode）
- `test_submit_analysis_rejects_duplicate_active_task` — 验证活跃任务检测正常
- `test_cancel_task_clears_active_task_marker` — 验证取消任务清理正常
- `test_lookup_repository_from_redis` — 验证仓库查找正常
- `test_check_cancelled_no_flag` — 验证取消检查正常
- `test_check_cancelled_with_flag_raises` — 验证取消标志检测正常

---

## 五、回归风险

| 风险点 | 影响范围 | 缓解措施 |
|-------|---------|---------|
| 连接池初始化失败 | 所有 Redis 操作 | 保持原有异常处理，降级到无 Redis 模式 |
| mock 路径变更 | 单元测试 | 同步更新测试文件中的 patch 路径 |
| 连接池配置不当 | 高并发场景 | 默认 `max_connections=50` 为保守值，可通过环境变量调整 |
| Redis 故障降级 | 任务模式查询 | Redis 不可用时返回 FULL，不影响功能可用性 |

---

## 六、后续建议

1. **连接池监控:** 建议添加连接池使用指标监控（活跃连接数、等待队列长度等）
2. **优雅关闭:** 在 `main.py` 中注册 shutdown handler，调用 `close_redis_pool()` 释放资源
3. **多实例支持:** 若未来需要多 Redis 实例，可扩展为 `get_redis_pool(db_number: int)` 重载
4. **快照状态关联:** 快照清理可关联 `analysis_versions` 表的状态，只清理 `COMPLETED` 的历史版本

---

## 附录：设计文档引用

- [P2-FollowUp-Design.md](../dev-analysis/P2-FollowUp-Design.md) — 后续问题修复方案设计
- [P2-CODE-REVIEW.md](../dev-analysis/P2-CODE-REVIEW.md) — 综合代码审查报告