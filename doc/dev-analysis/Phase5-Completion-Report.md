# Phase 5 完成报告：外部依赖与跨模块分析

## 一、概述

Phase 5 实现了外部依赖解析与跨模块调用映射能力，将代码分析范围从内部代码扩展到第三方依赖。

### 完成情况
- **计划任务数**：12 项
- **完成任务数**：12 项
- **完成率**：100%
- **测试用例**：27 个，全部通过

---

## 二、交付物清单

### 2.1 新增文件

| 文件路径 | 功能说明 |
|---------|---------|
| `codeinsight/models/external_dependency.py` | 外部依赖 ORM 模型（external_dependencies 表） |
| `codeinsight/schemas/external_dependency.py` | 外部依赖 Pydantic Schema（含 camelCase 别名） |
| `codeinsight/repositories/external_dependency_dao.py` | 外部依赖数据访问层（DAO） |
| `codeinsight/analyzers/dependency_parser.py` | 依赖声明文件解析器（Maven/NPM/Pip/Go） |
| `codeinsight/api/dependencies.py` | 依赖查询 API 路由 |
| `codeinsight/api/frameworks.py` | 框架查询 API 路由 |
| `codeinsight/api/routes.py` | 路由查询 API 路由 |
| `tests/test_parsers/test_phase5_enhancements.py` | Phase 5 单元测试（27 个） |

### 2.2 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `codeinsight/models/__init__.py` | 导出 ExternalDependencyModel |
| `codeinsight/schemas/__init__.py` | 导出 ExternalDependency、ExternalDependencyCreate |
| `codeinsight/repositories/__init__.py` | 导出 ExternalDependencyDAO |
| `codeinsight/analyzers/__init__.py` | 导出 DependencyParser |
| `codeinsight/analyzers/call_graph.py` | 增强调用图：qualified_name 索引、external/injected 调用类型 |
| `codeinsight/analyzers/module_graph.py` | 增强模块依赖图：Import → 外部依赖映射（种子规则 + 自动匹配） |
| `codeinsight/api/__init__.py` | 注册 dependencies、frameworks、routes 路由 |
| `codeinsight/tasks/analysis_orchestrator.py` | 集成依赖解析到分析流程 |
| `alembic/versions/xxxx_phase5_external_dependencies.py` | 数据库迁移脚本 |

---

## 三、核心功能详解

### 3.1 外部依赖数据模型

**表名**：`external_dependencies`

**核心字段**：
- `ecosystem`：生态系统（maven / npm / pip / go）
- `group_name`：分组名（Maven groupId / NPM scope）
- `artifact_name`：包名
- `version`：精确版本号
- `version_range`：版本范围声明（如 `^18.2.0`、`>=2.28.0`）
- `scope`：作用域（compile / test / dev / provided 等）
- `declaration_file`：依赖声明文件路径
- `used_by_files`：引用该依赖的文件列表（JSONB）

**索引**：
- `(repository_id, ecosystem, artifact_name)` 复合索引
- `(repository_id, group_name, artifact_name)` 复合索引

### 3.2 依赖声明解析器

支持 4 种主流生态系统：

#### Maven (pom.xml)
- 解析 `<dependencies>` 下的 `<dependency>` 节点
- 提取 groupId、artifactId、version、scope
- 支持 XML 命名空间

#### NPM (package.json)
- 解析 `dependencies`、`devDependencies`、`peerDependencies`
- scope 包自动拆分（`@angular/core` → group=`@angular`, artifact=`core`）
- 区分生产依赖（compile）和开发依赖（dev）

#### Pip (requirements.txt)
- 解析 `==`、`>=`、`<=`、`~=`、`<`、`>` 等版本约束
- 自动跳过注释（`#` 开头）和选项行（`-r`、`--index-url` 等）
- 提取版本范围字符串

#### Go (go.mod)
- 解析 `require` 块和单行 `require`
- 完整保留 module 路径作为 artifact_name
- 提取版本号（如 v1.9.0）

