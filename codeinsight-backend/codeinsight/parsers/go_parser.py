"""
Go 语言解析器

使用 tree-sitter 0.26.0 API 解析 Go 代码，提取函数、方法、结构体、调用、导入等节点。

Go 的特殊性：
- 函数可以是独立的（不在结构体中）
- 方法通过 `method_declaration` 节点表示
- 结构体通过 `type_spec` + `struct_type` 节点表示
- 调用通过 `call_expression` 节点表示
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
    from tree_sitter_go import language as go_language

    TREE_SITTER_AVAILABLE = True
except ImportError as exc:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter 不可用: %s", exc)
    Language = None  # type: ignore[assignment,misc]
    Parser = None  # type: ignore[assignment,misc]
    go_language = None  # type: ignore[assignment,misc]


def _node_text_to_str(node) -> str:
    """安全地将 tree-sitter 节点的 text 属性转换为字符串"""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    return cast(str, text.decode("utf-8"))


class GoParser(LanguageParser):
    """
    Go 语言解析器

    提取的节点类型：
    - function: 函数声明
    - struct: 结构体定义
    - method: 结构体的方法
    - call: 函数调用
    - import: import 语句
    """

    def __init__(self) -> None:
        if not TREE_SITTER_AVAILABLE:
            raise ImportError("tree-sitter 不可用，请安装 tree-sitter 和 tree-sitter-go")
        self._language = Language(go_language())
        self._parser = Parser(self._language)
        self._language_name = "go"

    def get_language_name(self) -> str:
        return self._language_name

    def _parse_file_impl(self, file_path: Path) -> ASTNodeList:
        """
        解析 Go 文件

        Args:
            file_path: Go 文件路径

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
            logger.error("解析 Go 文件失败 %s: %s", file_path, exc)
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

        # 函数声明: func name() { }
        if node_type == "function_declaration":
            ast_node = self._create_function_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 方法声明: func (r ReceiverType) MethodName()
        elif node_type == "method_declaration":
            ast_node = self._create_method_node(node, file_path, language, parent_node)
            result.add(ast_node)
            self._extract_nodes_from_node(node, result, file_path, language, ast_node)

        # 结构体类型: type Name struct { }
        elif node_type == "type_spec" and any(child.type == "struct_type" for child in node.children):
            ast_node = self._create_struct_node(node, file_path, language, parent_node)
            result.add(ast_node)

        # 导入语句 (P-7 修复：处理 import_declaration，避免重复计数)
        elif node_type == "import_declaration":
            for child in node.children:
                if child.type == "import_spec":
                    ast_node = self._create_import_node(child, file_path, language, parent_node)
                    result.add(ast_node)

        # 函数调用（P-10 修复：_extract_nodes 未处理，导致嵌套调用被跳过）
        elif node_type == "call_expression":
            call_node = self._create_call_node(node, file_path, language, parent_node)
            result.add(call_node)

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

            # 方法声明
            if child_type == "method_declaration":
                method_node = self._create_method_node(child, file_path, language, parent_node)
                result.add(method_node)
                self._extract_nodes_from_node(child, result, file_path, language, method_node)
            elif child_type == "call_expression":
                call_node = self._create_call_node(child, file_path, language, parent_node)
                result.add(call_node)
            else:
                self._extract_nodes(child, result, file_path, language, parent_node)

    def _extract_receiver_type(self, node) -> str:
        """
        从 method_declaration 节点中提取接收者类型名称

        Go 的 receiver 语法: func (s *Server) MethodName()
        解析 parameter_list -> parameter_declaration -> type 获取类型名

        Args:
            node: tree-sitter method_declaration 节点

        Returns:
            接收者类型名称，如 "Server"；若解析失败则返回 "unknown"
        """
        receiver_node = node.child_by_field_name("receiver")
        if receiver_node is None:
            return "unknown"
        # receiver 是 parameter_list，其子节点包含 parameter_declaration
        for child in receiver_node.children:
            if child.type == "parameter_declaration":
                type_node = child.child_by_field_name("type")
                if type_node is not None:
                    return self._node_text_to_str(type_node).lstrip("*")
        return "unknown"

    def _compute_qualified_name(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> str:
        """
        计算 Go 节点的模块限定名

        Go 格式：
        - 函数: {package_path}:{FunctionName}
        - 方法: {package_path}:{ReceiverType}.{MethodName}
        - 结构体: {package_path}:{StructName}

        package_path 从文件路径派生，使用文件名（不含扩展名）作为包标识符。

        Args:
            node: tree-sitter 节点
            file_path: 文件路径
            language: 语言名称
            parent_node: 父 ASTNode

        Returns:
            qualified_name 字符串
        """
        package_path = Path(file_path).stem
        node_type = node.type

        if node_type == "function_declaration":
            name_node = node.child_by_field_name("name")
            func_name = self._node_text_to_str(name_node) if name_node else "unknown"
            return f"{package_path}:{func_name}"

        if node_type == "method_declaration":
            receiver_type = self._extract_receiver_type(node)
            name_node = node.child_by_field_name("name")
            method_name = self._node_text_to_str(name_node) if name_node else "unknown"
            return f"{package_path}:{receiver_type}.{method_name}"

        if node_type == "type_spec":
            name_node = node.child_by_field_name("name")
            struct_name = self._node_text_to_str(name_node) if name_node else "unknown"
            return f"{package_path}:{struct_name}"

        return ""

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
            qualified_name=qualified_name,
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
            qualified_name=qualified_name,
        )

    def _create_struct_node(
        self,
        node,
        file_path: str,
        language: str,
        parent_node: ASTNode | None = None,
    ) -> ASTNode:
        """创建结构体节点"""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"
        qualified_name = self._compute_qualified_name(node, file_path, language, parent_node)

        return ASTNode(
            node_type="struct",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1] + 1,
            end_column=node.end_point[1] + 1,
            language=language,
            file_path=file_path,
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
                # 方法调用: obj.Method()
                if func_node.type == "selector_expression":
                    # selector_expression 包含两个字段：scope 和 name
                    name_node = func_node.child_by_field_name("name")
                    if name_node:
                        return f"*.{_node_text_to_str(name_node)}"
                return _node_text_to_str(func_node)
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
        """从导入节点中提取包名"""
        try:
            # 有别名导入：import f "fmt"
            name_node = node.child_by_field_name("name")
            if name_node:
                text = _node_text_to_str(name_node)
                return text.strip('"').strip("'")

            # 普通导入：import "fmt"（使用 path 字段）
            path_node = node.child_by_field_name("path")
            if path_node:
                return _node_text_to_str(path_node).strip('"').strip("'")

            return "unknown"
        except Exception:
            return "unknown"
