# 代码分析功能深度审查与增强报告

## 版本信息

- **文件：** `doc/dev-analysis/comprehensive-functionality-analysis.md`
- **最后更新：** 2026-07-27
- **涉及模块：** `analysis_orchestrator.py`, `incremental_analyzer.py`, `snapshot_manager.py`, `agents/graph.py`, `agents/node.py`

---

## 一、断点续跑功能（Resume Functionality）

### 1.1 当前实现机制

#### 1.1.1 版本状态追踪

分析任务的生命周期通过 `AnalysisVersion` 模型管理，包含以下状态流转：

```
PENDING → SCANNING → PARSING → ANALYZING_STRUCTURES → ANALYZING_MODULES → STORING → COMPLETED
                                                                 ↓
                                                               FAILED / CANCELLED
```

关键实现：
- `AnalysisVersionDAO.get_latest_in_progress()`：查找未终态的最新版本用于恢复
- `AnalysisOrchestrator.get_in_progress_version()`：将状态映射为 `skip_to_step` 标志

| TaskStatus | skip_to_step | 恢复位置 |
|------------|-------------|----------|
| PENDING | None | 从头开始 (step 1) |
| SCANNING | "scan" | 跳过扫描，从 AST 解析开始 (step 3) |
| PARSING | "ast" | 跳过 AST 解析，从结构分析开始 (step 4) |
| ANALYZING_STRUCTURES | "frameworks" | 跳过结构分析，只执行框架检测 (step 4.5) |
| ANALYZING_MODULES | "ai" | 跳过前面所有，直接从 AI 分析开始 (step 5) |
| STORING | "store" | 直接进入存储完成阶段 (step 6) |

#### 1.1.2 数据重建逻辑 (`_reconstruct_scan_result`)

当 `skip_to_step == "scan"` 时，从 `FileModel` 表重建扫描结果：

```python
async def _reconstruct_scan_result(self, db: AsyncSession | None = None) -> bool:
    files = await self.file_dao.get_by_repository(db, self.repo_uuid)  # 从 DB 读取所有文件
    if not files: return False
    
    self.total_files = len(files)
    
    class _DbScanResult:
        def __init__(self, files_list):
            self.files = [_DbScanFile(f) for f in files_list]
            self.total_count = len(files_list)
            self.total_lines = sum(f.line_count or 0 for f in files_list)
            self.language_distribution = {f.language: language_dist.get(f.language, 0) + 1 for f in files_list}
            self.skipped_count = 0  # ⚠️ 原始扫描中的 skipped_count 被重置为 0
            self.errors: list[str] = []  # ⚠️ 原始扫描错误丢失
```

#### 1.1.3 失败清理逻辑 (`cleanup_failed_step_data`)

不同失败阶段清理对应的数据库表：

```python
async def _cleanup_failed_step_data_inner(self, db, failed_status):
    if failed_status == TaskStatus.PARSING.value:
        await ast_dao.delete_by_repository(db, self.repo_uuid)  # 仅删除 AST
    elif failed_status == TaskStatus.ANALYZING_STRUCTURES.value:
        await call_edge_dao.delete_by_repository(...)  # 删除调用边、模块依赖、路由、框架模式
    elif failed_status == TaskStatus.PENDING.value:
        await file_dao.delete_by_repository(...)  # 删除文件
    elif failed_status == TaskStatus.FAILED.value:
        # ⚠️ 过于激进：删除所有表的数据
        await ast_dao.delete_by_repository(...)
        await call_edge_dao.delete_by_repository(...)
        await module_dep_dao.delete_by_repository(...)
        await api_route_dao.delete_by_repository(...)
        await framework_pattern_dao.delete_by_repository(...)
        await file_dao.delete_by_repository(...)
```

#### 1.1.4 快照持久化

- `SnapshotManager.save_snapshot()` 在 `complete()` 前保存所有文件的 `content_hash`
- 使用单一 shared DB session 贯穿整个分析流程（P2-FixP7），减少连接池压力

### 1.2 存在的问题

| 问题编号 | 描述 | 严重程度 | 影响范围 |
|----------|------|---------|---------|
| R-1 | **失败清理无并发隔离** - `cleanup_failed_step_data()` 按 repository ID 整表删除，多个并发分析任务会相互干扰 | 🔴 高 | 多用户/多任务环境 |
| R-2 | **重建数据信息不完整** - `_reconstruct_scan_result()` 丢失 `commit_hash`、`errors`、`skipped_count` 等原始扫描元数据 | 🟡 中 | 断点续跑后的统计准确性 |
| R-3 | **降级分支快照处理复杂** - `_fell_back_to_full` 标记需要特殊处理，增加代码耦合度 | 🟢 低 | 增量分析降级场景 |
| R-4 | **快照粒度粗** - 仅在最终存储步骤保存一次，中间失败无法从更早的节点恢复 | 🟡 中 | 长时间分析任务的容错 |
| R-5 | **缺少步骤级进度追踪** - 不知道具体哪个文件已经成功解析，重复解析已知成功的文件 | 🟢 低 | 效率问题 |

