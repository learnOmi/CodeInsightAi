"""
Phase 5: 外部依赖与跨模块分析测试

测试内容：
1. DependencyParser - 依赖声明文件解析（NPM/Maven/Pip/Go）
2. ExternalDependency Schema 序列化
3. 调用图增强 - qualified_name 匹配、external/injected 类型
4. 模块依赖图增强 - Import → 外部依赖映射
"""

from __future__ import annotations

import json
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from codeinsight.analyzers.call_graph import CallGraphBuilder
from codeinsight.analyzers.dependency_parser import (
    ECOSYSTEM_GO,
    ECOSYSTEM_MAVEN,
    ECOSYSTEM_NPM,
    ECOSYSTEM_PIP,
    DependencyEntry,
    DependencyParser,
)
from codeinsight.analyzers.module_graph import ModuleDependencyBuilder
from codeinsight.models import AstNodeModel, ExternalDependencyModel
from codeinsight.schemas import ExternalDependency, ExternalDependencyCreate

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def dependency_parser():
    """DependencyParser 实例"""
    return DependencyParser()


@pytest.fixture
def temp_dir():
    """临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ============================================================
# DependencyParser 测试
# ============================================================


class TestDependencyEntry:
    """DependencyEntry 数据类测试"""

    def test_dependency_entry_to_dict(self):
        """测试 DependencyEntry 转字典"""
        entry = DependencyEntry(
            ecosystem=ECOSYSTEM_NPM,
            artifact_name="react",
            group_name=None,
            version="18.2.0",
            version_range="^18.2.0",
            scope="compile",
            declaration_file="package.json",
            used_by_files=["src/App.tsx"],
        )

        d = entry.to_dict()
        assert d["ecosystem"] == ECOSYSTEM_NPM
        assert d["artifact_name"] == "react"
        assert d["group_name"] is None
        assert d["version"] == "18.2.0"
        assert d["version_range"] == "^18.2.0"
        assert d["scope"] == "compile"
        assert d["declaration_file"] == "package.json"
        assert len(d["used_by_files"]) == 1

    def test_dependency_entry_with_group(self):
        """测试带 group_name 的 DependencyEntry"""
        entry = DependencyEntry(
            ecosystem=ECOSYSTEM_MAVEN,
            group_name="org.springframework.boot",
            artifact_name="spring-boot-starter-web",
            version="3.2.0",
        )

        d = entry.to_dict()
        assert d["group_name"] == "org.springframework.boot"
        assert d["artifact_name"] == "spring-boot-starter-web"


class TestNpmPackageJson:
    """NPM package.json 解析测试"""

    def test_parse_package_json_basic(self, dependency_parser, temp_dir):
        """测试解析基础 package.json"""
        pkg = {
            "name": "test-project",
            "version": "1.0.0",
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
            },
            "devDependencies": {
                "typescript": "^5.0.0",
            },
        }

        pkg_path = temp_dir / "package.json"
        pkg_path.write_text(json.dumps(pkg), encoding="utf-8")

        deps = dependency_parser.parse_npm_package_json(pkg_path)
        assert len(deps) == 3

        dep_map = {d.artifact_name: d for d in deps}
        assert "react" in dep_map
        assert dep_map["react"].ecosystem == ECOSYSTEM_NPM
        assert dep_map["react"].version_range == "^18.2.0"
        assert dep_map["react"].scope == "compile"

        assert "typescript" in dep_map
        assert dep_map["typescript"].scope == "dev"

    def test_parse_package_json_scoped_packages(self, dependency_parser, temp_dir):
        """测试带 scope 的 npm 包（@scope/package）"""
        pkg = {
            "dependencies": {
                "@angular/core": "^17.0.0",
            },
        }

        pkg_path = temp_dir / "package.json"
        pkg_path.write_text(json.dumps(pkg), encoding="utf-8")

        deps = dependency_parser.parse_npm_package_json(pkg_path)
        assert len(deps) == 1

        dep = deps[0]
        assert dep.group_name == "@angular"
        assert dep.artifact_name == "core"
        assert dep.version_range == "^17.0.0"

    def test_parse_package_json_empty(self, dependency_parser, temp_dir):
        """测试空 package.json"""
        pkg = {"name": "empty-project"}
        pkg_path = temp_dir / "package.json"
        pkg_path.write_text(json.dumps(pkg), encoding="utf-8")

        deps = dependency_parser.parse_npm_package_json(pkg_path)
        assert len(deps) == 0

    def test_parse_package_json_invalid(self, dependency_parser, temp_dir):
        """测试无效的 package.json"""
        pkg_path = temp_dir / "package.json"
        pkg_path.write_text("not valid json {{{", encoding="utf-8")

        deps = dependency_parser.parse_npm_package_json(pkg_path)
        assert len(deps) == 0


class TestMavenPom:
    """Maven pom.xml 解析测试"""

    def test_parse_pom_xml_basic(self, dependency_parser, temp_dir):
        """测试解析基础 pom.xml"""
        ns = "http://maven.apache.org/POM/4.0.0"
        project = ET.Element(f"{{{ns}}}project")

        deps_elem = ET.SubElement(project, f"{{{ns}}}dependencies")

        dep1 = ET.SubElement(deps_elem, f"{{{ns}}}dependency")
        ET.SubElement(dep1, f"{{{ns}}}groupId").text = "org.springframework.boot"
        ET.SubElement(dep1, f"{{{ns}}}artifactId").text = "spring-boot-starter-web"
        ET.SubElement(dep1, f"{{{ns}}}version").text = "3.2.0"

        dep2 = ET.SubElement(deps_elem, f"{{{ns}}}dependency")
        ET.SubElement(dep2, f"{{{ns}}}groupId").text = "org.projectlombok"
        ET.SubElement(dep2, f"{{{ns}}}artifactId").text = "lombok"
        ET.SubElement(dep2, f"{{{ns}}}version").text = "1.18.30"
        ET.SubElement(dep2, f"{{{ns}}}scope").text = "provided"

        pom_path = temp_dir / "pom.xml"
        tree = ET.ElementTree(project)
        tree.write(pom_path, encoding="utf-8", xml_declaration=True)

        deps = dependency_parser.parse_maven_pom(pom_path)
        assert len(deps) == 2

        dep_map = {d.artifact_name: d for d in deps}
        assert "spring-boot-starter-web" in dep_map
        assert dep_map["spring-boot-starter-web"].ecosystem == ECOSYSTEM_MAVEN
        assert dep_map["spring-boot-starter-web"].group_name == "org.springframework.boot"
        assert dep_map["spring-boot-starter-web"].version == "3.2.0"

        assert "lombok" in dep_map
        assert dep_map["lombok"].scope == "provided"

    def test_parse_pom_xml_no_deps(self, dependency_parser, temp_dir):
        """测试无依赖的 pom.xml"""
        ns = "http://maven.apache.org/POM/4.0.0"
        project = ET.Element(f"{{{ns}}}project")
        ET.SubElement(project, f"{{{ns}}}modelVersion").text = "4.0.0"

        pom_path = temp_dir / "pom.xml"
        tree = ET.ElementTree(project)
        tree.write(pom_path, encoding="utf-8", xml_declaration=True)

        deps = dependency_parser.parse_maven_pom(pom_path)
        assert len(deps) == 0


class TestPipRequirements:
    """Pip requirements.txt 解析测试"""

    def test_parse_requirements_basic(self, dependency_parser, temp_dir):
        """测试解析基础 requirements.txt"""
        content = """flask==2.3.0
