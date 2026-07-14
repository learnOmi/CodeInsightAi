"""
Python 语言解析器

使用 tree-sitter 0.26.0 API 解析 Python 代码，提取函数、类、方法、调用、导入等节点。
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
    from tree_sitter_python import language as python_language

    TREE_SITTER_AVAILABLE = True
except ImportError as exc:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter 不可用: %s", exc)
    Language = None  # type: ignore[assignment,misc]
    Parser = None  # type: ignore[assignment,misc]
    python_language = None  # type: ignore[assignment,misc]


def _node_text_to_str(node) -> str:
    """安全地将 tree-sitter 节点的 text 属性转换为字符串"""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    return cast(str, text.decode("utf-8"))


class PythonParser(LanguageParser):
    """
    Python 语言解析器

    提取的节点类型：
    - function: 函数定义
    - class: 类定义
    - protocol: Protocol 接口定义（继承自 typing.Protocol）
    - enum: 枚举定义（继承自 enum.Enum）
    - method: 类中的方法
    - call: 函数调用
    - import: import 语句
    """

    def __init__(self) -> None:
        if not TREE_SITTER_AVAILABLE:
            raise ImportError("tree-sitter 不可用，请安装 tree-sitter 和 tree-sitter-python")
        self._language = Language(python_language())
        self._parser = Parser(self._language)
        self._language_name = "python"

    def get_language_name(self) -> str:
        return self._language_name

    def _parse_file_impl(self, file_path: Path) -> ASTNodeList:
        """
        解析 Python 文件

        Args:
            file_path: Python 文件路径

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
            logger.error("解析 Python 文件失败 %s: %s", file_path, exc)
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

        # 函数定义
        if node_type == "function_definition":
            ast_node = self._create_function_node(node, file_path, language, parent_node)
            result.add(ast_node)
            # 递归处理函数体
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 类定义
        elif node_type == "class_definition":
            # 检查是否为 Protocol
            if self._is_protocol(node):
                ast_node = self._create_protocol_node(node, file_path, language, parent_node)
                result.add(ast_node)
                self._extract_nodes_from_node(node, result, file_path, language, ast_node)
            # 检查是否为 Enum
            elif self._is_enum(node):
                ast_node = self._create_enum_node(node, file_path, language, parent_node)
                result.add(ast_node)
                self._extract_nodes_from_node(node, result, file_path, language, ast_node)
            else:
                ast_node = self._create_class_node(node, file_path, language, parent_node)
                result.add(ast_node)
                self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 导入语句
        elif node_type in ("import_statement", "import_from_statement"):
            ast_node = self._create_import_node(node, file_path, language, parent_node)
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

            # 在类中查找方法
            if parent_node.node_type == "class":
                if child_type == "function_definition":
                    method_node = self._create_method_node(child, file_path, language, parent_node)
                    result.add(method_node)
                    self._extract_nodes_from_node(child, result, file_path, language, method_node)
                elif child_type == "block":
                    # 遍历 block 中的所有方法定义（Python 使用 block 作为类体）
                    for body_child in child.children:
                        if body_child.type == "function_definition":
                            method_node = self._create_method_node(body_child, file_path, language, parent_node)
                            result.add(method_node)
                            self._extract_nodes_from_node(body_child, result, file_path, language, method_node)
            elif child_type == "call":
                call_node = self._create_call_node(child, file_path, language, parent_node)
                result.add(call_node)
            else:
                # 递归处理
                self._extract_nodes(child, result, file_path, language, parent_node)

    def _create_function_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建函数节点"""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"

        return ASTNode(
            node_type="function",
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
        parent_node: ASTNode,
    ) -> ASTNode:
        """创建方法节点（类中的函数）"""
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

    def _create_import_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建导入节点"""
        # 提取导入的模块名
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
            # import_statement: import module_name
            if node.type == "import_statement":
                name_node = node.child_by_field_name("module")
                if name_node:
                    return _node_text_to_str(name_node)

            # import_from_statement: from module import name
            elif node.type == "import_from_statement":
                module_node = node.child_by_field_name("module")
                if module_node:
                    return _node_text_to_str(module_node)

            return "unknown"
        except Exception:
            return "unknown"

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
        """从调用节点中提取被调用函数名"""
        try:
            # 简单调用: func()
            func_node = node.child_by_field_name("function")
            if func_node:
                # 方法调用: obj.method()
                if func_node.type == "attribute":
                    method_node = func_node.child_by_field_name("attribute")
                    if method_node:
                        return f"*.{_node_text_to_str(method_node)}"
                return _node_text_to_str(func_node)
            return "unknown"
        except Exception:
            return "unknown"

    def _is_protocol(self, node) -> bool:
        """检查类定义是否继承自 Protocol"""
        try:
            # 查找 superclasses 子节点
            superclasses_node = node.child_by_field_name("superclasses")
            if superclasses_node is None:
                return False
            # 遍历所有基类
            for child in superclasses_node.children:
                if child.type == "attribute":
                    # typing.Protocol 形式：检查 attribute 字段
                    attr_node = child.child_by_field_name("attribute")
                    if attr_node and _node_text_to_str(attr_node).strip() == "Protocol":
                        return True
                elif child.type == "identifier":
                    # 简单形式：直接写 Protocol
                    name = _node_text_to_str(child).strip()
                    if name == "Protocol":
                        return True
            return False
        except Exception:
            return False

    def _is_enum(self, node) -> bool:
        """检查类定义是否继承自 Enum"""
        try:
            superclasses_node = node.child_by_field_name("superclasses")
            if superclasses_node is None:
                return False
            for child in superclasses_node.children:
                if child.type == "attribute":
                    attr_node = child.child_by_field_name("attribute")
                    if attr_node and _node_text_to_str(attr_node).strip() == "Enum":
                        return True
                elif child.type == "identifier":
                    name = _node_text_to_str(child).strip()
                    if name == "Enum":
                        return True
            return False
        except Exception:
            return False

    def _create_protocol_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建 Protocol 节点"""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"

        return ASTNode(
            node_type="protocol",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )

    def _create_enum_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建 Enum 节点"""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"

        return ASTNode(
            node_type="enum",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
        )
