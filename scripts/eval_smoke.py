#!/usr/bin/env python3
"""
评估框架冒烟测试

用于 pre-commit hook，快速验证评估框架是否能正常导入和运行。
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the backend package is on the path.
_project_root = Path(__file__).resolve().parent.parent
_backend_root = _project_root / "codeinsight-backend"
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

try:
    from codeinsight.evaluation.engine import EvalConfig, EvalEngine  # noqa: E402

    print("[OK] 评估框架导入成功")
    sys.exit(0)
except Exception as exc:  # noqa: BLE001
    print(f"[FAIL] 评估框架导入失败: {exc}", file=sys.stderr)
    sys.exit(1)
