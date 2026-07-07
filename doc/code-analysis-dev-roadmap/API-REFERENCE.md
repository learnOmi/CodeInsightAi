# CodeInsight API — 接口文档

> **Base URL**: `http://localhost:8000` (开发环境) / `https://api.codeinsight.ai` (生产环境)
> **版本**: v1
> **认证**: Bearer Token (JWT)
> **Content-Type**: `application/json`

---

## 目录

1. [认证接口](#1-认证接口)
2. [仓库管理接口](#2-仓库管理接口)
3. [分析任务接口](#3-分析任务接口)
4. [知识点查询接口](#4-知识点查询接口)
5. [搜索接口](#5-搜索接口)
6. [版本管理接口](#6-版本管理接口)
7. [SSE 实时推送接口](#7-sse-实时推送接口)
8. [错误响应格式](#8-错误响应格式)
9. [速率限制](#9-速率限制)

---

## 通用说明

### 请求头

| Header | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `Authorization` | string | 否 | Bearer token，格式：`Bearer <token>` |
| `Content-Type` | string | 是 | `application/json` |
| `X-Request-ID` | string | 否 | 请求追踪 ID，用于日志关联 |

### 分页参数

所有列表接口支持分页，使用以下查询参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | integer | 1 | 页码，从 1 开始 |
| `page_size` | integer | 20 | 每页数量，范围 1-100 |

### 通用响应结构

```json
{
  "success": true,
  "data": {},
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-07-07T10:30:00Z"
  }
}
```

---

## 1. 认证接口

### 1.1 注册

**POST** `/api/v1/auth/register`

注册新用户。

**请求体：**

```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "SecurePass123!"
}
```

**响应 201 Created：**

```json
{
  "success": true,
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "john_doe",
    "email": "john@example.com",
    "created_at": "2026-07-07T10:00:00Z"
  }
}
```

### 1.2 登录

**POST** `/api/v1/auth/login`

**请求体：**

```json
{
  "username": "john_doe",
  "password": "SecurePass123!"
}
```

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "john_doe"
    }
  }
}
```

### 1.3 刷新 Token

**POST** `/api/v1/auth/refresh`

**请求体：**

```json
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4"
}
```

---

## 2. 仓库管理接口

### 2.1 添加仓库

**POST** `/api/v1/repositories`

添加一个新的代码仓库。

**认证**: 需要 Bearer Token

**请求体：**

```json
{
  "name": "my-awesome-project",
  "path": "/home/user/repos/my-awesome-project",
  "auto_analyze": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 仓库名称，长度 1-100 |
| `path` | string | 是 | 本地代码仓库绝对路径 |
| `auto_analyze` | boolean | 否 | 添加后立即开始分析，默认 `true` |

**响应 201 Created：**

```json
{
  "success": true,
  "data": {
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "my-awesome-project",
    "path": "/home/user/repos/my-awesome-project",
    "status": "pending",
    "current_version": null,
    "created_at": "2026-07-07T10:00:00Z"
  },
  "meta": {
    "task_id": "celery-task-uuid-12345",
    "message": "分析任务已提交"
  }
}
```

**错误响应 400 Bad Request：**

```json
{
  "success": false,
  "error": {
    "code": "INVALID_PATH",
    "message": "仓库路径不存在或无读取权限",
    "details": {
      "provided_path": "/invalid/path"
    }
  }
}
```

### 2.2 获取仓库列表

**GET** `/api/v1/repositories`

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | integer | 否 | 页码，默认 1 |
| `page_size` | integer | 否 | 每页数量，默认 20 |
| `status` | string | 否 | 按状态筛选：`pending` / `analyzing` / `completed` / `failed` |

**响应 200 OK：**

```json
{
  "success": true,
  "data": [
    {
      "repository_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "my-awesome-project",
      "path": "/home/user/repos/my-awesome-project",
      "status": "completed",
      "current_version": "v20260707-a3f2b1c",
      "knowledge_points_count": 128,
      "last_analyzed_at": "2026-07-07T10:30:00Z",
      "created_at": "2026-07-06T08:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

### 2.3 获取仓库详情

**GET** `/api/v1/repositories/{repository_id}`

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `repository_id` | string (UUID) | 仓库 ID |

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "my-awesome-project",
    "path": "/home/user/repos/my-awesome-project",
    "status": "completed",
    "current_version": "v20260707-a3f2b1c",
    "language_distribution": {
      "Python": 45,
      "JavaScript": 30,
      "TypeScript": 15,
      "Other": 10
    },
    "file_count": 523,
    "line_count": 48200,
    "knowledge_points_count": 128,
    "versions": [
      {
        "version": "v20260707-a3f2b1c",
        "status": "completed",
        "total_files": 523,
        "knowledge_points_count": 128,
        "created_at": "2026-07-07T10:30:00Z"
      },
      {
        "version": "v20260706-b2e1a0d",
        "status": "completed",
        "total_files": 510,
        "knowledge_points_count": 115,
        "created_at": "2026-07-06T08:00:00Z"
      }
    ],
    "created_at": "2026-07-06T08:00:00Z",
    "updated_at": "2026-07-07T10:30:00Z"
  }
}
```

### 2.4 删除仓库

**DELETE** `/api/v1/repositories/{repository_id}`

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `repository_id` | string (UUID) | 仓库 ID |

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "message": "仓库及其所有分析数据已删除"
  }
}
```

**错误响应 404 Not Found：**

```json
{
  "success": false,
  "error": {
    "code": "REPOSITORY_NOT_FOUND",
    "message": "仓库不存在",
    "details": {
      "repository_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  }
}
```

---

## 3. 分析任务接口

### 3.1 提交分析任务

**POST** `/api/v1/repositories/{repository_id}/analyze`

手动触发仓库分析（通常在添加仓库时已自动触发，此接口用于重新分析）。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `repository_id` | string (UUID) | 仓库 ID |

**请求体：**

```json
{
  "mode": "full",
  "agents": ["design_pattern", "architecture", "algorithm", "engineering_tips", "domain_knowledge"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | string | 否 | 分析模式：`full`（全量）/ `incremental`（增量），默认 `full` |
| `agents` | string[] | 否 | 启用的 Agent 列表，默认全部启用 |

**响应 202 Accepted：**

```json
{
  "success": true,
  "data": {
    "task_id": "celery-task-uuid-12345",
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",
    "mode": "full",
    "status": "pending",
    "submitted_at": "2026-07-07T10:00:00Z"
  }
}
```

**错误响应 409 Conflict：**

```json
{
  "success": false,
  "error": {
    "code": "TASK_ALREADY_RUNNING",
    "message": "该仓库已有正在运行的分析任务",
    "details": {
      "existing_task_id": "celery-task-uuid-existing"
    }
  }
}
```

### 3.2 查询任务状态

**GET** `/api/v1/tasks/{task_id}`

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | Celery 任务 ID |

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "task_id": "celery-task-uuid-12345",
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "processing",
    "progress": {
      "current_step": "analyzing_modules",
      "percent": 65,
      "files_processed": 340,
      "files_total": 523,
      "knowledge_points_found": 87
    },
    "started_at": "2026-07-07T10:00:00Z",
    "estimated_completion": "2026-07-07T10:05:00Z"
  }
}
```

**状态枚举：**

| 状态 | 说明 |
|------|------|
| `pending` | 排队等待中 |
| `scanning` | 正在扫描代码文件 |
| `parsing` | 正在解析 AST |
| `analyzing_modules` | 正在运行 AI Agent |
| `storing` | 正在存储结果 |
| `completed` | 分析完成 |
| `failed` | 分析失败 |
| `cancelled` | 已取消 |

### 3.3 取消分析任务

**POST** `/api/v1/tasks/{task_id}/cancel`

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | Celery 任务 ID |

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "task_id": "celery-task-uuid-12345",
    "status": "cancelled",
    "message": "任务已取消，当前进度已保存"
  }
}
```

---

## 4. 知识点查询接口

### 4.1 获取知识点列表

**GET** `/api/v1/knowledge-points`

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `repository_id` | string (UUID) | 是 | 仓库 ID |
| `version` | string | 否 | 分析版本号，不传则使用当前版本 |
| `category` | string | 否 | 按分类筛选：`DP-` / `AD-` / `AL-` / `ET-` / `DK-` |
| `tag` | string | 否 | 按标签筛选（如 `Factory`, `MVC`） |
| `page` | integer | 否 | 页码，默认 1 |
| `page_size` | integer | 否 | 每页数量，默认 20 |
| `sort_by` | string | 否 | 排序字段：`created_at` / `title` / `confidence` |
| `sort_order` | string | 否 | 排序方向：`asc` / `desc`，默认 `desc` |

**响应 200 OK：**

```json
{
  "success": true,
  "data": [
    {
      "id": "kp-001",
      "category": "DP-",
      "category_name": "设计模式",
      "title": "工厂方法模式",
      "description": "通过定义创建对象的接口，让子类决定实例化哪个类",
      "confidence": 0.92,
      "tags": ["Factory", "Creational", "OOP"],
      "related_files_count": 3,
      "snippet_preview": "def create_renderer(format: str) -> Renderer:...",
      "version": "v20260707-a3f2b1c",
      "created_at": "2026-07-07T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 128,
    "total_pages": 7
  }
}
```

### 4.2 获取知识点详情

**GET** `/api/v1/knowledge-points/{knowledge_point_id}`

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `knowledge_point_id` | string (UUID) | 知识点 ID |

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `version` | string | 版本号，不传则使用知识点所在版本 |

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "id": "kp-001",
    "category": "DP-",
    "category_name": "设计模式",
    "title": "工厂方法模式",
    "description": "通过定义创建对象的接口，让子类决定实例化哪个类。在该项目中，RendererFactory 类使用了工厂方法模式来创建不同类型的渲染器。",
    "confidence": 0.92,
    "tags": ["Factory", "Creational", "OOP"],
    "version": "v20260707-a3f2b1c",
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",

    "code_snippets": [
      {
        "file_path": "src/renderers/factory.py",
        "start_line": 45,
        "end_line": 78,
        "highlighted_lines": [50, 55, 60],
        "language": "python",
        "signature": "class RendererFactory:"
      },
      {
        "file_path": "src/renderers/png_renderer.py",
        "start_line": 10,
        "end_line": 25,
        "highlighted_lines": [12],
        "language": "python",
        "signature": "class PNGRenderer(Renderer):"
      }
    ],

    "call_chain": [
      {
        "node_id": "node-1",
        "node_type": "function",
        "file": "src/main.py",
        "lines": [20, 25],
        "signature": "def main():",
        "direction": "entry"
      },
      {
        "node_id": "node-2",
        "node_type": "function_call",
        "file": "src/main.py",
        "lines": [22],
        "signature": "RendererFactory.create('png')",
        "direction": "call"
      },
      {
        "node_id": "node-3",
        "node_type": "class_method",
        "file": "src/renderers/factory.py",
        "lines": [50, 65],
        "signature": "def create(cls, format: str) -> Renderer:",
        "direction": "implementation"
      }
    ],

    "expansion": {
      "principle": "工厂方法模式定义了一个创建对象的接口，但由子类决定要实例化的类。...",
      "applicable_scenarios": ["对象创建逻辑复杂时", "需要解耦创建和使用代码时", "...", "..."],
      "best_practices": ["工厂方法应返回抽象类型而非具体实现", "..."],
      "related_patterns": ["抽象工厂", "建造者模式", "原型模式"],
      "learning_resources": [
        {
          "title": "Head First 设计模式 - 工厂方法章",
          "url": "https://example.com/book"
        }
      ]
    },

    "metadata": {
      "agent": "design_pattern_agent",
      "prompt_version": "v1.2",
      "model": "claude-sonnet-4-20250514",
      "tokens_used": {
        "input": 4500,
        "output": 320
      }
    },

    "created_at": "2026-07-07T10:30:00Z",
    "updated_at": "2026-07-07T10:30:00Z"
  }
}
```

### 4.3 获取知识点统计

**GET** `/api/v1/repositories/{repository_id}/knowledge-stats`

获取仓库知识点的统计信息。

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "total_points": 128,
    "by_category": {
      "DP-": 35,
      "AD-": 12,
      "AL-": 28,
      "ET-": 40,
      "DK-": 13
    },
    "by_confidence": {
      "high": 95,
      "medium": 28,
      "low": 5
    },
    "top_tags": [
      {"tag": "Factory", "count": 8},
      {"tag": "Observer", "count": 6},
      {"tag": "Strategy", "count": 5}
    ],
    "files_covered": 156,
    "total_lines_analyzed": 12500
  }
}
```

---

## 5. 搜索接口

### 5.1 全文搜索

**GET** `/api/v1/search`

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | 是 | 搜索关键词 |
| `repository_id` | string (UUID) | 否 | 限定搜索范围，不传则搜索所有仓库 |
| `category` | string | 否 | 按分类筛选 |
| `mode` | string | 否 | 搜索模式：`text`（全文）/ `vector`（语义）/ `hybrid`（混合），默认 `hybrid` |
| `page` | integer | 否 | 页码，默认 1 |
| `page_size` | integer | 否 | 每页数量，默认 20 |

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "query": "工厂模式",
    "mode": "hybrid",
    "results": [
      {
        "type": "knowledge_point",
        "score": 0.95,
        "point": {
          "id": "kp-001",
          "title": "工厂方法模式",
          "category": "DP-",
          "description": "通过定义创建对象的接口...",
          "repository_id": "550e8400-e29b-41d4-a716-446655440000",
          "repository_name": "my-awesome-project",
          "version": "v20260707-a3f2b1c"
        },
        "matched_text": "工厂方法模式定义了一个创建对象的接口..."
      },
      {
        "type": "knowledge_point",
        "score": 0.82,
        "point": {
          "id": "kp-045",
          "title": "抽象工厂模式",
          "category": "DP-",
          "repository_id": "550e8400-e29b-41d4-a716-446655440000",
          "repository_name": "my-awesome-project",
          "version": "v20260707-a3f2b1c"
        },
        "matched_text": "抽象工厂模式提供了一种接口..."
      }
    ],
    "facets": {
      "by_category": {
        "DP-": 15,
        "AD-": 3
      },
      "by_repository": {
        "my-awesome-project": 18
      }
    }
  },
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 18,
    "total_pages": 1
  }
}
```

### 5.2 搜索建议

**GET** `/api/v1/search/suggestions`

获取搜索建议（用于输入框自动补全）。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | 是 | 部分搜索词（至少 2 个字符） |
| `limit` | integer | 否 | 返回数量上限，默认 5 |

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "query": "工厂",
    "suggestions": [
      {"text": "工厂方法模式", "type": "category_DP-", "count": 8},
      {"text": "抽象工厂模式", "type": "category_DP-", "count": 5},
      {"text": "工厂模式最佳实践", "type": "tag", "count": 12}
    ]
  }
}
```

---

## 6. 版本管理接口

### 6.1 获取仓库分析版本列表

**GET** `/api/v1/repositories/{repository_id}/versions`

**响应 200 OK：**

```json
{
  "success": true,
  "data": [
    {
      "version": "v20260707-a3f2b1c",
      "status": "completed",
      "total_files": 523,
      "knowledge_points_count": 128,
      "is_current": true,
      "created_at": "2026-07-07T10:30:00Z",
      "completed_at": "2026-07-07T10:35:00Z"
    },
    {
      "version": "v20260706-b2e1a0d",
      "status": "completed",
      "total_files": 510,
      "knowledge_points_count": 115,
      "is_current": false,
      "created_at": "2026-07-06T08:00:00Z",
      "completed_at": "2026-07-06T08:05:00Z"
    }
  ]
}
```

### 6.2 切换到指定版本

**POST** `/api/v1/repositories/{repository_id}/switch-version`

**请求体：**

```json
{
  "version": "v20260706-b2e1a0d"
}
```

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "message": "已切换到版本 v20260706-b2e1a0d",
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",
    "previous_version": "v20260707-a3f2b1c",
    "current_version": "v20260706-b2e1a0d"
  }
}
```

### 6.3 回滚到指定版本

**POST** `/api/v1/repositories/{repository_id}/rollback`

与 switch-version 类似，但会标记此次变更为"回滚"操作，保留回滚前的版本记录。

**请求体：**

```json
{
  "version": "v20260706-b2e1a0d"
}
```

**响应 200 OK：**

```json
{
  "success": true,
  "data": {
    "message": "已回滚到版本 v20260706-b2e1a0d",
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",
    "rolled_back_from": "v20260707-a3f2b1c",
    "rolled_back_to": "v20260706-b2e1a0d",
    "rollback_record_id": "rb-001"
  }
}
```

---

## 7. SSE 实时推送接口

### 7.1 订阅分析进度

**GET** `/api/v1/repositories/{repository_id}/events`

使用 Server-Sent Events 推送分析任务的实时进度。

**请求头：**

```
Accept: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

