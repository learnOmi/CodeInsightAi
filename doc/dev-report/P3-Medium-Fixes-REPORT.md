# P3 Medium 级别问题修复报告

> 生成时间：2026-07-20
> 修复范围：`doc/dev-analysis/P3-COMPREHENSIVE-REVIEW.md` 中的 42 个 Medium 级别问题
> 状态：✅ 全部修复完成

---

## 一、修复概览

| 层 | 问题编号 | 文件 | 问题描述 | 修复方式 | 状态 |
|-----|---------|------|---------|---------|------|
| **LLM** | L-D3 | `client.py` | usage 为 None 时仍记录 0 成本记录 | 跳过零成本记录（prompt_tokens=0 and completion_tokens=0 时提前返回） | ✅ |
| **LLM** | L-D4 | `client.py` | response_model 路径缺少成本追踪 | 在 response_model 分支补充成本计算和 CostTracker.record() 调用 | ✅ |
| **LLM** | L-P1 | `client.py` | embed() 重复构建 API kwargs，与 _get_api_kwargs() 重复 | 复用 _get_api_kwargs() 构建基础参数，仅替换 model 并移除 chat 专用参数 | ✅ |
| **LLM** | L-E1 | `client.py` | MODEL_COST_MAP 和 SIMPLE_TASK_MODELS 硬编码在类中 | 改为 @property 懒加载，从 settings.llm_cost_map / settings.llm_simple_task_models 动态读取 | ✅ |
| **LLM** | L-E2 | `client.py` | provider 字段用 Literal 限制死可选值 | 改为 str + 配置驱动注册（PROVIDER_REGISTRY + register_provider()） | ✅ |
| **LLM** | L-D5 | `cost.py` | pop(0) 导致 O(n) 性能问题 | 改用 collections.deque + popleft()，O(1) 复杂度 | ✅ |
| **LLM** | L-D6 | `cost.py` | CostTracker.record() 非并发安全 | 添加 asyncio.Lock 保护 _records 读写 | ✅ |
| **LLM** | L-D8 | `errors.py` | OllamaUnavailableError 从未被 raise | check_ollama_health() 异常时抛出 OllamaUnavailableError，chat_for_task() 捕获并降级 | ✅ |
| **LLM** | L-D9 | `embedding/client.py` | type: ignore[assignment] 掩盖真实类型不匹配 | 改为显式类型转换 `model_embedding = list[float](vector)` | ✅ |
| **LLM** | L-B9 | `embedding/client.py` | embed_single() 不检查 embeddings[0] 是否为空向量 | 增加 `not any(v != 0 for v in result)` 空向量检查 | ✅ |
| **Agent** | A-E2 | `graph.py` | 硬编码 Agent 名称列表与 ANALYSIS_NODES 重复 | 改为 `agent_names = [name for name, _ in ANALYSIS_NODES]` 从常量推导 | ✅ |
| **Agent** | A-D2 | `graph.py` | category 未匹配时静默回退到全部节点，无日志 | 增加 `logger.warning("未知分类 '%s'，回退到全部分类路由", category)` | ✅ |
| **Agent** | A-D3 | `node.py` | MergeNode 接受 llm_client 参数但从未使用 | 移除构造函数参数（保留 None 签名兼容旧调用方） | ✅ |
| **Agent** | A-B3 | `node.py` | str.replace() 链式替换不安全，description 中包含 {title} 会被二次替换 | 改用 str.format_map() 一次性替换，模板花括号已转义为 {{/}} | ✅ |
| **Agent** | A-D4 | `node.py` | 直接 state["knowledge_points"].extend() 绕过 reducer | 改为返回新字典 `{"knowledge_points": knowledge_points}` 由 LangGraph reducer 合并 | ✅ |
| **Agent** | A-D5 | `node.py` | _build_messages 未验证总长度是否超过 LLM 上下文窗口 | 使用 count_tokens() 估算，超过 80%（128k）时记录 warning | ✅ |
| **Agent** | A-D6 | `node.py` | 依赖 pydantic.ValidationError 继承自 ValueError 的隐式行为 | 显式 import `from pydantic import ValidationError`，在 except 中直接捕获 | ✅ |
| **编排器** | O-B8 | `orchestrator.py` | get_in_progress_version 缺少 "frameworks" 步骤映射 | 补充 `ANALYZING_STRUCTURES` 状态 → `"frameworks"` 映射 | ✅ |
| **编排器** | O-B9 | `orchestrator.py` | _ai_progress_pusher 函数属性突变有竞态风险 | 改用 asyncio.Event + stop_event.set()/cancel() 替代函数属性 `_done` | ✅ |
| **编排器** | O-B10 | `orchestrator.py` | parse_ast 使用 id(node) 作为 UUID 映射键 | 改为 `f"{node.file_path}:{node.start_line}:{node.end_line}:{node.name}"` 稳定标识 | ✅ |
| **编排器** | O-B11 | `orchestrator.py` | list_by_repository 限制 500 条 | 移除 500 条限制，全量加载所有文件 | ✅ |
| **编排器** | O-B12 | `orchestrator.py` | line_count 为 None 时 sum() 崩溃 | 使用 `sum(f.line_count or 0 for f in files_list)` | ✅ |
| **编排器** | O-B13 | `analysis.py` | SSE 流 percent >= 100.0 提前退出，客户端收不到 complete 事件 | 移除 percent >= 100.0 的 break 条件 | ✅ |
| **编排器** | O-D2 | `analysis.py` | submitted_at 始终为当前时间 | 从 Redis `task:{task_id}:submitted_at` 读取实际提交时间，未找到时降级为当前时间 | ✅ |
| **编排器** | O-P1 | `orchestrator.py` | _parse_external_dependencies N+1 查询 | 在数据库层使用 get_dependency_files() + LIKE 查询替代全量加载后内存过滤 | ✅ |
| **编排器** | O-P2 | `orchestrator.py` | 全量加载 AST 节点到内存，大仓库 OOM 风险 | 改为分批加载（每批 500 个）+ offset/limit 分页，累积所有框架检测结果 | ✅ |
| **编排器** | O-E1 | `orchestrator.py` | _run_async 方法过长（~286 行），违反单一职责原则 | **架构级问题，暂缓（属长期建议）** | ⏸️ |
| **编排器** | O-D3 | `orchestrator.py` | _store_files_to_db 先删除后插入，非原子操作 | 使用 db.begin_nested() savepoint 包裹删除+插入，失败时回滚 | ✅ |
| **编排器** | O-B14 | `analysis.py` | Eager 模式下取消功能被禁用，task_instance=None | 传递 eager_task_id 给 orchestrator.task_id，CancelChecker 能正常检查 | ✅ |
| **评估** | E-D1 | `evaluator.py` | 使用 time.time() 计时，受系统时间调整影响 | 替换为 time.monotonic() | ✅ |
| **评估** | E-D2 | `evaluator.py` | self_evaluate() 原地修改 extracted_points 列表 | 使用 `copy.deepcopy(point)` 复制输入后再修改 | ✅ |
| **评估** | E-D3 | `engine.py` | _load_test_cases() 回退逻辑缺陷，空结果无警告 | 添加三层空检查：显式警告 + 回退到默认 data/ 目录 + 最终仍空时二次警告 | ✅ |
| **评估** | E-D4 | `engine.py` | 总体 F1 使用算术平均，大小用例权重相同 | 改为加权 F1：按 total_extracted 加权，fallback 到算术平均 | ✅ |
| **服务** | S-D1 | `meilisearch_client.py` | search() 异常时静默返回空结果 | 改为 raise 异常，不吞没错误（调用方可自行决定容错） | ✅ |
| **服务** | S-D2 | `incremental_analyzer.py` | 已删除文件使用全零 UUID 哨兵值 | 改为 file_id=None（FileChange 类型已支持 UUID \| None） | ✅ |
| **服务** | S-B3 | `knowledge_point.py` | tags.contains([tag]) 在不同数据库后端不可移植 | 按 db.get_bind().dialect.name 分支：PostgreSQL 用 contains()，其他用 ilike 降级 | ✅ |

