# P1-09: 前端仓库管理页面 - 开发报告

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P1-09 |
| 任务名称 | 前端仓库管理页面（添加路径 + 仓库列表页） |
| 所属阶段 | Phase 1（第 2-3 周） |
| 优先级 | P0 |
| 预估工时 | 8h |
| 交付物 | 交互式表单 + 仓库列表页（含状态筛选、进度条、操作按钮） |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-03 Pydantic Schema | ✅ | Repository/RepositoryCreate 已定义 |
| P1-05 SQLAlchemy ORM | ✅ | RepositoryModel 已定义 |
| P1-07 Repository CRUD API | ✅ | GET/POST/PUT/DELETE /api/v1/repositories |
| P1-08 Analysis Task API | ✅ | 分析提交/查询/取消 API |
| @codeinsight/shared | ✅ | generated.ts 类型已生成 |
| Next.js + React Query | ✅ | 前端框架已搭建 |

---

## 二、前端分层架构设计

采用经典的三层架构：**API Client → React Query Hooks → UI Components**

### 2.1 架构图

```
┌─────────────────────────────────────────┐
│  Page (repositories/page.tsx)          │
│  - 组装 Form + List                    │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Components                            │
│  - RepoForm: 添加仓库表单              │
│  - RepoList: 列表 + 状态筛选          │
│  - RepoCard: 卡片 + 进度条 + 操作      │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Hooks (use-repositories.ts)           │
│  - useRepositories: 列表查询           │
│  - useCreateRepository: 创建 mutation  │
│  - useSubmitAnalysis: 分析提交         │
│  - useTaskStatus: 任务状态轮询         │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  API Client (api.ts)                   │
│  - apiFetch: 统一 fetch wrapper        │
│  - repositories CRUD                   │
│  - analysis tasks (submit/status/cancel)│
└─────────────────────────────────────────┘
                    │
                    ▼
              Backend API
```

### 2.2 类型系统

所有类型从 `@codeinsight/shared` 包导入，结构如下：

```typescript
type Repository = components["schemas"]["Repository"];
type RepositoryCreate = components["schemas"]["RepositoryCreate"];
type AnalysisTask = components["schemas"]["AnalysisTask"];
```

后端 Pydantic 使用 `alias_generator=to_camel` 序列化，前端接收 camelCase 字段。

---

## 三、核心功能实现

### 3.0 Pydantic Schema 类型对齐（API 500 → 200）

**问题**：前端开发时发现 `GET /api/v1/repositories` 返回 **500 Internal Server Error**，错误信息：

```
fastapi.exceptions.ResponseValidationError: 3 validation errors:
  {'type': 'string_type', 'loc': ('response', 0, 'id'), 'msg': 'Input should be a valid string',
   'input': UUID('9fba2fcc-...')}
  {'type': 'string_type', 'loc': ('response', 0, 'created_at'), 'msg': 'Input should be a valid string',
   'input': datetime.datetime(2026, 7, 9, ...)}
```

**根因**：Pydantic Schema 中 `id`、`created_at`、`updated_at` 定义为 `str`，但 ORM 模型返回的是 `UUID` 和 `datetime` 对象。FastAPI 序列化时类型不匹配导致 500。

**解决方案**：将 Schema 字段改为原生 Python 类型（`UUID`、`datetime`），使用 `@field_serializer` 序列化为 ISO 字符串，确保 API 响应为 JSON 兼容的 `string` 类型。

#### 修改清单

