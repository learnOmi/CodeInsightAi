# P2-08 规划：Phase 3 基础设施搭建

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-08 |
| 任务名称 | Phase 3 前置基础设施（LLM Client / Schema / Prompt 库 / Embedding） |
| 所属阶段 | Phase 2：代码扫描与解析 |
| 优先级 | P0 |
| 预估工时 | 3 天 |
| 状态 | 🔍 规划中 |

---

## 一、任务背景

当前主流 LLM（Claude 3.5 Sonnet / GPT-4o）的代码理解能力已成熟，无需花费时间验证精度。

P2-08 聚焦于 **为 Phase 3 的 AI 引擎搭建基础设施**，交付物是 P3 所有任务的先决条件。不验证可行性，只构建骨架。

---

## 二、交付物清单

| # | 交付物 | 路径 | 对应 P3 任务 | 说明 |
|---|--------|------|-------------|------|
| 1 | LLM Client 封装 | `codeinsight-backend/codeinsight/llm/client.py` | P3-01 | 统一 LLM 调用接口，支持 Claude/GPT/Ollama 切换 |
| 2 | 知识点 Schema | `codeinsight-backend/codeinsight/models/knowledge_point.py` | P3-05 | KnowledgePoint Pydantic 模型，含 5 类分类 |
| 3 | Prompt 库 | `codeinsight-backend/codeinsight/prompts/` | P3-04 | 5 类知识点的 System Prompt + Few-shot 初稿 |
| 4 | Embedding 管道 | `codeinsight-backend/codeinsight/embedding/` | P3-06 | 代码片段 → 向量 → pgvector 存储 |
| 5 | LangGraph 骨架 | `codeinsight-backend/codeinsight/agents/` | P3-02 | 最简 Agent 定义 + 工作流模板 |
| 6 | 评估框架 | `codeinsight-backend/scripts/eval_knowledge_points.py` | P3-11 | Precision/Recall 计算脚本 + 测试集目录结构 |
| 7 | P2-08 报告 | `doc/dev-report/P2-08-REPORT.md` | — | 执行总结 + 后续建议 |

---

## 三、执行步骤

### Day 1：LLM Client + 知识点 Schema

| 步骤 | 内容 | 输出 |
|------|------|------|
| 1.1 | LLM Client 接口设计：`LLMClient.chat(messages)` 统一签名 | `client.py` |
| 1.2 | LiteLLM 路由：支持 `claude-3.5-sonnet` / `gpt-4o` / `ollama:<model>` | 配置化 |
| 1.3 | 环境变量支持：`LLM_PROVIDER` / `LLM_API_KEY` / `OLLAMA_BASE_URL` | `.env.example` 更新 |
| 1.4 | KnowledgePoint Pydantic 模型：5 类分类 + 代码链路 + 拓展内容 | `knowledge_point.py` |
| 1.5 | Schema 单元测试：字段校验、分类枚举 | `test_knowledge_point.py` |

### Day 2：Prompt 库 + Embedding 管道

| 步骤 | 内容 | 输出 |
|------|------|------|
| 2.1 | 编写 DP- 设计模式 System Prompt（含 Few-shot 示例） | `prompts/design_pattern.md` |
| 2.2 | 编写 AD- 架构决策 System Prompt | `prompts/architecture.md` |
| 2.3 | 编写 AL- 算法实现 System Prompt | `prompts/algorithm.md` |
| 2.4 | 编写 ET- 工程技巧 System Prompt | `prompts/engineering.md` |
| 2.5 | 编写 DK- 领域知识 System Prompt | `prompts/domain.md` |
| 2.6 | Embedding 类：`EmbeddingClient.embed(text)` → `float[]` | `embedding/client.py` |
| 2.7 | pgvector 模型扩展：在 `knowledge_points` 表添加 `embedding` 列 | Alembic migration |

### Day 3：LangGraph 骨架 + 评估框架 + 报告

