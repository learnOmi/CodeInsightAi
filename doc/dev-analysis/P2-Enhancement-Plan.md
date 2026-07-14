# 代码分析增强方案 — 框架感知与依赖深度分析

## 1. 背景与目标

### 1.1 现状

当前系统具备基础的 AST 解析能力，覆盖 5 种语言（TypeScript、JavaScript、Java、Go、Python），可提取以下节点类型：

| 节点类型 | 说明 | 来源 |
|---------|------|------|
| `function` | 顶层函数/箭头函数 | TS/JS/Go/Python |
| `class` | 类定义 | 全部 |
| `method` | 类/接口方法 | TS/JS/Java/Go/Python |
| `constructor` | 构造函数 | TS/JS/Java |
| `interface` | 接口定义 | TS/Java/Go |
| `call` | 函数/方法调用 | 全部 |
| `import` | 导入语句 | 全部 |
| `type_alias` | 类型别名 | TS only |

### 1.2 现存问题

1. **缺少框架感知**：AST 节点无框架标签，无法区分 Vue 组件、React 组件、Spring Service 等
2. **对象字面量方法未提取**：Vue Options API 的 `mounted`、`methods`、`computed` 被忽略
3. **注解/装饰器未提取**：Java 的 `@Service`、Python 的 `@app.route`、TS 的 `@Component` 丢失
4. **Vue SFC 不解析**：`.vue` 文件只能解析 `<script>` 部分，`<template>` 和 `<style>` 被忽略
5. **外部依赖未追踪**：`package.json`、`pom.xml`、`requirements.txt` 未解析
6. **调用图仅按名称匹配**：不区分 `obj.method()` 中 `obj` 的类型，跨类同名方法均匹配
7. **缺少 API 路由/中间件分析**：无法提取 HTTP 端点、中间件链、拦截器链

### 1.3 目标

构建「框架感知」的代码分析系统，能够：
- 自动识别项目使用的框架和技术栈
- 标记代码节点的框架角色（组件、服务、路由、中间件等）
- 提取 API 路由、中间件链、依赖注入关系
- 解析外部依赖声明，追踪框架库使用情况
- 支持前端三大框架（React/Vue/Angular）和后端主流框架（Spring/Express/Koa/Flask/FastAPI）

---

## 2. 数据库变更

### 2.1 ast_nodes 表新增字段

```sql
-- 框架标签：JSON 数组，如 ["react-component", "react-hook"]
ALTER TABLE ast_nodes ADD COLUMN tags JSONB NOT NULL DEFAULT '[]';

-- 注解/装饰器：JSON 数组，如 [{"name":"@Service","args":[]}]
ALTER TABLE ast_nodes ADD COLUMN annotations JSONB NOT NULL DEFAULT '[]';

-- 所属模块限定名：如 "com.example.service.LogProducer.sendOperateLog"
ALTER TABLE ast_nodes ADD COLUMN qualified_name VARCHAR(1024);

-- 为调用图 qualified_name 匹配创建索引
CREATE INDEX idx_ast_nodes_qualified_name ON ast_nodes(repository_id, qualified_name);
```

**设计理由**：
- `tags` 用 JSONB 而非关系表：标签数量少（通常 1-3 个），查询模式简单（`tags @> '["react-component"]'`），JSONB 减少 JOIN 开销
- `annotations` 用 JSONB：各语言注解结构差异大，JSONB 灵活度高
- `qualified_name`：为调用图「按类型匹配」提供基础，替代纯名称匹配
- `qualified_name` 索引：调用图查询按 qualified_name 匹配是高频操作，关联 `repository_id` 做复合索引可避免全表扫描

### 2.2 新增表：external_dependencies

```sql
CREATE TABLE external_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    analysis_version_id UUID REFERENCES analysis_versions(id) ON DELETE CASCADE,
    ecosystem VARCHAR(32) NOT NULL,        -- maven, npm, pip, go, cargo
    group_name VARCHAR(256),               -- Maven groupId / npm scope
    artifact_name VARCHAR(256) NOT NULL,   -- Maven artifactId / npm package / pip package
    version VARCHAR(64),                   -- 语义化版本（精确版本号，从 lock 文件获取）
    version_range VARCHAR(64),             -- 版本范围声明（如 ^3.0.0，从 package.json 获取）
    scope VARCHAR(32) DEFAULT 'compile',   -- compile, test, dev, runtime, peer
    declaration_file VARCHAR(1024),        -- pom.xml / package.json 路径
    used_by_files JSONB DEFAULT '[]',      -- 引用了该依赖的文件列表
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_external_deps_repo ON external_dependencies(repository_id);
CREATE INDEX idx_external_deps_version ON external_dependencies(analysis_version_id);
CREATE INDEX idx_external_deps_ecosystem ON external_dependencies(repository_id, ecosystem);
```

### 2.3 新增表：api_routes

