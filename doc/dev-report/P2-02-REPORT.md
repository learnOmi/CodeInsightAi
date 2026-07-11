# P2-02: Tree-sitter 封装层开发报告

## 任务概述

基于 tree-sitter 0.26.0 新 API，重新实现多语言 AST 解析器，提供统一的接口和数据结构。

## 开发目标

1. 升级 tree-sitter 到 0.26.0 版本
2. 实现 5 种语言的解析器（Python, TypeScript, JavaScript, Java, Go）
3. 提供统一的接口（`LanguageParser`）和数据模型（`ASTNode`, `ASTNodeList`）
4. 实现工厂类（`ParserFactory`）支持动态获取解析器
5. 确保所有解析器功能完整（函数、类、方法、调用、导入）

## 技术选型

### tree-sitter 0.26.0 API 变更

tree-sitter 0.26.0 进行了重大 API 变更：

- **旧 API**（已废弃）：
  ```python
  parser = Parser()
  parser.set_language(Language("python"))
  ```

- **新 API**（0.26.0+）：
  ```python
  language = Language(python_language())
  parser = Parser(language)
  ```

- **语言包分离**：不再使用 `tree-sitter-languages` 统一包，每个语言需要独立安装：
  - `tree-sitter-python>=0.23.0`
  - `tree-sitter-javascript>=0.23.0`
  - `tree-sitter-typescript>=0.23.0`
  - `tree-sitter-java>=0.23.0`
  - `tree-sitter-go>=0.23.0`

### 语言包 API 差异

不同语言包的 API 略有差异：

| 语言 | 导入方式 |
|------|----------|
| Python | `from tree_sitter_python import language as python_language` |
| JavaScript | `from tree_sitter_javascript import language as javascript_language` |
| TypeScript | `from tree_sitter_typescript import language_typescript as typescript_language` |
| Java | `from tree_sitter_java import language as java_language` |
| Go | `from tree_sitter_go import language as go_language` |

## 架构设计

### 核心组件

```
codeinsight/parsers/
├── __init__.py              # 模块导出
├── base.py                  # 基础类定义
│   ├── ASTNode              # AST 节点数据结构
│   ├── ASTNodeList          # 节点列表，支持便捷查询
│   └── LanguageParser       # 解析器抽象基类
├── parser_factory.py        # 解析器工厂
├── python_parser.py         # Python 解析器
├── typescript_parser.py     # TypeScript 解析器
├── javascript_parser.py     # JavaScript 解析器
├── java_parser.py           # Java 解析器
└── go_parser.py             # Go 解析器
```

### ASTNode 数据结构

```python
@dataclass
class ASTNode:
    node_type: str           # 节点类型 (function, class, method, call, import)
    name: str                # 节点名称 (函数名/类名)
    start_line: int          # 起始行 (1-indexed)
    end_line: int            # 结束行 (1-indexed)
    start_column: int        # 起始列 (1-indexed)
    end_column: int          # 结束列 (1-indexed)
    children: list[ASTNode]  # 子节点
    parent: ASTNode | None   # 父节点
    language: str            # 语言类型
    file_path: str           # 源文件路径
```

### 节点类型定义

| 类型 | 说明 | 提取内容 |
|------|------|----------|
| `function` | 函数定义 | 函数名、位置 |
| `class` | 类定义 | 类名、位置 |
| `method` | 类中的方法 | 方法名、位置 |
| `call` | 函数调用 | 被调用函数名、位置 |
| `import` | 导入语句 | 模块名、位置 |

### 语言特定的 AST 结构

不同语言的 tree-sitter AST 结构有所不同，需要针对性处理：

| 语言 | 类体节点 | 方法定义节点 | 调用表达式节点 |
|------|----------|--------------|----------------|
| Python | `block` | `function_definition` | `call` |
| JavaScript | `class_body` | `method_definition` | `call_expression` |
| TypeScript | `class_body` | `method_definition` | `call_expression` |
| Java | `class_body` | `method_declaration` | `method_invocation` |
| Go | `declaration_list` | `method_spec` | `call_expression` |

## 实现细节

### 1. 解析器初始化