### 1.3 增强方案建议

#### R-R1: 引入按 version_id 隔离的失败清理

修改清理逻辑，将操作限制在当前版本相关的记录上，而非整个 repository：

```python
async def _cleanup_failed_step_data_inner(self, db, failed_status, version_id=None):
    if version_id:
        # 通过 version_id 过滤，只清理该版本相关的数据
        # 而不是按 repository_id 全量删除
        pass
```

#### R-R2: 完善扫描结果重建

增加 `commit_hash` 和错误信息的记录与恢复：

```python
class _DbScanResult:
    def __init__(self, files, commit_hash=None, errors=None):
        self.commit_hash = commit_hash  # 新增
        self.errors = errors or []      # 保留原始错误
```

需要在 `AnalysisVersion` 表中额外存储扫描阶段的元数据（commit_hash, scan_error_count）。

#### R-R3: 阶段性快照保存策略

在关键里程碑后保存临时快照：
- AST 解析完成后：保存当前已解析文件的快照
- 结构分析完成后：保存调用图和模块依赖快照
- AI 分析完成后：保存知识点结果快照

#### R-R4: 文件级进度跟踪

引入 `FileAnalysisProgress` 表记录每个文件在各分析阶段的状态（pending/analyzed/error），支持精确的断点续点。

---

## 二、AI 分析阶段 7 个方面及单独重试功能

### 2.1 七个分析节点定义

基于 `agents/graph.py` 的 `ANALYSIS_NODES`：

| # | 节点类 | 类别代码 | 中文名称 | 提示词源文件 |
|---|--------|---------|---------|-------------|
| 1 | DesignPatternNode | DP | 设计模式分析 | `load_design_pattern_prompt()` |
| 2 | ArchitectureNode | AD | 架构设计分析 | `load_architecture_prompt()` |
| 3 | AlgorithmNode | AL | 算法实现分析 | `load_algorithm_prompt()` |
| 4 | EngineeringNode | ET | 工程技术分析 | `load_engineering_prompt()` |
| 5 | DomainKnowledgeNode | DK | 领域知识分析 | `load_domain_knowledge_prompt()` |
| 6 | TemplateTechniqueNode | TT | 开发模板分析 | `load_template_technique_prompt()` |
| 7 | TechnologyStackNode | TK | 技术栈分析 | `load_technology_stack_prompt()` |

### 2.2 当前执行流程

```
┌─────────────────────────────────────────────────────────┐
│ AnalysisOrchestrator._run_async()                       │
│                                                         │
│ Step 5: AI 分析                                        │
│   └── 构建 initial_state (AST + code snippets)          │
│   └── agent_graph = AgentAnalysisGraph(llm_client)      │
│   └── final_state = await agent_graph.run(initial_state)│
│       ├── __start__ → fan-out 到 7 个并行节点           │
│       ├── 各节点 execute(): LLM 调用 → parse_response  │
│       ├── 全部汇聚到 MergeNode (去重+排序)             │
│       └── ExpansionNode (拓展内容生成) → END           │
│                                                         │
│  agent_results = final_state.get("agent_results")       │
│  → 保存到 AnalysisVersion.agent_status                 │
└─────────────────────────────────────────────────────────┘
```

### 2.3 单个节点的 execute 实现模式

以 `DesignPatternNode` 为例（其他 6 个节点结构完全相同）：

```python
class DesignPatternNode(AnalysisNode):
    async def execute(self, state: AnalysisState) -> AnalysisState:
        category = "DP"
        try:
            prompt = load_design_pattern_prompt()
            messages = await self._build_messages(state, prompt)
            response = await self._llm_client.chat(messages)  # LLM 调用
            knowledge_points = self._parse_response(response, category)  # 解析
            
            logger.info("设计模式分析完成: repo_id=%s, extracted=%d", ...)
            
            result = {
                "knowledge_points": knowledge_points,
                "current_category": category,
                "progress": 0.2,
                "agent_results": {category: {"status": "success", "count": len(knowledge_points)}},
            }
            return result

        except LLMError as exc:
            logger.error("设计模式分析失败: %s", exc)
            # ❌ 关键问题：捕获后立即返回失败结果，无任何重试机制
            return {
                "error": str(exc),
                "agent_results": {category: {"status": "failed", "error": str(exc)}},
            }
```

### 2.4 现有错误处理的局限性