```sql
CREATE TABLE api_routes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    analysis_version_id UUID REFERENCES analysis_versions(id) ON DELETE CASCADE,
    ast_node_id UUID REFERENCES ast_nodes(id) ON DELETE SET NULL,
    http_method VARCHAR(8) NOT NULL,       -- GET, POST, PUT, DELETE, PATCH, etc.
    path_pattern VARCHAR(1024) NOT NULL,   -- /api/users/{id}
    handler_function VARCHAR(256) NOT NULL,
    handler_file VARCHAR(1024) NOT NULL,
    middlewares JSONB DEFAULT '[]',        -- 中间件/拦截器链
    framework VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_api_routes_repo ON api_routes(repository_id);
CREATE INDEX idx_api_routes_version ON api_routes(analysis_version_id);
CREATE INDEX idx_api_routes_method_path ON api_routes(repository_id, http_method, path_pattern);
```

### 2.4 新增表：framework_patterns（仓库级框架检测结果）

```sql
CREATE TABLE framework_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    analysis_version_id UUID REFERENCES analysis_versions(id) ON DELETE CASCADE,
    framework VARCHAR(32) NOT NULL,        -- spring_boot, react, vue, express, flask, etc.
    category VARCHAR(32) NOT NULL,         -- frontend, backend, database, messaging, etc.
    confidence FLOAT NOT NULL DEFAULT 0.0,  -- 检测置信度 0.0-1.0
    evidence JSONB DEFAULT '{}',           -- 检测依据（文件路径、配置项、版本号等）
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_framework_patterns_repo ON framework_patterns(repository_id);
CREATE INDEX idx_framework_patterns_version ON framework_patterns(analysis_version_id);
CREATE UNIQUE INDEX idx_framework_patterns_repo_fw_ver ON framework_patterns(repository_id, framework, analysis_version_id);
```

**设计说明**：
- `analysis_version_id`：关联分析版本，每次分析独立记录框架检测结果，避免版本间覆盖
- `evidence` JSONB 中存储框架版本号（如 `{"version": "3.4.0"}`），用于后续区分 Vue 2/3 等版本差异
- UNIQUE 约束改为 `(repository_id, framework, analysis_version_id)` 三元组，同一版本内同一框架不重复

---

## 3. Parser 增强

### 3.1 ASTNode 数据类扩展

```python
@dataclass
class ASTNode:
    node_type: str
    name: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    children: list[ASTNode] = field(default_factory=list)
    parent: ASTNode | None = None
    language: str = ""
    file_path: str = ""
    # 新增字段
    tags: list[str] = field(default_factory=list)           # 框架标签
    annotations: list[dict] = field(default_factory=list)   # 注解/装饰器
    qualified_name: str = ""                                # 模块限定名
```

### 3.2 通用增强（所有 Parser）

#### 3.2.1 对象字面量方法提取

新增 `node_type = "object_method"`，从 `object` / `object_literal` 中提取方法定义。

```python
# 在各 parser 的 _extract_nodes 中新增
elif node_type == "object":
    for child in node.children:
        if child.type == "pair":
            # 提取 key: value，其中 value 是 function/arrow_function
            key_node = child.child_by_field_name("key")
            if key_node and self._is_function_node(child.child_by_field_name("value")):
                method_node = self._create_object_method_node(child, ...)
                result.add(method_node)
```

**parent 关系处理**：
- 顶层对象的 `object_method`：`parent` 指向文件级根节点
- 嵌套对象（如 `methods: { foo() {}, bar() {} }`）：`parent` 指向外层 `object_method` 节点，形成树形结构

**覆盖场景**：
- Vue Options API: `{ mounted() {}, methods: { foo() {} }, computed: { bar() {} } }`
- React: `{ componentDidMount() {} }`（类组件）
- 配置对象: `{ onSuccess() {}, onError() {} }`
- Express 路由: `router.get('/path', handler)`

#### 3.2.2 注解/装饰器提取

对各语言统一提取注解/装饰器：

| 语言 | 节点类型 | 示例 |
|------|---------|------|
| Java | `annotation` | `@Service`, `@Autowired`, `@RequestMapping` |
| Python | `decorator` | `@app.route("/")`, `@lru_cache` |
| TS/JS | `decorator` | `@Component`, `@Injectable` |

```python
# 在 _create_*_node 方法中统一提取
def _extract_annotations(self, node) -> list[dict]:
    """从修饰符中提取注解/装饰器"""
    annotations = []
    for child in node.children:
        if child.type in ("annotation", "decorator"):
            # 提取注解名和参数
            name_node = child.child_by_field_name("name")
            args_node = child.child_by_field_name("arguments")
            annotations.append({
                "name": _node_text_to_str(name_node) if name_node else "",
                "args": _extract_annotation_args(args_node) if args_node else [],
            })
    return annotations
```

### 3.3 语言特定增强

#### 3.3.1 TypeScript / JavaScript Parser

