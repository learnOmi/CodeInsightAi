# P3-04 Phase 1 审查报告：评估框架基础设施升级

## 基本信息

| 项目 | 内容 |
|------|------|
| **任务编号** | P3-04 Phase 1 |
| **任务名称** | 评估框架基础设施升级（注册表 + 匹配策略 + 引擎 + 报告 + 测试） |
| **审查日期** | 2026-07-19 |
| **当前状态** | 100% 完成，全部 CI 通过 |

---

## 审查范围

根据 `doc/dev-analysis/P3-04-EVALUATION-FRAMEWORK-UPGRADE.md` 定义的 Phase 1 计划，审查以下组件：

1. **注册表** (`evaluation/data/registry.py`)：数据模型 + JSON 加载 + 注册表
2. **匹配策略** (`evaluation/matcher.py`)：可插拔匹配器体系
3. **评估引擎** (`evaluation/engine.py`)：核心评估流程协调
4. **报告输出器** (`evaluation/reporters/`)：可插拔报告体系
5. **现有代码适配**：`runner.py` 向后兼容
6. **测试** (`tests/test_evaluation_v2.py`)：35 个测试用例

---

## 变更清单

### 新增文件（7 个）

| 文件 | 说明 |
|------|------|
| `evaluation/data/registry.py` | 数据模型：`CodeSnippet`、`ExpectedPoint`、`TestCase`、`EvalDataset`；JSON 加载与注册表 |
| `evaluation/matcher.py` | 匹配策略：`MatcherStrategy`(ABC)、`ExactTitleMatcher`、`FuzzyTitleMatcher`(difflib)、`CategoryMatcher`、`CompositeMatcher` |
| `evaluation/engine.py` | 评估引擎：`EvalConfig`、`EvalEngine`、`EvalReport`、`EvalSummary`、`MetricResult`、`Regression`、`Snapshot` |
| `evaluation/reporters/__init__.py` | 报告输出器包初始化 |
| `evaluation/reporters/base.py` | `Reporter`(ABC) 基类 |
| `evaluation/reporters/json_reporter.py` | `JsonReporter`：JSON 文件输出 |
| `evaluation/reporters/console_reporter.py` | `ConsoleReporter`：控制台表格输出 |
| `tests/test_evaluation_v2.py` | 35 个测试用例，覆盖注册表、匹配器、引擎、报告器 |

### 修改文件（3 个）

| 文件 | 变更内容 |
|------|---------|
| `evaluation/__init__.py` | 导出新组件：`EvalConfig`、`EvalEngine`、`EvalReport`、`EvalSummary`、所有匹配器、所有报告器 |
| `evaluation/runner.py` | 保持向后兼容，`EvaluationRunner` 和 `load_test_cases` 不变 |
| `tests/test_call_graph.py` | 修复 mypy 类型错误：`tags: list` → `tags: list[Any] \| None` |

---

## 架构设计

### 新组件数据流

```
evaluation/data/*.json (golden data)
    │
    ├─ registry.load_dataset_from_file() / load_datasets_from_dir()
    │   │
    │   ├─ EvalDataset(dataset_id, language, category, test_cases, ...)
    │   │   └─ TestCase(case_id, language, category, code_snippets, expected_points, ...)
    │   │
    │   └─ register_dataset() → _registry 内存注册表
    │
    ├─ EvalEngine.run()
    │   │
    │   ├─ _load_test_cases() → list[TestCase] (支持按 language/category 筛选)
    │   ├─ for each TestCase:
    │   │   ├─ agent_fn(code_snippets, category) → extracted_points
    │   │   ├─ KnowledgePointEvaluator.evaluate() → EvaluationResult
    │   │   └─ 按 language×category 分组聚合
    │   ├─ _build_report() → EvalReport
    │   │   ├─ 按语言聚合 → by_language metrics
    │   │   ├─ 按分类聚合 → by_category metrics
    │   │   └─ 按语言×分类聚合 → by_language_category nested metrics
    │   └─ reporters[].report(report) → JsonReporter / ConsoleReporter
    │
    └─ EvalEngine.detect_regressions()
        └─ 对比历史 Snapshot → list[Regression]
```

### 匹配策略体系

```
MatcherStrategy (ABC)
    ├── ExactTitleMatcher    — title 精确匹配
    ├── FuzzyTitleMatcher    — difflib.SequenceMatcher 模糊匹配（阈值 0.8）
    ├── CategoryMatcher      — category 分类匹配
    └── CompositeMatcher     — 组合匹配器
         ├── 先检查 category 是否一致
         └── 再按优先级尝试 ExactTitle → FuzzyTitle
```

### 报告输出器体系

```
Reporter (ABC)
    ├── JsonReporter         — JSON 文件输出 + 日志摘要
    └── ConsoleReporter      — 控制台表格输出（支持 verbose 模式显示语言×分类粒度）
```

### 评估报告结构

```
EvalReport
    ├── summary: EvalSummary
    │   ├── categories_evaluated, total_test_cases, total_extracted
    │   ├── overall_f1, total_time_seconds, timestamp
    ├── by_language: dict[str, MetricResult]
    ├── by_category: dict[str, MetricResult]
    ├── by_language_category: dict[str, dict[str, MetricResult]]
    ├── config: EvalConfig
    ├── history: list[Snapshot]
    └── regressions: list[Regression]
```

