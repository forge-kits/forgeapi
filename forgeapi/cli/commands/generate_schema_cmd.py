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


def _load_model_fields(class_name: str, module_dotted: str) -> tuple[list[dict], set[str]]:
    import importlib
    mod = importlib.import_module(module_dotted)
    model_cls = getattr(mod, class_name, None)
    if model_cls is None:
        return [], set()

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

    return fields, extra_imports


def _parse_schema_flags(args: list[str]) -> tuple[bool, bool, set[str] | None, list[str]]:
    """Parse --payload / --response and CRUD letter flags.

    CRUD rules:
      --crud       → {c, r, u}  (standard CRUD, no delete)
      --cru / --cu → literal letters
      -crud        → {c, r, u, d}  (compound short, all four)
      -cru / -cu   → literal letters

    CRUD flags only apply to --payload; --response always produces the full
    single Response + ListResponse pair regardless of any CRUD flags.

    Returns (want_payload, want_response, crud_ops | None, unknown_args).
    crud_ops is None when no CRUD flags given — callers apply their own defaults.
    """
    want_payload = False
    want_response = False
    crud_ops: set[str] = set()
    has_explicit_crud = False
    unknown: list[str] = []

    for arg in args:
        if arg == "--payload":
            want_payload = True
        elif arg == "--response":
            want_response = True
        elif arg == "--crud":
            # --crud (long flag) = standard CRUD without delete
            crud_ops |= {"c", "r", "u"}
            has_explicit_crud = True
        elif arg.startswith("--") and len(arg) > 2:
            token = arg[2:]
            if token and all(ch in "crud" for ch in token) and len(set(token)) == len(token):
                crud_ops |= set(token)
                has_explicit_crud = True
            else:
                unknown.append(arg)
        elif arg.startswith("-") and not arg.startswith("--") and len(arg) >= 2:
            letters = arg[1:]
            if letters and all(ch in "crud" for ch in letters) and len(set(letters)) == len(letters):
                crud_ops |= set(letters)
                has_explicit_crud = True
            else:
                unknown.append(arg)
        else:
            unknown.append(arg)

    return want_payload, want_response, (crud_ops if has_explicit_crud else None), unknown


# ── Content builders ──────────────────────────────────────────────────────────

def _type_imports_block(extra_imports: set[str]) -> list[str]:
    if not extra_imports:
        return []
    return sorted(extra_imports) + [""]


def _build_payload(class_name: str, ops: set[str], fields: list[dict], extra_imports: set[str]) -> str:
    lines: list[str] = ["from __future__ import annotations", ""]
    lines += _type_imports_block(extra_imports)

    need_base_model  = "r" in ops or "d" in ops
    need_create      = "c" in ops
    need_update      = "u" in ops

    forgeapi_imports = [x for x in ("BaseCreateSchema", "BaseUpdateSchema")
                        if (x == "BaseCreateSchema" and need_create) or (x == "BaseUpdateSchema" and need_update)]

    if need_base_model:
        lines.append("from pydantic import BaseModel")
    if forgeapi_imports:
        lines.append(f"from forgeapi import {', '.join(forgeapi_imports)}")
    lines.append("")

    def _section(cls_name: str, base: str, body_lines: list[str]) -> None:
        lines.append("")
        lines.append(f"class {cls_name}({base}):")
        lines.extend(body_lines if body_lines else ["    pass"])
        lines.append("")

    if "c" in ops:
        body: list[str] = []
        if fields:
            required = [f"    {f['name']}: {f['type']}" for f in fields
                        if not f["nullable"] and f["default"] is None]
            optional = [
                f"    {f['name']}: {f['type']} | None = None" if f["nullable"]
                else f"    {f['name']}: {f['type']} = {f['default']}"
                for f in fields if f["nullable"] or f["default"] is not None
            ]
            body = required + optional
        _section(f"{class_name}CreatePayload", "BaseCreateSchema", body)

    if "r" in ops:
        body = [f"    {f['name']}: {f['type']} | None = None" for f in fields] if fields else []
        _section(f"{class_name}GetPayload", "BaseModel", body)

    if "u" in ops:
        body = [f"    {f['name']}: {f['type']} | None = None" for f in fields] if fields else []
        _section(f"{class_name}UpdatePayload", "BaseUpdateSchema", body)

    if "d" in ops:
        _section(f"{class_name}DeletePayload", "BaseModel", [])

    return _trim(lines)