| 增强点 | 说明 | 优先级 |
|--------|------|--------|
| JSX/TSX 支持 | 启用 `tree-sitter-tsx`，解析 JSX 元素 | P0 |
| 装饰器提取 | `@Component`, `@NgModule`, `@Injectable` | P0 |
| 对象方法提取 | 覆盖 Vue Options API 和配置对象 | P0 |
| 变量声明函数命名 | 已实现（arrow_function 命名） | 已完成 |
| React 组件检测 | 大写函数名 + JSX 返回 | P1 |
| React Hooks 检测 | `use[A-Z]` 命名模式 | P1 |
| Vue Composition API | `setup()`, `defineComponent()` | P1 |

**JSX/TSX 解析**：
```python
# 使用 tree-sitter-tsx 替代 tree-sitter-typescript
try:
    from tree_sitter_tsx import language as tsx_language
    self._language = Language(tsx_language())
except ImportError:
    from tree_sitter_typescript import language_typescript as ts_language
    self._language = Language(ts_language())
```

JSX 节点提取为 `node_type = "jsx_element"`，用于组件结构分析。

#### 3.3.2 Vue SFC Parser（新增）

新建 `vue_parser.py`，处理 `.vue` 单文件组件：

```
.vue 文件结构:
├── <template>   → HTML 解析（tree-sitter-html）
│   ├── 组件嵌套结构
│   ├── v-if/v-for 指令
│   └── 事件绑定 @click="handler"
├── <script>     → TS/JS 解析（复用现有 parser）
│   ├── Options API: data, methods, computed, watch
│   ├── Composition API: setup(), ref(), reactive()
│   └── <script setup>（Vue 3 语法糖，优先级最高）
└── <style>      → 暂不解析
```

**`<script setup>` 处理**（Vue 3 主流写法）：
- 提取 `defineProps()` / `defineEmits()` / `defineExpose()` 调用，标记为 `vue-component-api`
- `ref()` / `reactive()` / `computed()` / `watch()` 调用标记为 `vue-composable`
- 顶层 `await` 表达式标记为 `vue-async-setup`

```python
class VueSfcParser:
    def parse(self, file_path: Path) -> ASTNodeList:
        content = file_path.read_text()
        # 提取各区块（支持 <script setup> 和普通 <script>）
        script_blocks = self._extract_script_blocks(content)
        template_content = self._extract_block(content, "template")
        
        nodes = ASTNodeList()
        # 优先处理 <script setup>，再处理普通 <script>
        for block_type, script_content in script_blocks:
            ts_parser = TypeScriptParser()
            block_nodes = ts_parser.parse_content(script_content)
            if block_type == "script_setup":
                self._tag_setup_nodes(block_nodes)  # 标记 defineProps/defineEmits 等
            nodes.extend(block_nodes)
        
        # 解析 template 结构
        if template_content:
            nodes.extend(self._parse_template(template_content))
        
        return nodes
    
    def _extract_script_blocks(self, content: str) -> list[tuple[str, str]]:
        """提取所有 <script> 区块，区分 setup 和普通"""
        blocks = []
        # 匹配 <script setup> 和 <script>（不含 setup）
        for match in re.finditer(r'<script\b([^>]*)>(.*?)</script>', content, re.DOTALL):
            attrs = match.group(1)
            body = match.group(2)
            block_type = "script_setup" if "setup" in attrs else "script"
            blocks.append((block_type, body.strip()))
        return blocks
```

#### 3.3.3 Java Parser

| 增强点 | 说明 | 优先级 |
|--------|------|--------|
| 注解提取 | `@Service`, `@Component`, `@Autowired` 等 | P0 |
| Spring 框架检测 | 基于注解识别框架角色 | P0 |
| 方法限定名 | `com.example.Service.method()` | P0 |
| 构造器注入检测 | `@Autowired` 构造函数 | P1 |
| JPA 实体检测 | `@Entity`, `@Table` | P2 |
| 异常处理链 | `@ControllerAdvice`, `@ExceptionHandler` | P2 |

**Spring 注解映射**：

| 注解 | 框架标签 | 角色说明 |
|------|---------|---------|
| `@SpringBootApplication` | `spring-boot-app` | 应用入口 |
| `@RestController` / `@Controller` | `http-controller` | HTTP 控制器 |
| `@Service` | `business-service` | 业务服务 |
| `@Repository` | `data-repository` | 数据访问层 |
| `@Component` | `spring-component` | 通用组件 |
| `@Configuration` | `spring-config` | 配置类 |
| `@Bean` | `spring-bean` | Bean 定义 |
| `@Autowired` / `@Inject` | `dependency-injection` | 依赖注入 |
| `@RequestMapping` / `@GetMapping` / `@PostMapping` | `api-endpoint` | API 端点 |
| `@Aspect` | `spring-aspect` | AOP 切面 |
| `@Transactional` | `transactional` | 事务管理 |
| `@Scheduled` | `scheduled-task` | 定时任务 |

#### 3.3.4 Python Parser

| 增强点 | 说明 | 优先级 |
|--------|------|--------|
| 装饰器提取 | `@app.route`, `@lru_cache`, `@staticmethod` | P0 |
| Flask 路由检测 | `@app.route("/path", methods=["GET"])` | P0 |
| FastAPI 路由检测 | `@app.get("/path")`, `@router.post("/path")` | P0 |
| Django 视图检测 | 函数视图 + URL 配置 | P2 |
| Celery 任务检测 | `@celery.task`, `@shared_task` | P2 |

