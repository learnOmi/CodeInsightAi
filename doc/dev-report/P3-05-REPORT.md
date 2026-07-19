# P3-05 实施报告：知识点 Schema 定义与校验

## 基本信息

| 项目 | 内容 |
|------|------|
| **任务编号** | P3-05 |
| **任务名称** | 知识点 Schema 定义与校验（Pydantic 严格模型，含 5 类分类） |
| **实施日期** | 2026-07-19 |
| **工时** | 8h（与计划一致） |
| **当前状态** | 100% 完成，全部 CI 通过 |

---

## 变更摘要

### 修改/新建文件

| 文件 | 变更类型 | 说明 |
|------|:--------:|------|
| `codeinsight/schemas/constants.py` | **新建** | 共享常量模块，统一管理 `CATEGORY_NAMES` 映射 |
| `codeinsight/schemas/knowledge.py` | 修改 | `KnowledgeCategory` 枚举值统一为短格式；添加 Pydantic 严格约束 |
| `codeinsight/agents/node.py` | 修改 | 导入共享常量；修复 `_normalize_knowledge_points()` 保留 expansion；修复 fallback 缺失 prefix |
| `codeinsight/evaluation/evaluator.py` | 修改 | 导入共享常量，移除重复定义 |
| `codeinsight/api/knowledge.py` | 修改 | 更新 API 文档注释 |
| `tests/test_agents.py` | 修改 | 新增 8 个边界校验测试用例 |
| `tests/test_knowledge_points.py` | 修改 | 更新 `"DP-"` → `"DP"` 测试数据 |

---

## 详细实现

### 1. 统一 `category` 格式

**变更**：`KnowledgeCategory` 枚举值从 `"DP-"` → `"DP"`（移除尾部 `-`）

| 字段 | 旧值 | 新值 |
|------|------|------|
| `DESIGN_PATTERN` | `"DP-"` | `"DP"` |
| `ARCHITECTURE_DECISION` | `"AD-"` | `"AD"` |
| `ALGORITHM` | `"AL-"` | `"AL"` |
| `ENGINEERING_TIP` | `"ET-"` | `"ET"` |
| `DOMAIN_KNOWLEDGE` | `"DK-"` | `"DK"` |

**影响范围**：
- `KnowledgePointExtraction.category` 已使用 `"DP"` 格式 → 不变
- `KnowledgePoint.category` 使用 `KnowledgeCategory` 枚举 → 自动同步
- ORM 模型存储字符串 → 无需变更
- API 响应序列化 → 格式统一

### 2. Pydantic 严格约束

**`KnowledgePointExtraction`** 新增/增强的字段约束：

| 字段 | 约束 | 说明 |
|------|------|------|
| `category` | `pattern=r"^(DP\|AD\|AL\|ET\|DK)$"` | 仅允许 5 个标准分类 |
| `prefix` | `pattern=r"^(DP\|AD\|AL\|ET\|DK)-.+$"` | 必须包含分类前缀，如 `DP-Factory` |
| `title` | `min_length=1` | 非空 |
| `description` | `min_length=1` | 非空 |
| `confidence` | `ge=0.0, le=1.0` | 0~1 范围 |

**`CodeSnippetExtraction`**：
| `start_line` / `end_line` | `gt=0` | 行号必须为正数 |

**`CallChainExtraction`**：
| `node_type` | `Literal["function", "class", "method", "function_call", "import", "module"]` | 与 `CallChainNode` 一致 |

### 3. 修复 `_normalize_knowledge_points()` 保留 `expansion`

**Before**：始终设置 `"expansion": {}`，丢弃 LLM 返回的拓展内容

**After**：保留 LLM 输出的拓展内容
```python
expansion = point.expansion.model_dump() if point.expansion else {}
# ...
"expansion": expansion,
```

### 4. 共享常量模块

**新建** `schemas/constants.py`：

```python
CATEGORY_NAMES: dict[str, str] = {
    "DP": "设计模式",
    "AD": "架构设计",
    "AL": "算法实现",
    "ET": "工程技术",
    "DK": "领域知识",
}
CATEGORY_LIST: list[str] = ["DP", "AD", "AL", "ET", "DK"]
```

**波及**：`agents/node.py` 和 `evaluation/evaluator.py` 中的重复定义被移除

### 5. 修复 LLM 解析 fallback 丢失字段

在 `_parse_response()` 的 fallback 分支中新增 `"prefix": f"{category}-Unknown"` 字段，确保 fallback 输出的格式与正常输出一致。

---

## 测试覆盖

### 新增边界测试（8 个）

| 测试方法 | 覆盖场景 |
|----------|---------|
| `test_invalid_confidence_above_range` | 置信度 > 1.0 拒绝 |
| `test_invalid_confidence_below_range` | 置信度 < 0.0 拒绝 |
| `test_invalid_category_format` | `"DP-"` 格式拒绝（应为 `"DP"`） |
| `test_invalid_prefix_format` | 缺少分类前缀拒绝 |
| `test_empty_title` | 空 title 拒绝 |
| `test_empty_description` | 空 description 拒绝 |
| `test_code_snippet_negative_line` | 负行号拒绝 |
| `test_call_chain_node_type_invalid` | 无效 node_type 拒绝 |

### 全量测试结果

| 测试套件 | 结果 |
|----------|:----:|
| `TestKnowledgePointExtraction` | ✅ **12 passed**（+8 新用例） |
| 全部测试 | ✅ **588 passed, 1 skipped**（+8 新用例） |

---

## CI 验证

| 检查项 | 结果 |
|--------|:----:|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 157 files already formatted |
| mypy | ✅ Success: no issues found in 148 source files |
| pytest | ✅ **588 passed, 1 skipped** (70.56s) |

---

## 代码质量改进

### 消除重复定义

`CATEGORY_NAMES` 之前在两处重复定义：
- `agents/node.py:29-35`（4 处引用）
- `evaluation/evaluator.py:25-31`（1 处引用）

全部集中到 `schemas/constants.py`，单一事实来源。

### 修复 bug

| Bug | 影响 | 修复方式 |
|-----|------|---------|
| `_normalize_knowledge_points()` 丢弃 expansion | ExpansionNode 重新生成，浪费 LLM 调用 | 保留 LLM 原始输出 |
| Fallback 缺失 prefix 字段 | 下游处理可能因字段缺失异常 | 添加 `"prefix": f"{category}-Unknown"` |
| `CallChainExtraction.node_type` 无约束 | 无效数据入库 | 添加 Literal 约束 |

---

## 变更记录

| 文件 | 行数变动 | 说明 |
|------|:--------:|------|
| `schemas/constants.py` | +16 | 新建共享常量模块 |
| `schemas/knowledge.py` | +15/-12 | 枚举值统一 + 严格约束 |
| `agents/node.py` | +7/-8 | 导入常量 + 修复 expansion/prefix |
| `evaluation/evaluator.py` | +2/-8 | 导入常量，移除重复 |
| `api/knowledge.py` | +1/-1 | 文档注释更新 |
| `tests/test_agents.py` | +102 | 8 个边界测试 |
| `tests/test_knowledge_points.py` | +14/-14 | 测试数据格式更新 |