"""
FrameworkTagger - 为 AST 节点打框架标签

根据节点类型、注解、命名模式等特征，为 AST 节点打上框架标签，如：
- React: react-component, react-hook, react-context
- Vue: vue-component, vue-composable, vue-lifecycle
- Spring: http-controller, business-service, data-repository
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codeinsight.parsers.base import ASTNode

if TYPE_CHECKING:
    from codeinsight.parsers.base import ASTNodeList

logger = logging.getLogger(__name__)


class FrameworkTagger:
    """
    框架标签器

    对 AST 节点进行框架特征分析，打上相应的框架标签。
    """

    REACT_HOOK_PATTERN = r"^use[A-Z]"

    REACT_COMPONENT_INDICATORS = {
        "import": {"react", "react-dom"},
        "call": {"createElement", "useState", "useEffect", "useContext"},
        "jsx_element": {},
    }

    VUE_COMPONENT_INDICATORS = {
        "import": {"vue", "@vue/composition-api"},
        "call": {"defineProps", "defineEmits", "ref", "reactive", "computed"},
        "object_method": {"mounted", "created", "data", "methods"},
    }

    SPRING_ANNOTATION_TO_TAG = {
        "@RestController": "http-controller",
        "@Controller": "http-controller",
        "@Service": "business-service",
        "@Repository": "data-repository",
        "@Component": "spring-component",
        "@Configuration": "spring-config",
        "@Bean": "spring-bean",
        "@Autowired": "dependency-injection",
        "@Inject": "dependency-injection",
        "@RequestMapping": "api-endpoint",
        "@GetMapping": "api-endpoint",
        "@PostMapping": "api-endpoint",
        "@PutMapping": "api-endpoint",
        "@DeleteMapping": "api-endpoint",
        "@PatchMapping": "api-endpoint",
        "@Aspect": "spring-aspect",
        "@Transactional": "transactional",
        "@Scheduled": "scheduled-task",
        "@SpringBootApplication": "spring-boot-app",
    }

    PYTHON_DECORATOR_TO_TAG = {
        "@app.route": "flask-route",
        "@bp.route": "flask-route",
        "@app.get": "fastapi-route",
        "@app.post": "fastapi-route",
        "@app.put": "fastapi-route",
        "@app.delete": "fastapi-route",
        "@router.get": "fastapi-route",
        "@router.post": "fastapi-route",
        "@router.put": "fastapi-route",
        "@router.delete": "fastapi-route",
        "@celery.task": "celery-task",
        "@shared_task": "celery-task",
        "@lru_cache": "cached-function",
        "@cache": "cached-function",
        "@staticmethod": "static-method",
        "@classmethod": "static-method",
        "@property": "property",
        "@contextmanager": "context-manager",
    }

    def __init__(self) -> None:
        pass

    def tag_all(self, nodes: ASTNodeList) -> None:
        """
        为所有节点打框架标签

        Args:
            nodes: AST 节点列表
        """
        for node in nodes.nodes:
            self.tag_node(node)

    def tag_node(self, node: ASTNode) -> None:
        """
        为单个节点打框架标签

        根据节点语言和类型，调用相应的标签方法。

        Args:
            node: AST 节点
        """
        if node.language in ("typescript", "javascript"):
            self._tag_typescript_node(node)
        elif node.language == "vue":
            self._tag_vue_node(node)
        elif node.language == "java":
            self._tag_java_node(node)
        elif node.language == "python":
            self._tag_python_node(node)
        elif node.language == "go":
            self._tag_go_node(node)

    def _tag_typescript_node(self, node: ASTNode) -> None:
        """
        为 TypeScript/JavaScript 节点打标签

        - React 组件：函数名首字母大写且包含 JSX
        - React Hook：use[A-Z] 命名模式
        - React Context：createContext 调用
        """
        self._tag_react_component(node)
        self._tag_react_hook(node)
        self._tag_react_context(node)

    def _tag_vue_node(self, node: ASTNode) -> None:
        """
        为 Vue 节点打标签

        - Vue 组件：defineComponent 调用或 .vue 文件中的函数
        - Vue Composable：use[A-Z] 命名模式
        """
        self._tag_vue_component(node)
        self._tag_vue_composable(node)

    def _tag_java_node(self, node: ASTNode) -> None:
        """
        为 Java 节点打标签

        - Spring：基于注解映射
        """
        self._tag_spring_annotations(node)

    def _tag_python_node(self, node: ASTNode) -> None:
        """
        为 Python 节点打标签

        - Flask/FastAPI：基于装饰器映射
        """
        self._tag_python_decorators(node)

    def _tag_go_node(self, node: ASTNode) -> None:
        """
        为 Go 节点打标签

        - Gin/Echo：基于方法命名模式
        """
        self._tag_go_http_handler(node)

    def _tag_react_component(self, node: ASTNode) -> None:
        """
        标记 React 组件

        规则：
        1. 函数名首字母大写
        2. 函数体包含 JSX 元素调用（createElement 或 jsx_element）
        3. 或使用 @Component 装饰器
        """
        if node.node_type != "function":
            return

        if not node.name or len(node.name) == 0:
            return

        if node.name[0].isupper():
            has_jsx = self._has_jsx_child(node) or self._has_jsx_import(node)
            if has_jsx:
                node.tags.append("react-component")

    def _tag_react_hook(self, node: ASTNode) -> None:
        """
        标记 React Hook

        规则：
        1. 函数名以 use[A-Z] 开头
        2. 或函数体中调用了 useState/useEffect 等 Hook
        """
        if node.node_type != "function":
            return

        if not node.name or len(node.name) < 4:
            return

        if node.name.startswith("use") and node.name[3].isupper():
            node.tags.append("react-hook")

    def _tag_react_context(self, node: ASTNode) -> None:
        """
        标记 React Context

        规则：
        - 调用 createContext
        """
        if node.node_type == "call":
            call_name = node.name.split("(")[0].strip()
            if call_name == "createContext":
                node.tags.append("react-context")

    def _tag_vue_component(self, node: ASTNode) -> None:
        """
        标记 Vue 组件

        规则：
        1. .vue 文件中的函数（排除 use[A-Z] 开头的 composable）
        2. 或 defineComponent 调用
        """
        if node.language == "vue" and node.node_type == "function":
            is_composable = len(node.name) >= 4 and node.name.startswith("use") and node.name[3].isupper()
            if not is_composable:
                node.tags.append("vue-component")

        if node.node_type == "call":
            call_name = node.name.split("(")[0].strip()
            if call_name == "defineComponent":
                node.tags.append("vue-component")

    def _tag_vue_composable(self, node: ASTNode) -> None:
        """
        标记 Vue Composable

        规则：
        1. 函数名以 use[A-Z] 开头
        2. 或函数体中调用了 ref/reactive/computed 等
        """
        if node.node_type != "function":
            return

        if not node.name or len(node.name) < 4:
            return

        if node.name.startswith("use") and node.name[3].isupper():
            node.tags.append("vue-composable")

    def _tag_spring_annotations(self, node: ASTNode) -> None:
        """
        根据 Spring 注解打标签

        使用 SPRING_ANNOTATION_TO_TAG 映射表。
        """
        for annotation in node.annotations:
            ann_name = annotation.get("name", "")
            if ann_name in self.SPRING_ANNOTATION_TO_TAG:
                tag = self.SPRING_ANNOTATION_TO_TAG[ann_name]
                if tag not in node.tags:
                    node.tags.append(tag)

    def _tag_python_decorators(self, node: ASTNode) -> None:
        """
        根据 Python 装饰器打标签

        使用 PYTHON_DECORATOR_TO_TAG 映射表。
        """
        for annotation in node.annotations:
            ann_name = annotation.get("name", "")
            for decorator_pattern, tag in self.PYTHON_DECORATOR_TO_TAG.items():
                if ann_name.startswith(decorator_pattern):
                    if tag not in node.tags:
                        node.tags.append(tag)
                    break

    def _tag_go_http_handler(self, node: ASTNode) -> None:
        """
        标记 Go HTTP Handler

        规则：
        - 方法接收者类型为 *gin.Context 或类似
        - 或函数名包含 Handler
        """
        if node.node_type != "method":
            return

        if node.qualified_name and ("Context" in node.qualified_name or "Handler" in node.name):
            node.tags.append("http-handler")

    def _has_jsx_child(self, node: ASTNode) -> bool:
        """
        检查节点是否包含 JSX 子节点

        Args:
            node: AST 节点

        Returns:
            是否包含 JSX 子节点
        """
        for child in node.children:
            if child.node_type == "jsx_element":
                return True
            if self._has_jsx_child(child):
                return True
        return False

    def _has_jsx_import(self, node: ASTNode) -> bool:
        """
        检查节点是否有 React 相关导入

        Args:
            node: AST 节点

        Returns:
            是否有 React 导入
        """
        for child in node.children:
            if child.node_type == "import":
                import_name = child.name.lower()
                if "react" in import_name:
                    return True
            if self._has_jsx_import(child):
                return True
        return False
