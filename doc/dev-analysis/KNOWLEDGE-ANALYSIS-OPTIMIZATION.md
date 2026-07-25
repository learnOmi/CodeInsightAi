# CodeInsight AI 知识分析优化方案

> **版本**: v2.0 — 基于实际代码库的验证与完善
> **最后更新**: 2026-07-25
> **状态**: 已验证 — 本报告所有问题描述均经过代码审查确认，并补充了遗漏的关键发现。

---

## 目录

1. [知识提取深度优化](#1-知识提取深度优化)
2. [超长上下文的连续性管理](#2-超长上下文的连续性管理)
3. [仓库创建后的自动分析流程优化](#3-仓库创建后的自动分析流程优化)
4. [增加"开发技巧/开发模板"分类](#4-增加开发技巧开发模板分类)
5. [增加"第三方库/技术栈"分类](#5-增加第三方库技术栈分类)
6. **[新增] 增量分析知识点保留策略优化**
7. **[新增] LLM 调用成本与速率控制**
8. **[新增] Prompt 模板质量提升**
9. **[新增] 前端 SSE 进度展示优化**
10. [总体实施建议](#10-总体实施建议)
11. [附录：当前系统架构概览](#附录当前系统架构概览)

---

## 1. 知识提取深度优化

### 当前问题分析

每个 Agent 的提取质量受限于以下因素（均已通过代码审查验证）：

| 瓶颈 | 当前值 | 代码位置 | 影响 |
|------|--------|----------|------|
| `MAX_CODE_SNIPPETS` | **20** 个 | [node.py:33](codeinsight-backend/codeinsight/agents/node.py:33) | 大型项目只能看到局部代码 |
| `MAX_CODE_CHARS_PER_SNIPPET` | **1000** 字符 | [node.py:34](codeinsight-backend/codeinsight/agents/node.py:34) | 函数体经常被截断，丢失关键逻辑 |
| `max_tokens` (LLMConfig) | **4096** | [client.py:54](codeinsight-backend/codeinsight/llm/client.py:54) | 输出受限，AI 只能写简短描述 |
| 代码上下文构建 | 简单拼接 | [node.py:204-258](codeinsight-backend/codeinsight/agents/node.py:204-258) | 缺少文件结构关系、依赖信息 |
| 单一 LLM 调用 | 每个分类一次 | [graph.py:32-38](codeinsight-backend/codeinsight/agents/graph.py:32-38) | 无法从不同角度挖掘同一代码库 |
| prompt 固定性 | 不随代码库类型调整 | [prompts/*.md](codeinsight-backend/codeinsight/prompts/) | 对不同类型代码库缺乏针对性 |
| AST fallback 限制 | ast_data[:500] | [node.py:226](codeinsight-backend/codeinsight/agents/node.py:226) | 当 code_snippets 为空时，AST 摘要只取前 500 节点 |

### 已实现的优化（报告中未记录）

在 [analysis_orchestrator.py:1565-1586](codeinsight-backend/codeinsight/tasks/analysis_orchestrator.py:1565-1586) 中，代码片段加载已改进为：
- 移除了 500 条文件限制（O-B11）
- 每个文件支持最多 5000 字符的代码内容
- 增加了读取失败的容错处理

但在 [node.py:252-257](codeinsight-backend/codeinsight/agents/node.py:252-257) 中，`MAX_CODE_SNIPPETS=20` 和 `MAX_CODE_CHARS_PER_SNIPPET=1000` 仍然限制了最终送入 LLM 的内容量。**这是矛盾点：加载了更多数据，但只用了 20 个 × 1000 字符。**

### 优化方案

#### 方案 A：上下文增强（低风险，立即见效）— **推荐优先实施**

1. **动态代码上下文大小**
   - 将 `MAX_CODE_SNIPPETS` 从 20 提高到 **40-50**
   - 将 `MAX_CODE_CHARS_PER_SNIPPET` 从 1000 提高到 **3000-5000**（与加载上限对齐）
   - 加入智能截断策略：优先保留 `def/class/async def` 的完整定义
   - 加入文件依赖信息（import 语句、文件结构）

2. **提高 max_tokens**
   - 将 `max_tokens` 从 4096 提高到 **8192**（可配置）
   - 或根据代码上下文大小动态计算：`min(8192, context_window * 0.2)`

3. **Prompt 增强**
   - 加入"深度挖掘"指令："请深入分析代码结构，识别隐藏的复用模式、隐含的设计意图"
   - 要求 AI 对每个知识点给出"反例"（什么时候不应该使用）
   - 增加"改进建议"字段

4. **修复 AST fallback 限制**
   - 将 [node.py:226](codeinsight-backend/codeinsight/agents/node.py:226) 中的 `ast_data[:500]` 改为动态比例（如 `min(len(ast_data), 2000)`）

#### 方案 B：多轮提取（中风险，效果更好）

1. **两轮提取策略**
   - 第一轮：全局扫描，提取所有可能的知识点（低精度门槛）
   - 第二轮：对每个知识点深度分析，提取更多细节和关联
   - 通过 LangGraph 条件边实现：`extract → refine → merge`

2. **递归提取**
   - 对大型代码库，先按目录分组提取
   - 然后合并各组的知识点
   - 避免单次 LLM 调用上下文过大

#### 方案 C：模型升级（需要配置）

1. 使用更强模型（Claude-4 / GPT-4.1）
2. 使用长上下文模型处理更多代码
3. 使用专用代码分析模型（CodeLlama / DeepSeek-Coder）

### 推荐实施顺序

1. 先做方案 A（2 天）
2. 评估效果后做方案 B（5 天）
3. 根据业务需要决定是否升级模型

### 代码修改点（修正版）

```
codeinsight/agents/node.py:
  - MAX_CODE_SNIPPETS: 20 → 50
  - MAX_CODE_CHARS_PER_SNIPPET: 1000 → 5000（与 orchestrator 加载上限对齐）
  - _build_code_context(): 增加文件结构信息、依赖关系
  - ast_data fallback: [:500] → [:min(len(ast_data), 2000)]
  - _build_messages(): 加入深度挖掘指令

codeinsight/llm/client.py:
  - LLMConfig.max_tokens: 4096 → 8192（可配置）

codeinsight/prompts/base.md:
  - 加入"深度挖掘"章节
  - 增加"改进建议"输出字段
  - 加入 Few-shot 示例展示深度分析
```

---

## 2. 超长上下文的连续性管理

### 当前问题分析

当代码库很大时，单次 LLM 调用的输入输出可能超过上下文窗口：

- Claude-3.5 Sonnet: 200k tokens
- GPT-4: 128k tokens
- 单个 Agent 可能需要的上下文：50 snippets × 5000 chars = 250k chars ≈ 62.5k tokens
- 加上 prompt 模板（~10k tokens）和输出（~10k tokens），总计可能接近或超过上下文窗口

**已实现的保护机制**：[node.py:184-200](codeinsight-backend/codeinsight/agents/node.py:184-200) 已有 Token 数估算和 80% 阈值警告，但仅记录日志，不采取主动措施。

### 核心矛盾：拆分 vs 调用次数

**关键问题**：将代码库拆分为多个 chunk 意味着对每个 chunk 都要调用 LLM，这会显著增加 API 调用次数和成本。对于普通规模的代码库（<500 文件），单次调用完全能容纳，拆分反而浪费。

**当前架构的隐式设计**：不拆分，靠裁剪适配上下文窗口。

| 机制 | 位置 | 作用 |
|------|------|------|
| `MAX_CODE_SNIPPETS=20` | [node.py:33](codeinsight-backend/codeinsight/agents/node.py:33) | 天然限制输入规模 |
| `MAX_CODE_CHARS_PER_SNIPPET=1000` | [node.py:34](codeinsight-backend/codeinsight/agents/node.py:34) | 控制单条消息体积 |
| Token 80% 阈值告警 | [node.py:184-200](codeinsight-backend/codeinsight/agents/node.py:184-200) | 超过时记录日志，静默继续 |

按当前配置估算：20 snippets × 1000 chars ≈ 5k tokens，加上 prompt ~10k tokens，总计约 15k tokens，远低于 Claude-3.5 Sonnet 的 200k 和 GPT-4 的 128k。**绝大多数代码库不需要拆分。**

### 拆分决策树

```
是否需要拆分？
│
├─ 文件数 < 500？
│  └─ 是 → 不拆分。当前 MAX_CODE_SNIPPETS + MAX_CODE_CHARS 足够。
│
├─ 单个 Agent 的 Token 估算 > 上下文窗口的 60%？
│  └─ 是 → 进入下一步判断
│  └─ 否 → 不拆分
│
└─ 代码库是否可自然分目录？
   ├─ 是 → 方案 C：任务分片（按目录拆分，各目录独立调用 LLM）
   │        适用场景：微服务、monorepo 中不同子系统
   │        代价：N 倍 LLM 调用次数
   │
   └─ 否 → 方案 B：自适应上下文窗口
            根据可用 token 动态调整 snippet 数量和大小
            代价：可能丢失部分代码上下文
```

### 优化方案

#### 方案 A：不拆分 — 动态上下文窗口（推荐用于大多数情况）

不做任何拆分，而是根据实际 token 用量动态调整送入 LLM 的代码量：

```python
async def _build_code_context(self, state: AnalysisState) -> str:
    snippets = state.get("code_snippets", [])
    
    # 先估算 prompt 模板的 token 数
    prompt_tokens = await self._estimate_prompt_tokens()
    
    # 计算剩余可用 token（保守估计，保留 40% 给输出）
    available_tokens = int(128_000 * 0.6) - prompt_tokens
    
    # 动态决定能放多少个 snippet
    avg_snippet_tokens = 250  # 1000 chars ≈ 250 tokens
    max_snippets = min(len(snippets), available_tokens // avg_snippet_tokens)
    
    # 取前 N 个最相关的片段（按文件复杂度排序）
    return self._format_snippets(snippets[:max_snippets])
```

**优点**：
- 零额外 LLM 调用
- 自动适应不同大小的代码库
- 与现有 80% 告警机制互补

**缺点**：
- 极端大仓库仍可能丢失上下文

#### 方案 B：超大文件分块（仅针对单文件超限）

当**单个文件**超过上下文窗口时才拆分：

```
超大文件 → 按函数/类分割 → 每个 chunk 独立分析 → 合并结果
```

- 只对文件数 > 1000 或最大文件 > 5000 行的仓库启用
- 使用滑动窗口：chunk_n 的末尾包含 chunk_{n-1} 的最后 10 行以保持上下文连贯
- 最终合并所有 chunk 的分析结果，按 title 去重

**代价**：一个超大文件可能需要 3-5 次 LLM 调用

#### 方案 C：任务分片 + 并行（仅适用于可分目录的大仓库）

```
Task 1: 分析 src/frontend/ + src/shared/
Task 2: 分析 src/backend/
Task 3: 分析 src/services/
...
```

- 每个子任务独立调用 LLM，最后合并知识点
- **仅在仓库文件数 > 2000 且可按目录自然分组时启用**
- 通过 Redis 存储各分片进度，支持断点续传

**代价**：N 倍 LLM 调用次数，但可并行执行

### 推荐实施

1. **默认不拆分** — 保持现有架构不变，先完成第 1 章的上下文增强（提高 MAX_CODE_SNIPPETS 和 MAX_CODE_CHARS）
2. **动态上下文窗口** — 在 node.py 中实现方案 A，根据实际 token 用量动态调整 snippet 数量
3. **按需启用分片** — 仅当代码库规模触发阈值（文件数 > 2000）时，才启用方案 C 的分片逻辑

### 代码修改点

```
codeinsight/agents/node.py:
  - _build_code_context(): 增加动态 token 感知裁剪逻辑
  - _estimate_prompt_tokens(): 新增方法，估算 prompt 模板 token 数
  - execute(): 可选参数 enable_chunking=False，默认不拆分

codeinsight/agents/state.py:
  - 仅在 enable_chunking=True 时增加 chunk_progress/chunk_results 字段

codeinsight/tasks/analysis_orchestrator.py:
  - 增加代码库规模检测（文件数、最大文件大小）
  - 根据规模决定是否启用分片模式
```

---

## 3. 仓库创建后的自动分析流程优化

### 当前问题分析

**现状**（已在代码中验证）：

```
用户勾选"自动分析" → POST /api/v1/repositories →
  1. 创建仓库记录
  2. 调用 _trigger_analysis()
  3. Eager 模式（默认）：同步执行整个分析流程（5-10 分钟）
  4. 返回响应（包含 repo 对象）
  5. 前端收到响应后跳转
```

**关键代码**：[repositories.py:68-82](codeinsight-backend/codeinsight/api/repositories.py:68-82) 和 [analysis.py:198-377](codeinsight-backend/codeinsight/api/analysis.py:198-377)

**问题**：

| 问题 | 当前状态 | 影响 |
|------|----------|------|
| HTTP 请求阻塞 | eager 模式下同步执行 | 浏览器等待响应可能超时 |
| 用户无法操作 | 整个页面卡住直到分析完成 | 差的用户体验 |
| 错误处理困难 | 分析失败时用户不知道原因 | 仅通过响应头传递错误 |
| 资源浪费 | 同步执行占用 worker 进程 | 并发能力受限 |
| celery_task_always_eager | **默认为 True** ([config.py:109](codeinsight-backend/codeinsight/config.py:109)) | 生产环境也需手动修改 |

### 已实现的功能（报告中未记录）

1. **SSE 实时推送**：[analysis.py:517-588](codeinsight-backend/codeinsight/api/analysis.py:517-588) 已实现 `/tasks/{task_id}/stream` SSE 端点
2. **前端 SSE Hook**：[use-sse.ts](codeinsight-frontend/src/hooks/use-sse.ts) 已实现 `useSSE()` React hook
3. **异步任务支持**：非 eager 模式下已通过 Celery 提交异步任务
4. **任务取消**：[analysis.py:460-514](codeinsight-backend/codeinsight/api/analysis.py:460-514) 已实现取消功能
5. **Eager 模式超时保护**：[analysis.py:278-282](codeinsight-backend/codeinsight/api/analysis.py:278-282) 设置了 600s 超时

### 优化方案

#### 方案 A：异步任务 + 轮询（推荐，行业标准做法）

1. **后端修改**
   - 生产环境设置 `celery_task_always_eager = False`
   - 创建仓库时始终返回 task_id（无论 eager 还是异步）
   - 添加 `X-Task-Id` 响应头

2. **前端修改**
   - 创建仓库后立即跳转，不等待分析完成
   - 使用 `useSSE()` hook 监听实时进度
   - 分析完成后自动刷新知识库数据

#### 方案 B：WebSocket/SSE 实时推送（已部分实现）

SSE 端点已存在，但前端在创建仓库后**没有自动连接 SSE**。需要：
- 在 RepoForm 或 Repositories 页面中添加 SSE 连接逻辑
- 将 SSE 进度展示到 UI 上

### 推荐实施

1. **立即实施**：修改 `create_repository` 始终返回 task_id
   - 前端使用 `useSSE(taskId)` 监听进度
   - 保持向后兼容（开发环境仍可用 eager 模式）

2. **后续优化**：完善 SSE 前端集成
   - 添加分析进度横幅组件
   - 在仓库列表页显示"分析进行中"状态

### 代码修改点

```
codeinsight/config.py:
  - celery_task_always_eager: True → False（生产环境）
  - 添加环境变量区分 dev/prod 默认值

codeinsight/api/repositories.py:
  - create_repository 始终返回 task_id（通过响应头或响应体）
  - 移除 eager 模式下的同步等待逻辑

codeinsight-frontend/src/api/repositories.ts:
  - createRepository 返回类型增加 task_id 字段

codeinsight-frontend/src/components/RepoForm.tsx:
  - 创建仓库后获取 task_id
  - 使用 useSSE(taskId) 监听进度

codeinsight-frontend/src/app/repositories/page.tsx:
  - 添加分析进度展示组件
  - 分析完成后自动刷新数据
```

---

## 4. 增加"开发模板/代码模板"分类

### 当前分类

| 分类码 | 名称 | 描述 |
|--------|------|------|
| DP | 设计模式 | GoF 设计模式及常见工程模式 |
| AD | 架构决策 | 系统架构风格和决策 |
| AL | 算法实现 | 经典算法和数据结构 |
| ET | 工程技巧 | 工程最佳实践 |
| DK | 领域知识 | 业务领域知识 |

**枚举定义**：[schemas/knowledge.py:21-36](codeinsight-backend/codeinsight/schemas/knowledge.py:21-36)
**常量定义**：[schemas/constants.py:7-15](codeinsight-backend/codeinsight/schemas/constants.py:7-15)

### 建议新增分类

**分类码**：`TT` (Template/Technique)

**名称**：开发模板/代码模板

**定义**：识别项目中反复出现的代码模板、脚手架模式、样板代码模式，以及可复用的代码骨架。

**示例场景**：

| 模板类型 | 示例 |
|----------|------|
| CRUD 模板 | Repository pattern, Service layer, DTO mapping |
| API 模板 | RESTful API 结构, GraphQL resolver, gRPC service |
| 测试模板 | Unit test fixture, Integration test pattern, Mock setup |
| 配置模板 | Spring Boot config, Django settings, TypeScript config |
| 事件处理模板 | Event listener pattern, Message queue consumer, Webhook handler |
| 中间件模板 | Auth middleware, Logging middleware, Error handling middleware |
| 数据迁移模板 | Database migration script, Data import/export, Schema evolution |
| 部署模板 | Dockerfile pattern, CI/CD pipeline, Kubernetes manifest |

**与现有分类的区别**：

| 对比项 | ET (工程技巧) | TT (开发模板) |
|--------|---------------|---------------|
| 关注点 | 通用工程最佳实践 | 具体代码结构模板 |
| 粒度 | 抽象原则 | 具体代码骨架 |
| 示例 | "使用重试模式" | "Spring Boot Controller 模板" |
| 适用性 | 跨项目通用 | 项目/框架特定 |

### Prompt 模板设计

```markdown
# 开发模板分析 Agent

你是资深软件架构师，擅长识别代码中的**模板模式**和**代码骨架**。

## 任务
分析代码，识别以下类型的开发模板：

1. **CRUD 模板**：标准的增删改查代码结构
2. **API 模板**：RESTful API 的 Controller/Service/Repository 分层
3. **测试模板**：测试用例的 Fixture/Mock/Assertion 结构
4. **配置模板**：框架配置的标准模式
5. **事件处理模板**：事件驱动的代码结构
6. **中间件模板**：请求/响应处理链的代码结构
7. **数据迁移模板**：数据库迁移和数据处理的代码结构
8. **部署模板**：容器化、CI/CD、K8s 的代码结构

## 输出格式
（与现有格式相同，category 改为 "TT"）

## 判断标准
- 是否有标准的分层结构（Controller → Service → Repository）
- 是否有模板方法模式（抽象类 + 具体实现）
- 是否有代码生成器模式（scaffold、template）
- 是否有标准的配置结构（properties、settings、config）
```

### 实施计划

1. **后端**
   - 添加 `tt.md` prompt 模板
   - 修改 `node.py` 添加 `TemplateTechniqueNode` 类
   - 修改 `state.py` 和 `graph.py` 支持新节点
   - 修改 `knowledge_point.py` 模型支持 `TT` 分类

2. **前端**
   - 添加 `TT` 分类的 UI 标签和颜色
   - 修改筛选器支持新分类

3. **数据迁移**
   - 为现有数据添加 `TT` 分类（如果需要）
   - 更新枚举值

### 代码修改点（精确到行）

```
codeinsight/prompts/tt.md:
  - 新建开发模板分析 prompt

codeinsight/agents/node.py:
  - 第 20-26 行 imports: 添加 load_template_technique_prompt
  - 第 33-34 行后: 无新增常量
  - 第 563 行后: 添加 TemplateTechniqueNode 类
  - _build_code_context 不变

codeinsight/agents/graph.py:
  - 第 32-38 行 ANALYSIS_NODES: 添加 ("template_technique", "开发模板分析")
  - 第 41-47 行 CATEGORY_TO_NODE: 添加 "TT": "template_technique"
  - 第 136-141 行: 添加 template_technique_node 实例
  - 第 145-149 行: 注册节点
  - 第 157-158 行: 添加汇聚边

codeinsight/prompts/__init__.py:
  - 添加 load_template_technique_prompt() 函数

codeinsight/schemas/knowledge.py:
  - KnowledgeCategory 枚举: 添加 TEMPLATE_TECHNIQUE = "TT"

codeinsight/schemas/constants.py:
  - CATEGORY_NAMES: 添加 "TT": "开发模板"
  - CATEGORY_LIST: 添加 "TT"

codeinsight-frontend/src/constants.ts:
  - 添加 TT 的 label 和 color

codeinsight-frontend/src/app/knowledge/page.tsx:
  - 添加 TT 到分类筛选器
```

---

## 5. 增加"第三方库/技术栈"分类

### 分类定位

识别并记录项目中使用的**第三方库、框架、中间件**及其使用方式，形成项目技术栈的自动化文档。

**分类码**：`TK` (Technology/Toolkit)

**名称**：技术栈/第三方库

**与现有分类的关系**：

| 分类 | 关注点 | 示例 |
|------|--------|------|
| AD (架构决策) | 为什么选这个架构 | "选择微服务架构以降低系统耦合度" |
| ET (工程技巧) | 怎么用工程方法 | "使用熔断器防止级联故障" |
| TT (开发模板) | 代码结构是什么 | "标准 CRUD 三层架构" |
| **TK (技术栈)** | **用了什么库** | "使用 Pydantic 2.x 做数据验证" |
| DK (领域知识) | 业务逻辑是什么 | "知识提取的业务流程" |

### 分析维度

| 维度 | 说明 |
|------|------|
| 库名称 | 第三方库的准确名称 |
| 版本信息 | 代码中体现的版本（如有） |
| 用途 | 该库在项目中的具体用途 |
| 关键用法 | 代码中实际使用到的 API、模式、配置 |
| 使用场景 | 项目中的具体业务场景 |
| 替代方案 | 同类库的对比（如有） |
| 注意事项 | 版本兼容性、已知限制、配置坑 |

### 典型识别场景

```
TK-PYDANTIC
  库名：Pydantic
  用途：数据验证和配置管理
  关键用法：BaseModel, Field, ConfigDict(extra="ignore"), model_validator
  场景：API Schema 定义、Settings 管理、LLM 输出校验
  版本：2.x

TK-REDIS
  库名：Redis
  用途：缓存、任务状态管理、Pub/Sub 消息队列
  关键用法：asyncio + aioredis, get/set 键值操作, pubsub 发布订阅
  场景：Celery 任务映射、取消标志、分析进度缓存
  版本：7.x

TK-LANGGRAPH
  库名：LangGraph
  用途：LLM Agent 工作流编排
  关键用法：StateGraph, add_node, add_conditional_edges, Send API
  场景：知识提取的 Fan-Out/Fan-In 并行架构
  版本：1.x

TK-CLOUDE
  库名：Anthropic Claude API
  用途：大语言模型推理
  关键用法：Anthropic SDK, chat completions, JSON Schema 约束
  场景：代码分析、知识提取、拓展内容生成
  版本：Claude-3.5-Sonnet

TK-FASTAPI
  库名：FastAPI
  用途：Web API 框架
  关键用法：APIRouter, Depends, HTTPException, Annotated
  场景：RESTful API 服务、异步请求处理
  版本：0.100+

TK-COMPOSER (前端)
  库名：@tanstack/react-query
  用途：服务端状态管理
  关键用法：useQuery, useMutation, invalidateQueries
  场景：知识库数据获取、任务状态轮询
```

### 实施价值

1. **自动化的技术栈文档** — 无需人工维护 README 中的技术栈章节
2. **快速发现隐藏依赖** — 有些库的使用可能没有文档记录
3. **依赖升级决策支持** — 了解库的使用深度，评估升级风险
4. **安全扫描辅助** — 识别项目中所有第三方依赖，便于漏洞排查
5. **技术债务识别** — 识别过时的库版本或不必要的依赖

### 实施计划

与 TT 分类类似，需要：

1. **后端**
   - 添加 `tk.md` prompt 模板
   - 修改 `node.py` 添加 `TechnologyStackNode` 类
   - 修改 `state.py` 和 `graph.py` 支持新节点
   - 修改 `knowledge_point.py` 模型支持 `TK` 分类

2. **前端**
   - 添加 `TK` 分类的 UI 标签和颜色
   - 修改筛选器支持新分类

3. **数据迁移**
   - 更新枚举值
   - 为现有数据添加 `TK` 分类（如果需要）

### 代码修改点

```
codeinsight/prompts/tk.md:
  - 新建第三方库分析 prompt

codeinsight/agents/node.py:
  - 添加 TechnologyStackNode 类
  - 添加到 ANALYSIS_NODES 列表

codeinsight/agents/state.py:
  - 修改 progress 值（TK → 1.3）

codeinsight/agents/graph.py:
  - 添加 technology_stack 节点
  - 添加到条件路由

codeinsight/schemas/knowledge.py:
  - 添加 TK 到 KnowledgeCategory 枚举

codeinsight-frontend/src/constants.ts:
  - 添加 TK 的 label 和 color

codeinsight-frontend/src/app/knowledge/page.tsx:
  - 添加 TK 到分类筛选器
```

---

## 6. [新增] 增量分析知识点保留策略优化

### 当前问题分析

在 [analysis_orchestrator.py:1588-1624](codeinsight-backend/codeinsight/tasks/analysis_orchestrator.py:1588-1624) 中，增量 AI Agent 模式的知识点保留逻辑存在以下问题：

| 问题 | 当前行为 | 影响 |
|------|----------|------|
| 保留策略过于粗糙 | 按 file_path 匹配保留/删除知识点 | 知识点可能关联多个文件，单文件变更导致整条知识点被删除 |
| 无增量知识合并 | 保留的知识点直接使用上一版本，不重新生成拓展内容 | 可能导致 expansion 与新代码上下文不一致 |
| 无版本一致性检查 | 保留的知识点没有标记"未重新分析" | 前端无法区分"全新分析"和"保留"的知识点 |

### 优化方案

#### 方案 A：智能保留策略

1. **多维度匹配保留**
   ```python
   # 不仅匹配 file_path，还匹配 description 中的关键词
   # 如果知识点描述中引用了变更文件，则删除；否则保留
   affected_paths = {c.path for c in incremental_diff.changed_files}
   
   for kp in existing_kps:
       kp_file_paths = {s.get("file_path") for s in kp.code_snippets or []}
       kp_description_words = set(kp.description.lower().split())
       
       # 如果知识点的所有代码片段都不在变更文件中
       # 且描述中不涉及变更文件的关键词，则保留
       if not kp_file_paths & affected_paths:
           preserve_kp(kp)
   ```

2. **保留标记**
   ```python
   # 为保留的知识点添加标记
   kp_data["metadata"]["preserved"] = True
   kp_data["metadata"]["preserved_reason"] = "no_changes_in_related_files"
   ```

3. **增量知识合并**
   ```python
   # 对新分析的知识点，与保留的知识点进行合并去重
   # 相同 title 的知识点保留置信度高的
   merged_kps = merge_preserved_and_new(preserved_kps, new_kps)
   ```

#### 方案 B：选择性重新分析

1. 只对涉及变更文件的知识点重新运行 LLM 分析
2. 其他知识点直接保留（包括 expansion）
3. 在合并阶段进行去重和排序

### 代码修改点

```
codeinsight/tasks/analysis_orchestrator.py:
  - 修改 _incremental_ai_agent 逻辑（约 1588-1624 行）
  - 增加知识点保留的智能匹配策略
  - 增加 preserved 元数据标记
  - 增加增量知识合并逻辑
```

---

## 7. [新增] LLM 调用成本与速率控制

### 当前问题分析

在 [llm/cost.py](codeinsight-backend/codeinsight/llm/cost.py) 和 [llm/client.py:318-325](codeinsight-backend/codeinsight/llm/client.py:318-325) 中，已有成本追踪机制，但存在以下问题：

| 问题 | 影响 |
|------|------|
| 无预算上限控制 | 单次分析可能消耗大量 API 费用 |
| 无成本预警机制 | 无法在费用过高时提前终止 |
| ExpansionNode 并发无限制 | MAX_CONCURRENCY=5，每个知识点 1 次调用，100 个知识点 = 100 次并发调用 |
| 无缓存机制 | 相同代码库重复分析会重复计费 |

### 优化方案

#### 方案 A：预算控制

```python
class CostBudget:
    """LLM 调用预算控制器"""
    
    def __init__(self, max_budget_usd: float = 10.0):
        self._max_budget = max_budget_usd
        self._spent = 0.0
    
    def check(self, estimated_cost: float) -> bool:
        """检查是否超出预算"""
        if self._spent + estimated_cost > self._max_budget:
            logger.warning("LLM 预算即将耗尽: spent=%.2f, estimated=%.2f, max=%.2f",
                          self._spent, estimated_cost, self._max_budget)
            return False
        return True
    
    def record(self, cost: float):
        self._spent += cost
```

#### 方案 B：结果缓存

```python
# 基于代码指纹的缓存
def _compute_code_fingerprint(snippets: list[dict]) -> str:
    """计算代码上下文的哈希指纹"""
    combined = "".join(s.get("code", "") for s in snippets)
    return hashlib.sha256(combined.encode()).hexdigest()

# 在 LLMClient 中检查缓存
async def chat_with_cache(self, messages: list[dict], cache_ttl: int = 86400):
    fingerprint = _compute_code_fingerprint(extract_snippets(messages))
    cached = await redis.get(f"llm_cache:{fingerprint}")
    if cached:
        return json.loads(cached)
    result = await self.chat(messages)
    await redis.setex(f"llm_cache:{fingerprint}", cache_ttl, json.dumps(result))
    return result
```

#### 方案 C：Expansion 维度合并（已部分实现）

当前 [node.py:678-766](codeinsight-backend/codeinsight/agents/node.py:678-766) 已经将 5 个拓展维度合并为 1 次 LLM 调用，这是一个很好的优化。但可以进一步：
- 对低置信度知识点跳过拓展生成
- 对相似知识点的拓展内容进行批量处理

### 代码修改点

```
codeinsight/llm/client.py:
  - 增加 CostBudget 类
  - 增加 chat_with_cache() 方法
  - 在 chat() 中集成预算检查

codeinsight/agents/node.py:
  - ExpansionNode: 增加低置信度过滤（confidence < 0.7 跳过拓展）
  - 增加批量拓展处理
```

---

## 8. [新增] Prompt 模板质量提升

### 当前问题分析

现有 prompt 模板（[prompts/*.md](codeinsight-backend/codeinsight/prompts/)）存在以下共性问题：

| 问题 | 影响 |
|------|------|
| 缺少 Few-shot 示例 | 每个 prompt 只有 1-2 个示例，不足以覆盖边界情况 |
| 输出格式约束不够严格 | LLM 偶尔返回非 JSON 格式，需要 fallback 解析 |
| 缺少"负向约束" | 没有明确告诉 AI 什么**不应该**输出 |
| 没有针对代码语言的差异化 | Python/TypeScript/Go 代码的结构差异未考虑 |
| base.md 约束力不足 | 子 prompt 继承 base.md，但子 prompt 可能覆盖关键约束 |

### 优化方案

#### 方案 A：增强 Few-shot 示例

每个 prompt 模板应包含 3-5 个不同复杂度的示例：
1. 简单场景（标准模式识别）
2. 中等场景（多个模式共存）
3. 困难场景（边界情况、易混淆模式）
4. 负例（看起来像但实际不是的场景）

#### 方案 B：增加负向约束

在 base.md 中增加明确的排除规则：
```markdown
## 负向约束（必须遵守）

- 不要将普通的 if-else 识别为 Strategy 模式
- 不要将简单的 getter/setter 识别为 Builder 模式
- 不要将临时变量识别为 Singleton
- 不要在没有代码证据的情况下推断架构决策
- 置信度低于 0.7 的知识点不要输出
```

#### 方案 C：代码语言差异化

根据 `state.get("language_distribution", {})` 动态调整 prompt：
```python
if "python" in language_dist:
    prompt += "\n注意：这是 Python 代码，请识别 Python 特有的模式（如装饰器、context manager）"
if "typescript" in language_dist:
    prompt += "\n注意：这是 TypeScript 代码，请识别类型系统中的模式（如泛型、interface 实现）"
```

### 代码修改点

```
codeinsight/prompts/base.md:
  - 增加负向约束章节
  - 增加更多 Few-shot 示例
  
codeinsight/prompts/design_pattern.md:
  - 增加 3-5 个 Few-shot 示例（含负例）
  
codeinsight/prompts/architecture.md:
  - 增加 Few-shot 示例
  
codeinsight/agents/node.py:
  - _build_messages(): 根据 language_distribution 动态注入语言提示
```

---

## 9. [新增] 前端 SSE 进度展示优化

### 当前问题分析

SSE 功能已实现（[use-sse.ts](codeinsight-frontend/src/hooks/use-sse.ts)），但存在以下问题：

| 问题 | 影响 |
|------|------|
| 创建仓库后未自动连接 SSE | [repositories.ts:22-27](codeinsight-frontend/src/api/repositories.ts:22-27) 的 `createRepository` 不返回 task_id |
| 无进度展示 UI | 用户创建仓库后跳转到仓库列表，看不到分析进度 |
| 无错误提示 | SSE 连接失败时只有控制台 error，用户无感知 |
| 无断线重连 | 网络波动导致 SSE 断开后不会自动重连 |

### 优化方案

#### 方案 A：创建仓库后自动连接 SSE

```typescript
// RepoForm.tsx
const handleCreate = async (data: RepositoryCreate) => {
  const response = await createRepository(data);
  const taskId = response.headers?.get('x-task-id');
  if (taskId && data.auto_analyze) {
    navigate(`/repositories/${response.id}/analysis?taskId=${taskId}`);
  } else {
    navigate('/repositories');
  }
};
```

#### 方案 B：进度展示组件

```tsx
// AnalysisProgress.tsx
export function AnalysisProgress({ taskId }: { taskId: string }) {
  const { data, error, isComplete } = useSSE(taskId);
  
  if (isComplete) return <SuccessBanner knowledgePoints={data?.progress.knowledgePointsFound} />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <ConnectingSpinner />;
  
  return (
    <ProgressBar 
      percent={data.progress.percent}
      step={data.progress.currentStep}
      knowledgePoints={data.progress.knowledgePointsFound}
    />
  );
}
```

#### 方案 C：断线重连

在 `useSSE` hook 中增加重连逻辑：
```typescript
// 连接断开后自动重连（最多 3 次）
const [reconnectAttempts, setReconnectAttempts] = useState(0);

if (error && reconnectAttempts < 3) {
  setTimeout(() => {
    setReconnectAttempts(a => a + 1);
    connect(); // 重新连接
  }, 3000);
}
```

### 代码修改点

```
codeinsight-frontend/src/api/repositories.ts:
  - createRepository 返回类型增加 task_id
  
codeinsight-frontend/src/components/AnalysisProgress.tsx:
  - 新建进度展示组件
  
codeinsight-frontend/src/components/RepoForm.tsx:
  - 创建仓库后获取 task_id 并导航到进度页面
  
codeinsight-frontend/src/hooks/use-sse.ts:
  - 增加断线重连逻辑
```

---

## 10. 总体实施建议

### 优先级排序（更新版）

| 优先级 | 任务 | 工作量 | 效果 | 状态 |
|--------|------|--------|------|------|
| **P0** | 修改 eager 模式默认值 + 前端 SSE 集成 | 1 天 | 用户体验大幅提升 | 后端已实现，前端未集成 |
| **P1** | 上下文增强（问题 1 方案 A） | 2 天 | 分析质量显著提升 | 未实施 |
| **P1** | 新增开发模板分类 TT（问题 4） | 3 天 | 覆盖更多知识点 | 未实施 |
| **P1** | 新增技术栈分类 TK（问题 5） | 3 天 | 自动化技术文档 | 未实施 |
| **P2** | Prompt 模板质量提升（问题 8） | 2 天 | 减少 LLM 幻觉 | 未实施 |
| **P2** | 增量分析知识点保留优化（问题 6） | 3 天 | 增量分析准确率提升 | 未实施 |
| **P2** | 任务分片 + 断点续传（问题 2 方案 C） | 5 天 | 支持超大代码库 | 未实施 |
| **P2** | LLM 成本预算控制（问题 7） | 2 天 | 防止费用超支 | 未实施 |
| **P3** | 多轮提取（问题 1 方案 B） | 5 天 | 分析深度显著提升 | 未实施 |
| **P3** | 自适应上下文窗口（问题 2 方案 B） | 5 天 | 智能处理超大上下文 | 未实施 |

### 实施阶段

**第一阶段（立即，P0）**：
1. 修改 `create_repository` 始终返回 task_id
2. 前端集成 SSE 监听（使用已有的 `useSSE` hook）
3. 添加进度展示 UI

**第二阶段（短期，P1-P2）**：
1. 提高 `MAX_CODE_SNIPPETS` 和 `MAX_CODE_CHARS_PER_SNIPPET`
2. 提高 `max_tokens`
3. 增强 prompt 模板（Few-shot + 负向约束）
4. 添加开发模板分类 TT
5. 添加技术栈分类 TK
6. 优化增量分析知识点保留策略
7. 增加 LLM 成本预算控制

**第三阶段（中期，P2-P3）**：
1. 实现任务分片逻辑
2. 实现多轮提取策略
3. 实现自适应上下文窗口
4. 实现代码缓存机制

### 风险评估（更新版）

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|----------|------|
| LLM API 成本增加 | 预算超支 | 限制 max_tokens，增加预算控制（问题 7） | 已有追踪，无上限 |
| 分析时间增加 | 用户体验下降 | 异步任务 + SSE 进度通知 | 后端已实现 |
| 代码复杂度增加 | 维护困难 | 模块化设计，清晰接口 | 现有代码已较模块化 |
| 模型幻觉 | 错误分析 | 增加置信度阈值，负向约束（问题 8） | 仅有基础约束 |
| SSE 连接不稳定 | 进度展示中断 | 断线重连（问题 9 方案 C） | 未实现 |
| 增量分析保留错误 | 知识点丢失或重复 | 多维度匹配 + 保留标记（问题 6） | 仅 file_path 匹配 |

---

## 附录：当前系统架构概览

```
用户创建仓库（勾选自动分析）
    ↓
POST /api/v1/repositories
    ↓
create_repository() [repositories.py:39-83]
    ↓
┌─ 创建仓库记录 ──────────────────────────┐
│  dao.create(db, request)                │
│  await db.commit()                      │
└─────────────────────────────────────────┘
    ↓
_trigger_analysis(repo_id, repo) [analysis.py:198-377]
    ↓
┌─ 双模式执行 ─────────────────────────────┐
│  if celery_task_always_eager (默认 True): │
│    同步执行 AnalysisOrchestrator._run_async()│
│    超时保护: 600s                         │
│    返回 AnalysisTask (含 task_id)         │
│  else:                                    │
│    提交 Celery 任务 run_analysis.delay()  │
│    返回 AnalysisTask (PENDING 状态)       │
└─────────────────────────────────────────┘
    ↓
前端收到响应
    ↓
┌─ 当前前端行为 ───────────────────────────┐
│  直接跳转到 /repositories                 │
│  ❌ 未连接 SSE 监听进度                   │
│  ❌ 用户看不到分析进度                    │
└─────────────────────────────────────────┘
    ↓
┌─ SSE 端点（已实现但未使用）──────────────┐
│  GET /api/v1/tasks/{task_id}/stream     │
│  → SSE 推送 progress/complete/error 事件 │
│  前端 useSSE() hook（已实现）            │
└─────────────────────────────────────────┘
    ↓
┌─ 分析流程（LangGraph）─────────────────┐
│  start → [5 agents parallel]           │
│  │     design_pattern                  │
│  │     architecture                    │
│  │     algorithm                       │
│  │     engineering                     │
│  │     domain_knowledge                │
│  └→ merge → expansion → END            │
│                                         │
│  ANALYSIS_NODES: 5 个（无 TT/TK）       │
│  超时保护: 600s [graph.py:95]          │
└─────────────────────────────────────────┘
    ↓
每个 Agent 执行：
    ↓
┌─ 构建代码上下文 ───────────────────────┐
│  加载: 全部文件, 每文件最多 5000 字符   │  ← O-B11 已改进
│  送入 LLM: MAX_CODE_SNIPPETS=20        │  ← 瓶颈!
│           MAX_CODE_CHARS_PER_SNIPPET=1000│ ← 瓶颈!
│  AST fallback: 取前 500 节点           │  ← 瓶颈!
│  Token 估算: 超过 80% 时警告           │  ← 已有保护
└─────────────────────────────────────────┘
    ↓
┌─ 调用 LLM ─────────────────────────────┐
│  max_tokens = 4096 (硬编码)            │  ← 瓶颈!
│  temperature = 0.3 (配置)              │
│  单次调用，无分块                       │
│  Provider 降级: chat_with_fallback()   │
│  任务路由: chat_for_task() (可选)      │
└─────────────────────────────────────────┘
    ↓
┌─ 解析响应 ─────────────────────────────┐
│  Pydantic TypeAdapter 校验             │
│  Markdown 代码块清理                    │
│  包装对象提取 (knowledge_points/items)  │
│  Fallback: 原始内容作为单条知识点       │
└─────────────────────────────────────────┘
    ↓
┌─ 合并结果 ─────────────────────────────┐
│  按 title 去重（保留高置信度）          │
│  按 confidence 降序排列                │
└─────────────────────────────────────────┘
    ↓
┌─ 生成拓展内容 ─────────────────────────┐
│  每个知识点 1 次 LLM 调用（5 维度合并） │  ← 已优化
│  并发控制: Semaphore(5)                │
│  限流: rate_limit_hits 退避            │
│  重试: MAX_RETRIES=2                   │
└─────────────────────────────────────────┘
    ↓
保存到数据库（共享 session）
    ↓
┌─ 增量分析分支 ─────────────────────────┐
│  计算变更文件 diff                      │
│  保留未涉及变更的知识点                 │
│  仅对变更文件重新运行 AI Agent          │
│  ⚠️ 保留策略仅基于 file_path 匹配      │
└─────────────────────────────────────────┘
    ↓
同步到 Meilisearch 索引
```

### 关键文件索引

| 文件 | 职责 | 关键行号 |
|------|------|----------|
| [analysis_orchestrator.py](codeinsight-backend/codeinsight/tasks/analysis_orchestrator.py) | 分析流程编排 | 全文件 |
| [agents/node.py](codeinsight-backend/codeinsight/agents/node.py) | 分析节点定义 | 33-34 (瓶颈), 158-202 (messages), 204-258 (context) |
| [agents/graph.py](codeinsight-backend/codeinsight/agents/graph.py) | LangGraph 图定义 | 32-38 (节点列表), 95 (超时) |
| [agents/state.py](codeinsight-backend/codeinsight/agents/state.py) | 状态定义 + Reducer | 全文件 |
| [llm/client.py](codeinsight-backend/codeinsight/llm/client.py) | LLM 客户端 | 54 (max_tokens), 233-338 (chat) |
| [config.py](codeinsight-backend/codeinsight/config.py) | 配置管理 | 109 (eager 默认) |
| [api/repositories.py](codeinsight-backend/codeinsight/api/repositories.py) | 仓库 API | 68-82 (自动分析触发) |
| [api/analysis.py](codeinsight-backend/codeinsight/api/analysis.py) | 分析任务 API | 198-377 (_trigger_analysis), 517-588 (SSE) |
| [schemas/knowledge.py](codeinsight-backend/codeinsight/schemas/knowledge.py) | 知识点 Schema | 21-36 (枚举), 263-306 (Extraction) |
| [schemas/constants.py](codeinsight-backend/codeinsight/schemas/constants.py) | 分类常量 | 7-15 |
| [prompts/base.md](codeinsight-backend/codeinsight/prompts/base.md) | 通用 Prompt 模板 | 全文件 |
| [hooks/use-sse.ts](codeinsight-frontend/src/hooks/use-sse.ts) | 前端 SSE Hook | 全文件 |
| [api/repositories.ts](codeinsight-frontend/src/api/repositories.ts) | 前端 API | 22-27 (createRepository) |
