"""
导出 FastAPI 应用的 OpenAPI schema 到 JSON 文件

使用方式：
    uv run python scripts/export_openapi.py

输出：
    packages/shared/src/openapi.json
"""

import json
import os
import sys


def export_openapi():
    # 确保后端目录在 Python 路径中
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 导入 FastAPI 应用
    from codeinsight.main import app

    # 获取 OpenAPI schema
    openapi_schema = app.openapi()

    # 输出到 packages/shared/src/openapi.json
    monorepo_root = os.path.dirname(project_root)
    output_path = os.path.join(monorepo_root, "packages", "shared", "src", "openapi.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, ensure_ascii=False, indent=2)

    print(f"OpenAPI schema 已导出到: {output_path}")
    print(f"路径数量: {len(openapi_schema.get('paths', {}))}")
    print(f"Schema 数量: {len(openapi_schema.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    export_openapi()