| 方面 | 当前行为 | 期望的"单独重试"能力 |
|------|---------|---------------------|
| **自动重试** | 无。LLMError 捕获后直接返回失败状态 | 应支持可配置的重试次数（指数退避） |
| **结果持久化** | agent_results 只在最终写入 DB；中间节点失败没有持久化记录 | 每个节点执行后应即时持久化到 DB，便于后续查询和重入 |
| **局部重入** | 不支持。一个节点失败导致整个分析"部分完成"，无法仅对该节点重新调用 | 提供 API 指定 category 重新执行该节点，保留其他已成功的结果 |
| **智能保留** | 无。失败后整个分析结果被视为不完整 | 结合增量分析的思路，仅重新提取失败的类别，保留已有的知识点 |
| **成本意识** | 无感知。失败后用户需重启整个分析（最多 7 次 LLM 调用） | 只需对失败的 1~N 个节点调用，显著降低成本 |

### 2.5 特别关注：ExpansionNode 的重试

需要注意的是，`ExpansionNode`（第 8 步，非 7 个主分析节点之一）实现了自己的重试机制：

```python
class ExpansionNode:
    MAX_RETRIES = 2  # 针对单个知识点的拓展维度生成重试
    
    async def _generate_expansion(self, kp: dict) -> dict | None:
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await self._llm_client.chat(..., num_retries=0)
                # 解析...
                return result
            except (LLMError, Exception) as exc:
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(1)  # 简单等待，非指数退避
                    continue
                return None
```

这是 Node 级别的重试，但仅针对 **Expansion** 阶段（对每个知识点生成 5 个维度的拓展内容），不属于 7 个主分析节点的范围。

### 2.6 基于用户建议的单独重试设计方案

> **用户观点："要尽量减少对模型的调用以节约成本，所以应该是在某个ai分析结果失败后，记录失败的是什么分析，在完成所有任务后，前端给用户一个单独重试该步骤的入口，重新尝试该分析"**

这个设计思路非常合理——**事后按需重试**优于事前自动重试，既保证了成本可控，又提供了灵活性。

#### 2.6.1 数据模型增强

在 `AnalysisVersionModel` 中扩展 `agent_status` 字段的结构，使其支持更丰富的元数据：

```python
# 当前 agent_status 是 JSON，存储 {"design_pattern": {"status": "failed", "error": "..."}}
# 增强后：
{
    "design_pattern": {
        "status": "failed",  # "success" | "failed" | "retrying" | "pending"
        "timestamp": ISO8601,     # 执行时间戳
        "attempts": 1,            # 调用次数
        "error": "LLM connection timeout...",  # 错误详情
        "knowledge_points": [],   # 即使失败也记录已提取的部分（如果有）
        "cost_estimate": 0.15     # 预估 token 成本
    },
    "architecture": {
        "status": "success",
        "timestamp": "...",
        "attempts": 1,
        "knowledge_points": [...],
        "cost_estimate": 0.20
    }
}
```

需要在 `_update_analysis_version()` 方法中支持传递完整的 `agent_status` 字典，而不仅仅是最终状态。

#### 2.6.2 API 接口设计

添加新的 REST API 端点：

```python
# endpoints: /api/retry/{repo_uuid}/{category}
@app.post("/api/retry/{repo_uuid:path}/{category:path}")
async def retry_analysis_category(
    repo_uuid: UUID,
    category: str,  # DP/AD/AL/ET/DK/TT/TK 中的一个
    current_user: User = Depends(get_current_user),
):
    """
    单独重试指定的 AI 分析类别。
    
    行为：
    1. 检查是否存在已完成的分析版本，获取已成功的其他节点结果作为上下文
    2. 创建新的分析子任务（或异步执行）
    3. 将新结果追加到原有知识点中
    4. 更新 version 的 agent_status
    """
    valid_categories = {"DP", "AD", "AL", "ET", "DK", "TT", "TK"}
    if category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of {valid_categories}")
    
    # 获取仓库最近的成功版本
    prev_version = await version_dao.get_latest_completed(repo_uuid)
    
    # 如果该 category 已成功过，直接返回已有结果（可选：强制覆盖）
    if prev_version and prev_version.agent_status:
        existing_status = prev_version.agent_status.get(category, {})
        if existing_status.get("status") == "success":
            # 可以选择返回已有结果，或询问用户是否强制重算
            return {
                "status": "exists",
                "message": f"{CATEGORY_NAMES[category]} analysis already completed.",
                "existing_kp_count": existing_status.get("knowledge_points_count", 0),
            }
    
    # 启动重试任务
    task = retry_category_task.delay(str(repo_uuid), category)
    return {"task_id": task.id}
```

