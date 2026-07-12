"""
LanguageParser 抽象基类

定义了解析器接口和 ASTNode 数据结构。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ASTNode:
    """
    AST 节点，表示语法树中的一个元素

    Attributes:
        node_type: 节点类型 (function, class, method, call, import, variable)
        name: 节点名称 (函数名/类名)
        start_line: 起始行 (1-indexed)
        end_line: 结束行 (1-indexed)
        start_column: 起始列 (1-indexed)
        end_column: 结束列 (1-indexed)
        children: 子节点列表
        parent: 父节点
        language: 源文件语言
        file_path: 源文件路径
    """

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

    def add_child(self, child: ASTNode) -> None:
        """添加子节点"""
        child.parent = self
        self.children.append(child)

    def get_functions(self) -> list[ASTNode]:
        """获取所有函数节点（包括方法）"""
        result: list[ASTNode] = []
        if self.node_type in ("function", "method"):
            result.append(self)
        for child in self.children:
            result.extend(child.get_functions())
        return result

    def get_classes(self) -> list[ASTNode]:
        """获取所有类节点"""
        result: list[ASTNode] = []
        if self.node_type == "class":
            result.append(self)
        for child in self.children:
            result.extend(child.get_classes())
        return result

    def get_calls(self) -> list[ASTNode]:
        """获取所有调用节点"""
        result: list[ASTNode] = []
        if self.node_type == "call":
            result.append(self)
        for child in self.children:
            result.extend(child.get_calls())
        return result

    def get_imports(self) -> list[ASTNode]:
        """获取所有导入节点"""
        result: list[ASTNode] = []
        if self.node_type == "import":
            result.append(self)
        for child in self.children:
            result.extend(child.get_imports())
        return result

    def to_dict(self) -> dict:
        """转为字典格式"""
        return {
            "node_type": self.node_type,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_column": self.start_column,
            "end_column": self.end_column,
            "language": self.language,
            "file_path": self.file_path,
            "children_count": len(self.children),
        }


class ASTNodeList:
    """
    AST 节点列表，支持便捷查询
    """

    def __init__(self, nodes: list[ASTNode] | None = None) -> None:
        self.nodes = nodes or []

    def add(self, node: ASTNode) -> None:
        """添加节点"""
        self.nodes.append(node)

    def add_all(self, nodes: ASTNodeList) -> None:
        """批量添加节点"""
        self.nodes.extend(nodes.nodes)

    def get_functions(self) -> list[ASTNode]:
        """获取所有函数"""
        return [node for node in self.nodes if node.node_type in ("function", "method")]

    def get_classes(self) -> list[ASTNode]:
        """获取所有类"""
        return [node for node in self.nodes if node.node_type == "class"]

    def get_calls(self) -> list[ASTNode]:
        """获取所有调用"""
        return [node for node in self.nodes if node.node_type == "call"]

    def get_imports(self) -> list[ASTNode]:
        """获取所有导入"""
        return [node for node in self.nodes if node.node_type == "import"]

    def get_interfaces(self) -> list[ASTNode]:
        """获取所有接口"""
        return [node for node in self.nodes if node.node_type == "interface"]

    def get_protocols(self) -> list[ASTNode]:
        """获取所有 Protocol"""
        return [node for node in self.nodes if node.node_type == "protocol"]

    def get_enums(self) -> list[ASTNode]:
        """获取所有枚举"""
        return [node for node in self.nodes if node.node_type == "enum"]

    def __iter__(self):
        return iter(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)


class LanguageParser(ABC):
    """
    语言解析器抽象基类

    所有具体语言解析器必须继承此类并实现 parse_file() 方法。
    """

    # ============================================================
    # 通用配置：子类覆盖这些常量而非复制方法
    # ============================================================

    #: tree-sitter 节点类型 → ASTNode.node_type 映射
    NODE_TYPE_MAP: dict[str, str] = {}

    #: 节点类型 → 名称提取方法名
    NAME_FIELD_MAP: dict[str, str] = {}

    # ============================================================
    # 通用辅助方法（消除 5 个 parser 间 ~80% 重复）
    # ============================================================

    @staticmethod
    def _create_node(
        node_type: str,
        name: str,
        start_line: int,
        end_line: int,
        start_column: int,
        end_column: int,
        file_path: str,
        language: str,
    ) -> ASTNode:
        """
        通用节点创建方法

        各 parser 只需调用此方法而非重复构造 ASTNode，
        将 ~80% 重复代码消除到 base.py。
        """
        return ASTNode(
            node_type=node_type,
            name=name,
            start_line=start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
            file_path=file_path,
            language=language,
        )

    def _extract_call_name(self, node_name: str | None) -> str:
        """
        通用调用名提取

        各 parser 只需传入 tree-sitter 节点，返回标准化调用名。
        动态调用（getattr 等）标记为 "dynamic"。
        """
        if not node_name:
            return ""

        # 方法调用：obj.method → obj.method
        if "." in node_name and not node_name.startswith("."):
            return f"*.{node_name.split('.', 1)[1]}"

        # 构造函数：new ClassName → new ClassName
        if node_name.startswith("new "):
            return node_name

        # 精确调用：function_name
        return node_name

    def _normalize_import_name(self, raw_name: str | None) -> str:
        """
        通用导入名标准化（base.py 版本，各 parser 可根据需要覆盖）

        处理引号去除、别名提取等。
        注意：各 parser 有自己独立的 `_extract_import_name(node)` 方法，
        此方法仅为 base.py 提供的辅助实现，不会覆盖子类签名。
        """
        if not raw_name:
            return ""

        # 去除常见引号包裹（JS/TS import）
        import_name = raw_name.strip("\"'")

        # 处理别名：from X import Y as Z
        if " as " in import_name:
            import_name = import_name.split(" as ")[-1].strip()

        return import_name

    # ============================================================
    # 抽象接口
    # ============================================================

    @abstractmethod
    def parse_file(self, file_path: Path | str) -> ASTNodeList:
        """
        解析文件，返回 AST 节点列表

        Args:
            file_path: 文件路径

        Returns:
            ASTNodeList 包含所有提取的节点
        """

    @abstractmethod
    def get_language_name(self) -> str:
        """返回语言名称"""

    def get_supported_node_types(self) -> set[str]:
        """
        返回支持的节点类型

        默认返回常用类型，子类可覆盖以添加特定类型。
        """
        return {
            "function",
            "class",
            "method",
            "call",
            "import",
            "variable",
            "interface",
            "protocol",
            "enum",
            "type",
            "struct",
            "constructor",
        }
