from __future__ import annotations

import re
from pathlib import Path

import typer

from forgeapi.cli.base import Command


_LETTER_TO_FLAG: dict[str, str] = {"m": "model", "c": "controller", "s": "schema"}
_VALID_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_ALLOWED_EXTRA: dict[str, set[str]] = {
    "controller": {"model", "schema"},
    "model":      {"controller", "schema"},
    "schema":     {"model", "controller"},
    "seed":       set(),
    "job":        set(),
    "policy":     set(),
    "observer":   set(),
    "provider":   set(),
}

_MAKE_KINDS = ("controller", "model", "schema", "seed", "job", "policy", "observer", "provider")


class MakeCommand(Command):
    name = "make"
    help_text = """\
make: commands

  make:controller <Name>   Generate controller  (-m -s)
  make:model <Name>        Generate model       (-c -s)
  make:schema <Name>       Generate stub schemas (-m -c)
  make:seed <Name>         Generate a seeder
  make:job <Name>          Generate a queue job
  make:policy <Model>      Generate a policy for a model
  make:observer <Model>    Generate a model observer
  make:provider <Name>     Generate a provider

Namespace controllers — each CamelCase word becomes a path segment:
  AdminUser      → controllers/admin/user_controller.py   /admin/users
  ApiV1User      → controllers/api/v1/user_controller.py  /api/v1/users

Flags combine: --ms  --mc  --mcs  -cs  etc.
Add -h after any subcommand for details.
"""

    _KIND_HELP = {
        "controller": """\
Usage: forgeapi make:controller <Name> [flags]

Generates a controller in controllers_dir.
CamelCase words before the last become a namespace subdirectory.

  User              → controllers/user_controller.py
  AdminUser         → controllers/admin/user_controller.py   /admin/users
  SuperAdminUser    → controllers/super/admin/user_controller.py

Flags:
  -m, --model    Also generate Tortoise model
  -s, --schema   Also generate stub schemas
  Compound: --ms  --mc  --mcs  -ms  etc.

Examples:
  forgeapi make:controller User
  forgeapi make:controller User --ms
  forgeapi make:controller AdminUser --ms
""",
        "model": """\
Usage: forgeapi make:model <Name> [flags]

Generates a Tortoise ORM model in models_dir.

Flags:
  -c, --controller      Also generate controller
  -s, --schema          Also generate stub schemas
  --alias <FileName>    Write model into models/<filename>.py instead of the
                        default <name>.py. If the file already exists and is
                        non-empty the new class is appended at the end.
  Compound: --cs  --mc  etc.

Examples:
  forgeapi make:model Post
  forgeapi make:model Post -cs
  forgeapi make:model Employee --alias Worker
  forgeapi make:model Contractor --alias Worker
""",
        "schema": """\
Usage: forgeapi make:schema <Name> [flags]

Generates stub Pydantic schemas (3 classes with pass).
For typed schemas from an existing model use generate:schema.

Flags:
  -m, --model        Also generate Tortoise model
  -c, --controller   Also generate controller

Examples:
  forgeapi make:schema Post
  forgeapi make:schema Post --mc
""",
        "job": """\
Usage: forgeapi make:job <Name>

Generates a queue Job in jobs_dir (default: app/jobs/).

Example:
  forgeapi make:job SendWelcomeEmail
  # → app/jobs/send_welcome_email.py   (class SendWelcomeEmail)
""",
        "policy": """\
Usage: forgeapi make:policy <Model>

Generates <Model>Policy in policies_dir (default: app/policies/), registered
with @gate.policy(<Model>) and picked up by gate.discover().
Import the model from models_dir, so create the model first (make:model).

Example:
  forgeapi make:policy Post
  # → app/policies/post_policy.py
""",
        "observer": """\
Usage: forgeapi make:observer <Model>

Generates <Model>Observer in observers_dir (default: app/observers/).
Observers are not auto-discovered: register with <Model>.observe(<Model>Observer)
at startup.

Example:
  forgeapi make:observer Post
  # → app/observers/post_observer.py
""",
        "provider": """\
Usage: forgeapi make:provider <Name>

Generates <Name>Provider in providers_dir (default: app/providers/).
Enable it by adding the dotted path to "providers" in config/project.py.

Example:
  forgeapi make:provider Metrics
  # → app/providers/metrics_provider.py   (class MetricsProvider)
""",
        "seed": """\
Usage: forgeapi make:seed <Name>

Generates a seeder file in seeds_dir (default: database/seeds/).

Example:
  forgeapi make:seed User
  # → database/seeds/user_seeder.py

  forgeapi make:seed AdminData
  # → database/seeds/admin_data_seeder.py
""",
    }

    def show_help(self, cmd: str = "") -> None:
        kind = cmd.split(":", 1)[1] if ":" in cmd else ""
        typer.echo(self._KIND_HELP.get(kind, self.help_text))

    def handle(self, cmd: str, args: list[str]) -> None:
        # cmd = "make" → show group help; "make:controller" → kind = "controller"
        if ":" not in cmd:
            typer.echo(self.help_text)
            return

        kind = cmd.split(":", 1)[1]

        if kind not in _MAKE_KINDS:
            self.abort(
                f"unknown command '{cmd}'.\n"
                f"  Available: {', '.join(f'make:{k}' for k in _MAKE_KINDS)}"
            )

        if not args or args[0].startswith("-"):
            self.abort(f"name is required.  Example: forgeapi make:{kind} MyName")

        name = args[0]
        remaining = list(args[1:])

        alias: str | None = None
        if "--alias" in remaining:
            idx = remaining.index("--alias")
            if idx + 1 >= len(remaining) or remaining[idx + 1].startswith("-"):
                self.abort("--alias requires a value.  Example: --alias Worker")
            alias = remaining[idx + 1]
            remaining = remaining[:idx] + remaining[idx + 2:]

        flags, unknown = self._parse_flags(remaining)
        if unknown:
            self.abort(f"unknown flags: {' '.join(unknown)}")

        self._run(kind=kind, name=name, flags=flags, alias=alias)

    def _run(self, kind: str, name: str, flags: dict[str, bool], alias: str | None) -> None:
        from forgeapi.config import load_config

        if not _VALID_NAME_RE.match(name):
            self.abort(
                "name must start with a letter and contain only letters, digits, "
                "and underscores (no slashes, dots, or other special characters)."
            )

        cfg = load_config()
        st = cfg.structure

        if alias and kind != "model":
            self.abort("--alias is only supported for make:model.")

        allowed = _ALLOWED_EXTRA[kind]
        for flag_name, val in flags.items():
            if not val:
                continue
            if flag_name == kind:
                self.abort(f"--{flag_name} is redundant for make:{kind} — already generating it.")
            if flag_name not in allowed:
                self.abort(f"--{flag_name} is not applicable for make:{kind}.")

        class_name = name[0].upper() + name[1:]
        module_name = self._to_snake(class_name)

        if kind == "seed":
            self._gen_seed(class_name, module_name, st)
            typer.echo("Done.")
            return

        if kind in ("job", "policy", "observer", "provider"):
            self._gen_simple(kind, class_name, st)
            typer.echo("Done.")
            return

        gen_model      = (kind == "model")      or flags.get("model",      False)
        gen_controller = (kind == "controller") or flags.get("controller", False)
        gen_schema     = (kind == "schema")     or flags.get("schema",     False)

        namespace, resource_word = self._parse_namespace(class_name)
        resource_module = self._to_snake(resource_word)

        if namespace:
            resource_plural = self._to_plural(resource_module)
            url_prefix    = f"/{namespace}/{resource_plural.replace('_', '-')}"
            tag           = f"{namespace.replace('/', ' ')} {resource_plural.replace('_', ' ')}"
            ns_parts      = namespace.split("/")
            ctrl_dir      = str(Path(st.controllers_dir).joinpath(*ns_parts))
            models_module = self._relative_import(ctrl_dir, st.models_dir)
            ctrl_filename = resource_module
        else:
            plural        = self._to_plural(module_name)
            url_prefix    = "/" + plural.replace("_", "-")
            tag           = plural.replace("_", " ")
            models_module = self._relative_import(st.controllers_dir, st.models_dir)
            ctrl_filename = module_name

        plural = self._to_plural(module_name)

        if gen_model:
            self._gen_model(class_name, module_name, plural, st, alias=alias)
        if gen_schema:
            self._gen_schema(class_name, module_name, st)
        if gen_controller:
            self._gen_controller(
                class_name, module_name, ctrl_filename,
                url_prefix, tag, models_module, gen_model, st,
                namespace=namespace,
            )

        typer.echo("Done.")

    # ── Generators ─────────────────────────────────────────────────────────────

    def _gen_model(self, class_name: str, module_name: str, plural: str, st, alias: str | None = None) -> None:
        file_name = self._to_snake(alias[0].upper() + alias[1:]) if alias else module_name
        file_path = Path(st.models_dir) / f"{file_name}.py"

        existing_text = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        append_mode   = bool(existing_text.strip())

        if append_mode and f"class {class_name}(Model):" in existing_text:
            typer.echo(f"  exists   {file_path} (class {class_name} already defined)")
        elif append_mode:
            chunk = self._render("model.py.jinja2", class_name=class_name, table_name=plural, append=True)
            with open(file_path, "a", encoding="utf-8", newline="") as f:
                f.write("\n\n" + chunk)
            typer.echo(f"  updated  {file_path}")
        else:
            content = self._render("model.py.jinja2", class_name=class_name, table_name=plural, append=False)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            typer.echo(f"  created  {file_path}")

        init_file   = Path(st.models_dir) / "__init__.py"
        import_line = f"from .{file_name} import {class_name}\n"
        existing    = init_file.read_text(encoding="utf-8") if init_file.exists() else ""
        if import_line not in existing:
            with open(init_file, "a", encoding="utf-8", newline="") as f:
                f.write(import_line)
            typer.echo(f"  updated  {init_file}")

    def _gen_schema(self, class_name: str, module_name: str, st) -> None:
        content = self._render("schema.py.jinja2", class_name=class_name)
        self._write(Path(st.schemas_dir) / f"{module_name}.py", content)

    def _gen_controller(
        self,
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
        content = self._render(
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
            for i in range(1, len(ns_parts) + 1):
                self._ensure_init(Path(st.controllers_dir).joinpath(*ns_parts[:i]))
            ctrl_dir = Path(st.controllers_dir).joinpath(*ns_parts)
            self._write(ctrl_dir / f"{ctrl_filename}_controller.py", content)
        else:
            self._write(Path(st.controllers_dir) / f"{ctrl_filename}_controller.py", content)

    def _gen_seed(self, class_name: str, module_name: str, st) -> None:
        content = self._render("seeder.py.jinja2", class_name=class_name)
        seeds_dir = getattr(st, "seeds_dir", "database/seeds")
        self._write(Path(seeds_dir) / f"{module_name}_seeder.py", content)

    _SIMPLE_SUFFIX = {"policy": "Policy", "observer": "Observer", "provider": "Provider"}

    def _gen_simple(self, kind: str, class_name: str, st) -> None:
        """job / policy / observer / provider: one file, no flags."""
        suffix = self._SIMPLE_SUFFIX.get(kind, "")
        if suffix and class_name.endswith(suffix) and len(class_name) > len(suffix):
            class_name = class_name[: -len(suffix)]
        module_name = self._to_snake(class_name)
        directory = {
            "job": st.jobs_dir,
            "policy": st.policies_dir,
            "observer": st.observers_dir,
            "provider": st.providers_dir,
        }[kind]
        file_name = f"{module_name}_{kind}.py" if suffix else f"{module_name}.py"

        context: dict = {"class_name": class_name}
        if kind == "policy":
            context["models_module"] = self._relative_import(directory, st.models_dir)
            context["var_name"] = module_name
        elif kind == "observer":
            context["models_import"] = ".".join(Path(st.models_dir).parts)
            context["observer_import"] = ".".join([*Path(directory).parts, file_name[:-3]])
        elif kind == "provider":
            context["dotted_path"] = ".".join([*Path(directory).parts, file_name[:-3], f"{class_name}Provider"])

        for i in range(1, len(Path(directory).parts) + 1):
            self._ensure_init(Path(*Path(directory).parts[:i]))
        created = self._write(Path(directory) / file_name, self._render(f"{kind}.py.jinja2", **context))

        if created and kind == "provider":
            typer.echo(f'  next     add "{context["dotted_path"]}" to "providers" in config/project.py')
        if created and kind == "observer":
            typer.echo(
                f"  next     {class_name}.observe({class_name}Observer) at startup (main.py or a Provider); "
                f"{class_name} must use ModelMixin"
            )

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_flags(args: list[str]) -> tuple[dict[str, bool], list[str]]:
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

    @staticmethod
    def _to_snake(name: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

    @staticmethod
    def _to_plural(name: str) -> str:
        if name.endswith("y"):
            return name[:-1] + "ies"
        if name.endswith(("s", "x", "z", "ch", "sh")):
            return name + "es"
        return name + "s"

    @staticmethod
    def _parse_namespace(class_name: str) -> tuple[str, str]:
        parts = re.findall(r'[A-Z][a-z0-9]*', class_name)
        if len(parts) >= 2:
            namespace = "/".join(p.lower() for p in parts[:-1])
            return namespace, parts[-1]
        return "", class_name

    @staticmethod
    def _relative_import(from_dir: str, to_dir: str) -> str:
        from pathlib import PurePosixPath
        from_parts = PurePosixPath(Path(from_dir).as_posix()).parts
        to_parts   = PurePosixPath(Path(to_dir).as_posix()).parts
        common = sum(1 for a, b in zip(from_parts, to_parts) if a == b)
        if common == 0:
            return ".".join(to_parts)
        ups   = len(from_parts) - common
        downs = to_parts[common:]
        return "." * (ups + 1) + ".".join(downs)

    @staticmethod
    def _render(template_name: str, **context) -> str:
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), keep_trailing_newline=True)
        return env.get_template(template_name).render(**context)

    @staticmethod
    def _write(path: Path, content: str) -> bool:
        if path.exists():
            typer.echo(f"  exists   {path}")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        typer.echo(f"  created  {path}")
        return True

    @staticmethod
    def _ensure_init(directory: Path) -> None:
        init = directory / "__init__.py"
        if not init.exists():
            directory.mkdir(parents=True, exist_ok=True)
            init.touch()
            typer.echo(f"  created  {init}")
