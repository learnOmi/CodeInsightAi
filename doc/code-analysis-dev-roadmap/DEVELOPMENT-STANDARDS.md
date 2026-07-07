# CodeInsight AI — 开发规范

> 本文档定义 CodeInsight AI 项目的编码规范、工作流程和技术标准。所有团队成员必须遵守。

---

## 目录

1. [通用规范](#一通用规范)
2. [Python 后端开发规范](#二python-后端开发规范)
3. [TypeScript/Next.js 前端开发规范](#三typescriptnextjs-前端开发规范)
4. [数据库开发规范](#四数据库开发规范)
5. [AI/LLM 开发规范](#五aillm-开发规范)
6. [Git 工作流规范](#六git-工作流规范)
7. [测试规范](#七测试规范)
8. [文档规范](#八文档规范)
9. [安全规范](#九安全规范)

---

## 一、通用规范

### 1.1 常量提取

所有魔法数字、字符串字面量、配置值必须按类别提取到常量类或配置文件中，禁止在业务逻辑中硬编码。

```python
# GOOD ✅
MAX_RETRY_COUNT = 3
SUPPORTED_LANGUAGES = ["python", "javascript", "typescript", "java", ...]
LLM_TIMEOUT_SECONDS = 120

# BAD ❌
for i in range(3):  # 魔法数字
    ...

if lang in ["python", "javascript"]:  # 硬编码列表
    ...
```

### 1.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块/包名 | 小写 + 下划线 | `knowledge_extractor.py` |
| 类名 | PascalCase | `KnowledgePoint`, `CallGraphBuilder` |
| 函数/方法名 | snake_case | `extract_knowledge()`, `build_call_chain()` |
| 常量名 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| 变量名 | snake_case | `file_list`, `knowledge_points` |
| 私有属性 | `_leading_underscore` | `_internal_cache` |
| 数据库表名 | 复数 snake_case | `knowledge_points`, `analysis_versions` |
| 数据库字段名 | snake_case | `knowledge_point_id`, `created_at` |

### 1.3 注释规范

- **所有 public 类、public 方法**必须包含清晰的文档字符串（docstring）
- **复杂逻辑块**必须包含行内注释解释意图
- **修改现有代码时**保留所有原有注释
- JavaDoc 风格注释鼓励用于 API 文档生成

```python
def extract_knowledge(
    code_snippet: str,
    category: KnowledgeCategory,
    context: AnalysisContext
) -> list[KnowledgePoint]:
    """
    从代码片段中提取指定类别的知识点。

    Args:
        code_snippet: 待分析的代码片段（不包含文件路径）
        category: 知识点分类（设计模式/架构决策等）
        context: 代码上下文信息（导入关系、调用图等）

    Returns:
        提取到的知识点列表，可能为空但不为 None

    Raises:
        ValidationError: 当代码片段格式不合法时
        LLMError: 当 LLM API 调用失败时
    """
    ...
```

### 1.4 方法长度限制

- 单个方法不超过 **50 行**（不含 docstring 和注释）
- 超过 50 行的方法必须拆分为多个子方法
- 超过 200 行的文件应当考虑拆分模块

### 1.5 错误处理

- **禁止空 catch 块**吞掉异常
- 至少记录异常日志或抛出有意义的业务异常
- API 层统一异常处理，返回用户友好的错误响应

```python
# GOOD ✅
try:
    result = llm_client.analyze(code_chunk)
except RateLimitError as e:
    logger.warning(f"LLM rate limited, backing off: {e}")
    time.sleep(exponential_backoff(retry_count))
    raise
except LLMConnectionError as e:
    logger.error(f"LLM connection failed: {e}", exc_info=True)
    raise ServiceUnavailableError("LLM 服务暂时不可用")

# BAD ❌
try:
    result = llm_client.analyze(code_chunk)
except Exception:
    pass  # 错误被静默吞掉
```

---

## 二、Python 后端开发规范

### 2.1 项目结构

```
backend/
├── codeinsight/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py             # 配置管理（Pydantic BaseSettings）
│   ├── dependencies.py       # DI 依赖注入
│   │
│   ├── api/                  # API 路由层
│   │   ├── __init__.py
│   │   ├── repositories.py   # 仓库管理路由
│   │   ├── analysis.py       # 分析任务路由
│   │   ├── knowledge.py      # 知识点查询路由
│   │   ├── search.py         # 搜索路由
│   │   └── versions.py       # 版本管理路由
│   │
│   ├── models/               # 数据库模型（SQLAlchemy）
│   │   ├── __init__.py
│   │   ├── repository.py
│   │   ├── knowledge_point.py
│   │   └── analysis_version.py
│   │
│   ├── schemas/              # Pydantic Schema
│   │   ├── __init__.py
│   │   ├── repository.py
│   │   ├── knowledge.py
│   │   └── search.py
│   │
│   ├── services/             # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── repository_service.py
│   │   ├── analysis_service.py
│   │   └── search_service.py
│   │
│   ├── engines/              # 核心引擎
│   │   ├── __init__.py
│   │   ├── scanner.py        # 代码扫描器
│   │   ├── parser.py         # Tree-sitter 解析器
│   │   ├── call_graph.py     # 调用图构建
│   │   └── incremental.py    # 增量分析
│   │
│   ├── agents/               # AI Agent
│   │   ├── __init__.py
│   │   ├── base.py           # Agent 基类
│   │   ├── design_pattern.py
│   │   ├── architecture.py
│   │   ├── algorithm.py
│   │   ├── engineering_tips.py
│   │   └── domain_knowledge.py
│   │
│   ├── llm/                  # LLM 客户端
│   │   ├── __init__.py
│   │   ├── client.py         # 统一 LLM 接口
│   │   ├── routing.py        # LiteLLM 路由
│   │   └── embeddings.py     # Embedding 服务
│   │
│   └── utils/                # 工具函数
│       ├── __init__.py
│       ├── logging.py
│       └── validators.py
│
├── tasks/                    # Celery 任务
│   ├── __init__.py
│   └── analysis_tasks.py
│
├── alembic/                  # 数据库迁移
│   ├── env.py
│   └── versions/
│
├── tests/                    # 测试
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── pyproject.toml
├── Dockerfile
└── alembic.ini
```

### 2.2 依赖注入

使用 FastAPI 的 `Depends` 进行依赖注入，禁止在路由函数中直接创建重对象。

```python
# GOOD ✅
def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session

@router.post("/repositories", status_code=201)
async def create_repository(
    repo_create: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
    task_queue: Celery = Depends(get_task_queue),
):
    ...

# BAD ❌
@router.post("/repositories", status_code=201)
async def create_repository(repo_create: RepositoryCreate):
    db = AsyncSession(...)  # 直接在路由中创建
    ...
```

### 2.3 Pydantic Schema 规范

```python
from pydantic import BaseModel, Field, HttpUrl, field_validator
from enum import Enum
from datetime import datetime


class KnowledgeCategory(str, Enum):
    DESIGN_PATTERN = "DP-"
    ARCHITECTURE_DECISION = "AD-"
    ALGORITHM = "AL-"
    ENGINEERING_TIP = "ET-"
    DOMAIN_KNOWLEDGE = "DK-"


class KnowledgePointBase(BaseModel):
    category: KnowledgeCategory
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=5000)

    class Config:
        use_enum_values = True


class KnowledgePointCreate(KnowledgePointBase):
    code_snippets: list[CodeSnippetCreate] = Field(..., min_length=1)


class KnowledgePointResponse(KnowledgePointBase):
    id: uuid.UUID
    version: str
    repository_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
```

### 2.4 日志规范

```python
import logging

# 每个模块使用独立 logger
logger = logging.getLogger(__name__)

# 日志级别使用
logger.debug("详细调试信息，仅开发环境")
logger.info("正常业务流程：仓库 %s 分析完成", repo_id)
logger.warning("可恢复的异常情况：LLM 响应慢 %.2fs", latency)
logger.error("错误但系统可继续：数据库连接失败", exc_info=True)
logger.critical("严重错误：系统无法继续运行")
```

### 2.5 异步编程规范

```python
# 使用 async/await 处理 IO 密集型操作
async def analyze_repository(repo_id: uuid.UUID) -> None:
    """异步分析仓库（Celery 任务入口）"""
    async with async_session_factory() as db:
        files = await collect_files(repo_id, db)
        for chunk in chunk_files(files, size=50):
            await process_chunk(chunk, db)

# 同步 CPU 密集型操作使用 run_in_executor
def parse_ast_sync(file_path: Path) -> AST:
    """Tree-sitter 同步解析（CPU 密集型）"""
    return parser.parse_file(str(file_path))

async def parse_async(file_path: Path) -> AST:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, parse_ast_sync, file_path)
```

---

## 三、TypeScript/Next.js 前端开发规范

### 3.1 项目结构

```
frontend/
├── app/                        # Next.js App Router
│   ├── layout.tsx              # 根布局
│   ├── page.tsx                # 首页
│   ├── repositories/
│   │   ├── page.tsx            # 仓库管理页
│   │   └── [id]/
│   │       ├── page.tsx        # 仓库详情
│   │       └── analysis/
│   │           └── page.tsx    # 分析进度页
│   ├── knowledge/
│   │   ├── page.tsx            # 知识卡片列表
│   │   └── [id]/
│   │       └── page.tsx        # 知识点详情
│   └── search/
│       └── page.tsx            # 搜索结果页
│
├── components/                 # 可复用组件
│   ├── ui/                     # 基础 UI 组件（Shadcn/UI）
│   ├── knowledge/              # 知识点相关组件
│   │   ├── KnowledgeCard.tsx
│   │   ├── KnowledgeDetail.tsx
│   │   └── CodeChainViewer.tsx
│   ├── repository/             # 仓库相关组件
│   └── search/                 # 搜索相关组件
│
├── lib/                        # 工具函数和配置
│   ├── api.ts                  # API 客户端
│   ├── query-keys.ts           # TanStack Query keys
│   └── utils.ts                # 通用工具函数
│
├── stores/                     # Zustand stores
│   ├── repository-store.ts
│   └── analysis-store.ts
│
├── types/                      # 共享 TypeScript 类型
│   ├── repository.ts
│   ├── knowledge.ts
│   └── search.ts
│
├── hooks/                      # 自定义 Hooks
│   ├── use-sse.ts              # SSE 连接 Hook
│   └── use-search.ts           # 搜索 Hook
│
├── public/
├── next.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

### 3.2 组件规范

```typescript
// 使用函数组件 + TypeScript 接口
interface KnowledgeCardProps {
  /** 知识点数据 */
  point: KnowledgePoint;
  /** 点击回调 */
  onClick?: (id: string) => void;
  /** 自定义类名 */
  className?: string;
}

/**
 * 知识卡片组件：展示单个知识点的摘要信息
 */
export function KnowledgeCard({ point, onClick, className }: KnowledgeCardProps) {
  const categoryLabel = getCategoryLabel(point.category);

  return (
    <article
      className={`rounded-lg border p-4 hover:shadow-md transition-shadow ${className ?? ""}`}
      onClick={() => onClick?.(point.id)}
    >
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-lg">{point.title}</h3>
        <span className="badge">{categoryLabel}</span>
      </div>
      <p className="text-muted-foreground mt-2 line-clamp-2">
        {point.description}
      </p>
    </article>
  );
}
```

### 3.3 状态管理规范

```typescript
// Zustand store
import { create } from "zustand";

interface AnalysisStore {
  taskId: string | null;
  progress: number;
  status: "idle" | "analyzing" | "completed" | "failed";
  errorMessage: string | null;
  setTask: (taskId: string) => void;
  updateProgress: (progress: number) => void;
  setStatus: (status: AnalysisStore["status"]) => void;
  setError: (error: string) => void;
  reset: () => void;
}

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  taskId: null,
  progress: 0,
  status: "idle",
  errorMessage: null,
  setTask: (taskId) => set({ taskId }),
  updateProgress: (progress) => set({ progress }),
  setStatus: (status) => set({ status }),
  setError: (errorMessage) => set({ errorMessage, status: "failed" }),
  reset: () => set({ taskId: null, progress: 0, status: "idle", errorMessage: null }),
}));
```

### 3.4 API 调用规范

```typescript
// 统一的 API 客户端
import { queryOptions, useQuery, useMutation } from "@tanstack/react-query";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchKnowledgePoints(params:SearchParams): Promise<KnowledgePoint[]> {
  const response = await fetch(`${API_BASE}/api/v1/knowledge-points?${params}`);
  if (!response.ok) throw new Error(`API error: ${response.status}`);
  return response.json();
}

export const knowledgePointKeys = {
  all: ["knowledge-points"] as const,
  list: (params:SearchParams) => [...knowledgePointKeys.all, params] as const,
  detail: (id: string) => [...knowledgePointKeys.all, "detail", id] as const,
};

export function useKnowledgePoints(params: SearchParams) {
  return useQuery({
    queryKey: knowledgePointKeys.list(params),
    queryFn: () => fetchKnowledgePoints(params),
    staleTime: 5 * 60 * 1000, // 5 分钟缓存
  });
}
```

### 3.5 代码风格

- 使用 **ESLint + Prettier** 统一代码风格
- 文件使用 **UTF-8 with BOM** 编码（可选）
- 使用 **双引号** 包裹字符串（Prettier 配置）
- 每条语句末尾使用 **分号**
- **禁止使用 `any` 类型**，使用 `unknown` + 类型守卫
- **禁止使用 `console.log`**，使用统一的 logger

```typescript
// BAD ❌
function processData(data: any) {
  console.log(data);
  return data.map((item: any) => item.value);
}

// GOOD ✅
function processData(data: unknown): number[] {
  if (!Array.isArray(data)) {
    throw new TypeError("Expected an array");
  }
  return data
    .map((item: unknown): { value: number } => {
      if (typeof item !== "object" || item === null) {
        throw new TypeError("Invalid item type");
      }
      return item as { value: number };
    })
    .map((item) => item.value);
}
```

---

## 四、数据库开发规范

### 4.1 命名规范

| 对象类型 | 命名规则 | 示例 |
|----------|---------|------|
| 表名 | 复数 snake_case | `knowledge_points` |
| 字段名 | snake_case | `knowledge_point_id` |
| 主键 | `id` (UUID) | `id UUID PRIMARY KEY` |
| 外键 | `{关联表}_id` | `repository_id UUID REFERENCES repositories(id)` |
| 索引 | `idx_{表名}_{字段}` | `idx_knowledge_points_category` |
| 唯一约束 | `uq_{表名}_{字段}` | `uq_analysis_versions_repository_version` |
| 时间戳 | `_at` 后缀 | `created_at`, `updated_at` |

### 4.2 必须遵循的规则

1. **所有表必须有 `id` (UUID) 主键**
2. **所有表必须有 `created_at` 和 `updated_at` 字段**
3. **外键必须建立索引**
4. **频繁查询的字段必须建立索引**
5. **向量字段使用 pgvector 的 `VECTOR(1536)` 类型**
6. **禁止在生产环境直接执行 ALTER TABLE 删除列**

```sql
-- GOOD ✅
CREATE TABLE knowledge_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version TEXT NOT NULL,
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    category KNOWLEDGE_CATEGORY NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_repo_version_title UNIQUE (repository_id, version, title)
);

-- 为常用查询建立索引
CREATE INDEX idx_knowledge_points_repository ON knowledge_points(repository_id);
CREATE INDEX idx_knowledge_points_category ON knowledge_points(category);
CREATE INDEX idx_knowledge_points_embedding ON knowledge_points USING hnsw (embedding vector_cosine_ops);
```

### 4.3 Migration 规范

- 使用 **Alembic** 管理数据库迁移
- 每次 Schema 变更必须创建 migration script
- Migration 文件必须包含 `upgrade()` 和 `downgrade()`
- 禁止手动修改已应用的 migration 文件

```bash
# 创建新的 migration
alembic revision --autogenerate -m "add knowledge points table"

# 应用 migration
alembic upgrade head

# 回滚 migration
alembic downgrade -1
```

---

## 五、AI/LLM 开发规范

### 5.1 Prompt 管理规范

```
prompts/
├── base/                   # 基础 Prompt 模板
│   ├── system_template.j2
│   └── few_shot_examples.j2
├── agents/                 # 各 Agent 的 Prompt
│   ├── design_pattern.j2
│   ├── architecture.j2
│   ├── algorithm.j2
│   ├── engineering_tips.j2
│   └── domain_knowledge.j2
├── evaluation/             # 评估集
│   ├── benchmark_dataset.jsonl
│   └── expected_outputs/
└── versions/               # Prompt 版本历史
    ├── v1.0/
    └── v1.1/
```

- 所有 Prompt 使用 **Jinja2 模板**，支持变量替换
- 每个 Prompt 必须有**版本号**，变更记录在 `versions/`
- Prompt 变更必须触发 **回归测试**（P3-11）
- 禁止在代码中硬编码 Prompt 字符串

### 5.2 LLM 调用规范

```python
class LLMClient:
    """统一 LLM 客户端接口"""

    def __init__(self, config: LLMConfig):
        self.router = LiteLLMRouter(config)
        self.rate_limiter = RateLimiter(max_requests=10, period=60)

    async def analyze(self, code: str, prompt: str) -> str:
        """
        调用 LLM 进行分析。

        Raises:
            LLMRateLimitError: 达到速率限制
            LLMQuotaExceededError: API 配额用尽
            LLMConnectionError: 网络连接失败
        """
        self.rate_limiter.acquire()
        try:
            return await self.router.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.3,  # 分析任务使用低温度
            )
        except RateLimitException:
            raise LLMRateLimitError("LLM API 速率限制，请稍后重试")
```

### 5.3 输出校验规范

```python
from pydantic import BaseModel, field_validator

class KnowledgePointOutput(BaseModel):
    category: KnowledgeCategory
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v

def validate_llm_output(raw_output: str) -> KnowledgePointOutput:
    """
    校验 LLM 输出是否符合 Schema。
    校验失败时抛出 ValidationError。
    """
    try:
        data = json.loads(raw_output)
        return KnowledgePointOutput(**data)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON from LLM: {e}")
    except ValidationError as e:
        raise ValidationError(f"Schema validation failed: {e}")
```

---

## 六、Git 工作流规范

### 6.1 分支策略

```
main (生产)
  ↑
develop (开发)
  ↑
feature/xxx (功能分支)
bugfix/xxx (修复分支)
release/v1.0 (发布分支)
```

- `main`：生产分支，只接受来自 `release/*` 的合并
- `develop`：开发分支，只接受来自 `feature/*` 的合并
- `feature/*`：功能分支，从 `develop` 创建，完成后合并回 `develop`
- `release/*`：发布分支，从 `develop` 创建，完成后合并到 `main` 和 `develop`

### 6.2 Commit Message 规范

遵循 **Conventional Commits** 规范：

```
<type>(<scope>): <subject>

<body> (optional)

<footer> (optional)
```

**Type 列表：**

| Type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `style` | 代码格式（不影响逻辑） |
| `refactor` | 重构（既不是新功能也不是修复） |
| `test` | 测试相关 |
| `chore` | 构建/工具链变更 |
| `perf` | 性能优化 |

**示例：**

```
feat(knowledge): 添加设计模式检测 Agent

新增 DP- 类别知识点的自动检测能力，支持 GoF 23 种设计模式识别。

- 新增 DesignPatternAgent
- 添加设计模式分类的 Few-shot 示例
- 更新 Prompt 版本到 v1.2

Closes #42
```

### 6.3 PR/MR 规范

- 每个 PR 必须关联一个 Issue
- PR 标题格式：`[类型] 简短描述`
- PR 描述必须包含：
  - **变更类型**：feat / fix / refactor / ...
  - **测试说明**：如何验证变更
  - **截图/录屏**（前端变更必需）
- 至少 **1 人 Approve** 才能合并
- 合并前确保 CI 全部通过

---

## 七、测试规范

### 7.1 测试覆盖要求

| 模块 | 最低覆盖率 |
|------|-----------|
| AST 解析器 | ≥ 90% |
| LLM 客户端 | ≥ 85% |
| API 端点 | ≥ 80% |
| 前端组件 | ≥ 75% |
| 整体项目 | ≥ 70% |

### 7.2 测试命名规范

```python
# 测试文件：test_{模块名}.py
# 测试类：Test{被测试类名}
# 测试方法：test_{方法名}_{场景}_{预期结果}

def test_parse_python_function_detects_decorator_when_present():
    """测试 Python 函数解析器在存在装饰器时能正确识别"""
    ...

def test_extract_knowledge_returns_empty_list_when_no_patterns_found():
    """测试知识点提取在无匹配模式时返回空列表"""
    ...
```

### 7.3 Mock 规范

```python
from unittest.mock import AsyncMock, patch

@patch("codeinsight.llm.client.LLMClient.complete", new_callable=AsyncMock)
async def test_agent_calls_llm_with_correct_prompt(mock_complete):
    """测试 Agent 使用正确的 Prompt 调用 LLM"""
    mock_complete.return_value = '{"category": "DP-", "title": "Factory"}'

    agent = DesignPatternAgent(llm_client=mock_complete)
    result = await agent.analyze(code_snippet)

    assert result.category == KnowledgeCategory.DESIGN_PATTERN
    mock_complete.assert_called_once()
    args, kwargs = mock_complete.call_args
    assert "factory" in kwargs["messages"][0]["content"].lower()
```

---

## 八、文档规范

### 8.1 API 文档

- 所有 API 端点必须包含 **OpenAPI 描述**（docstring）
- 参数和返回值必须有 **类型注解**
- 使用 **Swagger UI** 自动生成文档

```python
@router.post(
    "/repositories",
    status_code=status.HTTP_201_CREATED,
    summary="添加代码仓库",
    description="添加一个新的代码仓库并开始分析",
    responses={
        201: {"model": RepositoryResponse, "description": "仓库创建成功"},
        400: {"model": ErrorResponse, "description": "路径无效"},
        409: {"model": ErrorResponse, "description": "仓库已存在"},
    },
)
async def create_repository(
    repo_create: RepositoryCreate,
    ...
):
    ...
```

### 8.2 README 规范

项目根目录 `README.md` 必须包含：

1. 项目简介
2. 功能特性
3. 快速开始（安装 + 运行）
4. 技术栈
5. 目录结构
6. API 文档链接
7. 贡献指南

---

## 九、安全规范

### 9.1 敏感信息管理

- **禁止**在代码中硬编码 API Key、密码、Token
- 使用 **环境变量** 或 **密钥管理服务**
- `.env` 文件加入 `.gitignore`

```python
# GOOD ✅
from pydantic import BaseSettings

class Settings(BaseSettings):
    database_url: str
    llm_api_key: str
    redis_url: str

    class Config:
        env_file = ".env"

settings = Settings()

# BAD ❌
LLM_API_KEY = "sk-1234567890abcdef"  # 硬编码密钥
```

### 9.2 API 安全

- 所有 API 端点必须启用 **速率限制**
- 用户输入必须进行 **校验和清理**
- 文件路径必须防止 **路径遍历攻击**

```python
from pathlib import Path

def validate_repository_path(path_str: str) -> Path:
    """验证仓库路径，防止路径遍历攻击"""
    path = Path(path_str).resolve()
    allowed_base = Path.home() / "repos"  # 限制在允许目录内

    if not str(path).startswith(str(allowed_base)):
        raise ValueError("Repository path must be within allowed directory")

    return path
```

### 9.3 数据传输安全

- 所有数据传输必须使用 **HTTPS/TLS 1.3**
- 敏感字段（如 API Key）在数据库中必须**加密存储**
- 日志中**禁止记录**敏感信息（密码、Token、完整代码）
