"""
数据校验器

提供入库前数据校验逻辑：
- AstNodeValidator: AST 节点校验
- CallEdgeValidator: 调用边校验
- ModuleDepValidator: 模块依赖校验
"""

from __future__ import annotations

import uuid


class ValidationResult:
    """
    单条数据校验结果

    PL-4 修复：移除 __slots__，避免 slots 中存储可变 list。
    """

    def __init__(self, valid: bool = True, errors: list[str] | None = None) -> None:
        self.valid = valid
        self.errors = errors or []

    def __repr__(self) -> str:
        return f"ValidationResult(valid={self.valid}, errors={self.errors})"


class AstNodeValidator:
    """AST 节点校验器"""

    VALID_NODE_TYPES: frozenset[str] = frozenset(
        {
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
    )

    REQUIRED_FIELDS: tuple[str, ...] = (
        "file_id",
        "node_type",
        "name",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "file_path",
        "language",
    )

    @classmethod
    def validate(cls, node: dict, valid_file_ids: set[uuid.UUID] | None = None) -> ValidationResult:
        """
        校验单个 AST 节点

        检查：
        1. 必填字段是否存在
        2. node_type 是否在白名单内
        3. 行号/列号是否为非负数
        4. file_id 是否为合法 UUID
        5. file_id 是否存在于合法文件 ID 集合（M-4 修复：确保节点属于当前仓库）

        Args:
            node: 节点数据字典
            valid_file_ids: 合法的文件 ID 集合（来自 files 表），为 None 时跳过此检查

        Returns:
            ValidationResult
        """
        errors: list[str] = []

        for field in cls.REQUIRED_FIELDS:
            if field not in node:
                errors.append(f"缺少必填字段: {field}")

        if errors:
            return ValidationResult(valid=False, errors=errors)

        node_type = node.get("node_type", "")
        if node_type not in cls.VALID_NODE_TYPES:
            errors.append(f"非法节点类型: {node_type}")

        for coord in ("start_line", "end_line", "start_column", "end_column"):
            val = node.get(coord)
            if isinstance(val, int) and val < 0:
                errors.append(f"{coord} 不能为负数: {val}")

        start_line = node.get("start_line", 0)
        end_line = node.get("end_line", 0)
        if isinstance(start_line, int) and isinstance(end_line, int) and start_line > end_line:
            errors.append(f"start_line ({start_line}) 不能大于 end_line ({end_line})")

        file_id = node.get("file_id")
        if file_id is not None:
            try:
                file_id = uuid.UUID(str(file_id))
            except (ValueError, AttributeError):
                errors.append(f"非法 file_id: {file_id}")

            if isinstance(file_id, uuid.UUID) and valid_file_ids is not None and file_id not in valid_file_ids:
                errors.append(f"file_id 不存在于当前仓库: {file_id}")

        return ValidationResult(valid=len(errors) == 0, errors=errors)


class CallEdgeValidator:
    """调用边校验器"""

    VALID_CALL_TYPES: frozenset[str] = frozenset({"static", "dynamic", "unknown"})

    @classmethod
    def validate(
        cls,
        edge: dict,
        valid_node_ids: set[uuid.UUID],
    ) -> ValidationResult:
        """
        校验单条调用边

        检查：
        1. caller_node_id 是否存在于合法节点 ID 集合
        2. callee_node_id 如果存在，是否合法
        3. call_type 是否在白名单内
        4. start_line / start_column 是否为非负数

        Args:
            edge: 调用边数据字典
            valid_node_ids: 合法的节点 ID 集合（来自 ast_nodes 表）

        Returns:
            ValidationResult
        """
        errors: list[str] = []

        # caller_node_id 必须存在且合法
        caller_id = edge.get("caller_node_id")
        if caller_id is None:
            errors.append("缺少 caller_node_id")
        elif not isinstance(caller_id, uuid.UUID):
            try:
                caller_id = uuid.UUID(str(caller_id))
            except (ValueError, AttributeError):
                errors.append(f"非法 caller_node_id: {caller_id}")

        if isinstance(caller_id, uuid.UUID) and caller_id not in valid_node_ids:
            errors.append(f"caller_node_id 不存在: {caller_id}")

        # callee_node_id 可选，但如果提供则必须合法
        callee_id = edge.get("callee_node_id")
        if callee_id is not None:
            if not isinstance(callee_id, uuid.UUID):
                try:
                    callee_id = uuid.UUID(str(callee_id))
                except (ValueError, AttributeError):
                    errors.append(f"非法 callee_node_id: {callee_id}")
            elif callee_id not in valid_node_ids:
                errors.append(f"callee_node_id 不存在: {callee_id}")

        # call_type 合法性
        call_type = edge.get("call_type", "static")
        if call_type not in cls.VALID_CALL_TYPES:
            errors.append(f"非法 call_type: {call_type}")

        # 行号/列号合法性
        for coord in ("start_line", "start_column"):
            val = edge.get(coord)
            if isinstance(val, int) and val < 0:
                errors.append(f"{coord} 不能为负数: {val}")

        return ValidationResult(valid=len(errors) == 0, errors=errors)


class ModuleDepValidator:
    """模块依赖校验器"""

    VALID_IMPORT_TYPES: frozenset[str] = frozenset({"relative", "absolute", "external"})

    @classmethod
    def validate(
        cls,
        dep: dict,
        valid_file_ids: set[uuid.UUID],
    ) -> ValidationResult:
        """
        校验单条模块依赖

        检查：
        1. importer_file_id 是否存在于合法文件 ID 集合
        2. imported_file_id 如果存在，是否合法
        3. import_type 是否在白名单内
        4. import_name 是否为非空字符串

        Args:
            dep: 模块依赖数据字典
            valid_file_ids: 合法的文件 ID 集合（来自 files 表）

        Returns:
            ValidationResult
        """
        errors: list[str] = []

        # importer_file_id 必须存在且合法
        importer_id = dep.get("importer_file_id")
        if importer_id is None:
            errors.append("缺少 importer_file_id")
        elif not isinstance(importer_id, uuid.UUID):
            try:
                importer_id = uuid.UUID(str(importer_id))
            except (ValueError, AttributeError):
                errors.append(f"非法 importer_file_id: {importer_id}")

        if isinstance(importer_id, uuid.UUID) and importer_id not in valid_file_ids:
            errors.append(f"importer_file_id 不存在: {importer_id}")

        # imported_file_id 可选，但如果提供则必须合法
        imported_id = dep.get("imported_file_id")
        if imported_id is not None:
            if not isinstance(imported_id, uuid.UUID):
                try:
                    imported_id = uuid.UUID(str(imported_id))
                except (ValueError, AttributeError):
                    errors.append(f"非法 imported_file_id: {imported_id}")
            elif imported_id not in valid_file_ids:
                errors.append(f"imported_file_id 不存在: {imported_id}")

        # import_type 合法性
        import_type = dep.get("import_type", "absolute")
        if import_type not in cls.VALID_IMPORT_TYPES:
            errors.append(f"非法 import_type: {import_type}")

        # import_name 非空
        import_name = dep.get("import_name", "")
        if not isinstance(import_name, str) or not import_name.strip():
            errors.append("import_name 不能为空")

        return ValidationResult(valid=len(errors) == 0, errors=errors)
