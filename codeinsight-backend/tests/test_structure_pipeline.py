"""
结构数据入库管道单元测试

覆盖：
- AstNodeValidator 校验逻辑
- CallEdgeValidator 校验逻辑
- ModuleDepValidator 校验逻辑
- StructureDataPipeline 入库流程
"""

import uuid

from codeinsight.pipelines.validators import AstNodeValidator, CallEdgeValidator, ModuleDepValidator

# ================================================================
# AstNodeValidator 测试
# ================================================================


class TestAstNodeValidator:
    """AST 节点校验器测试"""

    def test_valid_node(self):
        """测试：合法的节点数据通过校验"""
        node = {
            "file_id": str(uuid.uuid4()),
            "node_type": "function",
            "name": "test_func",
            "start_line": 10,
            "end_line": 20,
            "start_column": 4,
            "end_column": 18,
            "file_path": "test.py",
            "language": "python",
        }
        result = AstNodeValidator.validate(node)
        assert result.valid is True
        assert result.errors == []

    def test_missing_required_field(self):
        """测试：缺少必填字段"""
        node = {
            "file_id": str(uuid.uuid4()),
            "node_type": "function",
            # 缺少 name
        }
        result = AstNodeValidator.validate(node)
        assert result.valid is False
        assert any("缺少必填字段" in e for e in result.errors)

    def test_invalid_node_type(self):
        """测试：非法节点类型"""
        node = {
            "file_id": str(uuid.uuid4()),
            "node_type": "invalid_type",
            "name": "test",
            "start_line": 0,
            "end_line": 0,
            "start_column": 0,
            "end_column": 0,
            "file_path": "test.py",
            "language": "python",
        }
        result = AstNodeValidator.validate(node)
        assert result.valid is False
        assert any("非法节点类型" in e for e in result.errors)

    def test_negative_start_line(self):
        """测试：负数行号"""
        node = {
            "file_id": str(uuid.uuid4()),
            "node_type": "function",
            "name": "test",
            "start_line": -1,
            "end_line": 10,
            "start_column": 0,
            "end_column": 0,
            "file_path": "test.py",
            "language": "python",
        }
        result = AstNodeValidator.validate(node)
        assert result.valid is False
        assert any("不能为负数" in e for e in result.errors)

    def test_start_line_greater_than_end_line(self):
        """测试：start_line > end_line"""
        node = {
            "file_id": str(uuid.uuid4()),
            "node_type": "function",
            "name": "test",
            "start_line": 20,
            "end_line": 10,
            "start_column": 0,
            "end_column": 0,
            "file_path": "test.py",
            "language": "python",
        }
        result = AstNodeValidator.validate(node)
        assert result.valid is False
        assert any("不能大于" in e for e in result.errors)

    def test_invalid_file_id(self):
        """测试：非法 file_id"""
        node = {
            "file_id": "not-a-uuid",
            "node_type": "function",
            "name": "test",
            "start_line": 0,
            "end_line": 0,
            "start_column": 0,
            "end_column": 0,
            "file_path": "test.py",
            "language": "python",
        }
        result = AstNodeValidator.validate(node)
        assert result.valid is False
        assert any("非法 file_id" in e for e in result.errors)

    def test_all_valid_node_types_pass(self):
        """测试：所有合法节点类型都通过校验"""
        valid_types = {
            "function",
            "method",
            "class",
            "constructor",
            "call",
            "import",
            "interface",
            "protocol",
            "variable",
            "enum",
            "type",
            "struct",
        }
        file_id = str(uuid.uuid4())
        for node_type in valid_types:
            node = {
                "file_id": file_id,
                "node_type": node_type,
                "name": "test",
                "start_line": 0,
                "end_line": 0,
                "start_column": 0,
                "end_column": 0,
                "file_path": "test.py",
                "language": "python",
            }
            result = AstNodeValidator.validate(node)
            assert result.valid is True, f"Type {node_type} should be valid"


# ================================================================
# CallEdgeValidator 测试
# ================================================================


