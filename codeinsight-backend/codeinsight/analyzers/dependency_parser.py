"""
依赖声明解析器

解析各语言/生态的依赖声明文件，提取外部依赖信息。
支持：Maven(pom.xml)、NPM(package.json)、Pip(requirements.txt/pyproject.toml)、Go(go.mod)。

架构说明（策略模式 + 注册机制）：
- 每个生态系统的解析器独立为一个类，实现统一的 EcosystemParser 接口
- DependencyParser 维护 _parsers 注册表，parse_file 通过注册表查找解析器
- 新增生态系统只需新增解析器类 + 调用 register 注册，无需修改 parse_file
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

ECOSYSTEM_MAVEN = "maven"
ECOSYSTEM_NPM = "npm"
ECOSYSTEM_PIP = "pip"
ECOSYSTEM_GO = "go"
ECOSYSTEM_CARGO = "cargo"

SCOPE_COMPILE = "compile"
SCOPE_DEV = "dev"
SCOPE_TEST = "test"
SCOPE_RUNTIME = "runtime"
SCOPE_PEER = "peer"

DEPENDENCY_FILE_PATTERNS = {
    "pom.xml": ECOSYSTEM_MAVEN,
    "build.gradle": ECOSYSTEM_MAVEN,
    "build.gradle.kts": ECOSYSTEM_MAVEN,
    "package.json": ECOSYSTEM_NPM,
    "requirements.txt": ECOSYSTEM_PIP,
    "pyproject.toml": ECOSYSTEM_PIP,
    "Pipfile": ECOSYSTEM_PIP,
    "go.mod": ECOSYSTEM_GO,
    "Cargo.toml": ECOSYSTEM_CARGO,
}


@dataclass
class DependencyEntry:
    """
    依赖条目

    从声明文件中解析出的单个依赖信息。
    """

    ecosystem: str
    artifact_name: str
    group_name: str | None = None
    version: str | None = None
    version_range: str | None = None
    scope: str = SCOPE_COMPILE
    declaration_file: str | None = None
    used_by_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为字典（用于数据库写入）"""
        return {
            "ecosystem": self.ecosystem,
            "group_name": self.group_name,
            "artifact_name": self.artifact_name,
            "version": self.version,
            "version_range": self.version_range,
            "scope": self.scope,
            "declaration_file": self.declaration_file,
            "used_by_files": self.used_by_files,
        }


class EcosystemParser(ABC):
    """
    生态系统解析器抽象基类

    定义统一的依赖文件解析接口，每个生态系统实现自己的解析逻辑。
    新增生态系统时继承该类并实现 parse 方法即可。
    """

    @abstractmethod
    def parse(self, path: Path) -> list[DependencyEntry]:
        """
        解析依赖声明文件

        Args:
            path: 依赖声明文件路径

        Returns:
            依赖条目列表
        """
        ...


