"""
Git 仓库扫描器

使用 GitPython 打开 Git 仓库，递归收集源代码文件，支持 .gitignore 过滤。
"""

import hashlib
import logging
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import git

from codeinsight.config import settings

logger = logging.getLogger(__name__)

# D-3 修复：从配置统一读取，不再硬编码
MAX_FILE_SIZE_BYTES = settings.max_file_size_bytes
READ_BUFFER_SIZE = 64 * 1024
DEFAULT_MAX_LINE_COUNT = 10000
DEFAULT_MAX_FILES = 50000

# Phase 5: 依赖声明文件名集合（这些文件需要被扫描，尽管不是源代码文件）
DEPENDENCY_DECLARATION_FILES: frozenset[str] = frozenset(
    {
        "package.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "requirements.txt",
        "pyproject.toml",
        "Pipfile",
        "go.mod",
        "Cargo.toml",
    }
)


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
        max_line_count: int = DEFAULT_MAX_LINE_COUNT,
        relative_path: Path | None = None,
    ) -> "ScannedFile | None":
        """
        从文件路径创建 ScannedFile 实例

        使用流式分块读取，始终控制内存占用（最大 ~64KB 缓冲）。

        Args:
            file_path: 文件绝对路径
            repo_path: 仓库根路径
            language: 语言类型
            max_line_count: 最大行数限制，超过则返回 None
            relative_path: 预先计算的相对路径，避免重复计算

        Returns:
            ScannedFile 实例或 None（文件过大、行数过多或无法读取）
        """
        try:
            # 先检查文件大小，无需加载到内存
            size_bytes = file_path.stat().st_size

            # 跳过过大文件（>10MB）
            if size_bytes > MAX_FILE_SIZE_BYTES:
                logger.debug("跳过过大文件: %s (%.1fMB)", file_path, size_bytes / (1024 * 1024))
                return None

            # 分块读取，计算 hash + 统计行数
            sha = hashlib.sha256()
            line_count = 0
            partial_line = 0  # 记录前一个 chunk 末尾不完整的行数

            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(READ_BUFFER_SIZE)
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

            # 使用预先计算的相对路径，避免重复计算 (S-5 修复)
            if relative_path is None:
                try:
                    relative_path = file_path.relative_to(repo_path)
                except ValueError:
                    relative_path = file_path

            return cls(
                path=str(relative_path),
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
    commit_hash: str | None = None

    def to_dict(self) -> dict:
        """转为字典格式"""
        return {
            "total_count": self.total_count,
            "total_lines": self.total_lines,
            "language_distribution": self.language_distribution,
            "skipped_count": self.skipped_count,
            "errors": self.errors,
        }

    def batch_iter(self, batch_size: int = 1000) -> Generator[list[ScannedFile], None, None]:
        """
        S-2 修复：分批迭代文件，减少内存占用。

        Args:
            batch_size: 每批文件数量，默认为 1000

        Returns:
            分批生成器，每次返回一批文件
        """
        for i in range(0, len(self.files), batch_size):
            yield self.files[i : i + batch_size]


class GitScanner:
    """
    Git 仓库扫描器

    使用 GitPython 打开仓库，递归收集源代码文件，
    支持 .gitignore 过滤和语言分类。
    """

    # 默认排除的目录名（不依赖 .gitignore）
    DEFAULT_EXCLUDE_DIRS = frozenset(
        {
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
        }
    )

    def __init__(
        self,
        repo_path: str,
        exclude_dirs: frozenset[str] | None = None,
        max_line_count: int = DEFAULT_MAX_LINE_COUNT,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None:
        """
        Args:
            repo_path: Git 仓库路径（绝对路径）
            exclude_dirs: 排除的目录名集合，默认使用 DEFAULT_EXCLUDE_DIRS
            max_line_count: 最大行数限制，超过则跳过文件
            max_files: 最大文件数量限制，防止内存溢出
        """
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise FileNotFoundError(f"仓库路径不存在: {self.repo_path}")
        if not self.repo_path.is_dir():
            raise NotADirectoryError(f"仓库路径不是目录: {self.repo_path}")
        self.exclude_dirs = exclude_dirs or self.DEFAULT_EXCLUDE_DIRS
        self.max_line_count = max_line_count
        self.max_files = max_files
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
            language_detector = LanguageDetector.get_instance()

        git_repo = self._open_repo()
        files: list[ScannedFile] = []
        errors: list[str] = []
        skipped_count = 0
        language_distribution: dict[str, int] = {}
        repo_path_str = str(self.repo_path)

        try:
            for file_path in self.repo_path.rglob("*"):
                try:
                    if file_path.is_dir():
                        continue

                    if any(part in self.exclude_dirs for part in file_path.parts):
                        skipped_count += 1
                        continue

                    relative: Path | None = None
                    if git_repo is not None:
                        try:
                            relative = file_path.relative_to(self.repo_path)
                        except ValueError:
                            skipped_count += 1
                            continue
                        if git_repo.ignored(str(relative)):
                            skipped_count += 1
                            continue

                    language = language_detector.detect(file_path)

                    # Phase 5: 依赖声明文件即使不是源代码文件也需要扫描
                    is_dep_file = file_path.name in DEPENDENCY_DECLARATION_FILES

                    if not is_dep_file and not language_detector.is_source_file(file_path):
                        skipped_count += 1
                        continue

                    scanned = ScannedFile.from_path(
                        file_path=file_path,
                        repo_path=self.repo_path,
                        language=language,
                        max_line_count=self.max_line_count,
                        relative_path=relative,
                    )

                    if scanned is None:
                        skipped_count += 1
                        continue

                    if file_path.is_symlink():
                        resolved = file_path.resolve()
                        if not str(resolved).startswith(repo_path_str):
                            logger.warning("符号链接指向仓库外，跳过: %s -> %s", file_path, resolved)
                            skipped_count += 1
                            continue

                    files.append(scanned)

                    language_distribution[language] = language_distribution.get(language, 0) + 1

                    if len(files) >= self.max_files:
                        logger.warning("已达到最大文件数量限制，停止扫描: %d", self.max_files)
                        break

                except OSError as exc:
                    errors.append(f"处理文件失败: {file_path}: {exc}")
                    logger.warning("处理文件失败: %s: %s", file_path, exc)
                    skipped_count += 1
                except Exception as exc:
                    errors.append(f"处理文件异常: {file_path}: {exc}")
                    logger.warning("处理文件异常: %s: %s", file_path, exc)
                    skipped_count += 1

        except OSError as exc:
            errors.append(f"扫描目录失败: {self.repo_path}: {exc}")
            logger.error("扫描目录失败: %s: %s", self.repo_path, exc)
        except Exception as exc:
            errors.append(f"扫描异常: {self.repo_path}: {exc}")
            logger.error("扫描异常: %s: %s", self.repo_path, exc)

        total_lines = sum(f.line_count for f in files)

        commit_hash: str | None = None
        if git_repo is not None and git_repo.head.is_valid():
            commit_hash = git_repo.head.commit.hexsha

        if errors:
            logger.warning("扫描完成但存在错误: files=%d, errors=%d", len(files), len(errors))

        return ScanResult(
            files=files,
            total_count=len(files),
            total_lines=total_lines,
            language_distribution=language_distribution,
            skipped_count=skipped_count,
            errors=errors,
            commit_hash=commit_hash,
        )