**Python 装饰器映射**：

| 装饰器 | 框架标签 | 角色说明 |
|--------|---------|---------|
| `@app.route` / `@bp.route` | `flask-route` | Flask 路由 |
| `@app.get` / `@router.post` | `fastapi-route` | FastAPI 路由 |
| `@celery.task` / `@shared_task` | `celery-task` | 异步任务 |
| `@lru_cache` / `@cache` | `cached-function` | 缓存函数 |
| `@staticmethod` / `@classmethod` | `static-method` | 静态/类方法 |
| `@property` | `property` | 属性访问器 |
| `@contextmanager` | `context-manager` | 上下文管理器 |

#### 3.3.5 Go Parser

| 增强点 | 说明 | 优先级 |
|--------|------|--------|
| 结构体方法标签 | `func (s *Server) Handle()` 提取接收者 | P0 |
| Gin/Echo 路由检测 | 路由注册模式 | P1 |
| 接口实现检测 | `var _ Interface = (*Impl)(nil)` | P2 |
| go.mod 依赖解析 | 提取外部依赖 | P1 |

### 3.4 qualified_name 计算规范

各语言 `qualified_name` 格式统一为 `{模块路径}:{类名}.{方法名}`，用于调用图精确匹配。

| 语言 | 格式 | 示例 |
|------|------|------|
| Java | `{package}.{Class}.{method}` | `com.example.service.LogProducer.sendOperateLog` |
| TypeScript/JS | `{relative_path}:{Class}.{method}` | `src/components/Button.tsx:Button.handleClick` |
| Python | `{module}.{Class}.{method}` | `myapp.views:home` |
| Go | `{package_path}:{Type}.{Method}` | `github.com/gin-gonic/gin:Context.JSON` |

**计算规则**：
- **class/method**：从所属包/模块路径 + 类名 + 方法名拼接
- **function**：仅包含模块路径 + 函数名（无类名）
- **object_method**：使用对象所在上下文 + 方法名
- **import**：不计算 qualified_name（import 节点不参与调用图匹配）

---

## 4. 框架检测引擎

### 4.1 架构

```
┌─────────────────────────────────────────────────────────┐
│                    FrameworkDetector                     │
├─────────────────────────────────────────────────────────┤
│  detect(repository_id) → list[FrameworkPattern]         │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 文件级检测    │  │ AST级检测     │  │ 依赖级检测    │  │
│  │ (file names, │  │ (annotations,│  │ (pom.xml,    │  │
│  │  dir structure│  │  decorators) │  │  package.json)│  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 4.2 检测策略

#### 文件级检测（最快，零解析成本）

```python
FRAMEWORK_FILE_SIGNATURES = {
    "spring_boot": {
        "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "content_patterns": ["spring-boot-starter", "org.springframework.boot"],
    },
    "react": {
        "files": ["package.json"],
        "content_patterns": ['"react":', '"react-dom":'],
    },
    "vue": {
        "files": ["package.json"],
        "content_patterns": ['"vue":'],
    },
    "flask": {
        "files": ["requirements.txt", "Pipfile", "pyproject.toml"],
        "content_patterns": ["flask", "Flask"],
    },
    "express": {
        "files": ["package.json"],
        "content_patterns": ['"express":'],
    },
    "gin": {
        "files": ["go.mod"],
        "content_patterns": ["gin-gonic/gin"],
    },
    # ... 可扩展
}
```

#### AST 级检测（精确，解析后执行）

遍历 AST 节点，根据注解/装饰器/命名模式打标签：

```python
class FrameworkTagger:
    """对 AST 节点打框架标签"""
    
    def tag_java(self, node: ASTNode) -> list[str]:
        tags = []
        for annotation in node.annotations:
            name = annotation["name"]
            if name == "@RestController" or name == "@Controller":
                tags.append("http-controller")
            elif name == "@Service":
                tags.append("business-service")
            # ...
        return tags
    
    def tag_typescript(self, node: ASTNode) -> list[str]:
        tags = []
        # React 组件：函数名首字母大写 + 包含 JSX
        if node.node_type == "function" and len(node.name) > 0 and node.name[0].isupper():
            if self._has_jsx_return(node):
                tags.append("react-component")
        # React Hook：use[A-Z] 开头（需确保 name 长度 >= 3）
        if len(node.name) >= 3 and node.name.startswith("use") and node.name[2].isupper():
            tags.append("react-hook")
        return tags
```

#### 依赖级检测

解析依赖声明文件，识别框架依赖：

| 语言 | 文件 | 解析方式 |
|------|------|---------|
| Java | `pom.xml` | XML 解析 |
| Java | `build.gradle` | Groovy/文本解析 |
| Node.js | `package.json` | JSON 解析 |
| Python | `requirements.txt` | 行解析 |
| Python | `pyproject.toml` | TOML 解析 |
| Go | `go.mod` | 行解析 |

### 4.3 检测流程

```
1. 文件扫描阶段（在 Orchestrator 扫描文件后、AST 解析前调用）
   ├── 扫描仓库文件列表
   ├── 匹配 FRAMEWORK_FILE_SIGNATURES
   ├── 解析依赖声明文件提取框架版本号
   └── 输出初步框架候选列表（含版本信息）

