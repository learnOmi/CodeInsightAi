"""
结构分析模块

提供代码结构分析相关功能：
- CallGraphBuilder: 调用图构建
- ModuleDependencyBuilder: 模块依赖图构建
- FrameworkTagger: AST 节点框架标签检测
- FrameworkDetector: 框架检测引擎
- RouteExtractor: API 路由提取
- MiddlewareAnalyzer: 中间件链分析
- DependencyParser: 外部依赖声明解析
"""

from codeinsight.analyzers.call_graph import CallGraphBuilder
from codeinsight.analyzers.dependency_parser import DependencyParser
from codeinsight.analyzers.framework_detector import FrameworkDetector
from codeinsight.analyzers.framework_tagger import FrameworkTagger
from codeinsight.analyzers.middleware_analyzer import MiddlewareAnalyzer
from codeinsight.analyzers.module_graph import ModuleDependencyBuilder
from codeinsight.analyzers.route_extractor import RouteExtractor

__all__ = [
    "CallGraphBuilder",
    "ModuleDependencyBuilder",
    "FrameworkTagger",
    "FrameworkDetector",
    "RouteExtractor",
    "MiddlewareAnalyzer",
    "DependencyParser",
]
