# P2 阶段深度问题分析清单

## 项目信息
- **项目**: CodeInsight AI 后端
- **分析日期**: 2026-07-14
- **技术栈**: Python 3.12 + FastAPI + SQLAlchemy asyncio + Celery + PostgreSQL

---

## 一、严重问题（🔴 3 个）

### S-1：健康检查端点泄露敏感信息

| 属性 | 值 |
|------|------|
| **严重程度** | 🔴 严重 |
| **文件** | `codeinsight/main.py:90-126` |
| **问题描述** | `/api/v1/health` 端点未添加认证保护，当数据库或 Redis 连接失败时，直接返回详细错误信息（包含连接字符串、密码片段等） |
| **影响分析** | 外部攻击者可获取内部架构信息、数据库连接错误详情，可能导致进一步的安全攻击 |
| **修复方案** | 1. 健康检查端点添加认证保护；2. 错误信息仅返回 "unavailable" 状态，详细错误记录到日志 |

### S-2：API_KEY 为空时所有 API 免认证

| 属性 | 值 |
|------|------|
| **严重程度** | 🔴 严重 |
| **文件** | `codeinsight/auth.py:66-71`, `codeinsight/config.py:70` |
| **问题描述** | 当 `settings.api_key` 为空（默认值 `""`）时，`get_api_key_dependency(None)` 返回的依赖函数直接跳过认证。生产环境如果 `.env` 中 `API_KEY` 未配置，整个 API 将对外公开 |
| **影响分析** | 生产环境误部署可能导致全部数据泄露、未授权访问 |
| **修复方案** | 当 `app_env == "production"` 且 `api_key` 为空时，启动时直接报错退出 |

### S-3：Bearer Token 验证为弱检查

| 属性 | 值 |
|------|------|
| **严重程度** | 🔴 严重 |
| **文件** | `codeinsight/auth.py:100-107` |
| **问题描述** | `get_bearer_token_dependency` 仅检查 `token.credentials` 非空，未进行任何签名验证。注释明确标注 "TODO: 集成用户系统后" |
| **影响分析** | 如果未来启用 JWT 方案但未实现完整验证，将完全形同虚设 |
| **修复方案** | 添加注释标记为 "不可用" 或抛异常，避免误用 |

---

## 二、高优先级问题（🟠 3 个）

### P-1：增量分析全量加载到内存

| 属性 | 值 |
|------|------|
| **严重程度** | 🟠 高 |
| **文件** | `codeinsight/services/incremental_analyzer.py:379-384` |
| **问题描述** | 依赖传播 BFS 前将所有调用边、模块依赖和 AST 节点加载到内存。对于大型仓库（数万文件、数十万 AST 节点），内存占用极高 |
| **影响分析** | 内存占用随仓库规模线性增长，大型仓库可能导致 OOM |
| **修复方案** | 改为按需逐层查询 — 在 BFS 的每一层通过当前 file_id/node_id 动态查询相关边和节点 |

### P-2：async_session_factory 大量分散使用

| 属性 | 值 |
|------|------|
| **严重程度** | 🟠 高 |
| **文件** | `analysis_orchestrator.py`（20+ 处）、`analysis_tasks.py`（10+ 处） |
| **问题描述** | AnalysisOrchestrator 每个内部方法都创建独立的 `async_session_factory()`，同一任务执行中可能有 10-15 个独立的数据库连接被创建和销毁 |
| **影响分析** | 连接池频繁创建/销毁，增加延迟；在事务语义上每个操作独立，无法保证跨操作原子性 |
| **修复方案** | 对同一逻辑操作使用共享 session；在 AnalysisOrchestrator 中维护一个 session 上下文管理器 |

### P-3：魔法数字硬编码

