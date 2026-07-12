# P2-04: 结构提取引擎增强与调用图构建

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-04 |
| 任务名称 | 结构提取引擎增强 + 调用图构建：接口/协议提取 + 模块依赖分析 + 函数调用链 |
| 所属阶段 | Phase 2（第 4-6 周） |
| 优先级 | P0 |
| 预估工时 | 16h（原14h + 2h结构提取增强） |
| 交付物 | CodeStructure数据模型 + CallGraph构建器 + 结构提取规则引擎增强 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P2-01 GitScanner | ✅ | 文件扫描器已实现，提供 `ScanResult` |
| P2-02 Tree-sitter 解析层 | ✅ | 5种语言解析器已实现，提取基础节点（函数/类/方法/调用/导入） |
| P2-03 持久化存储 | ✅ | `ast_nodes` 表已就绪，支持 `node_type`, `name`, `parent_node_id`, `file_id` |
| P1-05 ORM 模型 | ✅ | `AstNodeModel` 已定义，包含 `signature`, `docstring` 字段 |
| P1-07 DAO 层 | ✅ | `AstNodeDAO` 已实现，支持批量创建和查询 |

### 任务背景

P2-02 的 Tree-sitter 封装层已实现**基础结构提取**（函数、类、方法、调用、导入），但缺少：

1. **更丰富的节点类型**：接口（TypeScript `interface`、Java `interface`）、协议（Python `Protocol`）、变量/常量
2. **调用关系分析**：P2-02 只提取了 `call` 节点，但**没有构建调用图**（谁调用了谁、模块间依赖）
3. **高层结构模型**：没有模块结构、文件结构等聚合视图

本任务将 P2-02 的基础提取能力**增强**为完整的结构提取引擎，并构建**调用图**为后续 AI 分析（P3-02）和前端展示（P2-07）提供数据基础。

---

## 二、整体架构位置

P2-04 在 CodeInsight 分析管线中的位置：

```
┌──────────────────────────────────────────────────────────────────────┐
│  run_analysis 完整流程                                                │
│                                                                      │
│  Step 1: _do_analysis_setup()                                        │
│                                                                      │
│  Step 2: GitScanner.scan()  ←── P2-01 ✅                             │
│          → _store_files_to_db()                                       │
│                                                                      │
│  Step 3: ParserFactory 解析  ←── P2-02 ✅                            │
│          → _parse_and_store_ast() ←── P2-03 ✅                       │
│                                                                      │
│  Step 4: 结构提取引擎增强 ←── P2-04 ⬅️ 本任务                         │
│          ┌────────────────────────────────────────────────────┐     │
│          │ 1. 补充节点类型提取（接口/协议/变量）                │     │
│          │ 2. 构建调用图（CallGraph）                          │     │
│          │ 3. 构建模块依赖图（ModuleDependencyGraph）          │     │
│          │ 4. 持久化到 call_edges 表                           │     │
│          └────────────────────────────────────────────────────┘     │
│                                                                      │
│  Step 5: AI 分析  ←── P3 (待接入)                                    │
│                                                                      │
│  Step 6: 完成                                                         │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 数据流向

```
P2-02 AST 节点（ast_nodes 表）
    │
    ├── 节点类型补充
    │   ├── interface 节点（TypeScript interface, Java interface）
    │   ├── protocol 节点（Python Protocol）
    │   ├── variable 节点（常量/全局变量）
    │   └── 持久化到 ast_nodes 表
    │
    ├── 调用图构建
    │   ├── 提取 call 节点 → 解析被调用函数名
    │   ├── 匹配函数定义节点（同名函数）
    │   ├── 构建调用边（caller → callee）
    │   └── 持久化到 call_edges 表
    │
    └── 模块依赖图构建
        ├── 提取 import 节点 → 解析导入模块路径
        ├── 匹配文件路径（import 目标）
        ├── 构建依赖边（importer → imported）
        └── 持久化到 module_dependencies 表