### 3.3 调用图增强

#### 三级降级匹配策略
```
Level 1: qualified_name 精确匹配（最高优先级）
  ↓ 未匹配
Level 2: 方法名匹配（降级，带歧义消解）
  ↓ 未匹配
Level 3: 外部依赖匹配（再降级，external 类型）
  ↓ 未匹配
Level 4: 依赖注入检测（injected 类型）
```

#### 新增调用类型
- `external`：调用外部依赖的方法（如 `axios.get()`）
- `injected`：依赖注入调用（如 `@Autowired` 注入的 service 方法调用）

### 3.4 模块依赖图增强

#### Import → 外部依赖映射
**两级匹配策略**：
1. **种子规则匹配**：硬编码常见框架映射（如 `import flask` → `flask` 依赖）
2. **自动匹配**：基于 `external_dependencies` 表的精确匹配和前缀匹配

#### 种子规则覆盖
- **Java**：Spring Boot 全家桶、Hibernate、Jackson、Lombok 等 20+ 常见框架
- **Python**：Flask、Django、FastAPI、Requests、SQLAlchemy 等 20+ 常见库
- **TS/JS**：React、Vue、Angular、Axios、Express 等 20+ 常见框架

### 3.5 API 接口

#### 依赖查询
- `GET /api/repositories/{id}/dependencies`：获取仓库所有依赖
  - 查询参数：`ecosystem`（按生态系统过滤）、`scope`（按作用域过滤）
- `GET /api/repositories/{id}/dependencies/ecosystem/{ecosystem}`：按生态系统查询

#### 框架查询
- `GET /api/repositories/{id}/frameworks`：获取检测到的所有框架模式
  - 查询参数：`category`（按类别过滤）

#### 路由查询
- `GET /api/repositories/{id}/routes`：获取所有 API 路由
  - 查询参数：`framework`（按框架过滤）、`method`（按 HTTP 方法过滤）

### 3.6 分析流程集成

在 `AnalysisOrchestrator` 的 Step 4.5（框架检测 + 路由提取）中新增：
1. 清理旧的外部依赖数据
2. 从 `files` 表中筛选依赖声明文件
3. 使用 `DependencyParser` 解析每个文件
4. 去重后写入 `external_dependencies` 表
5. 后续调用图和模块依赖图构建时自动使用外部依赖数据

---

## 四、测试结果

### 4.1 测试用例统计

| 测试类别 | 用例数 | 通过数 | 失败数 |
|---------|-------|-------|-------|
| DependencyEntry 数据类 | 2 | 2 | 0 |
| NPM package.json 解析 | 4 | 4 | 0 |
| Maven pom.xml 解析 | 2 | 2 | 0 |
| Pip requirements.txt 解析 | 3 | 3 | 0 |
| Go go.mod 解析 | 3 | 3 | 0 |
| 自动识别文件类型 | 2 | 2 | 0 |
| ExternalDependency Schema | 2 | 2 | 0 |
| 调用图 qualified_name 匹配 | 2 | 2 | 0 |
| 调用图外部依赖索引 | 1 | 1 | 0 |
| 模块依赖图外部依赖索引 | 1 | 1 | 0 |
| 种子规则匹配 | 5 | 5 | 0 |
| **合计** | **27** | **27** | **0** |

### 4.2 测试覆盖场景

- ✅ 基础解析功能（4 种生态系统）
- ✅ 边界情况（空文件、无效文件、无依赖）
- ✅ 特殊格式（scope 包、多行 require、注释和选项行）
- ✅ Schema 序列化（camelCase 别名）
- ✅ 调用图索引构建
- ✅ 种子规则匹配（Java/Python/TS/JS）
- ✅ 语言类型判断

---

## 五、设计决策与权衡

