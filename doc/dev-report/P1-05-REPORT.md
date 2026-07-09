# P1-05: SQLAlchemy 2.0 ORM 模型定义 - 开发报告

## 一、任务概述

### 1.1 任务定义

| 项目 | 内容 |
|------|------|
| 任务编号 | P1-05 |
| 任务名称 | SQLAlchemy 2.0 ORM 模型定义（Repository, File, KnowledgePoint, Version）|
| 所属阶段 | Phase 1 |
| 优先级 | P0 |
| 预估工时 | 10h |
| 交付物 | 数据库 Migration |

### 1.2 目标

完成 CodeInsight AI 后端的数据库层基础设施建设，包括：
- SQLAlchemy 2.0 异步数据库连接管理
- 4 个核心实体的 ORM 模型定义
- Alembic 异步迁移配置与初始迁移脚本
- pgvector 扩展集成支持语义搜索

### 1.3 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-02 Docker Compose | ✅ | PostgreSQL + pgvector 镜像已配置 |
| P1-03 Pydantic Schema | ✅ | API 契约层已就绪，ORM 模型需与其对齐 |
| pyproject.toml | ✅ | sqlalchemy[asyncio]、asyncpg、alembic、pgvector 依赖已声明 |

---

## 二、技术选型

### 2.1 ORM 框架

选择 **SQLAlchemy 2.0** 作为 ORM 框架，原因：
- 支持异步操作（asyncpg）
- Declarative Base API 简洁直观
- 与 FastAPI 无缝集成
- Pydantic `from_attributes=True` 支持直接从 ORM 实例转换

### 2.2 迁移工具

选择 **Alembic** 作为数据库迁移工具，原因：
- SQLAlchemy 官方迁移工具
- 支持异步数据库连接
- 成熟稳定，社区活跃

### 2.3 向量数据库

选择 **pgvector** 作为向量存储，原因：
- 与 PostgreSQL 深度集成，无需额外服务
- 支持 ANN（Approximate Nearest Neighbor）搜索
- 维度 1536（适配 sentence-transformers 模型输出）

---

## 三、目录结构

### 3.1 新增文件

```
codeinsight-backend/
├── alembic/                                    # Alembic 迁移配置
│   ├── __init__.py                             # 模块标识
│   ├── env.py                                  # 异步迁移配置（核心）
│   ├── script.py.mako                          # 迁移脚本模板
│   └── versions/                               # 迁移脚本存放目录
│       ├── .gitkeep                            # Git 占位文件
│       └── 20260709_001_initial_schema.py      # 初始迁移（含 pgvector）
├── alembic.ini                                 # Alembic 主配置文件
└── codeinsight/
    ├── db/                                     # 数据库基础设施
    │   ├── __init__.py                         # 统一导出
    │   ├── base.py                             # SQLAlchemy Declarative Base
    │   ├── engine.py                           # 异步 Engine 创建
    │   └── session.py                          # AsyncSession 工厂
    └── models/                                 # ORM 模型
        ├── __init__.py                         # 统一导出
        ├── repository.py                       # Repository 模型
        ├── file.py                             # File 模型
        ├── knowledge_point.py                  # KnowledgePoint 模型（含向量）
        └── analysis_version.py                 # AnalysisVersion 模型
```

### 3.2 关键文件说明

| 文件 | 职责 | 关键特性 |
|------|------|---------|
| `db/base.py` | 定义 Declarative Base | 所有 ORM 模型的父类 |
| `db/engine.py` | 创建异步 Engine | 使用 `postgresql+asyncpg://` |
| `db/session.py` | 会话工厂 | `AsyncGenerator[AsyncSession, None]` |
| `db/__init__.py` | 统一导出 | Base, engine, async_session_factory, get_db_session |
| `models/__init__.py` | 统一导出 | 4 个 ORM 模型 |
| `alembic/env.py` | 异步迁移入口 | `async_engine_from_config` + `asyncio.run()` |
| `alembic/versions/20260709_001_initial_schema.py` | 初始迁移 | 创建 pgvector 扩展 + 4 张表 |

---

## 四、核心实体设计

### 4.1 Repository（仓库）

| 字段 | ORM 类型 | SQL 类型 | 说明 |
|------|---------|---------|------|
| id | UUID | UUID | 主键，默认 uuid4 |
| name | String | TEXT | 仓库名称 |
| path | String | TEXT | 本地路径（唯一约束） |
| status | String | TEXT | pending/analyzing/completed/failed/cancelled |
| current_version | String | TEXT | 当前分析版本号 |
| file_count | Integer | INT | 文件数量 |
| line_count | Integer | INT | 代码行数 |
| knowledge_points_count | Integer | INT | 知识点数量 |
| language_distribution | JSONB | JSONB | 语言分布统计 |
| created_at | DateTime | TIMESTAMPTZ | 创建时间（server_default=NOW()） |
| updated_at | DateTime | TIMESTAMPTZ | 更新时间（onupdate=NOW()） |
| last_analyzed_at | DateTime | TIMESTAMPTZ | 最后分析时间 |