| 步骤 | 内容 | 输出 |
|------|------|------|
| 3.1 | LangGraph State 定义：`AnalysisState`（输入/输出/进度） | `agents/state.py` |
| 3.2 | 单 Agent 节点定义：`AnalysisNode`（调用 LLM + Schema 校验） | `agents/node.py` |
| 3.3 | 最简工作流：`build_analysis_graph()` → 可编译但不运行 | `agents/graph.py` |
| 3.4 | 评估脚本：`eval_knowledge_points.py`（对比 Ground Truth） | 脚本 + 测试集目录 |
| 3.5 | 编写 P2-08 报告 | `P2-08-REPORT.md` |

---

## 四、详细设计

### 4.1 LLM Client

```python
# codeinsight-backend/codeinsight/llm/client.py

class LLMConfig(BaseSettings):
    provider: Literal["claude", "gpt", "ollama"] = "claude"
    model: str = "claude-3.5-sonnet-20241022"
    api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 4096

class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    async def chat(
        self,
        messages: list[dict],
        response_model: type[PydanticModel] | None = None,
    ) -> dict | PydanticModel:
        """统一聊天接口。如果传入 response_model，返回 Pydantic 实例。"""
        ...

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """批量向量化（复用 LiteLLM 的 embedding 路由）。"""
        ...
```

### 4.2 KnowledgePoint Schema

```python
# codeinsight-backend/codeinsight/models/knowledge_point.py

class KnowledgePointCategory(str, Enum):
    DESIGN_PATTERN = "DP"
    ARCHITECTURE_DECISION = "AD"
    ALGORITHM = "AL"
    ENGINEERING_TECHNIQUE = "ET"
    DOMAIN_KNOWLEDGE = "DK"

class CodeSnippet(BaseModel):
    file: str
    start_line: int
    end_line: int
    content: str | None = None
    highlighted_lines: list[int] | None = None

class CallChainNode(BaseModel):
    node_id: str
    node_type: str  # class, method, function
    file: str
    name: str
    lines: tuple[int, int]

class KnowledgePoint(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    repository_id: UUID
    version: str
    category: KnowledgePointCategory
    prefix: str  # DP-Factory, AD-MVC 等
    title: str
    description: str
    code_snippets: list[CodeSnippet]
    call_chain: list[CallChainNode]
    expansion: str | None = None
    confidence: float = Field(ge=0, le=1, default=1.0)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
```

### 4.3 Prompt 模板结构

```
codeinsight-backend/codeinsight/prompts/
├── base.md                     # 通用指令（输出格式、约束）
├── design_pattern.md           # DP- 设计模式
├── architecture.md             # AD- 架构决策
├── algorithm.md                # AL- 算法实现
├── engineering.md              # ET- 工程技巧
└── domain.md                   # DK- 领域知识
```

每个 Prompt 文件包含：
- **角色定义**：你是谁
- **任务描述**：要做什么
- **输入说明**：AST + 代码片段的格式
- **输出 Schema**：JSON 结构（引用 KnowledgePoint Schema）
- **Few-shot 示例**：2-3 个典型输入→输出
- **约束**：温度、置信度阈值等

### 4.4 LangGraph 骨架

```python
# codeinsight-backend/codeinsight/agents/state.py

class AnalysisState(TypedDict):
    repo_id: str
    ast_data: list[dict]
    code_snippets: list[dict]
    knowledge_points: list[dict]
    current_category: str
    progress: float
    error: str | None
```

```python
# codeinsight-backend/codeinsight/agents/graph.py

def build_analysis_graph() -> CompiledStateGraph:
    """构建分析工作流。P3-02 在此基础上扩展多 Agent 编排。"""
    ...
```

### 4.5 Embedding 管道

```python
# codeinsight-backend/codeinsight/embedding/client.py

class EmbeddingClient:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """调用 LiteLLM embedding API，返回向量列表。"""
        ...

    async def store(
        self,
        session: AsyncSession,
        knowledge_point: KnowledgePoint,
        vector: list[float],
    ) -> None:
        """将向量写入 knowledge_points.embedding（pgvector）。"""
        ...
```

---

