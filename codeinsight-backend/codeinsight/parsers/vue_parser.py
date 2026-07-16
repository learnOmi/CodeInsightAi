"""
Vue SFC 单文件组件解析器

解析 .vue 文件，提取：
- <script> 区块（含 <script setup>）
- <template> 中的组件引用
- Vue 特定 API 调用（defineProps/defineEmits/defineExpose）
- Composition API（ref/reactive/computed/watch）
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .base import ASTNode, ASTNodeList, LanguageParser
from .typescript_parser import TypeScriptParser

logger = logging.getLogger(__name__)


class VueSfcParser(LanguageParser):
    """
    Vue SFC 解析器

    提取的节点类型：
    - function: 顶层函数/箭头函数
    - class: 类声明
    - method: 类/接口中的方法
    - object_method: Options API 的 methods/computed/watch
    - call: 函数调用
    - import: import 语句
    - jsx_element: JSX 元素
    - vue-component-api: defineProps/defineEmits/defineExpose
    - vue-composable: ref/reactive/computed/watch 等
    """

    _VUE_COMPONENT_API_CALLS = {"defineProps", "defineEmits", "defineExpose", "withDefaults"}
    _VUE_COMPOSABLE_CALLS = {
        "ref",
        "reactive",
        "computed",
        "watch",
        "watchEffect",
        "readonly",
        "shallowRef",
        "shallowReactive",
        "shallowReadonly",
        "toRef",
        "toRefs",
        "markRaw",
        "customRef",
    }
    _VUE_LIFECYCLE_CALLS = {
        "onMounted",
        "onUnmounted",
        "onCreated",
        "onBeforeMount",
        "onBeforeUnmount",
        "onBeforeUpdate",
        "onUpdated",
        "onActivated",
        "onDeactivated",
        "onErrorCaptured",
        "onRenderTracked",
        "onRenderTriggered",
        "onServerPrefetch",
    }

    def __init__(self) -> None:
        self._ts_parser = TypeScriptParser()
        self._language_name = "vue"

    def get_language_name(self) -> str:
        return self._language_name

    def _parse_file_impl(self, file_path: Path) -> ASTNodeList:
        """
        解析 Vue SFC 文件

        Args:
            file_path: Vue 文件路径

        Returns:
            ASTNodeList 包含所有提取的节点
        """
        try:
            if not file_path.exists():
                logger.warning("文件不存在: %s", file_path)
                return ASTNodeList()

            content = file_path.read_text(encoding="utf-8")

            nodes = ASTNodeList()

            script_blocks = self._extract_script_blocks(content)

            for _block_type, script_content in script_blocks:
                block_nodes = self._ts_parser.parse_content(script_content)

                for node in block_nodes.nodes:
                    node.file_path = str(file_path)
                    node.language = "vue"
                    nodes.add(node)

            self._tag_all_nodes(nodes)

            return nodes

        except Exception as exc:
            logger.error("解析 Vue 文件失败 %s: %s", file_path, exc)
            return ASTNodeList()

    def _extract_script_blocks(self, content: str) -> list[tuple[str, str]]:
        """
        提取所有 <script> 区块，区分 setup 和普通

        Returns:
            [(block_type, body), ...]
            block_type: "script_setup" 或 "script"
        """
        blocks = []

        script_pattern = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE)

        for match in script_pattern.finditer(content):
            attrs = match.group(1)
            body = match.group(2)

            block_type = "script_setup" if "setup" in attrs.lower() else "script"

            blocks.append((block_type, body.strip()))

        return blocks

    def _tag_setup_nodes(self, nodes: ASTNodeList) -> None:
        """
        同时处理 <script setup> 和 Options API：
        - defineProps/defineEmits/defineExpose → vue-component-api
        - ref/reactive/computed/watch/watchEffect → vue-composable
        - onMounted/onUnmounted 等生命周期 → vue-lifecycle
        - Options API 的 mounted/created 等 → vue-lifecycle
        - use[A-Z] 函数 → vue-composable
        """
        for node in nodes.nodes:
            if node.node_type == "call":
                call_name = node.name.split("(")[0].strip()
                if call_name in self._VUE_COMPONENT_API_CALLS:
                    node.tags.append("vue-component-api")
                elif call_name in self._VUE_COMPOSABLE_CALLS:
                    node.tags.append("vue-composable")
                elif call_name in self._VUE_LIFECYCLE_CALLS:
                    node.tags.append("vue-lifecycle")

            elif node.node_type == "function":
                self._tag_vue_function(node)

            elif node.node_type == "object_method":
                self._tag_vue_lifecycle_object_method(node)

    def _tag_all_nodes(self, nodes: ASTNodeList) -> None:
        """
        为所有节点打标签（同时处理 script 和 script_setup）

        在 _parse_file_impl 中调用，确保所有脚本区块的节点都被标记。
        """
        self._tag_setup_nodes(nodes)

    def _tag_vue_function(self, node: ASTNode) -> None:
        """
        为函数节点打 Vue 标签

        - use[A-Z] 开头的函数 → vue-composable（自定义 composable）
        """
        if len(node.name) >= 4 and node.name.startswith("use") and node.name[3].isupper():
            node.tags.append("vue-composable")

    def _tag_vue_lifecycle_object_method(self, node: ASTNode) -> None:
        """
        为 Options API 的对象方法打 Vue 生命周期标签

        - mounted/created/beforeMount/beforeCreate → vue-lifecycle
        """
        lifecycle_methods = {
            "mounted",
            "created",
            "beforeMount",
            "beforeCreate",
            "beforeUpdate",
            "updated",
            "beforeUnmount",
            "unmounted",
            "activated",
            "deactivated",
            "errorCaptured",
        }

        if node.name in lifecycle_methods:
            node.tags.append("vue-lifecycle")

    def parse_content(self, content: str) -> ASTNodeList:
        """
        解析字符串内容（用于测试等场景）

        Args:
            content: Vue SFC 内容

        Returns:
            ASTNodeList 包含所有提取的节点
        """
        nodes = ASTNodeList()

        script_blocks = self._extract_script_blocks(content)

        for block_type, script_content in script_blocks:
            block_nodes = self._ts_parser.parse_content(script_content)

            if block_type == "script_setup":
                self._tag_setup_nodes(block_nodes)

            for node in block_nodes.nodes:
                node.language = "vue"
                nodes.add(node)

        return nodes