Celery 任务示例 (`tasks/analysis_tasks.py` 新增)：

```python
@celery_app.task(name="tasks.retry_analysis_category", bind=True)
def retry_analysis_category(self, repo_uuid: str, category: str):
    """单独重试某个 AI 分析类别"""
    repo_uuid = UUID(repo_uuid)
    
    orchestrator = AnalysisOrchestrator(repo_uuid=repo_uuid, mode="full")
    
    # 加载历史成功的 agent_status 和知识点
    prev_version = await orchestrator.version_dao.get_latest_completed(None, repo_uuid)
    existing_kps = []
    if prev_version and prev_version.version:
        existing_kps = await kp_dao.list(None, repo_uuid, version=prev_version.version)
    
    # 只构建该 category 需要的状态（current_category 设定为该 category）
    from codeinsight.agents.graph import CATEGORY_TO_NODE, ANALYSIS_NODES
    category_name = CATEGORY_TO_NODE.get(category)
    if not category_name:
        raise ValueError(f"Unknown category: {category}")
    
    # 重新准备数据：使用已有的 ast_data 和 code_snippets
    ast_nodes = await orchestrator.ast_node_dao.get_by_repository(None, repo_uuid)
    ast_data = [...]  # 转换格式
    
    files = await orchestrator.file_dao.get_by_repository(None, repo_uuid)
    repo_path = await orchestrator._get_repo_path(None)
    code_snippets = [...]  # 读取文件内容
    
    # 创建初始状态，只针对该 category
    initial_state = AgentAnalysisGraph.create_initial_state(
        repo_id=str(repo_uuid),
        ast_data=ast_data,
        code_snippets=code_snippets,
        category=category,  # ✅ 关键：设置 current_category 使 router 只分发到对应节点
        enable_chunking=orchestrator.total_files > 2000,
    )
    
    # 载入已有的知识点（避免去重冲突）
    initial_state["knowledge_points"] = existing_kps
    
    llm_client = LLMClient()
    agent_graph = AgentAnalysisGraph(llm_client)
    
    # 执行（会运行 fan-out → 但该 category 只有 1 个节点实际工作）
    final_state = await agent_graph.run(initial_state)
    
    # 更新 agent_status：标记该 category 为成功，记录 attempts=1
    new_agent_status = {
        category: {
            "status": "success",
            "timestamp": datetime.now(UTC).isoformat(),
            "attempts": 1,
            "knowledge_points_count": len(final_state.get("knowledge_points", [])),
        }
    }
    
    # 将新知识点追加到数据库（而不是覆盖）
    new_kps = [kp for kp in final_state.get("knowledge_points", []) 
               if not any(kp["title"] == existing["title"] for existing in existing_kps)]
    if new_kps:
        await kp_dao.batch_create(None, new_kps)
    
    # 更新版本记录（可选：创建新版本，或更新当前版本）
    # ...
```

#### 2.6.3 前端界面设计

在分析结果页面，为每个分析类别显示状态图标和操作按钮：