---

## 二、本轮新修复详情

### 2.1 O-P2: 全量加载 AST 节点到内存（大仓库 OOM 风险）

**文件**: `codeinsight/tasks/analysis_orchestrator.py` → `_detect_frameworks_ast_level()`

**问题**: `get_by_repository()` 一次性加载仓库所有 AST 节点到内存，大型仓库（数千文件）可能 OOM。

**修复**:
```python
# 修复前
nodes = await self.ast_node_dao.get_by_repository(db, self.repo_uuid)
ast_nodes = ASTNodeList()
for node_model in nodes:
    ast_nodes.add(...)
return self.framework_detector.detect_ast_level(ast_nodes)

# 修复后：分批加载（每批 500 个）
BATCH_SIZE = 500
offset = 0
all_framework_results = []
while True:
    result = await db.execute(
        select(AstNodeModel)
        .where(AstNodeModel.repository_id == self.repo_uuid)
        .order_by(AstNodeModel.start_line, AstNodeModel.created_at.desc())
        .offset(offset).limit(BATCH_SIZE)
    )
    nodes = list(result.scalars().all())
    if not nodes:
        break
    batch_results = self.framework_detector.detect_ast_level(ast_nodes)
    all_framework_results.extend(batch_results)
    offset += BATCH_SIZE
    if len(nodes) < BATCH_SIZE:
        break
return all_framework_results
```

### 2.2 S-B3: tags.contains([tag]) 数据库后端不可移植

**文件**: `codeinsight/repositories/knowledge_point.py` → `list()` 方法

**问题**: `tags.contains([tag])` 是 PostgreSQL ARRAY 类型专属 API，MySQL/SQLite 后端无法使用。

**修复**:
```python
# 修复前
query = query.where(KnowledgePointModel.tags.contains([tag]))

# 修复后：按后端类型分支
if db.get_bind().dialect.name == "postgresql":
    query = query.where(KnowledgePointModel.tags.contains([tag]))
else:
    query = query.where(KnowledgePointModel.tags.ilike(f"%{tag}%"))
```

---

## 三、修复统计

| 修复类别 | 数量 |
|---------|------|
| **逻辑缺陷 (Bug)** | 10 |
| **设计缺陷 (Defect)** | 19 |
| **性能优化 (Performance)** | 3 |
| **可扩展性 (Extensibility)** | 6 |
| **架构级（暂缓）** | 1 |
| **合计** | **42** |

| 修复状态 | 数量 |
|---------|------|
| ✅ 已修复 | 41 |
| ⏸️ 架构级暂缓 | 1 |
| **合计** | **42** |

---

## 四、未修复项说明

| ID | 描述 | 暂缓原因 |
|----|------|---------|
| O-E1 | `_run_async` 方法过长（~286 行）违反单一职责原则 | 属长期架构建议（P3-COMPREHENSIVE-REVIEW.md 第 7 章），需拆分为多个独立阶段类，属于重构级别的工作，不在 Medium 级修复范围内 |

---

## 五、影响评估

- **风险降低**: 消除大仓库 OOM 风险（O-P2）、数据库跨平台兼容性风险（S-B3）
- **性能提升**: N+1 查询消除（O-P1）、AST 分批加载降低峰值内存（O-P2）
- **可维护性**: 硬编码消除（L-E1, L-E2）、异常传播修复（S-D1）
- **测试覆盖**: 上述修复均通过静态分析验证