| 属性 | 值 |
|------|------|
| **严重程度** | 🟠 高 |
| **文件** | `analysis.py:40,337`, `structure_pipeline.py:63`, `base.py:20`, `git_scanner.py:17` |
| **问题描述** | `_MAPPING_TTL = 86400 * 7`、`cancelled` 标志 TTL 60 秒、`batch_size = 500`、`MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024` 等魔法数字硬编码在多个文件中 |
| **影响分析** | 配置不可调，违反常量提取原则，多处定义可能导致不一致 |
| **修复方案** | 提取到 `config.py` 作为配置项，其他文件通过 `settings` 读取 |

---

## 三、中优先级问题（🟡 9 个）

### D-1：analysis_tasks.py 中存在死代码

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `analysis_tasks.py:135-690` |
| **问题描述** | 存在与 Orchestrator 重复的辅助函数和未使用的 `_STATUS_TO_STEP` 字典 |
| **修复方案** | 移除死代码和重复函数 |

### D-2：Redis 键命名散落各处

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `analysis.py`, `analysis_tasks.py`, `analysis_orchestrator.py` |
| **问题描述** | Redis 键使用 f-string 硬编码命名，TTL 值为魔法数字 |
| **修复方案** | 提取到 `constants/redis_keys.py` |

### D-3：MAX_FILE_SIZE_BYTES 重复定义

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `base.py:20`, `git_scanner.py:17`, `config.py:79` |
| **问题描述** | `MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024` 在三处独立定义 |
| **修复方案** | 统一到 `config.py` |

### D-4：ModuleDependencyDAO.delete_by_file_ids 两次 DELETE

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `module_dependency.py:93-110` |
| **问题描述** | 删除操作分为两次独立的 DELETE，性能不一致 |
| **修复方案** | 合并为单次 DELETE |

### Q-1：健康检查返回异常详情

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `main.py:107-112,118-122` |
| **问题描述** | 数据库/Redis 连接失败时直接返回 `str(e)` 作为错误信息 |
| **修复方案** | 仅返回 "unavailable" 状态，详细错误记录到日志 |

### Q-2：全局异常处理器不完整

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `main.py:60-80` |
| **问题描述** | 仅注册了 3 个自定义异常处理器，其他异常未被捕获 |
| **修复方案** | 添加全局 Exception 处理器，返回统一格式的 500 响应 |

### Q-3：CancelledError 在两个文件中独立定义

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `analysis_tasks.py:86-89`, `analysis_orchestrator.py:42-45` |
| **问题描述** | 两个文件独立定义 `CancelledError`，不是同一个类 |
| **修复方案** | 提取到 `exceptions.py` 作为共享异常类 |

### DB-1：ast_nodes 表缺少关键索引

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `models/ast_node.py` |
| **问题描述** | 缺少 `repository_id + node_type` 和 `repository_id + file_id` 复合索引 |
| **修复方案** | 数据库迁移添加索引 |

### DB-2：call_edges 和 module_dependencies 缺少索引

| 属性 | 值 |
|------|------|
| **严重程度** | 🟡 中 |
| **文件** | `models/call_edge.py`, `models/module_dependency.py` |
| **问题描述** | 缺少 `repository_id` 索引 |
| **修复方案** | 数据库迁移添加索引 |

---

## 四、低优先级问题（🟢 5 个）

| # | 问题 | 文件 | 修复方案 |
|---|------|------|----------|
| M-1 | `print` 混用在模块顶层 | `main.py:22-36` | 替换为 `logger.info()` |
| M-2 | `FileDAO.get_by_repository` 无分页 | `file.py:186-200` | 添加 `limit` 参数 |
| M-3 | `RepositoryModel.status` 用 `str` 而非 Enum | `repository.py` | 改为 Enum 类型 |
| M-4 | pgvector 维度硬编码 `vector(1536)` | `knowledge_point.py` | 从配置读取 |
| M-5 | `ModuleDependencyDAO.delete_by_file_ids` rowcount 读取方式不一致 | `module_dependency.py:99,107` | 统一使用 `getattr` |