```
┌──────────────────────────────────────────────────────────────┐
│ 代码分析报告 - 仓库: my-app-repo                            │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  📊 总体概览                                                 │
│  总文件数: 142  知识点总数: 87  完成时间: 2026-07-27         │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  AI 分析结果明细                                       │  │
│  ├────────────────────────────────────────────────────────┤  │
│  │  □ 设计模式分析 (DP)      ✗ Failed   [Retry]            │  │  ← 点击 Retry 触发上述 API
│  │  ✓ 架构设计分析 (AD)      ✓ Success   12 points         │
│  │  ✓ 算法实现分析 (AL)      ✓ Success   8 points          │
│  │  ✓ 工程技术分析 (ET)      ✓ Success   15 points         │
│  │  ✓ 领域知识分析 (DK)      ✓ Success   23 points         │
│  │  ✓ 开发模板分析 (TT)      ✓ Success   10 points         │
│  │  ✓ 技术栈分析 (TK)        ✓ Success   19 points         │
│  │                                                          │  │
│  │  (注: ✗ 表示该节点分析失败，可单独重试 ✓ 表示成功)     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  [查看完整报告]  [下载报告]                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**关键交互流程：**
1. 用户点击 "Retry" 按钮
2. 前端调用 `POST /api/retry/{repo_uuid}/DP`
3. 后端执行单独的 LLM 调用（仅设计模式分析节点）
4. 成功后更新 UI，状态由 "Failed" 变为 "Success"，并显示新提取的知识点数量

#### 2.6.4 成本估算对比

| 方案 | 7 个节点均失败时的额外开销 | 典型场景（1 个节点失败） |
|------|--------------------------|------------------------|
| 整体重新运行 | 7×LLM 调用 ≈ $0.70~$1.40 | 7×LLM 调用 ≈ $0.70~$1.40 |
| 单独重试（本方案） | 1×LLM 调用 ≈ $0.10~$0.20 | 1×LLM 调用 ≈ $0.10~$0.20 |
| **节省比例** | **≈ 85-90%** | **≈ 85-90%** |

### 2.7 实施路线图

| 优先级 | 任务 | 工作量 | 依赖 |
|--------|------|--------|------|
| P0 (阻塞) | 增强 `agent_status` 数据结构记录 `attempts` 和时间戳 | 低 | 无 |
| P0 (阻塞) | 每个节点执行后将 intermediate status 写入 version 表 | 中 | P0 |
| P1 (高) | 新增 `/retry/{repo_uuid}/{category}` API 端点 | 中 | P0, P1 |
| P1 (高) | 创建 Celery worker 任务执行单节点重试 | 中 | P1 |
| P2 (中) | 前端 UI 显示各节点状态 + Retry 按钮 | 中 | P1 |
| P2 (中) | 失败节点自动记录到 Redis，供前端轮询获取 | 低 | P0 |
| P3 (优化) | 支持批量 retry（多个 category 同时重试） | 低 | P1 |
| P3 (优化) | 增加 retry 次数上限，防止无限重试循环 | 低 | P0 |

---

## 三、增量分析功能（Incremental Analysis）

### 3.1 整体架构

增量分析由三个核心组件协同工作：

```
┌─────────────────┐       ┌──────────────────┐       ┌────────────────────┐
│ Incremental     │──────▶│ SnapshotManager  │──────▶│ AnalysisOrchestrator│
│ Analyzer        │ (diff)│ (content_hash    │ (version tag)│ (do_full_analysis│
│                 │       │  persistence)    │       │ + apply diff)    │
└─────────────────┘       └──────────────────┘       └────────────────────┘
                                ▲                                     │
                                │                                     ▼
                          FileAnalysisSnapshot                  IncrementalDiff
                          (DB table)                          (changed_files,
                                                                   propagated_files,
                                                                   needs_full_analysis)
```

### 3.2 增量差异计算 (`compute_diff`)

#### 3.2.1 变更检测算法

三向比较流程：

```python
def _compute_changes(self, current_files, previous_snapshot) -> list[FileChange]:
    current_by_path = {f.path: f for f in current_files}      # O(N)
    previous_by_path = previous_snapshot                     # {path: hash} (O(1) lookup)
    
    changes = []
    
    # 1. 遍历当前文件：判断 added/modified
    for file_obj in current_files:
        path = file_obj.path
        new_hash = file_obj.content_hash
        
        if path not in previous_by_path:
            # ADDED: 新增文件
            changes.append(FileChange(file_id=file_obj.id, path=path,
                                      change_type=ADDED, old_hash=None,
                                      new_hash=new_hash))
        elif previous_by_path[path] != new_hash:
            # MODIFIED: hash 变化
            changes.append(FileChange(file_id=file_obj.id, path=path,
                                      change_type=MODIFIED, old_hash=previous_by_path[path],
                                      new_hash=new_hash))
        # else: no change → skip
    
    # 2. 遍历上一版本：判断 deleted
    for path in previous_by_path:
        if path not in current_by_path:
            # DELETED: 删除的文件（file_id 为 None）
            changes.append(FileChange(file_id=None, path=path,
                                      change_type=DELETED, old_hash=previous_by_path[path],
                                      new_hash=""))
    
    return changes
```

时间复杂度：O(N)，其中 N 为文件总数。空间复杂度：O(N)。

#### 3.2.2 BFS 依赖传播 (`_propagate_dependencies`)

**传播规则：**
1. 变更文件被其他文件调用 → **调用方**需要重分析（caller propagates）
2. 变更文件调用了其他文件 → **被调用方**需要重分析（callee propagates）  
3. 变更文件被其他文件 import → **导入方**需要重分析（importer propagates）
4. 变更文件 import 了其他文件 → **被导入方**可能需要重分析（importee propagates）

**算法流程（带最大深度限制）：**

```python
async def _propagate_dependencies(self, repo_uuid, changes, max_depth=3):
    modified_changes = [c for c in changes if c.change_type != DELETED]
    if not modified_changes: return []
    
    visited = set({c.path for c in modified_changes})  # 起始加入变更文件
    propagated = set()
    queue = deque([(change.path, 0) for change in modified_changes])
    
    async with get_session(db) as session:
        # 一次性加载文件映射（小数据集）
        all_files = await file_dao.get_by_repository(session, repo_uuid)
        file_path_to_id = {f.path: f.id for f in all_files}
        file_id_to_path = {f.id: f.path for f in all_files}
        
        while queue:
            current_path, depth = queue.popleft()
            
            if depth >= max_depth: continue
            
            current_file_id = file_path_to_id.get(current_path)
            if current_file_id is None: continue
            
            # P-1 按需查询：不预加载所有 AST 节点
            node_ids = await self._get_node_ids_by_file(session, repo_uuid, current_file_id)
            
            # P-2 批量查询：2 次 JOIN 查询代替 N+1 问题
            caller_paths, callee_paths = await self._get_related_call_paths(session, repo_uuid, node_ids)
            importer_paths, importee_paths = await self._get_related_import_paths(session, repo_uuid, current_file_id, file_id_to_path)
            
            for path in caller_paths | callee_paths | importer_paths | importee_paths:
                if path not in visited:
                    visited.add(path)
                    propagated.add(path)
                    queue.append((path, depth + 1))
    
    return list(propagated)