```python
def __init__(self) -> None:
    if not TREE_SITTER_AVAILABLE:
        raise ImportError("tree-sitter 不可用，请安装相关依赖")
    
    # 使用新 API 创建 Language 和 Parser
    self._language = Language(language_function())
    self._parser = Parser(self._language)
    self._language_name = "language_name"
```

### 2. 文件解析流程

```python
def parse_file(self, file_path: Path | str) -> ASTNodeList:
    path = Path(file_path)
    if not path.exists():
        return ASTNodeList()
    
    content = path.read_bytes()
    tree = self._parser.parse(content)
    root_node = tree.root_node
    
    nodes = ASTNodeList()
    self._extract_nodes(root_node, nodes, str(path), self._language_name)
    
    return nodes
```

### 3. 节点提取算法

采用递归遍历 AST 的策略：

```python
def _extract_nodes(self, node, result, file_path, language, parent_node=None):
    node_type = node.type
    
    # 处理特定节点类型
    if node_type == "function_declaration":
        ast_node = self._create_function_node(...)
        result.add(ast_node)
        self._extract_nodes_from_node(node, result, ..., ast_node)
    
    elif node_type == "class_declaration":
        ast_node = self._create_class_node(...)
        result.add(ast_node)
        self._extract_nodes_from_node(node, result, ..., ast_node)
    
    # 递归处理子节点
    for child in node.children:
        self._extract_nodes(child, result, file_path, language, parent_node)
```

### 4. 方法提取的特殊处理

类方法位于类体（class body）节点内，需要特殊处理：

```python
def _extract_nodes_from_node(self, node, result, file_path, language, parent_node):
    for child in node.children:
        child_type = child.type
        
        # 在类中查找方法
        if parent_node.node_type == "class":
            # 直接的方法定义
            if child_type == "method_definition":
                method_node = self._create_method_node(...)
                result.add(method_node)
                self._extract_nodes_from_node(child, result, ..., method_node)
            
            # 类体节点（class_body/block/declaration_list）
            elif child_type in ("class_body", "block", "declaration_list"):
                for body_child in child.children:
                    if body_child.type == "method_definition":
                        method_node = self._create_method_node(...)
                        result.add(method_node)
                        self._extract_nodes_from_node(body_child, result, ..., method_node)
        
        # 处理函数调用
        elif child_type == "call_expression":
            call_node = self._create_call_node(...)
            result.add(call_node)
        
        # 递归处理其他节点
        else:
            self._extract_nodes(child, result, file_path, language, parent_node)
```

### 5. 工厂类设计

```python
class ParserFactory:
    _parsers: dict[str, type[LanguageParser]] = {
        "python": PythonParser,
        "typescript": TypeScriptParser,
        "javascript": JavaScriptParser,
        "java": JavaParser,
        "go": GoParser,
    }
    
    @classmethod
    def get_parser(cls, language: str) -> LanguageParser:
        parser_class = cls._parsers.get(language.lower())
        if not parser_class:
            raise ValueError(f"不支持的语言: {language}")
        return parser_class()
```

## 测试结果

### 测试覆盖

- **总计**: 37 个测试用例
- **Python 解析器**: 13 个测试
- **TypeScript 解析器**: 7 个测试
- **JavaScript 解析器**: 5 个测试
- **Java 解析器**: 6 个测试
- **Go 解析器**: 6 个测试

### 测试用例

每个语言解析器的测试包括：

1. `test_get_language_name` - 验证语言名称
2. `test_parse_file_returns_ast_node_list` - 验证返回类型
3. `test_parse_file_extracts_function` - 验证函数提取
4. `test_parse_file_extracts_class` - 验证类提取
5. `test_parse_file_extracts_method` - 验证方法提取
6. `test_parse_file_extracts_import` - 验证导入提取
7. `test_parse_file_extracts_call` - 验证调用提取

### 测试结果

```
============================= 37 passed in 2.32s ==============================
```

所有测试通过！

## 文件变更清单

### 新增文件

