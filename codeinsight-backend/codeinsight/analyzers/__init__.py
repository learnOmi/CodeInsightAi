"""
结构分析模块

提供代码结构分析相关功能：
- CallGraphBuilder: 调用图构建
- ModuleDependencyBuilder: 模块依赖图构建
- FrameworkTagger: AST 节点框架标签检测
- FrameworkDetector: 框架检测引擎
"""

from codeinsight.analyzers.call_graph import CallGraphBuilder
from codeinsight.analyzers.framework_detector import FrameworkDetector
from codeinsight.analyzers.framework_tagger import FrameworkTagger
from codeinsight.analyzers.module_graph import ModuleDependencyBuilder

__all__ = [
    "CallGraphBuilder",
    "ModuleDependencyBuilder",
    "FrameworkTagger",
    "FrameworkDetector",
]
