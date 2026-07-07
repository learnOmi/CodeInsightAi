# CodeInsight AI — 业务逻辑流程图

> 本文档描述 CodeInsight AI 系统的核心业务流程，使用 Mermaid 图表呈现。

---

## 目录

1. [仓库添加与分析全流程](#一仓库添加与分析全流程)
2. [增量分析流程](#二增量分析流程)
3. [知识点提取多 Agent 协作流程](#三点知识点提取多-agent-协作流程)
4. [前端用户操作流程](#四前端用户操作流程)
5. [代码链路构建流程](#五代码链路构建流程)
6. [搜索流程](#六搜索流程)
7. [版本管理与回滚流程](#七版本管理与回滚流程)
8. [错误处理与重试流程](#八错误处理与重试流程)

---

## 一、仓库添加与分析全流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant FE as 前端 (Next.js)
    participant API as 后端 API (FastAPI)
    participant CEL as Celery Worker
    participant SCAN as 代码扫描器
    participant TS as Tree-sitter 解析
    participant LG as LangGraph Agent
    participant LLM as LLM (Claude/GPT)
    participant DB as PostgreSQL
    participant MS as Meilisearch
    participant REDIS as Redis

    U->>FE: 输入仓库路径
    FE->>API: POST /api/v1/repositories
    API->>REDIS: 验证路径权限
    REDIS-->>API: 验证通过
    API->>DB: 创建 Repository 记录 (status=pending)
    API-->>FE: 201 {repository_id, task_id}
    FE->>U: 显示分析进度页面

    API->>CEL: 触发 analyze_repository 任务
    CEL->>SCAN: 执行代码扫描
    SCAN->>SCAN: GitPython 打开仓库
    SCAN->>SCAN: pathlib 递归收集源文件
    SCAN-->>CEL: 文件列表 + 元数据

    CEL->>TS: 批量 AST 解析
    TS->>TS: 检测文件语言类型
    TS->>TS: 生成语法树
    TS-->>CEL: 结构化数据 (函数/类/调用图)

    CEL->>DB: 保存结构数据 (status=analyzing)

    loop 每个代码模块
        CEL->>LG: 提交模块分析任务
        LG->>LLM: 发送代码片段 + Prompt
        LLM-->>LG: 知识点候选列表
        LG->>LG: Pydantic Schema 校验
        alt 校验失败
            LG->>LLM: 重试 (最多 3 次)
        else 校验通过
            LG->>DB: 保存知识点 + 向量嵌入
        end
    end

    CEL->>MS: 同步知识点全文索引
    CEL->>DB: 更新 Repository status=completed
    CEL->>REDIS: 推送 SSE 进度事件 (100%)

    FE->>API: GET /api/v1/knowledge-points?repository_id=xxx
    API->>DB: 查询知识点列表
    DB-->>API: 知识点数据
    API-->>FE: 200 {points: [...]}
    FE->>U: 渲染知识卡片列表
```

---

## 二、增量分析流程

```mermaid
flowchart TD
    A[用户修改代码并保存] --> B[触发增量分析]
    B --> C{上次分析是否存在?}
    C -->|否| D[执行全量分析]
    C -->|是| E[git diff 检测变更文件]
    
    E --> F[构建变更文件集合]
    F --> G[调用图反向遍历<br/>找出依赖文件]
    G --> H[确定重分析文件集合]
    
    H --> I{重分析文件数}
    I -->|0| J[无变化, 跳过]
    I -->|<= 10| K[直接分析]
    I -->|> 10| L[分批并行分析]
    
    K --> M[AST 解析 + AI 分析]
    L --> M
    
    M --> N[生成新版本号]
    N --> O[合并新旧知识点]
    O --> P[未受影响知识点<br/>标记沿用上一版本]
    P --> Q[更新 Meilisearch 索引]
    Q --> R[推送 SSE 完成事件]
    R --> S[前端刷新知识列表]
    
    D --> T[生成全新版本号]
    T --> S
```

**依赖传播算法伪代码：**

```python
def find_dependent_files(changed_files: set[str], call_graph: CallGraph) -> set[str]:
    """
    找出所有受变更文件影响的文件。
    策略：变更文件的所有调用方 + 被调用方。
    """
    affected = set(changed_files)
    queue = deque(changed_files)
    
    while queue:
        current = queue.popleft()
        # 上游依赖：谁调用了 current
        callers = call_graph.get_callers(current)
        # 下游依赖：current 调用了谁
        callees = call_graph.get_callees(current)
        
        for dep in callers | callees:
            if dep not in affected:
                affected.add(dep)
                queue.append(dep)
    
    return affected
```

---

## 三、知识点提取多 Agent 协作流程

```mermaid
flowchart LR
    subgraph INPUT["输入：结构化代码数据"]
        CODE[代码片段<br/>函数/类/模块]
        CTX[上下文：<br/>导入关系 + 调用图]
    end

    INPUT --> ROUTER[任务路由器<br/>LangGraph State]

    ROUTER --> AGENT1[设计模式<br/>检测 Agent]
    ROUTER --> AGENT2[架构决策<br/>识别 Agent]
    ROUTER --> AGENT3[算法复杂度<br/>分析 Agent]
    ROUTER --> AGENT4[工程技巧<br/>提取 Agent]
    ROUTER --> AGENT5[领域知识<br/>提取 Agent]

    AGENT1 --> VALIDATE[Schema 校验器]
    AGENT2 --> VALIDATE
    AGENT3 --> VALIDATE
    AGENT4 --> VALIDATE
    AGENT5 --> VALIDATE

    VALIDATE --> PASS{全部通过?}
    PASS -->|是| MERGE[结果合并管道]
    PASS -->|否| RETRY[重试 Agent<br/>最多 3 次]
    RETRY --> VALIDATE

    MERGE --> EXPANSION[拓展内容生成 Agent]
    EXPANSION --> EMBED[Embedding 向量化]
    EMBED --> STORE[(PostgreSQL<br/>+ pgvector)]
```

**各 Agent Prompt 结构模板：**

```
System Prompt:
你是 CodeInsight AI 的{AGENT_NAME}。你的任务是分析代码并识别{TARGET_PATTERN}。

分析规则：
1. {RULE_1}
2. {RULE_2}
3. {RULE_3}

输出格式（严格遵守 JSON Schema）：
{PYDANTIC_SCHEMA}

Few-shot 示例：
示例 1: {EXAMPLE_1}
示例 2: {EXAMPLE_2}
```

---

## 四、前端用户操作流程

```mermaid
flowchart TD
    START([用户访问应用]) --> HOME{是否已登录?}
    HOME -->|否| LOGIN[登录页]
    HOME -->|是| DASHBOARD[仪表盘]

    LOGIN --> AUTH_SUCCESS{认证通过?}
    AUTH_SUCCESS -->|否| LOGIN
    AUTH_SUCCESS -->|是| DASHBOARD

    DASHBOARD --> ACTION{用户操作}

    ACTION -->|添加仓库| ADD_REPO[输入仓库路径]
    ADD_REPO --> VERIFY{路径有效?}
    VERIFY -->|否| ADD_REPO
    VERIFY -->|是| ANALYZING[开始分析<br/>显示进度条]

    ACTION -->|查看知识| KB_LIST[知识卡片列表]
    KB_LIST --> FILTER[筛选：分类/标签/仓库]
    FILTER --> CARD_CLICK[点击知识卡片]

    ACTION -->|搜索| SEARCH_BAR[输入搜索关键词]
    SEARCH_BAR --> SEARCH_RESULTS[Meilisearch 即时搜索结果]
    SEARCH_RESULTS --> RESULT_CLICK[点击结果]

    CARD_CLICK --> DETAIL[知识点详情页]
    RESULT_CLICK --> DETAIL

    DETAIL --> TAB{选择标签页}
    TAB -->|简介| INTRO[知识点简介 + 分类标签]
    TAB -->|代码链路| CALL_CHAIN[代码链路查看器<br/>Shiki 高亮 + 行号]
    TAB -->|拓展内容| EXPANSION[AI 生成的拓展说明]

    CALL_CHAIN --> FILE_NAV[文件导航面板]
    FILE_NAV --> LINE_JUMP[跳转到指定行]
    LINE_JUMP --> HIGHLIGHT[高亮关键代码行]

    EXPANSION --> LEARNING_RES[相关学习资料链接]

    ANALYZING --> PROGRESS_UPDATE[SSE 实时进度推送]
    PROGRESS_UPDATE --> COMPLETE{分析完成?}
    COMPLETE -->|否| ANALYZING
    COMPLETE -->|是| KB_LIST
```

---

## 五、代码链路构建流程

```mermaid
flowchart TD
    START([点击知识点]) --> FETCH[获取知识点关联数据]
    
    FETCH --> LINKS[code_snippets + call_chain]
    
    LINKS --> BUILD_CHAIN{是否有预构建链路?}
    BUILD_CHAIN -->|是| RENDER[渲染已有链路]
    BUILD_CHAIN -->|否| CONSTRUCT[动态构建调用链]
    
    CONSTRUCT --> CURRENT[当前知识点代码位置]
    CURRENT --> UPSTREAM[BFS 向上游追溯<br/>查找调用者]
    DOWNSTREAM[BFS 向下游追溯<br/>查找被调用者]
    UPSTREAM --> BOTH[合并上下链路]
    DOWNSTREAM --> BOTH
    
    BOTH --> DEDUP[去重 + 排序]
    DEDUP --> FORMAT[格式化为链路节点]
    FORMAT --> STORE_CACHE[缓存到 Redis]
    STORE_CACHE --> RENDER
    
    RENDER --> SHOW[前端展示]
    
    SHOW --> HIGHLIGHT[Shiki 语法高亮]
    HIGHLIGHT --> MARK[标记关键行]
    MARK --> NAV[文件导航面板]
    NAV --> END([用户交互])
```

**调用链 BFS 算法：**

```python
def build_call_chain(
    start_node: ASTNode,
    call_graph: CallGraph,
    direction: str = "both",  # "upstream" | "downstream" | "both"
    max_depth: int = 5
) -> list[CallChainNode]:
    """
    从起始节点出发，BFS 遍历调用图构建完整链路。
    """
    chain = []
    visited = set()
    queue = deque([(start_node, 0)])
    
    while queue:
        node, depth = queue.popleft()
        if node.id in visited or depth > max_depth:
            continue
        visited.add(node.id)
        
        chain.append(CallChainNode(
            node_id=node.id,
            node_type=node.type,
            file=node.file,
            lines=node.lines,
            signature=node.signature
        ))
        
        if direction in ("upstream", "both"):
            for caller in call_graph.get_callers(node):
                queue.append((caller, depth + 1))
        
        if direction in ("downstream", "both"):
            for callee in call_graph.get_callees(node):
                queue.append((callee, depth + 1))
    
    return sorted_by_execution_order(chain)
```

---

## 六、搜索流程

```mermaid
flowchart LR
    USER[用户输入搜索词] --> FE[前端 TanStack Query]
    FE -->|防抖 300ms| API[GET /api/v1/search?q=xxx]
    
    API --> TYPE_CHECK{搜索类型}
    TYPE_CHECK -->|全文搜索| MEILI[Meilisearch 查询]
    TYPE_CHECK -->|向量搜索| PGVECTOR[pgvector 相似度搜索]
    TYPE_CHECK -->|混合搜索| HYBRID[加权合并结果]
    
    MEILI --> RE_RANK[重排序：相关性 + 时间衰减]
    PGVECTOR --> RE_RANK
    HYBRID --> RE_RANK
    
    RE_RANK --> PAGINATE[分页处理]
    PAGINATE --> RESP[返回搜索结果]
    
    RESP --> FE
    FE --> DISPLAY[前端渲染结果列表]
    
    DISPLAY --> CLICK[点击结果]
    CLICK --> DETAIL[跳转知识点详情页]
```

**搜索权重配置：**

```yaml
search:
  meilisearch:
    attributes_to_search_on: [title, description, tags]
    limit: 20
    offset: 0
  
  vector_search:
    embedding_model: text-embedding-3-small
    top_k: 10
    similarity_threshold: 0.75
  
  hybrid:
    meilisearch_weight: 0.6
    vector_weight: 0.4
    rerank_model: cross-encoder-ms-marco-MiniLM-L-6-v2
```

---

## 七、版本管理与回滚流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant FE as 前端
    participant API as 后端 API
    participant DB as PostgreSQL

    U->>FE: 选择仓库
    FE->>API: GET /api/v1/repositories/{id}/versions
    DB->>DB: 查询该仓库所有分析版本
    DB-->>API: 版本列表 [v1, v2, v3]
    API-->>FE: 200 {versions: [...]}
    FE->>U: 显示版本选择器

    U->>FE: 选择版本 v2
    FE->>API: GET /api/v1/repositories/{id}/knowledge?version=v2
    DB->>DB: 查询 version='v2' 的知识点
    DB-->>API: 知识点数据
    API-->>FE: 200 {points: [...], version: 'v2'}
    FE->>U: 渲染 v2 版本的知识点

    U->>FE: 点击"回滚到此版本"
    FE->>API: POST /api/v1/repositories/{id}/rollback
    API->>DB: 将 repository.current_version 更新为 v2
    DB-->>API: 更新成功
    API-->>FE: 200 {message: "已回滚到 v2"}
    FE->>U: 显示成功提示 + 刷新知识列表
```

---

## 八、错误处理与重试流程

```mermaid
flowchart TD
    TASK[Celery 任务执行] --> EXEC{执行阶段}
    
    EXEC -->|代码扫描| SCAN_ERR{扫描失败?}
    SCAN_ERR -->|是| SCAN_RETRY[重试 ≤ 3 次]
    SCAN_ERR -->|否| PARSE
    SCAN_RETRY --> SCAN_MAX{超过最大重试?}
    SCAN_MAX -->|是| SCAN_FAIL[标记任务失败]
    SCAN_MAX -->|否| SCAN_ERR
    
    PARSE[Tree-sitter 解析] --> PARSE_ERR{解析失败?}
    PARSE_ERR -->|是| PARSE_SKIP[跳过文件 + 记录日志]
    PARSE_ERR -->|否| AGENT
    PARSE_SKIP --> AGENT[LangGraph Agent]
    
    AGENT --> AGENT_ERR{Agent 执行失败?}
    AGENT_ERR -->|是| AGENT_RETRY[重试 ≤ 3 次]
    AGENT_ERR -->|否| LLM_REQ
    AGENT_RETRY --> AGENT_MAX{超过最大重试?}
    AGENT_MAX -->|是| AGENT_FAIL[标记模块分析失败]
    AGENT_MAX -->|否| AGENT_ERR
    
    LLM_REQ[LLM API 调用] --> LLM_ERR{API 失败?}
    LLM_ERR -->|Rate Limit| LLM_WAIT[等待退避<br/>Exponential Backoff]
    LLM_ERR -->|Timeout| LLM_RETRY[重试 ≤ 2 次]
    LLM_ERR -->|正常响应| STORE
    LLM_WAIT --> LLM_REQ
    LLM_RETRY --> LLM_MAX{超过最大重试?}
    LLM_MAX -->|是| LLM_FAIL[降级：使用缓存结果]
    LLM_MAX -->|否| LLM_REQ
    
    STORE[数据入库] --> DB_ERR{入库失败?}
    DB_ERR -->|是| DB_RETRY[重试 ≤ 3 次]
    DB_ERR -->|否| DONE
    DB_RETRY --> DB_MAX{超过最大重试?}
    DB_MAX -->|是| DB_FAIL[任务标记失败 + 告警]
    DB_MAX -->|否| STORE
    
    SCAN_FAIL --> NOTIFY[通知用户]
    AGENT_FAIL --> NOTIFY
    LLM_FAIL --> NOTIFY
    DB_FAIL --> NOTIFY
    
    NOTIFY --> END([流程结束])
```

**错误码定义：**

| 错误码 | HTTP Status | 说明 | 处理建议 |
|--------|------------|------|----------|
| `REPO_NOT_FOUND` | 404 | 仓库不存在 | 检查 repository_id |
| `REPO_PATH_INVALID` | 400 | 仓库路径无效 | 验证路径权限 |
| `TASK_NOT_FOUND` | 404 | 分析任务不存在 | 检查 task_id |
| `TASK_ALREADY_RUNNING` | 409 | 分析任务正在运行 | 等待或取消已有任务 |
| `TASK_FAILED` | 422 | 分析任务失败 | 查看 error_message |
| `KNOWLEDGE_NOT_FOUND` | 404 | 知识点不存在 | 检查 knowledge_point_id |
| `VERSION_NOT_FOUND` | 404 | 版本号不存在 | 检查版本号是否正确 |
| `SEARCH_ERROR` | 500 | 搜索服务异常 | 联系管理员 |
| `LLM_RATE_LIMIT` | 429 | LLM API 限流 | 自动退避重试 |
| `LLM_QUOTA_EXCEEDED` | 402 | LLM API 配额用尽 | 升级套餐或使用本地模型 |

---

## 附录：数据模型关系图

```mermaid
erDiagram
    REPOSITORY ||--o{ ANALYSIS_VERSION : "has"
    REPOSITORY ||--o{ KNOWLEDGE_POINT : "contains"
    ANALYSIS_VERSION ||--o{ KNOWLEDGE_POINT : "includes"
    
    KNOWLEDGE_POINT ||--o{ CODE_SNIPPET : "has"
    KNOWLEDGE_POINT ||--o{ CALL_CHAIN_NODE : "has"
    KNOWLEDGE_POINT ||--o{ EXPANSION_CONTENT : "has"
    
    KNOWLEDGE_POINT }|--|| KNOWLEDGE_CATEGORY : "belongs to"
    
    FILE ||--o{ AST_NODE : "contains"
    AST_NODE }|--|| FILE : "calls"
    AST_NODE }|--|| AST_NODE : "imports"
    
    REPOSITORY {
        uuid id PK
        string name
        string path
        string current_version
        timestamp created_at
    }
    
    ANALYSIS_VERSION {
        uuid id PK
        uuid repository_id FK
        string version_tag
        string status
        int total_files
        int knowledge_points_count
        timestamp created_at
    }
    
    KNOWLEDGE_POINT {
        uuid id PK
        uuid repository_id FK
        string version
        string category
        string title
        text description
        jsonb metadata
        vector embedding
        timestamp created_at
    }
    
    KNOWLEDGE_CATEGORY {
        string code PK "DP- / AD- / AL- / ET- / DK-"
        string name
        text definition
    }
    
    CODE_SNIPPET {
        uuid id PK
        uuid knowledge_point_id FK
        string file_path
        int start_line
        int end_line
        jsonb highlighted_lines
    }
```