### 5.1 种子规则 vs 自动匹配
- **种子规则**：硬编码常见映射，覆盖度高但维护成本大
- **自动匹配**：基于 external_dependencies 表动态匹配，灵活但对 import 名要求高
- **决策**：两者结合，种子规则作为兜底，自动匹配为主力

### 5.2 qualified_name 索引 vs 方法名匹配
- **qualified_name**：精确但需要完整的类/包信息
- **方法名匹配**：宽松但歧义多
- **决策**：三级降级策略，优先精确匹配，必要时降级

### 5.3 依赖解析时机
- **方案 A**：扫描阶段直接扫描文件系统
- **方案 B**：从 files 表中筛选（已扫描文件）
- **决策**：方案 B，复用扫描结果，保持增量分析一致性

---

## 六、扩展性重构（策略模式 + 注册机制）

### 6.1 重构动机

Phase 5 完成后，对 `analyzers/` 目录下全部 7 个文件进行了扩展性评估，发现 **30 个扩展性瓶颈**，核心问题是：

- **违反开闭原则（OCP）**：新增语言/框架/生态系统必须修改已有的 if-elif 分支
- **硬编码配置**：种子规则、注解映射、框架签名等以模块级字典形式硬编码，无法外部扩展
- **单一类承担过多职责**：一个类中混合了多种语言/框架的处理逻辑

### 6.2 重构范围

| 文件 | 重构内容 | 新增架构组件 |
|------|---------|-------------|
| `dependency_parser.py` | if-elif 生态系统分发 → 策略模式 | `EcosystemParser` ABC + 5 个解析器类 + `register()` |
| `route_extractor.py` | if-elif 框架分发 → 策略模式 | `RouteExtractionStrategy` ABC + 4 个策略类 + `register()` |
| `module_graph.py` | 硬编码种子字典 → 注册表 | `SeedRuleRegistry` + `_LANGUAGE_PROFILES` 配置表 |
| `call_graph.py` | if-elif 调用类型匹配 → 策略链 | `CallMatchStrategy` Protocol + 4 个策略类 + `DiAnnotationRegistry` + `CallSeedRuleRegistry` |
| `framework_detector.py` | 硬编码签名字典 → 注册表 | `FrameworkSignatureRegistry` + 3 个签名 dataclass |
| `framework_tagger.py` | if-elif 语言分发 → 策略模式 | `NodeTaggingStrategy` Protocol + 5 个策略类 |
| `middleware_analyzer.py` | 硬编码模式集合 → 注册表 | `MiddlewarePatternRegistry` + `register()` |

### 6.3 核心设计模式

#### 策略模式 + 注册机制（统一范式）

```python
# 1. 定义抽象接口
class EcosystemParser(ABC):
    @abstractmethod
    def parse(self, path: Path) -> list[DependencyEntry]: ...

# 2. 每种生态独立实现
class MavenParser(EcosystemParser):
    def parse(self, path: Path) -> list[DependencyEntry]: ...

# 3. 注册表 + 自动注册
class DependencyParser:
    def __init__(self):
        self._parsers: dict[str, EcosystemParser] = {}
        self._register_builtin_parsers()

    def register(self, ecosystem: str, parser: EcosystemParser):
        self._parsers[ecosystem] = parser

    def parse_file(self, path):
        ecosystem = DEPENDENCY_FILE_PATTERNS.get(path.name)
        parser = self._parsers.get(ecosystem)
        return parser.parse(path) if parser else []
```

#### 调用匹配策略链（Chain of Responsibility）

```python
# call_graph.py — 4 级匹配策略按优先级链式执行
strategies = [
    QualifiedNameMatchStrategy(),  # Level 1: qualified_name 精确匹配
    MethodNameMatchStrategy(),     # Level 2: 方法名匹配（降级）
    ExternalDepMatchStrategy(),    # Level 3: 外部依赖匹配
    InjectedCallMatchStrategy(),   # Level 4: 依赖注入检测
]
for strategy in strategies:
    edge = strategy.match(call_node, ...)
    if edge:
        return edge  # 首个命中即返回
```

