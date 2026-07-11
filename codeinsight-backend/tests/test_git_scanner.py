"""
Git 扫描器单元测试

使用临时 Git 仓库测试扫描功能，包括 .gitignore 过滤和语言检测。
"""

from pathlib import Path

import git
import pytest

from codeinsight.scanners.git_scanner import GitScanner, ScanResult


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    """创建临时 Git 仓库"""
    repo = git.Repo.init(tmp_path)

    # 创建 Python 文件
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "utils.py").write_text("def helper():\n    pass\n")

    # 创建 TypeScript 文件
    (tmp_path / "app.ts").write_text("const x = 1;\n")

    # 创建 .gitignore 文件
    (tmp_path / ".gitignore").write_text("secret.py\n")

    # 创建被 .gitignore 忽略的文件（不提交到 git）
    (tmp_path / "secret.py").write_text("secret = 'key'\n")

    # 创建应被排除的目录
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "node_modules").mkdir(exist_ok=True)
    (tmp_path / "__pycache__").mkdir(exist_ok=True)

    # 创建配置文件
    (tmp_path / "config.json").write_text('{"key": "value"}\n')

    # 创建 Markdown 文件
    (tmp_path / "README.md").write_text("# Test\n\nHello World\n")

    # 提交到 Git（不包含 secret.py，因为它被 .gitignore 忽略）
    repo.index.add(["main.py", "utils.py", "app.ts", "config.json", "README.md"])
    repo.index.commit("initial commit")

    return tmp_path


class TestGitScanner:
    """GitScanner 单元测试"""

    def test_scan_returns_scanned_files(self, test_repo: Path) -> None:
        """测试扫描返回文件列表"""
        scanner = GitScanner(str(test_repo))
        result = scanner.scan()

        assert isinstance(result, ScanResult)
        assert result.total_count >= 2  # 至少 main.py 和 utils.py

    def test_scan_filters_gitignore(self, test_repo: Path) -> None:
        """测试 .gitignore 过滤"""
        scanner = GitScanner(str(test_repo))
        result = scanner.scan()

        # secret.py 应该在 .gitignore 中
        ignored_files = [f for f in result.files if f.path == "secret.py"]
        assert len(ignored_files) == 0

    def test_scan_filters_excluded_dirs(self, test_repo: Path) -> None:
        """测试排除目录过滤"""
        scanner = GitScanner(str(test_repo))
        result = scanner.scan()

        # 不应包含 .git 或 node_modules 中的文件
        git_files = [f for f in result.files if f.path.startswith(".git")]
        assert len(git_files) == 0

        node_files = [f for f in result.files if f.path.startswith("node_modules")]
        assert len(node_files) == 0

    def test_scan_filters_non_source(self, test_repo: Path) -> None:
        """测试过滤非源代码文件"""
        scanner = GitScanner(str(test_repo))
        result = scanner.scan()

        # JSON 和 Markdown 文件不应包含在结果中
        json_files = [f for f in result.files if f.path.endswith(".json")]
        assert len(json_files) == 0

        md_files = [f for f in result.files if f.path.endswith(".md")]
        assert len(md_files) == 0

    def test_scan_language_distribution(self, test_repo: Path) -> None:
        """测试语言分布统计"""
        scanner = GitScanner(str(test_repo))
        result = scanner.scan()

        assert "python" in result.language_distribution
        assert "typescript" in result.language_distribution

    def test_scan_file_content_hash(self, test_repo: Path) -> None:
        """测试文件内容 hash"""
        scanner = GitScanner(str(test_repo))
        result = scanner.scan()

        for file in result.files:
            assert len(file.content_hash) == 64  # SHA-256 hex
            assert file.content_hash == file.content_hash.lower()

    def test_scan_skipped_count(self, test_repo: Path) -> None:
        """测试跳过文件计数"""
        scanner = GitScanner(str(test_repo))
        result = scanner.scan()

        # 至少有一个文件被跳过（如 .gitignore 中的 secret.py）
        assert result.skipped_count > 0

    def test_scan_non_git_repo(self, tmp_path: Path) -> None:
        """测试非 Git 仓库降级"""
        # 创建非 Git 仓库
        test_path = tmp_path / "non_git"
        test_path.mkdir()
        (test_path / "test.py").write_text("print('hello')\n")

        scanner = GitScanner(str(test_path))
        result = scanner.scan()

        # 应降级为文件系统扫描，仍然能扫描到文件
        assert result.total_count >= 1

    def test_scan_empty_repo(self, tmp_path: Path) -> None:
        """测试空仓库"""
        repo = git.Repo.init(tmp_path)
        repo.index.commit("initial empty commit")

        scanner = GitScanner(str(tmp_path))
        result = scanner.scan()

        assert result.total_count == 0
