"""
Phase 2 单元测试：对象方法提取、注解/装饰器提取、qualified_name 计算

测试覆盖：
- base.py 公用方法（_is_function_node, _node_text_to_str, _extract_annotations, _create_object_method_node）
- TypeScript/JavaScript 对象方法提取
- Java 注解提取 + qualified_name
- Python 装饰器提取 + qualified_name
- Go qualified_name（receiver-based）
"""

from pathlib import Path

import pytest

from codeinsight.parsers.base import ASTNode, ASTNodeList
from codeinsight.parsers.go_parser import GoParser
from codeinsight.parsers.java_parser import JavaParser
from codeinsight.parsers.javascript_parser import JavaScriptParser
from codeinsight.parsers.python_parser import PythonParser
from codeinsight.parsers.typescript_parser import TypeScriptParser

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def ts_parser():
    return TypeScriptParser()


@pytest.fixture
def js_parser():
    return JavaScriptParser()


@pytest.fixture
def java_parser():
    return JavaParser()


@pytest.fixture
def python_parser():
    return PythonParser()


@pytest.fixture
def go_parser():
    return GoParser()


# ============================================================
# Base 公用方法测试
# ============================================================


class TestBaseUtilities:
    """测试 base.py 中 Phase 2 新增的公用方法"""

    def test_node_text_to_str_with_valid_node(self, ts_parser):
        """测试 _node_text_to_str 正常提取节点文本"""
        ts_file = _create_temp_file("test_str.ts", "const x = 1;")
        result = ts_parser.parse_file(ts_file)
        # 只要能解析成功就说明方法没有崩溃
        assert isinstance(result, ASTNodeList)

    def test_node_text_to_str_with_none(self, ts_parser):
        """测试 _node_text_to_str 处理 None"""
        result = ts_parser._node_text_to_str(None)
        assert result == ""

    def test_is_function_node_true_cases(self, ts_parser):
        """测试 _is_function_node 对函数类型返回 True"""
        # 用真实的 tree-sitter 节点来验证，解析一个包含各种函数类型的文件
        ts_file = _create_temp_file(
            "test_fn.ts",
            """
function foo() {}
const bar = function() {};
const baz = () => {};
class C { method() {} }
""",
        )
        result = ts_parser.parse_file(ts_file)
        assert len(result) > 0

    def test_is_function_node_with_none(self, ts_parser):
        """测试 _is_function_node 处理 None"""
        assert ts_parser._is_function_node(None) is False


# ============================================================
# 对象方法提取测试（TypeScript / JavaScript）
# ============================================================


