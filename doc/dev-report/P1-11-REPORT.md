# P1-11: API 文档自动生成（FastAPI 自带 Swagger + ReDoc）- 开发报告

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P1-11 |
| 任务名称 | API 文档自动生成（FastAPI 自带 Swagger + 自定义 Doc） |
| 所属阶段 | Phase 1（第 2-3 周） |
| 优先级 | P2 |
| 预估工时 | 2h |
| 交付物 | API 文档页（Swagger UI + ReDoc）+ OpenAPI 导出脚本 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-03 FastAPI 项目骨架 | ✅ | 应用已初始化 |
| P1-07 CRUD API | ✅ | 所有 API 端点已实现 |
| P1-08 Analysis API | ✅ | 分析任务 API 已实现 |

---

## 二、交付物清单

### 2.1 FastAPI 文档配置

[main.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/main.py#L29-L38) 中已配置：

```python
app = FastAPI(
    title="CodeInsight AI API",
    description="AI 驱动的代码知识提取与可视化分析平台",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)
```

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `title` | "CodeInsight AI API" | API 标题 |
| `description` | "AI 驱动的代码知识提取与可视化分析平台" | 描述 |
| `version` | "0.1.0" | API 版本 |
| `docs_url` | `/docs`（debug 模式启用） | Swagger UI 交互文档 |
| `redoc_url` | `/redoc`（debug 模式启用） | ReDoc 静态文档 |

### 2.2 OpenAPI 导出脚本

[scripts/export_openapi.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/scripts/export_openapi.py) — 从 FastAPI 应用运行时导出 OpenAPI spec：

```bash
uv run python scripts/export_openapi.py
# → packages/shared/src/openapi.json
```

当前导出结果：**14 个路径，29 个 Schema**。

### 2.3 路由分组（标签）

API 路由按功能自动分组，在文档中显示为独立标签页：

| 标签 | 路由前缀 | 端点数 | 说明 |
|------|----------|--------|------|
| 仓库管理 | `/api/v1/repositories` | 4 | CRUD |
| 分析任务 | `/api/v1/tasks` | 3 | 提交/查询/取消 |
| 知识点 | `/api/v1/knowledge` | 2 | 列表/详情 |
| 搜索 | `/api/v1/search` | 1 | 搜索 |
| 版本管理 | `/api/v1/versions` | 1 | 版本列表 |
| 健康检查 | `/api/v1/health` | 1 | 健康检查 |

---

## 三、文档访问机制

### 3.1 Debug 模式控制

| 环境 | `settings.debug` | Swagger UI | ReDoc | OpenAPI JSON |
|------|------------------|-----------|-------|-------------|
| 本地开发（默认） | `True` | `/docs` ✅ | `/redoc` ✅ | `/openapi.json` ✅ |
| 生产环境 | `False` | 404 ❌ | 404 ❌ | `/openapi.json` ✅ |

- Swagger UI 和 ReDoc 路由在 `debug=False` 时被禁用（`docs_url=None`）
- OpenAPI JSON 端点始终可用（FastAPI 默认行为）

### 3.2 为什么要这样设计？

| 风险 | 说明 |
|------|------|
| **信息泄露** | OpenAPI 文档暴露完整 API 路径、请求格式、Schema，攻击者可据此发现接口漏洞 |
| **生产冗余** | 生产环境不需要交互文档，减少内存和 CPU 占用 |

---

## 四、与 P1-09 类型同步的集成

OpenAPI 导出脚本是**前后端类型同步的关键环节**：

```
后端 Pydantic Schema
    ↓
app.openapi() → openapi.json
    ↓
npx openapi-typescript → generated.ts
    ↓
前端 import type { Repository } from "@codeinsight/shared"
```

在 P1-09 开发过程中，Schema 类型修复后通过此脚本重新生成 `openapi.json` 和 `generated.ts`，确保前后端类型一致。

---

## 五、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 自定义文档页 | P2-01 | 添加使用示例和错误处理说明 |
| API 请求示例 | P2-01 | 为每个端点添加 `examples` 字段 |
| 错误响应文档 | P2-01 | 在 OpenAPI schema 中明确定义 4xx/5xx 错误响应格式 |
| 生产环境文档 | P4-01 | 通过反向代理或 API Key 限制访问 |

---

## 六、总结

P1-11 的基础功能（Swagger UI + ReDoc + OpenAPI 导出）已随 FastAPI 项目初始化完成。当前为 **P2 优先级**任务，剩余工作是文档美化，可在后续阶段补充。