2. AST 解析阶段（在 Orchestrator AST 解析完成后调用）
   ├── 解析所有源文件
   ├── 提取注解/装饰器
   ├── 对节点打框架标签
   └── 更新框架候选置信度

3. 依赖解析阶段（与外部依赖分析并行）
   ├── 解析依赖声明文件
   ├── 写入 external_dependencies 表
   └── 确认框架版本

4. 汇总阶段
   ├── 综合三种检测结果
   ├── 计算置信度（文件级权重 0.3，AST 级 0.4，依赖级 0.3）
   ├── 提取框架版本号存入 evidence JSONB
   └── 写入 framework_patterns 表
```

**Orchestrator 集成点**：

```python
# 在 AnalysisOrchestrator._run_async() 中：
async def _run_async(self):
    # 1. 扫描文件
    files = await self._scan_files()
    
    # 2. 框架检测（文件级）— 在 AST 解析前
    detector = FrameworkDetector(self.repo_uuid)
    fw_candidates = await detector.detect_file_level(files)
    
    # 3. AST 解析
    await self._parse_ast(files)
    
    # 4. 框架检测（AST 级 + 依赖级）— 在 AST 解析后
    await detector.detect_ast_level(fw_candidates)
    await detector.detect_dependency_level(fw_candidates)
    
    # 5. 汇总入库
    await detector.finalize(fw_candidates)
    
    # 6. 后续分析...
```

**置信度计算**：
- 文件级命中（如 pom.xml 含 spring-boot-starter）：+0.3
- AST 级命中（如检测到 @SpringBootApplication 注解）：+0.4
- 依赖级命中（如 pom.xml 声明 spring-boot-starter-web 依赖）：+0.3
- 最终 `confidence >= 0.5` 视为确认检测

---

## 5. 外部依赖分析

### 5.1 依赖声明解析

```python
class DependencyParser:
    """解析各语言的依赖声明文件"""
    
    async def parse_maven(self, pom_path: Path) -> list[DependencyEntry]:
        """解析 pom.xml"""
        tree = ET.parse(pom_path)
        deps = []
        for dep in tree.findall(".//dependency"):
            deps.append(DependencyEntry(
                group=dep.findtext("groupId"),
                artifact=dep.findtext("artifactId"),
                version=dep.findtext("version"),
                scope=dep.findtext("scope", "compile"),
            ))
        return deps
    
    async def parse_npm(self, package_json_path: Path) -> list[DependencyEntry]:
        """解析 package.json"""
        data = json.loads(package_json_path.read_text())
        deps = []
        for dep_type in ["dependencies", "devDependencies", "peerDependencies"]:
            for name, version in data.get(dep_type, {}).items():
                scope = {
                    "dependencies": "compile",
                    "devDependencies": "dev",
                    "peerDependencies": "peer",
                }.get(dep_type, "compile")
                deps.append(DependencyEntry(
                    artifact=name,
                    version_range=version,  # package.json 中的版本范围（如 ^3.0.0）
                    scope=scope,
                ))
        return deps
    
    async def parse_npm_lock(self, lock_path: Path) -> dict[str, str]:
        """解析 package-lock.json，获取精确版本号（可选增强）"""
        data = json.loads(lock_path.read_text())
        versions = {}
        for name, pkg in data.get("packages", {}).items():
            if name == "":
                continue
            versions[name.lstrip("node_modules/")] = pkg.get("version", "unknown")
        return versions
```

### 5.2 Import → 外部依赖映射

在现有 `module_dependency` 分析基础上，增加 import 到外部依赖的映射。采用**种子规则 + 自动匹配**两级策略：

#### 5.2.1 种子规则（硬编码映射，覆盖常见框架）

```python
# 示例：Java import → Maven 依赖
IMPORT_TO_DEPENDENCY_RULES = {
    # Spring
    "org.springframework.web.bind.annotation": ("spring-boot-starter-web", "maven"),
    "org.springframework.stereotype.Service": ("spring-boot-starter", "maven"),
    # JPA
    "jakarta.persistence": ("spring-boot-starter-data-jpa", "maven"),
    # Lombok
    "lombok": ("lombok", "maven"),
}

