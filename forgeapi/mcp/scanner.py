from __future__ import annotations

import tomllib
from pathlib import Path


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _ast_parse_safe(path: Path):
    import ast
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


def _node_name(node: object) -> str:
    import ast
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    return ""


def _call_name(node: object) -> str:
    import ast
    if isinstance(node, ast.Call):
        return _node_name(node.func)
    return _node_name(node)


def _scan_models(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    model_bases = {"Model", "PermissionsMixin", "ModelMixin"}
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if not any(b in model_bases for b in bases):
                continue
            table = node.name.lower()
            fields: list[str] = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if not isinstance(t, ast.Name) or t.id.startswith("_"):
                            continue
                        fname = _call_name(item.value)
                        if fname and "field" in fname.lower():
                            kwargs: list[str] = []
                            if isinstance(item.value, ast.Call):
                                for kw in item.value.keywords:
                                    if kw.arg in ("max_length", "null", "default", "primary_key",
                                                  "unique", "on_delete", "related_name"):
                                        if isinstance(kw.value, ast.Constant):
                                            kwargs.append(f"{kw.arg}={kw.value.value!r}")
                                        elif isinstance(kw.value, ast.Attribute):
                                            kwargs.append(f"{kw.arg}={_node_name(kw.value)}")
                            short  = fname.split(".")[-1]
                            kw_str = f"({', '.join(kwargs)})" if kwargs else ""
                            fields.append(f"    {t.id}: {short}{kw_str}")
                if isinstance(item, ast.ClassDef) and item.name == "Meta":
                    for meta_item in item.body:
                        if isinstance(meta_item, ast.Assign):
                            for t in meta_item.targets:
                                if isinstance(t, ast.Name) and t.id == "table":
                                    if isinstance(meta_item.value, ast.Constant):
                                        table = meta_item.value.value
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            out.append(f"  {node.name}  [table={table!r}]  ({rel})")
            if fields:
                out.extend(fields[:10])
                if len(fields) > 10:
                    out.append(f"    ... +{len(fields) - 10} more")
    return out


def _scan_controllers(files: list[Path], root: Path, base_prefix: str) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if not any("Controller" in b for b in bases):
                continue
            prefix = None
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name) and t.id == "prefix":
                            if isinstance(item.value, ast.Constant):
                                prefix = item.value.value
            routes: list[str] = []
            for item in node.body:
                if not isinstance(item, ast.AsyncFunctionDef):
                    continue
                for dec in item.decorator_list:
                    method = path = None
                    if isinstance(dec, ast.Attribute) and _node_name(dec.value) == "route":
                        method = dec.attr.upper()
                        path = "/"
                    elif isinstance(dec, ast.Call):
                        func = dec.func
                        if isinstance(func, ast.Attribute) and _node_name(func.value) == "route":
                            method = func.attr.upper()
                            path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else "/"
                    if method and path is not None:
                        full = f"{base_prefix}{prefix or ''}{path}".replace("//", "/")
                        routes.append(f"    {method:<6} {full}")
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            out.append(f"  {node.name}  prefix={prefix or 'auto'}  ({rel})")
            out.extend(routes)
    return out


def _scan_schemas(files: list[Path], root: Path) -> list[str]:
    import ast
    schema_bases = {"BaseSchema", "BaseCreateSchema", "BaseUpdateSchema", "BaseModel"}
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        classes: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if any(b in schema_bases for b in bases):
                classes.append(f"    {node.name}({', '.join(bases)})")
        if classes:
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            out.append(f"  {rel}:")
            out.extend(classes)
    return out


def _scan_events(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if "Event" not in bases:
                continue
            flags: list[str] = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name) and t.id == "background":
                            if isinstance(item.value, ast.Constant) and item.value.value:
                                flags.append("background")
                        if isinstance(t, ast.Name) and t.id == "redis":
                            if isinstance(item.value, ast.Constant) and item.value.value:
                                redis_type = "pubsub"
                                for item2 in node.body:
                                    if isinstance(item2, ast.Assign):
                                        for t2 in item2.targets:
                                            if isinstance(t2, ast.Name) and t2.id == "redis_type":
                                                if isinstance(item2.value, ast.Constant):
                                                    redis_type = item2.value.value
                                flags.append(f"redis/{redis_type}")
            init_params: list[str] = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for arg in item.args.args[1:]:
                        init_params.append(arg.arg)
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            out.append(f"  {node.name}{flag_str}")
            if init_params:
                out.append(f"    fields: {', '.join(init_params)}")
    return out


def _scan_listeners(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Name)
                    and dec.func.id == "listen"
                    and dec.args
                ):
                    event = _node_name(dec.args[0])
                    out.append(f"  {node.name}  →  {event}")
    return out