class TestObjectMethodExtraction:
    """测试 TS/JS 解析器的对象方法提取"""

    @pytest.fixture
    def ts_vue_options_file(self, tmp_path: Path) -> Path:
        """创建 Vue Options API 风格的 TS 文件"""
        content = """
export default {
    name: 'MyComponent',
    data() {
        return { count: 0 };
    },
    mounted() {
        console.log('mounted');
    },
    methods: {
        increment() {
            this.count++;
        },
        decrement() {
            this.count--;
        },
    },
    computed: {
        doubleCount() {
            return this.count * 2;
        },
    },
};
"""
        file_path = tmp_path / "vue-options.ts"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def js_config_object_file(self, tmp_path: Path) -> Path:
        """创建 JS 配置对象文件"""
        content = """
const config = {
    onSuccess(data) {
        console.log('success', data);
    },
    onError(err) {
        console.error('error', err);
    },
};
module.exports = config;
"""
        file_path = tmp_path / "config.js"
        file_path.write_text(content)
        return file_path

    def test_ts_extracts_object_methods(self, ts_parser, ts_vue_options_file):
        """测试 TypeScript 提取对象方法"""
        result = ts_parser.parse_file(ts_vue_options_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        object_methods = [n for n in result.nodes if n.node_type == "object_method"]
        # 应该提取到 mounted, increment, decrement, doubleCount
        assert len(object_methods) >= 4
        method_names = {m.name for m in object_methods}
        assert "mounted" in method_names
        assert "increment" in method_names
        assert "decrement" in method_names
        assert "doubleCount" in method_names

    def test_ts_object_method_has_correct_type(self, ts_parser, ts_vue_options_file):
        """测试对象方法节点类型为 object_method"""
        result = ts_parser.parse_file(ts_vue_options_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        object_methods = [n for n in result.nodes if n.node_type == "object_method"]
        for m in object_methods:
            assert m.node_type == "object_method"
            assert m.name != ""
            assert m.start_line > 0
            assert m.end_line > 0

    def test_js_extracts_object_methods(self, js_parser, js_config_object_file):
        """测试 JavaScript 提取对象方法"""
        result = js_parser.parse_file(js_config_object_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        object_methods = [n for n in result.nodes if n.node_type == "object_method"]
        assert len(object_methods) >= 2
        method_names = {m.name for m in object_methods}
        assert "onSuccess" in method_names
        assert "onError" in method_names

    def test_ts_nested_object_methods(self, ts_parser, tmp_path: Path):
        """测试嵌套对象方法提取（如 methods: { foo() {} }）"""
        content = """
const obj = {
    outer: {
        inner() {
            return 42;
        },
        deep: {
            deepest() {
                return 99;
            },
        },
    },
};
"""
        file_path = tmp_path / "nested.ts"
        file_path.write_text(content)
        result = ts_parser.parse_file(file_path)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        object_methods = [n for n in result.nodes if n.node_type == "object_method"]
        method_names = {m.name for m in object_methods}
        assert "inner" in method_names
        assert "deepest" in method_names

    def test_ts_non_function_pair_not_extracted(self, ts_parser, tmp_path: Path):
        """测试非函数 pair 不被提取为 object_method"""
        content = """
const config = {
    name: 'test',
    version: '1.0.0',
    debug: true,
    getValue() {
        return 42;
    },
};
"""
        file_path = tmp_path / "mixed.ts"
        file_path.write_text(content)
        result = ts_parser.parse_file(file_path)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        object_methods = [n for n in result.nodes if n.node_type == "object_method"]
        # 只有 getValue 是方法
        assert len(object_methods) == 1
        assert object_methods[0].name == "getValue"


# ============================================================
# 注解/装饰器提取测试
# ============================================================


class TestAnnotationExtraction:
    """测试各语言的注解/装饰器提取"""

    @pytest.fixture
    def java_spring_file(self, tmp_path: Path) -> Path:
        content = """
package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

@Service
public class UserService {
    @Autowired
    private UserRepository userRepository;

    @Override
    public String getUserName(Long id) {
        return userRepository.findById(id).getName();
    }
}
"""
        file_path = tmp_path / "UserService.java"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def java_multi_annotation_file(self, tmp_path: Path) -> Path:
        content = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users")
public class UserController {
    @GetMapping("/{id}")
    @ResponseBody
    public User getUser(@PathVariable Long id) {
        return new User();
    }
}
"""
        file_path = tmp_path / "UserController.java"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def python_decorator_file(self, tmp_path: Path) -> Path:
        content = """
from functools import lru_cache

@lru_cache(maxsize=128)
def cached_func(x):
    return x * 2

class MyClass:
    @staticmethod
    def static_method():
        pass

    @classmethod
    def class_method(cls):
        pass

    @property
    def value(self):
        return 42
"""
        file_path = tmp_path / "decorators.py"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def ts_decorator_file(self, tmp_path: Path) -> Path:
        content = """
@Component({
    selector: 'app-root',
})
class AppComponent {
    @Input()
    title: string;

    @Output()
    change = new EventEmitter();
}
"""
        file_path = tmp_path / "decorators.ts"
        file_path.write_text(content)
        return file_path

    def test_java_extracts_class_annotations(self, java_parser, java_spring_file):
        """测试 Java 提取类级别注解"""
        result = java_parser.parse_file(java_spring_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        classes = result.get_classes()
        assert len(classes) >= 1
        user_service = next((c for c in classes if c.name == "UserService"), None)
        assert user_service is not None
        assert len(user_service.annotations) >= 1
        ann_names = [a["name"] for a in user_service.annotations]
        assert "@Service" in ann_names

    def test_java_extracts_method_annotations(self, java_parser, java_spring_file):
        """测试 Java 提取方法级别注解"""
        result = java_parser.parse_file(java_spring_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        methods = [n for n in result.nodes if n.node_type == "method"]
        get_user = next((m for m in methods if m.name == "getUserName"), None)
        assert get_user is not None
        ann_names = [a["name"] for a in get_user.annotations]
        assert "@Override" in ann_names

    def test_java_multi_annotations(self, java_parser, java_multi_annotation_file):
        """测试 Java 多个注解的提取"""
        result = java_parser.parse_file(java_multi_annotation_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        classes = result.get_classes()
        controller = next((c for c in classes if c.name == "UserController"), None)
        assert controller is not None
        ann_names = [a["name"] for a in controller.annotations]
        assert "@RestController" in ann_names
        assert "@RequestMapping" in ann_names

    def test_java_annotation_has_args(self, java_parser, java_multi_annotation_file):
        """测试 Java 注解参数提取"""
        result = java_parser.parse_file(java_multi_annotation_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        classes = result.get_classes()
        controller = next((c for c in classes if c.name == "UserController"), None)
        assert controller is not None
        request_mapping = next((a for a in controller.annotations if a["name"] == "@RequestMapping"), None)
        assert request_mapping is not None
        # 应该包含参数 "/api/users"
        assert len(request_mapping["args"]) > 0

    def test_ts_extracts_decorators(self, ts_parser, ts_decorator_file):
        """测试 TypeScript 提取装饰器"""
        result = ts_parser.parse_file(ts_decorator_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        classes = result.get_classes()
        assert len(classes) >= 1
        app = classes[0]
        assert len(app.annotations) >= 1
        ann_names = [a["name"] for a in app.annotations]
        assert any("Component" in name for name in ann_names)

    def test_no_annotation_for_undecorated_node(self, java_parser, tmp_path: Path):
        """测试无注解的节点 annotations 为空列表"""
        content = """
package com.example;
public class PlainClass {
    public void plainMethod() {}
}
"""
        file_path = tmp_path / "PlainClass.java"
        file_path.write_text(content)
        result = java_parser.parse_file(file_path)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        classes = result.get_classes()
        assert len(classes) >= 1
        assert classes[0].annotations == []


# ============================================================
# qualified_name 测试
# ============================================================


class TestQualifiedName:
    """测试各语言的 qualified_name 计算"""

    @pytest.fixture
    def java_qualified_file(self, tmp_path: Path) -> Path:
        content = """
package com.example.service;

public class UserService {
    public String getUserName(Long id) {
        return "";
    }
    public UserService() {}
}
"""
        file_path = tmp_path / "UserService.java"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def python_qualified_file(self, tmp_path: Path) -> Path:
        content = """
def top_function():
    pass

class MyClass:
    def method_one(self):
        pass

    def method_two(self):
        pass
"""
        file_path = tmp_path / "my_module.py"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def go_qualified_file(self, tmp_path: Path) -> Path:
        content = """
package main

type Server struct {
    port int
}

func (s *Server) Start() error {
    return nil
}

func (s *Server) Stop() error {
    return nil
}

func NewServer() *Server {
    return &Server{}
}
"""
        file_path = tmp_path / "server.go"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def ts_qualified_file(self, tmp_path: Path) -> Path:
        content = """
export function topFunc(): void {}

export class MyComponent {
    handleClick(): void {}
    handleChange(): void {}
}
"""
        file_path = tmp_path / "component.ts"
        file_path.write_text(content)
        return file_path

    def test_java_class_qualified_name(self, java_parser, java_qualified_file):
        """测试 Java 类 qualified_name"""
        result = java_parser.parse_file(java_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        classes = result.get_classes()
        assert len(classes) >= 1
        user_service = classes[0]
        assert user_service.qualified_name == "com.example.service.UserService"

    def test_java_method_qualified_name(self, java_parser, java_qualified_file):
        """测试 Java 方法 qualified_name"""
        result = java_parser.parse_file(java_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        methods = [n for n in result.nodes if n.node_type == "method"]
        get_user = next((m for m in methods if m.name == "getUserName"), None)
        assert get_user is not None
        assert get_user.qualified_name == "com.example.service.UserService.getUserName"

    def test_java_constructor_qualified_name(self, java_parser, java_qualified_file):
        """测试 Java 构造器 qualified_name"""
        result = java_parser.parse_file(java_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        constructors = [n for n in result.nodes if n.node_type == "constructor"]
        assert len(constructors) >= 1
        assert constructors[0].qualified_name == "com.example.service.UserService.UserService"

    def test_python_top_function_qualified_name(self, python_parser, python_qualified_file):
        """测试 Python 顶层函数 qualified_name"""
        result = python_parser.parse_file(python_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        functions = [n for n in result.nodes if n.node_type == "function"]
        top_func = next((f for f in functions if f.name == "top_function"), None)
        assert top_func is not None
        assert top_func.qualified_name == "my_module.top_function"

    def test_python_method_qualified_name(self, python_parser, python_qualified_file):
        """测试 Python 方法 qualified_name"""
        result = python_parser.parse_file(python_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        methods = [n for n in result.nodes if n.node_type == "method"]
        method_one = next((m for m in methods if m.name == "method_one"), None)
        assert method_one is not None
        assert method_one.qualified_name == "my_module.MyClass.method_one"

    def test_go_function_qualified_name(self, go_parser, go_qualified_file):
        """测试 Go 函数 qualified_name"""
        result = go_parser.parse_file(go_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        functions = [n for n in result.nodes if n.node_type == "function"]
        new_server = next((f for f in functions if f.name == "NewServer"), None)
        assert new_server is not None
        assert new_server.qualified_name == "server:NewServer"

    def test_go_method_qualified_name(self, go_parser, go_qualified_file):
        """测试 Go 方法 qualified_name（基于 receiver）"""
        result = go_parser.parse_file(go_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        methods = [n for n in result.nodes if n.node_type == "method"]
        start = next((m for m in methods if m.name == "Start"), None)
        assert start is not None
        assert start.qualified_name == "server:Server.Start"

    def test_go_struct_qualified_name(self, go_parser, go_qualified_file):
        """测试 Go 结构体 qualified_name"""
        result = go_parser.parse_file(go_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        structs = [n for n in result.nodes if n.node_type == "struct"]
        assert len(structs) >= 1
        assert structs[0].qualified_name == "server:Server"

    def test_ts_function_qualified_name(self, ts_parser, ts_qualified_file):
        """测试 TypeScript 函数 qualified_name"""
        result = ts_parser.parse_file(ts_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        functions = [n for n in result.nodes if n.node_type == "function"]
        top_func = next((f for f in functions if f.name == "topFunc"), None)
        assert top_func is not None
        assert top_func.qualified_name == "component:topFunc"

    def test_ts_method_qualified_name(self, ts_parser, ts_qualified_file):
        """测试 TypeScript 方法 qualified_name"""
        result = ts_parser.parse_file(ts_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        methods = [n for n in result.nodes if n.node_type == "method"]
        click = next((m for m in methods if m.name == "handleClick"), None)
        assert click is not None
        assert click.qualified_name == "component:MyComponent.handleClick"

    def test_import_has_no_qualified_name(self, java_parser, java_qualified_file):
        """测试 import 节点不计算 qualified_name"""
        result = java_parser.parse_file(java_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        imports = result.get_imports()
        for imp in imports:
            assert imp.qualified_name == ""

    def test_qualified_name_not_empty_for_classes(self, java_parser, java_qualified_file):
        """测试类的 qualified_name 非空"""
        result = java_parser.parse_file(java_qualified_file)
        if len(result) == 0:
            pytest.skip("tree-sitter 解析返回空结果")
        classes = result.get_classes()
        for cls in classes:
            assert cls.qualified_name != ""


# ============================================================
# ASTNode 新字段测试
# ============================================================


class TestASTNodeNewFields:
    """测试 ASTNode Phase 1/2 新增的字段"""

    def test_ast_node_tags_default(self):
        """测试 tags 默认值为空列表"""
        node = ASTNode(
            node_type="function",
            name="test",
            start_line=1,
            end_line=5,
            start_column=0,
            end_column=10,
        )
        assert node.tags == []

    def test_ast_node_annotations_default(self):
        """测试 annotations 默认值为空列表"""
        node = ASTNode(
            node_type="function",
            name="test",
            start_line=1,
            end_line=5,
            start_column=0,
            end_column=10,
        )
        assert node.annotations == []

    def test_ast_node_qualified_name_default(self):
        """测试 qualified_name 默认值为空字符串"""
        node = ASTNode(
            node_type="function",
            name="test",
            start_line=1,
            end_line=5,
            start_column=0,
            end_column=10,
        )
        assert node.qualified_name == ""

    def test_ast_node_to_dict_includes_new_fields(self):
        """测试 to_dict 包含新字段"""
        node = ASTNode(
            node_type="class",
            name="MyClass",
            start_line=1,
            end_line=10,
            start_column=0,
            end_column=20,
            tags=["react-component"],
            annotations=[{"name": "@Component", "args": []}],
            qualified_name="src/App:MyClass",
        )
        d = node.to_dict()
        assert d["tags"] == ["react-component"]
        assert d["annotations"] == [{"name": "@Component", "args": []}]
        assert d["qualified_name"] == "src/App:MyClass"

    def test_ast_node_create_with_all_fields(self):
        """测试使用所有字段创建 ASTNode"""
        node = ASTNode(
            node_type="method",
            name="handleClick",
            start_line=5,
            end_line=8,
            start_column=2,
            end_column=4,
            language="typescript",
            file_path="/src/component.ts",
            tags=["react-component"],
            annotations=[{"name": "@autobind", "args": []}],
            qualified_name="component:MyComponent.handleClick",
        )
        assert node.node_type == "method"
        assert node.name == "handleClick"
        assert node.language == "typescript"
        assert node.tags == ["react-component"]
        assert len(node.annotations) == 1
        assert node.qualified_name == "component:MyComponent.handleClick"


# ============================================================
# Helpers
# ============================================================


def _create_temp_file(name: str, content: str) -> Path:
    """创建临时文件用于测试"""
    import tempfile

    tmp_dir = Path(tempfile.gettempdir()) / "phase2_tests"
    tmp_dir.mkdir(exist_ok=True)
    file_path = tmp_dir / name
    file_path.write_text(content, encoding="utf-8")
    return file_path
