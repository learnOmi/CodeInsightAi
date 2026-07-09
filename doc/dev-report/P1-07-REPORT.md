# P1-07: 仓库管理 CRUD API + 单元测试 - 开发报告

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P1-07 |
| 任务名称 | 仓库/文件/知识点/版本管理 CRUD API（DAO 层 + API 端点 + 单元测试） |
| 所属阶段 | Phase 1 |
| 优先级 | P0 |
| 预估工时 | 24h |
| 交付物 | REST API + 单元测试 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-03 FastAPI 项目骨架 | ✅ | 已有 `main.py`、健康检查端点 |
| P1-05 SQLAlchemy ORM 模型 | ✅ | RepositoryModel/FileModel/KnowledgePointModel/AnalysisVersionModel 已定义 |
| P1-03 Pydantic Schema | ✅ | 所有 Schema 已定义 |

---

## 二、修复 API/Schemas/Models 对齐问题

在实施 P1-07 之前，发现多个模块的 API 参数类型与 ORM Model 不一致，先行修复。

### 2.1 修复清单

| 模块 | 问题 | 修复方式 |
|------|------|---------|
| repositories | `repository_id: str` 应为 `UUID` | 改为 `from uuid import UUID` |
| repositories | 列表缺分页参数 | 添加 `skip`/`limit` Query 参数 |
| repositories | DELETE 缺 response_model | 添加 `DeleteResponse` 响应体 |
| knowledge | `point_id`/`repository_id` 用 `str` | 改为 `UUID` |
| versions | `repository_id` 用 `int` | 改为 `UUID`；switch/rollback 添加 `version` 查询参数 |
| analysis | `repository_id` 用 `str` | 改为 `UUID` |
| schemas/knowledge | KnowledgePoint 缺 `embedding` | 添加 `embedding: list[float] \| None` |
| schemas/analysis | AnalysisVersion 缺字段 | 补齐 `analyzed_files`、`started_at`、`error_message` |

### 2.2 修复后的 API 签名对比

**repositories.py**：
```python
# 修复前
async def get_repository(repository_id: str):
async def list_repositories():

# 修复后
async def get_repository(repository_id: UUID):
async def list_repositories(skip: int = Query(default=0), limit: int = Query(default=100)):
```

**versions.py**：
```python
# 修复前
async def list_versions(repository_id: int):
async def switch_version(repository_id: int):

# 修复后
async def list_versions(repository_id: UUID):
async def switch_version(repository_id: UUID, version: str = Query(...)):
```

---

## 三、创建 DAO/Repository 层

### 3.1 文件结构

```
codeinsight/repositories/
├── __init__.py                      # 包初始化，导出所有 DAO
├── repository.py                    # RepositoryDAO 类（仓库 CRUD）
├── file.py                          # FileDAO 类（文件 CRUD）
├── knowledge_point.py               # KnowledgePointDAO 类（知识点 CRUD）
└── analysis_version.py              # AnalysisVersionDAO 类（版本 CRUD）
```

### 3.2 DAO 设计

**RepositoryDAO** — 仓库 CRUD：
```python
class RepositoryDAO:
    async def create(db, data) -> RepositoryModel
    async def get_by_id(db, repository_id) -> RepositoryModel | None
    async def list(db, skip, limit) -> list[RepositoryModel]
    async def update(db, repository_id, data) -> RepositoryModel
    async def delete(db, repository_id) -> bool
    async def exists_by_path(db, path) -> bool  # 唯一约束冲突检测
```

**FileDAO** — 文件 CRUD：
```python
class FileDAO:
    async def create(db, data) -> FileModel
    async def get_by_id(db, file_id) -> FileModel | None
    async def list_by_repository(db, repository_id, skip, limit) -> list[FileModel]
    async def update(db, file_id, data) -> FileModel
    async def delete(db, file_id) -> bool
    async def get_by_content_hash(db, repository_id, content_hash) -> FileModel | None
```

**KnowledgePointDAO** — 知识点 CRUD：
```python
class KnowledgePointDAO:
    async def create(db, data) -> KnowledgePointModel
    async def get_by_id(db, point_id) -> KnowledgePointModel | None
    async def list(db, repository_id, version, category, tag, skip, limit, sort_by, sort_order) -> list[KnowledgePointModel]
    async def count(db, repository_id, version, category) -> int
    async def update(db, point_id, data) -> KnowledgePointModel
    async def delete(db, point_id) -> bool
```

**AnalysisVersionDAO** — 分析版本 CRUD：
```python
class AnalysisVersionDAO:
    async def create(db, data) -> AnalysisVersionModel
    async def get_by_id(db, version_id) -> AnalysisVersionModel | None
    async def list_by_repository(db, repository_id, skip, limit) -> list[AnalysisVersionModel]
    async def get_by_version_tag(db, repository_id, version_tag) -> AnalysisVersionModel | None
    async def update(db, version_id, data) -> AnalysisVersionModel
    async def delete(db, version_id) -> bool
```

### 3.3 依赖注入模式

