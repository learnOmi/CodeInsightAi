"""
LLM 自定义异常

定义与大模型交互相关的业务异常类。
"""

from __future__ import annotations


class LLMError(Exception):
    """
    LLM 调用异常

    当与大语言模型交互失败时抛出，包含详细的上下文信息。
    """

    def __init__(self, message: str, provider: str = "", model: str = ""):
        self.message = message
        self.provider = provider
        self.model = model
        super().__init__(f"LLM error [{provider}/{model}]: {message}")
