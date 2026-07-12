"""
模块依赖图构建器单元测试

测试 ModuleDependencyBuilder 的核心功能。
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from codeinsight.analyzers.module_graph import ModuleDependencyBuilder


@dataclass
class FakeAstNode:
    """模拟 AstNode ORM 对象"""

    id: str = ""
    repository_id: str = ""
    file_id: str = ""
    node_type: str = "import"
    name: str = ""
    start_line: int = 1
    end_line: int = 1
    start_column: int = 0
    end_column: int = 0
    parent_node_id: str | None = None
    file_path: str = ""
    language: str = "python"
    signature: str | None = None
    docstring: str | None = None
    created_at: str = "2026-07-09T00:00:00Z"


@dataclass
class FakeFile:
    """模拟 File ORM 对象"""

    id: str = ""
    repository_id: str = ""
    path: str = ""
    absolute_path: str = ""
    language: str = "python"
    line_count: int = 0
    size_bytes: int = 0
    content_hash: str = ""
    created_at: str = "2026-07-09T00:00:00Z"
    updated_at: str = "2026-07-09T00:00:00Z"


# ======================== ModuleDependencyBuilder 测试 ========================


@pytest.fixture
def module_dep_builder():
    """创建 ModuleDependencyBuilder 实例"""
    return ModuleDependencyBuilder()


def test_resolve_module_path_absolute_python():
    """测试：解析绝对导入路径（Python 风格）"""
    import_name = "com.example.utils"
    importer_path = "/path/to/file.py"

    result = ModuleDependencyBuilder._resolve_module_path(import_name, importer_path)
    assert result == "com/example/utils"


def test_resolve_module_path_with_slashes():
    """测试：解析已包含斜杠的导入路径"""
    import_name = "package/submodule"
    importer_path = "/path/to/file.py"

    result = ModuleDependencyBuilder._resolve_module_path(import_name, importer_path)
    assert result == "package/submodule"


def test_resolve_module_path_relative():
    """测试：解析相对导入路径"""
    import_name = "../utils"
    importer_path = "/path/to/module/file.py"

    result = ModuleDependencyBuilder._resolve_module_path(import_name, importer_path)
    assert "utils" in result


def test_resolve_module_path_with_quotes():
    """测试：解析带引号的导入名称"""
    import_name = '"path"'
    importer_path = "/path/to/file.ts"

    result = ModuleDependencyBuilder._resolve_module_path(import_name, importer_path)
    assert result == "path"


def test_find_imported_file_exact_match():
    """测试：精确匹配导入目标文件"""
    file_index = {
        "utils/helpers.py": FakeFile(id="file-1", path="utils/helpers.py"),
        "utils/__init__.py": FakeFile(id="file-2", path="utils/__init__.py"),
    }
    file_index_reverse = {file.id: file.path for file in file_index.values()}
    builder = ModuleDependencyBuilder()

    result = builder._find_imported_file("utils/helpers.py", file_index, file_index_reverse)
    assert result is not None
    assert result.path == "utils/helpers.py"


def test_find_imported_file_prefix_match():
    """测试：前缀匹配导入目标文件（import com.example 匹配 com/example/file.py）"""
    file_index = {
        "com/example/MyClass.java": FakeFile(id="file-1", path="com/example/MyClass.java"),
        "com/example/util/Helper.java": FakeFile(id="file-2", path="com/example/util/Helper.java"),
    }
    file_index_reverse = {file.id: file.path for file in file_index.values()}
    builder = ModuleDependencyBuilder()

    result = builder._find_imported_file("com/example/MyClass", file_index, file_index_reverse)
    assert result is not None
    assert "MyClass" in result.path


def test_find_imported_file_entry_point_match():
    """测试：入口文件匹配（__init__.py, index.ts 等）"""
    file_index = {
        "utils/__init__.py": FakeFile(id="file-1", path="utils/__init__.py"),
        "utils/helpers.py": FakeFile(id="file-2", path="utils/helpers.py"),
    }
    file_index_reverse = {file.id: file.path for file in file_index.values()}
    builder = ModuleDependencyBuilder()

    result = builder._find_imported_file("utils", file_index, file_index_reverse)
    assert result is not None
    assert result.path == "utils/__init__.py"


def test_find_imported_file_not_found():
    """测试：找不到导入目标文件返回 None"""
    file_index = {
        "utils/helpers.py": FakeFile(id="file-1", path="utils/helpers.py"),
    }
    file_index_reverse = {file.id: file.path for file in file_index.values()}
    builder = ModuleDependencyBuilder()

    result = builder._find_imported_file("nonexistent/module", file_index, file_index_reverse)
    assert result is None


def test_determine_import_type_external():
    """测试：外部库标记为 external"""
    assert ModuleDependencyBuilder._determine_import_type("requests", None, "/path/to/file.py") == "external"


def test_determine_import_type_relative():
    """测试：相对导入标记为 relative"""
    imported_file = FakeFile(id="file-1", path="utils/helpers.py")
    assert (
        ModuleDependencyBuilder._determine_import_type("../utils", imported_file, "/path/to/module/file.py")
        == "relative"
    )
    assert ModuleDependencyBuilder._determine_import_type("./helpers", imported_file, "/path/to/file.py") == "relative"


def test_determine_import_type_absolute():
    """测试：绝对导入标记为 absolute"""
    imported_file = FakeFile(id="file-1", path="utils/helpers.py")
    assert (
        ModuleDependencyBuilder._determine_import_type("utils.helpers", imported_file, "/path/to/file.py") == "absolute"
    )


def test_match_dependencies_absolute_import():
    """测试：绝对导入匹配"""
    import_nodes = [
        FakeAstNode(id="import-1", node_type="import", name="utils.helpers", file_path="src/main.py"),
    ]
    file_index = {
        "utils/helpers.py": FakeFile(id="file-1", path="utils/helpers.py"),
        "src/main.py": FakeFile(id="file-2", path="src/main.py"),
    }
    file_index_reverse = {file.id: file.path for file in file_index.values()}
    repo_uuid = uuid4()
    builder = ModuleDependencyBuilder()

    deps = builder._match_dependencies(import_nodes, file_index, file_index_reverse, repo_uuid)
    assert len(deps) == 1
    assert deps[0]["import_type"] == "absolute"


def test_match_dependencies_external_import():
    """测试：外部库导入"""
    import_nodes = [
        FakeAstNode(id="import-1", node_type="import", name="requests", file_path="src/main.py"),
    ]
    file_index = {
        "src/main.py": FakeFile(id="file-2", path="src/main.py"),
    }
    file_index_reverse = {file.id: file.path for file in file_index.values()}
    repo_uuid = uuid4()
    builder = ModuleDependencyBuilder()

    deps = builder._match_dependencies(import_nodes, file_index, file_index_reverse, repo_uuid)
    assert len(deps) == 1
    assert deps[0]["import_type"] == "external"
    assert deps[0]["imported_file_id"] is None


@pytest.mark.asyncio
async def test_build_creates_dependencies():
    """测试：模块依赖构建创建依赖边"""
    builder = ModuleDependencyBuilder()

    # Mock AST nodes and files
    mock_nodes = [
        FakeAstNode(id="import-1", node_type="import", name="utils.helpers", file_path="src/main.py"),
    ]
    mock_files = [
        FakeFile(id="file-1", path="utils/helpers.py"),
        FakeFile(id="file-2", path="src/main.py"),
    ]

    # Mock DAOs
    builder.ast_dao = MagicMock()
    builder.ast_dao.get_by_repository_and_types = AsyncMock(return_value=mock_nodes)
    builder.file_dao = MagicMock()
    builder.file_dao.get_by_repository = AsyncMock(return_value=mock_files)
    builder.dep_dao = MagicMock()
    builder.dep_dao.delete_by_repository = AsyncMock(return_value=0)
    builder.dep_dao.create_many = AsyncMock(return_value=[])

    with patch("codeinsight.analyzers.module_graph.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()
        mock_session_factory.return_value = mock_session

        count = await builder.build(uuid4())
        assert count == 1
        builder.dep_dao.delete_by_repository.assert_called_once()
        builder.dep_dao.create_many.assert_called_once()
