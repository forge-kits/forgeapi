from __future__ import annotations

import enum
from unittest.mock import MagicMock, patch

import pytest

from forgeapi.cli.commands.generate_schema_cmd import GenerateSchemaCommand


# ── Fixtures ──────────────────────────────────────────────────────────────────

class Status(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Priority(int, enum.Enum):
    LOW = 1
    HIGH = 2


# ── _resolve_python_type ──────────────────────────────────────────────────────

class TestResolvePythonType:
    def test_builtins(self):
        assert GenerateSchemaCommand._resolve_python_type(str) == ("str", None)
        assert GenerateSchemaCommand._resolve_python_type(int) == ("int", None)
        assert GenerateSchemaCommand._resolve_python_type(float) == ("float", None)
        assert GenerateSchemaCommand._resolve_python_type(bool) == ("bool", None)
        assert GenerateSchemaCommand._resolve_python_type(bytes) == ("bytes", None)

    def test_enum_returns_class_name_and_import(self):
        py_type, import_line = GenerateSchemaCommand._resolve_python_type(Status)
        assert py_type == "Status"
        assert import_line == f"from {Status.__module__} import Status"

    def test_int_enum_returns_class_name_and_import(self):
        py_type, import_line = GenerateSchemaCommand._resolve_python_type(Priority)
        assert py_type == "Priority"
        assert import_line == f"from {Priority.__module__} import Priority"

    def test_unknown_class_returns_any(self):
        py_type, import_line = GenerateSchemaCommand._resolve_python_type(None)
        assert py_type == "Any"
        assert import_line == "from typing import Any"


# ── _literal_default ──────────────────────────────────────────────────────────

class TestLiteralDefault:
    def test_none(self):
        assert GenerateSchemaCommand._literal_default(None) is None

    def test_callable_skipped(self):
        assert GenerateSchemaCommand._literal_default(lambda: "x") is None

    def test_bool(self):
        assert GenerateSchemaCommand._literal_default(True) == "True"
        assert GenerateSchemaCommand._literal_default(False) == "False"

    def test_int(self):
        assert GenerateSchemaCommand._literal_default(42) == "42"

    def test_float(self):
        assert GenerateSchemaCommand._literal_default(3.14) == "3.14"

    def test_str(self):
        assert GenerateSchemaCommand._literal_default("hello") == "'hello'"

    def test_enum_instance(self):
        assert GenerateSchemaCommand._literal_default(Status.ACTIVE) == "Status.ACTIVE"
        assert GenerateSchemaCommand._literal_default(Priority.HIGH) == "Priority.HIGH"

    def test_unknown_type_returns_none(self):
        assert GenerateSchemaCommand._literal_default(object()) is None


# ── _load_model_fields with enum ──────────────────────────────────────────────

class TestLoadModelFieldsEnum:
    def _make_char_enum_field(self, enum_cls, null=False, default=None):
        field = MagicMock()
        type(field).__name__ = "CharEnumFieldInstance"
        field.python_type = enum_cls
        field.null = null
        field.default = default
        return field

    def _make_int_enum_field(self, enum_cls, null=False, default=None):
        field = MagicMock()
        type(field).__name__ = "IntEnumFieldInstance"
        field.python_type = enum_cls
        field.null = null
        field.default = default
        return field

    def _make_model_cls(self, fields_map: dict):
        meta = MagicMock()
        meta.fields_map = fields_map
        model = MagicMock()
        model._meta = meta
        return model

    def _run(self, fields_map: dict):
        model_cls = self._make_model_cls(fields_map)
        module = MagicMock()
        module.MyModel = model_cls
        with patch("importlib.import_module", return_value=module):
            return GenerateSchemaCommand._load_model_fields("MyModel", "app.models.my_model")

    def test_char_enum_field_generates_correct_type(self):
        fields_map = {"status": self._make_char_enum_field(Status)}
        result_fields, extra_imports = self._run(fields_map)

        assert len(result_fields) == 1
        field = result_fields[0]
        assert field["name"] == "status"
        assert field["type"] == "Status"
        assert not field["nullable"]
        assert f"from {Status.__module__} import Status" in extra_imports

    def test_int_enum_field_generates_correct_type(self):
        fields_map = {"priority": self._make_int_enum_field(Priority)}
        result_fields, extra_imports = self._run(fields_map)

        assert result_fields[0]["type"] == "Priority"
        assert f"from {Priority.__module__} import Priority" in extra_imports

    def test_nullable_enum_field(self):
        fields_map = {"status": self._make_char_enum_field(Status, null=True)}
        result_fields, _ = self._run(fields_map)
        assert result_fields[0]["nullable"] is True

    def test_enum_default_value(self):
        fields_map = {"status": self._make_char_enum_field(Status, default=Status.ACTIVE)}
        result_fields, _ = self._run(fields_map)
        assert result_fields[0]["default"] == "Status.ACTIVE"

    def test_auto_skip_fields_excluded(self):
        id_field = self._make_char_enum_field(Status)
        status_field = self._make_char_enum_field(Status)
        fields_map = {"id": id_field, "created_at": id_field, "updated_at": id_field, "status": status_field}
        result_fields, _ = self._run(fields_map)
        names = [f["name"] for f in result_fields]
        assert "id" not in names
        assert "created_at" not in names
        assert "status" in names

    def test_custom_field_falls_back_via_python_type(self):
        custom_field = MagicMock()
        type(custom_field).__name__ = "CustomWeirdField"
        custom_field.python_type = str
        custom_field.null = False
        custom_field.default = None

        fields_map = {"slug": custom_field}
        result_fields, _ = self._run(fields_map)
        assert result_fields[0]["type"] == "str"

    def test_unknown_field_without_python_type_falls_back_to_any(self):
        custom_field = MagicMock(spec=[])
        type(custom_field).__name__ = "MysteriousField"
        custom_field.null = False
        custom_field.default = None

        fields_map = {"data": custom_field}
        result_fields, extra_imports = self._run(fields_map)
        assert result_fields[0]["type"] == "Any"
        assert "from typing import Any" in extra_imports