```

**性能优化亮点：**
- **P-1 修复**：原代码一次性加载所有 AST 节点到内存 → 大仓库 OOM 风险；改为 BFS 每层按需查询
- **P-2 修复**：原代码对每个节点单独查询调用边 → N+1 查询问题；改为批量 JOIN 查询，仅 2 次 DB 请求

#### 3.2.3 降级判断 (`fallback_threshold`)

```python
total_current = len(current_files)
affected_count = len(changed_paths) | len(propagated)
needs_full_analysis = (affected_count / max(total_current, 1)) > self.fallback_threshold  # default 0.3
```

- 受影响比例 **严格大于** 阈值时触发降级（等于阈值不触发）
- 降级日志输出具体百分比，便于观察触发原因

### 3.3 增量解析与结构重建

#### AST 解析增量版本 (`parse_ast_incremental`)

```python
async def parse_ast_incremental(self, db, progress_callback):
    if not self.files_to_parse: return
    
    # 只删除变更文件的旧节点
    file_ids = [f.id for f in self.files_to_parse]
    deleted = await self.ast_node_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
    logger.info("增量 AST 解析: 删除旧节点 %d 条", deleted)
    
    pipeline = StructureDataPipeline(db=db, progress_callback=progress_callback)
    parsed_count = 0
    
    for file_obj in self.files_to_parse:  # 只遍历变更文件
        try:
            parser = ParserFactory.get_parser(file_obj.language)
            ast_nodes = parser.parse_file(file_obj.absolute_path)
            self.framework_tagger.tag_all(ast_nodes)  # 应用框架标签
            # 构建 nodes_data 并 ingest...
            result = await pipeline.ingest_ast_nodes(self.repo_uuid, nodes_data)
            parsed_count += result.inserted_count
        except Exception as exc:
            logger.warning("增量解析失败: file=%s, error=%s", file_obj.path, exc)
            continue  # 单个文件失败不影响其他文件
    
    logger.info("增量 AST 解析完成: %d 个节点", parsed_count)
```

关键点：单个文件失败只抛出 warning 并继续，不影响其他文件；与全量版的 savepoint 回滚策略形成对比。

#### 结构分析增量版本 (`build_structures_incremental`)

类似 AST 增量解析，只删除和重建指定文件的调用边和模块依赖：

```python
async def build_structures_incremental(self, db, progress_callback):
    if not self.files_to_parse: return
    
    file_ids = [f.id for f in self.files_to_parse]
    file_paths = [f.path for f in self.files_to_parse]
    
    deleted_edges = await self.call_edge_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
    deleted_deps = await self.module_dep_dao.delete_by_file_ids(db, self.repo_uuid, file_ids)
    
    call_edges = await self.call_graph_builder.build_data_for_files(self.repo_uuid, db=db, file_ids=file_ids)
    deps = await self.module_dep_builder.build_data_for_files(self.repo_uuid, file_paths=file_paths, db=db)
    
    # ingest ...
    await db.commit()  # 事务提交