# 示例：TS import → npm 依赖
NPM_IMPORT_TO_DEPENDENCY = {
    "react": ("react", "npm"),
    "vue": ("vue", "npm"),
    "@angular/core": ("@angular/core", "npm"),
    "express": ("express", "npm"),
}
```

#### 5.2.2 自动匹配（基于 external_dependencies 表）

种子规则覆盖不到的 import，通过已有的 `external_dependencies` 表进行自动匹配：

```python
async def auto_match_import_to_dependency(
    import_name: str,
    ecosystem: str,
    external_deps: list[ExternalDependency],
) -> ExternalDependency | None:
    """
    自动匹配 import 到外部依赖：
    1. 精确匹配 artifact_name（如 import "react" ↔ artifact "react"）
    2. 前缀匹配（如 import "org.springframework.web" ↔ artifact "spring-boot-starter-web"）
    3. 规范路径匹配（如 import "com.fasterxml.jackson" ↔ artifact "jackson-databind"）
    """
    # 1. 精确匹配
    for dep in external_deps:
        if import_name == dep.artifact_name or import_name.startswith(dep.artifact_name):
            return dep
    
    # 2. 前缀匹配（Java Maven 常见：import 包名 ↔ groupId）
    if ecosystem == "maven":
        for dep in external_deps:
            if dep.group_name and import_name.startswith(dep.group_name):
                return dep
    
    return None  # 无法匹配，标记为 unknown 外部依赖
```

**优势**：种子规则提供初始覆盖，自动匹配基于实际解析的依赖表动态扩展，避免了硬编码所有映射的维护成本。

---

## 6. API 路由与中间件链分析

### 6.1 路由提取

| 框架 | 路由定义方式 | 提取方式 | 示例 |
|------|------------|---------|------|
| Spring MVC | `@RequestMapping("/path")` | 注解解析 | `@GetMapping("/api/users/{id}")` |
| Spring Boot | `@GetMapping("/path")` | 注解解析 | `@PostMapping("/api/users")` |
| Express | `app.get("/path", handler)` | AST 模式匹配 | `router.get('/api/users/:id', handler)` |
| Koa | `router.get("/path", handler)` | AST 模式匹配 | `router.post('/api/users', handler)` |
| Flask | `@app.route("/path")` | 装饰器解析 | `@app.route("/api/users/<int:id>")` |
| FastAPI | `@app.get("/path")` | 装饰器解析 | `@app.get("/api/users/{id}")` |
| Gin | `router.GET("/path", handler)` | AST 模式匹配 | `router.GET("/api/users/:id", handler)` |

**路径模式标准化**：各框架的路径参数语法不同，统一转换为 OpenAPI 风格 `{param}` 格式存储到 `path_pattern`：
- Express/Koa `:id` → `{id}`
- Flask `<int:id>` → `{id}`（类型信息存储到 meta JSONB）
- Gin `:id` → `{id}`

### 6.2 中间件链提取

```python
class MiddlewareChainAnalyzer:
    """分析中间件/拦截器链"""
    
    def analyze_spring(self, repo_uuid: UUID) -> list[MiddlewareChain]:
        """分析 Spring Interceptor / Filter 链"""
        chains = []
        # 查找 @Configuration + WebMvcConfigurer 实现
        # 提取 addInterceptors() 方法中的拦截器注册
        return chains
    
    def analyze_express(self, repo_uuid: UUID) -> list[MiddlewareChain]:
        """分析 Express 中间件链"""
        chains = []
        # 查找 app.use(middleware) 调用
        # 按调用顺序（源码行号）构建中间件链
        return chains
```

**中间件链存储格式**（`api_routes.middlewares` JSONB）：

```json
[
  {
    "name": "authMiddleware",
    "order": 1,
    "file": "src/middleware/auth.ts",
    "type": "authentication"
  },
  {
    "name": "rateLimiter",
    "order": 2,
    "file": "src/middleware/rateLimiter.ts",
    "type": "rate_limiting"
  }
]
```

中间件链为**全局自动构建**：先扫描所有全局中间件（`app.use()`），再按路由注册时注入的中间件与全局中间件合并，通过源码行号排序确定执行顺序。

---

## 7. 调用图增强

### 7.1 当前问题

调用图仅按函数名匹配（`_match_call_edges` 第 270 行），`obj.method()` 只匹配 `method`，不区分对象类型。

### 7.2 增强方案：qualified_name 匹配

```python
# 当前：纯名称匹配
candidates = function_index.get(call_name, [])

# 增强：qualified_name 匹配（三级降级）
# 1. 精确匹配 qualified_name（如 "com.example.Service.method"）
candidates = qualified_index.get(call_name, [])
if not candidates:
    # 2. 方法名匹配（跨类同名，当前行为）
    candidates = function_index.get(method_name, [])
if not candidates:
    # 3. 未知调用
    edges_data.append({"callee_node_id": None, "call_type": "unknown"})
