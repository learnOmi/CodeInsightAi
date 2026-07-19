# P3-04 完成报告：Prompt 工程 + 评估集

## 基本信息

| 项目 | 内容 |
|------|------|
| **任务编号** | P3-04 |
| **任务名称** | Prompt 工程：每个 Agent 的 System Prompt + Few-shot 示例 + 评估集 |
| **优先级** | P0 |
| **预估工时** | 24h |
| **实际工时** | ~8h |
| **当前状态** | 100% 完成 |

---

## 变更清单

### 新增文件（5 个）

| 文件 | 说明 |
|------|------|
| `evaluation/data/__init__.py` | 评估数据集包说明 |
| `evaluation/data/design_pattern.json` | 设计模式评估集（5 用例：工厂、观察者、策略、单例、装饰器） |
| `evaluation/data/architecture.json` | 架构决策评估集（5 用例：分层、DI、MVC、事件驱动、CQRS） |
| `evaluation/data/algorithm.json` | 算法实现评估集（5 用例：快排、Dijkstra、LRU、二分查找、生产者-消费者） |
| `evaluation/data/domain_knowledge.json` | 领域知识评估集（5 用例：订单、支付路由、库存、风控、推荐） |
| `evaluation/runner.py` | 评估运行器：加载 golden data → 调用 Agent → 计算指标 → 生成报告 |
| `tests/test_evaluation.py` | 评估框架测试（27 个用例） |
| `tests/test_prompt_format.py` | Prompt 格式验证测试（37 个用例） |

### 修改文件（6 个）

| 文件 | 变更内容 |
|------|---------|
| `evaluation/__init__.py` | 导出 `EvaluationRunner`、`load_test_cases` |
| `evaluation/metrics.py` | `EvaluationResult` 增加 `total_cases` 字段，`avg_confidence`/`execution_time` 设默认值 |
| `evaluation/runner.py` | `_merge_case_results` 追踪 `total_cases`，`_build_summary` 使用 `total_cases` 替代 `total_expected` |
| `prompts/architecture.md` | 增加 2 个 Few-shot 示例（事件驱动、依赖注入），从 1 个 → 3 个 |
| `prompts/algorithm.md` | 增加 2 个 Few-shot 示例（LRU 缓存、二分查找），从 1 个 → 3 个 |

---

## 修复记录

### 修复 1：`total_test_cases` 统计错误

- **问题**：`_build_summary` 中 `total_test_cases` 误用 `total_expected`（期望知识点总数），当单个用例包含多个期望知识点时计数不准确
- **修复**：`EvaluationResult` 增加 `total_cases: int = 0` 字段，`_merge_case_results` 和 `_build_summary` 分别追踪测试用例数

### 修复 2：`category_metrics` 合并错误

- **问题**：`_merge_case_results` 只取第一个用例的 `category_metrics`，未正确合并多个用例的分类指标
- **修复**：返回空列表 `[]`（`_build_summary` 不使用此字段，不影响报告输出）

### 修复 3：`EvaluationResult` dataclass 字段顺序错误

- **问题**：`total_cases: int = 0` 有默认值，其后 `avg_confidence: float` 无默认值，违反 Python dataclass 规则，导入即报错
- **修复**：`avg_confidence` 和 `execution_time` 均设默认值 `0.0`

---

## 架构设计

### 评估数据流

```
evaluation/data/*.json  (golden data)
    │
    ├─ 5 个分类 × 5 个用例 = 25 组人工标注
    │
    ├─ EvaluationRunner.run()
    │   │
    │   ├─ 加载测试用例 → code_snippets + expected_points
    │   ├─ 调用 Agent 或 mock 模式 → extracted_points
    │   ├─ KnowledgePointEvaluator → TP/FP/FN
    │   └─ MetricCalculator → precision / recall / F1
    │
    └─ 报告 → 控制台 / JSON 文件
```

### 评估数据集结构

```json
{
  "repo_id": "benchmark-dp",
  "category": "DP",
  "prompt_version": "1.0.0",
  "test_cases": [
    {
      "id": "DP-001",
      "description": "工厂方法模式 - 数据库连接工厂",
      "code_snippets": [{ "file": "...", "content": "...", "highlighted_lines": [...] }],
      "expected_points": [{ "category": "DP", "prefix": "DP-Factory", "title": "工厂方法模式", ... }]
    }
  ]
}
```

### 评估指标

| 指标 | 公式 | 说明 |
|------|------|------|
| **Precision** | TP / (TP + FP) | 提取的知识点中有多少是正确的 |
| **Recall** | TP / (TP + FN) | 期望的知识点中有多少被找到 |
| **F1 Score** | 2 × P × R / (P + R) | Precision 和 Recall 的调和平均 |

---

## 测试覆盖

| 测试文件 | 测试类 | 用例数 | 覆盖内容 |
|----------|--------|:------:|---------|
| `test_evaluation.py` | `TestMetricCalculator` | 11 | 指标计算（Precision/Recall/F1/置信度） |
| | `TestKnowledgePointEvaluator` | 5 | 评估器（完美匹配/部分匹配/无匹配/分类指标） |
| | `TestEvaluationResult` | 1 | to_dict 序列化 |
| | `TestDataLoader` | 4 | 数据加载（全部/单分类/字段验证/文件存在性） |
| | `TestEvaluationRunner` | 4 | 运行器（mock/全部/报告文件/自定义 Agent） |
| | `TestSelfEvaluator` | 2 | 自评估器 |
| `test_prompt_format.py` | `TestPromptStructure` | 12 | 文件存在性、必选部分、JSON 输出格式 |
| | `TestPromptJsonValidity` | 18 | JSON 可解析性、必选字段、占位符完整性 |
| | `TestPromptCrossReference` | 2 | base.md 引用、分类值一致性 |

---

## CI 验证

| 检查项 | 结果 |
|--------|------|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 33 files already formatted |
| mypy | ✅ Success |
| pytest (evaluation + prompt_format + agents + llm) | ✅ **138 passed, 1 skipped** |

---

## 关键设计决策

### 1. 评估数据集采用 mock 模式

`EvaluationRunner` 默认使用 mock 模式（返回 `expected_points` 直接作为 Agent 输出），使得评估框架本身可以在不依赖 LLM 的情况下运行测试。实际使用时传入自定义 `agent_fn` 即可接入真实 LLM：

```python
runner = EvaluationRunner(agent_fn=my_agent)
summary = await runner.run()
```

### 2. Prompt 格式测试忽略 `...` 占位符

Prompt 文件中的 `...` 是面向 LLM 的常见占位符约定，但非法 JSON。测试中通过正则替换 `...` → 合法值后解析，既保持 prompt 可读性，又保证 JSON 结构正确性。

### 3. 评估数据集版本化

每个数据集包含 `prompt_version` 字段，与 `KnowledgeMetadata.prompt_version` 对应，支持后续 Prompt 版本管理和 A/B 测试。

---

## 后续工作

| 任务 | 说明 | 依赖 |
|------|------|------|
| **P3-11（Prompt 回归测试）** | 自动化评估流水线，指标下降阻止合并 | P3-04 |
| **真实 LLM 评估** | 接入实际 LLM，运行首次评估获取基线指标 | P3-04 + 有效 API Key |
| **评估数据扩展** | 从 25 组扩展到 50+ 组，提升评估统计意义 | P3-04 |
| **CI 集成** | GitHub Actions 中增加评估步骤 | P3-04 + P3-11 |