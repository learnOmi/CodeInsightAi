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

# 非源代码文件类型（S-8 修复：提取为常量）
NON_SOURCE_LANGUAGES: frozenset[str] = frozenset(
    {
        "markdown",
        "text",
        "rst",
        "json",
        "yaml",
        "toml",
        "ini",
    }
)


class LanguageDetector:
    """
    文件语言检测器

    通过文件扩展名映射到编程语言类型。
    对于无法识别的文件，返回 "unknown"。

    单例模式：LanguageDetector 的查找表从不变化，使用单例避免重复初始化。
    """

    _instance: "LanguageDetector | None" = None

    # 默认支持的语言（有 Tree-sitter 解析器的语言）
    DEFAULT_SUPPORTED_LANGUAGES = frozenset(
        {
            "python",
            "javascript",
            "typescript",
            "java",
            "go",
            "rust",
            "c",
            "cpp",
            "csharp",
            "ruby",
            "php",
            "swift",
            "kotlin",
        }
    )

    def __init__(self, supported_languages: frozenset[str] | None = None) -> None:
        """
        Args:
            supported_languages: 支持的语言集合，默认为 DEFAULT_SUPPORTED_LANGUAGES
        """
        self.supported = supported_languages or self.DEFAULT_SUPPORTED_LANGUAGES
        self.extensions = LANGUAGE_EXTENSIONS

    @classmethod
    def get_instance(cls) -> "LanguageDetector":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect(self, file_path: Path) -> str:
        """
        检测文件的语言类型

        Args:
            file_path: 文件路径

        Returns:
            语言名称（如 "python", "javascript"），未识别返回 "unknown"

        S-7 修复：处理双后缀文件（如 .pyc, .js.map）
        """
        ext = file_path.suffix.lower()

        if ext in self.extensions:
            return self.extensions[ext]

        if ext == ".h":
            stem = file_path.stem
            if stem.endswith(".inl") or stem.endswith(".ipp"):
                return "cpp"
            return "cpp"

        if ext == ".hpp":
            return "cpp"

        double_ext = file_path.suffixes
        if len(double_ext) >= 2:
            combined = "".join(double_ext[-2:]).lower()
            if combined in self.extensions:
                return self.extensions[combined]
            primary = double_ext[-2].lower()
            if primary in self.extensions:
                return self.extensions[primary]

        return "unknown"

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
        return language != "unknown" and language not in NON_SOURCE_LANGUAGES
