"""
模块依赖图构建器

将 AST 中的 import 节点关联到具体的文件，构建模块依赖图。

匹配策略：
1. 绝对导入：匹配文件路径前缀（如 import com.example 匹配 com/example/file.py）
2. 相对导入：基于导入者文件路径计算相对路径
3. 外部库：无法匹配到仓库内文件，标记为 "external"，imported_file_id = None
"""

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import async_session_factory
from codeinsight.models import AstNodeModel, FileModel
from codeinsight.repositories import AstNodeDAO, FileDAO, ModuleDependencyDAO

logger = logging.getLogger(__name__)


class ModuleDependencyBuilder:
    """
    模块依赖图构建器

    从 ast_nodes 表中的 import 节点和 files 表出发，构建模块依赖边（importer → imported）。
    """

    def __init__(self):
        self.ast_dao = AstNodeDAO()
        self.file_dao = FileDAO()
        self.dep_dao = ModuleDependencyDAO()

    async def build(
        self,
        repo_uuid: UUID,
        db: AsyncSession | None = None,
        dry_run: bool = False,
    ) -> int:
        """
        构建模块依赖图

        Args:
            repo_uuid: 仓库 UUID
            db: 可选的数据库会话。提供时复用；否则创建独立会话。
            dry_run: True 时不写入数据库，只返回依赖边列表长度

        Returns:
            创建的依赖边数量（dry_run 时返回计算出的边数量）
        """
        deps_data = await self.build_data(repo_uuid, db=db)

        if dry_run:
            logger.info("模块依赖构建 (dry_run): repo=%s, dependencies=%d", repo_uuid, len(deps_data))
            return len(deps_data)

        # 需要写入，使用独立 session
        use_context = db is None
        session = db
        if use_context:
            session = await async_session_factory().__aenter__()
        assert session is not None  # type narrowing for mypy

        try:
            await self.dep_dao.delete_by_repository(session, repo_uuid)
            if deps_data:
                await self.dep_dao.create_many(session, deps_data)
            await session.commit()
            logger.info("模块依赖构建完成: repo=%s, dependencies=%d", repo_uuid, len(deps_data))
            return len(deps_data)
        finally:
            if use_context:
                await session.__aexit__(None, None, None)

    async def build_data(self, repo_uuid: UUID, db: AsyncSession | None = None) -> list[dict]:
        """
        构建模块依赖数据（不写入数据库）

        用于 StructureDataPipeline 接管写入。

        Args:
            repo_uuid: 仓库 UUID
            db: 可选的数据库会话。提供时复用；否则创建独立会话。

        Returns:
            依赖边数据列表
        """
        use_context = db is None
        session = db
        if use_context:
            session = await async_session_factory().__aenter__()
        assert session is not None  # type narrowing for mypy

        try:
            # 1. 按需加载 import 节点和文件
            import_nodes = await self.ast_dao.get_by_repository_and_types(session, repo_uuid, {"import"})
            files = await self.file_dao.get_by_repository(session, repo_uuid)
            logger.info(
                "模块依赖数据构建: repo=%s, imports=%d, files=%d",
                repo_uuid,
                len(import_nodes),
                len(files),
            )

            # 2. 构建文件索引
            file_index = {f.path: f for f in files}
            file_index_reverse = {f.id: f.path for f in files}

            # 3. 构建依赖边
            return self._match_dependencies(import_nodes, file_index, file_index_reverse, repo_uuid)
        finally:
            if use_context:
                await session.__aexit__(None, None, None)

    async def build_data_for_files(
        self,
        repo_uuid: UUID,
        file_paths: list[str],
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """
        为指定文件构建模块依赖数据（不写入数据库）

        Args:
            repo_uuid: 仓库 UUID
            file_paths: 需要构建依赖的文件路径列表
            db: 可选的数据库会话。提供时复用；否则创建独立会话。

        Returns:
            依赖边数据列表
        """
        if not file_paths:
            logger.info("模块依赖增量构建: repo=%s, file_paths=0 (跳过)", repo_uuid)
            return []

        use_context = db is None
        session = db
        if use_context:
            session = await async_session_factory().__aenter__()
        assert session is not None

        try:
            # 增量构建：只加载需要文件的 import 节点和文件
            file_paths_set = set(file_paths)
            import_nodes = await self.ast_dao.get_by_repository_and_types(session, repo_uuid, {"import"})
            files = await self.file_dao.get_by_repository(session, repo_uuid)

            # 过滤：只保留目标文件的 import 节点和文件
            import_nodes = [n for n in import_nodes if n.file_path in file_paths_set]
            files = [f for f in files if f.path in file_paths_set]

            logger.info(
                "模块依赖增量构建: repo=%s, imports=%d, files=%d",
                repo_uuid,
                len(import_nodes),
                len(files),
            )

            file_index = {f.path: f for f in files}
            file_index_reverse = {f.id: f.path for f in files}

            return self._match_dependencies(import_nodes, file_index, file_index_reverse, repo_uuid)
        finally:
            if use_context:
                await session.__aexit__(None, None, None)

    def _match_dependencies(
        self,
        import_nodes: list[AstNodeModel],
        file_index: dict[str, FileModel],
        file_index_reverse: dict[UUID, str],
        repo_uuid: UUID,
    ) -> list[dict]:
        """
        匹配依赖边

        Args:
            import_nodes: import 类型节点列表
            file_index: 文件路径 → FileModel
            file_index_reverse: file_id → file_path
            repo_uuid: 仓库 UUID

        Returns:
            依赖边数据列表
        """
        deps_data = []

        for node in import_nodes:
            import_name = node.name.strip()
            importer_file_path = node.file_path

            # 解析导入名称为模块路径（去掉引号，替换 . 为 /）
            module_path = self._resolve_module_path(import_name, importer_file_path)

            # 匹配目标文件
            imported_file = self._find_imported_file(module_path, file_index, file_index_reverse)

            # 确定导入类型
            import_type = self._determine_import_type(import_name, imported_file, importer_file_path)

            deps_data.append(
                {
                    "repository_id": repo_uuid,
                    "importer_file_id": self._get_file_id_by_path(node.file_path, file_index),
                    "imported_file_id": imported_file.id if imported_file else None,
                    "import_name": import_name,
                    "import_type": import_type,
                }
            )

        return deps_data

    @staticmethod
    def _resolve_module_path(import_name: str, importer_path: str) -> str:
        """
        将导入名称解析为模块路径

        Args:
            import_name: 导入名称（如 "com.example" 或 "path"）
            importer_path: 导入者文件路径

        Returns:
            模块路径（如 "com/example" 或 "path"）
        """
        # 去掉引号
        module_path = import_name.strip("\"'")

        # 替换 . 为 /（Python/Java 风格）
        if "/" not in module_path:
            module_path = module_path.replace(".", "/")

        # 相对导入处理（如 "../utils"）
        if module_path.startswith("../") or module_path.startswith("./"):
            # 计算相对于导入者文件的实际路径
            importer_dir = str(Path(importer_path).parent)
            module_path = str(Path(importer_dir) / module_path)

        return module_path.replace("\\", "/")

    def _find_imported_file(
        self,
        module_path: str,
        file_index: dict[str, FileModel],
        file_index_reverse: dict[UUID, str],
    ) -> FileModel | None:
        """
        根据模块路径查找导入目标文件

        Args:
            module_path: 模块路径（如 "com/example"）
            file_index: 文件路径 → FileModel
            file_index_reverse: file_id → file_path

        Returns:
            FileModel 实例，找不到则返回 None
        """
        # 精确匹配
        if module_path in file_index:
            return file_index[module_path]

        # 前缀匹配（import com.example 可能匹配 com/example/file.py）
        for file_path, file_obj in file_index.items():
            if file_path.startswith(module_path + "/") or file_path.startswith(module_path.replace("/", ".")):
                return file_obj

        # 常见入口文件匹配（__init__.py, index.ts 等）
        entry_patterns = [
            f"{module_path}/__init__.py",
            f"{module_path}/__init__.ts",
            f"{module_path}/index.ts",
            f"{module_path}/index.js",
            f"{module_path}/index.py",
            f"{module_path}.py",
            f"{module_path}.ts",
            f"{module_path}.js",
        ]
        for pattern in entry_patterns:
            if pattern in file_index:
                return file_index[pattern]

        # 模糊匹配：模块路径作为文件路径的一部分
        for file_path in file_index:
            if module_path.replace("/", ".") in file_path or module_path in file_path:
                return file_index[file_path]

        return None

    @staticmethod
    def _determine_import_type(
        import_name: str,
        imported_file: FileModel | None,
        importer_path: str,
    ) -> str:
        """
        确定导入类型

        Args:
            import_name: 导入名称
            imported_file: 导入目标文件
            importer_path: 导入者文件路径

        Returns:
            "relative" / "absolute" / "external"
        """
        # 外部库：无法匹配到文件
        if imported_file is None:
            return "external"

        # 相对导入
        if import_name.startswith(".") or import_name.startswith(".."):
            return "relative"

        # 绝对导入
        return "absolute"

    @staticmethod
    def _get_file_id_by_path(file_path: str, file_index: dict[str, FileModel]) -> UUID:
        """根据文件路径获取 file_id"""
        if file_path in file_index:
            return file_index[file_path].id

        # 模糊匹配
        for path, file_obj in file_index.items():
            if file_path == path or file_path.endswith("/" + path):
                return file_obj.id

        # 如果找不到，返回占位 UUID（不应发生）
        raise ValueError(f"Could not find file_id for path: {file_path}")