1. `codeinsight/parsers/__init__.py` - 模块导出
2. `codeinsight/parsers/base.py` - 基础类（`ASTNode`, `ASTNodeList`, `LanguageParser`）
3. `codeinsight/parsers/parser_factory.py` - 解析器工厂
4. `codeinsight/parsers/python_parser.py` - Python 解析器
5. `codeinsight/parsers/typescript_parser.py` - TypeScript 解析器
6. `codeinsight/parsers/javascript_parser.py` - JavaScript 解析器
7. `codeinsight/parsers/java_parser.py` - Java 解析器
8. `codeinsight/parsers/go_parser.py` - Go 解析器
9. `tests/test_parsers/test_python_parser.py` - Python 解析器测试
10. `tests/test_parsers/test_other_parsers.py` - 其他语言解析器测试

### 修改文件

1. `pyproject.toml` - 更新依赖（移除 `tree-sitter-languages`，添加独立语言包）

### 依赖变更

```diff
 dependencies = [
     "fastapi>=0.115.0",
     ...
-    "tree-sitter-languages>=1.10.0",
+    "tree-sitter>=0.26.0",
+    "tree-sitter-python>=0.23.0",
+    "tree-sitter-javascript>=0.23.0",
+    "tree-sitter-typescript>=0.23.0",
+    "tree-sitter-java>=0.23.0",
+    "tree-sitter-go>=0.23.0",
     ...
 ]
```

## 技术难点与解决方案

### 1. tree-sitter 0.26.0 API 兼容性

**问题**：旧版 `tree-sitter-languages` 包与 0.26.0 不兼容，`Parser.set_language()` 已移除。

**解决方案**：
- 升级到 0.26.0 新 API
- 使用独立的语言包替代统一包
- 每个语言包独立导入和初始化

### 2. TypeScript 语言包 API 特殊性

**问题**：`tree-sitter-typescript` 使用 `language_typescript()` 而非 `language()`。

**解决方案**：
```python
from tree_sitter_typescript import language_typescript as typescript_language
self._language = Language(typescript_language())
```

### 3. 不同语言的类体节点差异

**问题**：各语言使用不同的节点类型表示类体：
- Python: `block`
- JavaScript/TypeScript: `class_body`
- Java: `class_body`
- Go: `declaration_list`

**解决方案**：
在 `_extract_nodes_from_node` 中统一处理这些节点类型：
```python
elif child_type in ("class_body", "block", "declaration_list"):
    for body_child in child.children:
        if body_child.type == "method_definition":
            # 提取方法
```

### 4. Python 方法定义节点

**问题**：Python 中方法和函数都使用 `function_definition` 节点。

**解决方案**：
通过检查父节点是否为主题判断是方法还是函数：
```python
if parent_node.node_type == "class" and child_type == "function_definition":
    method_node = self._create_method_node(...)
```

## 性能考虑

### 内存优化

- 使用 `path.read_bytes()` 一次性读取文件，适用于中小文件
- 对于大文件，建议后续优化为流式分块读取

### 解析性能

- tree-sitter 是增量解析引擎，性能优异
- 平均解析时间：2-3 秒（包括 5 个解析器的初始化和测试）

## 后续优化方向

1. **缓存机制**：为解析器添加缓存，避免重复解析相同文件
2. **异步支持**：实现异步解析接口，提高并发性能
3. **大文件优化**：实现流式解析，减少内存占用
4. **更多语言支持**：扩展到 C/C++, Rust, Ruby 等语言
5. **节点扩展**：添加更多节点类型（变量、常量、枚举等）

## 任务完成状态

- [x] 升级 tree-sitter 到 0.26.0
- [x] 实现 Python 解析器
- [x] 实现 TypeScript 解析器
- [x] 实现 JavaScript 解析器
- [x] 实现 Java 解析器
- [x] 实现 Go 解析器
- [x] 实现工厂类
- [x] 编写单元测试（37 个测试用例）
- [x] 所有测试通过
- [x] 清理调试代码
- [x] 编写开发报告

## 总结

P2-02 任务已完成。成功实现了基于 tree-sitter 0.26.0 的多语言 AST 解析器，提供统一的接口和数据模型，所有 37 个测试用例均通过。该封装层为后续的代码分析功能（函数依赖、调用关系、复杂度计算等）提供了坚实的基础。

---

**开发日期**: 2026-07-12  
**开发人员**: Trae AI  
**任务编号**: P2-02  
**状态**: ✅ 已完成
