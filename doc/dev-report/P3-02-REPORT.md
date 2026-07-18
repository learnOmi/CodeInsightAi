# P3-02 交付报告：LangGraph 工作流（单模块分析 Agent）

## 概述

- **阶段**: P3 (AI 分析引擎)
- **任务**: P3-02 — LangGraph 工作流：单模块分析 Agent
- **优先级**: P0
- **状态**: ✅ 已完成
- **交付日期**: 2026-07-19

## 完成度

| 模块 | 完成度 | 说明 |
|------|--------|------|
| Agent State | 100% | `AnalysisState` TypedDict，含 `repo_id`, `ast_data`, `code_snippets`, `knowledge_points`(去重追加), `progress`, `error`, `messages` |
| Agent Node | 100% | 基类 + 5 个子类，使用 Pydantic `TypeAdapter` 结构化输出校验 |
| Agent Graph | 100% | `StateGraph` 线性串联 DAG，`run()` + `create_initial_state()` + `get_graph_info()` |
| 领域知识 Prompt | 100% | 新建 `domain.md`，含 5 类领域知识定义 + 2 个 Few-shot 示例 |
| 结构化输出 | 100% | `KnowledgePointExtraction` Schema + `TypeAdapter` 校验，替代手写 JSON 解析 |
| Orchestrator 集成 | 100% | Step 5 完整流程：读取 AST → 构建代码片段 → 运行 AnalysisGraph → 持久化 |
| 测试覆盖 | 100% | 27 个测试用例，覆盖 State/Schema/Node/Graph/ParseResponse |
| 全量 CI | 100% | 76 个测试全部通过（含 P3-01 + KnowledgePoint 存量测试） |

## 架构

```
用户触发分析
  ↓
Orchestrator Step 1-4: 扫描 → 解析 → 建图
  ↓
Orchestrator Step 5 (P3-02 交付):
  ├─ 从 DB 读取 AST 节点 (AstNodeDAO.get_by_repository)
  ├─ 从磁盘读取文件内容
  ├─ AnalysisGraph.run() 依次执行 5 个 Agent
  │   ├─ DesignPatternNode   → 设计模式   → progress 0.2
  │   ├─ ArchitectureNode     → 架构决策   → progress 0.4
  │   ├─ AlgorithmNode        → 算法实现   → progress 0.6
  │   ├─ EngineeringNode      → 工程技巧   → progress 0.8
  │   └─ DomainKnowledgeNode  → 领域知识   → progress 1.0
  └─ 结果持久化到 knowledge_points 表 (KnowledgePointDAO.create)
  ↓
Orchestrator Step 6-7: 存储 → 完成
```

## 详细设计

### 1. Agent State (`codeinsight/agents/state.py`)

```python
class AnalysisState(TypedDict):
    repo_id: str                                    # 仓库 UUID
    ast_data: list[dict]                            # AST 节点（Tree-sitter 解析结果）
    code_snippets: list[dict]                       # 代码片段（文件路径 + 内容）
    knowledge_points: Annotated[list[dict], ...]    # 知识点（按 title 去重追加）
    current_category: str                           # 当前分析分类
    progress: float                                 # 0.0 → 1.0
    error: str | None                               # 错误信息
    messages: list[dict]                            # LLM 对话历史
```

- 使用 `Annotated` + `_accumulate_knowledge_points` 实现 LangGraph 的**追加合并**语义
- 去重逻辑：按 `title` 字段去重，优先保留已有条目

### 2. Agent Node (`codeinsight/agents/node.py`)

| 节点 | 分类 | Prompt 文件 | Progress |
|------|------|-------------|----------|
| `DesignPatternNode` | DP | `design_pattern.md` | 0.2 |
| `ArchitectureNode` | AD | `architecture.md` | 0.4 |
| `AlgorithmNode` | AL | `algorithm.md` | 0.6 |
| `EngineeringNode` | ET | `engineering.md` | 0.8 |
| `DomainKnowledgeNode` | DK | `domain.md` | 1.0 |

**关键改进**（相比 P3-02 设计稿）：
- 使用 Pydantic `TypeAdapter(list[KnowledgePointExtraction])` **替代手写 JSON 解析**
- `_parse_response()` 支持 3 种 LLM 输出格式：JSON 数组、`knowledge_points` 包装对象、原始文本 fallback
- `KnowledgePointExtraction.category` 字段带 `Field(pattern=r"^(DP|AD|AL|ET|DK)$")` 正则校验

### 3. Agent Graph (`codeinsight/agents/graph.py`)

- 使用 `langgraph.graph.StateGraph` 构建有向无环图
- 5 个节点线性串联：`design_pattern → architecture → algorithm → engineering → domain_knowledge → END`
- `run()` 方法：调用 `graph.ainvoke()`，异常时日志记录 + 重新抛出
- `create_initial_state()` 静态工厂方法

### 4. 结构化输出 Schema (`codeinsight/schemas/knowledge.py`)

新增 3 个 Pydantic 模型：

