"""
填充测试数据脚本

用于开发/测试环境，快速生成真实感的数据以验证业务逻辑。
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import cast

# 添加项目根目录到 Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeinsight.db.engine import get_engine
from codeinsight.models import AstNodeModel, FileModel, RepositoryModel

# 模拟的测试仓库结构
TEST_REPOS = [
    {
        "name": "example-python-project",
        "path": "/workspace/example-python-project",
    },
    {
        "name": "example-typescript-project",
        "path": "/workspace/example-typescript-project",
    },
]


def fake_time(base: datetime, offset_hours: float = 0) -> datetime:
    """生成带有随机偏移的时间戳"""
    return base - timedelta(hours=offset_hours, minutes=int(offset_hours * 60 % 60))


def generate_files(repo_name: str) -> list[dict]:
    """为给定仓库生成模拟文件列表"""
    if "python" in repo_name:
        return [
            # 源码文件
            {"path": "src/__init__.py", "language": "python", "line_count": 3},
            {"path": "src/main.py", "language": "python", "line_count": 120},
            {"path": "src/app.py", "language": "python", "line_count": 250},
            {"path": "src/models/user.py", "language": "python", "line_count": 85},
            {"path": "src/models/article.py", "language": "python", "line_count": 130},
            {"path": "src/services/auth_service.py", "language": "python", "line_count": 200},
            {"path": "src/services/article_service.py", "language": "python", "line_count": 180},
            {"path": "src/api/routes.py", "language": "python", "line_count": 150},
            {"path": "src/utils/helpers.py", "language": "python", "line_count": 90},
            {"path": "src/utils/validators.py", "language": "python", "line_count": 60},
            # 测试文件
            {"path": "tests/__init__.py", "language": "python", "line_count": 1},
            {"path": "tests/test_main.py", "language": "python", "line_count": 45},
            {"path": "tests/test_models.py", "language": "python", "line_count": 120},
            {"path": "tests/test_services.py", "language": "python", "line_count": 200},
            {"path": "tests/test_api.py", "language": "python", "line_count": 90},
            # 配置和脚本
            {"path": "config.py", "language": "python", "line_count": 80},
            {"path": "requirements.txt", "language": "text", "line_count": 20},
            {"path": "setup.py", "language": "python", "line_count": 40},
        ]
    else:
        return [
            # 前端组件
            {"path": "src/index.ts", "language": "typescript", "line_count": 30},
            {"path": "src/App.tsx", "language": "typescript", "line_count": 150},
            {"path": "src/components/Header.tsx", "language": "typescript", "line_count": 80},
            {"path": "src/components/Sidebar.tsx", "language": "typescript", "line_count": 120},
            {"path": "src/components/Dashboard.tsx", "language": "typescript", "line_count": 200},
            {"path": "src/components/UserProfile.tsx", "language": "typescript", "line_count": 160},
            # Hooks
            {"path": "src/hooks/useAuth.ts", "language": "typescript", "line_count": 70},
            {"path": "src/hooks/useApi.ts", "language": "typescript", "line_count": 90},
            {"path": "src/hooks/useTheme.ts", "language": "typescript", "line_count": 50},
            # Pages
            {"path": "src/pages/LoginPage.tsx", "language": "typescript", "line_count": 100},
            {"path": "src/pages/HomePage.tsx", "language": "typescript", "line_count": 180},
            {"path": "src/pages/SettingsPage.tsx", "language": "typescript", "line_count": 140},
            # Utils
            {"path": "src/utils/format.ts", "language": "typescript", "line_count": 40},
            {"path": "src/utils/constants.ts", "language": "typescript", "line_count": 60},
            # Config
            {"path": "tsconfig.json", "language": "json", "line_count": 30},
            {"path": "package.json", "language": "json", "line_count": 45},
        ]


def generate_ast_nodes(repo_name: str, file: dict, repo_id: str, actual_file_id: uuid.UUID) -> list[dict]:
    """为单个文件生成模拟 AST 节点（真实树形结构）"""
    nodes: list[dict] = []
    # 定义每个文件类型的模拟结构
    # parent_name 是父节点的名称（用于 name_to_id 查找），None 表示顶级节点
    structures = {
        "python": {
            "service": [
                ("class", "UserService", None),
                ("method", "__init__", "UserService"),
                ("method", "get_user", "UserService"),
                ("method", "create_user", "UserService"),
                ("method", "update_user", "UserService"),
                ("method", "delete_user", "UserService"),
                ("method", "_validate", "UserService"),
                ("method", "_format_response", "UserService"),
            ],
            "models": [
                ("class", "User", None),
                ("method", "__init__", "User"),
                ("method", "to_dict", "User"),
                ("method", "from_dict", "User"),
                ("variable", "tablename", "User"),
                ("variable", "__table_args__", "User"),
            ],
            "tests": [
                ("class", "TestUserService", None),
                ("method", "test_get_user", "TestUserService"),
                ("method", "test_create_user", "TestUserService"),
                ("method", "test_delete_user", "TestUserService"),
                ("method", "setUp", "TestUserService"),
            ],
            "default": [
                ("function", "main", None),
                ("function", "_setup", None),
                ("function", "_process", None),
                ("function", "_cleanup", None),
            ],
        },
        "typescript": {
            "components": [
                ("class", "Header", None),
                ("method", "render", "Header"),
                ("variable", "state", "Header"),
                ("method", "_handleClick", "Header"),
                ("method", "_getStyles", "Header"),
                ("variable", "props", "Header"),
                ("method", "_validate", "Header"),
            ],
            "pages": [
                ("class", "LoginPage", None),
                ("method", "render", "LoginPage"),
                ("method", "_handleSubmit", "LoginPage"),
                ("method", "_handleError", "LoginPage"),
                ("variable", "state", "LoginPage"),
            ],
            "hooks": [
                ("function", "useAuth", None),
                ("variable", "authState", "useAuth"),
                ("function", "login", "useAuth"),
                ("function", "logout", "useAuth"),
            ],
            "default": [
                ("function", "init", None),
                ("function", "_helper", None),
                ("function", "_format", None),
            ],
        },
    }

    lang = file["language"]
    path = file["path"]

    if lang not in structures:
        return nodes

    # 确定使用哪种结构模板
    use_key = "default"
    for key in ["service", "models", "tests", "components", "pages", "hooks"]:
        if key in path:
            use_key = key
            break

    template: list[tuple[str, str, str | None]] = cast(
        "list[tuple[str, str, str | None]]",
        structures[lang].get(use_key, structures[lang]["default"]),
    )

    # 建立名称到节点 ID 的映射（用于 parent 查找）
    name_to_id: dict[str, uuid.UUID] = {}

    for i, (ntype, name, parent_name) in enumerate(template):
        node_id = uuid.uuid4()
        parent_id = name_to_id.get(parent_name) if parent_name else None

        nodes.append(
            {
                "id": node_id,
                "repository_id": repo_id,
                "file_id": actual_file_id,
                "node_type": ntype,
                "name": name,
                "start_line": 5 + i * 20,
                "end_line": 25 + i * 20,
                "start_column": 1,
                "end_column": 50,
                "parent_node_id": parent_id,
                "file_path": file["path"],
                "language": file["language"],
                "signature": f"{ntype} {name}()",
                "docstring": f"This is a test {ntype}: {name} in {file['path']}",
                "created_at": datetime.now(),
            }
        )
        # 用名称注册以便子节点引用
        name_to_id[name] = node_id

    return nodes


async def seed_database():
    """主入口：填充所有测试数据"""
    engine = get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        now = datetime.now()  # 数据库使用 TIMESTAMP WITHOUT TIME ZONE，传入 naive datetime

        # 1. 创建仓库
        repos = []
        for repo_info in TEST_REPOS:
            repo = RepositoryModel(
                id=uuid.uuid4(),
                name=repo_info["name"],
                path=repo_info["path"],
                status="completed",
                file_count=0,
                line_count=0,
                knowledge_points_count=0,
                created_at=now,
                updated_at=now,
            )
            session.add(repo)
            repos.append(repo)

        await session.commit()
        await session.refresh(repos[0])
        await session.refresh(repos[1])

        # 2. 创建文件和 AST 节点
        total_files = 0
        total_nodes = 0

        for repo, repo_info in zip(repos, TEST_REPOS, strict=True):
            files = generate_files(repo_info["name"])
            repo.file_count = len(files)
            total_files += len(files)

            # 第一阶段：添加所有文件并 flush（生成数据库 ID）
            file_models = []
            for file_info in files:
                file_id = uuid.uuid4()
                abs_path = os.path.join(repo.path, file_info["path"])
                file_model = FileModel(
                    id=file_id,
                    repository_id=repo.id,
                    path=file_info["path"],
                    absolute_path=abs_path,
                    language=file_info["language"],
                    line_count=file_info["line_count"],
                    size_bytes=file_info["line_count"] * 50,  # 模拟文件大小
                    content_hash=f"hash_{uuid.uuid4().hex[:16]}",
                    created_at=now,
                    updated_at=now,
                )
                session.add(file_model)
                file_models.append((file_info, file_id, file_model))

            # Flush 文件到数据库（外键约束需要）
            await session.flush()

            # 第二阶段：添加 AST 节点（分阶段插入以满足外键约束）
            for file_info, file_id, _ in file_models:
                nodes = generate_ast_nodes(repo_info["name"], file_info, repo.id, file_id)

                # 阶段 2a：先插入父节点（parent_node_id=None）
                parent_nodes = [n for n in nodes if n["parent_node_id"] is None]
                for node_data in parent_nodes:
                    node = AstNodeModel(**node_data)
                    session.add(node)
                total_nodes += len(parent_nodes)
                await session.flush()  # 让父节点 ID 可用

                # 阶段 2b：再插入子节点（parent_node_id 已存在）
                child_nodes = [n for n in nodes if n["parent_node_id"] is not None]
                for node_data in child_nodes:
                    node = AstNodeModel(**node_data)
                    session.add(node)
                    total_nodes += 1

            # 提交文件和 AST 节点
            repo.line_count = sum(f["line_count"] for f in files)
            await session.commit()

    print("✅ 测试数据填充完成！")
    print(f"   仓库数: {len(TEST_REPOS)}")
    print(f"   文件数: {total_files}")
    print(f"   AST 节点数: {total_nodes}")


if __name__ == "__main__":
    print("🚀 开始填充测试数据...")
    asyncio.run(seed_database())
