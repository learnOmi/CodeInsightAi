"""
Repository 数据访问对象包

导出仓库相关的 DAO 类。
"""

from codeinsight.repositories.analysis_version import AnalysisVersionDAO
from codeinsight.repositories.api_route import ApiRouteDAO
from codeinsight.repositories.ast_node import AstNodeDAO
from codeinsight.repositories.call_edge import CallEdgeDAO
from codeinsight.repositories.external_dependency import ExternalDependencyDAO
from codeinsight.repositories.file import FileDAO
from codeinsight.repositories.file_analysis_progress import FileAnalysisProgressDAO  # R-R4
from codeinsight.repositories.file_analysis_snapshot import FileAnalysisSnapshotDAO
from codeinsight.repositories.framework_pattern import FrameworkPatternDAO
from codeinsight.repositories.knowledge_point import KnowledgePointDAO
from codeinsight.repositories.module_dependency import ModuleDependencyDAO
from codeinsight.repositories.repository import RepositoryDAO

__all__ = [
    "RepositoryDAO",
    "FileDAO",
    "FileAnalysisSnapshotDAO",
    "FileAnalysisProgressDAO",  # R-R4
    "AstNodeDAO",
    "CallEdgeDAO",
    "ModuleDependencyDAO",
    "KnowledgePointDAO",
    "AnalysisVersionDAO",
    "ApiRouteDAO",
    "FrameworkPatternDAO",
    "ExternalDependencyDAO",
]
