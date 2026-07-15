"""
JavaScript 语言解析器

使用 tree-sitter 0.26.0 API 解析 JavaScript 代码，提取函数、类、方法、调用、导入等节点。

注意：JavaScript 和 TypeScript 使用相似的 Tree-sitter 语法，
但解析器使用不同的 language 标识。
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
    from tree_sitter_javascript import language as javascript_language

    TREE_SITTER_AVAILABLE = True
except ImportError as exc:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter 不可用: %s", exc)
    Language = None  # type: ignore[assignment,misc]
    Parser = None  # type: ignore[assignment,misc]
    javascript_language = None  # type: ignore[assignment,misc]


def _node_text_to_str(node) -> str:
    """安全地将 tree-sitter 节点的 text 属性转换为字符串"""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    return cast(str, text.decode("utf-8"))


class JavaScriptParser(LanguageParser):
    """
    JavaScript 语言解析器

    提取的节点类型：
    - function: 函数声明
    - class: 类声明
    - method: 类中的方法
    - call: 函数调用
    - import: import 语句（ES6 module）
    """

    def __init__(self) -> None:
        if not TREE_SITTER_AVAILABLE:
            raise ImportError("tree-sitter 不可用，请安装 tree-sitter 和 tree-sitter-javascript")
        self._language = Language(javascript_language())
        self._parser = Parser(self._language)
        self._language_name = "javascript"

    def get_language_name(self) -> str:
        return self._language_name

    def _parse_file_impl(self, file_path: Path) -> ASTNodeList:
        """
        解析 JavaScript 文件

        Args:
            file_path: JavaScript 文件路径

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
            logger.error("解析 JavaScript 文件失败 %s: %s", file_path, exc)
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

        # 函数表达式 / 箭头函数：仅当能获取到名称时才提取（匿名回调跳过）
        elif node_type in ("function_expression", "arrow_function"):
            ast_node = self._create_function_node(node, file_path, language, parent_node)
            if ast_node.name:
                result.add(ast_node)
                self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 类声明
        elif node_type == "class_declaration":
            ast_node = self._create_class_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 导入语句
        elif node_type == "import_statement":
            self._extract_import_nodes(node, result, file_path, language, parent_node)

        # 调用表达式（P-10 修复：_extract_nodes 未处理，导致嵌套调用被跳过）
        elif node_type == "call_expression":
            call_node = self._create_call_node(node, file_path, language, parent_node)
            result.add(call_node)

        # 对象字面量：提取对象方法（Vue Options API、配置对象等）
        elif node_type in ("object", "object_literal"):
            self._extract_object_methods(node, result, file_path, language, parent_node)

        # 递归处理子节点
        for child in node.children:
            self._extract_nodes(child, result, file_path, language, parent_node)

    def _extract_object_methods(
        self,
        node,
        result: ASTNodeList,
        file_path: str,
        language: str,
        parent_node: ASTNode | None,
    ) -> None:
        """
        从 object/object_literal 节点中提取对象方法

        处理两种形式：
        1. method_definition 直接子节点（JS 简写方法: `{ foo() {} }`）
        2. pair 子节点（`{ key: function() {} }` 或 `{ key: () => {} }`）

        若 value 为嵌套对象则递归处理。
        """
        for child in node.children:
            # 1. 简写方法：method_definition 直接作为 object 的子节点
            if child.type == "method_definition":
                name_node = child.child_by_field_name("name")
                annotations = self._extract_annotations(child)
                obj_method = self._create_object_method_node(
                    node=child,
                    file_path=file_path,
                    language=language,
                    parent_node=parent_node,
                    key_node=name_node,
                )
                obj_method.annotations = annotations
                obj_method.qualified_name = self._compute_qualified_name(child, file_path, language, parent_node)
                result.add(obj_method)
                self._extract_nodes_from_node(child, result, file_path, language, obj_method)
            # 2. pair 形式：{ key: function/arrow }
            elif child.type == "pair":
                key_node = child.child_by_field_name("key")
                value_node = child.child_by_field_name("value")
                if value_node is None:
                    continue
                if self._is_function_node(value_node):
                    annotations = self._extract_annotations(child)
                    obj_method = self._create_object_method_node(
                        node=value_node,
                        file_path=file_path,
                        language=language,
                        parent_node=parent_node,
                        key_node=key_node,
                    )
                    obj_method.annotations = annotations
                    obj_method.qualified_name = self._compute_qualified_name(
                        value_node, file_path, language, parent_node
                    )
                    result.add(obj_method)
                    self._extract_nodes_from_node(value_node, result, file_path, language, obj_method)
                elif value_node.type in ("object", "object_literal"):
                    self._extract_object_methods(value_node, result, file_path, language, parent_node)

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
            for child in node.children:
                if child.type == "from_clause":
                    for sub in child.children:
                        if sub.type == "string" or sub.type == "string_literal":
                            return _node_text_to_str(sub).strip('"').strip("'")

            # 直接导入: import "module"
            for child in node.children:
                if child.type == "string" or child.type == "string_literal":
                    return _node_text_to_str(child).strip('"').strip("'")

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
        """创建函数节点

        对于匿名函数（箭头函数 / 函数表达式），尝试从父级 variable_declarator 获取名称，
        例如 `const Foo = () => {}` 或 `const Foo = function() {}` → name = "Foo"。
        """
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else ""

        # 匿名函数：尝试从父级变量声明中获取名称
        if not name and node.type in ("arrow_function", "function_expression"):
            ts_parent = node.parent
            if ts_parent is not None and ts_parent.type == "variable_declarator":
                name_child = ts_parent.child_by_field_name("name")
                if name_child:
                    name = name_child.text.decode("utf-8")

        annotations = self._extract_annotations(node)
        qualified_name = self._compute_qualified_name(node, file_path, language, parent_node)

        return ASTNode(
            node_type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
            annotations=annotations,
            qualified_name=qualified_name,
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
        annotations = self._extract_annotations(node)
        qualified_name = self._compute_qualified_name(node, file_path, language, parent_node)

        return ASTNode(
            node_type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
            annotations=annotations,
            qualified_name=qualified_name,
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
        annotations = self._extract_annotations(node)
        qualified_name = self._compute_qualified_name(node, file_path, language, parent_node)

        return ASTNode(
            node_type="class",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
            annotations=annotations,
            qualified_name=qualified_name,
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
                if func_node.type == "member_expression":
                    prop_node = func_node.child_by_field_name("property")
                    if prop_node:
                        return f"*.{_node_text_to_str(prop_node)}"
                return _node_text_to_str(func_node)
            return "unknown"
        except Exception:
            return "unknown"

    def _compute_qualified_name(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> str:
        """
        计算节点的模块限定名

        格式：
        - 方法：{module_name}:{ClassName}.{methodName}
        - 顶层函数：{module_name}:{functionName}

        Args:
            node: tree-sitter 节点
            file_path: 文件路径
            language: 语言名称
            parent_node: 父 ASTNode

        Returns:
            qualified_name 字符串
        """
        module_name = Path(file_path).stem

        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"

        if parent_node is not None and parent_node.node_type == "class":
            return f"{module_name}:{parent_node.name}.{name}"

        return f"{module_name}:{name}"