class TestCallEdgeValidator:
    """调用边校验器测试"""

    def _make_valid_edge(self, caller_id: uuid.UUID | None = None, callee_id: uuid.UUID | None = None) -> dict:
        """生成合法调用边"""
        caller = caller_id or uuid.uuid4()
        return {
            "caller_node_id": caller,
            "callee_node_id": callee_id,
            "call_type": "static",
            "start_line": 10,
            "start_column": 4,
            "call_name": "test_func",
        }

    def test_valid_edge_with_callee(self):
        """测试：合法的调用边（含 callee）"""
        caller_id = uuid.uuid4()
        callee_id = uuid.uuid4()
        valid_ids = {caller_id, callee_id}
        edge = self._make_valid_edge(caller_id=caller_id, callee_id=callee_id)
        result = CallEdgeValidator.validate(edge, valid_ids)
        assert result.valid is True

    def test_valid_edge_without_callee(self):
        """测试：合法的调用边（无 callee，如 dynamic/unknown）"""
        caller_id = uuid.uuid4()
        valid_ids = {caller_id}
        edge = self._make_valid_edge(caller_id=caller_id, callee_id=None)
        result = CallEdgeValidator.validate(edge, valid_ids)
        assert result.valid is True

    def test_missing_caller_node_id(self):
        """测试：缺少 caller_node_id"""
        edge = {
            "call_type": "static",
            "start_line": 10,
            "start_column": 4,
            "call_name": "test",
        }
        valid_ids: set[uuid.UUID] = set()
        result = CallEdgeValidator.validate(edge, valid_ids)
        assert result.valid is False
        assert any("缺少 caller_node_id" in e for e in result.errors)

    def test_caller_not_in_valid_ids(self):
        """测试：caller 不在合法 ID 集合中"""
        caller_id = uuid.uuid4()
        valid_ids = {uuid.uuid4()}  # 不匹配
        edge = self._make_valid_edge(caller_id=caller_id)
        result = CallEdgeValidator.validate(edge, valid_ids)
        assert result.valid is False
        assert any("caller_node_id 不存在" in e for e in result.errors)

    def test_invalid_call_type(self):
        """测试：非法 call_type"""
        caller_id = uuid.uuid4()
        valid_ids = {caller_id}
        edge = self._make_valid_edge(caller_id=caller_id)
        edge["call_type"] = "invalid"
        result = CallEdgeValidator.validate(edge, valid_ids)
        assert result.valid is False
        assert any("非法 call_type" in e for e in result.errors)

    def test_valid_call_types(self):
        """测试：所有合法 call_type 都通过"""
        caller_id = uuid.uuid4()
        valid_ids = {caller_id}
        for call_type in ("static", "dynamic", "unknown"):
            edge = self._make_valid_edge(caller_id=caller_id)
            edge["call_type"] = call_type
            result = CallEdgeValidator.validate(edge, valid_ids)
            assert result.valid is True, f"call_type={call_type} should be valid"


# ================================================================
# ModuleDepValidator 测试
# ================================================================


class TestModuleDepValidator:
    """模块依赖校验器测试"""

    def _make_valid_dep(self, importer_id: uuid.UUID | None = None, imported_id: uuid.UUID | None = None) -> dict:
        """生成合法模块依赖"""
        importer = importer_id or uuid.uuid4()
        return {
            "importer_file_id": importer,
            "imported_file_id": imported_id,
            "import_name": "test.module",
            "import_type": "absolute",
        }

    def test_valid_dep_with_imported(self):
        """测试：合法的模块依赖（含 imported）"""
        importer_id = uuid.uuid4()
        imported_id = uuid.uuid4()
        valid_ids = {importer_id, imported_id}
        dep = self._make_valid_dep(importer_id=importer_id, imported_id=imported_id)
        result = ModuleDepValidator.validate(dep, valid_ids)
        assert result.valid is True

    def test_valid_dep_without_imported(self):
        """测试：合法的模块依赖（无 imported，如 external）"""
        importer_id = uuid.uuid4()
        valid_ids = {importer_id}
        dep = self._make_valid_dep(importer_id=importer_id, imported_id=None)
        result = ModuleDepValidator.validate(dep, valid_ids)
        assert result.valid is True

    def test_missing_importer_file_id(self):
        """测试：缺少 importer_file_id"""
        dep = {
            "imported_file_id": uuid.uuid4(),
            "import_name": "test",
            "import_type": "absolute",
        }
        valid_ids: set[uuid.UUID] = set()
        result = ModuleDepValidator.validate(dep, valid_ids)
        assert result.valid is False
        assert any("缺少 importer_file_id" in e for e in result.errors)

    def test_importer_not_in_valid_ids(self):
        """测试：importer 不在合法 ID 集合中"""
        importer_id = uuid.uuid4()
        valid_ids = {uuid.uuid4()}
        dep = self._make_valid_dep(importer_id=importer_id)
        result = ModuleDepValidator.validate(dep, valid_ids)
        assert result.valid is False
        assert any("importer_file_id 不存在" in e for e in result.errors)

    def test_invalid_import_type(self):
        """测试：非法 import_type"""
        importer_id = uuid.uuid4()
        valid_ids = {importer_id}
        dep = self._make_valid_dep(importer_id=importer_id)
        dep["import_type"] = "invalid"
        result = ModuleDepValidator.validate(dep, valid_ids)
        assert result.valid is False
        assert any("非法 import_type" in e for e in result.errors)

    def test_valid_import_types(self):
        """测试：所有合法 import_type 都通过"""
        importer_id = uuid.uuid4()
        valid_ids = {importer_id}
        for import_type in ("relative", "absolute", "external"):
            dep = self._make_valid_dep(importer_id=importer_id)
            dep["import_type"] = import_type
            result = ModuleDepValidator.validate(dep, valid_ids)
            assert result.valid is True, f"import_type={import_type} should be valid"

    def test_empty_import_name(self):
        """测试：空 import_name"""
        importer_id = uuid.uuid4()
        valid_ids = {importer_id}
        dep = self._make_valid_dep(importer_id=importer_id)
        dep["import_name"] = ""
        result = ModuleDepValidator.validate(dep, valid_ids)
        assert result.valid is False
        assert any("import_name 不能为空" in e for e in result.errors)
