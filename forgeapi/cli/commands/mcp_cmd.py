from __future__ import annotations

import json
import sys
from pathlib import Path

from forgeapi.cli.base import Command


class McpCommand(Command):
    name = "mcp:install"
    aliases = ("mcp:remove", "mcp:status")
    help_text = """\
Usage:
  forgeapi mcp:install [--global] [--force]
  forgeapi mcp:remove  [--global]
  forgeapi mcp:status  [--global]

Registers (or removes) the forge-kits MCP server in Claude Code settings.

Options:
  --global    Write to ~/.claude/settings.json  (all projects)
              Default: prompt to choose scope
  --project   Write to .claude/settings.json (current project only)
  --force     Overwrite existing entry

Examples:
  forgeapi mcp:install             # prompts for scope
  forgeapi mcp:install --global    # global (all Claude projects)
  forgeapi mcp:install --project   # project-level only
  forgeapi mcp:remove --global     # remove from global settings
  forgeapi mcp:status              # show current registration status
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        import typer

        is_global = "--global" in args or "-g" in args
        is_project = "--project" in args or "-p" in args
        force = "--force" in args or "-f" in args

        if cmd == "mcp:status":
            self._status(typer)
            return

        if not is_global and not is_project:
            scope = self._prompt_scope(typer)
            is_global = scope == "global"

        settings_path = self._settings_path(is_global)

        if cmd == "mcp:remove":
            self._remove(settings_path, typer)
        else:
            self._install(settings_path, is_global, force, typer)

    # ------------------------------------------------------------------

    def _prompt_scope(self, typer) -> str:
        typer.echo("")
        typer.echo("Install scope:")
        typer.echo("  1. project  — .claude/settings.json  (this project only)")
        typer.echo("  2. global   — ~/.claude/settings.json (all projects)")
        typer.echo("")
        choices = {
            "1": "project", "2": "global",
            "project": "project", "global": "global",
        }
        while True:
            raw = typer.prompt("Choose [1/2]", default="1")
            scope = choices.get(raw.strip().lower())
            if scope:
                return scope
            typer.echo("  Invalid choice. Enter 1 or 2.", err=True)

    def _settings_path(self, is_global: bool) -> Path:
        if is_global:
            return Path.home() / ".claude" / "settings.json"
        return Path.cwd() / ".claude" / "settings.json"

    def _install(self, settings_path: Path, is_global: bool, force: bool, typer) -> None:
        mcp_bin = self._find_mcp_bin()
        data = self._read_settings(settings_path)
        data.setdefault("mcpServers", {})

        if "forge-kits" in data["mcpServers"] and not force:
            existing = data["mcpServers"]["forge-kits"].get("command", "?")
            typer.echo(f"  Already registered in {settings_path}")
            typer.echo(f"  command: {existing}")
            typer.echo("  Use --force to overwrite.")
            raise typer.Exit()

        data["mcpServers"]["forge-kits"] = {
            "command": mcp_bin,
            "type": "stdio",
        }

        self._write_settings(settings_path, data)

        scope = "global" if is_global else "project"
        typer.echo(f"\n  forge-kits MCP server registered ({scope})")
        typer.echo(f"  config : {settings_path}")
        typer.echo(f"  command: {mcp_bin}")
        typer.echo("\n  Restart Claude Code for changes to take effect.")

    def _remove(self, settings_path: Path, typer) -> None:
        if not settings_path.exists():
            typer.echo(f"  {settings_path} not found — nothing to remove.")
            raise typer.Exit()

        data = self._read_settings(settings_path)
        servers = data.get("mcpServers", {})

        if "forge-kits" not in servers:
            typer.echo("  forge-kits not found in settings — nothing to remove.")
            raise typer.Exit()

        del servers["forge-kits"]
        self._write_settings(settings_path, data)
        typer.echo(f"  Removed forge-kits from {settings_path}")
        typer.echo("  Restart Claude Code for changes to take effect.")

    def _status(self, typer) -> None:
        project_path = Path.cwd() / ".claude" / "settings.json"
        global_path = Path.home() / ".claude" / "settings.json"

        typer.echo("\n  forge-kits MCP status:")
        typer.echo("")

        for label, path in [("project", project_path), ("global", global_path)]:
            data = self._read_settings(path)
            entry = data.get("mcpServers", {}).get("forge-kits")
            if entry:
                cmd = entry.get("command", "?")
                typer.echo(f"  [{label}]  registered")
                typer.echo(f"            config : {path}")
                typer.echo(f"            command: {cmd}")
            else:
                typer.echo(f"  [{label}]  not installed  ({path})")
            typer.echo("")

    # ------------------------------------------------------------------

    def _find_mcp_bin(self) -> str:
        python = Path(sys.executable)
        scripts_dir = python.parent  # <venv>/Scripts on Windows, <venv>/bin on Unix
        for name in ("forgeapi-mcp.exe", "forgeapi-mcp"):
            candidate = scripts_dir / name
            if candidate.exists():
                return str(candidate)
        return "forgeapi-mcp"

    @staticmethod
    def _read_settings(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text) if text.strip() else {}
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _write_settings(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