```

### 2.2 关键约束

- **调用匹配策略**：同名函数可能有多个重载（Java/TypeScript），需支持多目标匹配
- **跨文件调用**：`call` 节点可能调用其他文件定义的函数，需要全局索引
- **动态调用**：Python 的 `getattr(obj, name)()` 等动态调用无法静态分析，需标记为 `unknown`
- **增量更新**：调用图随 AST 节点增量更新（P2-06 依赖）

---

## 三、修改模块结构

```
codeinsight-backend/
├── codeinsight/
│   ├── models/
│   │   ├── call_edge.py         # 新增: CallEdgeModel（调用边）
│   │   └── module_dependency.py # 新增: ModuleDependencyModel（模块依赖）
│   ├── repositories/
│   │   ├── call_edge.py         # 新增: CallEdgeDAO
│   │   └── module_dependency.py # 新增: ModuleDependencyDAO
│   ├── schemas/
│   │   ├── call_edge.py         # 新增: CallEdge, CallEdgeCreate
│   │   └── module_dependency.py # 新增: ModuleDependency, ModuleDependencyCreate
│   ├── analyzers/               # 新增: 结构分析模块
│   │   ├── __init__.py
│   │   ├── structure_extractor.py # 结构提取规则引擎增强
│   │   ├── call_graph.py        # 调用图构建器
│   │   └── module_graph.py      # 模块依赖图构建器
│   └── tasks/
│       └── analysis_tasks.py    # 扩展: 集成结构分析到 run_analysis
│
└── tests/
    ├── test_structure_extractor.py # 新增: 结构提取测试
    ├── test_call_graph.py          # 新增: 调用图构建测试
    └── test_module_graph.py        # 新增: 模块依赖图测试
```

---

## 四、核心功能设计

### 4.1 结构提取规则引擎增强（`StructureExtractor`）

在 P2-02 的 `LanguageParser` 基础上，增强节点类型提取规则：

#### 4.1.1 新增节点类型

| 节点类型 | 语言 | Tree-sitter 节点 | 提取逻辑 |
|---------|------|------------------|---------|
| `interface` | TypeScript | `interface_declaration` | 类似 `class_declaration` |
| `interface` | Java | `interface_declaration` | 类似 `class_declaration` |
| `protocol` | Python | `class_definition` + `Protocol` 基类 | 检查继承链 |
| `variable` | 通用 | `variable_declaration`, `const_declaration` | 提取声明的变量 |
| `enum` | TypeScript/Java | `enum_declaration` | 类似 `class_declaration` |
| `type` | TypeScript | `type_alias_declaration` | 类型别名 |

#### 4.1.2 实现方式

在 `StructureExtractor` 中封装节点提取逻辑：

```python
class StructureExtractor:
    """
    结构提取规则引擎
    
    在 LanguageParser 基础上，增强节点类型提取，并支持自定义提取规则。
    """
    
    def __init__(self, parser: LanguageParser):
        self.parser = parser
    
    def extract_structures(self, file_path: Path | str) -> StructureResult:
        """
        提取代码结构
        
        Returns:
            StructureResult 包含 AST 节点和结构摘要
        """
        # 1. 调用 ParserFactory 解析 AST 节点
        ast_nodes = self.parser.parse_file(file_path)
        
        # 2. 增强节点类型（接口、协议、变量等）
        enhanced_nodes = self._enhance_nodes(ast_nodes, file_path)
        
        # 3. 生成结构摘要
        summary = self._generate_summary(enhanced_nodes)
        
        return StructureResult(
            nodes=enhanced_nodes,
            summary=summary,
            file_path=str(file_path),
        )
    
    def _enhance_nodes(self, nodes: ASTNodeList, file_path: str) -> ASTNodeList:
        """增强节点类型提取"""
        # 针对不同语言，补充接口、协议、变量等节点
        ...
```

#### 4.1.3 结构摘要数据模型

```python
@dataclass
class StructureSummary:
    """文件结构摘要"""
    
    file_path: str
    language: str
    functions_count: int
    classes_count: int
    interfaces_count: int
    methods_count: int
    imports_count: int
    calls_count: int
    top_level_nodes: list[str]  # 顶级节点名称列表
