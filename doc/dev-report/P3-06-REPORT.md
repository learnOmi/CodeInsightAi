# P3-06 实施报告：Embedding 向量化

## 基本信息

| 项目 | 内容 |
|------|------|
| **任务编号** | P3-06 |
| **任务名称** | Embedding 向量化：代码片段 → 向量 → pgvector 存储 |
| **实施日期** | 2026-07-19 |
| **工时** | 10h（与计划一致） |
| **当前状态** | 100% 完成，全部 CI 通过 |

---

## 变更摘要

### 修改/新建文件

| 文件 | 变更类型 | 说明 |
|------|:--------:|------|
| `codeinsight/config.py` | 修改 | `embedding_dimension` 768 → **1536**（对齐 text-embedding-3-small） |
| `codeinsight/tasks/analysis_orchestrator.py` | 修改 | 分析管线集成 `EmbeddingClient`，保存前生成向量 |
| `alembic/versions/20260719_008_sync_embedding_dimension.py` | **新建** | 迁移：IVFFlat → **HNSW** 索引 |
| `tests/test_llm_client.py` | 修改 | 新增 3 个测试：store、store rollback、DAO with embedding |

---

## 详细实现

### 1. 统一 `embedding_dimension` 为 1536

**变更**：[config.py:118](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/config.py#L118)

| 字段 | 旧值 | 新值 | 说明 |
|------|:----:|:----:|------|
| `embedding_dimension` | 768 | **1536** | 对齐 `text-embedding-3-small` 输出维度 |

**修复的维度不一致问题**：

| 位置 | 旧值 | 新值 | 对齐 |
|------|:----:|:----:|:----:|
| `config.py` | 768 | **1536** | ✅ |
| ORM `Vector(settings.embedding_dimension)` | 768 | **1536** | ✅ |
| Alembic migration `vector(1536)` | 1536 | 1536 | ✅ 不变 |
| `text-embedding-3-small` 输出 | 1536 | 1536 | ✅ |

### 2. 分析管线集成 Embedding 调用

**变更**：[analysis_orchestrator.py:1456](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/tasks/analysis_orchestrator.py#L1456-L1475)

```python
# 新增：创建 EmbeddingClient（复用已有的 LLMClient 实例）
embedding_client = EmbeddingClient(llm_client=llm_client)

for kp in final_state["knowledge_points"]:
    try:
        # 新增：生成嵌入向量
        embed_text = f"{kp['title']}\n{kp['description']}"
        embedding = await embedding_client.embed_single(embed_text)

        kp_data = {
            # ... 原有字段 ...
            "embedding": embedding,  # 新增：嵌入向量
        }
        await kp_dao.create(shared_db, kp_data)
```

**嵌入文本策略**：`title + "\n" + description` — 标题+描述构成语义完整、长度适中的向量化输入。

### 3. Alembic 迁移：HNSW 索引

**变更**：新建迁移 `20260719_008_sync_embedding_dimension`

| 变更 | 旧值 | 新值 | 说明 |
|------|------|------|------|
| 索引类型 | **IVFFlat** (`lists=100`) | **HNSW** (`m=16, ef_construction=64`) | 更高召回率，无需训练步骤 |

**HNSW 优势**：
- 无需训练步骤（IVFFlat 需要 k-means 聚类训练）
- 小到中等规模数据集召回率更高
- 适合 codeinsight 的典型使用场景

### 4. 测试覆盖

**新增 3 个测试用例**：

| 测试方法 | 覆盖场景 |
|----------|---------|
| `TestEmbeddingClient.test_store` | EmbeddingClient.store() 存储向量 |
| `TestEmbeddingClient.test_store_rollback_on_failure` | 存储失败时回滚 |
| `TestKnowledgePointDAOWithEmbedding.test_create_with_embedding` | DAO create 含 embedding 字段 |

---

## CI 验证

| 检查项 | 结果 |
|--------|:----:|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 158 files already formatted |
| mypy | ✅ Success: no issues found in 148 source files |
| pytest | ✅ **591 passed, 1 skipped** (+3 新用例) |

---

## 架构说明

### 数据流

```
AnalysisOrchestrator._run_async()
        │
        ├── LLMClient() → AgentGraph.run() → knowledge_points
        │
        ├── EmbeddingClient(llm_client=llm_client)
        │       │
        │       └── embed_single(title + "\n" + description)
        │               │
        │               └── LLMClient.embed([text])
        │                       │
        │                       └── litellm.aembedding(model="text-embedding-3-small")
        │
        └── KnowledgePointDAO.create(shared_db, kp_data)
                │
                └── KnowledgePointModel(embedding=vector)
                        │
                        └── pgvector HNSW 索引 → 余弦相似度搜索
```

### 现有基础设施（无需变更）

| 组件 | 位置 | 说明 |
|------|------|------|
| `LLMClient.embed()` | `llm/client.py:362` | 批量嵌入，支持 semaphore 并发控制 |
| `EmbeddingClient` | `embedding/client.py` | embed() / embed_single() / store() |
| ORM 模型 | `models/knowledge_point.py:48` | `Vector(1536)` + HNSW 索引 |
| Pydantic Schema | `schemas/knowledge.py:139` | `embedding: list[float] \| None` |
| Docker pgvector | `docker-compose.yml` | `ankane/pgvector:latest` |

---

## 变更记录

| 文件 | 行数变动 | 说明 |
|------|:--------:|------|
| `config.py` | +1/-1 | `embedding_dimension` 768 → 1536 |
| `tasks/analysis_orchestrator.py` | +5 | 导入 EmbeddingClient + 嵌入调用 |
| `alembic/versions/20260719_008_sync_embedding_dimension.py` | +52 | 新建迁移（IVFFlat → HNSW） |
| `tests/test_llm_client.py` | +9/-1 | 新增 3 个测试（import + 测试代码） |