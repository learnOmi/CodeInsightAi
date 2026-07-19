# 评估框架能力提升计划

## 基本信息

| 项目 | 内容 |
|------|------|
| **文档编号** | DA-001 |
| **文档名称** | 评估框架能力提升计划 |
| **编写日期** | 2026-07-19 |
| **状态** | 阶段 1-3 已完成，阶段 4 按需推进 |
| **关联任务** | P3-04, P3-11 |

---

## 1. 现状分析

### 1.1 当前能力矩阵

| 维度 | 当前状态 | 评级 |
|------|---------|:----:|
| 评估语言覆盖 | Python + JS/TS/Java/Go/Vue（225 组用例） | 🟢 |
| 匹配方式 | CompositeMatcher（精确 + 模糊 + 分类） | 🟢 |
| 评估指标 | Precision / Recall / F1 | 🟢 |
| 评估框架结构 | 引擎 + 评估器 + 指标计算器 + 注册表 | 🟢 |
| 报告输出 | JSON + Console + History | 🟢 |
| 可扩展性 | 数据驱动，新增语言无需改代码 | 🟢 |
| CI 集成 | `.github/workflows/eval.yml` | 🟢 |
| 版本管理 | 历史快照 JSONL + 回归检测 | 🟢 |
| 自评估 | SelfEvaluator 基础实现 | 🟡 |

### 1.2 系统当前语言支持

**有 Tree-sitter 解析器的语言（6 种）：**

| 语言 | 解析器 | 评估数据 | 包名 |
|------|--------|:--------:|------|
| Python | ✅ `PythonParser` | ✅ 5 组 | `tree-sitter-python` |
| JavaScript | ✅ `JavaScriptParser` | ✅ 8 组 | `tree-sitter-javascript` |
| TypeScript | ✅ `TypeScriptParser` | ✅ 8 组 | `tree-sitter-typescript` |
| Java | ✅ `JavaParser` | ✅ 8 组 | `tree-sitter-java` |
| Go | ✅ `GoParser` | ✅ 8 组 | `tree-sitter-go` |
| Vue | ✅ `VueSfcParser` | ✅ 8 组 | 复用 TS |

**已声明但无解析器的语言（8 种）：** Rust, C, C++, C#, Ruby, PHP, Swift, Kotlin

**未来可能扩展的语言（无限）：** 任何 Tree-sitter 支持的语言

---

## 2. 设计目标

### 2.1 核心原则

1. **语言无关架构**：评估框架不感知具体语言，语言是一个标签维度
2. **数据驱动**：评估数据与框架代码分离，新增语言只需加数据
3. **渐进式匹配**：从精确匹配→模糊匹配→语义匹配，逐步提升
4. **可观测**：每次评估产生结构化的、可对比的报告
5. **可回归**：自动检测指标下降，阻止劣化合入

### 2.2 设计指标