**Event 格式：**

```
event: progress
data: {"task_id": "celery-task-uuid", "step": "analyzing_modules", "percent": 45, "files_processed": 235, "knowledge_points_found": 52}

event: knowledge_point
data: {"id": "kp-001", "title": "工厂方法模式", "category": "DP-", "status": "found"}

event: status_change
data: {"task_id": "celery-task-uuid", "status": "completed", "message": "分析完成"}

event: error
data: {"task_id": "celery-task-uuid", "error": "LLM API timeout", "recoverable": true}

event: done
data: {"task_id": "celery-task-uuid", "total_knowledge_points": 128, "duration_seconds": 300}
```

### 7.2 订阅知识库变更

**GET** `/api/v1/repositories/{repository_id}/changes`

当仓库有新的分析版本完成时推送通知。

```
event: new_version
data: {"version": "v20260708-c4g3d2e", "knowledge_points_count": 135, "changed_files_count": 12}
```

---

## 8. 错误响应格式

所有错误响应遵循统一格式：

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误描述",
    "details": {}
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-07-07T10:30:00Z"
  }
}
```

**错误码列表：**

| 错误码 | HTTP Status | 说明 |
|--------|------------|------|
| `AUTH_REQUIRED` | 401 | 未提供认证信息 |
| `AUTH_INVALID` | 401 | Token 无效或已过期 |
| `REPOSITORY_NOT_FOUND` | 404 | 仓库不存在 |
| `REPO_PATH_INVALID` | 400 | 仓库路径无效 |
| `REPO_PATH_UNAUTHORIZED` | 403 | 无权访问该路径 |
| `TASK_NOT_FOUND` | 404 | 分析任务不存在 |
| `TASK_ALREADY_RUNNING` | 409 | 已有任务正在运行 |
| `TASK_CANCELLED` | 410 | 任务已被取消 |
| `TASK_FAILED` | 422 | 任务执行失败 |
| `KNOWLEDGE_NOT_FOUND` | 404 | 知识点不存在 |
| `VERSION_NOT_FOUND` | 404 | 版本号不存在 |
| `SEARCH_ERROR` | 500 | 搜索服务异常 |
| `LLM_RATE_LIMIT` | 429 | LLM API 限流 |
| `LLM_QUOTA_EXCEEDED` | 402 | LLM API 配额用尽 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |
| `VALIDATION_ERROR` | 422 | 请求参数校验失败 |

**验证错误示例（422）：**

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数校验失败",
    "details": {
      "errors": [
        {
          "field": "path",
          "message": "路径不能为空",
          "code": "missing"
        },
        {
          "field": "name",
          "message": "名称长度不能超过 100",
          "code": "too_long"
        }
      ]
    }
  }
}
```

