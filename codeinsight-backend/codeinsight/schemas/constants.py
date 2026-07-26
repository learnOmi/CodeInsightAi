"""
知识点分类常量

集中管理分类名称映射，避免重复定义。
"""

CATEGORY_NAMES: dict[str, str] = {
    "DP": "设计模式",
    "AD": "架构设计",
    "AL": "算法实现",
    "ET": "工程技术",
    "DK": "领域知识",
    "TT": "开发模板",
    "TK": "技术栈",
    "DS": "设计结构",
}

CATEGORY_LIST: list[str] = ["DP", "AD", "AL", "ET", "DK", "TT", "TK", "DS"]