```

### 7.3 调用类型细分

| call_type | 当前值 | 增强后 | 说明 |
|-----------|--------|--------|------|
| `static` | 有 | 有 | 确定的目标调用 |
| `dynamic` | 有 | 有 | 反射/动态调用 |
| `unknown` | 有 | 有 | 无法匹配的调用 |
| **`external`** | 无 | **新增** | 外部依赖调用 |
| **`polymorphic`** | 无 | **新增（实验性）** | 多态调用（接口/父类，需类型推断，后续迭代实现） |
| **`injected`** | 无 | **新增** | 依赖注入调用 |

**`polymorphic` 标注为实验性的原因**：多态调用检测需要分析继承链和接口实现关系，在 AST 级别难以实现精确的类型推断。建议先在 Phase 5 中实现 `external` 和 `injected` 类型，`polymorphic` 留待后续迭代配合类型解析引擎实现。

**跨版本调用图存储**：调用图结果按 `analysis_version_id` 关联分析版本，前端切换版本时调用对应的调用图数据，避免版本间数据混淆。

---

## 8. 实施计划

### Phase 1：基础设施（预计 5-7 天）

| 任务 | 涉及文件 | 产出 |
|------|---------|------|
| ASTNode 数据类扩展 | `parsers/base.py` | tags, annotations, qualified_name 字段 |
| AstNodeModel 新增字段 | `models/ast_node.py` | tags, annotations, qualified_name 列 |
| Schema 同步 | `schemas/ast_node.py` | API 类型同步 |
| 数据库迁移脚本 | `migrations/` | ALTER TABLE + 新表 DDL（3 张新表 + 3 个字段） |
| AstNodeDAO 更新 | `repositories/ast_node.py` | 新增字段的 CRUD |
| StructurePipeline 适配 | `pipelines/structure_pipeline.py` | 新增字段写入 |
| 向后兼容性验证 | — | 验证已有仓库数据迁移后正常运行，现有 AST 节点默认值兼容 |

### Phase 2：Parser 通用增强（预计 5-7 天）

| 任务 | 涉及文件 | 产出 |
|------|---------|------|
| 对象方法提取（所有 parser） | `parsers/*.py` | `object_method` 节点类型 |
| 注解/装饰器提取（Java/Python/TS） | `parsers/java_parser.py`, `python_parser.py`, `typescript_parser.py` | annotations 字段填充 |
| qualified_name 计算 | `parsers/*.py` | 各语言限定名逻辑 |
| 单元测试 | `tests/parsers/` | 覆盖率 > 80% |

### Phase 3：前端框架支持（预计 5-7 天）

| 任务 | 涉及文件 | 产出 |
|------|---------|------|
| JSX/TSX 解析集成 | `parsers/typescript_parser.py` | tree-sitter-tsx 集成（需验证依赖可用性） |
| Vue SFC Parser（新建） | `parsers/vue_parser.py` | .vue 文件解析（含 `<script setup>` 支持） |
| React 组件/Hook 检测 | `analyzers/framework_tagger.py`（新建） | 标签逻辑 |
| Vue 组件/Composable 检测 | `analyzers/framework_tagger.py` | 标签逻辑 |
| 前端框架检测 | `analyzers/framework_detector.py`（新建） | 文件级检测 |

### Phase 4：后端框架支持（预计 5-7 天）

| 任务 | 涉及文件 | 产出 |
|------|---------|------|
| Spring 注解映射 | `analyzers/framework_tagger.py` | 10+ Spring 标签 |
| Spring 路由提取 | `analyzers/route_extractor.py`（新建） | api_routes 表写入 |
| Flask/FastAPI 路由提取 | `analyzers/route_extractor.py` | 装饰器路由解析 |
| Express/Koa 路由提取 | `analyzers/route_extractor.py` | AST 模式匹配 |
| 中间件链分析 | `analyzers/middleware_analyzer.py`（新建） | 链式结构提取 |
| Orchestrator 集成 | `tasks/analysis_orchestrator.py` | FrameworkDetector + RouteExtractor 调用 |

### Phase 5：外部依赖与跨模块（预计 5-7 天）

| 任务 | 涉及文件 | 产出 |
|------|---------|------|
| 依赖声明解析器 | `analyzers/dependency_parser.py`（新建） | pom.xml/package.json 等解析 |
| 依赖文件扫描 | `tasks/analysis_orchestrator.py` | 在扫描阶段集成 |
| Import → 外部依赖映射 | `analyzers/module_graph.py` | external_dependencies 关联（种子规则 + 自动匹配） |
| 调用图增强 | `analyzers/call_graph.py` | qualified_name 匹配 + `external`/`injected` 调用类型 |
| **依赖查询 API** | `api/dependencies.py`（新建） | GET /api/v1/repositories/{id}/dependencies |
| **路由查询 API** | `api/routes.py`（新建） | GET /api/v1/repositories/{id}/routes |
| **框架信息 API** | `api/frameworks.py`（新建） | GET /api/v1/repositories/{id}/frameworks |

### Phase 6：前端展示（预计 5-7 天）

| 任务 | 涉及文件 | 产出 |
|------|---------|------|
| 框架标签展示 | `components/RepoDetail.tsx` | 文件列表显示框架标签 |
| API 路由列表 | `components/RouteList.tsx`（新建） | 路由列表页面 |
| 外部依赖列表 | `components/DependencyList.tsx`（新建） | 依赖列表页面 |
| 调用图增强 | `components/CallGraph.tsx` | 外部调用节点样式 + 版本切换 |
| 中间件链可视化 | `components/MiddlewareChain.tsx`（新建） | DAG 图展示 |

**总工期估算**：30-42 天（Phase 3 和 Phase 4 可并行开发，实际工期可压缩至 25-35 天）。

---

## 9. 新增文件清单

```
codeinsight-backend/codeinsight/
├── parsers/
│   └── vue_parser.py              # 新增：Vue SFC 解析器
├── analyzers/
│   ├── framework_detector.py      # 新增：框架检测引擎
│   ├── framework_tagger.py        # 新增：AST 节点框架标签
│   ├── route_extractor.py         # 新增：API 路由提取
│   ├── middleware_analyzer.py     # 新增：中间件链分析
│   └── dependency_parser.py       # 新增：外部依赖声明解析
├── models/
│   ├── external_dependency.py     # 新增：ExternalDependencyModel
│   ├── api_route.py               # 新增：ApiRouteModel
│   └── framework_pattern.py       # 新增：FrameworkPatternModel
├── schemas/
│   ├── external_dependency.py     # 新增：Pydantic Schema
│   ├── api_route.py               # 新增：Pydantic Schema
│   └── framework_pattern.py       # 新增：Pydantic Schema
├── repositories/
│   ├── external_dependency.py     # 新增：DAO
│   ├── api_route.py               # 新增：DAO
│   └── framework_pattern.py       # 新增：DAO
├── api/
│   ├── dependencies.py            # 新增：依赖查询 API
│   ├── routes.py                  # 新增：路由查询 API
│   └── frameworks.py              # 新增：框架信息 API
└── migrations/
    └── versions/
        └── 003_framework_enhancement.py  # 新增：数据库迁移
```

---

## 10. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| tree-sitter-tsx 不可用 | TSX 解析失败 | 降级为 tree-sitter-typescript（自带 TSX 支持），忽略 JSX 元素 |
| Vue SFC 解析复杂度高 | 开发周期长 | 先只解析 `<script>`（含 `<script setup>`），`<template>` 后续迭代 |
| 框架版本差异导致注解/装饰器名称变化 | 检测遗漏 | 使用正则匹配 + 别名映射，支持自定义规则 |
| 分析性能下降（新增框架检测、依赖解析、路由提取等） | 单次分析耗时增加 2-3 倍 | 框架检测与依赖解析可并行执行；大型仓库按模块分批处理；文件级检测零解析成本 |
| 大仓库外部依赖解析耗时 | 分析变慢 | 异步解析，缓存依赖解析结果 |
| 调用图 qualified_name 匹配增加存储 | 数据库膨胀 | 仅对 class/method 节点计算 qualified_name |
| 多种框架混用（如 React + Express） | 检测混淆 | 分语言/目录独立检测，标签不冲突 |
| 数据库迁移失败（3 张新表 + 3 个字段） | 系统不可用 | 迁移脚本分步执行，每步支持回滚；迁移前全量备份数据库；先在 staging 环境验证 |
| 已有仓库数据迁移后兼容性 | 分析结果不一致 | Phase 1 增加向后兼容性验证任务；新字段均有默认值（`[]` / `""` / `NULL`），旧数据无需重新分析 |

---

## 11. 附录：框架标签完整列表

### 前端框架

| 标签 | 框架 | 含义 |
|------|------|------|
| `react-component` | React | 函数/类组件 |
| `react-hook` | React | 自定义 Hook |
| `react-context` | React | Context Provider |
| `vue-component` | Vue | 组件定义 |
| `vue-lifecycle` | Vue | 生命周期钩子 |
| `vue-composable` | Vue | Composition API |
| `vue-component-api` | Vue | `<script setup>` defineProps/defineEmits |
| `vue-async-setup` | Vue | `<script setup>` 顶层 await |
| `vue-directive` | Vue | 自定义指令 |
| `angular-component` | Angular | 组件 |
| `angular-service` | Angular | 服务 |
| `angular-module` | Angular | 模块 |
| `angular-pipe` | Angular | 管道 |

### 后端框架

| 标签 | 框架 | 含义 |
|------|------|------|
| `http-controller` | Spring | REST 控制器 |
| `business-service` | Spring | 业务服务 |
| `data-repository` | Spring | 数据仓库 |
| `spring-config` | Spring | 配置类 |
| `spring-aspect` | Spring | AOP 切面 |
| `spring-bean` | Spring | Bean 定义 |
| `flask-route` | Flask | 路由处理函数 |
| `fastapi-route` | FastAPI | 路由处理函数 |
| `express-route` | Express | 路由处理函数 |
| `express-middleware` | Express | 中间件 |
| `koa-middleware` | Koa | 中间件 |
| `django-view` | Django | 视图函数 |

### 通用

| 标签 | 含义 |
|------|------|
| `dependency-injection` | 依赖注入点 |
| `api-endpoint` | API 端点 |
| `transactional` | 事务边界 |
| `scheduled-task` | 定时任务 |
| `event-listener` | 事件监听器 |
| `cached-function` | 缓存函数 |
| `async-task` | 异步任务 |
| `external-dependency` | 外部依赖调用 |