```

---

### 4.2 调用图构建器（`CallGraphBuilder`）

#### 4.2.1 数据模型：`CallEdgeModel`

```python
class CallEdgeModel(Base):
    """
    调用边实体
    
    存储函数调用关系：caller（调用者）→ callee（被调用者）
    """
    
    __tablename__ = "call_edges"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    caller_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("ast_nodes.id", ondelete="CASCADE"), nullable=False
    )
    callee_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("ast_nodes.id", ondelete="SET NULL"), nullable=True
    )
    # 调用位置
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_column: Mapped[int] = mapped_column(Integer, nullable=False)
    # 调用信息
    call_name: Mapped[str] = mapped_column(String, nullable=False)  # 被调用的函数名
    call_type: Mapped[str] = mapped_column(String, nullable=False)  # "static" / "dynamic" / "unknown"
    # 索引
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
```

#### 4.2.2 调用匹配策略

```python
class CallGraphBuilder:
    """
    调用图构建器
    
    将 call 节点关联到具体的函数定义节点，构建完整的调用图。
    """
    
    def build(self, repo_uuid: UUID) -> None:
        """
        构建调用图
        
        流程：
        1. 查询仓库所有 ast_nodes（call 类型）
        2. 查询仓库所有 ast_nodes（function/method/constructor 类型）
        3. 构建函数索引（name → node_id）
        4. 遍历 call 节点，匹配被调用函数
        5. 构建调用边并持久化
        """
        # 1. 加载数据
        call_nodes = self._load_call_nodes(repo_uuid)
        function_nodes = self._load_function_nodes(repo_uuid)
        
        # 2. 构建函数索引（支持同名函数重载）
        function_index = self._build_function_index(function_nodes)
        
        # 3. 匹配调用边
        call_edges = self._match_call_edges(call_nodes, function_index, repo_uuid)
        
        # 4. 持久化
        self._store_call_edges(repo_uuid, call_edges)
    
    def _match_call_edges(
        self, 
        call_nodes: list[AstNodeModel], 
        function_index: dict[str, list[uuid.UUID]],
        repo_uuid: UUID
    ) -> list[CallEdge]:
        """
        匹配调用边
        
        匹配策略：
        1. 精确匹配：call_name 完全匹配函数名
        2. 方法调用：*.method 匹配同名方法（需要作用域分析）
        3. 构造器调用：new Class() 匹配 constructor 节点
        4. 动态调用：getattr/反射等标记为 "dynamic"，不匹配
        5. 未知调用：无法匹配，标记为 "unknown"，callee_node_id = None
        """
        ...
```

#### 4.2.3 调用图查询接口

```python
class CallGraphQuery:
    """调用图查询接口"""
    
    async def get_callers(self, node_id: UUID) -> list[CallEdge]:
        """获取调用该函数的所有调用者（反向调用图）"""
        ...
    
    async def get_callees(self, node_id: UUID) -> list[CallEdge]:
        """获取该函数调用的所有被调用者（正向调用图）"""
        ...
    
    async def get_call_chain(self, node_id: UUID, max_depth: int = 10) -> list[CallEdge]:
        """获取从该函数开始的完整调用链（DFS 遍历）"""
        ...
    
    async def get_callers_chain(self, node_id: UUID, max_depth: int = 10) -> list[CallEdge]:
        """获取调用该函数的完整调用链（反向 DFS 遍历）"""
        ...
```

---

### 4.3 模块依赖图构建器（`ModuleDependencyBuilder`）

#### 4.3.1 数据模型：`ModuleDependencyModel`

```python
class ModuleDependencyModel(Base):
    """
    模块依赖实体
    
    存储模块间依赖关系：importer（导入者）→ imported（被导入者）
    """
    
    __tablename__ = "module_dependencies"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    importer_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    imported_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    # 导入信息
    import_name: Mapped[str] = mapped_column(String, nullable=False)  # 导入的模块名
    import_type: Mapped[str] = mapped_column(String, nullable=False)  # "relative" / "absolute" / "external"
    # 索引
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
```

#### 4.3.2 依赖匹配策略

```python
class ModuleDependencyBuilder:
    """
    模块依赖图构建器
    
    将 import 节点关联到具体的文件，构建模块依赖图。
    """
    
    def build(self, repo_uuid: UUID) -> None:
        """
        构建模块依赖图
        
        流程：
        1. 查询仓库所有 ast_nodes（import 类型）
        2. 查询仓库所有 files 表
        3. 构建文件索引（file_path → file_id）
        4. 遍历 import 节点，解析导入路径
        5. 匹配导入目标文件
        6. 构建依赖边并持久化
        """
        ...
```

---

## 五、集成到 `run_analysis`

在 `analysis_tasks.py` 的 `run_analysis` 任务中，Step 3（AST 解析）之后增加 Step 4（结构分析）：

```python
# Step 3: AST 解析并存储 ←── P2-02/P2-03 ✅
asyncio.run(_parse_and_store_ast(repo_uuid, scan_result))

# Step 4: 结构分析（调用图 + 模块依赖）←── P2-04 ⬅️ 本任务
_update_progress(self, TaskStatus.ANALYZING_STRUCTURES, 40.0, total_files, total_files)
if task_id:
    _check_cancelled(self, task_id)

# 更新分析版本状态
asyncio.run(
    _update_analysis_version(
        version_id,
        TaskStatus.ANALYZING_STRUCTURES,
    )
)

# 构建调用图
asyncio.run(_build_call_graph(repo_uuid))

