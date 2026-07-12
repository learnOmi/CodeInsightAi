"""
结构分析模块

提供代码结构分析相关功能：
- CallGraphBuilder: 调用图构建
- ModuleDependencyBuilder: 模块依赖图构建
"""

from codeinsight.analyzers.call_graph import CallGraphBuilder
from codeinsight.analyzers.module_graph import ModuleDependencyBuilder

__all__ = [
    "CallGraphBuilder",
    "ModuleDependencyBuilder",
]
