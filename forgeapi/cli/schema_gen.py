"""Builds ``app/schemas/<name>.py`` (Create / Update / Response) from a Tortoise model."""
from __future__ import annotations

import enum
import importlib
import re
from typing import Iterable

FIELD_TYPE_MAP: dict[str, str] = {
    "CharField": "str",
    "TextField": "str",
    "EmailField": "str",
    "URLField": "str",
    "IPAddressField": "str",
    "IntField": "int",
    "BigIntField": "int",
    "SmallIntField": "int",
    "FloatField": "float",
    "DecimalField": "Decimal",
    "BooleanField": "bool",
    "DatetimeField": "datetime",
    "DateField": "date",
    "TimeField": "time",
    "JSONField": "Any",
    "UUIDField": "UUID",
    "BinaryField": "bytes",
}

EXTRA_IMPORTS: dict[str, str] = {
    "Decimal": "from decimal import Decimal",
    "datetime": "from datetime import datetime",
    "date": "from datetime import date",
    "time": "from datetime import time",
    "Any": "from typing import Any",
    "UUID": "from uuid import UUID",
}

#: Provided by BaseSchema, never repeated in the generated classes.
AUTO_SKIP = {"id", "created_at", "updated_at"}

BACKWARD_RELATIONS = {
    "BackwardFKRelation",
    "BackwardOneToOneRelation",
    "ManyToManyFieldInstance",
    "ManyToManyRelation",
    "ReverseRelation",
}

FK_RELATIONS = {"ForeignKeyFieldInstance", "OneToOneFieldInstance"}

#: Fields that look like credentials are left out of the Response class.
SECRET_FIELD_RE = re.compile(r"password|passwd|secret|token|api_?key|_hash$", re.IGNORECASE)


def resolve_python_type(cls) -> tuple[str, str | None]:
    """Resolve a Python type class to (annotation_string, import_line_or_None).

    Handles built-ins, enums, and arbitrary classes from any module.
    """
    builtins = {str: "str", int: "int", float: "float", bool: "bool", bytes: "bytes"}
    if cls in builtins:
        return builtins[cls], None

    name = getattr(cls, "__name__", None)
    if not name:
        return "Any", EXTRA_IMPORTS["Any"]

    module = getattr(cls, "__module__", "builtins")
    if module == "builtins":
        return name, None

    return name, f"from {module} import {name}"


def literal_default(value) -> str | None:
    if value is None or callable(value):
        return None
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return repr(value)
    return None


def load_model_fields(class_name: str, module_dotted: str) -> tuple[list[dict], set[str]]:
    """Fields of ``<module_dotted>.<class_name>`` as dicts: name, type, nullable, default."""
    mod = importlib.import_module(module_dotted)
    model_cls = getattr(mod, class_name, None)
    if model_cls is None:
        return [], set()

    extra_imports: set[str] = set()
    fields: list[dict] = []

    for field_name, field in model_cls._meta.fields_map.items():
        if field_name in AUTO_SKIP:
            continue
        field_cls = type(field).__name__
        if field_cls in BACKWARD_RELATIONS:
            continue
        if field_cls in FK_RELATIONS:
            nullable = getattr(field, "null", False)
            fields.append({"name": field_name + "_id", "type": "int", "nullable": nullable, "default": None})
            continue

        py_type = FIELD_TYPE_MAP.get(field_cls)
        if py_type is None:
            python_type_cls = getattr(field, "python_type", None)
            if python_type_cls is not None:
                py_type, import_line = resolve_python_type(python_type_cls)
                if import_line:
                    extra_imports.add(import_line)
            else:
                py_type = "Any"

        if py_type in EXTRA_IMPORTS:
            extra_imports.add(EXTRA_IMPORTS[py_type])

        nullable = getattr(field, "null", False)
        default = literal_default(getattr(field, "default", None))
        fields.append({"name": field_name, "type": py_type, "nullable": nullable, "default": default})

    return fields, extra_imports


def build_schema_module(
    class_name: str,
    fields: list[dict],
    extra_imports: set[str],
    exclude: Iterable[str] = (),
) -> tuple[str, list[str]]:
    """Source of ``<Name>Create``, ``<Name>Update`` (derived) and ``<Name>Response``.

    ``exclude`` drops fields from every class.  Credential-looking fields (``password``,
    ``*_hash``, ``*token*``, ...) are dropped from the Response only: they are legitimate
    input, but must never be sent back.

    Returns ``(source, names of fields hidden from the Response automatically)``.
    """
    excluded = set(exclude)
    fields = [f for f in fields if f["name"] not in excluded]
    hidden = [f["name"] for f in fields if SECRET_FIELD_RE.search(f["name"])]
    response_fields = [f for f in fields if f["name"] not in hidden]

    required = [f for f in fields if not f["nullable"] and f["default"] is None]
    optional = [f for f in fields if f["nullable"] or f["default"] is not None]

    def create_line(f: dict) -> str:
        if not f["nullable"] and f["default"] is None:
            return f"    {f['name']}: {f['type']}"
        if f["nullable"]:
            return f"    {f['name']}: {f['type']} | None = None"
        return f"    {f['name']}: {f['type']} = {f['default']}"

    def response_line(f: dict) -> str:
        return f"    {f['name']}: {f['type']} | None = None" if f["nullable"] else f"    {f['name']}: {f['type']}"

    create_body = [create_line(f) for f in [*required, *optional]] or ["    pass  # TODO: add the input fields"]
    response_body = [response_line(f) for f in response_fields] or ["    pass  # TODO: add the output fields"]

    lines = ["from __future__ import annotations", ""]
    lines += sorted(extra_imports) + ([""] if extra_imports else [])
    lines += ["from forgeapi import BaseSchema, Schema", "", ""]
    lines += [f"class {class_name}Create(Schema):", *create_body, "", ""]
    lines += [f"{class_name}Update = {class_name}Create.partial(\"{class_name}Update\")", "", ""]
    lines += [f"class {class_name}Response(BaseSchema):", *response_body, ""]
    return "\n".join(lines), hidden