---

## 9. 速率限制

所有 API 端点受到速率限制：

| 认证状态 | 限制 | 窗口 |
|----------|------|------|
| 未认证 | 30 请求 | 每分钟 |
| 已认证 | 200 请求 | 每分钟 |
| 已认证（分析相关） | 10 请求 | 每分钟 |

**限流响应头：**

```
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 195
X-RateLimit-Reset: 1720345600
Retry-After: 45  (仅 429 响应时)
```

**限流错误响应（429）：**

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "请求过于频繁，请稍后重试",
    "details": {
      "limit": 200,
      "window_seconds": 60,
      "retry_after": 45
    }
  }
}
```

---

## 附录 A: cURL 示例

### 添加仓库

```bash
curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "django",
    "path": "/home/user/repos/django",
    "auto_analyze": true
  }'
```

### 查询知识点列表

```bash
curl "http://localhost:8000/api/v1/knowledge-points?repository_id=$REPO_ID&category=DP-&page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN"
```

### SSE 订阅

```bash
curl -N "http://localhost:8000/api/v1/repositories/$REPO_ID/events" \
  -H "Accept: text/event-stream" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 附录 B: WebSocket 接口（可选，Phase 5 后考虑）

> 以下为预留接口设计，实际实现可能在后续版本。

### 连接

```
ws://localhost:8000/api/v1/ws
```

### 消息格式

**客户端 → 服务端：**

```json
{
  "type": "subscribe",
  "payload": {
    "repository_id": "550e8400-e29b-41d4-a716-446655440000",
    "events": ["progress", "knowledge_point", "status_change"]
  }
}
```

**服务端 → 客户端：**

```json
{
  "type": "event",
  "payload": {
    "event": "knowledge_point",
    "data": {...}
  }
}
```