## 五、技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| LLM 路由 | LiteLLM | 统一接口，支持多 provider，成本路由 |
| LLM 主模型 | Claude 3.5 Sonnet | 代码理解能力最强 |
| LLM 备选 | GPT-4o | 对比/降级 |
| 本地模型 | Ollama + Llama 3.1 8B | 简单任务路由，节省 API 成本 |
| Embedding 模型 | text-embedding-3-small | OpenAI 提供，效果好，成本低 |
| 向量存储 | pgvector (HNSW) | 已在 PostgreSQL 中，零额外基础设施 |
| 工作流引擎 | LangGraph 0.2+ | P3-02 正式使用，此处搭建骨架 |

---

## 六、数据库变更

### 6.1 knowledge_points 表扩展

```sql
-- Alembic migration: 20260715_add_knowledge_points_schema

CREATE TABLE knowledge_points (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories(id),
    version TEXT NOT NULL,
    category TEXT NOT NULL,           -- DP / AD / AL / ET / DK
    prefix TEXT NOT NULL,             -- DP-Factory / AD-MVC 等
    title TEXT NOT NULL,
    description TEXT,
    code_snippets JSONB,              -- [{file, start_line, end_line, highlighted_lines}]
    call_chain JSONB,                 -- [{node_id, node_type, file, name, lines}]
    expansion TEXT,                   -- AI 生成的拓展内容
    confidence FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    embedding VECTOR(1536),           -- pgvector
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 向量索引（HNSW，P95 < 10ms）
CREATE INDEX idx_knowledge_points_embedding 
ON knowledge_points 
USING hnsw (embedding vector_cosine_ops);
```

---

## 七、与后续任务的关系

| P3 任务 | 依赖 P2-08 的交付物 |
|---------|-------------------|
| **P3-01** LLM 客户端封装 | 直接继承 LLMClient 实现 |
| **P3-02** LangGraph 工作流 | 使用 AnalysisState + build_analysis_graph() 骨架 |
| **P3-03** 多 Agent 编排 | 在骨架上扩展 5 个 Agent 节点 |
| **P3-04** Prompt 工程 | 在初稿基础上优化（加 Few-shot、CoT 等） |
| **P3-05** 知识点 Schema | 直接继承 KnowledgePoint 模型 |
| **P3-06** Embedding 向量化 | 在 EmbeddingClient 上扩展批处理和索引优化 |
| **P3-08** 拓展内容生成 | 使用同一 LLM Client + KnowledgePoint Schema |
| **P3-11** Prompt 回归测试 | 使用评估框架 + 测试集目录 |

---

## 八、时间线

```
Day 1: LLM Client + KnowledgePoint Schema + 单元测试
Day 2: Prompt 库（5 个） + Embedding 管道 + Alembic migration
Day 3: LangGraph 骨架 + 评估框架 + P2-08 报告
```

---

## 九、成功标准

1. **LLM Client**：可以成功调用 Claude/GPT/Ollama，返回结构化响应
2. **KnowledgePoint Schema**：Pydantic 模型通过所有校验测试
3. **Prompt 库**：5 个 Prompt 文件编写完成，格式统一
4. **Embedding 管道**：可以将文本向量化并写入 pgvector
5. **LangGraph 骨架**：`build_analysis_graph()` 可编译，state 定义完整
6. **评估框架**：脚本可运行（即使暂无测试数据）
7. **数据库 migration**：`knowledge_points` 表 + HNSW 索引创建成功

---

## 十、风险与应对

| 风险 | 等级 | 应对策略 |
|------|------|----------|
| LiteLLM 与当前环境不兼容 | 低 | 用 `asyncio + httpx` 直接调用 API 作为 fallback |
| pgvector extension 未安装 | 中 | 在 docker-compose.yml 中添加 `initdb` 脚本安装 |
| LangGraph 版本变动 | 低 | 锁定版本 `langgraph>=0.2.0,<0.3.0` |
| Embedding 模型选型偏差 | 低 | 先使用 text-embedding-3-small，P3-06 再评估替换 |