class MavenParser(EcosystemParser):
    """
    Maven 生态系统解析器

    支持 pom.xml（Maven）与 build.gradle / build.gradle.kts（Gradle）。
    """

    def parse(self, path: Path) -> list[DependencyEntry]:
        """
        解析 Maven/Gradle 依赖文件

        根据文件扩展名分发到具体的解析方法：.xml 走 pom 解析，其余走 Gradle 解析。

        Args:
            path: 依赖声明文件路径

        Returns:
            依赖条目列表
        """
        if path.name.endswith(".xml"):
            return self.parse_maven_pom(path)
        return self.parse_gradle(path)

    def parse_maven_pom(self, pom_path: Path) -> list[DependencyEntry]:
        """
        解析 Maven pom.xml

        Args:
            pom_path: pom.xml 文件路径

        Returns:
            依赖条目列表
        """
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()

            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0].strip("{")

            def _tag(name: str) -> str:
                return f"{{{ns}}}{name}" if ns else name

            deps = []
            dep_path = f".//{_tag('dependencies')}/{_tag('dependency')}"

            for dep_elem in root.findall(dep_path):
                group_id = dep_elem.findtext(_tag("groupId"))
                artifact_id = dep_elem.findtext(_tag("artifactId"))
                version = dep_elem.findtext(_tag("version"))
                scope = dep_elem.findtext(_tag("scope"), SCOPE_COMPILE)

                if not artifact_id:
                    continue

                deps.append(
                    DependencyEntry(
                        ecosystem=ECOSYSTEM_MAVEN,
                        group_name=group_id,
                        artifact_name=artifact_id,
                        version=version,
                        version_range=version,
                        scope=scope or SCOPE_COMPILE,
                        declaration_file=str(pom_path),
                    )
                )

            logger.info("Maven pom.xml 解析完成: %s, 依赖数=%d", pom_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("Maven pom.xml 解析失败: %s, 错误=%s", pom_path, exc)
            return []

    def parse_gradle(self, gradle_path: Path) -> list[DependencyEntry]:
        """
        解析 Gradle 构建文件（build.gradle / build.gradle.kts）

        支持基本的 implementation、testImplementation 等声明。

        Args:
            gradle_path: build.gradle 文件路径

        Returns:
            依赖条目列表
        """
        try:
            content = gradle_path.read_text(encoding="utf-8", errors="replace")
            deps = []

            pattern = re.compile(
                r"(implementation|api|compileOnly|runtimeOnly|testImplementation|testCompileOnly|testRuntimeOnly)"
                r"\s+['\"]([^:]+):([^:]+):?([^'\"]*)['\"]",
                re.MULTILINE,
            )

            scope_map = {
                "implementation": SCOPE_COMPILE,
                "api": SCOPE_COMPILE,
                "compileOnly": SCOPE_COMPILE,
                "runtimeOnly": SCOPE_RUNTIME,
                "testImplementation": SCOPE_TEST,
                "testCompileOnly": SCOPE_TEST,
                "testRuntimeOnly": SCOPE_TEST,
            }

            for match in pattern.finditer(content):
                scope_key = match.group(1)
                group = match.group(2)
                artifact = match.group(3)
                version = match.group(4) or None

                scope = scope_map.get(scope_key, SCOPE_COMPILE)

                deps.append(
                    DependencyEntry(
                        ecosystem=ECOSYSTEM_MAVEN,
                        group_name=group,
                        artifact_name=artifact,
                        version=version,
                        version_range=version,
                        scope=scope,
                        declaration_file=str(gradle_path),
                    )
                )

            logger.info("Gradle 解析完成: %s, 依赖数=%d", gradle_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("Gradle 解析失败: %s, 错误=%s", gradle_path, exc)
            return []


class NpmParser(EcosystemParser):
    """NPM 生态系统解析器（package.json）"""

    def parse(self, path: Path) -> list[DependencyEntry]:
        """
        解析 NPM package.json

        Args:
            path: package.json 文件路径

        Returns:
            依赖条目列表
        """
        return self.parse_npm_package_json(path)

    def parse_npm_package_json(self, package_json_path: Path) -> list[DependencyEntry]:
        """
        解析 NPM package.json

        解析 dependencies、devDependencies、peerDependencies。

        Args:
            package_json_path: package.json 文件路径

        Returns:
            依赖条目列表
        """
        try:
            with open(package_json_path, encoding="utf-8") as f:
                data = json.load(f)

            deps = []

            dep_sections = [
                ("dependencies", SCOPE_COMPILE),
                ("devDependencies", SCOPE_DEV),
                ("peerDependencies", SCOPE_PEER),
                ("optionalDependencies", SCOPE_RUNTIME),
            ]

            for section, scope in dep_sections:
                deps_dict = data.get(section, {})
                if not isinstance(deps_dict, dict):
                    continue

                for name, version_range in deps_dict.items():
                    group_name = None
                    artifact_name = name

                    if name.startswith("@") and "/" in name:
                        parts = name.split("/", 1)
                        group_name = parts[0]
                        artifact_name = parts[1]

                    deps.append(
                        DependencyEntry(
                            ecosystem=ECOSYSTEM_NPM,
                            group_name=group_name,
                            artifact_name=artifact_name,
                            version=None,
                            version_range=str(version_range),
                            scope=scope,
                            declaration_file=str(package_json_path),
                        )
                    )

            logger.info("NPM package.json 解析完成: %s, 依赖数=%d", package_json_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("NPM package.json 解析失败: %s, 错误=%s", package_json_path, exc)
            return []


class PipParser(EcosystemParser):
    """
    Pip 生态系统解析器

    支持 requirements.txt、pyproject.toml、Pipfile。
    """

    def parse(self, path: Path) -> list[DependencyEntry]:
        """
        解析 Pip 依赖声明文件

        根据文件名分发到具体的解析方法。

        Args:
            path: 依赖声明文件路径

        Returns:
            依赖条目列表
        """
        filename = path.name
        if filename == "requirements.txt":
            return self.parse_pip_requirements(path)
        if filename == "pyproject.toml":
            return self.parse_pip_pyproject(path)
        if filename == "Pipfile":
            return self.parse_pipfile(path)
        return []

    def parse_pip_requirements(self, req_path: Path) -> list[DependencyEntry]:
        """
        解析 Pip requirements.txt

        支持标准格式：package==version, package>=version, package~=version 等。

        Args:
            req_path: requirements.txt 文件路径

        Returns:
            依赖条目列表
        """
        try:
            content = req_path.read_text(encoding="utf-8", errors="replace")
            deps = []

            version_pattern = re.compile(
                r"^([a-zA-Z0-9_.-]+)\s*([<>=!~]+.*)?$",
                re.MULTILINE,
            )

            for line in content.splitlines():
                line = line.strip()

                if not line or line.startswith("#") or line.startswith("-"):
                    continue

                if "#" in line:
                    line = line.split("#")[0].strip()

                match = version_pattern.match(line)
                if not match:
                    continue

                package = match.group(1)
                version_spec = match.group(2)

                version = None
                version_range = version_spec

                if version_spec and "==" in version_spec:
                    version = version_spec.replace("==", "").strip()

                deps.append(
                    DependencyEntry(
                        ecosystem=ECOSYSTEM_PIP,
                        artifact_name=package,
                        version=version,
                        version_range=version_range,
                        scope=SCOPE_COMPILE,
                        declaration_file=str(req_path),
                    )
                )

            logger.info("Pip requirements.txt 解析完成: %s, 依赖数=%d", req_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("Pip requirements.txt 解析失败: %s, 错误=%s", req_path, exc)
            return []

    def parse_pip_pyproject(self, toml_path: Path) -> list[DependencyEntry]:
        """
        解析 Pip pyproject.toml

        支持 [project.dependencies] 和 [tool.poetry.dependencies]。
        优先使用 tomllib（Python 3.11+），其次尝试 tomli 库。

        Args:
            toml_path: pyproject.toml 文件路径

        Returns:
            依赖条目列表
        """
        try:
            content = toml_path.read_text(encoding="utf-8")

            try:
                import tomllib

                data = tomllib.loads(content)
            except ImportError:
                try:
                    import tomli

                    data = tomli.loads(content)
                except ImportError:
                    logger.warning("未安装 tomli，无法解析 pyproject.toml（需要 Python 3.11+ 或 tomli 库）")
                    return []

            deps = []

            project_deps = data.get("project", {}).get("dependencies", [])
            if isinstance(project_deps, list):
                for dep_str in project_deps:
                    entry = self._parse_pip_dep_string(dep_str, SCOPE_COMPILE, str(toml_path))
                    if entry:
                        deps.append(entry)

            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            if isinstance(poetry_deps, dict):
                for name, spec in poetry_deps.items():
                    if name.lower() == "python":
                        continue
                    version_range = spec if isinstance(spec, str) else spec.get("version")
                    deps.append(
                        DependencyEntry(
                            ecosystem=ECOSYSTEM_PIP,
                            artifact_name=name,
                            version=None,
                            version_range=version_range,
                            scope=SCOPE_COMPILE,
                            declaration_file=str(toml_path),
                        )
                    )

            poetry_dev_deps = data.get("tool", {}).get("poetry", {}).get("dev-dependencies", {})
            if isinstance(poetry_dev_deps, dict):
                for name, spec in poetry_dev_deps.items():
                    version_range = spec if isinstance(spec, str) else spec.get("version")
                    deps.append(
                        DependencyEntry(
                            ecosystem=ECOSYSTEM_PIP,
                            artifact_name=name,
                            version=None,
                            version_range=version_range,
                            scope=SCOPE_DEV,
                            declaration_file=str(toml_path),
                        )
                    )

            logger.info("Pip pyproject.toml 解析完成: %s, 依赖数=%d", toml_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("Pip pyproject.toml 解析失败: %s, 错误=%s", toml_path, exc)
            return []

    def parse_pipfile(self, pipfile_path: Path) -> list[DependencyEntry]:
        """
        解析 Pipfile

        Args:
            pipfile_path: Pipfile 文件路径

        Returns:
            依赖条目列表
        """
        try:
            content = pipfile_path.read_text(encoding="utf-8")

            try:
                import tomllib

                data = tomllib.loads(content)
            except ImportError:
                try:
                    import tomli

                    data = tomli.loads(content)
                except ImportError:
                    logger.warning("未安装 tomli，无法解析 Pipfile")
                    return []

            deps = []

            for section, scope in [("packages", SCOPE_COMPILE), ("dev-packages", SCOPE_DEV)]:
                deps_dict = data.get(section, {})
                if not isinstance(deps_dict, dict):
                    continue
                for name, spec in deps_dict.items():
                    version_range = spec if isinstance(spec, str) else spec.get("version", "*")
                    deps.append(
                        DependencyEntry(
                            ecosystem=ECOSYSTEM_PIP,
                            artifact_name=name,
                            version=None,
                            version_range=version_range,
                            scope=scope,
                            declaration_file=str(pipfile_path),
                        )
                    )

            logger.info("Pipfile 解析完成: %s, 依赖数=%d", pipfile_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("Pipfile 解析失败: %s, 错误=%s", pipfile_path, exc)
            return []

    @staticmethod
    def _parse_pip_dep_string(dep_str: str, scope: str, declaration_file: str) -> DependencyEntry | None:
        """
        解析 PEP 508 格式的依赖字符串

        例如："requests>=2.25.0,<3.0.0" 或 "package[extra]==1.0"

        Args:
            dep_str: 依赖字符串
            scope: 作用域
            declaration_file: 声明文件路径

        Returns:
            DependencyEntry 或 None
        """
        dep_str = dep_str.strip()
        if not dep_str:
            return None

        pattern = re.compile(r"^([a-zA-Z0-9_.-]+)(\[[^\]]+\])?\s*(.*)")
        match = pattern.match(dep_str)
        if not match:
            return None

        package = match.group(1)
        version_spec = match.group(3).strip() or None

        version = None
        if version_spec and "==" in version_spec:
            version_match = re.search(r"==\s*([\w.]+)", version_spec)
            if version_match:
                version = version_match.group(1)

        return DependencyEntry(
            ecosystem=ECOSYSTEM_PIP,
            artifact_name=package,
            version=version,
            version_range=version_spec,
            scope=scope,
            declaration_file=declaration_file,
        )


class GoParser(EcosystemParser):
    """Go 生态系统解析器（go.mod）"""

    def parse(self, path: Path) -> list[DependencyEntry]:
        """
        解析 Go go.mod

        Args:
            path: go.mod 文件路径

        Returns:
            依赖条目列表
        """
        return self.parse_go_mod(path)

    def parse_go_mod(self, gomod_path: Path) -> list[DependencyEntry]:
        """
        解析 Go go.mod

        解析 require 块中的依赖声明。

        Args:
            gomod_path: go.mod 文件路径

        Returns:
            依赖条目列表
        """
        try:
            content = gomod_path.read_text(encoding="utf-8", errors="replace")
            deps = []

            in_require_block = False

            for line in content.splitlines():
                stripped = line.strip()

                if stripped.startswith("require ("):
                    in_require_block = True
                    continue

                if in_require_block and stripped == ")":
                    in_require_block = False
                    continue

                dep_line = None
                if in_require_block and stripped and not stripped.startswith("//"):
                    dep_line = stripped
                elif stripped.startswith("require ") and "// indirect" not in stripped:
                    dep_line = stripped[len("require ") :].strip()

                if dep_line:
                    parts = dep_line.split()
                    if len(parts) >= 2:
                        module_path = parts[0]
                        version = parts[1]

                        deps.append(
                            DependencyEntry(
                                ecosystem=ECOSYSTEM_GO,
                                artifact_name=module_path,
                                version=version,
                                version_range=version,
                                scope=SCOPE_COMPILE,
                                declaration_file=str(gomod_path),
                            )
                        )

            logger.info("Go go.mod 解析完成: %s, 依赖数=%d", gomod_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("Go go.mod 解析失败: %s, 错误=%s", gomod_path, exc)
            return []


class CargoParser(EcosystemParser):
    """Rust Cargo 生态系统解析器（Cargo.toml）"""

    def parse(self, path: Path) -> list[DependencyEntry]:
        """
        解析 Rust Cargo.toml

        Args:
            path: Cargo.toml 文件路径

        Returns:
            依赖条目列表
        """
        return self.parse_cargo_toml(path)

    def parse_cargo_toml(self, cargo_path: Path) -> list[DependencyEntry]:
        """
        解析 Rust Cargo.toml

        Args:
            cargo_path: Cargo.toml 文件路径

        Returns:
            依赖条目列表
        """
        try:
            content = cargo_path.read_text(encoding="utf-8")

            try:
                import tomllib

                data = tomllib.loads(content)
            except ImportError:
                try:
                    import tomli

                    data = tomli.loads(content)
                except ImportError:
                    logger.warning("未安装 tomli，无法解析 Cargo.toml")
                    return []

            deps = []

            for section, scope in [
                ("dependencies", SCOPE_COMPILE),
                ("dev-dependencies", SCOPE_DEV),
                ("build-dependencies", SCOPE_RUNTIME),
            ]:
                deps_dict = data.get(section, {})
                if not isinstance(deps_dict, dict):
                    continue
                for name, spec in deps_dict.items():
                    version = None
                    if isinstance(spec, str):
                        version = spec
                    elif isinstance(spec, dict):
                        version = spec.get("version")

                    deps.append(
                        DependencyEntry(
                            ecosystem=ECOSYSTEM_CARGO,
                            artifact_name=name,
                            version=None,
                            version_range=version,
                            scope=scope,
                            declaration_file=str(cargo_path),
                        )
                    )

            logger.info("Cargo.toml 解析完成: %s, 依赖数=%d", cargo_path.name, len(deps))
            return deps
        except Exception as exc:
            logger.warning("Cargo.toml 解析失败: %s, 错误=%s", cargo_path, exc)
            return []


class DependencyParser:
    """
    依赖声明解析器

    支持多种生态系统的依赖声明文件解析，输出统一的 DependencyEntry 列表。

    采用策略模式 + 注册机制：
    - 内部维护 _parsers 注册表（ecosystem -> EcosystemParser）
    - __init__ 中自动注册所有内置解析器
    - parse_file 通过注册表查找对应解析器，不再使用 if-elif 分支
    - 通过 register 方法支持外部注册自定义生态系统解析器
    """

    def __init__(self) -> None:
        """初始化解析器并注册所有内置生态系统解析器"""
        self._parsers: dict[str, EcosystemParser] = {}
        self._register_builtin_parsers()

    def _register_builtin_parsers(self) -> None:
        """注册内置的生态系统解析器"""
        self.register(ECOSYSTEM_MAVEN, MavenParser())
        self.register(ECOSYSTEM_NPM, NpmParser())
        self.register(ECOSYSTEM_PIP, PipParser())
        self.register(ECOSYSTEM_GO, GoParser())
        self.register(ECOSYSTEM_CARGO, CargoParser())

    def register(self, ecosystem: str, parser: EcosystemParser) -> None:
        """
        注册生态系统解析器

        新增生态系统只需创建解析器类（实现 EcosystemParser 接口）并调用此方法注册，
        无需修改 parse_file 方法，符合开闭原则。

        Args:
            ecosystem: 生态系统标识（如 ECOSYSTEM_MAVEN）
            parser: 实现 EcosystemParser 接口的解析器实例
        """
        self._parsers[ecosystem] = parser

    def parse_file(self, file_path: str | Path) -> list[DependencyEntry]:
        """
        自动识别文件类型并解析依赖

        通过 DEPENDENCY_FILE_PATTERNS 映射文件名到生态系统标识，
        再从 _parsers 注册表中查找对应解析器进行解析。

        Args:
            file_path: 依赖声明文件路径

        Returns:
            依赖条目列表
        """
        path = Path(file_path)
        filename = path.name
        ecosystem = DEPENDENCY_FILE_PATTERNS.get(filename)

        if ecosystem is None:
            logger.debug("无法识别的依赖文件类型: %s", filename)
            return []

        parser = self._parsers.get(ecosystem)
        if parser is None:
            logger.debug("未注册的生态系统解析器: %s", ecosystem)
            return []

        return parser.parse(path)

    # ============================================================
    # 向后兼容：保留原有的具体解析方法，委托给注册表中对应的解析器
    # ============================================================

    def parse_maven_pom(self, pom_path: Path) -> list[DependencyEntry]:
        """解析 Maven pom.xml（委托给 MavenParser）"""
        parser = self._parsers[ECOSYSTEM_MAVEN]
        assert isinstance(parser, MavenParser)
        return parser.parse_maven_pom(pom_path)

    def parse_gradle(self, gradle_path: Path) -> list[DependencyEntry]:
        """解析 Gradle 构建文件（委托给 MavenParser）"""
        parser = self._parsers[ECOSYSTEM_MAVEN]
        assert isinstance(parser, MavenParser)
        return parser.parse_gradle(gradle_path)

    def parse_npm_package_json(self, package_json_path: Path) -> list[DependencyEntry]:
        """解析 NPM package.json（委托给 NpmParser）"""
        parser = self._parsers[ECOSYSTEM_NPM]
        assert isinstance(parser, NpmParser)
        return parser.parse_npm_package_json(package_json_path)

    def parse_pip_requirements(self, req_path: Path) -> list[DependencyEntry]:
        """解析 Pip requirements.txt（委托给 PipParser）"""
        parser = self._parsers[ECOSYSTEM_PIP]
        assert isinstance(parser, PipParser)
        return parser.parse_pip_requirements(req_path)

    def parse_pip_pyproject(self, toml_path: Path) -> list[DependencyEntry]:
        """解析 Pip pyproject.toml（委托给 PipParser）"""
        parser = self._parsers[ECOSYSTEM_PIP]
        assert isinstance(parser, PipParser)
        return parser.parse_pip_pyproject(toml_path)

    def parse_pipfile(self, pipfile_path: Path) -> list[DependencyEntry]:
        """解析 Pipfile（委托给 PipParser）"""
        parser = self._parsers[ECOSYSTEM_PIP]
        assert isinstance(parser, PipParser)
        return parser.parse_pipfile(pipfile_path)

    def parse_go_mod(self, gomod_path: Path) -> list[DependencyEntry]:
        """解析 Go go.mod（委托给 GoParser）"""
        parser = self._parsers[ECOSYSTEM_GO]
        assert isinstance(parser, GoParser)
        return parser.parse_go_mod(gomod_path)

    def parse_cargo_toml(self, cargo_path: Path) -> list[DependencyEntry]:
        """解析 Rust Cargo.toml（委托给 CargoParser）"""
        parser = self._parsers[ECOSYSTEM_CARGO]
        assert isinstance(parser, CargoParser)
        return parser.parse_cargo_toml(cargo_path)
