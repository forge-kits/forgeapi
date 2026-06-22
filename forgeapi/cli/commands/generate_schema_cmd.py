from __future__ import annotations

import sys
from pathlib import Path


_FIELD_TYPE_MAP: dict[str, str] = {
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

_EXTRA_IMPORTS: dict[str, str] = {
    "Decimal": "from decimal import Decimal",
    "datetime": "from datetime import datetime",
    "date": "from datetime import date",
    "time": "from datetime import time",
    "Any": "from typing import Any",
    "UUID": "from uuid import UUID",
}

_AUTO_SKIP = {"id", "created_at", "updated_at"}

_BACKWARD_RELATIONS = {
    "BackwardFKRelation",
    "BackwardOneToOneRelation",
    "ManyToManyFieldInstance",
    "ManyToManyRelation",
    "ReverseRelation",
}

_FK_RELATIONS = {"ForeignKeyFieldInstance", "OneToOneFieldInstance"}


def _to_snake(name: str) -> str:
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _literal_default(value) -> str | None:
    if value is None or callable(value):
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return repr(value)
    return None


def run(model_name: str, config_path: str = "forgeapi.toml") -> None:
    import typer
    from forgeapi.config import load_config

    cfg = load_config(config_path)
    st = cfg.structure

    class_name = model_name[0].upper() + model_name[1:]
    module_name = _to_snake(class_name)
    module_dotted = st.models_dir.replace("\\", "/").replace("/", ".") + "." + module_name

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        import importlib
        mod = importlib.import_module(module_dotted)
    except ModuleNotFoundError as exc:
        typer.echo(f"Error: cannot import '{module_dotted}': {exc}", err=True)
        typer.echo("  Run from the project root with tortoise-orm installed.", err=True)
        raise typer.Exit(code=1)

    model_cls = getattr(mod, class_name, None)
    if model_cls is None:
        typer.echo(f"Error: class '{class_name}' not found in '{module_dotted}'.", err=True)
        raise typer.Exit(code=1)

    extra_imports: set[str] = set()
    fields: list[dict] = []

    for field_name, field in model_cls._meta.fields_map.items():
        if field_name in _AUTO_SKIP:
            continue

        field_cls = type(field).__name__

        if field_cls in _BACKWARD_RELATIONS:
            continue

        if field_cls in _FK_RELATIONS:
            nullable = getattr(field, "null", False)
            fields.append({"name": field_name + "_id", "type": "int", "nullable": nullable, "default": None})
            continue

        py_type = _FIELD_TYPE_MAP.get(field_cls, "Any")
        if py_type in _EXTRA_IMPORTS:
            extra_imports.add(_EXTRA_IMPORTS[py_type])

        nullable = getattr(field, "null", False)
        default = _literal_default(getattr(field, "default", None))

        fields.append({"name": field_name, "type": py_type, "nullable": nullable, "default": default})

    lines: list[str] = ["from __future__ import annotations", ""]
    for imp in sorted(extra_imports):
        lines.append(imp)
    if extra_imports:
        lines.append("")
    lines += ["from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema", ""]

    # Response schema
    lines.append(f"class {class_name}Schema(BaseSchema):")
    if fields:
        for f in fields:
            if f["nullable"]:
                lines.append(f"    {f['name']}: {f['type']} | None = None")
            else:
                lines.append(f"    {f['name']}: {f['type']}")
    else:
        lines.append("    pass")
    lines.append("")

    # Create schema — required fields first, then optional / defaulted
    lines.append(f"class {class_name}CreateSchema(BaseCreateSchema):")
    if fields:
        required = []
        optional = []
        for f in fields:
            if f["nullable"]:
                optional.append(f"    {f['name']}: {f['type']} | None = None")
            elif f["default"] is not None:
                optional.append(f"    {f['name']}: {f['type']} = {f['default']}")
            else:
                required.append(f"    {f['name']}: {f['type']}")
        for line in required + optional:
            lines.append(line)
        if not required and not optional:
            lines.append("    pass")
    else:
        lines.append("    pass")
    lines.append("")

    # Update schema — all Optional
    lines.append(f"class {class_name}UpdateSchema(BaseUpdateSchema):")
    if fields:
        for f in fields:
            lines.append(f"    {f['name']}: {f['type']} | None = None")
    else:
        lines.append("    pass")
    lines.append("")

    content = "\n".join(lines)

    out = Path(st.schemas_dir) / f"{module_name}.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    typer.echo(f"  created  {out}")
