"""
语言解析器工厂

根据语言名称获取对应的解析器实例。
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import RLock
from typing import cast

from .base import ASTNodeList, LanguageParser

logger = logging.getLogger(__name__)

# 线程安全的解析器缓存
_parser_cache: dict[str, LanguageParser | None] = {}
_cache_lock = RLock()

# P-4 修复：不缓存 None，每次重新尝试创建
_CACHE_MISS = object()


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
        from .vue_parser import VueSfcParser

        parser_map = {
            "python": PythonParser,
            "typescript": TypeScriptParser,
            "javascript": JavaScriptParser,
            "java": JavaParser,
            "go": GoParser,
            "vue": VueSfcParser,
        }

        parser_class = parser_map.get(language)
        if parser_class is None:
            logger.warning("不支持的语言: %s", language)
            return None

        concrete_class = cast(type[LanguageParser], parser_class)
        return concrete_class()

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
        P-4 修复：使用 RLock 保证线程安全；不缓存 None（失败时不锁定，下次重试）。

        Args:
            language: 语言名称

        Returns:
            LanguageParser 实例或 None
        """
        with _cache_lock:
            if language in _parser_cache:
                return _parser_cache[language]

            parser = _create_parser_for_language(language)
            if parser is not None:
                _parser_cache[language] = parser
            # 不缓存 None：避免导入失败后永久返回 None
            return parser

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