| 文件 | 改动 |
|------|------|
| [schemas/repository.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/repository.py) | `id: str` → `UUID` + `@field_serializer("id")`；`created_at/updated_at: str` → `datetime` + `@field_serializer` |
| [schemas/file.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/file.py) | 同上 |
| [schemas/knowledge.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/knowledge.py) | `id/repository_id: str` → `UUID`；`created_at/updated_at: str` → `datetime` |
| [schemas/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/analysis.py) | `repository_id: str` → `UUID`；`submitted_at/started_at/completed_at: str` → `datetime`；`AnalysisVersion` 同理 |
| [generated.ts](file:///c:/Users/Administrator/CodeInsightAi/packages/shared/src/generated.ts) | 重新生成 OpenAPI spec（UUID/datetime 序列化为 `string`，前端无需改动） |

#### 验证结果

```python
# GET /api/v1/repositories 返回 200
[{'id': '9fba2fcc-...', 'name': 'my-project', ..., 
  'createdAt': '2026-07-09T18:43:21.135017+00:00', 
  'updatedAt': '2026-07-09T18:43:21.135017+00:00'}]
```

### 3.1 SQLAlchemy ORM `Mapped` 标注类型修正（mypy 9 errors → 0）

**问题**：Schema 类型对齐后，`uv run mypy codeinsight` 发现 9 个类型错误，核心原因是两处不一致：

1. **Schema 改为 `UUID`/`datetime` 后**，API 代码中构造 Pydantic 模型时仍传入 `str`（如 `str(repo_id)`、`str(v.created_at)`）
2. **ORM 模型使用 `Mapped[DateTime]`/`Mapped[UUID]`**，这是 SQLAlchemy **列类型**而非 Python 原生类型，违反了 `Mapped` 的语义约定

**根因**：SQLAlchemy 2.0 的 `Mapped[T]` 标注应该使用 **Python 原生类型**，而非 SQLAlchemy 列类型：

| 错误写法 | 正确写法 |
|----------|---------|
| `Mapped[DateTime]`（SQLAlchemy 列类型） | `Mapped[datetime]`（Python 原生类型） |
| `Mapped[UUID]`（SQLAlchemy 列类型） | `Mapped[uuid.UUID]`（Python 原生类型） |

**解决方案**：

- 4 个 ORM 模型文件：`Mapped[DateTime]` → `Mapped[datetime]`，`Mapped[UUID]` → `Mapped[uuid.UUID]`
- API 代码：移除不必要的 `str()` 包装，直接传递原生 `UUID`/`datetime` 对象
- `_utcnow()` 函数：返回值从 `str` 改为 `datetime`

#### 修改清单

| 文件 | 改动 |
|------|------|
| [models/repository.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/repository.py) | `Mapped[DateTime]` → `Mapped[datetime]`（3 处：created_at, updated_at, last_analyzed_at） |
| [models/analysis_version.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/analysis_version.py) | `Mapped[DateTime]` → `Mapped[datetime]`（4 处：started_at, completed_at, created_at） |
| [models/knowledge_point.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/knowledge_point.py) | `Mapped[DateTime]` → `Mapped[datetime]`（2 处：created_at, updated_at） |
| [models/file.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/file.py) | `Mapped[DateTime]` → `Mapped[datetime]`（2 处：created_at, updated_at） |
| [api/versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/versions.py) | `str(v.created_at)` → `v.created_at`（传递原生 datetime） |
| [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py) | `_utcnow()` 返回 `datetime`；移除 `str(repo_id)`、`str(value)` 包装；`meta["started_at"]` 从 ISO 字符串解析回 `datetime` |
| [tests/test_analysis_tasks.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_analysis_tasks.py) | `result.repository_id == repo_uuid` → `str(result.repository_id) == repo_uuid` |
| [repositories/analysis_version.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/repositories/analysis_version.py) | `session.add(version)` → `session.add_all(...)` |

#### 验证结果

```
ruff check      → ✅ All checks passed!
mypy            → ✅ Success: no issues found in 33 source files
pytest          → ✅ 96 passed, 11 warnings
```

---

### 3.2 API 客户端层

| 函数 | 用途 | 端点 |
|------|------|------|
| `apiFetch<T>()` | 统一请求封装（错误处理、JSON 序列化） | - |
| `getRepositories()` | 获取仓库列表 | GET /api/v1/repositories |
| `createRepository()` | 创建仓库 | POST /api/v1/repositories |
| `deleteRepository()` | 删除仓库 | DELETE /api/v1/repositories/:id |
| `submitAnalysis()` | 提交分析任务 | POST /api/v1/repositories/:id/analyze |
| `getTaskStatus()` | 查询任务状态 | GET /api/v1/tasks/:task_id |
| `cancelTask()` | 取消任务 | POST /api/v1/tasks/:task_id/cancel |

**错误处理**：自定义 `APIError` 类，包含 `status` 和 `message`，便于组件根据 HTTP 状态码展示不同提示。

### 3.3 React Query Hooks

| Hook | 功能 | 特性 |
|------|------|------|
| `useRepositories()` | 列表查询 | 自动缓存、后台刷新 |
| `useCreateRepository()` | 创建 mutation | 成功后自动刷新列表 |
| `useDeleteRepository()` | 删除 mutation | 成功后自动刷新列表 |
| `useSubmitAnalysis()` | 分析提交 | 409 去重错误处理 |
| `useTaskStatus()` | 任务状态轮询 | 每 2 秒自动刷新 |
| `useCancelTask()` | 取消任务 | 清理 Redis 取消标志 |

### 3.4 UI 组件

#### RepoForm — 添加仓库表单

| 功能 | 说明 |
|------|------|
| 名称输入 | 必填，trim 处理 |
| 路径输入 | 必填，trim 处理 |
| 自动分析 | 默认勾选的 checkbox |
| 409 处理 | 路径重复时显示"该路径已存在仓库" |
| 提交状态 | 按钮禁用 + 加载提示 |

#### RepoCard — 仓库卡片

| 功能 | 说明 |
|------|------|
| 状态 badge | 5 种状态颜色区分（待分析/分析中/已完成/失败/已取消） |
| 进度条 | 分析中显示百分比进度 + 当前步骤（扫描文件/解析代码/分析模块/存储结果） |
| 统计数据 | 文件数、代码行数、知识点数 |
| 开始分析 | 非分析中状态显示 |
| 取消分析 | 分析中状态显示，触发 P1-08 的 Redis 取消标志 |
| 删除确认 | 二次确认弹窗 |
| 409 处理 | 重复提交时显示"已有分析任务正在进行" |

#### RepoList — 仓库列表

| 功能 | 说明 |
|------|------|
| 状态筛选 | 全部/待分析/分析中/已完成/失败/已取消 |
| 网格布局 | 响应式 1/2/3 列 |
| 加载状态 | 加载动画 |
| 空状态 | 无数据提示 |

### 3.5 页面组装

`repositories/page.tsx` 整合所有组件：
- 页面标题 + "添加仓库"按钮
- 表单区域（弹窗式展示）
- 列表区域（带筛选器）

---

## 四、P1-08 优化项集成

### 4.1 细粒度取消

- **UI 触发**：点击"取消分析"按钮 → 调用 `cancelTask()` API
- **状态更新**：React Query 自动轮询任务状态，检测到 `cancelled` 状态后更新 UI
- **进度条**：分析过程中实时显示当前步骤和百分比

### 4.2 重复提交去重

- **表单层**：创建仓库时检测 409 → 提示"该路径已存在仓库"
- **卡片层**：提交分析时检测 409 → 提示"已有分析任务正在进行"
- **按钮禁用**：分析中状态隐藏"开始分析"按钮，显示"取消分析"按钮

---

## 五、文件变更清单

| 文件 | 操作 | 行数 | 说明 |
|------|------|------|------|
| [src/lib/api.ts](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/src/lib/api.ts) | 新建 | 87 | API 客户端层 |
| [src/hooks/use-repositories.ts](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/src/hooks/use-repositories.ts) | 新建 | 98 | React Query Hooks |
| [src/components/RepoForm.tsx](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/src/components/RepoForm.tsx) | 新建 | 132 | 添加仓库表单 |
| [src/components/RepoCard.tsx](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/src/components/RepoCard.tsx) | 新建 | 200 | 仓库卡片 |
| [src/components/RepoList.tsx](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/src/components/RepoList.tsx) | 新建 | 78 | 仓库列表 |
| [src/app/repositories/page.tsx](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/src/app/repositories/page.tsx) | 重写 | 36 | 页面组装 |
| src/components/.gitkeep | 删除 | - | 占位文件 |
| src/hooks/.gitkeep | 删除 | - | 占位文件 |
| src/store/.gitkeep | 删除 | - | 占位文件 |
| **后端 Schema 修复（3.0）** | | | |
| [schemas/repository.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/repository.py) | 修改 | +14 / -3 | `id`/`created_at`/`updated_at` → UUID/datetime + field_serializer |
| [schemas/file.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/file.py) | 修改 | +14 / -3 | 同上 |
| [schemas/knowledge.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/knowledge.py) | 修改 | +16 / -3 | 同上 |
| [schemas/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/analysis.py) | 修改 | +20 / -5 | `repository_id`/时间字段 → UUID/datetime + field_serializer |
| [tests/test_knowledge_points.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_knowledge_points.py) | 修改 | +10 / -10 | mock UUID 改用 `str(uuid4())` |
| [generated.ts](file:///c:/Users/Administrator/CodeInsightAi/packages/shared/src/generated.ts) | 重新生成 | — | OpenAPI spec 更新 |
| **后端 ORM 类型修正（3.1）** | | | |
| [models/repository.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/repository.py) | 修改 | - | `Mapped[DateTime]` → `Mapped[datetime]` (3 处) |
| [models/analysis_version.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/analysis_version.py) | 修改 | - | `Mapped[DateTime]` → `Mapped[datetime]` (4 处) |
| [models/knowledge_point.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/knowledge_point.py) | 修改 | - | `Mapped[DateTime]` → `Mapped[datetime]` (2 处) |
| [models/file.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/models/file.py) | 修改 | - | `Mapped[DateTime]` → `Mapped[datetime]` (2 处) |
| [api/versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/versions.py) | 修改 | - | 移除 `str()` 包装，传递原生 datetime |
| [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py) | 修改 | - | `_utcnow()` 返回 `datetime`；移除 `str()` 包装 |
| [tests/test_analysis_tasks.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_analysis_tasks.py) | 修改 | - | `str(result.repository_id) == repo_uuid` |
| [repositories/analysis_version.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/repositories/analysis_version.py) | 修改 | - | `session.add_all(...)` |

---

## 六、验证结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| ESLint | ✅ 通过 | 0 errors, 0 warnings |
| TypeScript | ✅ 通过 | `tsc --noEmit` 无错误 |
| Tailwind CSS | ✅ 通过 | v4 配置正确 |
| React Query | ✅ 通过 | 缓存、刷新、失效逻辑正确 |
| **后端 CI** | | |
| Ruff check | ✅ 通过 | All checks passed! |
| mypy | ✅ 通过 | Success: no issues found in 33 source files |
| pytest | ✅ 通过 | 96 passed, 11 warnings |

---

## 七、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 文件列表页 | P2-01 | 展示仓库下文件列表 |
| 知识点详情页 | P2-03 | 展示知识点详情和代码片段 |
| 搜索页面 | P3-07 | Meilisearch 全文搜索 |
| Toast 通知组件 | P4-01 | 全局通知（替代 inline 错误提示） |
| 前端单元测试 | P5-01 | 组件和 hooks 的单元测试 |