```python
def get_repository_dao() -> RepositoryDAO:
    return RepositoryDAO()

@router.post("", response_model=Repository, status_code=201)
async def create_repository(
    request: RepositoryCreate,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: RepositoryDAO = Depends(get_repository_dao),  # noqa: B008
):
    ...
```

**优势**：测试中可通过 `MagicMock(spec=RepositoryDAO)` 轻松 mock DAO。

---

## 四、实现 API 端点

### 4.1 仓库管理端点（5 个）— [api/repositories.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/repositories.py)

| 端点 | 方法 | 路径 | 状态码 | 说明 |
|------|------|------|--------|------|
| 创建仓库 | POST | `/api/v1/repositories` | 201 | 含路径重复检测（409） |
| 仓库列表 | GET | `/api/v1/repositories?skip=0&limit=100` | 200 | 支持分页 |
| 获取仓库 | GET | `/api/v1/repositories/{repository_id}` | 200/404 | UUID 路径参数 |
| 更新仓库 | PUT | `/api/v1/repositories/{repository_id}` | 200/404 | 部分更新 |
| 删除仓库 | DELETE | `/api/v1/repositories/{repository_id}` | 200/404 | 级联删除 |

### 4.2 文件管理端点（5 个）— [api/files.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/files.py)

| 端点 | 方法 | 路径 | 状态码 | 说明 |
|------|------|------|--------|------|
| 创建文件 | POST | `/api/v1/files` | 201 | 添加新文件 |
| 获取文件 | GET | `/api/v1/files/{file_id}` | 200/404 | UUID 路径参数 |
| 按哈希查找 | GET | `/api/v1/files/by-hash/{content_hash}?repository_id=` | 200 | 增量检测用 |
| 更新文件 | PUT | `/api/v1/files/{file_id}` | 200/404 | 部分更新 |
| 删除文件 | DELETE | `/api/v1/files/{file_id}` | 200/404 | 删除文件记录 |

### 4.3 知识点管理端点（3 个）— [api/knowledge.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/knowledge.py)

| 端点 | 方法 | 路径 | 状态码 | 说明 |
|------|------|------|--------|------|
| 知识点列表 | GET | `/api/v1/knowledge-points?repository_id=&page=1&page_size=20` | 200 | 分页+筛选+排序 |
| 获取知识点 | GET | `/api/v1/knowledge-points/{point_id}` | 200/404 | UUID 路径参数 |
| 知识点统计 | GET | `/api/v1/repositories/{repository_id}/knowledge-stats` | 200 | 分类/置信度分布 |

### 4.4 版本管理端点（3 个）— [api/versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/versions.py)

| 端点 | 方法 | 路径 | 状态码 | 说明 |
|------|------|------|--------|------|
| 版本列表 | GET | `/api/v1/repositories/{repository_id}/versions` | 200 | 含 is_current 标记 |
| 切换版本 | POST | `/api/v1/repositories/{repository_id}/switch-version?version=` | 200 | 更新 current_version |
| 回滚版本 | POST | `/api/v1/repositories/{repository_id}/rollback?version=` | 200 | 恢复到历史版本 |

### 4.5 错误处理

```python
# 路径重复 → 409 Conflict
if await dao.exists_by_path(db, request.path):
    raise HTTPException(status_code=409, detail=f"Repository path already exists: {request.path}")

# 仓库不存在 → 404 Not Found
if repo is None:
    raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")
```

---

## 五、全局异常处理器

在 [main.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/main.py) 中注册自定义异常处理器：

```python
@app.exception_handler(RepositoryPathExistsError)
async def repository_path_exists_handler(request: Request, exc: RepositoryPathExistsError):
    return JSONResponse(status_code=409, content={"detail": f"Repository path already exists: {exc.path}"})

@app.exception_handler(RepositoryNotFoundError)
async def repository_not_found_handler(request: Request, exc: RepositoryNotFoundError):
    return JSONResponse(status_code=404, content={"detail": f"Repository not found: {exc.repository_id}"})
```

---

## 六、编写单元测试

### 6.1 测试策略

- **Mock DAO 层**：使用 `unittest.mock.AsyncMock` + `MagicMock(spec=RepositoryDAO)`
- **直接测试 API 函数**：绕过 TestClient，直接调用异步函数并传入 mock 对象
- **覆盖所有分支**：成功路径 + 错误路径（404、409）

### 6.2 测试用例清单（73 个）

#### 仓库 DAO/API 测试（21 个）— [tests/test_repositories.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_repositories.py)

| 类别 | 测试数 | 覆盖场景 |
|------|--------|---------|
| DAO | 10 | create, get_by_id(found/not found), list, list_pagination, update, delete(success/not found), exists_by_path(true/false) |
| API | 11 | create(success/duplicate), get(found/not found), list(empty), update(success/not found), delete(success/not found) |

#### 文件 DAO/API 测试（19 个）— [tests/test_files.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_files.py)