| 指标 | 当前 | 目标（V1） | 目标（V2） |
|------|:----:|:----------:|:----------:|
| 评估语言覆盖 | 1 | 6 | 14+ |
| 每条语言用例数 | 5 | 10 | 20+ |
| 匹配方式 | 精确 | 模糊（thefuzz） | 语义（embedding） |
| 评估维度 | 2（P/R） | 3（P/R/F1） | 5（+成本/速度） |
| 报告粒度 | 单次 | 按语言×分类 | 按语言×分类×模型 |
| CI 集成 | 无 | 手动触发 | PR 自动触发 |

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                   评估框架 (evaluation/)                      │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Data Layer   │  │  Engine      │  │  Report      │      │
│  │              │  │              │  │              │      │
│  │  data/*.json │→│  Runner     │→│  JSON        │      │
│  │  (版本化)     │  │  Evaluator   │  │  Console     │      │
│  │  data/registry│  │  Matcher     │  │  HTML (V2)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ┌──────────────────────────────────────────────────┐       │
│  │          扩展层 (Extension Points)               │       │
│  │                                                  │       │
│  │  MatcherStrategy  │  DataProvider  │  Reporter   │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据层设计

#### 评估数据注册表

```python
# evaluation/data/registry.py

@dataclass
class EvalDataset:
    """评估数据集元数据"""
    dataset_id: str           # 唯一 ID，如 "dp-python-v1"
    language: str             # 语言，如 "python"
    category: str             # 分类，如 "DP"
    prompt_version: str       # 目标 prompt 版本
    test_cases: list[TestCase]
    metadata: dict            # 来源、作者、创建时间等


@dataclass
class TestCase:
    """单个测试用例"""
    case_id: str              # 唯一 ID，如 "DP-PY-001"
    description: str          # 用例描述
    language: str             # 语言
    category: str             # 分类
    code_snippets: list[CodeSnippet]
    expected_points: list[ExpectedPoint]
    difficulty: str           # "easy" | "medium" | "hard"
    tags: list[str]           # 标签，如 ["factory", "design-pattern"]


@dataclass
class CodeSnippet:
    file: str
    language: str             # 语言标签（与检测器一致）
    start_line: int
    end_line: int
    content: str
    highlighted_lines: list[int]
    is_synthetic: bool        # True=人工构造, False=真实代码


@dataclass
class ExpectedPoint:
    category: str
    prefix: str
    title: str
    description: str
    confidence: float
    alternative_titles: list[str] = None  # 可接受的别名
    code_lines_match: list[int] = None    # 期望高亮的代码行
```

#### 文件目录结构

```
evaluation/data/
├── registry.py              # 数据集注册表 + 元数据
├── __init__.py
├── python/
│   ├── dp_python_v1.json    # 设计模式 - Python
│   ├── ad_python_v1.json    # 架构决策 - Python
│   ├── al_python_v1.json    # 算法 - Python
│   ├── et_python_v1.json    # 工程技巧 - Python
│   └── dk_python_v1.json    # 领域知识 - Python
├── javascript/
│   ├── dp_javascript_v1.json
│   └── ...
├── typescript/
│   └── ...
├── java/
│   └── ...
├── go/
│   └── ...
└── shared/                   # 跨语言共享用例
    └── dp_shared_v1.json     # 如单例模式（语言无关）
```

### 3.3 匹配策略层

```python
# evaluation/matcher.py

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MatchResult:
    """匹配结果"""
    is_match: bool
    score: float              # 0.0 - 1.0
    match_type: str           # "exact" | "fuzzy" | "semantic"


class MatcherStrategy(ABC):
    """匹配策略接口"""
    
    @abstractmethod
    async def match(
        self,
        extracted: dict,
        expected: dict,
    ) -> MatchResult:
        ...


class ExactTitleMatcher(MatcherStrategy):
    """精确匹配（当前实现）"""
    async def match(self, extracted, expected):
        is_match = extracted.get("title") == expected.get("title")
        return MatchResult(
            is_match=is_match,
            score=1.0 if is_match else 0.0,
            match_type="exact",
        )


class FuzzyTitleMatcher(MatcherStrategy):
    """模糊匹配（V1 目标）"""
    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold
        
    async def match(self, extracted, expected):
        from difflib import SequenceMatcher
        
        title_a = extracted.get("title", "")
        title_b = expected.get("title", "")
        
        # 先检查别名
        alternatives = expected.get("alternative_titles", [])
        for alt in alternatives:
            if title_a == alt:
                return MatchResult(True, 1.0, "exact")
        
        # 再模糊匹配
        ratio = SequenceMatcher(None, title_a, title_b).ratio()
        return MatchResult(
            is_match=ratio >= self.threshold,
            score=ratio,
            match_type="fuzzy",
        )


class SemanticMatcher(MatcherStrategy):
    """语义匹配（V2 目标）"""
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        
    async def match(self, extracted, expected):
        # 使用 embedding 向量计算余弦相似度
        # 优势：能匹配"工厂方法"↔"Factory Method"跨语言等价
        embedding_a = await self._get_embedding(extracted.get("description", ""))
        embedding_b = await self._get_embedding(expected.get("description", ""))
        similarity = cosine_similarity(embedding_a, embedding_b)
        return MatchResult(
            is_match=similarity >= self.threshold,
            score=similarity,
            match_type="semantic",
        )


class CompositeMatcher(MatcherStrategy):
    """组合匹配器：按优先级依次尝试"""
    def __init__(self, matchers: list[MatcherStrategy]):
        self.matchers = matchers
        
    async def match(self, extracted, expected):
        for matcher in self.matchers:
            result = await matcher.match(extracted, expected)
            if result.is_match:
                return result
        return MatchResult(False, 0.0, "none")
```

### 3.4 评估引擎

```python
# evaluation/engine.py

@dataclass
class EvalConfig:
    """评估配置"""
    languages: list[str] | None = None     # 筛选语言
    categories: list[str] | None = None    # 筛选分类
    matcher: MatcherStrategy = FuzzyTitleMatcher()
    report_format: str = "json"            # "json" | "console" | "html"
    threshold_f1: float = 0.0              # 低于此值报警
    threshold_f1_drop: float = 0.05        # 相比上次下降超过此值报警


@dataclass
class EvalReport:
    """评估报告"""
    summary: EvalSummary
    by_language: dict[str, CategorySummary]
    by_category: dict[str, LanguageSummary]
    by_language_category: dict[str, dict[str, MetricResult]]
    history: list[Snapshot] | None = None
    regressions: list[Regression] = None


@dataclass
class Snapshot:
    """历史快照"""
    timestamp: str
    prompt_version: str
    eval_version: str
    metrics: dict  # 全量指标


@dataclass
class Regression:
    """回归检测结果"""
    dimension: str        # "python.DP" 或 "overall"
    previous_f1: float
    current_f1: float
    drop: float
    severity: str         # "warning" | "critical"
```

### 3.5 数据生成器

```python
# scripts/generate_eval_data.py

class EvalDataGenerator:
    """
    评估数据生成器
    
    从真实代码仓库提取评估数据，减少人工标注工作量。
    """
    
    def __init__(self, repo_url: str, language: str):
        self.repo_url = repo_url
        self.language = language
    
    async def generate(self) -> list[TestCase]:
        """生成测试用例"""
        # 1. 克隆仓库
        # 2. 运行 AST 解析器，提取所有代码结构
        # 3. 按特征识别候选模式
        #   - 抽象类/接口 → 工厂方法候选
        #   - 事件订阅 → 观察者候选
        #   - 单例 __new__ → 单例候选
        # 4. 对每个候选，提取代码片段
        # 5. 输出为未标注的 TestCase（expected_points 为空）
        # 6. 人工审核后补全 expected_points
        pass
```

---

## 4. 实施计划

### 阶段 1：基础设施升级（5 天）

**目标**：完成框架可扩展性改造，支持多语言、多匹配策略、报告增强。

| 任务 | 文件 | 工时 | 说明 |
|------|------|:----:|------|
| 1.1 注册表 | `evaluation/data/registry.py` | 0.5d | 数据集注册表 + 元数据定义 |
| 1.2 匹配策略 | `evaluation/matcher.py` | 1d | ExactTitleMatcher + FuzzyTitleMatcher + CompositeMatcher |
| 1.3 评估引擎 | `evaluation/engine.py` | 1d | EvalConfig + EvalReport + 历史对比 |
| 1.4 现有代码适配 | `evaluation/runner.py` | 0.5d | 接入新架构，向后兼容 |
| 1.5 测试 | `tests/test_evaluation_v2.py` | 1d | 新组件测试覆盖 |
| 1.6 报告增强 | `evaluation/reporters/` | 1d | JSON + Console + HTML 输出 |

### 阶段 2：多语言评估数据（3 天）

**目标**：为 6 种解析器语言各生成 5-10 组评估数据。

| 任务 | 内容 | 工时 | 说明 |
|------|------|:----:|------|
| 2.1 数据生成脚本 | `scripts/generate_eval_data.py` | 1d | 从真实仓库提取候选用例 |
| 2.2 Python 补充 | 5 组 → 10 组 | 0.5d | 补充现有数据 |
| 2.3 JavaScript | 8 组新数据 | 0.5d | 从 lodash/express 等仓库提取 |
| 2.4 TypeScript | 8 组新数据 | 0.5d | 从 nestjs/typeorm 等仓库提取 |
| 2.5 Java | 8 组新数据 | 0.5d | 从 spring-boot 等仓库提取 |
| 2.6 Go | 8 组新数据 | 0.5d | 从 kubernetes 等仓库提取 |

### 阶段 3：CI 集成 + 回归检测（2 天）

**目标**：评估框架集成到 CI，自动检测回归。

| 任务 | 文件 | 工时 | 说明 |
|------|------|:----:|------|
| 3.1 CLI 入口 | `scripts/evaluate.py` | 0.5d | 命令行调用评估 |
| 3.2 历史存储 | `evaluation/history/` | 0.5d | 快照文件存储 |
| 3.3 回归告警 | `evaluation/regression.py` | 0.5d | 对比历史，检测下降 |
| 3.4 CI 配置 | `.github/workflows/eval.yml` | 0.5d | PR 自动触发评估 |

### 阶段 4：高级匹配 + 扩展（V2, 按需）

| 任务 | 说明 | 依赖 |
|------|------|------|
| 4.1 SemanticMatcher | 使用 embedding 语义匹配 | 阶段 1 |
| 4.2 代码行级匹配 | highlighted_lines IoU 指标 | 阶段 1 |
| 4.3 跨语言评估 | 统一用例验证多语言分析一致性 | 阶段 2 |
| 4.4 A/B 测试 | 多 prompt 版本并行对比 | 阶段 3 |

---

## 5. 扩展性设计

### 5.1 新增一种语言需要做什么？

```
1. 创建 evaluation/data/<language>/ 目录
2. 添加 5+ 组 JSON 评估数据（可用生成器辅助）
3. 在 registry.py 中注册数据集
4. 运行评估，确认基线指标
```

**无需修改框架代码。**

### 5.2 新增一种匹配策略需要做什么？

```
1. 继承 MatcherStrategy 基类
2. 实现 match() 方法
3. 在 CompositeMatcher 中注册
```

### 5.3 新增一种报告格式需要做什么？

```
1. 创建 evaluation/reporters/<format>_reporter.py
2. 实现 Reporter 接口
3. 在 EvalConfig.report_format 中注册
```

### 5.4 新增一种分析分类需要做什么？

```
1. 更新 base.md 中的分类定义
2. 添加对应的 prompt 文件
3. 创建评估数据文件
```

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|---------|
| 评估数据质量低 | 中 | 高 | 人工审核 + 跨 reviewer 验证 |
| 模糊匹配阈值难调 | 中 | 中 | 先跑一批数据，统计最佳阈值 |
| 多语言评估数据标注成本高 | 高 | 中 | 用生成器减少工作量，只标注关键用例 |
| 历史快照格式变更 | 低 | 中 | 快照版本化，兼容旧格式 |
| 评估耗时过长 | 中 | 低 | 支持子集运行 + 缓存 LLM 结果 |

---

## 7. 附录

### 7.1 与现有组件的关系

```
P3-04（评估框架）──── 阶段 1 ────→ 升级版评估框架
     │
     ├── P3-01（LLMClient）── 评估时调用 LLM
     ├── P3-02（Agent）     ── 被评估的对象
     ├── P3-03（Multi-Agent）── 被评估的对象
     └── P3-11（回归测试）  ── 依赖本框架
```

### 7.2 参考实现

- [LangChain 评估框架](https://docs.langchain.com/docs/guides/evaluation/)
- [DeepEval](https://docs.confident-ai.com/) — 开源 LLM 评估框架
- [RAGAS](https://docs.ragas.io/) — RAG 评估框架