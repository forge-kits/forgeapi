from __future__ import annotations

import sys
from pathlib import Path

from forgeapi.cli.base import Command


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


class GenerateSchemaCommand(Command):
    name = "generate:schema"
    help_text = """\
Usage: forgeapi generate:schema <Name> --payload [crud] | --response

Reads an existing Tortoise model and generates typed Pydantic schemas.
At least one of --payload or --response is required.

  --payload   schemas/payload/<name>.py   (input / request schemas)
  --response  schemas/response/<name>.py  (always: Response + ListResponse)

CRUD flags (--payload only):
  --crud     c+r+u  (default when --payload given without CRUD flags)
  -crud      c+r+u+d  (all four, including delete)
  --cu       create + update
  --cr       create + read
  -d         delete payload only
  (any letter combo of c r u d)

Generated classes:
  payload c → {Name}CreatePayload(BaseCreateSchema)
  payload r → {Name}GetPayload(BaseModel)
  payload u → {Name}UpdatePayload(BaseUpdateSchema)
  payload d → {Name}DeletePayload(BaseModel)
  response  → {Name}Response(BaseSchema)  +  {Name}ListResponse(BaseModel)

Examples:
  forgeapi generate:schema User --payload
  forgeapi generate:schema User --response
  forgeapi generate:schema User --payload --response
  forgeapi generate:schema User --payload -crud
  forgeapi generate:schema User --payload --cu
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        import typer
        from forgeapi.config import load_config

        model_name = next((a for a in args if not a.startswith("-") and a != "--model"), None)
        if not model_name:
            self.abort(
                "model name is required.\n"
                "  Example: forgeapi generate:schema User --payload"
            )

        extra_args = [a for a in args if a != model_name and a != "--model"]
        want_payload, want_response, explicit_crud, unknown = self._parse_flags(extra_args)

        if unknown:
            self.abort(f"unknown flags: {' '.join(unknown)}")

        if not want_payload and not want_response:
            self.abort(
                "specify --payload and/or --response.\n"
                "\n"
                "  forgeapi generate:schema User --payload\n"
                "  forgeapi generate:schema User --response\n"
                "  forgeapi generate:schema User --payload --response\n"
                "  forgeapi generate:schema User --payload --crud\n"
                "  forgeapi generate:schema User --payload -crud"
            )

        cfg = load_config()
        st = cfg.structure

        class_name = model_name[0].upper() + model_name[1:]
        module_name = self._to_snake(class_name)
        module_dotted = Path(st.models_dir).as_posix().replace("/", ".") + "." + module_name

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        fields: list[dict] = []
        extra_imports: set[str] = set()
        try:
            fields, extra_imports = self._load_model_fields(class_name, module_dotted)
        except ModuleNotFoundError:
            typer.echo(f"  note: model '{class_name}' not found — generating stubs")
        except Exception as exc:
            typer.echo(f"Warning: could not load model '{class_name}': {exc}", err=True)
            typer.echo("  Generating stubs.")

        payload_ops = explicit_crud if explicit_crud is not None else {"c", "r", "u"}

        if want_payload:
            self._ensure_init(Path(st.schemas_dir) / "payload")
            content = self._build_payload(class_name, payload_ops, fields, extra_imports)
            self._write(Path(st.schemas_dir) / "payload" / f"{module_name}.py", content, typer)

        if want_response:
            self._ensure_init(Path(st.schemas_dir) / "response")
            content = self._build_response(class_name, fields, extra_imports)
            self._write(Path(st.schemas_dir) / "response" / f"{module_name}.py", content, typer)

        typer.echo("Done.")

    # ── Flag parsing ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_flags(args: list[str]) -> tuple[bool, bool, set[str] | None, list[str]]:
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

    # ── Model loading ───────────────────────────────────────────────────────────

    @staticmethod
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
            default = GenerateSchemaCommand._literal_default(getattr(field, "default", None))
            fields.append({"name": field_name, "type": py_type, "nullable": nullable, "default": default})

        return fields, extra_imports

    @staticmethod
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

    # ── Content builders ────────────────────────────────────────────────────────

    @staticmethod
    def _type_imports_block(extra_imports: set[str]) -> list[str]:
        if not extra_imports:
            return []
        return sorted(extra_imports) + [""]

    @staticmethod
    def _trim(lines: list[str]) -> str:
        while lines and lines[-1] == "":
            lines.pop()
        lines.append("")
        return "\n".join(lines)

    def _build_payload(self, class_name: str, ops: set[str], fields: list[dict], extra_imports: set[str]) -> str:
        lines: list[str] = ["from __future__ import annotations", ""]
        lines += self._type_imports_block(extra_imports)

        need_base_model = "r" in ops or "d" in ops
        need_create     = "c" in ops
        need_update     = "u" in ops

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

        return self._trim(lines)

    def _build_response(self, class_name: str, fields: list[dict], extra_imports: set[str]) -> str:
        lines: list[str] = ["from __future__ import annotations", ""]
        lines += self._type_imports_block(extra_imports)

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

        return self._trim(lines)

    # ── I/O helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _write(path: Path, content: str, typer) -> None:
        if path.exists():
            typer.echo(f"  exists   {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        typer.echo(f"  created  {path}")

    @staticmethod
    def _ensure_init(directory: Path) -> None:
        import typer as _typer
        init = directory / "__init__.py"
        if not init.exists():
            directory.mkdir(parents=True, exist_ok=True)
            init.touch()
            _typer.echo(f"  created  {init}")

    @staticmethod
    def _to_snake(name: str) -> str:
        import re
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