# 构建模块依赖图
asyncio.run(_build_module_dependencies(repo_uuid))
```

### 5.1 新增状态：`ANALYZING_STRUCTURES`

在 `TaskStatus` 枚举中新增：

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    PARSING = "parsing"
    ANALYZING_STRUCTURES = "analyzing_structures"  # 新增
    ANALYZING_MODULES = "analyzing_modules"
    STORING = "storing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
```

---

## 六、数据库 Migration

需要新增两个数据表：

```sql
-- call_edges 表
CREATE TABLE call_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    caller_node_id UUID NOT NULL REFERENCES ast_nodes(id) ON DELETE CASCADE,
    callee_node_id UUID REFERENCES ast_nodes(id) ON DELETE SET NULL,
    start_line INTEGER NOT NULL,
    start_column INTEGER NOT NULL,
    call_name VARCHAR(255) NOT NULL,
    call_type VARCHAR(50) NOT NULL DEFAULT 'static',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_call_edge UNIQUE (caller_node_id, start_line, start_column)
);

-- module_dependencies 表
CREATE TABLE module_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    importer_file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    imported_file_id UUID REFERENCES files(id) ON DELETE SET NULL,
    import_name VARCHAR(255) NOT NULL,
    import_type VARCHAR(50) NOT NULL DEFAULT 'absolute',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_dependency UNIQUE (importer_file_id, import_name)
);
```

---

## 七、测试覆盖

### 7.1 test_structure_extractor.py（预计 15 个测试用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_extract_interface_typescript` | TypeScript interface 提取 |
| `test_extract_interface_java` | Java interface 提取 |
| `test_extract_protocol_python` | Python Protocol 提取 |
| `test_extract_variable` | 变量/常量提取 |
| `test_extract_enum` | 枚举提取 |
| `test_generate_summary` | 结构摘要生成 |

### 7.2 test_call_graph.py（预计 20 个测试用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_build_call_graph_simple` | 简单函数调用匹配 |
| `test_build_call_graph_method` | 方法调用匹配 |
| `test_build_call_graph_constructor` | 构造器调用匹配 |
| `test_build_call_graph_dynamic` | 动态调用标记为 "dynamic" |
| `test_build_call_graph_unknown` | 未知调用标记为 "unknown" |
| `test_build_call_graph_overload` | 函数重载（同名多目标） |
| `test_get_callers` | 查询调用者（反向） |
| `test_get_callees` | 查询被调用者（正向） |
| `test_get_call_chain` | 获取调用链（DFS） |
| `test_get_callers_chain` | 获取调用者链（反向 DFS） |

### 7.3 test_module_graph.py（预计 12 个测试用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_build_dependency_absolute` | 绝对路径导入匹配 |
| `test_build_dependency_relative` | 相对路径导入匹配 |
| `test_build_dependency_external` | 外部库导入标记为 "external" |
| `test_build_dependency_unmatched` | 未匹配导入标记为 None |
| `test_get_dependencies` | 查询文件依赖 |
| `test_get_dependents` | 查询被依赖文件 |

---

## 八、设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **调用匹配粒度** | 函数级（function/method/constructor） | 细粒度，支持方法重载 |
| **动态调用处理** | 标记为 `dynamic`，不匹配目标 | 静态分析无法确定，避免误匹配 |
| **未知调用处理** | 标记为 `unknown`，`callee_node_id = None` | 保留调用记录，不阻塞图构建 |
| **函数索引策略** | `name → [node_id]` 支持重载 | Java/TypeScript 支持同名重载 |
| **作用域分析** | 暂不实现（P3 扩展） | 简单匹配已覆盖大部分场景 |
| **增量更新** | 全量重建（P2-06 优化） | 当前阶段简单可靠，后续优化 |
| **循环依赖检测** | 暂不实现（P3 扩展） | 基础图构建先完成 |
| **ModuleDependency 索引** | `importer_file_id + import_name` 唯一约束 | 避免重复依赖边 |

---

## 九、与 Phase 2 其他任务的关系

| 任务 | 状态 | 与 P2-04 的关系 |
|------|------|----------------|
| P2-01 GitScanner | ✅ 已完成 | P2-04 使用 `files` 表进行模块依赖匹配 |
| P2-02 Tree-sitter 解析 | ✅ 已完成 | P2-04 增强 P2-02 的节点类型提取，并消费 `call`/`import` 节点 |
| P2-03 持久化存储 | ✅ 已完成 | P2-04 依赖 `ast_nodes` 表，新增 `call_edges` 和 `module_dependencies` 表 |
| P2-05 结构数据入库管道 | ⬜ 待实现 | P2-04 的调用图和模块依赖是 P2-05 的核心数据源 |
| P2-06 增量扫描 | ⬜ 待实现 | P2-04 的调用图和模块依赖需要增量更新 |
| P2-07 解析结果前端预览 | ⬜ 待实现 | P2-07 使用 P2-04 的调用图和模块依赖进行可视化 |

