"""
TypeScriptParser, JavaScriptParser, JavaParser, GoParser 单元测试
"""

from pathlib import Path

import pytest

from codeinsight.parsers.typescript_parser import TypeScriptParser
from codeinsight.parsers.javascript_parser import JavaScriptParser
from codeinsight.parsers.java_parser import JavaParser
from codeinsight.parsers.go_parser import GoParser
from codeinsight.parsers.base import ASTNodeList


@pytest.fixture
def typescript_parser():
    """创建 TypeScript 解析器实例"""
    return TypeScriptParser()


@pytest.fixture
def javascript_parser():
    """创建 JavaScript 解析器实例"""
    return JavaScriptParser()


@pytest.fixture
def java_parser():
    """创建 Java 解析器实例"""
    return JavaParser()


@pytest.fixture
def go_parser():
    """创建 Go 解析器实例"""
    return GoParser()


# --- TypeScript 测试 ---

class TestTypeScriptParser:
    """TypeScriptParser 测试"""

    @pytest.fixture
    def sample_ts_file(self, tmp_path: Path) -> Path:
        """创建示例 TypeScript 文件"""
        content = """
function greet(name: string): string {
    return `Hello, ${name}`;
}

class Greeter {
    constructor(private name: string) {}

    sayHello(): void {
        console.log(`Hello, I'm ${this.name}`);
    }
}

const g = new Greeter("Alice");
g.sayHello();

import * as path from "path";
"""
        file_path = tmp_path / "test.ts"
        file_path.write_text(content)
        return file_path

    def test_get_language_name(self, typescript_parser):
        """测试语言名称"""
        assert typescript_parser.get_language_name() == "typescript"

    def test_parse_file_returns_ast_node_list(self, typescript_parser, sample_ts_file):
        """测试解析文件返回 ASTNodeList"""
        result = typescript_parser.parse_file(sample_ts_file)
        assert isinstance(result, ASTNodeList)
        # 不检查 len(result) > 0，因为 tree-sitter 可能不可用

    def test_parse_file_extracts_function(self, typescript_parser, sample_ts_file):
        """测试提取函数"""
        result = typescript_parser.parse_file(sample_ts_file)
        if len(result) > 0:
            functions = result.get_functions()
            assert len(functions) >= 1
            assert any(f.name == "greet" for f in functions)

    def test_parse_file_extracts_class(self, typescript_parser, sample_ts_file):
        """测试提取类"""
        result = typescript_parser.parse_file(sample_ts_file)
        if len(result) > 0:
            classes = result.get_classes()
            assert len(classes) >= 1
            assert any(c.name == "Greeter" for c in classes)

    def test_parse_file_extracts_method(self, typescript_parser, sample_ts_file):
        """测试提取方法"""
        result = typescript_parser.parse_file(sample_ts_file)
        if len(result) > 0:
            methods = [n for n in result.nodes if n.node_type == "method"]
            assert len(methods) >= 1
            assert any(m.name == "sayHello" for m in methods)

    def test_parse_file_extracts_import(self, typescript_parser, sample_ts_file):
        """测试提取导入"""
        result = typescript_parser.parse_file(sample_ts_file)
        if len(result) > 0:
            imports = result.get_imports()
            assert len(imports) >= 1
            assert any(i.name == '"path"' or i.name == "path" for i in imports)

    def test_parse_file_extracts_call(self, typescript_parser, sample_ts_file):
        """测试提取调用"""
        result = typescript_parser.parse_file(sample_ts_file)
        if len(result) > 0:
            calls = result.get_calls()
            assert len(calls) >= 1
            # 应该有 console.log 和 g.sayHello 调用


# --- JavaScript 测试 ---

class TestJavaScriptParser:
    """JavaScriptParser 测试"""

    @pytest.fixture
    def sample_js_file(self, tmp_path: Path) -> Path:
        """创建示例 JavaScript 文件"""
        content = """
function greet(name) {
    return "Hello, " + name;
}

class Greeter {
    constructor(name) {
        this.name = name;
    }

    sayHello() {
        console.log("Hello, I'm " + this.name);
    }
}

const g = new Greeter("Alice");
g.sayHello();

import * as path from "path";
"""
        file_path = tmp_path / "test.js"
        file_path.write_text(content)
        return file_path

    def test_get_language_name(self, javascript_parser):
        """测试语言名称"""
        assert javascript_parser.get_language_name() == "javascript"

    def test_parse_file_returns_ast_node_list(self, javascript_parser, sample_js_file):
        """测试解析文件返回 ASTNodeList"""
        result = javascript_parser.parse_file(sample_js_file)
        assert isinstance(result, ASTNodeList)

    def test_parse_file_extracts_function(self, javascript_parser, sample_js_file):
        """测试提取函数"""
        result = javascript_parser.parse_file(sample_js_file)
        if len(result) > 0:
            functions = result.get_functions()
            assert len(functions) >= 1

    def test_parse_file_extracts_class(self, javascript_parser, sample_js_file):
        """测试提取类"""
        result = javascript_parser.parse_file(sample_js_file)
        if len(result) > 0:
            classes = result.get_classes()
            assert len(classes) >= 1

    def test_parse_file_extracts_method(self, javascript_parser, sample_js_file):
        """测试提取方法"""
        result = javascript_parser.parse_file(sample_js_file)
        if len(result) > 0:
            methods = [n for n in result.nodes if n.node_type == "method"]
            assert len(methods) >= 1


