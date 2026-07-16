"""
模块依赖图构建器

将 AST 中的 import 节点关联到具体的文件，构建模块依赖图。

匹配策略：
1. 绝对导入：匹配文件路径前缀（如 import com.example 匹配 com/example/file.py）
2. 相对导入：基于导入者文件路径计算相对路径
3. 外部库：无法匹配到仓库内文件，标记为 "external"，imported_file_id = None
4. 外部依赖映射：将外部 import 关联到 external_dependencies 表中的具体依赖（种子规则 + 自动匹配）
"""

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import async_session_factory
from codeinsight.models import AstNodeModel, ExternalDependencyModel, FileModel
from codeinsight.repositories import AstNodeDAO, ExternalDependencyDAO, FileDAO, ModuleDependencyDAO

logger = logging.getLogger(__name__)


class SeedRuleRegistry:
    """
    种子规则注册表

    管理 import → 外部依赖的种子规则，支持按语言注册和匹配。
    每条种子规则为 (import_prefix, dependency_name, ecosystem, language) 元组。

    匹配策略按语言区分（由 _LANGUAGE_PROFILES 配置决定）：
    - "prefix" 风格：import 以规则前缀开头即匹配（Java 包名风格）
    - "module" 风格：import 与规则前缀精确相等，或以 "前缀+分隔符" 开头即匹配
      （TS/JS 用 "/"，Python 用 "."）

    扩展新语言：在 _LANGUAGE_PROFILES 增加语言配置后，调用 register() 添加规则即可，
    无需修改 ModuleDependencyBuilder._match_seed_rule。
    """

    # 语言配置：language -> (文件扩展名元组, 匹配风格, 模块分隔符)
    _LANGUAGE_PROFILES: dict[str, tuple[tuple[str, ...], str, str]] = {
        "java": ((".java", ".kt"), "prefix", ""),
        "typescript": ((".ts", ".tsx", ".js", ".jsx", ".vue"), "module", "/"),
        "python": ((".py",), "module", "."),
    }

    def __init__(self) -> None:
        # language -> [(import_prefix, dependency_name, ecosystem), ...]（保持注册顺序）
        self._rules: dict[str, list[tuple[str, str, str]]] = {}

    def register(self, language: str, import_prefix: str, dep_name: str, ecosystem: str) -> None:
        """
        注册一条种子规则

        Args:
            language: 语言标识（见 _LANGUAGE_PROFILES，如 "java"/"typescript"/"python"）
            import_prefix: import 前缀（如 "org.springframework" / "react" / "flask"）
            dep_name: 对应的外部依赖 artifact_name
            ecosystem: 依赖生态（如 "maven"/"npm"/"pip"）
        """
        self._rules.setdefault(language, []).append((import_prefix, dep_name, ecosystem))

    def match(self, import_name: str, file_path: str) -> str | None:
        """
        根据文件路径确定语言，匹配 import 到外部依赖名

        Args:
            import_name: import 名称（可为原始值，内部会做 strip + 小写归一化）
            file_path: 文件路径（用于按扩展名判断语言）

        Returns:
            匹配到的依赖 artifact_name，未匹配则返回 None
        """
        import_lower = import_name.strip().strip("\"'").lower()
        for language, profile in self._LANGUAGE_PROFILES.items():
            extensions, style, separator = profile
            if not file_path.endswith(extensions):
                continue
            for import_prefix, dep_name, _ecosystem in self._rules.get(language, []):
                prefix_lower = import_prefix.lower()
                if style == "prefix":
                    if import_lower.startswith(prefix_lower):
                        return dep_name
                else:  # module 风格：精确匹配或带分隔符的前缀匹配
                    if import_lower == prefix_lower or import_lower.startswith(prefix_lower + separator):
                        return dep_name
            # 语言已确定但未命中任何规则
            return None
        return None


