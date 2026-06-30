import re
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
    "seed":       set(),
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
    # Different top-level packages — use absolute import
    if common == 0:
        return ".".join(to_parts)
    ups   = len(from_parts) - common
    downs = to_parts[common:]
    return "." * (ups + 1) + ".".join(downs)


def _to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _to_plural(name: str) -> str:
    if name.endswith("y"):
        return name[:-1] + "ies"
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return name + "es"
    return name + "s"


def _parse_namespace(class_name: str) -> tuple[str, str]:
    """Split CamelCase into (namespace_path, resource_word).

    All CamelCase words except the last form the namespace path (joined with '/').
    The last word is the resource.

    'User'              → ('',               'User')
    'AdminUser'         → ('admin',           'User')
    'SuperAdminUser'    → ('super/admin',     'User')
    'ApiV1AdminUser'    → ('api/v1/admin',    'User')
    """
    parts = re.findall(r'[A-Z][a-z0-9]*', class_name)
    if len(parts) >= 2:
        namespace = "/".join(p.lower() for p in parts[:-1])
        return namespace, parts[-1]
    return "", class_name


def _render(template_name: str, **context) -> str:
    from jinja2 import Environment, FileSystemLoader
    templates_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), keep_trailing_newline=True)
    return env.get_template(template_name).render(**context)


def _write(path: Path, content: str) -> bool:
    """Write file; skip and print 'exists' if already present. Returns True if created."""
    if path.exists():
        typer.echo(f"  exists   {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    typer.echo(f"  created  {path}")
    return True


def _ensure_init(directory: Path) -> None:
    """Create an empty __init__.py if it doesn't exist."""
    init = directory / "__init__.py"
    if not init.exists():
        directory.mkdir(parents=True, exist_ok=True)
        init.touch()
        typer.echo(f"  created  {init}")


# ── Generators ────────────────────────────────────────────────────────────────

def _gen_model(class_name: str, module_name: str, plural: str, st, alias: str | None = None) -> None:
    file_name = _to_snake(alias[0].upper() + alias[1:]) if alias else module_name
    file_path = Path(st.models_dir) / f"{file_name}.py"

    existing_text = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    append_mode   = bool(existing_text.strip())

    if append_mode and f"class {class_name}(Model):" in existing_text:
        typer.echo(f"  exists   {file_path} (class {class_name} already defined)")
    elif append_mode:
        chunk = _render("model.py.jinja2", class_name=class_name, table_name=plural, append=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + chunk)
        typer.echo(f"  updated  {file_path}")
    else:
        content = _render("model.py.jinja2", class_name=class_name, table_name=plural, append=False)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        typer.echo(f"  created  {file_path}")

    # Always update __init__.py (idempotent — checks for duplicate line)
    init_file   = Path(st.models_dir) / "__init__.py"
    import_line = f"from .{file_name} import {class_name}\n"
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
    ctrl_filename: str,
    url_prefix: str,
    tag: str,
    models_module: str,
    with_model: bool,
    st,
    namespace: str = "",
) -> None:
    content = _render(
        "controller.py.jinja2",
        class_name=class_name,
        module_name=module_name,
        url_prefix=url_prefix,
        tag=tag,
        models_module=models_module,
        with_model=with_model,
    )
    if namespace:
        ns_parts = namespace.split("/")
        # Ensure __init__.py exists at every level of the namespace path
        for i in range(1, len(ns_parts) + 1):
            _ensure_init(Path(st.controllers_dir).joinpath(*ns_parts[:i]))
        ctrl_dir = Path(st.controllers_dir).joinpath(*ns_parts)
        _write(ctrl_dir / f"{ctrl_filename}_controller.py", content)
    else:
        _write(Path(st.controllers_dir) / f"{ctrl_filename}_controller.py", content)


def _gen_seed(class_name: str, module_name: str, st) -> None:
    content = _render("seeder.py.jinja2", class_name=class_name)
    seeds_dir = getattr(st, "seeds_dir", "database/seeds")
    _write(Path(seeds_dir) / f"{module_name}_seeder.py", content)


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

def run_make(kind: str, name: str, flags: dict[str, bool], alias: str | None = None) -> None:
    from forgeapi.config import load_config

    cfg = load_config()
    st  = cfg.structure

    if alias and kind != "model":
        typer.echo("Error: --alias is only supported for make:model.", err=True)
        raise typer.Exit(code=1)

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

    if kind == "seed":
        _gen_seed(class_name, module_name, st)
        typer.echo("Done.")
        return

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

    # Detect namespace: last CamelCase word = resource, all preceding = namespace path
    namespace, resource_word = _parse_namespace(class_name)
    resource_module = _to_snake(resource_word)

    if namespace:
        resource_plural = _to_plural(resource_module)
        url_prefix      = f"/{namespace}/{resource_plural.replace('_', '-')}"
        tag             = f"{namespace.replace('/', ' ')} {resource_plural.replace('_', ' ')}"
        ns_parts        = namespace.split("/")
        ctrl_dir        = str(Path(st.controllers_dir).joinpath(*ns_parts))
        models_module   = _relative_import(ctrl_dir, st.models_dir)
        ctrl_filename   = resource_module
    else:
        plural        = _to_plural(module_name)
        url_prefix    = "/" + plural.replace("_", "-")
        tag           = plural.replace("_", " ")
        models_module = _relative_import(st.controllers_dir, st.models_dir)
        ctrl_filename = module_name

    # model and schema always use the full module_name (e.g. super_admin_user.py)
    plural = _to_plural(module_name)

    if gen_model:
        _gen_model(class_name, module_name, plural, st, alias=alias)
    if gen_schema:
        _gen_schema(class_name, module_name, st)
    if gen_controller:
        _gen_controller(
            class_name, module_name, ctrl_filename,
            url_prefix, tag, models_module, gen_model, st,
            namespace=namespace,
        )

    typer.echo("Done.")
