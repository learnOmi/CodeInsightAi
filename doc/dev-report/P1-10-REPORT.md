# P1-10: 数据库 Migration 脚本（Alembic 集成）- 开发报告

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P1-10 |
| 任务名称 | 数据库 Migration 脚本（Alembic 集成） |
| 所属阶段 | Phase 1（第 2-3 周） |
| 优先级 | P0 |
| 预估工时 | 4h |
| 交付物 | Alembic 配置 + 初始迁移脚本 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-05 SQLAlchemy ORM 模型 | ✅ | 4 个 ORM 模型已定义 |
| P1-03 Pydantic Schema | ✅ | 类型定义完成 |
| P1-02 Docker Compose | ✅ | PostgreSQL + pgvector 环境已就绪 |

---

## 二、交付物清单

### 2.1 Alembic 配置

| 文件 | 说明 |
|------|------|
| [alembic.ini](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/alembic.ini) | Alembic 主配置文件 |
| [alembic/env.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/alembic/env.py) | 异步迁移环境配置 |
| [alembic/script.py.mako](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/alembic/script.py.mako) | 迁移脚本模板 |

### 2.2 初始迁移脚本

| 文件 | 说明 |
|------|------|
| [20260709_001_initial_schema.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/alembic/versions/20260709_001_initial_schema.py) | 初始数据库 schema 迁移（4 张表 + 索引） |

### 2.3 项目集成

| 文件 | 说明 |
|------|------|
| [pyproject.toml](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/pyproject.toml) | 依赖声明：`alembic>=1.14.0` |
| [.gitignore](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/.gitignore) | 排除 `alembic/versions/production_*.py` |
| [README.md](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/README.md) | 文档更新 |

---

## 三、环境配置分析

### 3.1 异步迁移支持（env.py）

```python
target_metadata = Base.metadata  # 自动发现所有 ORM 模型
```

Alembic 配置支持**异步迁移**，使用 `async_engine_from_config` 从 `settings.database_url` 读取连接字符串。关键设计：

| 特性 | 实现 |
|------|------|
| 离线模式 | `run_migrations_offline()` |
| 在线模式 | `run_migrations_online()` → `asyncio.run(run_async_migrations())` |
| 事务性 DDL | `context.configure(...)` 默认启用 |

### 3.2 与 ORM 模型的自动同步

`Base.metadata` 作为目标元数据，Alembic 的 `--autogenerate` 功能可以自动检测 ORM 模型变化并生成迁移脚本。当前 4 个模型已完整注册：

- `RepositoryModel`
- `FileModel`
- `KnowledgePointModel`
- `AnalysisVersionModel`

---

## 四、初始迁移脚本分析

### 4.1 表结构

| 表名 | 字段数 | 主键 | 外键 | 说明 |
|------|--------|------|------|------|
| `repositories` | 11 | UUID | - | 仓库信息 |
| `files` | 9 | UUID | → repositories | 代码文件 |
| `analysis_versions` | 10 | UUID | → repositories | 分析版本 |
| `knowledge_points` | 14 | UUID | → repositories | 知识点（含向量） |

### 4.2 关键设计决策

#### 4.2.1 pgvector 扩展

```sql
CREATE EXTENSION IF NOT EXISTS vector
```

必须在使用 `vector` 类型之前执行。

#### 4.2.2 knowledge_points 表使用原生 SQL

```sql
CREATE TABLE knowledge_points (
    embedding vector(1536),  -- pgvector 向量类型
    ...
)
```

**原因**：Alembic 的 `op.create_table()` API 对 pgvector 第三方扩展类型支持不完善，使用原生 SQL 确保向量类型定义和维度参数完全正确。

#### 4.2.3 索引设计

| 索引 | 表 | 用途 |
|------|-----|------|
| `idx_files_repository_id` | files | 外键加速 |
| `idx_files_content_hash` | files | 内容去重 |
| `idx_analysis_versions_repository_id` | analysis_versions | 外键加速 |
| `idx_knowledge_points_repository_id` | knowledge_points | 外键加速 |
| `idx_knowledge_points_category` | knowledge_points | 分类筛选 |
| `idx_knowledge_points_version` | knowledge_points | 版本筛选 |
| `idx_knowledge_points_embedding` | knowledge_points | IVFFlat 向量索引（余弦相似度） |

### 4.3 时间字段一致性

所有时间字段使用 `sa.DateTime(timezone=True)` 并设置 `server_default=sa.text("now()")`：

| 字段 | 表 | 类型 | 默认值 |
|------|-----|------|--------|
| `created_at` | 所有表 | `TIMESTAMPTZ` | `NOW()` |
| `updated_at` | repositories, files, knowledge_points | `TIMESTAMPTZ` | `NOW()` |
| `last_analyzed_at` | repositories | `TIMESTAMPTZ` | NULL |
| `started_at` | analysis_versions | `TIMESTAMPTZ` | NULL |
| `completed_at` | analysis_versions | `TIMESTAMPTZ` | NULL |

这与 ORM 模型中的 `Mapped[datetime]` 标注完全一致。

---

## 五、验证结果

### 5.1 数据库当前版本

```bash
$ uv run alembic current
20260709_001_initial_schema (head)
```

✅ 数据库已迁移到最新版本。

### 5.2 与 ORM 模型一致性

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 表结构 | ✅ 一致 | 4 张表字段完整匹配 |
| 主键类型 | ✅ 一致 | UUID |
| 时间字段 | ✅ 一致 | `DateTime(timezone=True)` |
| pgvector 类型 | ✅ 一致 | `vector(1536)` |
| 外键约束 | ✅ 一致 | `ON DELETE CASCADE` |
| 索引 | ✅ 一致 | 7 个索引完整创建 |

---

## 六、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| CI 集成迁移检查 | P1-11 / P1-06 | 在 GitHub Actions 中增加 `alembic upgrade head` |
| Docker 自动迁移 | P1-02 | 容器启动时自动执行 `alembic upgrade head` |
| 数据库版本检查 | P2-05 | API 启动时检查 `alembic_version` 表 |
| 自动生成迁移脚本 | 开发过程中 | 当 ORM 模型变化时，使用 `alembic revision --autogenerate -m "..."` |

---

## 七、总结

P1-10 任务在 P1-05（ORM 模型定义）阶段已随基础项目搭建完成。Alembic 配置完整，初始迁移脚本覆盖了所有 4 张核心表，支持异步迁移，并正确集成了 pgvector 扩展。当前数据库版本为 `20260709_001_initial_schema`，与 ORM 模型完全一致。

后续开发中，当 ORM 模型发生变化时，使用以下命令生成新的迁移脚本：

```bash
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
```