def _build_default_seed_registry() -> SeedRuleRegistry:
    """构建默认种子规则注册表，注册所有内置种子规则"""
    registry = SeedRuleRegistry()
    # Java Maven 种子规则
    registry.register("java", "org.springframework", "spring-boot-starter", "maven")
    registry.register("java", "org.springframework.boot", "spring-boot-starter", "maven")
    registry.register("java", "org.springframework.web", "spring-boot-starter-web", "maven")
    registry.register("java", "org.springframework.data", "spring-boot-starter-data-jpa", "maven")
    registry.register("java", "jakarta.persistence", "spring-boot-starter-data-jpa", "maven")
    registry.register("java", "javax.persistence", "spring-boot-starter-data-jpa", "maven")
    registry.register("java", "lombok", "lombok", "maven")
    registry.register("java", "org.slf4j", "slf4j-api", "maven")
    registry.register("java", "org.apache.commons", "commons-lang3", "maven")
    registry.register("java", "com.fasterxml.jackson", "jackson-databind", "maven")
    registry.register("java", "org.junit", "junit", "maven")
    registry.register("java", "org.mockito", "mockito-core", "maven")
    registry.register("java", "org.mybatis", "mybatis", "maven")
    # TS/JS NPM 种子规则
    registry.register("typescript", "react", "react", "npm")
    registry.register("typescript", "react-dom", "react-dom", "npm")
    registry.register("typescript", "vue", "vue", "npm")
    registry.register("typescript", "@angular/core", "@angular/core", "npm")
    registry.register("typescript", "express", "express", "npm")
    registry.register("typescript", "koa", "koa", "npm")
    registry.register("typescript", "next", "next", "npm")
    registry.register("typescript", "axios", "axios", "npm")
    registry.register("typescript", "lodash", "lodash", "npm")
    registry.register("typescript", "typescript", "typescript", "npm")
    registry.register("typescript", "next/navigation", "next", "npm")
    registry.register("typescript", "next/router", "next", "npm")
    # Python Pip 种子规则
    registry.register("python", "flask", "flask", "pip")
    registry.register("python", "fastapi", "fastapi", "pip")
    registry.register("python", "django", "django", "pip")
    registry.register("python", "sqlalchemy", "sqlalchemy", "pip")
    registry.register("python", "pydantic", "pydantic", "pip")
    registry.register("python", "requests", "requests", "pip")
    registry.register("python", "numpy", "numpy", "pip")
    registry.register("python", "pandas", "pandas", "pip")
    registry.register("python", "pytest", "pytest", "pip")
    registry.register("python", "uvicorn", "uvicorn", "pip")
    registry.register("python", "redis", "redis", "pip")
    return registry