### 6.4 扩展示例

新增一个生态系统（如 Composer）只需 2 步，**无需修改任何现有代码**：

```python
# 步骤1：新建解析器类
class ComposerParser(EcosystemParser):
    def parse(self, path: Path) -> list[DependencyEntry]:
        # 解析 composer.json
        ...

# 步骤2：注册
parser = DependencyParser()
parser.register("composer", ComposerParser())
```

新增一个框架路由提取器（如 Django REST）只需 2 步：

```python
class DjangoRouteStrategy(RouteExtractionStrategy):
    async def extract(self, nodes, db, repo_uuid) -> list[RouteInfo]:
        # 从装饰器 @api_view 提取
        ...

extractor = RouteExtractor()
extractor.register(DjangoRouteStrategy())
```

### 6.5 重构验证

| 验证项 | 结果 |
|-------|------|
| Ruff lint（全部 analyzers 文件） | ✅ All checks passed |
| Phase 4 测试（41 个） | ✅ 全部通过 |
| Phase 5 测试（27 个） | ✅ 全部通过 |
| call_graph 测试（14 个） | ✅ 全部通过 |
| module_graph 测试（3 个） | ✅ 全部通过 |
| framework_tagger 测试（7 个） | ✅ 全部通过 |
| middleware_analyzer 测试（10 个） | ✅ 全部通过 |
| **合计** | **94 个测试全部通过** |

### 6.6 重构前后对比

| 维度 | 重构前 | 重构后 |
|------|--------|--------|
| 新增生态系统 | 修改 3 处（字典 + if-elif + 新方法） | 新增 1 个类 + 1 行注册 |
| 新增框架路由 | 修改 build_data + 新增方法 | 新增 1 个策略类 + 1 行注册 |
| 新增种子规则 | 修改硬编码字典 | 调用 `registry.register()` |
| 新增调用匹配级别 | 修改 _match_call_edges | 新增 1 个策略类 + 加入策略链 |
| 新增框架检测 | 修改 3 个签名字典 + 2 个方法 | 调用 `registry.register_*()` |
| 新增语言标签 | 修改 tag_node if-elif | 新增 1 个策略类 + 1 行注册 |

---

## 七、已知限制与后续优化

### 7.1 已知限制
1. **间接依赖未解析**：仅解析直接依赖，不解析传递依赖
2. **版本范围解析简单**：Pip 等的复杂版本约束仅提取字符串，未结构化
3. **种子规则覆盖有限**：仅覆盖常见框架，小众框架需要依赖自动匹配
4. **多模块 Maven 支持有限**：仅解析当前 pom，未处理父 POM 和 module 继承

### 7.2 后续优化方向
1. 支持更多生态系统（Cargo、Composer、NuGet 等）—— 现已可通过注册机制快速扩展
2. 解析传递依赖（如 Maven dependency:tree、npm ls）
3. 版本范围结构化存储（支持版本兼容性分析）
4. 依赖漏洞扫描集成（如 Snyk、OWASP Dependency-Check）
5. 多模块项目的依赖合并
6. 将种子规则外部化为 YAML/JSON 配置文件，支持热加载

---

## 八、数据库迁移

新增表 `external_dependencies`，迁移脚本：
```bash
alembic revision --autogenerate -m "phase5_external_dependencies"
alembic upgrade head
```

---

## 九、总结

Phase 5 成功实现了外部依赖分析与跨模块调用映射能力，将代码分析边界从内部代码扩展到第三方依赖。27 个单元测试全部通过，功能完整覆盖需求文档中的所有要点。

核心价值：
1. **依赖可视化**：清晰展示项目使用的所有第三方依赖
2. **调用精确性**：qualified_name 匹配大幅提升调用图准确率
3. **外部调用识别**：区分内部调用、外部依赖调用和依赖注入调用
4. **框架关联**：Import 与外部依赖建立映射，支持框架级分析
