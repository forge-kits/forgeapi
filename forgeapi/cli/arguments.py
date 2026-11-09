"""Turn the typed signature of ``Command.run`` into CLI arguments and options.

    def run(self, report_id: int, *emails: str, to: str = "me", dry_run: bool = False) -> None: ...

    forgeapi send:report 42 a@x.com b@x.com --to bob --dry-run

* a parameter without a default is a positional argument (``*names`` takes the rest);
* a parameter with a default (or keyword-only) is an option ``--name value`` / ``--name=value``,
  ``_`` becomes ``-`` in the option name;
* ``bool`` options are flags: ``--dry-run`` sets True, a ``True`` default is switched off with ``--no-name``;
* ``int``, ``float``, ``str``, ``Path`` and any type built from a string are converted, ``X | None`` is allowed,
  ``list[X]`` options may repeat: ``--tag a --tag b``.
"""
from __future__ import annotations

import inspect
import re
import types
import typing
from dataclasses import dataclass
from typing import Any

_NUMBER = re.compile(r"^-\d+(\.\d+)?$")
_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}


class ArgumentError(Exception):
    """The command line does not match the signature of ``run``."""


@dataclass
class _Param:
    name: str
    kind: str   # positional | variadic | option | flag | negated_flag
    type: Any = str
    many: bool = False
    required: bool = False
    default: Any = inspect.Parameter.empty

    @property
    def dashed(self) -> str:
        return self.name.replace("_", "-")


def _unwrap(annotation: Any) -> tuple[Any, bool]:
    """``(item type, is a list)``: ``X | None`` unwraps to X, ``list[X]`` to ``(X, True)``."""
    if annotation is inspect.Parameter.empty or isinstance(annotation, str):
        return str, False
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        inner = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _unwrap(inner[0]) if len(inner) == 1 else (str, False)
    if origin is list:
        args = typing.get_args(annotation)
        return (args[0] if args else str), True
    return annotation, False


def _specs(func: Any) -> list[_Param]:
    try:
        hints = typing.get_type_hints(getattr(func, "__func__", func))
    except Exception:
        hints = {}
    specs: list[_Param] = []
    for p in inspect.signature(func).parameters.values():
        if p.kind is p.VAR_KEYWORD:
            raise TypeError("run() cannot take **kwargs")
        tp, many = _unwrap(hints.get(p.name, p.annotation))
        has_default = p.default is not p.empty
        if p.kind is p.VAR_POSITIONAL:
            specs.append(_Param(p.name, "variadic", tp))
        elif tp is bool and (has_default or p.kind is p.KEYWORD_ONLY):
            negated = has_default and p.default is True
            specs.append(_Param(p.name, "negated_flag" if negated else "flag", bool, default=p.default))
        elif p.kind is p.KEYWORD_ONLY or has_default:
            specs.append(_Param(p.name, "option", tp, many, required=not has_default, default=p.default))
        elif many:
            raise TypeError(f"run(): use *{p.name}: {getattr(tp, '__name__', 'str')} to take several positional values")
        else:
            specs.append(_Param(p.name, "positional", tp))
    return specs


def _convert(raw: str, tp: Any, label: str) -> Any:
    if tp is bool:
        low = raw.lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise ArgumentError(f"{label}: '{raw}' is not a valid boolean (true/false)")
    if tp is str or tp is typing.Any or not callable(tp):
        return raw
    try:
        return tp(raw)
    except (ValueError, TypeError):
        raise ArgumentError(f"{label}: '{raw}' is not a valid {getattr(tp, '__name__', tp)}") from None


