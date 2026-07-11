"""
语言解析器工厂

根据语言名称获取对应的解析器实例。
"""

from __future__ import annotations

import logging
from pathlib import Path

from .base import ASTNodeList, LanguageParser

logger = logging.getLogger(__name__)

# 解析器缓存
_parser_cache: dict[str, LanguageParser | None] = {}


def _create_parser_for_language(language: str) -> LanguageParser | None:
    """
    根据语言名称创建解析器实例

    Args:
        language: 语言名称 (python, typescript, javascript, java, go)

    Returns:
        对应语言的 LanguageParser 实例，或 None（不支持的语言）
    """
    try:
        from .go_parser import GoParser
        from .java_parser import JavaParser
        from .javascript_parser import JavaScriptParser
        from .python_parser import PythonParser
        from .typescript_parser import TypeScriptParser

        parser_map = {
            "python": PythonParser,
            "typescript": TypeScriptParser,
            "javascript": JavaScriptParser,
            "java": JavaParser,
            "go": GoParser,
        }

        parser_class = parser_map.get(language)
        if parser_class is None:
            logger.warning("不支持的语言: %s", language)
            return None

        return parser_class()  # type: ignore[abstract]

    except ImportError as exc:
        logger.error("无法导入解析器: %s", exc)
        return None


class ParserFactory:
    """
    解析器工厂类

    使用示例：
        parser = ParserFactory.get_parser("python")
        if parser:
            ast = parser.parse_file("path/to/file.py")
    """

    @staticmethod
    def get_parser(language: str) -> LanguageParser | None:
        """
        获取指定语言的解析器

        使用缓存避免重复创建解析器实例。

        Args:
            language: 语言名称

        Returns:
            LanguageParser 实例或 None
        """
        if language not in _parser_cache:
            _parser_cache[language] = _create_parser_for_language(language)
        return _parser_cache[language]

    @staticmethod
    def parse_file(
        language: str,
        file_path: Path | str,
    ) -> ASTNodeList:
        """
        解析文件的便捷方法

        自动获取对应语言的解析器并解析文件。

        Args:
            language: 语言名称
            file_path: 文件路径

        Returns:
            ASTNodeList 包含所有提取的节点
        """
        parser = ParserFactory.get_parser(language)
        if parser is None:
            logger.warning("跳过不支持的语言: %s (文件: %s)", language, file_path)
            return ASTNodeList()
        return parser.parse_file(file_path)