---

## 修复记录

### 修复 1：mypy 类型错误 — test_call_graph.py

- **问题**：`tests/test_call_graph.py:35: error: Incompatible types in assignment (expression has type "None", variable has type "list[Any]")`
- **原因**：`FakeFunctionInfo` dataclass 中 `tags: list = None` 的类型注解为 `list[Any]`，但给 `None` 值不兼容
- **修复**：将 `tags: list = None` 改为 `tags: list[Any] | None = None`，并添加 `from typing import Any` 导入

### 修复 2：前后端代码无新增问题

- **ruff check**：0 个错误（全部通过）
- **ruff format**：154 个文件已格式化（无需变更）
- **mypy**：1 个错误已修复 → 0 个错误
- **pytest**：565 passed, 1 skipped（全部通过）

---

## 测试覆盖

### V2 测试 (`test_evaluation_v2.py`)

| 测试类 | 用例数 | 覆盖内容 |
|--------|:------:|---------|
| `TestEvalDataset` | 2 | 数据模型创建和字段验证 |
| `TestLoadDataset` | 4 | JSON 加载、注册表、旧格式兼容、目录加载 |
| `TestExactTitleMatcher` | 3 | 精确匹配/不匹配/空标题 |
| `TestFuzzyTitleMatcher` | 5 | 精确/别名/模糊(达标/不达标)/空标题 |
| `TestCategoryMatcher` | 3 | 分类匹配/不匹配/空字段 |
| `TestCompositeMatcher` | 3 | 组合匹配/分类不匹配/无匹配器 |
| `TestCreateDefaultMatcher` | 2 | 默认创建/使用 |
| `TestEvalEngine` | 5 | 初始状态/运行(mock)/语言筛选/分类筛选/空数据 |
| `TestJsonReporter` | 2 | 文件输出/日志输出 |
| `TestConsoleReporter` | 2 | 标准输出/verbose 模式 |
| `TestMetricResult` | 1 | 默认值 |
| `TestRegression` | 2 | 回归检测/无回归 |
| `TestSnapshot` | 1 | 快照创建 |

**总计：35 个测试用例**

### 全量测试结果

| 测试套件 | 结果 |
|----------|:----:|
| test_evaluation_v2.py | ✅ 35 passed |
| 全部测试 | ✅ **565 passed, 1 skipped** |

---

## CI 验证

| 检查项 | 结果 |
|--------|:----:|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 154 files already formatted |
| mypy | ✅ Success: no issues found in 145 source files |
| pytest | ✅ **565 passed, 1 skipped** (25.96s) |

---

## 关键设计决策

### 1. 语言无关的评估架构

新的评估框架完全基于语言无关设计。`TestCase` 和 `EvalDataset` 将 `language` 作为标签字段而非框架逻辑的一部分，新增语言只需添加 JSON 数据文件，无需修改框架代码。

### 2. 渐进式匹配策略

采用 `CompositeMatcher` 组合模式，按优先级依次尝试匹配策略：
- 先检查 `category` 分类一致性（快速过滤）
- 再尝试精确标题匹配（`ExactTitleMatcher`）
- 最后尝试模糊匹配（`FuzzyTitleMatcher`，基于 `difflib.SequenceMatcher`，阈值 0.8）

这种设计允许未来 V2 轻松添加语义匹配（embedding-based）策略。

### 3. 可插拔报告体系

`Reporter` 抽象基类允许任意数量的输出器同时工作。`EvalEngine` 初始化时接受 `list[Reporter]`，运行时依次调用。当前实现 `JsonReporter` + `ConsoleReporter`，未来可扩展 HTML 报告、Grafana 推送等。

### 4. 向后兼容

`evaluation/runner.py` 中的 `EvaluationRunner` 和 `load_test_cases` 保持原有接口不变，确保现有代码（如 `tests/test_evaluation.py`）不受影响。新引擎通过 `EvalEngine` 提供，旧运行器通过 `EvaluationRunner` 提供。

### 5. 回归检测机制

`EvalEngine.detect_regressions()` 支持对比历史快照（`Snapshot`），自动检测 F1 指标下降。`EvalConfig.threshold_f1_drop`（默认 0.05）控制告警灵敏度，下降 ≥ 0.1 标记为 `critical`。

---

## 后续工作

| 任务 | 说明 | 依赖 |
|------|------|------|
| **Phase 2：多语言评估数据** | 为 6 种支持的语言（Python/JS/TS/Java/Go/Vue）各生成 5-10 组用例 | Phase 1 |
| **Phase 3：CI 集成 + 回归检测** | GitHub Actions 评估步骤，指标下降阻止合并 | Phase 2 |
| **Phase 4：高级匹配 + 扩展 V2** | 语义匹配（embedding-based）、LLM 自评估增强 | Phase 3 |
| **真实 LLM 评估** | 接入实际 LLM，运行首次评估获取基线指标 | Phase 1 + API Key |