requests>=2.28.0
sqlalchemy~=2.0.0
# this is a comment
pytest<8.0.0
"""

        req_path = temp_dir / "requirements.txt"
        req_path.write_text(content, encoding="utf-8")

        deps = dependency_parser.parse_pip_requirements(req_path)
        assert len(deps) >= 3

        dep_map = {d.artifact_name: d for d in deps}
        assert "flask" in dep_map
        assert dep_map["flask"].ecosystem == ECOSYSTEM_PIP
        assert dep_map["flask"].version == "2.3.0"

        assert "requests" in dep_map
        assert dep_map["requests"].version_range == ">=2.28.0"

    def test_parse_requirements_empty(self, dependency_parser, temp_dir):
        """测试空 requirements.txt"""
        req_path = temp_dir / "requirements.txt"
        req_path.write_text("", encoding="utf-8")

        deps = dependency_parser.parse_pip_requirements(req_path)
        assert len(deps) == 0

    def test_parse_requirements_comments_and_options(self, dependency_parser, temp_dir):
        """测试带注释和选项的 requirements.txt"""
        content = """# production deps
flask==2.0.0  # web framework
-r other.txt
--index-url https://example.com/simple
"""

        req_path = temp_dir / "requirements.txt"
        req_path.write_text(content, encoding="utf-8")

        deps = dependency_parser.parse_pip_requirements(req_path)
        assert len(deps) == 1
        assert deps[0].artifact_name == "flask"


class TestGoMod:
    """Go go.mod 解析测试"""

    def test_parse_go_mod_basic(self, dependency_parser, temp_dir):
        """测试解析基础 go.mod"""
        content = """module github.com/example/project