class ModuleDependencyBuilder:
    """
    模块依赖图构建器

    从 ast_nodes 表中的 import 节点和 files 表出发，构建模块依赖边（importer → imported）。

    Phase 5 增强：
    - 支持外部 import → external_dependencies 映射
    - 两级匹配策略：种子规则 + 自动匹配
    - 更新 external_dependencies.used_by_files 字段
    """

    # 类级共享种子规则注册表（懒加载，首次访问时注册所有内置种子规则）
    _seed_registry: SeedRuleRegistry | None = None

    def __init__(
        self,
        ext_dep_dao: ExternalDependencyDAO | None = None,
    ):
        self.ast_dao = AstNodeDAO()
        self.file_dao = FileDAO()
        self.dep_dao = ModuleDependencyDAO()
        self.ext_dep_dao = ext_dep_dao or ExternalDependencyDAO()
        # 持有种子规则注册表实例（首次构建时注册所有内置种子规则）
        self.seed_registry = self._ensure_seed_registry()

    @classmethod
    def _ensure_seed_registry(cls) -> SeedRuleRegistry:
        """
        获取（必要时构建）共享的种子规则注册表

        首次调用时通过 _build_default_seed_registry 注册所有内置种子规则，
        后续调用直接复用类级缓存实例。
        """
        if cls._seed_registry is None:
            cls._seed_registry = _build_default_seed_registry()
        return cls._seed_registry

    async def _get_session(self, db: AsyncSession | None = None, method_name: str = "") -> tuple[AsyncSession, bool]:
        """
        获取数据库会话（A-11 修复：提取重复的 session 管理模板）

        Args:
            db: 可选的数据库会话
            method_name: 调用方法名，用于日志警告

        Returns:
            (session, use_context) 元组，use_context 表示是否需要手动关闭
        """
        if db is None:
            db = await async_session_factory().__aenter__()
            use_context = True
            if method_name:
                logger.warning(
                    "%s: 未传入 db session，已创建新 session。建议调用方传入共享 session 以优化资源管理",
                    method_name,
                )
        else:
            use_context = False
        return db, use_context

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

        session, use_context = await self._get_session(db, "ModuleDependencyBuilder.build")

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
        Phase 5 增强：加载外部依赖表，用于 import → 外部依赖映射。

        Args:
            repo_uuid: 仓库 UUID
            db: 可选的数据库会话。提供时复用；否则创建独立会话。

        Returns:
            依赖边数据列表
        """
        session, use_context = await self._get_session(db, "ModuleDependencyBuilder.build_data")

        try:
            # 1. 按需加载 import 节点和文件
            import_nodes = await self.ast_dao.get_by_repository_and_types(session, repo_uuid, {"import"})
            files = await self.file_dao.get_by_repository(session, repo_uuid)
            # Phase 5: 加载外部依赖，用于 import → 依赖映射
            external_deps = await self.ext_dep_dao.get_by_repository(session, repo_uuid)
            logger.info(
                "模块依赖数据构建: repo=%s, imports=%d, files=%d, external_deps=%d",
                repo_uuid,
                len(import_nodes),
                len(files),
                len(external_deps),
            )

            # 2. 构建文件索引（A-4 优化：预构建前缀索引）
            file_index, prefix_index = self._build_file_indices(files)
            file_index_reverse = {f.id: f.path for f in files}
            # Phase 5: 构建外部依赖索引
            ext_dep_index = self._build_ext_dep_index(external_deps)

            # 3. 构建依赖边（含外部依赖映射）
            return self._match_dependencies(
                import_nodes, file_index, prefix_index, file_index_reverse, ext_dep_index, repo_uuid
            )
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

        session, use_context = await self._get_session(db, "ModuleDependencyBuilder.build_data_for_files")

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

            # A-4 优化：预构建前缀索引
            file_index, prefix_index = self._build_file_indices(files)
            file_index_reverse = {f.id: f.path for f in files}
            # Phase 5: 外部依赖索引（增量构建时加载全部外部依赖）
            external_deps = await self.ext_dep_dao.get_by_repository(session, repo_uuid)
            ext_dep_index = self._build_ext_dep_index(external_deps)

            return self._match_dependencies(
                import_nodes, file_index, prefix_index, file_index_reverse, ext_dep_index, repo_uuid
            )
        finally:
            if use_context:
                await session.__aexit__(None, None, None)

    def _match_dependencies(
        self,
        import_nodes: list[AstNodeModel],
        file_index: dict[str, FileModel],
        prefix_index: dict[str, list[str]],
        file_index_reverse: dict[UUID, str],
        ext_dep_index: dict[str, list[ExternalDependencyModel]],
        repo_uuid: UUID,
    ) -> list[dict]:
        """
        匹配依赖边

        Phase 5 增强：外部 import 映射到 external_dependencies（种子规则 + 自动匹配）。

        Args:
            import_nodes: import 类型节点列表
            file_index: 文件路径 → FileModel
            prefix_index: 路径前缀 → 文件路径列表（A-4 优化）
            file_index_reverse: file_id → file_path
            ext_dep_index: 外部依赖索引（artifact_name → [dep]）
            repo_uuid: 仓库 UUID

        Returns:
            依赖边数据列表
        """
        deps_data = []

        for node in import_nodes:
            import_name = node.name.strip()
            importer_file_path = node.file_path

            module_path = self._resolve_module_path(import_name, importer_file_path)

            imported_file = self._find_imported_file(module_path, file_index, prefix_index, file_index_reverse)

            import_type = self._determine_import_type(import_name, imported_file, importer_file_path)

            importer_file_id = self._get_file_id_by_path(node.file_path, file_index)
            if importer_file_id is None:
                logger.debug("跳过依赖：无法找到导入者文件路径: %s", node.file_path)
                continue

            # Phase 5: 外部依赖映射（仅对 external 类型的 import）
            if import_type == "external":
                matched_dep = self._match_import_to_external_dep(import_name, importer_file_path, ext_dep_index)
                if matched_dep:
                    # TODO: Phase 5 后续可扩展 module_dependencies 表添加 external_dependency_id 字段
                    pass

            deps_data.append(
                {
                    "repository_id": repo_uuid,
                    "importer_file_id": importer_file_id,
                    "imported_file_id": imported_file.id if imported_file else None,
                    "import_name": import_name,
                    "import_type": import_type,
                }
            )

        return deps_data

    @staticmethod
    def _build_file_indices(files: list[FileModel]) -> tuple[dict[str, FileModel], dict[str, list[str]]]:
        """
        构建文件索引

        A-4 优化：预构建精确索引和前缀索引，将 _find_imported_file 的复杂度从 O(n) 降至 O(1)。

        Args:
            files: 文件列表

        Returns:
            (精确索引, 前缀索引)
        """
        file_index: dict[str, FileModel] = {}
        prefix_index: dict[str, list[str]] = {}

        for f in files:
            file_index[f.path] = f

            parts = f.path.split("/")
            for i in range(1, len(parts) + 1):
                prefix = "/".join(parts[:i])
                prefix_index.setdefault(prefix, []).append(f.path)

        return file_index, prefix_index

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
        prefix_index: dict[str, list[str]],
        file_index_reverse: dict[UUID, str],
    ) -> FileModel | None:
        """
        根据模块路径查找导入目标文件

        A-4 优化：使用预构建的前缀索引替代线性扫描，将复杂度从 O(n) 降至 O(1)。
        A-8 修复：精确匹配优先，模糊匹配使用严格前缀规则。

        Args:
            module_path: 模块路径（如 "com/example"）
            file_index: 文件路径 → FileModel
            prefix_index: 路径前缀 → 文件路径列表
            file_index_reverse: file_id → file_path

        Returns:
            FileModel 实例，找不到则返回 None
        """
        # 1. 精确匹配（O(1)）
        if module_path in file_index:
            return file_index[module_path]

        # 2. 常见入口文件精确匹配（__init__.py, index.ts 等）（O(1)）
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

        # 3. 前缀匹配（O(1) 查找 + O(k) 候选过滤，k 通常很小）
        # 3a. 目录前缀（module_path/...）
        dir_prefix = module_path + "/"
        if dir_prefix in prefix_index:
            for file_path in prefix_index[dir_prefix]:
                return file_index[file_path]

        # 3b. 文件前缀（module_path.ext），如 "com/example/MyClass" 匹配 "com/example/MyClass.java"
        # 查找所有以 module_path 开头的前缀
        for prefix_key, file_paths in prefix_index.items():
            if prefix_key == module_path or (
                prefix_key.startswith(module_path) and prefix_key[len(module_path)] == "."
            ):
                for file_path in file_paths:
                    if file_path.startswith(module_path + "."):
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
    def _get_file_id_by_path(file_path: str, file_index: dict[str, FileModel]) -> UUID | None:
        """
        根据文件路径获取 file_id

        支持精确匹配和路径后缀匹配：
        - 精确匹配：file_path 与 file_index 的 key 完全一致
        - 后缀匹配：ast_nodes.file_path 可能是绝对路径（如 C:\\...\\src\\main.ts），
          而 file_index 的 key 可能是相对路径（如 main.ts 或 src/main.ts），
          通过路径后缀匹配进行关联。

        Args:
            file_path: AST 节点的文件路径（可能是绝对路径）
            file_index: 文件路径 → FileModel 索引（key 通常是相对路径）

        Returns:
            文件 ID，未找到则返回 None
        """
        # 1. 精确匹配
        if file_path in file_index:
            return file_index[file_path].id

        # 2. 路径后缀匹配（绝对路径 → 相对路径）
        normalized = file_path.replace("\\", "/")
        for key, file_model in file_index.items():
            normalized_key = key.replace("\\", "/")
            if normalized == normalized_key:
                return file_model.id
            # 绝对路径以相对路径结尾（如 .../src/main.ts 匹配 src/main.ts）
            if normalized.endswith("/" + normalized_key):
                return file_model.id

        return None

    @staticmethod
    def _build_ext_dep_index(
        ext_deps: list[ExternalDependencyModel],
    ) -> dict[str, list[ExternalDependencyModel]]:
        """
        构建外部依赖索引

        Phase 5: 构建 artifact_name → [dep] 映射，用于快速匹配 import 到外部依赖。

        Args:
            ext_deps: 外部依赖列表

        Returns:
            索引字典，key 为小写的 artifact_name 或 group/artifact 全名
        """
        index: dict[str, list[ExternalDependencyModel]] = {}
        for dep in ext_deps:
            art_key = dep.artifact_name.lower()
            index.setdefault(art_key, []).append(dep)
            if dep.group_name:
                full_key = f"{dep.group_name}/{dep.artifact_name}".lower()
                index.setdefault(full_key, []).append(dep)
                # 也用 group_name 作为前缀索引
                group_key = dep.group_name.lower()
                index.setdefault(group_key, []).append(dep)
        return index

    @staticmethod
    def _match_import_to_external_dep(
        import_name: str,
        importer_file_path: str,
        ext_dep_index: dict[str, list[ExternalDependencyModel]],
    ) -> ExternalDependencyModel | None:
        """
        将 import 匹配到外部依赖

        两级匹配策略：
        1. 种子规则匹配：硬编码的常见框架 import → 依赖映射
        2. 自动匹配：基于 external_dependencies 表的动态匹配

        Args:
            import_name: import 名称
            importer_file_path: 导入者文件路径（用于判断语言/生态）
            ext_dep_index: 外部依赖索引

        Returns:
            匹配到的外部依赖，未匹配则返回 None
        """
        import_clean = import_name.strip().strip("\"'")
        import_lower = import_clean.lower()

        # Level 1: 种子规则匹配
        seed_dep_name = ModuleDependencyBuilder._match_seed_rule(import_lower, importer_file_path)
        if seed_dep_name:
            # 在 ext_dep_index 中查找对应的依赖
            seed_key = seed_dep_name.lower()
            if seed_key in ext_dep_index:
                return ext_dep_index[seed_key][0]

        # Level 2: 自动匹配（基于 external_dependencies 表）
        # 精确匹配 artifact_name
        if import_lower in ext_dep_index:
            return ext_dep_index[import_lower][0]

        # 前缀匹配（Java 包名风格）
        for key, deps in ext_dep_index.items():
            if import_lower.startswith(key + ".") or import_lower.startswith(key + "/"):
                return deps[0]
            if key.startswith(import_lower + ".") or key.startswith(import_lower + "/"):
                return deps[0]

        return None

    @staticmethod
    def _match_seed_rule(import_lower: str, file_path: str) -> str | None:
        """
        通过种子规则匹配 import 到依赖名

        委托给 SeedRuleRegistry.match 完成按语言的注册表查找；
        新增语言只需在注册表中注册，无需修改本方法。

        Args:
            import_lower: 小写的 import 名
            file_path: 文件路径（用于判断语言）

        Returns:
            匹配到的依赖 artifact_name，未匹配则返回 None
        """
        return ModuleDependencyBuilder._ensure_seed_registry().match(import_lower, file_path)
