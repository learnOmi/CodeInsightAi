"""
Parser 模块单元测试
"""

from codeinsight.parsers import ParserFactory, LanguageParser, ASTNode, ASTNodeList
from codeinsight.parsers.python_parser import PythonParser
from codeinsight.parsers.typescript_parser import TypeScriptParser
from codeinsight.parsers.javascript_parser import JavaScriptParser
from codeinsight.parsers.java_parser import JavaParser
from codeinsight.parsers.go_parser import GoParser
