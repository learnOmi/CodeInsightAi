"""
Prompt 版本注册表

跟踪所有 Prompt 文件的 SHA256 哈希和版本标签，
用于评估框架在每次运行时检测 Prompt 是否发生变化，
并在快照中标记对应的 prompt_version。

设计原则：
- 只读操作（hash 计算）在 CI 环境中不会触发写磁盘
- 支持增量更新：只计算本次运行的哈希，不保存历史
- 与 EvalConfig.prompt_version 配合使用
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PromptEntry:
    """单个 Prompt 文件的注册信息"""

    file_name: str
    file_path: Path
    sha256: str
    size_bytes: int

    @staticmethod
    def from_file(file_path: Path) -> PromptEntry:
        """从文件路径创建注册项"""
        data = file_path.read_bytes()
        return PromptEntry(
            file_name=file_path.name,
            file_path=file_path,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )


class PromptRegistry:
    """Prompt 版本注册表

    计算所有已知 Prompt 文件的 SHA256 哈希，生成全局签名，
    用于评估快照的版本标识。

    用法：
        >>> registry = PromptRegistry()
        >>> registry.scan()
        >>> version = registry.compute_version()
        >>> print(version)
        "v1.2.3-a1b2c3"
    """

    # 已知 Prompt 文件列表（相对于 prompts 目录）
    KNOWN_PROMPTS = [
        "base.md",
        "design_pattern.md",
        "architecture.md",
        "algorithm.md",
        "engineering.md",
        "domain.md",
        "expansion.md",
    ]

    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        """初始化注册表

        Args:
            prompts_dir: Prompt 目录路径，默认自动定位到 codeinsight/prompts/
        """
        if prompts_dir:
            self._prompts_dir = Path(prompts_dir)
        else:
            # 自动定位：从当前模块目录向上找到 prompts/
            self._prompts_dir = Path(__file__).parent.parent / "prompts"

        self._entries: dict[str, PromptEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> list[PromptEntry]:
        """扫描所有已知 Prompt 文件并计算哈希

        Returns:
            已扫描的 PromptEntry 列表
        """
        if not self._prompts_dir.is_dir():
            logger.warning("Prompts directory not found: %s", self._prompts_dir)
            return []

        self._entries.clear()
        entries: list[PromptEntry] = []

        for file_name in self.KNOWN_PROMPTS:
            file_path = self._prompts_dir / file_name
            if file_path.is_file():
                entry = PromptEntry.from_file(file_path)
                self._entries[file_name] = entry
                entries.append(entry)
                logger.debug("已注册 Prompt: %s (SHA256=%s...)", file_name, entry.sha256[:12])
            else:
                logger.warning("Prompt file not found: %s", file_path)

        return entries

    def compute_version(self, base_version: str = "1.0.0") -> str:
        """计算全局 Prompt 版本标识

        将 base_version 和所有 Prompt 文件哈希拼接，生成稳定版本字符串。

        Args:
            base_version: 基础版本标签（默认 "1.0.0"）

        Returns:
            版本字符串，格式 "v{base_version}-{combined_hash[:8]}"
        """
        if not self._entries:
            self.scan()

        if not self._entries:
            logger.warning("No prompt entries found, using base version only")
            return base_version

        # 按文件名列序计算组合哈希，确保版本标识稳定
        combined = "|".join(f"{name}={entry.sha256}" for name, entry in sorted(self._entries.items()))
        combined_hash = hashlib.sha256(combined.encode()).hexdigest()[:8]

        version = f"v{base_version}-{combined_hash}"
        logger.info("Prompt 版本标识: %s", version)
        return version

    def get_entry(self, file_name: str) -> PromptEntry | None:
        """获取指定 Prompt 文件的注册信息

        Args:
            file_name: 文件名（如 "base.md"）

        Returns:
            PromptEntry，不存在时返回 None
        """
        return self._entries.get(file_name)

    def get_all_entries(self) -> dict[str, PromptEntry]:
        """获取所有注册信息

        Returns:
            文件名到 PromptEntry 的映射
        """
        return dict(self._entries)

    def as_dict(self) -> dict[str, Any]:
        """导出为字典（用于快照记录）

        Returns:
            包含每个 Prompt 文件哈希和版本的字典
        """
        if not self._entries:
            self.scan()

        return {
            "prompt_version": self.compute_version(),
            "entries": {
                name: {
                    "sha256": entry.sha256,
                    "size_bytes": entry.size_bytes,
                }
                for name, entry in sorted(self._entries.items())
            },
        }
