"""
FrameworkTagger - 为 AST 节点打框架标签

根据节点类型、注解、命名模式等特征，为 AST 节点打上框架标签，如：
- React: react-component, react-hook, react-context
- Vue: vue-component, vue-composable, vue-lifecycle
- Spring: http-controller, business-service, data-repository
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from codeinsight.parsers.base import ASTNode

if TYPE_CHECKING:
    from codeinsight.parsers.base import ASTNodeList

logger = logging.getLogger(__name__)


class NodeTaggingStrategy(Protocol):
    """
    节点标签策略协议

    各语言策略实现该协议，为对应语言的 AST 节点生成框架标签。
    新增语言只需实现该协议并向 FrameworkTagger.register_strategy 注册。
    """

    def tag(self, node: ASTNode) -> list[str]:
        """
        为节点生成框架标签

        Args:
            node: AST 节点

        Returns:
            该节点匹配到的框架标签列表（未匹配返回空列表）。
            实现方不应直接修改 node.tags，由 FrameworkTagger 统一追加，
            以保留对去重等行为的集中控制。
        """
        ...


class TsTaggingStrategy:
    """
    TypeScript/JavaScript 节点标签策略

    覆盖 React 组件 / Hook / Context 检测。
    """

    REACT_HOOK_PATTERN = r"^use[A-Z]"

    REACT_COMPONENT_INDICATORS = {
        "import": {"react", "react-dom"},
        "call": {"createElement", "useState", "useEffect", "useContext"},
        "jsx_element": {},
    }

    def tag(self, node: ASTNode) -> list[str]:
        """
        为 TypeScript/JavaScript 节点生成标签

        - React 组件：函数名首字母大写且包含 JSX
        - React Hook：use[A-Z] 命名模式
        - React Context：createContext 调用
        """
        tags: list[str] = []
        tags.extend(self._tag_react_component(node))
        tags.extend(self._tag_react_hook(node))
        tags.extend(self._tag_react_context(node))
        return tags

    def _tag_react_component(self, node: ASTNode) -> list[str]:
        """
        标记 React 组件

        规则：
        1. 函数名首字母大写
        2. 函数体包含 JSX 元素调用（createElement 或 jsx_element）
        3. 或使用 @Component 装饰器
        """
        if node.node_type != "function":
            return []

        if not node.name or len(node.name) == 0:
            return []

        if node.name[0].isupper():
            has_jsx = self._has_jsx_child(node) or self._has_jsx_import(node)
            if has_jsx:
                return ["react-component"]
        return []

    def _tag_react_hook(self, node: ASTNode) -> list[str]:
        """
        标记 React Hook

        规则：
        1. 函数名以 use[A-Z] 开头
        2. 或函数体中调用了 useState/useEffect 等 Hook
        """
        if node.node_type != "function":
            return []

        if not node.name or len(node.name) < 4:
            return []

        if node.name.startswith("use") and node.name[3].isupper():
            return ["react-hook"]
        return []

    def _tag_react_context(self, node: ASTNode) -> list[str]:
        """
        标记 React Context

        规则：
        - 调用 createContext
        """
        if node.node_type == "call":
            call_name = node.name.split("(")[0].strip()
            if call_name == "createContext":
                return ["react-context"]
        return []

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


class VueTaggingStrategy:
    """
    Vue 节点标签策略

    覆盖 Vue 组件 / Composable 检测。
    """

    VUE_COMPONENT_INDICATORS = {
        "import": {"vue", "@vue/composition-api"},
        "call": {"defineProps", "defineEmits", "ref", "reactive", "computed"},
        "object_method": {"mounted", "created", "data", "methods"},
    }

    def tag(self, node: ASTNode) -> list[str]:
        """
        为 Vue 节点生成标签

        - Vue 组件：defineComponent 调用或 .vue 文件中的函数
        - Vue Composable：use[A-Z] 命名模式
        """
        tags: list[str] = []
        tags.extend(self._tag_vue_component(node))
        tags.extend(self._tag_vue_composable(node))
        return tags

    def _tag_vue_component(self, node: ASTNode) -> list[str]:
        """
        标记 Vue 组件

        规则：
        1. .vue 文件中的函数（排除 use[A-Z] 开头的 composable）
        2. 或 defineComponent 调用
        """
        if node.language == "vue" and node.node_type == "function":
            is_composable = len(node.name) >= 4 and node.name.startswith("use") and node.name[3].isupper()
            if not is_composable:
                return ["vue-component"]

        if node.node_type == "call":
            call_name = node.name.split("(")[0].strip()
            if call_name == "defineComponent":
                return ["vue-component"]
        return []

    def _tag_vue_composable(self, node: ASTNode) -> list[str]:
        """
        标记 Vue Composable

        规则：
        1. 函数名以 use[A-Z] 开头
        2. 或函数体中调用了 ref/reactive/computed 等
        """
        if node.node_type != "function":
            return []

        if not node.name or len(node.name) < 4:
            return []

        if node.name.startswith("use") and node.name[3].isupper():
            return ["vue-composable"]
        return []


class JavaTaggingStrategy:
    """
    Java 节点标签策略

    覆盖 Spring 注解检测。
    """

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

    def tag(self, node: ASTNode) -> list[str]:
        """
        为 Java 节点生成标签

        - Spring：基于注解映射
        """
        return self._tag_spring_annotations(node)

    def _tag_spring_annotations(self, node: ASTNode) -> list[str]:
        """
        根据 Spring 注解打标签

        使用 SPRING_ANNOTATION_TO_TAG 映射表。
        保留原逻辑：对 node.tags 中已存在的标签去重，
        同时对本次将要返回的标签去重，避免 @RestController 与 @Controller
        等同义注解产生重复标签。
        """
        tags: list[str] = []
        seen: set[str] = set()
        for annotation in node.annotations:
            ann_name = annotation.get("name", "")
            if ann_name in self.SPRING_ANNOTATION_TO_TAG:
                tag = self.SPRING_ANNOTATION_TO_TAG[ann_name]
                if tag not in node.tags and tag not in seen:
                    tags.append(tag)
                    seen.add(tag)
        return tags


class PythonTaggingStrategy:
    """
    Python 节点标签策略

    覆盖 Flask/FastAPI/Celery 等装饰器检测。
    """

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

    def tag(self, node: ASTNode) -> list[str]:
        """
        为 Python 节点生成标签

        - Flask/FastAPI：基于装饰器映射
        """
        return self._tag_python_decorators(node)

    def _tag_python_decorators(self, node: ASTNode) -> list[str]:
        """
        根据 Python 装饰器打标签

        使用 PYTHON_DECORATOR_TO_TAG 映射表。
        保留原逻辑：每个装饰器匹配到第一个模式后即 break，
        且对 node.tags 中已存在的标签去重；
        同时对本次将要返回的标签去重，避免多装饰器映射到同一标签时产生重复。
        """
        tags: list[str] = []
        seen: set[str] = set()
        for annotation in node.annotations:
            ann_name = annotation.get("name", "")
            for decorator_pattern, tag in self.PYTHON_DECORATOR_TO_TAG.items():
                if ann_name.startswith(decorator_pattern):
                    if tag not in node.tags and tag not in seen:
                        tags.append(tag)
                        seen.add(tag)
                    break
        return tags


class GoTaggingStrategy:
    """
    Go 节点标签策略

    覆盖 Gin/Echo 等 HTTP Handler 检测。
    """

    def tag(self, node: ASTNode) -> list[str]:
        """
        为 Go 节点生成标签

        - Gin/Echo：基于方法命名模式
        """
        return self._tag_go_http_handler(node)

    def _tag_go_http_handler(self, node: ASTNode) -> list[str]:
        """
        标记 Go HTTP Handler

        规则：
        - 方法接收者类型为 *gin.Context 或类似
        - 或函数名包含 Handler
        """
        if node.node_type != "method":
            return []

        if node.qualified_name and ("Context" in node.qualified_name or "Handler" in node.name):
            return ["http-handler"]
        return []


class FrameworkTagger:
    """
    框架标签器

    对 AST 节点进行框架特征分析，打上相应的框架标签。

    通过策略注册表支持多语言扩展：新增语言只需实现 NodeTaggingStrategy
    协议，并调用 register_strategy 注册即可，无需修改 tag_node 分支逻辑。
    """

    def __init__(self) -> None:
        self._strategies: dict[str, NodeTaggingStrategy] = {}
        # 注册内置语言策略
        self.register_strategy("typescript", TsTaggingStrategy())
        self.register_strategy("javascript", TsTaggingStrategy())
        self.register_strategy("vue", VueTaggingStrategy())
        self.register_strategy("java", JavaTaggingStrategy())
        self.register_strategy("python", PythonTaggingStrategy())
        self.register_strategy("go", GoTaggingStrategy())

    def register_strategy(self, language: str, strategy: NodeTaggingStrategy) -> None:
        """
        注册语言标签策略

        Args:
            language: 语言名称（需与 ASTNode.language 取值一致，
                如 "java"、"python"、"typescript"）
            strategy: 实现了 NodeTaggingStrategy 协议的策略实例
        """
        self._strategies[language] = strategy

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

        根据节点语言从注册表中查找对应策略并委托打标签；
        若该语言未注册策略则跳过（保持原 if-elif 链的缺省行为）。

        Args:
            node: AST 节点
        """
        strategy = self._strategies.get(node.language)
        if strategy is None:
            return
        tags = strategy.tag(node)
        if tags:
            node.tags.extend(tags)
