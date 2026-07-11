"""
PythonParser 单元测试
"""

from pathlib import Path

import pytest

from codeinsight.parsers.base import ASTNode, ASTNodeList
from codeinsight.parsers.python_parser import PythonParser


@pytest.fixture
def python_parser():
    """创建 Python 解析器实例"""
    return PythonParser()


@pytest.fixture
def sample_python_file(tmp_path: Path) -> Path:
    """创建示例 Python 文件"""
    content = """
def greet(name):
    print(f"Hello, {name}")

class Greeter:
    def __init__(self, name):
        self.name = name

    def say_hello(self):
        print(f"Hello, I'm {self.name}")

    def say_goodbye(self):
        print("Goodbye!")

# 使用
g = Greeter("Alice")
g.say_hello()
g.say_goodbye()

import os
from pathlib import Path
"""
    file_path = tmp_path / "test.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_python_imports_file(tmp_path: Path) -> Path:
    """创建仅包含导入的 Python 文件"""
    content = """
import os
import sys
from pathlib import Path
from collections import defaultdict
"""
    file_path = tmp_path / "imports.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_python_calls_file(tmp_path: Path) -> Path:
    """创建包含各种调用的 Python 文件"""
    content = """
import os
import json

def process_data(data):
    return json.dumps(data)

def main():
    data = {"key": "value"}
    result = process_data(data)
    os.path.join("path", "file")
    print(result)

if __name__ == "__main__":
    main()
"""
    file_path = tmp_path / "calls.py"
    file_path.write_text(content)
    return file_path


class TestPythonParser:
    """PythonParser 测试"""

    def test_get_language_name(self, python_parser):
        """测试语言名称"""
        assert python_parser.get_language_name() == "python"

    def test_parse_file_returns_ast_node_list(self, python_parser, sample_python_file):
        """测试解析文件返回 ASTNodeList"""
        result = python_parser.parse_file(sample_python_file)
        assert isinstance(result, ASTNodeList)
        assert len(result) > 0

    def test_parse_file_extracts_functions(self, python_parser, sample_python_file):
        """测试提取函数"""
        result = python_parser.parse_file(sample_python_file)
        functions = result.get_functions()
        assert len(functions) >= 2  # greet 和 main（如果有的话）

    def test_parse_file_extracts_class(self, python_parser, sample_python_file):
        """测试提取类"""
        result = python_parser.parse_file(sample_python_file)
        classes = result.get_classes()
        assert len(classes) >= 1
        assert any(cls.name == "Greeter" for cls in classes)

    def test_parse_file_extracts_methods(self, python_parser, sample_python_file):
        """测试提取方法"""
        result = python_parser.parse_file(sample_python_file)
        methods = [n for n in result.nodes if n.node_type == "method"]
        assert len(methods) >= 2  # __init__, say_hello, say_goodbye

    def test_parse_file_extracts_imports(self, python_parser, sample_python_imports_file):
        """测试提取导入"""
        result = python_parser.parse_file(sample_python_imports_file)
        imports = result.get_imports()
        assert len(imports) >= 4

    def test_parse_file_extracts_calls(self, python_parser, sample_python_calls_file):
        """测试提取调用"""
        result = python_parser.parse_file(sample_python_calls_file)
        calls = result.get_calls()
        assert len(calls) >= 3  # process_data, os.path.join, print

    def test_parse_file_with_nonexistent_file(self, python_parser, tmp_path):
        """测试解析不存在的文件"""
        nonexistent = tmp_path / "nonexistent.py"
        result = python_parser.parse_file(nonexistent)
        # 应该返回空列表，不抛出异常
        assert isinstance(result, ASTNodeList)
        assert len(result) == 0

    def test_parse_file_with_invalid_syntax(self, python_parser, tmp_path):
        """测试解析语法错误的文件"""
        invalid = tmp_path / "invalid.py"
        invalid.write_text("def broken")
        result = python_parser.parse_file(invalid)
        # 应该返回空列表，不抛出异常
        assert isinstance(result, ASTNodeList)

    def test_ast_node_creation(self):
        """测试 ASTNode 创建"""
        node = ASTNode(
            node_type="function",
            name="test_func",
            start_line=1,
            end_line=5,
            start_column=0,
            end_column=10,
            language="python",
            file_path="/path/to/file.py",
        )
        assert node.node_type == "function"
        assert node.name == "test_func"
        assert len(node.children) == 0

    def test_ast_node_add_child(self):
        """测试 ASTNode 添加子节点"""
        parent = ASTNode(
            node_type="function",
            name="parent",
            start_line=1,
            end_line=10,
            start_column=0,
            end_column=10,
        )
        child = ASTNode(
            node_type="call",
            name="child_call",
            start_line=5,
            end_line=5,
            start_column=4,
            end_column=10,
        )
        parent.add_child(child)
        assert len(parent.children) == 1
        assert child.parent == parent

    def test_ast_node_list_operations(self):
        """测试 ASTNodeList 操作"""
        node_list = ASTNodeList()
        node1 = ASTNode("function", "func1", 1, 5, 0, 10)
        node2 = ASTNode("class", "Class1", 10, 20, 0, 10)
        node3 = ASTNode("call", "call1", 15, 15, 4, 10)

        node_list.add(node1)
        node_list.add(node2)
        node_list.add(node3)

        assert len(node_list) == 3
        assert len(node_list.get_functions()) == 1
        assert len(node_list.get_classes()) == 1
        assert len(node_list.get_calls()) == 1

    def test_ast_node_to_dict(self):
        """测试 ASTNode 转为字典"""
        node = ASTNode(
            node_type="function",
            name="test",
            start_line=1,
            end_line=5,
            start_column=0,
            end_column=10,
            language="python",
            file_path="/path/to/file.py",
        )
        node_dict = node.to_dict()
        assert node_dict["node_type"] == "function"
        assert node_dict["name"] == "test"
        assert node_dict["children_count"] == 0
