"""
调用图构建器

将 AST 中的 call 节点关联到函数定义节点，构建完整的调用图。

匹配策略（三级降级）：
1. qualified_name 精确匹配：优先按限定名匹配（最精确）
2. 方法名匹配：按函数名/方法名匹配（当前行为，支持重载）
3. 外部依赖匹配：无法匹配到内部函数时，检查是否为外部依赖调用
4. 动态调用：getattr/反射等标记为 "dynamic"
5. 未知调用：无法匹配，标记为 "unknown"，callee_node_id = None

调用类型：
- static: 确定的内部函数调用
- dynamic: 反射/动态调用
- unknown: 无法匹配的调用
- external: 外部依赖调用
- injected: 依赖注入调用

扩展性设计：
- DiAnnotationRegistry：DI 注解可注册集合，替代硬编码 frozenset
- CallSeedRuleRegistry：种子依赖规则注册表，替代硬编码语言字典
- CallMatchStrategy：调用匹配策略链（Chain of Responsibility），替代 if-elif 判断
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import async_session_factory
from codeinsight.models import AstNodeModel
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO, ExternalDependencyDAO

logger = logging.getLogger(__name__)

# 函数类型：可作为被调用目标
_CALLABLE_NODE_TYPES: set[str] = {"function", "method", "constructor"}

# 动态调用模式（精确匹配，不匹配 obj.getattr(x)）
_DYNAMIC_CALL_NAMES = frozenset({"getattr", "setattr", "delattr", "hasattr", "__getattr__"})

# 依赖注入相关 tag（用于检测注入调用）
_DI_TAGS: frozenset[str] = frozenset({"dependency-injection", "spring-component", "business-service"})


# ============================================================
# 依赖注入注解注册表
# ============================================================


class DiAnnotationRegistry:
    """
    依赖注入注解注册表

    管理 DI 注解/装饰器名称的可注册集合，替代原先硬编码的 frozenset。
    扩展新注解只需调用 register()，无需修改匹配逻辑。

    默认注解（在 _build_default_di_annotation_registry 中注册）：
    @Autowired / @Inject / @Resource / @Injectable / @Component /
    @Service / @Repository / @Controller / @RestController
    """

    def __init__(self) -> None:
        self._annotations: set[str] = set()

    def register(self, annotation_name: str) -> None:
        """
        注册一个依赖注入注解/装饰器名称

        Args:
            annotation_name: 注解名称（如 "@Autowired"）
        """
        self._annotations.add(annotation_name)

    def contains(self, annotation_name: str) -> bool:
        """
        判断注解是否已注册

        Args:
            annotation_name: 注解名称

        Returns:
            是否已注册
        """
        return annotation_name in self._annotations


def _build_default_di_annotation_registry() -> DiAnnotationRegistry:
    """构建默认 DI 注解注册表，注册所有内置注解"""
    registry = DiAnnotationRegistry()
    for annotation in (
        "@Autowired",
        "@Inject",
        "@Resource",
        "@Injectable",
        "@Component",
        "@Service",
        "@Repository",
        "@Controller",
        "@RestController",
    ):
        registry.register(annotation)
    return registry


# ============================================================
# 调用图种子规则注册表
# ============================================================


class CallSeedRuleRegistry:
    """
    调用图种子规则注册表

    管理 import → 外部依赖的种子规则，支持按语言注册和按对象名匹配。
    采用与 module_graph.SeedRuleRegistry 相似的注册机制，但匹配策略不同：
    通过对象名（qualified_name 的首段）匹配 import 前缀的最后一段，
    用于将方法调用（obj.method）的对象名关联到外部依赖。

    语言配置（_LANGUAGE_PROFILES）：language -> (文件扩展名元组, 模块分隔符)
    - "java": 分隔符 "."，匹配 import 前缀的最后一段（如 org.springframework → springframework）
    - "typescript": 分隔符 "/"，匹配 import 路径的最后一段（如 @angular/core → core）
    - "python": 分隔符 "."，匹配 import 路径的最后一段（如 flask → flask）

    扩展新语言：在 _LANGUAGE_PROFILES 增加语言配置后，调用 register() 添加规则即可，
    无需修改 match_by_object_name。
    """

    # 语言配置：language -> (文件扩展名元组, 模块分隔符)
    _LANGUAGE_PROFILES: dict[str, tuple[tuple[str, ...], str]] = {
        "java": ((".java", ".kt"), "."),
        "typescript": ((".ts", ".tsx", ".js", ".jsx", ".vue"), "/"),
        "python": ((".py",), "."),
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

    def match_by_object_name(self, obj_name: str, file_path: str) -> str | None:
        """
        根据文件路径确定语言，按对象名匹配 import 到外部依赖名

        匹配策略：取 import_prefix 按语言分隔符切分后的最后一段，与 obj_name 比较。
        替代原先 _match_seed_dependency 中按语言 if-elif 判断的硬编码逻辑。

        Args:
            obj_name: 对象名（来自 call 节点 qualified_name 的首段）
            file_path: 文件路径（用于按扩展名判断语言）

        Returns:
            匹配到的依赖 artifact_name，未匹配则返回 None
        """
        obj_lower = obj_name.strip().lower()
        for language, profile in self._LANGUAGE_PROFILES.items():
            extensions, separator = profile
            if not file_path.endswith(extensions):
                continue
            for import_prefix, dep_name, _ecosystem in self._rules.get(language, []):
                last_segment = import_prefix.lower().rsplit(separator, 1)[-1]
                if obj_lower == last_segment:
                    return dep_name
            # 语言已确定但未命中任何规则
            return None
        return None


def _build_default_call_seed_registry() -> CallSeedRuleRegistry:
    """构建默认调用图种子规则注册表，注册所有内置种子规则"""
    registry = CallSeedRuleRegistry()
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
    return registry


# ============================================================
# 调用匹配策略（Chain of Responsibility）
# ============================================================


@dataclass
class CallEdge:
    """
    调用匹配结果

    由各匹配策略返回，封装候选节点列表和调用类型。
    """

    # 匹配到的内部函数候选节点（可为空，表示未匹配到内部函数）
    candidates: list[AstNodeModel] = field(default_factory=list)
    # 调用类型：static / dynamic / external / injected / unknown
    call_type: str = "static"
    # 外部依赖名（仅 external 类型时填充，如 "react.useState"）
    external_dep_name: str | None = None


@dataclass
class CallMatchContext:
    """
    调用匹配上下文

    封装各匹配策略所需的共享数据，避免策略方法参数过多。
    """

    function_index: dict[str, list[AstNodeModel]]
    qualified_index: dict[str, AstNodeModel]
    import_index: dict[UUID, list[AstNodeModel]]
    ext_dep_index: dict[str, list]
    enclosing_func: AstNodeModel | None
    caller_node_id: UUID
    repo_uuid: UUID


class CallMatchStrategy(Protocol):
    """
    调用匹配策略协议

    每个策略负责一种匹配级别，返回 CallEdge 或 None。
    _match_call_edges 按优先级遍历策略链，首个非 None 结果生效。
    新增匹配级别只需实现本 Protocol 并加入策略链，无需修改既有匹配逻辑。
    """

    def match(
        self,
        call_node: AstNodeModel,
        call_name: str,
        method_name: str,
        is_method_call: bool,
        context: CallMatchContext,
    ) -> CallEdge | None:
        """
        匹配调用节点

        Args:
            call_node: call 类型节点
            call_name: 原始调用名（含 "*." / "new " 前缀）
            method_name: 方法名（已去掉 "*." 前缀）
            is_method_call: 是否为方法调用（*.method）
            context: 匹配上下文

        Returns:
            匹配结果，未匹配则返回 None（交由下一策略处理）
        """
        ...


class QualifiedNameMatchStrategy:
    """
    Level 1: qualified_name 精确匹配策略

    对于方法调用（*.method），从 call_node.qualified_name 提取对象限定名，
    推断类名后在 qualified_index 中查找。
    对于普通调用，直接用 call_node.qualified_name 精确匹配。
    """

    def match(
        self,
        call_node: AstNodeModel,
        call_name: str,
        method_name: str,
        is_method_call: bool,
        context: CallMatchContext,
    ) -> CallEdge | None:
        candidates = self._match_by_qualified_name(call_node, method_name, context.qualified_index, is_method_call)
        if candidates:
            return CallEdge(candidates=candidates, call_type="static")
        return None

    @staticmethod
    def _match_by_qualified_name(
        call_node: AstNodeModel,
        method_name: str,
        qualified_index: dict[str, AstNodeModel],
        is_method_call: bool,
    ) -> list[AstNodeModel]:
        """
        通过 qualified_name 精确匹配

        对于方法调用（*.method），尝试从 call_node.qualified_name 中提取
        对象限定名，再与方法名拼接成完整的 qualified_name 进行匹配。

        Args:
            call_node: call 节点
            method_name: 方法名（已去掉 "*." 前缀）
            qualified_index: qualified_name 索引
            is_method_call: 是否为方法调用

        Returns:
            匹配到的候选节点列表（空列表表示未匹配）
        """
        if not is_method_call:
            qname = call_node.qualified_name or ""
            if qname and qname in qualified_index:
                return [qualified_index[qname]]
            return []

        # 方法调用：从 call_node.qualified_name 提取对象部分
        call_qname = call_node.qualified_name or ""
        if not call_qname or "." not in call_qname:
            return []

        # call_qname 格式可能是 "obj.method" 或 "this.field.method"
        # 提取对象变量名，尝试常见的类名推断
        parts = call_qname.split(".")
        if len(parts) < 2:
            return []

        obj_var = parts[0].strip()
        if obj_var == "this" and len(parts) >= 3:
            obj_var = parts[1].strip()

        if not obj_var:
            return []

        # 从 enclosing function 的 qualified_name 中提取类名上下文
        # 这里简化处理：尝试多种可能的 qualified_name 模式
        guessed_class = obj_var[0].upper() + obj_var[1:] if obj_var else ""

        # 遍历 qualified_index，查找包含 guessed_class 且以 method_name 结尾的项
        candidates = []
        for qname, node in qualified_index.items():
            if qname.endswith("." + method_name) and guessed_class in qname:
                candidates.append(node)

        return candidates


class MethodNameMatchStrategy:
    """
    Level 2: 方法名匹配策略（降级）

    按函数名/方法名匹配，支持重载和方法调用的多候选消歧。
    """

    def match(
        self,
        call_node: AstNodeModel,
        call_name: str,
        method_name: str,
        is_method_call: bool,
        context: CallMatchContext,
    ) -> CallEdge | None:
        candidates: list[AstNodeModel] = []
        if is_method_call:
            all_candidates = context.function_index.get(method_name, [])
            candidates = CallGraphBuilder._disambiguate_candidates(call_node, all_candidates)
        elif call_name.startswith("new "):
            class_name = call_name[4:]
            candidates = context.function_index.get(class_name, [])
        else:
            candidates = context.function_index.get(call_name, [])

        if candidates:
            return CallEdge(candidates=candidates, call_type="static")
        return None


class ExternalDepMatchStrategy:
    """
    Level 3: 外部依赖匹配策略（再降级）

    通过文件的 import 节点，判断调用是否来自外部依赖。
    匹配顺序：1) import → external_dependencies 表  2) 种子规则注册表
    """

    def __init__(self, seed_registry: CallSeedRuleRegistry) -> None:
        self._seed_registry = seed_registry

    def match(
        self,
        call_node: AstNodeModel,
        call_name: str,
        method_name: str,
        is_method_call: bool,
        context: CallMatchContext,
    ) -> CallEdge | None:
        external_dep_name = self._match_external_dependency(
            call_node,
            method_name,
            context.import_index,
            context.ext_dep_index,
            is_method_call,
        )
        if external_dep_name:
            return CallEdge(call_type="external", external_dep_name=external_dep_name)
        return None

    def _match_external_dependency(
        self,
        call_node: AstNodeModel,
        method_name: str,
        import_index: dict[UUID, list[AstNodeModel]],
        ext_dep_index: dict[str, list],
        is_method_call: bool,
    ) -> str | None:
        """
        外部依赖匹配

        通过文件的 import 节点，判断调用是否来自外部依赖。

        匹配逻辑：
        1. 获取当前文件的所有 import
        2. 对于方法调用（obj.method），检查 obj 是否匹配某个 import 的模块名
        3. 检查 import 模块名是否匹配 external_dependencies 表中的依赖

        Args:
            call_node: call 节点
            method_name: 方法名
            import_index: 文件级 import 索引
            ext_dep_index: 外部依赖索引
            is_method_call: 是否为方法调用

        Returns:
            外部依赖名称（如 "react.useState"），无法匹配则返回 None
        """
        if not is_method_call or not call_node.file_id:
            return None

        file_imports = import_index.get(call_node.file_id, [])
        if not file_imports:
            return None

        # 从 call_node.qualified_name 提取对象名
        call_qname = call_node.qualified_name or ""
        if not call_qname or "." not in call_qname:
            return None

        obj_name = call_qname.split(".")[0].strip()
        if not obj_name:
            return None

        # 检查 import 中是否有匹配的模块
        for imp in file_imports:
            import_name = imp.name.strip().strip("\"'")
            # 提取 import 的最后一段作为对象名
            import_parts = import_name.replace("/", ".").split(".")
            import_last = import_parts[-1] if import_parts else ""

            if obj_name.lower() == import_last.lower():
                # 找到匹配的 import，检查是否为外部依赖
                dep_name = self._find_external_dep(import_name, ext_dep_index)
                if dep_name:
                    return f"{dep_name}.{method_name}"

        # 种子规则匹配（注册表查找，按语言区分，替代原先 if-elif 语言判断）
        dep_from_seed = self._seed_registry.match_by_object_name(obj_name, call_node.file_path or "")
        if dep_from_seed:
            return f"{dep_from_seed}.{method_name}"

        return None

    @staticmethod
    def _find_external_dep(import_name: str, ext_dep_index: dict[str, list]) -> str | None:
        """
        在外部依赖索引中查找匹配的依赖

        Args:
            import_name: import 模块名
            ext_dep_index: 外部依赖索引

        Returns:
            匹配到的依赖名称，未匹配则返回 None
        """
        import_lower = import_name.lower()

        # 精确匹配
        if import_lower in ext_dep_index:
            deps = ext_dep_index[import_lower]
            if deps:
                dep_name: str = deps[0].artifact_name
                return dep_name

        # 前缀匹配（Java 包名风格：org.springframework.web → spring-boot-starter-web）
        for key, deps in ext_dep_index.items():
            if (import_lower.startswith(key + ".") or key.startswith(import_lower + ".")) and deps:
                dep_name = str(deps[0].artifact_name)
                return dep_name

        return None


class InjectedCallMatchStrategy:
    """
    Level 4: 依赖注入调用检测策略

    通过检查 enclosing function 所在类的注解/装饰器是否包含 DI 注解，
    判断是否为依赖注入调用。注解通过 DiAnnotationRegistry 查找，可扩展。
    """

    def __init__(self, di_registry: DiAnnotationRegistry) -> None:
        self._di_registry = di_registry

    def match(
        self,
        call_node: AstNodeModel,
        call_name: str,
        method_name: str,
        is_method_call: bool,
        context: CallMatchContext,
    ) -> CallEdge | None:
        if self._is_injected_call(context.enclosing_func):
            return CallEdge(call_type="injected")
        return None

    def _is_injected_call(self, enclosing_func: AstNodeModel | None) -> bool:
        """
        判断是否为依赖注入调用

        通过检查 enclosing function 所在类的注解/装饰器是否包含 DI 注解。

        Args:
            enclosing_func: 包含该调用的函数/方法节点

        Returns:
            是否为依赖注入调用
        """
        if enclosing_func is None:
            return False

        # 检查 enclosing function 本身的注解（通过注册表查找）
        annotations = getattr(enclosing_func, "annotations", None) or []
        for ann in annotations:
            ann_name = ann.get("name", "") if isinstance(ann, dict) else str(ann)
            if self._di_registry.contains(ann_name):
                return True

        # 检查 enclosing function 的 tags
        tags = getattr(enclosing_func, "tags", None) or []
        return any(tag in _DI_TAGS for tag in tags)


# ============================================================
# CallGraphBuilder
# ============================================================


class CallGraphBuilder:
    """
    调用图构建器

    从 ast_nodes 表中的 call 节点和函数定义节点出发，构建调用边（caller → callee）。

    扩展性设计：
    - DI 注解通过 DiAnnotationRegistry 注册，新增注解无需修改匹配逻辑
    - 种子依赖规则通过 CallSeedRuleRegistry 注册，新增语言/规则无需修改匹配逻辑
    - 调用匹配通过策略链（CallMatchStrategy）扩展，新增匹配级别只需实现 Protocol 并加入链
    """

    # 类级共享注册表（懒加载，首次访问时注册所有内置规则）
    _di_annotation_registry: DiAnnotationRegistry | None = None
    _call_seed_registry: CallSeedRuleRegistry | None = None

    def __init__(
        self,
        ast_dao: AstNodeDAO | None = None,
        call_edge_dao: CallEdgeDAO | None = None,
        ext_dep_dao: ExternalDependencyDAO | None = None,
    ):
        self.ast_dao = ast_dao or AstNodeDAO()
        self.call_edge_dao = call_edge_dao or CallEdgeDAO()
        self.ext_dep_dao = ext_dep_dao or ExternalDependencyDAO()
        # 初始化注册表（懒加载共享实例）
        self._di_annotations = self._ensure_di_annotation_registry()
        self._seed_registry = self._ensure_call_seed_registry()
        # 构建匹配策略链（按优先级排序：qualified_name → method name → external dep → injected）
        self._match_strategies: list[CallMatchStrategy] = [
            QualifiedNameMatchStrategy(),
            MethodNameMatchStrategy(),
            ExternalDepMatchStrategy(self._seed_registry),
            InjectedCallMatchStrategy(self._di_annotations),
        ]

    @classmethod
    def _ensure_di_annotation_registry(cls) -> DiAnnotationRegistry:
        """
        获取（必要时构建）共享的 DI 注解注册表

        首次调用时通过 _build_default_di_annotation_registry 注册所有内置注解，
        后续调用直接复用类级缓存实例。
        """
        if cls._di_annotation_registry is None:
            cls._di_annotation_registry = _build_default_di_annotation_registry()
        return cls._di_annotation_registry

    @classmethod
    def _ensure_call_seed_registry(cls) -> CallSeedRuleRegistry:
        """
        获取（必要时构建）共享的调用图种子规则注册表

        首次调用时通过 _build_default_call_seed_registry 注册所有内置种子规则，
        后续调用直接复用类级缓存实例。
        """
        if cls._call_seed_registry is None:
            cls._call_seed_registry = _build_default_call_seed_registry()
        return cls._call_seed_registry

    async def build(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
        dry_run: bool = False,
    ) -> int:
        """
        构建调用图

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话（由调用者管理生命周期）
            dry_run: True 时不写入数据库，只返回调用边列表长度

        Returns:
            创建的调用边数量（dry_run 时返回计算出的边数量）
        """
        edges_data = await self.build_data(repo_uuid, db=db)

        if dry_run:
            logger.info("调用图构建 (dry_run): repo=%s, edges=%d", repo_uuid, len(edges_data))
            return len(edges_data)

        await self.call_edge_dao.delete_by_repository(db, repo_uuid)
        if edges_data:
            await self.call_edge_dao.create_many(db, edges_data)
        logger.info("调用图构建完成: repo=%s, edges=%d", repo_uuid, len(edges_data))
        return len(edges_data)

    async def build_data(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
        file_ids: list[UUID] | None = None,
    ) -> list[dict]:
        """
        构建调用图数据（不写入数据库）

        A-1 修复：支持 file_ids 过滤，避免全量加载所有节点。
        Phase 5 增强：添加 qualified_name 精确匹配和外部依赖匹配。

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话
            file_ids: 可选的文件 ID 列表，限制查询范围（增量分析用）

        Returns:
            调用边数据列表
        """
        call_nodes = await self.ast_dao.get_by_repository_and_types(db, repo_uuid, {"call"}, file_ids=file_ids)
        function_nodes = await self.ast_dao.get_by_repository_and_types(
            db, repo_uuid, _CALLABLE_NODE_TYPES, file_ids=file_ids
        )
        import_nodes = await self.ast_dao.get_by_repository_and_types(db, repo_uuid, {"import"}, file_ids=file_ids)
        ext_deps = await self.ext_dep_dao.get_by_repository(db, repo_uuid)

        logger.info(
            "调用图数据构建: repo=%s, file_ids=%s, calls=%d, functions=%d, imports=%d, ext_deps=%d",
            repo_uuid,
            len(file_ids) if file_ids else "all",
            len(call_nodes),
            len(function_nodes),
            len(import_nodes),
            len(ext_deps),
        )

        function_index = self._build_function_index(function_nodes)
        qualified_index = self._build_qualified_index(function_nodes)
        import_index = self._build_import_index(import_nodes)
        ext_dep_index = self._build_external_dep_index(ext_deps)

        return self._match_call_edges(
            call_nodes,
            function_index,
            qualified_index,
            import_index,
            ext_dep_index,
            repo_uuid,
        )

    async def build_data_for_files(
        self,
        repo_uuid: UUID,
        db: AsyncSession,
        file_ids: list[UUID] | None = None,
    ) -> list[dict]:
        """
        为指定文件构建调用图数据（增量分析用）

        A-1 修复：已委托给 build_data，统一使用 file_ids 过滤。

        Args:
            repo_uuid: 仓库 UUID
            db: 数据库会话
            file_ids: 需要构建调用图的文件 ID 列表（None 时等同于全量 build_data）

        Returns:
            调用边数据列表
        """
        if file_ids is None:
            return await self.build_data(repo_uuid, db=db)

        if not file_ids:
            logger.info("调用图增量构建: repo=%s, file_ids=0 (跳过)", repo_uuid)
            return []

        return await self.build_data(repo_uuid, db=db, file_ids=file_ids)

    @staticmethod
    def _build_function_index(function_nodes: list[AstNodeModel]) -> dict[str, list[AstNodeModel]]:
        """
        构建函数名索引

        支持函数重载：name → [node] 映射。
        """
        index: dict[str, list[AstNodeModel]] = {}
        for node in function_nodes:
            index.setdefault(node.name, []).append(node)
        return index

    @staticmethod
    def _build_qualified_index(function_nodes: list[AstNodeModel]) -> dict[str, AstNodeModel]:
        """
        构建 qualified_name 索引

        qualified_name 唯一映射到单个函数节点（精确匹配用）。
        空 qualified_name 的节点不加入索引。
        """
        index: dict[str, AstNodeModel] = {}
        for node in function_nodes:
            if node.qualified_name:
                index[node.qualified_name] = node
        return index

    @staticmethod
    def _build_import_index(import_nodes: list[AstNodeModel]) -> dict[UUID, list[AstNodeModel]]:
        """
        构建文件级 import 索引

        file_id → [import_node] 映射，用于快速查找某文件导入了哪些外部模块。
        """
        index: dict[UUID, list[AstNodeModel]] = {}
        for node in import_nodes:
            if node.file_id:
                index.setdefault(node.file_id, []).append(node)
        return index

    @staticmethod
    def _build_external_dep_index(ext_deps: list) -> dict[str, list]:
        """
        构建外部依赖索引

        artifact_name → [dep] 映射，用于快速匹配外部依赖。
        """
        index: dict[str, list] = {}
        for dep in ext_deps:
            index.setdefault(dep.artifact_name.lower(), []).append(dep)
            if dep.group_name:
                full_name = f"{dep.group_name}/{dep.artifact_name}".lower()
                index.setdefault(full_name, []).append(dep)
        return index

    @staticmethod
    def _build_function_by_file_index(function_nodes: list[AstNodeModel]) -> dict[UUID, list[AstNodeModel]]:
        """
        按文件构建函数索引

        Args:
            function_nodes: 函数/方法节点列表

        Returns:
            file_id → [function_node] 映射
        """
        index: dict[UUID, list[AstNodeModel]] = {}
        for node in function_nodes:
            index.setdefault(node.file_id, []).append(node)
        # 按 start_line 排序，方便后续查找
        for file_id in index:
            index[file_id].sort(key=lambda n: n.start_line)
        return index

    @staticmethod
    def _find_enclosing_function(
        call_node: AstNodeModel,
        function_by_file_index: dict[UUID, list[AstNodeModel]],
    ) -> AstNodeModel | None:
        """
        找到包含该调用节点的函数/方法

        通过位置匹配：找到同一文件中 start_line <= call.start_line
        且 end_line >= call.start_line 的函数/方法节点。

        对于嵌套函数，选择最内层（end_line 最小）的函数。

        Args:
            call_node: call 类型节点
            function_by_file_index: 按文件组织的函数索引

        Returns:
            包含该调用的函数/方法节点，或 None
        """
        functions = function_by_file_index.get(call_node.file_id, [])
        if not functions:
            return None

        call_line = call_node.start_line
        candidates = []

        for func in functions:
            if func.start_line <= call_line <= func.end_line:
                candidates.append(func)

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        return min(candidates, key=lambda f: f.end_line)

    @staticmethod
    def _disambiguate_candidates(
        call_node: AstNodeModel,
        candidates: list[AstNodeModel],
    ) -> list[AstNodeModel]:
        """
        多候选消歧：利用对象变量名推断类名，缩小候选范围

        当 *.method 调用匹配到多个同名方法时，通过 call 节点的
        qualified_name（如 "tokenUserInfoDto.getUserId"）提取对象变量名，
        按命名约定推断类名（camelCase → PascalCase），过滤候选方法。

        Args:
            call_node: call 类型节点（含 qualified_name）
            candidates: 所有同名候选方法列表

        Returns:
            消歧后的候选列表（若无法消歧则返回原列表）
        """
        if len(candidates) <= 1:
            return candidates

        # 从 qualified_name 提取对象变量名
        qname = call_node.qualified_name or ""
        if not qname or "." not in qname:
            return candidates

        # qualified_name 格式: "objVar.methodName" 或 "this.field.methodName"
        # 取第一个 "." 前的部分作为对象变量名
        parts = qname.split(".")
        if len(parts) < 2:
            return candidates

        obj_var = parts[0].strip()
        # 处理 this.field.method → 取 field
        if obj_var == "this" and len(parts) >= 3:
            obj_var = parts[1].strip()

        if not obj_var:
            return candidates

        # 按命名约定推断类名：camelCase → PascalCase
        # tokenUserInfoDto → TokenUserInfoDto
        guessed_class = obj_var[0].upper() + obj_var[1:]

        # 过滤候选：qualified_name 中包含推断的类名
        filtered = [c for c in candidates if c.qualified_name and guessed_class in c.qualified_name]

        if filtered:
            return filtered

        return candidates

    def _match_call_edges(
        self,
        call_nodes: list[AstNodeModel],
        function_index: dict[str, list[AstNodeModel]],
        qualified_index: dict[str, AstNodeModel],
        import_index: dict[UUID, list[AstNodeModel]],
        ext_dep_index: dict[str, list],
        repo_uuid: UUID,
    ) -> list[dict]:
        """
        匹配调用边

        Phase 5 增强 + 扩展性重构：策略链匹配（Chain of Responsibility）
        1. qualified_name 精确匹配（QualifiedNameMatchStrategy）
        2. 方法名匹配（MethodNameMatchStrategy）
        3. 外部依赖匹配（ExternalDepMatchStrategy）
        4. 依赖注入调用检测（InjectedCallMatchStrategy）
        全部策略未命中则标记为 "unknown"。

        动态调用（getattr/setattr 等）作为前置短路检查，命中即标记为 "dynamic"。

        Args:
            call_nodes: call 类型节点列表
            function_index: 函数名索引（name → [node]）
            qualified_index: qualified_name 索引（qname → node）
            import_index: 文件级 import 索引（file_id → [import_node]）
            ext_dep_index: 外部依赖索引（artifact_name → [dep]）
            repo_uuid: 仓库 UUID

        Returns:
            调用边数据列表
        """
        edges_data = []

        function_nodes = []
        for nodes in function_index.values():
            function_nodes.extend(nodes)
        function_by_file_index = CallGraphBuilder._build_function_by_file_index(function_nodes)

        for call_node in call_nodes:
            call_name = call_node.name.strip()

            # A-6: 防御空/None 名称
            if not call_name:
                continue

            # 找到包含该调用的函数/方法节点
            enclosing_func = CallGraphBuilder._find_enclosing_function(call_node, function_by_file_index)
            caller_node_id = enclosing_func.id if enclosing_func else call_node.id

            # 动态调用：精确匹配动态模式名，不匹配 getattr.x 等对象方法
            if call_name in _DYNAMIC_CALL_NAMES:
                edges_data.append(
                    {
                        "repository_id": repo_uuid,
                        "caller_node_id": caller_node_id,
                        "callee_node_id": None,
                        "start_line": call_node.start_line,
                        "start_column": call_node.start_column,
                        "call_name": call_name,
                        "call_type": "dynamic",
                    }
                )
                continue

            # 提取方法名（用于方法调用和普通调用）
            is_method_call = call_name.startswith("*.")
            method_name = call_name[2:] if is_method_call else call_name

            context = CallMatchContext(
                function_index=function_index,
                qualified_index=qualified_index,
                import_index=import_index,
                ext_dep_index=ext_dep_index,
                enclosing_func=enclosing_func,
                caller_node_id=caller_node_id,
                repo_uuid=repo_uuid,
            )

            # 按优先级遍历匹配策略链，首个非 None 结果生效
            result: CallEdge | None = None
            for strategy in self._match_strategies:
                result = strategy.match(call_node, call_name, method_name, is_method_call, context)
                if result is not None:
                    break

            # 全部策略未命中 → unknown
            if result is None:
                result = CallEdge(call_type="unknown")

            if result.candidates:
                # 有多个重载时，创建多个调用边（指向每个可能的目标）
                for candidate in result.candidates:
                    edges_data.append(
                        {
                            "repository_id": repo_uuid,
                            "caller_node_id": caller_node_id,
                            "callee_node_id": candidate.id,
                            "start_line": call_node.start_line,
                            "start_column": call_node.start_column,
                            "call_name": call_name,
                            "call_type": result.call_type,
                        }
                    )
            else:
                # 未知调用 / 外部调用 / 注入调用（callee_node_id = None）
                final_call_name = result.external_dep_name or call_name
                edges_data.append(
                    {
                        "repository_id": repo_uuid,
                        "caller_node_id": caller_node_id,
                        "callee_node_id": None,
                        "start_line": call_node.start_line,
                        "start_column": call_node.start_column,
                        "call_name": final_call_name,
                        "call_type": result.call_type,
                    }
                )

        return edges_data


class CallGraphQuery:
    """
    调用图查询接口

    提供正向/反向查询和调用链遍历。
    """

    def __init__(
        self,
        call_edge_dao: CallEdgeDAO | None = None,
        ast_dao: AstNodeDAO | None = None,
    ):
        self.call_edge_dao = call_edge_dao or CallEdgeDAO()
        self.ast_dao = ast_dao or AstNodeDAO()

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

    async def get_callees(
        self,
        caller_node_id: UUID,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """
        获取该节点调用的所有目标（正向调用图）

        Args:
            caller_node_id: 调用节点 ID
            db: 可选的数据库会话；为 None 时创建独立会话（兼容旧调用）

        Returns:
            调用边列表（含 caller 和 callee 节点信息）
        """
        db, use_context = await self._get_session(db, "get_callees")

        try:
            edges = await self.call_edge_dao.get_callees(db, caller_node_id)

            # A-2: 批量预加载所有 callee 节点，消除 N+1
            callee_ids = [e.callee_node_id for e in edges if e.callee_node_id]
            callee_map: dict[UUID, AstNodeModel | None] = {}
            if callee_ids:
                nodes_result = await db.execute(select(AstNodeModel).where(AstNodeModel.id.in_(callee_ids)))
                for node in nodes_result.scalars().all():
                    callee_map[node.id] = node

            callees_result = []
            for edge in edges:
                callee = callee_map.get(edge.callee_node_id) if edge.callee_node_id else None
                callees_result.append(
                    {
                        "edge_id": edge.id,
                        "call_name": edge.call_name,
                        "call_type": edge.call_type,
                        "start_line": edge.start_line,
                        "start_column": edge.start_column,
                        "callee": (
                            {
                                "id": str(callee.id),
                                "name": callee.name,
                                "node_type": callee.node_type,
                                "file_path": callee.file_path,
                            }
                            if callee
                            else None
                        ),
                    }
                )
            return callees_result
        finally:
            if use_context:
                await db.__aexit__(None, None, None)

    async def get_callers(
        self,
        callee_node_id: UUID,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """
        获取调用该节点的所有调用者（反向调用图）

        Args:
            callee_node_id: 被调用节点 ID
            db: 可选的数据库会话；为 None 时创建独立会话（兼容旧调用）

        Returns:
            调用边列表（含 caller 节点信息）
        """
        db, use_context = await self._get_session(db, "get_callers")

        try:
            edges = await self.call_edge_dao.get_callers(db, callee_node_id)

            # A-2: 批量预加载所有 caller 节点，消除 N+1
            caller_ids = [e.caller_node_id for e in edges if e.caller_node_id]
            caller_map: dict[UUID, AstNodeModel | None] = {}
            if caller_ids:
                nodes_result = await db.execute(select(AstNodeModel).where(AstNodeModel.id.in_(caller_ids)))
                for node in nodes_result.scalars().all():
                    caller_map[node.id] = node

            callers_result = []
            for edge in edges:
                caller = caller_map.get(edge.caller_node_id) if edge.caller_node_id else None
                callers_result.append(
                    {
                        "edge_id": edge.id,
                        "call_name": edge.call_name,
                        "call_type": edge.call_type,
                        "start_line": edge.start_line,
                        "start_column": edge.start_column,
                        "caller": (
                            {
                                "id": str(caller.id),
                                "name": caller.name,
                                "node_type": caller.node_type,
                                "file_id": str(caller.file_id),
                                "file_path": caller.file_path,
                            }
                            if caller
                            else None
                        ),
                    }
                )
            return callers_result
        finally:
            if use_context:
                await db.__aexit__(None, None, None)

    async def get_call_chain(
        self,
        caller_node_id: UUID,
        max_depth: int = 10,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """
        获取从该节点开始的完整调用链（DFS 遍历）

        A-2 修复：使用共享 session 而非每层新建，消除 session 爆炸。

        Args:
            caller_node_id: 起始节点 ID
            max_depth: 最大遍历深度
            db: 可选的数据库会话；为 None 时创建独立会话

        Returns:
            调用链节点列表（按深度排序）
        """
        db, use_context = await self._get_session(db)

        try:
            return await self._dfs_chain(db, caller_node_id, max_depth, 0, [], set())
        finally:
            if use_context:
                await db.__aexit__(None, None, None)

    async def _dfs_chain(
        self,
        db: AsyncSession,
        node_id: UUID,
        max_depth: int,
        depth: int,
        path: list[str],
        visited: set[UUID],
    ) -> list[dict]:
        """DFS 调用链递归实现"""
        chain: list[dict] = []
        if depth > max_depth or node_id in visited:
            return chain

        visited.add(node_id)

        # 使用共享 session 获取 callees
        callees = await self.get_callees(node_id, db=db)
        for callee_info in callees:
            if callee_info["callee"]:
                callee_id = UUID(callee_info["callee"]["id"])
                new_path = path + [callee_info["call_name"]]
                chain.append(
                    {
                        "depth": depth + 1,
                        "node_id": callee_info["callee"]["id"],
                        "node_name": callee_info["callee"]["name"],
                        "node_type": callee_info["callee"]["node_type"],
                        "call_name": callee_info["call_name"],
                        "call_type": callee_info["call_type"],
                        "path": new_path,
                    }
                )
                chain.extend(await self._dfs_chain(db, callee_id, max_depth, depth + 1, new_path, visited))

        return chain