```

### 3.4 增量 AI 分析——智能知识点保留

这是增量分析中最精妙的部分，位于 `_run_async()` 的 AI 分析阶段（1727-1802 行）：

#### 3.4.1 工作流程

```python
if not do_full_analysis and self.incremental_diff is not None:
    affected_paths: set[str] = {c.path for c in self.incremental_diff.changed_files}
    affected_paths.update(self.incremental_diff.propagated_files)  # 传播路径
    
    # 构建 file_id → path 映射
    file_path_to_id = {f.path: f.id for f in files}
    affected_file_ids = {file_path_to_id[p] for p in affected_paths if p in file_path_to_id}
    
    # 过滤 AST 数据和代码片段：只保留受影响文件的内容
    ast_data = [a for a in ast_data if a["file_id"] in affected_file_ids]
    code_snippets = [s for s in code_snippets if s["file_path"] in affected_paths]
    
    # 🔑 核心：保留历史知识点
    prev_version = await self.version_dao.get_latest_completed(shared_db, self.repo_uuid)
    if prev_version and prev_version.version != self.version_tag:
        existing_kps = await kp_dao.list(shared_db, self.repo_uuid, version=prev_version.version)
        
        for existing_kp in existing_kps:
            # 1. 检查代码片段是否直接关联变更文件
            kp_file_paths = {s.get("file_path") for s in (existing_kp.code_snippets or [])}
            directly_affected = bool(kp_file_paths & affected_paths)
            
            if directly_affected:
                # 直接相关 → 删除并重生成
                await kp_dao.delete(shared_db, existing_kp.id)
                continue
            
            # 2. 检查描述关键词是否匹配
            description_words = set((existing_kp.description or "").lower().split())
            affected_keywords = set()
            for p in affected_paths:
                parts = p.replace("/", "/").split("/")  # 兼容 Windows 路径分隔符
                affected_keywords.update(parts[-2:])  # 取最后两级目录/文件名
            
            # 过滤空字符串和常见后缀
            affected_keywords = {k for k in affected_keywords if k and "." not in k and len(k) > 2}
            
            description_affected = bool(description_words & affected_keywords)
            
            if description_affected and not directly_affected:
                logger.debug("知识点描述可能涉及变更文件，但代码片段不直接关联，保留: kp=%s", existing_kp.title)
            
            # 3. 未受影响 → 保留，加 preserved 标记
            kp_data = existing_kp.to_dict()
            kp_data["metadata"] = {
                "preserved": True,
                "preserved_reason": "no_changes_in_related_files",
                "preserved_from_version": prev_version.version,
            }
            await kp_dao.update(shared_db, existing_kp.id, {
                "version": self.version_tag,
                "metadata": kp_data.get("metadata", {}),
            })
            preserved_kps.append(kp_data)
            preserved_kp_count += 1
```

#### 3.4.2 保留判定逻辑总结

```
为上一个版本的每个知识点 K：
  如果 K.code_snippets 中有文件路径 ∈ affected_paths:
      → 直接删除，后续 AI 重新提取（需要 LLM 调用）
  否则 K.description 的单词集合 ∩ affected_keywords ≠ ∅:
      → 保留但记录警告（可能存在误判）
  否则:
      → 保留 unchanged，标记 metadata.preserved=True
```

**优点：** 避免了对完全无关的代码进行重复 LLM 调用，极大降低增量分析的成本。

**改进空间：** 基于字符串关键词的匹配较为粗糙，未来可考虑使用向量相似度（embedding）来判断相关性。

### 3.5 降级为全量分析的处理

当 `compute_incremental_diff()` 返回 `False`（异常或 needs_full_analysis=True）时：

```python
async def compute_incremental_diff(self, db) -> bool:
    if self.mode == AnalysisMode.FULL.value:
        return False
    
    try:
        analyzer = IncrementalAnalyzer()
        # ... 计算 incremental_diff
        if self.incremental_diff.needs_full_analysis:
            logger.info("增量分析触发降级... 切换为全量分析")
            self.incremental_diff = None  # 关键：置为 None，后续逻辑会走全量路径
            return False
        # ...
    except Exception as exc:
        logger.warning("增量分析失败，回退为全量分析: %s")
        self.incremental_diff = None
        return False

# 在 _run_async() 中:
do_full_analysis = self.mode == AnalysisMode.FULL.value
if not do_full_analysis:
    do_full_analysis = not await self.compute_incremental_diff(shared_db)  # 返回 False 则 do_full_analysis=True
```

**注意：** 降级后 `self.incremental_diff` 被设为 `None`，后续的 AI 分析阶段不会进入增量分支的逻辑（`if not do_full_analysis and self.incremental_diff is not None:`），因此会使用全量的 AST 数据和代码片段。

#### 3.6 降级分支的快照保存问题

`save_snapshot()` 方法中包含一个特殊标记 `_fell_back_to_full`，用于处理降级场景：

```python
async def save_snapshot(self, db: AsyncSession | None = None) -> None:
    # O-B3: 修复增量降级全量时快照丢失的问题
    if getattr(self, "_fell_back_to_full", False):
        self.incremental_diff = None  # 确保状态一致
    
    if not getattr(self, "scan_result", None):
        return
    
    try:
        if db is not None:
            files = await self.file_dao.get_by_repository(db, self.repo_uuid)
            snapshot_manager = SnapshotManager(db)
            count = await snapshot_manager.save_snapshot(self.repo_uuid, self.version_tag, files)
            return  # 直接返回，不使用 incremental_diff
        
        # ... 异步版本逻辑
    except Exception:
        logger.warning("快照保存失败", exc_info=True)