| 类别 | 测试数 | 覆盖场景 |
|------|--------|---------|
| DAO | 10 | create, get_by_id(found/not found), list_by_repository(empty), update, delete(success/not found), get_by_content_hash(found/not found) |
| API | 9 | create, get(found/not found), get_by_hash(found/not found), update(success/not found), delete(success/not found) |

#### 知识点 DAO/API 测试（16 个）— [tests/test_knowledge_points.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_knowledge_points.py)

| 类别 | 测试数 | 覆盖场景 |
|------|--------|---------|
| DAO | 10 | create, get_by_id(found/not found), list, list_with_filters, count, count_with_category, update, delete(success/not found) |
| API | 6 | list_knowledge_points(category filter/pagination), get_knowledge_point(found/not found), get_knowledge_stats |

#### 分析版本 DAO/API 测试（17 个）— [tests/test_analysis_versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_analysis_versions.py)

| 类别 | 测试数 | 覆盖场景 |
|------|--------|---------|
| DAO | 10 | create, get_by_id(found/not found), list_by_repository(empty), get_by_version_tag(found/not found), update, delete(success/not found) |
| API | 7 | list_versions(no current), switch_version(success/repo not found/target not found), rollback_version(success/repo not found) |

### 6.3 测试结果

```
======================== 73 passed, 5 warnings in ~1.0s =========================
```

---

## 七、技术细节

### 7.1 Pydantic Schema ↔ ORM Model 转换

```python
# ORM Model (RepositoryModel)
class RepositoryModel(Base):
    id = Column(UUID, primary_key=True)
    name = Column(String)
    ...

# Pydantic Schema (Repository)
class Repository(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # ← 关键配置
    id: str  # ← Pydantic 自动将 UUID → str
    name: str
    ...
```

Pydantic 的 `from_attributes=True` 使得 API 端点直接返回 ORM 模型即可自动序列化。

### 7.2 UUID 类型处理

| 层级 | 类型 | 说明 |
|------|------|------|
| API 参数 | `UUID` | FastAPI 自动解析路径参数 |
| ORM Column | `Column(UUID)` | SQLAlchemy 原生 UUID 类型 |
| Pydantic 输出 | `str` | 通过 `alias_generator=to_camel` 转为 camelCase |

---

## 八、文件变更清单

| 文件 | 操作 | 行数变化 |
|------|------|---------|
| [api/repositories.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/repositories.py) | 重写 | +108 / -52 |
| [api/files.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/files.py) | 新建 | +104 |
| [api/knowledge.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/knowledge.py) | 重写 | +118 / -2 |
| [api/versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/versions.py) | 重写 | +120 / -5 |
| [repositories/__init__.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/repositories/__init__.py) | 新建 | +9 |
| [repositories/repository.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/repositories/repository.py) | 新建 | +136 |
| [repositories/file.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/repositories/file.py) | 新建 | +129 |
| [repositories/knowledge_point.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/repositories/knowledge_point.py) | 新建 | +163 |
| [repositories/analysis_version.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/repositories/analysis_version.py) | 新建 | +136 |
| [exceptions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/exceptions.py) | 新建 | +21 |
| [schemas/file.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/file.py) | 新建 | +48 |
| [schemas/__init__.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/__init__.py) | 修改 | +5 |
| [main.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/main.py) | 修改 | +18 |
| [tests/test_repositories.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_repositories.py) | 新建 | +343 |
| [tests/test_files.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_files.py) | 新建 | +340 |
| [tests/test_knowledge_points.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_knowledge_points.py) | 新建 | +314 |
| [tests/test_analysis_versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/tests/test_analysis_versions.py) | 新建 | +362 |
| [api/knowledge.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/knowledge.py) | 修改 | +3 / -3 |
| [api/versions.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/versions.py) | 修改 | +15 / -5 |
| [api/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/api/analysis.py) | 修改 | +2 / -1 |
| [schemas/knowledge.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/knowledge.py) | 修改 | +1 |
| [schemas/analysis.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/schemas/analysis.py) | 修改 | +3 |

### Bug 修复（测试阶段发现）

| 问题 | 修复方式 |
|------|---------|
| `delete_file` 返回 `BaseModel()` 导致 Pydantic 崩溃 | 新增 `DeleteFileResponse` 响应模型 |
| 旧测试文件 `test_knowledge.py`/`test_versions.py` 与 P1-07 API 签名不兼容 | 删除旧文件，使用新测试文件 |

---

## 九、验证结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Ruff lint | ✅ 通过 | `All checks passed!` |
| pytest | ✅ 通过 | **73 passed, 0 failed** |
| API 类型对齐 | ✅ 完成 | UUID 统一，分页参数补齐 |
| Pydantic 序列化 | ✅ 完成 | 使用 `@dataclass` Fake 模型兼容 `from_attributes=True` |

---

## 十、待后续工作

| 任务 | 关联 P1 任务 | 说明 |
|------|-------------|------|
| 集成测试 | P5-02 | 当前为 Mock 测试，Phase 5 补充真实 DB 容器测试 |

---

**报告生成时间**：2026-07-10
**作者**：CodeInsight AI Agent
**状态**：✅ 完成