### 4.2 File（文件）

| 字段 | ORM 类型 | SQL 类型 | 说明 |
|------|---------|---------|------|
| id | UUID | UUID | 主键 |
| repository_id | UUID(ForeignKey) | UUID | 外键：repositories.id，CASCADE 删除 |
| path | String | TEXT | 相对路径 |
| absolute_path | String | TEXT | 绝对路径 |
| language | String | TEXT | 编程语言 |
| line_count | Integer | INT | 行数 |
| size_bytes | Integer | INT | 文件大小 |
| content_hash | String | TEXT | 内容哈希（增量检测用） |
| created_at | DateTime | TIMESTAMPTZ | 创建时间 |
| updated_at | DateTime | TIMESTAMPTZ | 更新时间 |

### 4.3 KnowledgePoint（知识点）⭐ 核心

| 字段 | ORM 类型 | SQL 类型 | 说明 |
|------|---------|---------|------|
| id | UUID | UUID | 主键 |
| version | String | TEXT | 分析版本号 |
| repository_id | UUID(ForeignKey) | UUID | 外键：repositories.id，CASCADE 删除 |
| category | String | TEXT | DP- / AD- / AL- / ET- / DK- |
| category_name | String | TEXT | 分类中文名 |
| title | String | TEXT | 标题 |
| description | Text | TEXT | 简介 |
| confidence | Float | FLOAT | 置信度 |
| tags | JSONB | JSONB | 标签列表 |
| code_snippets | JSONB | JSONB | 关联代码片段 |
| call_chain | JSONB | JSONB | 调用链 |
| expansion | JSONB | JSONB | AI 生成的拓展内容 |
| **embedding** | **Vector(1536)** | **vector(1536)** | **pgvector 向量** |
| knowledge_metadata | JSONB | JSONB | 元数据（agent、模型、tokens 等） |
| created_at | DateTime | TIMESTAMPTZ | 创建时间 |
| updated_at | DateTime | TIMESTAMPTZ | 更新时间 |

### 4.4 AnalysisVersion（分析版本）

| 字段 | ORM 类型 | SQL 类型 | 说明 |
|------|---------|---------|------|
| id | UUID | UUID | 主键 |
| repository_id | UUID(ForeignKey) | UUID | 外键：repositories.id，CASCADE 删除 |
| version | String | TEXT | 版本号（唯一约束） |
| status | String | TEXT | pending/analyzing/completed/failed |
| total_files | Integer | INT | 总文件数 |
| analyzed_files | Integer | INT | 已分析文件数 |
| knowledge_points_count | Integer | INT | 提取的知识点数量 |
| started_at | DateTime | TIMESTAMPTZ | 开始时间 |
| completed_at | DateTime | TIMESTAMPTZ | 完成时间 |
| error_message | Text | TEXT | 错误信息 |
| created_at | DateTime | TIMESTAMPTZ | 创建时间 |

---

## 五、ORM 与 Schema 对齐策略

### 5.1 两层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    API Layer (Pydantic)                      │
│  Repository, KnowledgePoint, AnalysisVersion (snake_case)   │
│  → alias_generator=to_camel → API 返回 camelCase            │
│  → from_attributes=True → 可从 ORM 实例自动转换              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    DB Layer (SQLAlchemy)                    │
│  RepositoryModel, KnowledgePointModel (snake_case)          │
│  → PostgreSQL UUID, TIMESTAMPTZ, JSONB, Vector(1536)        │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 关键差异

| 特性 | Pydantic Schema | SQLAlchemy Model |
|------|-----------------|------------------|
| 时间类型 | `str` (ISO 8601) | `DateTime(timezone=True)` |
| ID 类型 | `str` | `UUID` |
| 数组/对象 | `list[...]`, `dict[...]` | `JSONB` |
| 向量 | 无（API 不直接暴露） | `Vector(1536)` |
| 元数据字段 | `metadata` | `knowledge_metadata`（Python 属性名），数据库列名仍为 `metadata` |

**metadata 字段特殊处理**：由于 `metadata` 是 SQLAlchemy Declarative Base 的保留属性（用于存储表元数据），ORM 模型使用 `knowledge_metadata` 作为 Python 属性名，但通过 `Column("metadata", ...)` 指定数据库列名为 `metadata`。Pydantic Schema 通过 `Field(validation_alias="knowledge_metadata")` 实现从 ORM 实例到 Schema 的自动转换。