```

此处的设计意图是：即使降级为全量分析且 `incremental_diff` 为 `None`，只要 `scan_result` 存在，仍能保存完整快照，避免因增量计算失败而导致快照丢失。

### 3.7 增量分析测试覆盖情况

`test_incremental_analyzer.py` 提供了全面的单元测试：

**测试 `compute_diff`：**
- ✅ 无历史版本 → 全量
- ✅ 所有文件 hash 相同 → 空 diff
- ✅ 单个文件修改 → MODIFIED 变更
- ✅ 新增文件 → ADDED 变更
- ✅ 删除文件 → DELETED 变更
- ✅ 混合变更类型 → ADD/MOD/DEL 混合
- ✅ 无变更 → 空 diff
- ✅ 超过阈值 → needs_full_analysis=True
- ✅ 恰好阈值 → needs_full_analysis=False（边界条件验证）

**测试 `_propagate_dependencies`：**
- ✅ 无边 → 空传播
- ✅ 单级 caller 传播 → callee 变更时 caller 被纳入
- ✅ 单级 callee 传播 → caller 变更时 callee 被纳入
- ✅ BFS 深度限制 → 不超过 max_depth
- ✅ 访问控制 → 不重复加入已访问文件
- ✅ 仅 call_edges 传播验证
- ✅ 仅 module deps 传播验证
- ✅ 两者结合验证
- ✅ 循环依赖 → visited 避免死循环
- ✅ 缺失节点 → 优雅跳过
- ✅ DELETED 变更 → 不参与传播
- ✅ 空变更列表 → 空结果

✅ **整体测试覆盖率良好，覆盖了核心功能和边界情况。**

---

## 四、综合分析结论与建议

### 4.1 成熟度评级

| 功能 | 成熟度 | 评分 (1-5) | 备注 |
|------|--------|-----------|------|
| 断点续跑 | Basic | ⭐⭐☆ | 基本可用但有严重并发问题和数据完整性隐患 |
| AI 分析单独重试 | Not Implemented | ☆☆☆ | 完全缺失，需全新设计实现 |
| 增量分析 | Production-ready | ⭐⭐⭐⭐⭐ | 设计精巧，测试完备，性能优化到位 |

### 4.2 跨功能协同建议

1. **断点续跑 + 增量分析**：增量分析本身就需要历史快照，可与断点续跑共享快照服务。建议在恢复时优先考虑增量模式（如果当前模式配置为 incremental），利用已有的 diff 计算仅重新处理变更部分。

2. **AI 单独重试 + 断点续跑**：当某个 AI 节点失败后，用户可以通过"单独重试"功能恢复，而不必走完整的断点续跑流程。两者可以互补：断点续跑适用于步骤级失败（如解析崩溃），单独重试适用于节点级失败（如 LLM 网络超时）。

3. **AI 单独重试 + 增量分析**：对于增量分析中保留的知识点，如果某个特定分析类别需要重新运行，应同时考虑增量逻辑——即只对变更文件重新分析，而不是全量重新分析所有文件。这需要额外的协调逻辑。

### 4.3 优先级排序

1. **最高优先**：修复断点续跑的并发清理问题（R-1），避免生产环境任务互相干扰
2. **高优先**：实现 AI 分析单独重试功能（满足用户核心需求），提升用户体验并显著降低重试成本
3. **中优先**：完善断点续跑的数据重建完整性（R-2）
4. **低优先**：阶段性快照保存（R-3）和文件级进度跟踪（R-5）作为长期优化项

---

## 附录：关键代码引用位置

| 特性 | 文件 | 关键行号 |
|------|------|---------|
| IncrementalAnalyzer | `services/incremental_analyzer.py` | 全文档 |
| SnapshotManager | `services/snapshot_manager.py` | 全文档 |
| AnalysisOrchestrator | `tasks/analysis_orchestrator.py` | run() (1516), _run_async() (1540), get_in_progress_version() (1426), cleanup_failed_step_data() (1456) |
| AnalysisGraph | `agents/graph.py` | ANALYSIS_NODES (34), _route_to_agents (56), run() (177) |
| AnalysisNodes | `agents/node.py` | DesignPatternNode (716), ArchitectureNode (757), ..., ExpansionNode (1047) |
| AnalysisState | `agents/state.py` | TypedDict definition (115), reducer functions |
| AnalysisVersionDAO | `repositories/analysis_version.py` | get_latest_in_progress() (188), _IN_PROGRESS_STATUSES (179) |
| Incremental tests | `tests/test_incremental_analyzer.py` | 全文档 |
| Incremental integration tests | `tests/test_analysis_tasks_incremental.py` | 全文档 |
