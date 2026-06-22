import typer
from pathlib import Path

_LETTER_TO_FLAG: dict[str, str] = {"m": "model", "c": "controller", "s": "schema"}

# Which cross-flags are valid per command type
_ALLOWED_EXTRA: dict[str, set[str]] = {
    "controller": {"model", "schema"},
    "model":      {"controller", "schema"},
    "schema":     {"model", "controller"},
    "event":      set(),
    "listener":   set(),
}


def parse_flags(args: list[str]) -> tuple[dict[str, bool], list[str]]:
    """
    Parse -m / -s / -c / --model / --schema / --controller and compound
    forms like --ms, --mcs, -cs (any permutation of m/c/s letters).
    Returns (flags_dict, unknown_args).
    """
    flags: dict[str, bool] = {"model": False, "controller": False, "schema": False}
    unknown: list[str] = []

    for arg in args:
        if arg.startswith("--"):
            token = arg[2:]
            if token in flags:
                flags[token] = True
            elif token and all(ch in "mcs" for ch in token) and len(set(token)) == len(token):
                for ch in token:
                    flags[_LETTER_TO_FLAG[ch]] = True
            else:
                unknown.append(arg)
        elif arg.startswith("-") and len(arg) >= 2:
            letters = arg[1:]
            if all(ch in "mcs" for ch in letters) and len(set(letters)) == len(letters):
                for ch in letters:
                    flags[_LETTER_TO_FLAG[ch]] = True
            else:
                unknown.append(arg)
        else:
            unknown.append(arg)

    return flags, unknown


# ── Helpers ───────────────────────────────────────────────────────────────────

def _relative_import(from_dir: str, to_dir: str) -> str:
    from pathlib import PurePosixPath
    from_parts = PurePosixPath(from_dir.replace("\\", "/")).parts
    to_parts   = PurePosixPath(to_dir.replace("\\", "/")).parts
    common = sum(1 for a, b in zip(from_parts, to_parts) if a == b)
    ups    = len(from_parts) - common
    downs  = to_parts[common:]
    return "." * (ups + 1) + ".".join(downs)


def _to_snake(name: str) -> str:
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _to_plural(name: str) -> str:
    if name.endswith("y"):
        return name[:-1] + "ies"
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return name + "es"
    return name + "s"


def _render(template_name: str, **context) -> str:
    from jinja2 import Environment, FileSystemLoader
    templates_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), keep_trailing_newline=True)
    return env.get_template(template_name).render(**context)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    typer.echo(f"  created  {path}")


# ── Generators ────────────────────────────────────────────────────────────────

def _gen_model(class_name: str, module_name: str, plural: str, st) -> None:
    content = _render("model.py.jinja2", class_name=class_name, table_name=plural)
    _write(Path(st.models_dir) / f"{module_name}.py", content)

    init_file   = Path(st.models_dir) / "__init__.py"
    import_line = f"from .{module_name} import {class_name}\n"
    existing    = init_file.read_text(encoding="utf-8") if init_file.exists() else ""
    if import_line not in existing:
        with open(init_file, "a", encoding="utf-8") as f:
            f.write(import_line)
    typer.echo(f"  updated  {init_file}")


def _gen_schema(class_name: str, module_name: str, st) -> None:
    content = _render("schema.py.jinja2", class_name=class_name)
    _write(Path(st.schemas_dir) / f"{module_name}.py", content)


def _gen_controller(
    class_name: str,
    module_name: str,
    url_prefix: str,
    plural: str,
    models_module: str,
    with_model: bool,
    st,
) -> None:
    content = _render(
        "controller.py.jinja2",
        class_name=class_name,
        module_name=module_name,
        url_prefix=url_prefix,
        tag=plural.replace("_", " "),
        models_module=models_module,
        with_model=with_model,
    )
    _write(Path(st.controllers_dir) / f"{module_name}_controller.py", content)


def _gen_event(class_name: str, module_name: str, st) -> None:
    content = _render("event.py.jinja2", class_name=class_name, module_name=module_name)
    _write(Path(st.events_dir) / f"{module_name}_event.py", content)


def _gen_listener(class_name: str, module_name: str, st) -> None:
    events_module = _relative_import(st.listeners_dir, st.events_dir)
    content = _render(
        "listener.py.jinja2",
        class_name=class_name,
        module_name=module_name,
        events_module=events_module,
    )
    _write(Path(st.listeners_dir) / f"{module_name}_listener.py", content)


# ── Entry point ───────────────────────────────────────────────────────────────

def run_make(kind: str, name: str, flags: dict[str, bool]) -> None:
    from forgeapi.config import load_config

    cfg = load_config()
    st  = cfg.structure

    allowed = _ALLOWED_EXTRA[kind]
    for flag_name, val in flags.items():
        if not val:
            continue
        if flag_name == kind:
            typer.echo(
                f"Error: --{flag_name} is redundant for make:{kind} — already generating it.",
                err=True,
            )
            raise typer.Exit(code=1)
        if flag_name not in allowed:
            typer.echo(
                f"Error: --{flag_name} is not applicable for make:{kind}.",
                err=True,
            )
            raise typer.Exit(code=1)

    class_name  = name[0].upper() + name[1:]
    module_name = _to_snake(class_name)

    if kind == "event":
        _gen_event(class_name, module_name, st)
        typer.echo("Done.")
        return

    if kind == "listener":
        _gen_listener(class_name, module_name, st)
        typer.echo("Done.")
        return

    # controller / model / schema with cross-generation
    gen_model      = (kind == "model")      or flags.get("model",      False)
    gen_controller = (kind == "controller") or flags.get("controller", False)
    gen_schema     = (kind == "schema")     or flags.get("schema",     False)

    plural        = _to_plural(module_name)
    url_prefix    = "/" + plural.replace("_", "-")
    models_module = _relative_import(st.controllers_dir, st.models_dir)

    if gen_model:
        _gen_model(class_name, module_name, plural, st)
    if gen_schema:
        _gen_schema(class_name, module_name, st)
    if gen_controller:
        _gen_controller(class_name, module_name, url_prefix, plural, models_module, gen_model, st)

    typer.echo("Done.")