### 5.3 转换示例

```python
# Pydantic Schema（API 契约）
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class Repository(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,    # 支持从 ORM 实例转换
        populate_by_name=True,   # 支持 snake_case 和 camelCase 反序列化
        alias_generator=to_camel, # API 序列化时自动转 camelCase
    )
    id: str
    name: str
    path: str
    # ...

# ORM Model（数据库层）
class RepositoryModel(Base):
    __tablename__ = "repositories"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)
    # ...

# 转换使用
async def get_repository(db: AsyncSession, repo_id: UUID) -> Repository:
    db_repo = await db.get(RepositoryModel, repo_id)
    return Repository.from_orm(db_repo)  # 自动转换
```

---

## 六、Alembic 异步配置

### 6.1 env.py 关键配置

Alembic 默认使用同步连接，项目使用 `asyncpg`，需自定义异步迁移逻辑：

```python
async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())
```

### 6.2 初始迁移内容

首个迁移脚本 `20260709_001_initial_schema.py` 包含：

1. **创建 pgvector 扩展**（必须在表之前）
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **创建 4 张表**：repositories、files、analysis_versions、knowledge_points

4. **创建索引**：为查询性能优化添加以下索引：
   - `idx_files_repository_id`（files.repository_id）
   - `idx_files_content_hash`（files.content_hash）
   - `idx_analysis_versions_repository_id`（analysis_versions.repository_id）
   - `idx_knowledge_points_repository_id`（knowledge_points.repository_id）
   - `idx_knowledge_points_category`（knowledge_points.category）
   - `idx_knowledge_points_version`（knowledge_points.version）
   - `idx_knowledge_points_embedding`（knowledge_points.embedding，IVFFlat 索引，支持向量相似度搜索）

---

## 七、验证结果

### 7.1 ORM 模型导入验证

```
ORM models imported successfully
Tables: ['repositories', 'files', 'knowledge_points', 'analysis_versions']
```

### 7.2 Ruff 检查

```
Found 17 errors (17 fixed, 0 remaining).
```

### 7.3 Mypy 检查

```
Success: no issues found in 9 source files
```

### 7.4 修复的问题

| 问题 | 文件 | 修复方式 |
|------|------|---------|
| `metadata` 是 SQLAlchemy 保留属性 | `knowledge_point.py` + `knowledge.py` | ORM 使用 `knowledge_metadata` 属性名 + `Column("metadata", ...)` 列名；Pydantic 使用 `Field(validation_alias="knowledge_metadata")` |
| AsyncGenerator 返回类型错误 | `session.py` | 返回类型改为 `AsyncGenerator[AsyncSession, None]` |
| 缺少数据库索引 | `20260709_001_initial_schema.py` | 添加 7 个索引（外键 + 分类 + 版本 + IVFFlat 向量索引） |
| 未使用的导入 | 多个文件 | ruff --fix 自动清理 |
| 导入顺序不规范 | 多个文件 | ruff --fix 自动格式化 |

---

## 八、后续工作

### 8.1 待实施

| 任务 | 关联 P1 任务 | 说明 |
|------|------------|------|
| 运行迁移脚本 | P1-10 | 需要 PostgreSQL 容器运行 |
| 创建 DAO/Repository 层 | P1-07 | 在 ORM 模型之上封装 CRUD 操作 |
| 实现 API 端点 | P1-07 | 接入 FastAPI 路由 |
| 创建 pgvector 索引 | P1-10 | 为 embedding 列创建 ANN 索引 |

### 8.2 迁移运行方式

```bash
# 需要先启动 PostgreSQL 容器
docker-compose -f docker-compose.yml up -d

# 运行迁移
cd codeinsight-backend
uv run alembic upgrade head
```

---

## 九、总结

P1-05 任务已完成，主要成果：

1. **数据库基础设施**：`codeinsight/db/` 提供完整的异步 SQLAlchemy 连接管理
2. **ORM 模型**：4 个核心实体（Repository、File、KnowledgePoint、AnalysisVersion），字段与 P1-03 的 Pydantic Schema 对齐
3. **pgvector 集成**：KnowledgePoint 模型包含 `embedding Vector(1536)` 列，支持后续语义搜索功能
4. **Alembic 配置**：完整的异步迁移配置，初始迁移脚本已创建
5. **代码质量**：通过 ruff 和 mypy 检查，无错误

---

**报告生成时间**：2026-07-09
**作者**：CodeInsight AI Agent
**状态**：✅ 完成