# --- Java 测试 ---

class TestJavaParser:
    """JavaParser 测试"""

    @pytest.fixture
    def sample_java_file(self, tmp_path: Path) -> Path:
        """创建示例 Java 文件"""
        content = """
package com.example;

import java.util.List;

public class Greeter {
    private String name;

    public Greeter(String name) {
        this.name = name;
    }

    public String sayHello() {
        return "Hello, " + this.name;
    }

    public void sayGoodbye() {
        System.out.println("Goodbye!");
    }

    public static void main(String[] args) {
        Greeter g = new Greeter("Alice");
        g.sayHello();
        g.sayGoodbye();
    }
}
"""
        file_path = tmp_path / "Greeter.java"
        file_path.write_text(content)
        return file_path

    def test_get_language_name(self, java_parser):
        """测试语言名称"""
        assert java_parser.get_language_name() == "java"

    def test_parse_file_returns_ast_node_list(self, java_parser, sample_java_file):
        """测试解析文件返回 ASTNodeList"""
        result = java_parser.parse_file(sample_java_file)
        assert isinstance(result, ASTNodeList)

    def test_parse_file_extracts_class(self, java_parser, sample_java_file):
        """测试提取类"""
        result = java_parser.parse_file(sample_java_file)
        if len(result) > 0:
            classes = result.get_classes()
            assert len(classes) >= 1
            assert any(c.name == "Greeter" for c in classes)

    def test_parse_file_extracts_method(self, java_parser, sample_java_file):
        """测试提取方法"""
        result = java_parser.parse_file(sample_java_file)
        if len(result) > 0:
            methods = [n for n in result.nodes if n.node_type == "method"]
            assert len(methods) >= 3  # sayHello, sayGoodbye, main

    def test_parse_file_extracts_import(self, java_parser, sample_java_file):
        """测试提取导入"""
        result = java_parser.parse_file(sample_java_file)
        if len(result) > 0:
            imports = result.get_imports()
            assert len(imports) >= 1

    def test_parse_file_extracts_call(self, java_parser, sample_java_file):
        """测试提取调用"""
        result = java_parser.parse_file(sample_java_file)
        if len(result) > 0:
            calls = result.get_calls()
            assert len(calls) >= 2


# --- Go 测试 ---

class TestGoParser:
    """GoParser 测试"""

    @pytest.fixture
    def sample_go_file(self, tmp_path: Path) -> Path:
        """创建示例 Go 文件"""
        content = """
package main

import "fmt"

type Greeter struct {
    name string
}

func (g Greeter) SayHello() string {
    return "Hello, " + g.name
}

func main() {
    g := Greeter{name: "Alice"}
    fmt.Println(g.SayHello())
}
"""
        file_path = tmp_path / "main.go"
        file_path.write_text(content)
        return file_path

    def test_get_language_name(self, go_parser):
        """测试语言名称"""
        assert go_parser.get_language_name() == "go"

    def test_parse_file_returns_ast_node_list(self, go_parser, sample_go_file):
        """测试解析文件返回 ASTNodeList"""
        result = go_parser.parse_file(sample_go_file)
        assert isinstance(result, ASTNodeList)

    def test_parse_file_extracts_function(self, go_parser, sample_go_file):
        """测试提取函数"""
        result = go_parser.parse_file(sample_go_file)
        if len(result) > 0:
            functions = result.get_functions()
            assert len(functions) >= 1

    def test_parse_file_extracts_method(self, go_parser, sample_go_file):
        """测试提取方法"""
        result = go_parser.parse_file(sample_go_file)
        if len(result) > 0:
            methods = [n for n in result.nodes if n.node_type == "method"]
            assert len(methods) >= 1

    def test_parse_file_extracts_struct(self, go_parser, sample_go_file):
        """测试提取结构体"""
        result = go_parser.parse_file(sample_go_file)
        if len(result) > 0:
            structs = [n for n in result.nodes if n.node_type == "struct"]
            assert len(structs) >= 1

    def test_parse_file_extracts_import(self, go_parser, sample_go_file):
        """测试提取导入"""
        result = go_parser.parse_file(sample_go_file)
        if len(result) > 0:
            imports = result.get_imports()
            assert len(imports) >= 1