def _build_response(class_name: str, fields: list[dict], extra_imports: set[str]) -> str:
    lines: list[str] = ["from __future__ import annotations", ""]
    lines += _type_imports_block(extra_imports)

    lines.append("from forgeapi import BaseSchema")
    lines.append("from pydantic import BaseModel")
    lines.append("")

    def _schema_body() -> list[str]:
        if not fields:
            return ["    pass"]
        return [
            f"    {f['name']}: {f['type']} | None = None" if f["nullable"]
            else f"    {f['name']}: {f['type']}"
            for f in fields
        ]

    def _section(cls_name: str, base: str, body_lines: list[str]) -> None:
        lines.append("")
        lines.append(f"class {cls_name}({base}):")
        lines.extend(body_lines if body_lines else ["    pass"])
        lines.append("")

    _section(f"{class_name}Response", "BaseSchema", _schema_body())
    _section(
        f"{class_name}ListResponse", "BaseModel",
        [f"    items: list[{class_name}Response]", "    total: int"],
    )

    return _trim(lines)


def _trim(lines: list[str]) -> str:
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")
    return "\n".join(lines)


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _write(path: Path, content: str) -> None:
    import typer
    if path.exists():
        typer.echo(f"  exists   {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    typer.echo(f"  created  {path}")


def _ensure_init(directory: Path) -> None:
    import typer
    init = directory / "__init__.py"
    if not init.exists():
        directory.mkdir(parents=True, exist_ok=True)
        init.touch()
        typer.echo(f"  created  {init}")


# ── Entry point ───────────────────────────────────────────────────────────────

def run(model_name: str, extra_args: list[str] | None = None, config_path: str = "forgeapi.toml") -> None:
    import typer
    from forgeapi.config import load_config

    extra_args = extra_args or []
    cfg = load_config(config_path)
    st = cfg.structure

    want_payload, want_response, explicit_crud, unknown = _parse_schema_flags(extra_args)

    if unknown:
        typer.echo(f"Error: unknown flags: {' '.join(unknown)}", err=True)
        raise typer.Exit(code=1)

    if not want_payload and not want_response:
        typer.echo(
            "Error: specify --payload and/or --response.\n"
            "\n"
            "  forgeapi generate:schema User --payload            # CreatePayload, GetPayload, UpdatePayload\n"
            "  forgeapi generate:schema User --response           # GetResponse + ListResponse\n"
            "  forgeapi generate:schema User --payload --crud     # cru (same as default)\n"
            "  forgeapi generate:schema User --payload -crud      # all four incl. delete\n"
            "  forgeapi generate:schema User --payload --response",
            err=True,
        )
        raise typer.Exit(code=1)

    class_name = model_name[0].upper() + model_name[1:]
    module_name = _to_snake(class_name)
    module_dotted = Path(st.models_dir).as_posix().replace("/", ".") + "." + module_name

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    fields: list[dict] = []
    extra_imports: set[str] = set()
    try:
        fields, extra_imports = _load_model_fields(class_name, module_dotted)
    except Exception:
        typer.echo(f"  note: model '{class_name}' not found — generating stubs")

    # Per-mode defaults when no CRUD flags were given
    payload_ops = explicit_crud if explicit_crud is not None else {"c", "r", "u"}

    if want_payload:
        _ensure_init(Path(st.schemas_dir) / "payload")
        content = _build_payload(class_name, payload_ops, fields, extra_imports)
        _write(Path(st.schemas_dir) / "payload" / f"{module_name}.py", content)

    if want_response:
        _ensure_init(Path(st.schemas_dir) / "response")
        content = _build_response(class_name, fields, extra_imports)
        _write(Path(st.schemas_dir) / "response" / f"{module_name}.py", content)

    typer.echo("Done.")