def _scan_seeders(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if any("Seeder" in b for b in bases):
                out.append(f"  {node.name}")
    return out


def _read_pyproject_deps(root: Path) -> list[str]:
    pp = root / "pyproject.toml"
    if not pp.exists():
        return []
    try:
        with open(pp, "rb") as fh:
            data = tomllib.load(fh)
        return data.get("project", {}).get("dependencies", [])
    except Exception:
        return []


def _read_env_keys(root: Path) -> list[str]:
    env = root / ".env"
    if not env.exists():
        return []
    keys: list[str] = []
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.append(line.split("=", 1)[0].strip())
    return keys


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def scan_project(path: str = ".") -> str:
    """Deep-scan a forge-kits project and return its full structure.

    Reads all Python source files via AST (no imports) to extract:
    - Tortoise ORM models with field names and types
    - Controllers with every registered route (METHOD + full path)
    - Pydantic schema classes grouped by file
    - Events (background/redis flags, field names)
    - Listeners and which events they handle
    - Seeders
    - pyproject.toml dependencies
    - .env variable names (values hidden)

    Use this at the start of every coding session on a forge-kits project so you
    have a complete picture of what already exists before making changes.

    Args:
        path: Path to the project root (directory containing forgeapi.toml).
              Defaults to current directory.

    Returns:
        Structured text report of the entire project.
    """
    given    = Path(path).expanduser().resolve()
    toml_path = given if (given.is_file() and given.name == "forgeapi.toml") else given / "forgeapi.toml"

    if not toml_path.exists():
        return (
            f"No forgeapi.toml found at '{given}'.\n"
            "Run `forgeapi init <name>` to scaffold a project."
        )

    try:
        with open(toml_path, "rb") as fh:
            raw = tomllib.load(fh)
    except Exception as exc:
        return f"Error reading forgeapi.toml: {exc}"

    root = toml_path.parent
    defaults = {
        "models_dir": "database/models", "controllers_dir": "app/controllers",
        "schemas_dir": "app/schemas",
        "listeners_dir": "app/listeners", "seeds_dir": "database/seeds",
        "base_prefix": "/api/v1",
    }
    struct      = {**defaults, **raw.get("structure", {})}
    proj        = raw.get("project", {})
    auth        = {**{"strategy": "cookie"}, **raw.get("auth", {})}
    base_prefix = struct["base_prefix"]

    sections: list[str] = [
        f"# Project: {proj.get('name', root.name)}  v{proj.get('version', '?')}",
        f"  auth={auth['strategy']}  prefix={base_prefix}",
        "",
    ]

    def _glob_py(dir_key: str, pattern: str) -> list[Path]:
        d = root / struct[dir_key]
        return sorted(d.rglob(pattern)) if d.exists() else []

    for label, dir_key, pattern, scanner in [
        ("Models",      "models_dir",      "*.py",              lambda f: _scan_models(f, root)),
        ("Controllers", "controllers_dir", "*_controller.py",   lambda f: _scan_controllers(f, root, base_prefix)),
        ("Schemas",     "schemas_dir",     "*.py",              lambda f: _scan_schemas(f, root)),
        ("Listeners",   "listeners_dir",   "*_listener.py",     lambda f: _scan_listeners(f, root)),
        ("Seeders",     "seeds_dir",       "*_seeder.py",       lambda f: _scan_seeders(f, root)),
    ]:
        files = _glob_py(dir_key, pattern)
        if label in ("Models", "Schemas"):
            files = [f for f in files if f.name != "__init__.py"]
        lines = scanner(files)
        sections.append(f"## {label}")
        sections.extend(lines if lines else ["  (none found)"])
        sections.append("")

    deps = _read_pyproject_deps(root)
    sections.append("## Dependencies (pyproject.toml)")
    sections.extend(f"  {d}" for d in deps) if deps else sections.append("  (pyproject.toml not found)")
    sections.append("")

    env_keys = _read_env_keys(root)
    sections.append("## .env variables (keys only)")
    sections.extend(f"  {k}" for k in env_keys) if env_keys else sections.append("  (.env not found)")

    return "\n".join(sections)


def project_info(path: str = ".") -> str:
    """Read a user's forgeapi.toml and return project structure information.

    Args:
        path: Path to the project directory or directly to forgeapi.toml.
              Defaults to the current directory.

    Returns:
        Formatted project configuration and directory structure summary.
    """
    given     = Path(path).expanduser().resolve()
    toml_path = given if (given.is_file() and given.name == "forgeapi.toml") else given / "forgeapi.toml"

    if not toml_path.exists():
        return (
            f"No forgeapi.toml found at '{given}'.\n\n"
            "Create one with: forgeapi init <project-name>\n"
            "Or run in a directory that contains forgeapi.toml."
        )

    try:
        with open(toml_path, "rb") as fh:
            raw = tomllib.load(fh)
    except Exception as exc:
        return f"Error reading forgeapi.toml: {exc}"

    root = toml_path.parent
    defaults = {
        "models_dir": "database/models", "controllers_dir": "app/controllers",
        "schemas_dir": "app/schemas",
        "listeners_dir": "app/listeners", "seeds_dir": "database/seeds",
        "base_prefix": "/api/v1",
    }
    struct = {**defaults, **raw.get("structure", {})}
    proj   = raw.get("project", {})
    auth   = {**{"strategy": "cookie"}, **raw.get("auth", {})}
    pag    = {**{"default_limit": 20, "max_limit": 100}, **raw.get("pagination", {})}

    lines = [
        f"# forge-kits project: {toml_path}", "",
        "## Project",
        f"  name    = {proj.get('name', 'my-app')!r}",
        f"  version = {proj.get('version', '0.1.0')!r}", "",
        "## Structure",
    ]

    for key, val in struct.items():
        marker = "" if key == "base_prefix" else (" [exists]" if (root / val).exists() else " [missing]")
        lines.append(f"  {key:<20} = {val!r}{marker}")

    lines += [
        "", "## Auth",
        f"  strategy = {auth['strategy']!r}",
        "", "## Pagination",
        f"  default_limit = {pag['default_limit']}",
        f"  max_limit     = {pag['max_limit']}",
        "",
    ]

    for label, dir_key, glob in [
        ("Controllers", "controllers_dir", "*_controller.py"),
        ("Listeners",   "listeners_dir",   "*_listener.py"),
    ]:
        d = root / struct[dir_key]
        if d.exists():
            files = sorted(d.rglob(glob))
            if files:
                lines.append(f"## {label} found")
                for f in files:
                    try:
                        lines.append(f"  {f.relative_to(root)}")
                    except ValueError:
                        lines.append(f"  {f}")
                lines.append("")

    return "\n".join(lines)
