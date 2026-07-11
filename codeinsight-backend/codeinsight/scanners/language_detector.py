"""
文件语言检测器

通过文件扩展名映射到编程语言类型，用于 Tree-sitter 解析器选择。
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# 扩展名 → 语言名映射表
# 格式：.ext → "language_name"
# 优先级：第一个匹配生效
LANGUAGE_EXTENSIONS: dict[str, str] = {
    # Python
    ".py": "python",
    ".pyi": "python",

    # JavaScript / TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",

    # Java
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",

    # Go
    ".go": "go",

    # Rust
    ".rs": "rust",

    # C / C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",

    # C#
    ".cs": "csharp",

    # Ruby
    ".rb": "ruby",

    # PHP
    ".php": "php",

    # Swift
    ".swift": "swift",

    # 配置/数据文件（不解析 AST，但可记录）
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",

    # 文档（跳过）
    ".md": "markdown",
    ".txt": "text",
    ".rst": "rst",
}


class LanguageDetector:
    """
    文件语言检测器

    通过文件扩展名映射到编程语言类型。
    对于无法识别的文件，返回 "unknown"。
    """

    # 默认支持的语言（有 Tree-sitter 解析器的语言）
    DEFAULT_SUPPORTED_LANGUAGES = frozenset({
        "python", "javascript", "typescript", "java", "go",
        "rust", "c", "cpp", "csharp", "ruby", "php", "swift",
        "kotlin",
    })

    def __init__(self, supported_languages: frozenset[str] | None = None) -> None:
        """
        Args:
            supported_languages: 支持的语言集合，默认为 DEFAULT_SUPPORTED_LANGUAGES
        """
        self.supported = supported_languages or self.DEFAULT_SUPPORTED_LANGUAGES
        self.extensions = LANGUAGE_EXTENSIONS

    def detect(self, file_path: Path) -> str:
        """
        检测文件的语言类型

        Args:
            file_path: 文件路径

        Returns:
            语言名称（如 "python", "javascript"），未识别返回 "unknown"
        """
        ext = file_path.suffix.lower()
        return self.extensions.get(ext, "unknown")

    def is_supported(self, file_path: Path) -> bool:
        """
        检查文件是否为支持的语言

        Args:
            file_path: 文件路径

        Returns:
            True 如果文件语言在支持列表中
        """
        language = self.detect(file_path)
        return language in self.supported

    def is_source_file(self, file_path: Path) -> bool:
        """
        检查文件是否为源代码文件（排除文档、配置等）

        Args:
            file_path: 文件路径

        Returns:
            True 如果文件是源代码文件
        """
        language = self.detect(file_path)
        return language != "unknown" and language not in (
            "markdown", "text", "rst", "json", "yaml", "toml", "ini"
        )
