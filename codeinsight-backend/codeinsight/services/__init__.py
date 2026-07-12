"""
服务层模块

提供上层业务编排服务。
"""

from codeinsight.services.incremental_analyzer import ChangeType, FileChange, IncrementalAnalyzer, IncrementalDiff
from codeinsight.services.snapshot_manager import SnapshotManager
from codeinsight.services.structure_pipeline import (
    ProgressCallback,
    StructureDataPipeline,
)

__all__ = [
    "StructureDataPipeline",
    "ProgressCallback",
    "SnapshotManager",
    "IncrementalAnalyzer",
    "IncrementalDiff",
    "FileChange",
    "ChangeType",
]
