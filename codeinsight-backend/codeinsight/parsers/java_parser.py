"""
Java 语言解析器

使用 tree-sitter 0.26.0 API 解析 Java 代码，提取类、方法、调用、导入等节点。

Java 的特殊性：
- 所有代码必须在类中定义
- 方法通过 `method_declaration` 节点表示
- 调用通过 `method_invocation` 节点表示
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from .base import ASTNode, ASTNodeList, LanguageParser

logger = logging.getLogger(__name__)

TREE_SITTER_AVAILABLE = False

try:
    from tree_sitter import Language, Parser
    from tree_sitter_java import language as java_language

    TREE_SITTER_AVAILABLE = True
except ImportError as exc:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter 不可用: %s", exc)
    Language = None  # type: ignore[assignment,misc]
    Parser = None  # type: ignore[assignment,misc]
    java_language = None  # type: ignore[assignment,misc]


def _node_text_to_str(node) -> str:
    """安全地将 tree-sitter 节点的 text 属性转换为字符串"""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    return cast(str, text.decode("utf-8"))


class JavaParser(LanguageParser):
    """
    Java 语言解析器

    提取的节点类型：
    - class: 类定义
    - interface: 接口定义
    - method: 类/接口中的方法
    - call: 方法调用
    - import: import 语句
    """

    def __init__(self) -> None:
        if not TREE_SITTER_AVAILABLE:
            raise ImportError("tree-sitter 不可用，请安装 tree-sitter 和 tree-sitter-java")
        self._language = Language(java_language())
        self._parser = Parser(self._language)
        self._language_name = "java"

    def get_language_name(self) -> str:
        return self._language_name

    def _parse_file_impl(self, file_path: Path) -> ASTNodeList:
        """
        解析 Java 文件

        Args:
            file_path: Java 文件路径

        Returns:
            ASTNodeList 包含所有提取的节点
        """
        try:
            if not file_path.exists():
                logger.warning("文件不存在: %s", file_path)
                return ASTNodeList()

            content = file_path.read_bytes()
            tree = self._parser.parse(content)
            root_node = tree.root_node

            nodes = ASTNodeList()
            self._extract_nodes(root_node, nodes, str(file_path), self._language_name)

            return nodes

        except Exception as exc:
            logger.error("解析 Java 文件失败 %s: %s", file_path, exc)
            return ASTNodeList()

    def _extract_nodes(
        self,
        node,
        result: ASTNodeList,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> None:
        """
        递归提取 AST 节点
        """
        node_type = node.type

        # 类定义
        if node_type == "class_declaration":
            ast_node = self._create_class_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 接口定义
        elif node_type == "interface_declaration":
            ast_node = self._create_interface_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 方法声明
        elif node_type == "method_declaration":
            ast_node = self._create_method_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 方法调用
        elif node_type == "method_invocation":
            ast_node = self._create_call_node(node, file_path, language, parent_node)
            result.add(ast_node)

        # 导入语句
        elif node_type == "import_declaration":
            ast_node = self._create_import_node(node, file_path, language, parent_node)
            result.add(ast_node)

        # 构造器
        elif node_type == "constructor_declaration":
            ast_node = self._create_constructor_node(node, file_path, language, parent_node)
            result.add(ast_node)

        # 递归处理子节点
        for child in node.children:
            self._extract_nodes(child, result, file_path, language, parent_node)

    def _extract_nodes_from_node(
        self,
        node,
        result: ASTNodeList,
        file_path: str,
        language: str,
        parent_node: ASTNode,
    ) -> None:
        """
        从节点中提取子节点
        """
        for child in node.children:
            child_type = child.type

            # 方法调用
            if child_type == "method_invocation":
                call_node = self._create_call_node(child, file_path, language, parent_node)
                result.add(call_node)
            # 嵌套类
            elif child_type == "class_declaration":
                class_node = self._create_class_node(child, file_path, language, parent_node)
                result.add(class_node)
                self._extract_nodes_from_node(child, result, file_path, language, class_node)
            # 嵌套接口
            elif child_type == "interface_declaration":
                interface_node = self._create_interface_node(child, file_path, language, parent_node)
                result.add(interface_node)
                self._extract_nodes_from_node(child, result, file_path, language, interface_node)
            # 在接口中查找方法
            elif parent_node.node_type == "interface":
                if child_type == "method_declaration":
                    method_node = self._create_method_node(child, file_path, language, parent_node)
                    result.add(method_node)
                elif child_type == "class_body":
                    for body_child in child.children:
                        if body_child.type == "method_declaration":
                            method_node = self._create_method_node(body_child, file_path, language, parent_node)
                            result.add(method_node)
            else:
                self._extract_nodes(child, result, file_path, language, parent_node)

    def _create_class_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建类节点"""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"

        return ASTNode(
            node_type="class",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )

    def _create_method_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建方法节点"""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"

        return ASTNode(
            node_type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )

    def _create_constructor_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建构造器节点"""
        name_node = node.child_by_field_name("name")
        name = f"{name_node.text.decode('utf-8')}.<init>" if name_node else "unknown.<init>"

        return ASTNode(
            node_type="constructor",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )

    def _create_call_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建调用节点"""
        name = self._extract_call_name(node)

        return ASTNode(
            node_type="call",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )

    def _extract_call_name(self, node) -> str:
        """从调用节点中提取被调用方法名"""
        try:
            # method_invocation: obj.method() 或 method()
            name_node = node.child_by_field_name("name")
            if name_node:
                return _node_text_to_str(name_node)
            return "unknown"
        except Exception:
            return "unknown"

    def _create_import_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建导入节点"""
        name = self._extract_import_name(node)

        return ASTNode(
            node_type="import",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )

    def _extract_import_name(self, node) -> str:
        """从导入节点中提取模块名"""
        try:
            # import_declaration: import com.example.Class;
            name_node = node.child_by_field_name("name")
            if name_node:
                return _node_text_to_str(name_node)
            return "unknown"
        except Exception:
            return "unknown"

    def _create_interface_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建接口节点"""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"

        return ASTNode(
            node_type="interface",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )
