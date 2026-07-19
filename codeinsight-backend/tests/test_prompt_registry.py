"""
P3-11 PromptRegistry 测试

测试 PromptRegistry 和 PromptEntry 组件。
"""

from __future__ import annotations

from pathlib import Path

from codeinsight.evaluation.prompt_registry import PromptEntry, PromptRegistry


class TestPromptEntry:
    """PromptEntry 测试"""

    def test_from_file(self, tmp_path):
        """从文件创建注册项"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Prompt\nContent here", encoding="utf-8")

        entry = PromptEntry.from_file(test_file)
        assert entry.file_name == "test.md"
        assert entry.file_path == test_file
        assert len(entry.sha256) == 64  # SHA256 hex length
        assert entry.size_bytes == len(test_file.read_bytes())

    def test_same_content_same_hash(self, tmp_path):
        """相同内容产生相同哈希"""
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("same content", encoding="utf-8")
        f2.write_text("same content", encoding="utf-8")

        e1 = PromptEntry.from_file(f1)
        e2 = PromptEntry.from_file(f2)
        assert e1.sha256 == e2.sha256

    def test_different_content_different_hash(self, tmp_path):
        """不同内容产生不同哈希"""
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("content A", encoding="utf-8")
        f2.write_text("content B", encoding="utf-8")

        e1 = PromptEntry.from_file(f1)
        e2 = PromptEntry.from_file(f2)
        assert e1.sha256 != e2.sha256


class TestPromptRegistry:
    """PromptRegistry 测试"""

    def test_scan_known_prompts(self):
        """扫描已知 Prompt 文件"""
        registry = PromptRegistry()
        entries = registry.scan()

        # 应扫描到至少一个 Prompt 文件
        assert len(entries) > 0

    def test_compute_version_stable(self):
        """版本标识稳定性"""
        registry = PromptRegistry()
        v1 = registry.compute_version(base_version="1.0.0")
        v2 = registry.compute_version(base_version="1.0.0")
        assert v1 == v2

    def test_compute_version_different_base(self):
        """不同 base 产生不同版本"""
        registry = PromptRegistry()
        v1 = registry.compute_version(base_version="1.0.0")
        v2 = registry.compute_version(base_version="2.0.0")
        assert v1 != v2

    def test_get_entry(self):
        """获取单个注册项"""
        registry = PromptRegistry()
        registry.scan()
        entry = registry.get_entry("base.md")
        if entry:
            assert entry.file_name == "base.md"
            assert len(entry.sha256) == 64

    def test_get_all_entries(self):
        """获取所有注册项"""
        registry = PromptRegistry()
        registry.scan()
        entries = registry.get_all_entries()
        assert isinstance(entries, dict)
        for name, entry in entries.items():
            assert entry.file_name == name

    def test_as_dict(self):
        """导出为字典"""
        registry = PromptRegistry()
        data = registry.as_dict()
        assert "prompt_version" in data
        assert "entries" in data
        assert isinstance(data["entries"], dict)
        for _, entry_data in data["entries"].items():
            assert "sha256" in entry_data
            assert "size_bytes" in entry_data

    def test_custom_prompts_dir(self, tmp_path):
        """自定义 prompts 目录"""
        # 创建自定义目录结构
        custom_dir = tmp_path / "prompts"
        custom_dir.mkdir()
        (custom_dir / "custom.md").write_text("# Custom", encoding="utf-8")

        registry = PromptRegistry(prompts_dir=custom_dir)
        registry.KNOWN_PROMPTS = ["custom.md"]
        entries = registry.scan()
        assert len(entries) == 1
        assert entries[0].file_name == "custom.md"

    def test_missing_prompts_dir(self):
        """不存在的 prompts 目录"""
        registry = PromptRegistry(prompts_dir=Path("/nonexistent"))
        entries = registry.scan()
        assert len(entries) == 0
        # 应回退到 base_version
        version = registry.compute_version(base_version="test")
        assert version == "test"

    def test_version_format(self):
        """版本格式验证"""
        registry = PromptRegistry()
        version = registry.compute_version(base_version="1.0.0")
        assert version.startswith("v1.0.0-")
        assert len(version) >= 11  # v1.0.0-xxxxx

    def test_scan_multiple_times(self):
        """多次扫描不累积"""
        registry = PromptRegistry()
        registry.scan()
        first_count = len(registry.get_all_entries())
        registry.scan()
        second_count = len(registry.get_all_entries())
        assert first_count == second_count
