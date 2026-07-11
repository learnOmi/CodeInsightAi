"""
Git 仓库扫描器

使用 GitPython 打开 Git 仓库，递归收集源代码文件，支持 .gitignore 过滤。
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import git

logger = logging.getLogger(__name__)


@dataclass
class ScannedFile:
    """扫描到的文件信息"""

    path: str  # 仓库内相对路径
    absolute_path: str  # 绝对路径
    language: str  # 语言类型
    line_count: int  # 代码行数
    size_bytes: int  # 文件大小
    content_hash: str  # 内容 SHA-256 hash

    @classmethod
    def from_path(
        cls,
        file_path: Path,
        repo_path: Path,
        language: str = "unknown",
        max_line_count: int = 10000,
    ) -> "ScannedFile | None":
        """
        从文件路径创建 ScannedFile 实例

        使用流式分块读取，始终控制内存占用（最大 ~64KB 缓冲）。

        Args:
            file_path: 文件绝对路径
            repo_path: 仓库根路径
            language: 语言类型
            max_line_count: 最大行数限制，超过则返回 None

        Returns:
            ScannedFile 实例或 None（文件过大、行数过多或无法读取）
        """
        try:
            # 先检查文件大小，无需加载到内存
            size_bytes = file_path.stat().st_size

            # 跳过过大文件（>10MB）
            if size_bytes > 10 * 1024 * 1024:
                logger.debug("跳过过大文件: %s (%.1fMB)", file_path, size_bytes / (1024 * 1024))
                return None

            # 分块读取，计算 hash + 统计行数
            _buffer_size = 64 * 1024  # 64KB 分块，控制内存占用
            sha = hashlib.sha256()
            line_count = 0
            partial_line = 0  # 记录前一个 chunk 末尾不完整的行数

            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(_buffer_size)
                    if not chunk:
                        break
                    sha.update(chunk)
                    line_count += chunk.count(b"\n")
                    if not chunk.endswith(b"\n"):
                        partial_line = 1

            # 文件不以换行结尾时补 1 行
            if size_bytes > 0 and partial_line:
                line_count += 1

            content_hash = sha.hexdigest()

            # 行数超过限制，跳过
            if line_count > max_line_count:
                logger.debug("跳过行数过多文件: %s (%d lines)", file_path, line_count)
                return None

            # 计算相对路径
            try:
                relative = file_path.relative_to(repo_path)
            except ValueError:
                relative = file_path

            return cls(
                path=str(relative),
                absolute_path=str(file_path),
                language=language,
                line_count=line_count,
                size_bytes=size_bytes,
                content_hash=content_hash,
            )

        except OSError as exc:
            logger.warning("无法读取文件 %s: %s", file_path, exc)
            return None


@dataclass
class ScanResult:
    """扫描结果"""

    files: list[ScannedFile]
    total_count: int
    total_lines: int
    language_distribution: dict[str, int]
    skipped_count: int
    errors: list[str]

    def to_dict(self) -> dict:
        """转为字典格式"""
        return {
            "total_count": self.total_count,
            "total_lines": self.total_lines,
            "language_distribution": self.language_distribution,
            "skipped_count": self.skipped_count,
            "errors": self.errors,
        }


class GitScanner:
    """
    Git 仓库扫描器

    使用 GitPython 打开仓库，递归收集源代码文件，
    支持 .gitignore 过滤和语言分类。
    """

    # 默认排除的目录名（不依赖 .gitignore）
    DEFAULT_EXCLUDE_DIRS = frozenset({
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".env",
        "dist",
        "build",
        "target",
        "out",
        "bin",
        "obj",
        ".idea",
        ".vscode",
        ".next",
        "coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".vs",
    })

    def __init__(
        self,
        repo_path: str,
        exclude_dirs: frozenset[str] | None = None,
        max_line_count: int = 10000,
    ) -> None:
        """
        Args:
            repo_path: Git 仓库路径（绝对路径）
            exclude_dirs: 排除的目录名集合，默认使用 DEFAULT_EXCLUDE_DIRS
            max_line_count: 最大行数限制，超过则跳过文件
        """
        self.repo_path = Path(repo_path).resolve()
        self.exclude_dirs = exclude_dirs or self.DEFAULT_EXCLUDE_DIRS
        self.max_line_count = max_line_count
        self._git_repo: git.Repo | None = None

    def _open_repo(self) -> git.Repo | None:
        """打开 Git 仓库"""
        try:
            self._git_repo = git.Repo(str(self.repo_path))
            return self._git_repo
        except git.InvalidGitRepositoryError:
            # 非 Git 仓库，降级为纯 pathlib 扫描
            logger.warning("非 Git 仓库，降级为纯文件系统扫描: %s", self.repo_path)
            return None

    def scan(self, language_detector=None) -> ScanResult:
        """
        扫描仓库中的所有源代码文件

        Args:
            language_detector: 语言检测器，默认使用内置的 LanguageDetector

        Returns:
            ScanResult 包含所有扫描到的文件信息
        """
        from .language_detector import LanguageDetector

        if language_detector is None:
            language_detector = LanguageDetector()

        git_repo = self._open_repo()
        files: list[ScannedFile] = []
        errors: list[str] = []
        skipped_count = 0
        language_distribution: dict[str, int] = {}

        # 递归遍历所有文件
        try:
            for file_path in self.repo_path.rglob("*"):
                # 跳过目录
                if file_path.is_dir():
                    continue

                # 检查是否在排除目录中
                if any(part in self.exclude_dirs for part in file_path.parts):
                    skipped_count += 1
                    continue

                # 使用 GitPython 检查 .gitignore
                if git_repo is not None:
                    relative = file_path.relative_to(self.repo_path)
                    if git_repo.ignored(str(relative)):
                        skipped_count += 1
                        continue

                # 检测语言
                language = language_detector.detect(file_path)

                # 只扫描源代码文件
                if not language_detector.is_source_file(file_path):
                    skipped_count += 1
                    continue

                # 创建 ScannedFile
                scanned = ScannedFile.from_path(
                    file_path=file_path,
                    repo_path=self.repo_path,
                    language=language,
                    max_line_count=self.max_line_count,
                )

                if scanned is None:
                    skipped_count += 1
                    continue

                files.append(scanned)

                # 统计语言分布
                language_distribution[language] = language_distribution.get(language, 0) + 1

        except OSError as exc:
            errors.append(f"扫描失败: {exc}")
            logger.exception("扫描失败: %s", exc)

        # 计算总行数
        total_lines = sum(f.line_count for f in files)

        return ScanResult(
            files=files,
            total_count=len(files),
            total_lines=total_lines,
            language_distribution=language_distribution,
            skipped_count=skipped_count,
            errors=errors,
        )