| 模型 | 字段 | 说明 |
|------|------|------|
| `KnowledgePointExtraction` | category, prefix, title, description, confidence, code_snippets, call_chain, tags | LLM 输出主模型 |
| `CodeSnippetExtraction` | file, start_line, end_line, content, highlighted_lines | 代码片段 |
| `CallChainExtraction` | node_id, node_type, file, name, lines | 调用链节点 |

### 5. 领域知识 Prompt (`codeinsight/prompts/domain.md`)

- 5 类：领域模型、业务规则、业务流程、核心概念、业务策略
- 4 条判断标准：领域特有性、业务价值、可复用性、非通用性
- 2 个 Few-shot 示例：订单领域模型、多通道支付路由策略

### 6. Orchestrator 集成 (`codeinsight/tasks/analysis_orchestrator.py`)

Step 5 核心流程：

```python
# 1. 查询 AST 数据
ast_nodes = await self.ast_node_dao.get_by_repository(shared_db, self.repo_uuid)

# 2. 读取文件内容
repo_path = await self._get_repo_path(shared_db)
files = await self.file_dao.list_by_repository(shared_db, self.repo_uuid, limit=500)

# 3. 运行 AnalysisGraph
llm_client = LLMClient()
agent_graph = AnalysisGraph(llm_client)
initial_state = AnalysisGraph.create_initial_state(repo_id, ast_data, code_snippets)
final_state = await agent_graph.run(initial_state)

# 4. 持久化到数据库
kp_dao = KnowledgePointDAO()
for kp in final_state["knowledge_points"]:
    kp_data = { "id": uuid.uuid4(), ..., "code_snippets": ..., "tags": ... }
    await kp_dao.create(shared_db, kp_data)
await shared_db.commit()
```

## 测试

### 测试覆盖

| 测试类 | 测试数量 | 覆盖内容 |
|--------|----------|---------|
| TestAnalysisState | 4 | 初始状态创建、去重、空列表边界 |
| TestKnowledgePointExtraction | 4 | 有效解析、默认值、TypeAdapter 列表、校验失败 |
| TestAnalysisNode | 2 | 基类 NotImplementedError、代码上下文构建 |
| TestDesignPatternNode | 3 | 成功执行、LLMError 处理、空响应 |
| TestArchitectureNode | 1 | 成功执行 |
| TestAlgorithmNode | 1 | 成功执行 |
| TestEngineeringNode | 1 | 成功执行 |
| TestDomainKnowledgeNode | 1 | 成功执行 |
| TestAnalysisGraph | 4 | 图创建、图信息、成功运行、错误传播、空数据 |
| TestParseResponse | 4 | JSON 数组、包装对象、空内容、无效 JSON fallback |
| **合计** | **27** | |

### CI 结果

| 检查项 | 结果 |
|--------|------|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 6 files already formatted |
| mypy | ✅ No issues found |
| pytest (agents) | ✅ 27 passed |
| pytest (agents + llm + knowledge) | ✅ **76 passed** |

## 变更文件清单

| 文件 | 操作 | 行数 |
|------|------|------|
| `codeinsight/prompts/domain.md` | **新增** | ~120 |
| `codeinsight/schemas/knowledge.py` | **修改** | +40 |
| `codeinsight/agents/state.py` | 无变更 | - |
| `codeinsight/agents/node.py` | **修改** | `_parse_response` 重构 + `_normalize_knowledge_points` 重写 |
| `codeinsight/agents/graph.py` | 无变更 | - |
| `codeinsight/tasks/analysis_orchestrator.py` | **修改** | Step 5 空壳 → 完整集成 |
| `tests/test_agents.py` | **新增** | 27 个测试用例 |

## 设计决策

### 为什么用 `TypeAdapter` 而不是 `response_model`？

`LLMClient.chat()` 的 `response_model` 参数只能接受单个 `BaseModel`，但 LLM 返回的是 JSON 数组。
`TypeAdapter(list[KnowledgePointExtraction])` 可以同时校验列表和元素，更灵活。

### 为什么 `knowledge_points` 保持 `list[dict]` 而非 `list[KnowledgePoint]`？

`KnowledgePoint` 是完整持久化模型，含 `id/uuid/version/repository_id/created_at` 等系统字段，
不适合作为中间状态。`KnowledgePointExtraction` 是轻量级 LLM 输出模型，仅含 LLM 可填写的字段。

### 为什么 orchestrator 集成不用 `KnowledgePointExtraction` 直接持久化？

Orchestrator 需要组装完整的 `KnowledgePoint` 行（含 `id`、`version`、`repository_id` 等系统字段），
因此持久化时直接组装 dict，而非使用 `KnowledgePointExtraction`。

## 后续任务 (P3-03)

- 多 Agent 并行编排：将线性串联改为并行执行，减少总耗时
- 跨节点知识合并：实现语义去重和知识融合
- 结果验证管道：自动评估知识点的置信度和准确性
- 增量分析：只分析变更的文件，复用已有结果