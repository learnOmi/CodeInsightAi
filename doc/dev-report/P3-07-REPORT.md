# P3-07 实施报告：Meilisearch 索引构建

## 基本信息

| 项目 | 内容 |
|------|------|
| **任务编号** | P3-07 |
| **任务名称** | Meilisearch 索引构建：知识点标题/标签/简介全文索引 |
| **实施日期** | 2026-07-19 |
| **工时** | 6h（与计划一致） |
| **当前状态** | 100% 完成，全部 CI 通过 |

---

## 变更摘要

### 新建文件

| 文件 | 说明 |
|------|------|
| `codeinsight/services/meilisearch_client.py` | Meilisearch 全文搜索客户端，封装索引管理、文档同步、搜索操作 |

### 修改文件

| 文件 | 变更类型 | 说明 |
|------|:--------:|------|
| `pyproject.toml` | 修改 | 新增 `meilisearch>=1.12.0` 依赖 |
| `codeinsight/main.py` | 修改 | 应用启动时初始化 Meilisearch 索引 |
| `codeinsight/api/search.py` | 修改 | 新增 `GET /search/knowledge-points` 全文搜索端点 |
| `codeinsight/tasks/analysis_orchestrator.py` | 修改 | 知识点创建后同步到 Meilisearch 索引 |
| `codeinsight/repositories/knowledge_point.py` | 修改 | 知识点更新/删除时同步到 Meilisearch 索引 |

---

## 详细实现

### 1. Meilisearch 客户端服务

**新建** `services/meilisearch_client.py`，提供完整封装：

| 方法 | 说明 |
|------|------|
| `ensure_index()` | 确保索引存在并配置搜索属性（幂等操作） |
| `add_document(kp)` | 添加或更新单个知识点文档 |
| `add_documents(kps)` | 批量添加知识点文档 |
| `delete_document(point_id)` | 从索引中删除知识点文档 |
| `search(query, ...)` | 全文搜索，支持筛选、排序、分页 |

**索引配置**：

| 属性 | 配置值 |
|------|--------|
| `primaryKey` | `id` |
| `searchableAttributes` | `title`, `description`, `tags` |
| `filterableAttributes` | `category`, `repository_id`, `version`, `tags` |
| `sortableAttributes` | `confidence`, `created_at` |
| `displayedAttributes` | `id`, `title`, `description`, `category`, `category_name`, `tags`, `confidence`, `repository_id`, `version`, `created_at` |

**设计特点**：
- 单例模式，确保全局复用同一个客户端实例
- 懒初始化，客户端实例在首次访问时创建
- 所有同步操作使用 try/except 包裹，失败仅记录日志，不阻塞主流程

### 2. 应用启动时初始化索引

**`main.py` lifespan** 中新增：

```python
# 初始化 Meilisearch 索引
meili_client = MeiliSearchClient()
meili_client.ensure_index()
```

异常时仅记录 warning，不阻止应用启动。

### 3. 知识点全文搜索 API

**新增** `GET /api/v1/search/knowledge-points` 端点：

| 参数 | 类型 | 说明 |
|------|------|------|
| `q` | string | 搜索关键词（必填） |
| `repository_id` | UUID | 按仓库筛选（可选） |
| `category` | string | 按分类筛选（可选） |
| `limit` | int | 返回条数上限，默认 20，最大 100 |
| `offset` | int | 偏移量，默认 0 |

**返回格式**：
```json
{
  "hits": [...],
  "total": 42,
  "query": "factory"
}
```

### 4. 知识点创建/更新/删除时同步

**创建时**（`analysis_orchestrator.py`）：
```python
# 知识点保存到 PostgreSQL 后，同步到 Meilisearch
meili_client = MeiliSearchClient()
meili_client.add_documents(final_state["knowledge_points"])
```

**更新时**（`knowledge_point.py`）：
```python
# update() 方法中，flush 后同步到 Meilisearch
meili_client.add_document({...})
```

**删除时**（`knowledge_point.py`）：
```python
# delete() 方法中，flush 后从 Meilisearch 删除
meili_client.delete_document(point_id)
```

**同步策略**：
- 使用 lazy import 避免循环依赖
- 失败仅记录 warning，不阻塞主流程
- 单条操作幂等，可安全重试

---

## CI 验证

| 检查项 | 结果 |
|--------|:----:|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 159 files already formatted |
| mypy | ✅ Success: no issues found in 149 source files |
| pytest | ✅ **591 passed, 1 skipped** (73.16s) |

---

## 数据流

```
AnalysisOrchestrator._run_async()
        │
        ├── AgentGraph.run() → knowledge_points
        ├── EmbeddingClient.embed_single() → pgvector
        ├── KnowledgePointDAO.create() → PostgreSQL
        │
        └── MeiliSearchClient.add_documents() → Meilisearch 索引
                │
                └── GET /api/v1/search/knowledge-points?q=xxx
                        │
                        └── Meilisearch 全文搜索 → 毫秒级响应
```

## 变更记录

| 文件 | 行数 | 说明 |
|------|:----:|------|
| `services/meilisearch_client.py` | +195 | 新建 Meilisearch 客户端服务 |
| `pyproject.toml` | +1 | 新增 `meilisearch>=1.12.0` 依赖 |
| `main.py` | +9 | 启动时初始化索引 |
| `api/search.py` | +40 | 新增知识点搜索端点 |
| `tasks/analysis_orchestrator.py` | +10 | 同步知识点到 Meilisearch |
| `repositories/knowledge_point.py` | +20 | 更新/删除时同步 |