---

## 十、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 作用域分析 | P3 | 精确匹配方法调用（需要类型推导） |
| 循环依赖检测 | P3 | 调用图和模块依赖的环路检测 |
| 调用复杂度计算 | P3 | 基于调用图的圈复杂度、深度分析 |
| 前端调用图可视化 | P4 | D3.js / React Flow 渲染调用图和依赖图 |
| 增量调用图更新 | P2-06 | 基于 `content_hash` 增量更新调用图 |

---

## 十一、文件变更明细

### 新增文件

| 文件 | 说明 |
|------|------|
| `codeinsight/models/call_edge.py` | CallEdgeModel ORM 模型 |
| `codeinsight/models/module_dependency.py` | ModuleDependencyModel ORM 模型 |
| `codeinsight/repositories/call_edge.py` | CallEdgeDAO 数据访问对象 |
| `codeinsight/repositories/module_dependency.py` | ModuleDependencyDAO 数据访问对象 |
| `codeinsight/schemas/call_edge.py` | CallEdge, CallEdgeCreate Pydantic Schema |
| `codeinsight/schemas/module_dependency.py` | ModuleDependency, ModuleDependencyCreate Pydantic Schema |
| `codeinsight/analyzers/__init__.py` | 结构分析模块导出 |
| `codeinsight/analyzers/structure_extractor.py` | 结构提取规则引擎增强 |
| `codeinsight/analyzers/call_graph.py` | 调用图构建器 + 查询接口 |
| `codeinsight/analyzers/module_graph.py` | 模块依赖图构建器 |
| `tests/test_structure_extractor.py` | 结构提取测试 |
| `tests/test_call_graph.py` | 调用图构建测试 |
| `tests/test_module_graph.py` | 模块依赖图测试 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `codeinsight/schemas/analysis.py` | 新增 `TaskStatus.ANALYZING_STRUCTURES` |
| `codeinsight/tasks/analysis_tasks.py` | 集成结构分析到 `run_analysis`（Step 4） |
| `codeinsight/models/__init__.py` | 导出 `CallEdgeModel`, `ModuleDependencyModel` |
| `codeinsight/repositories/__init__.py` | 导出 `CallEdgeDAO`, `ModuleDependencyDAO` |
| `codeinsight/schemas/__init__.py` | 导出 `CallEdge`, `ModuleDependency` 相关 Schema |

---

## 十二、任务完成状态

- [ ] 设计 CallEdgeModel 和 ModuleDependencyModel 数据模型
- [ ] 实现 CallEdgeDAO 和 ModuleDependencyDAO 数据访问对象
- [ ] 实现 CallEdge 和 ModuleDependency Pydantic Schema
- [ ] 实现 StructureExtractor 结构提取规则引擎增强
- [ ] 实现 CallGraphBuilder 调用图构建器
- [ ] 实现 CallGraphQuery 调用图查询接口
- [ ] 实现 ModuleDependencyBuilder 模块依赖图构建器
- [ ] 创建 Alembic Migration（call_edges, module_dependencies 表）
- [ ] 集成结构分析到 run_analysis（Step 4）
- [ ] 新增 TaskStatus.ANALYZING_STRUCTURES 状态
- [ ] 编写结构提取测试（15 个用例）
- [ ] 编写调用图构建测试（20 个用例）
- [ ] 编写模块依赖图测试（12 个用例）
- [ ] 全部测试通过

---

## 总结

P2-04 将 P2-02 的基础结构提取能力**增强**为完整的结构提取引擎（接口、协议、变量等节点类型），并构建**调用图**和**模块依赖图**，为后续 AI 分析（P3-02）提供调用关系数据，为前端可视化（P2-07/P4）提供图数据基础。

核心交付物：
1. **结构提取规则引擎增强**：补充接口、协议、变量等节点类型
2. **调用图构建器**：将 `call` 节点关联到函数定义，构建完整调用图
3. **模块依赖图构建器**：将 `import` 节点关联到文件，构建模块依赖图
4. **调用图和依赖图查询接口**：支持正向/反向查询和调用链遍历
5. **数据库 Migration**：新增 `call_edges` 和 `module_dependencies` 表

---

**开发日期**: 2026-07-12  
**开发人员**: Trae AI  
**任务编号**: P2-04  
**状态**: ⬜ 待实现
