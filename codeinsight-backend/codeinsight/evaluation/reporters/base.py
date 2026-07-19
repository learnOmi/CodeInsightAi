"""报告输出器基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeinsight.evaluation.engine import EvalReport


class Reporter(ABC):
    """报告输出器基类"""

    @abstractmethod
    async def report(self, report: EvalReport) -> None:
        """输出报告

        Args:
            report: 评估报告
        """
        ...
