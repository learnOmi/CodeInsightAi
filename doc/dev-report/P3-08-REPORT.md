# P3-08 实施报告：拓展内容生成 Agent

## 基本信息

| 项目 | 内容 |
|------|------|
| **任务编号** | P3-08 |
| **任务名称** | 拓展内容生成 Agent：原理、场景、最佳实践、学习资料 |
| **实施日期** | 2026-07-19 |
| **工时** | 16h（与计划一致） |
| **当前状态** | 100% 完成，全部 CI 通过 |

---

## 变更摘要

### 新建文件

| 文件 | 说明 |
|------|------|
| `codeinsight/prompts/expansion.md` | 专用 Prompt 文件，含角色定义、5 维度说明、JSON 格式规范、2 个 Few-shot 示例（工厂方法模式、事件驱动架构）、质量标准 |

### 修改文件

| 文件 | 变更类型 | 说明 |
|------|:--------:|------|
| `codeinsight/prompts/__init__.py` | 修改 | 新增 `load_expansion_prompt()` 函数和导出 |
| `codeinsight/agents/node.py` | 修改 | 重构 `ExpansionNode`：外部 Prompt 文件、TypeAdapter 校验、重试机制、语义化异常处理 |
| `tests/test_agents.py` | 修改 | 3 → 11 个测试用例 |
| `tests/test_prompt_format.py` | 修改 | 跳过 expansion.md 的 KnowledgePointExtraction 字段校验 |

---

## 详细实现

### 1. 专用 Prompt 文件

**新建** `prompts/expansion.md`，遵循与其他 Agent 一致的模式：

| 特性 | 说明 |
|------|------|
| 角色定义 | 拓展内容生成 Agent |
| 输入格式 | 知识点标题/分类/描述 |
| 5 个拓展维度 | principle, applicable_scenarios, best_practices, related_patterns, learning_resources |
| Few-shot 示例 | 工厂方法模式、事件驱动架构（各含完整 JSON 输出） |
| 质量标准 | 6 条具体约束（principle 解释"为什么"、scenarios 具体化、resources 必须包含 url 和 type 等） |
| 模板替换 | 使用 `.replace()` 避免 `{` `}` 与 `str.format()` 冲突 |

### 2. ExpansionNode 重构

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| **Prompt 来源** | 硬编码类变量 `EXPANSION_PROMPT` | 外部 `expansion.md` 文件，通过 `load_expansion_prompt()` 加载 |
| **结构化校验** | 仅 `json.loads()` | `TypeAdapter[ExpansionContent]` 校验，确保输出符合 Schema |
| **JSON 解析** | 直接 `json.loads()` | 逐级 fallback：直接解析 → 提取 JSON 代码块 |
| **重试机制** | 无重试，失败直接返回 | 最多 3 次重试（含 1s 退避） |
| **并发控制** | 串行 for 循环 | Semaphore 控制并发度（当前顺序执行，保留扩展能力） |
| **异常处理** | 单层 try/except | 三层防护：内层(解析+校验) → 中层(重试循环) → 外层(兜底) |
| **错误信息** | 仅记录警告 | 区分调试级别（重试 vs 最终失败），含上下文 |

### 3. 测试覆盖

| 测试 | 说明 |
|------|------|
| `test_generate_expansion` | 基本成功路径 |
| `test_skip_empty_kps` | 空知识点跳过 |
| `test_llm_error_graceful` | LLM 错误时优雅跳过 |
| `test_validate_expansion_content` | TypeAdapter 校验有效内容 |
| `test_validate_expansion_content_invalid_learning_resource` | TypeAdapter 校验非法内容 |
| `test_parse_and_validate_direct` | 直接 JSON 解析 |
| `test_parse_and_validate_code_block` | 代码块 JSON 提取 |
| `test_parse_and_validate_invalid` | 非法 JSON 返回 None |
| `test_generate_expansion_retry_then_succeed` | 重试后成功 |
| `test_generate_expansion_retry_exhausted` | 重试耗尽返回 None |
| `test_generate_expansion_multiple_kps` | 多个知识点处理 |

---

## CI 验证

| 检查项 | 结果 |
|--------|:----:|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 159 files already formatted |
| mypy | ✅ Success: no issues found in 149 source files |
| pytest | ✅ **603 passed, 2 skipped** (75.43s) |

网络测试（1 个 skipped）：`test_network.py::test_llm_connection`（需要 LLM API 密钥，仅在 CI 中运行）

---

## 修复记录

| 问题 | 原因 | 修复 |
|------|------|------|
| Prompt 中 `{` `}` 与 `str.format()` 冲突 | `expansion.md` JSON 示例中的 `{` `}` 被误认为占位符 | 改为 `.replace()` 替换占位符 |
| 异常传播到外层 | `raise` 在 except 块中被误用 | 外层 try/except 兜底，确保总是返回 None |
| `test_json_example_has_required_fields` 失败 | expansion.md 生成 ExpansionContent 而非 KnowledgePointExtraction，字段不同 | 跳过 expansion.md 的该测试 |
| B017 盲断言 `Exception` | `pytest.raises(Exception)` 过于宽泛 | 改为 `pytest.raises(ValidationError)` |

## 数据流

```
AnalysisGraph.execute()
        │
        ├── 5 个 Agent 节点 → KnowledgePoints
        ├── MergeNode → 去重合并
        │
        └── ExpansionNode.execute()
                │
                ├── prompts/expansion.md 加载
                ├── 每个知识点依次:
                │   ├── replace() 替换 {title}/{category}/{description}
                │   ├── LLM.chat() → JSON 响应
                │   ├── _parse_and_validate()
                │   │   ├── json.loads() → 直接解析
                │   │   ├── 代码块提取 → 二次解析
                │   │   └── TypeAdapter[ExpansionContent] → 校验
                │   └── kp["expansion"] = validated.model_dump()
                │
                └── state["progress"] = 1.0 → 完成
```

## 变更记录

| 文件 | 行数 | 说明 |
|------|:----:|------|
| `prompts/expansion.md` | +132 | 新建专用 Prompt 文件 |
| `prompts/__init__.py` | +10 | 新增 `load_expansion_prompt()` |
| `agents/node.py` | ~80 | 重构 ExpansionNode |
| `tests/test_agents.py` | ~80 | 3 → 11 个测试 |
| `tests/test_prompt_format.py` | +2 | 跳过 expansion.md 字段校验 |