go 1.21

require (
    github.com/gin-gonic/gin v1.9.0
    gorm.io/gorm v1.25.0
)
"""

        gomod_path = temp_dir / "go.mod"
        gomod_path.write_text(content, encoding="utf-8")

        deps = dependency_parser.parse_go_mod(gomod_path)
        assert len(deps) == 2

        dep_map = {d.artifact_name: d for d in deps}
        assert "github.com/gin-gonic/gin" in dep_map
        assert dep_map["github.com/gin-gonic/gin"].ecosystem == ECOSYSTEM_GO
        assert dep_map["github.com/gin-gonic/gin"].version == "v1.9.0"

    def test_parse_go_mod_single_require(self, dependency_parser, temp_dir):
        """测试单行 require"""
        content = """module example.com/app

require github.com/redis/go-redis/v9 v9.0.0
"""

        gomod_path = temp_dir / "go.mod"
        gomod_path.write_text(content, encoding="utf-8")

        dependency_parser.parse_go_mod(gomod_path)

    def test_parse_go_mod_empty(self, dependency_parser, temp_dir):
        """测试空 go.mod"""
        gomod_path = temp_dir / "go.mod"
        gomod_path.write_text("module example.com/app\n", encoding="utf-8")

        deps = dependency_parser.parse_go_mod(gomod_path)
        assert len(deps) == 0


class TestDependencyParserAutoDetect:
    """DependencyParser 自动识别文件类型测试"""

    def test_parse_file_package_json(self, dependency_parser, temp_dir):
        """测试自动识别 package.json"""
        pkg = {"dependencies": {"flask": "2.0.0"}}
        pkg_path = temp_dir / "package.json"
        pkg_path.write_text(json.dumps(pkg), encoding="utf-8")

        deps = dependency_parser.parse_file(pkg_path)
        assert len(deps) == 1
        assert deps[0].ecosystem == ECOSYSTEM_NPM

    def test_parse_file_unknown_type(self, dependency_parser, temp_dir):
        """测试未知文件类型"""
        unknown_path = temp_dir / "random.txt"
        unknown_path.write_text("hello", encoding="utf-8")

        deps = dependency_parser.parse_file(unknown_path)
        assert len(deps) == 0


# ============================================================
# ExternalDependency Schema 测试
# ============================================================


class TestExternalDependencySchema:
    """ExternalDependency Pydantic Schema 测试"""

    def test_external_dependency_create(self):
        """测试 ExternalDependencyCreate Schema"""
        repo_id = uuid4()

        dep = ExternalDependencyCreate(
            repository_id=repo_id,
            ecosystem=ECOSYSTEM_NPM,
            artifact_name="react",
            version="18.2.0",
            scope="compile",
        )

        assert dep.ecosystem == ECOSYSTEM_NPM
        assert dep.artifact_name == "react"
        assert dep.repository_id == repo_id

    def test_external_dependency_serialization(self):
        """测试 ExternalDependency 序列化（camelCase）"""
        dep_id = uuid4()
        repo_id = uuid4()
        version_id = uuid4()

        dep = ExternalDependency(
            id=dep_id,
            repository_id=repo_id,
            analysis_version_id=version_id,
            ecosystem=ECOSYSTEM_MAVEN,
            group_name="org.springframework",
            artifact_name="spring-core",
            version="6.0.0",
            version_range="6.0.x",
            scope="compile",
            declaration_file="pom.xml",
            used_by_files=["src/main/java/Controller.java"],
            created_at=datetime.now(),
        )

        data = dep.model_dump(by_alias=True)
        assert "groupName" in data
        assert "artifactName" in data
        assert "versionRange" in data
        assert "declarationFile" in data
        assert "usedByFiles" in data
        assert data["ecosystem"] == ECOSYSTEM_MAVEN


# ============================================================
# 调用图增强测试
# ============================================================


class TestCallGraphQualifiedName:
    """调用图 qualified_name 匹配测试"""

    def test_build_qualified_index(self):
        """测试构建 qualified_name 索引"""
        node1 = AstNodeModel(
            id=uuid4(),
            repository_id=uuid4(),
            file_id=uuid4(),
            node_type="method",
            name="getUser",
            start_line=10,
            end_line=20,
            start_column=0,
            end_column=0,
            file_path="src/service/UserService.java",
            qualified_name="com.example.service.UserService.getUser",
        )

        node2 = AstNodeModel(
            id=uuid4(),
            repository_id=uuid4(),
            file_id=uuid4(),
            node_type="method",
            name="getUser",
            start_line=5,
            end_line=15,
            start_column=0,
            end_column=0,
            file_path="src/service/OrderService.java",
            qualified_name="com.example.service.OrderService.getUser",
        )

        index = CallGraphBuilder._build_qualified_index([node1, node2])
        assert len(index) == 2
        assert "com.example.service.UserService.getUser" in index
        assert index["com.example.service.UserService.getUser"].id == node1.id

    def test_build_qualified_index_empty(self):
        """测试空 qualified_name 不加入索引"""
        node = AstNodeModel(
            id=uuid4(),
            repository_id=uuid4(),
            file_id=uuid4(),
            node_type="function",
            name="helper",
            start_line=1,
            end_line=5,
            start_column=0,
            end_column=0,
            file_path="src/utils.js",
        )

        index = CallGraphBuilder._build_qualified_index([node])
        assert len(index) == 0


class TestCallGraphExternalDep:
    """调用图外部依赖匹配测试"""

    def test_build_external_dep_index(self):
        """测试构建外部依赖索引"""
        dep1 = ExternalDependencyModel(
            id=uuid4(),
            repository_id=uuid4(),
            ecosystem=ECOSYSTEM_NPM,
            artifact_name="react",
            version="18.2.0",
        )

        dep2 = ExternalDependencyModel(
            id=uuid4(),
            repository_id=uuid4(),
            ecosystem=ECOSYSTEM_MAVEN,
            group_name="org.springframework.boot",
            artifact_name="spring-boot-starter-web",
            version="3.2.0",
        )

        index = CallGraphBuilder._build_external_dep_index([dep1, dep2])
        assert "react" in index
        assert "spring-boot-starter-web" in index
        assert "org.springframework.boot/spring-boot-starter-web" in index


# ============================================================
# 模块依赖图增强测试
# ============================================================


class TestModuleDependencyExtDep:
    """模块依赖图外部依赖映射测试"""

    def test_build_ext_dep_index(self):
        """测试构建外部依赖索引"""
        dep1 = ExternalDependencyModel(
            id=uuid4(),
            repository_id=uuid4(),
            ecosystem=ECOSYSTEM_PIP,
            artifact_name="flask",
            version="2.3.0",
        )

        dep2 = ExternalDependencyModel(
            id=uuid4(),
            repository_id=uuid4(),
            ecosystem=ECOSYSTEM_MAVEN,
            group_name="org.springframework",
            artifact_name="spring-core",
            version="6.0.0",
        )

        index = ModuleDependencyBuilder._build_ext_dep_index([dep1, dep2])
        assert "flask" in index
        assert "spring-core" in index
        assert "org.springframework/spring-core" in index

    def test_match_seed_rule_java(self):
        """测试 Java 种子规则匹配"""
        result = ModuleDependencyBuilder._match_seed_rule(
            "org.springframework.web.bind.annotation.getmapping",
            "src/controller/Controller.java",
        )
        assert result is not None
        # org.springframework 前缀先匹配到 spring-boot-starter
        assert "spring-boot" in result

    def test_match_seed_rule_python(self):
        """测试 Python 种子规则匹配"""
        result = ModuleDependencyBuilder._match_seed_rule(
            "flask",
            "src/app.py",
        )
        assert result == "flask"

    def test_match_seed_rule_ts(self):
        """测试 TS/JS 种子规则匹配"""
        result = ModuleDependencyBuilder._match_seed_rule(
            "react",
            "src/components/App.tsx",
        )
        assert result == "react"

    def test_match_seed_rule_no_match(self):
        """测试无匹配的种子规则"""
        result = ModuleDependencyBuilder._match_seed_rule(
            "unknown.package",
            "src/main.py",
        )
        assert result is None

    def test_match_seed_rule_wrong_language(self):
        """测试语言不匹配时种子规则不生效"""
        result = ModuleDependencyBuilder._match_seed_rule(
            "flask",
            "src/App.tsx",
        )
        assert result is None
