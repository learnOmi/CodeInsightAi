"""
TypeScript 语言解析器

使用 tree-sitter 0.26.0 API 解析 TypeScript 代码，提取函数、类、方法、调用、导入等节点。
"""

from __future__ import annotations

import logging
from pathlib import Path

from .base import ASTNode, ASTNodeList, LanguageParser

logger = logging.getLogger(__name__)

TREE_SITTER_AVAILABLE = False
_import_error = None

try:
    from tree_sitter import Language, Parser
    from tree_sitter_typescript import language_typescript as typescript_language

    TREE_SITTER_AVAILABLE = True
    logger.info("tree-sitter-typescript 导入成功")
except ImportError as exc:
    TREE_SITTER_AVAILABLE = False
    _import_error = exc
    logger.error("tree-sitter-typescript 导入失败: %s", exc)
    Language = None  # type: ignore
    Parser = None  # type: ignore
    typescript_language = None  # type: ignore[assignment,misc]


class TypeScriptParser(LanguageParser):
    """
    TypeScript 语言解析器

    提取的节点类型：
    - function: 函数声明
    - class: 类声明
    - method: 类中的方法
    - call: 函数调用
    - import: import 语句
    """

    def __init__(self) -> None:
        if not TREE_SITTER_AVAILABLE:
            raise ImportError(
                f"tree-sitter 不可用，请安装 tree-sitter 和 tree-sitter-typescript. Error: {_import_error}"
            )
        self._language = Language(typescript_language())
        self._parser = Parser(self._language)
        self._language_name = "typescript"

    def get_language_name(self) -> str:
        return self._language_name

    def parse_file(self, file_path: Path | str) -> ASTNodeList:
        """
        解析 TypeScript 文件

        Args:
            file_path: TypeScript 文件路径

        Returns:
            ASTNodeList 包含所有提取的节点
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning("文件不存在: %s", path)
                return ASTNodeList()

            content = path.read_bytes()
            tree = self._parser.parse(content)
            root_node = tree.root_node

            nodes = ASTNodeList()
            self._extract_nodes(root_node, nodes, str(path), self._language_name)

            return nodes

        except Exception as exc:
            logger.error("解析 TypeScript 文件失败 %s: %s", file_path, exc)
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

        # 函数声明: function name() { }
        if node_type == "function_declaration":
            ast_node = self._create_function_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 箭头函数
        elif node_type == "arrow_function":
            # 箭头函数通常是表达式，不提取为顶级函数
            pass

        # 类声明
        elif node_type == "class_declaration":
            ast_node = self._create_class_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 导入语句
        elif node_type in ("import_statement", "import_specifier", "named_imports"):
            # import_statement 可能包含多个 import_specifier
            if node_type == "import_statement":
                self._extract_import_nodes(node, result, file_path, language, parent_node)

        # 函数调用
        elif node_type == "call_expression":
            ast_node = self._create_call_node(node, file_path, language, parent_node)
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
                if child_type == "method_definition":
                    method_node = self._create_method_node(child, file_path, language, parent_node)
                    result.add(method_node)
                    self._extract_nodes_from_node(child, result, file_path, language, method_node)
                elif child_type == "class_body":
                    # 遍历 class_body 中的所有方法定义
                    for body_child in child.children:
                        if body_child.type == "method_definition":
                            method_node = self._create_method_node(body_child, file_path, language, parent_node)
                            result.add(method_node)
                            self._extract_nodes_from_node(body_child, result, file_path, language, method_node)
            elif child_type == "call_expression":
                call_node = self._create_call_node(child, file_path, language, parent_node)
                result.add(call_node)
            else:
                self._extract_nodes(child, result, file_path, language, parent_node)

    def _extract_import_nodes(
        self,
        node,
        result: ASTNodeList,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> None:
        """从 import_statement 中提取导入节点"""
        name = self._extract_import_name(node)
        if name and name != "unknown":
            ast_node = ASTNode(
                node_type="import",
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
                language=language,
                file_path=file_path,
            )
            result.add(ast_node)

    def _extract_import_name(self, node) -> str:
        """从导入节点中提取模块名"""
        try:
            # import_statement: import { X } from "module"
            # 查找 "from_clause" 子节点
            for child in node.children:
                if child.type == "from_clause":
                    # from_clause 包含字符串字面量
                    for sub in child.children:
                        if sub.type == "string" or sub.type == "string_literal":
                            return str(sub.text.decode("utf-8")).strip('"').strip("'")  # type: ignore[union-attr]

            # 直接导入: import "module"
            for child in node.children:
                if child.type == "string" or child.type == "string_literal":
                    return str(child.text.decode("utf-8")).strip('"').strip("'")  # type: ignore[union-attr]

            return "unknown"
        except Exception:
            return "unknown"

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
                if func_node.type == "member_access_expression":
                    prop_node = func_node.child_by_field_name("property")
                    if prop_node:
                        return f"*. {str(prop_node.text.decode('utf-8'))}"  # type: ignore[union-attr]
                return str(func_node.text.decode("utf-8"))  # type: ignore[union-attr]
            return "unknown"
        except Exception:
            return "unknown"