def bind(func: Any, args: list[str]) -> tuple[list[Any], dict[str, Any]]:
    """Match the raw command-line *args* to the signature of *func*: ``func(*values, **kwargs)``."""
    specs = _specs(func)
    positional = [s for s in specs if s.kind == "positional"]
    variadic = next((s for s in specs if s.kind == "variadic"), None)
    options: dict[str, _Param] = {}
    for s in specs:
        if s.kind in ("option", "flag", "negated_flag"):
            options[s.dashed] = s
            if s.kind == "negated_flag":
                options[f"no-{s.dashed}"] = s

    kwargs: dict[str, Any] = {}
    raw_positional: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        i += 1
        if token == "--":
            raw_positional.extend(args[i:])
            break
        if token.startswith("--"):
            name, has_value, value = token[2:].partition("=")
            spec = options.get(name)
            if spec is None:
                raise ArgumentError(f"unknown option --{name}")
            if spec.kind in ("flag", "negated_flag"):
                if has_value:
                    raise ArgumentError(f"option --{name} takes no value")
                kwargs[spec.name] = spec.kind == "flag" or name == spec.dashed
                continue
            if not has_value:
                if i >= len(args) or (args[i].startswith("-") and args[i] != "-" and not _NUMBER.match(args[i])):
                    raise ArgumentError(f"option --{name} needs a value")
                value = args[i]
                i += 1
            converted = _convert(value, spec.type, f"--{name}")
            if spec.many:
                kwargs.setdefault(spec.name, []).append(converted)
            else:
                kwargs[spec.name] = converted
            continue
        if token.startswith("-") and token != "-" and not _NUMBER.match(token):
            raise ArgumentError(f"unknown option {token}")
        raw_positional.append(token)

    values: list[Any] = []
    for idx, spec in enumerate(positional):
        if idx >= len(raw_positional):
            raise ArgumentError(f"missing argument <{spec.name}>")
        values.append(_convert(raw_positional[idx], spec.type, f"<{spec.name}>"))
    rest = raw_positional[len(positional):]
    if rest:
        if variadic is None:
            raise ArgumentError(f"unexpected argument '{rest[0]}'")
        values.extend(_convert(r, variadic.type, f"<{variadic.name}>") for r in rest)
    for s in specs:
        if s.kind == "option" and s.required and s.name not in kwargs:
            raise ArgumentError(f"missing required option --{s.dashed}")
    return values, kwargs


def help_text(func: Any, prog: str, summary: str = "") -> str:
    """A ``help_text`` generated from the signature (and docstring) of *func*."""
    specs = _specs(func)
    usage = [f"forgeapi {prog}"]
    rows_args: list[tuple[str, str]] = []
    rows_opts: list[tuple[str, str]] = []
    for s in specs:
        tname = getattr(s.type, "__name__", "str")
        if s.kind == "positional":
            usage.append(f"<{s.name}>")
            rows_args.append((f"<{s.name}>", tname))
        elif s.kind == "variadic":
            usage.append(f"[<{s.name}>...]")
            rows_args.append((f"<{s.name}>...", f"{tname}, any number"))
        elif s.kind in ("flag", "negated_flag"):
            flag = f"--{s.dashed}" if s.kind == "flag" else f"--no-{s.dashed}"
            usage.append(f"[{flag}]")
            rows_opts.append((flag, "flag"))
        else:
            opt = f"--{s.dashed} {s.name.upper()}"
            usage.append(opt if s.required else f"[{opt}]")
            note = "required" if s.required else (f"default: {s.default}" if s.default not in (None, "") else "")
            kind = f"{tname}, repeatable" if s.many else tname
            rows_opts.append((opt, f"{kind}, {note}" if note else kind))

    lines = [f"Usage: {' '.join(usage)}", ""]
    doc = (inspect.getdoc(func) or "").split("\n\n")[0].strip() or summary
    if doc:
        lines += [doc, ""]
    for title, rows in (("Arguments:", rows_args), ("Options:", rows_opts)):
        if rows:
            width = max(len(left) for left, _ in rows) + 2
            lines.append(title)
            lines += [f"  {left.ljust(width)}{right}" for left, right in rows]
    return "\n".join(lines) + "\n"
