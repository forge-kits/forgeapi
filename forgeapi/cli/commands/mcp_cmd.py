from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from rich.text import Text

from forgeapi.cli import ui
from forgeapi.cli.base import Command


class McpCommand(Command):
    name = "mcp:install"
    requires_project = False
    is_group = True
    aliases = ("mcp", "mcp:remove", "mcp:status", "mcp:debug")
    help_text = """\
Usage:
  forgeapi mcp:install [--global] [--project]
  forgeapi mcp:remove  [--global] [--project]
  forgeapi mcp:status

Registers (or removes) the forge-kits MCP server via `claude mcp add/remove`.

Scopes:
  --global    user scope   — available in all projects  (claude mcp add --scope user)
  --project   project scope — .mcp.json in project root (claude mcp add --scope project)
  default     local scope  — current machine only       (claude mcp add --scope local)

Examples:
  forgeapi mcp:install             # local scope (prompts)
  forgeapi mcp:install --global    # all projects
  forgeapi mcp:install --project   # project .mcp.json (commit to git)
  forgeapi mcp:remove --global     # remove from user scope
  forgeapi mcp:status              # show registered MCP servers
  forgeapi mcp:debug               # dump full MCP context (instructions + tools + cheatsheet)
  forgeapi mcp:debug --tools       # tools only
  forgeapi mcp:debug --cheatsheet  # cheatsheet only
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        import typer

        if cmd == "mcp":
            self.show_help(cmd)
            return

        is_global = "--global" in args or "-g" in args
        is_project = "--project" in args or "-p" in args

        if cmd == "mcp:status":
            self._status(typer)
            return

        if cmd == "mcp:debug":
            self._debug(args, typer)
            return

        scope = self._resolve_scope(is_global, is_project, typer)

        if cmd == "mcp:remove":
            self._remove(scope, typer)
        else:
            self._install(scope, typer)

    # ------------------------------------------------------------------

    def _resolve_scope(self, is_global: bool, is_project: bool, typer) -> str:
        if is_global:
            return "user"
        if is_project:
            return "project"
        ui.blank()
        return ui.choose("Install scope", [
            ("local", "local", "this machine only (default)"),
            ("user", "user", "all projects on this machine (--global)"),
            ("project", "project", ".mcp.json committed to git (--project)"),
        ])

    def _install(self, scope: str, typer) -> None:
        mcp_bin = self._find_mcp_bin(typer)
        self._run_claude(
            ["mcp", "add", "--scope", scope, "forge-kits", mcp_bin],
            typer,
        )
        ui.success(f"forge-kits MCP server installed (scope: {scope}).")

    def _status(self, typer) -> None:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            ui.error("claude CLI not found in PATH.")
            raise typer.Exit(code=1)

        result = subprocess.run(
            [claude_bin, "mcp", "list"],
            text=True,
            capture_output=True,
        )
        lines = (result.stdout or "").splitlines()
        forge_lines = [l for l in lines if "forge-kits" in l]

        if forge_lines:
            ui.blank()
            for l in forge_lines:
                self._print_status(l)
            ui.blank()
        else:
            ui.warn("forge-kits is not installed.")
            ui.console.print(Text("  Run: forgeapi mcp:install", style="dim"))

    @staticmethod
    def _print_status(line: str) -> None:
        """``forge-kits: /path/forgeapi-mcp  - ✔ Connected`` -> dotted line + dimmed path."""
        match = re.match(r"^(?P<name>[^:]+):\s*(?P<target>.*?)\s+-\s+(?P<status>.*)$", line.strip())
        if not match:
            ui.console.print(Text("  " + line.strip()), soft_wrap=True)
            return
        status = match["status"].lstrip("✔✓✗✘!⚠ ").strip() or match["status"]
        lowered = status.lower()
        kind = "done" if lowered.startswith("connected") else "error" if "fail" in lowered else "warn"
        ui.leader(match["name"], status.upper(), kind=kind)
        ui.indented(match["target"], wrap=False)

    @staticmethod
    def _debug(args: list[str], typer) -> None:
        from forgeapi.mcp.docs import get_docs, _DOCS
        from forgeapi.mcp.generators import generate_controller, generate_schema
        from forgeapi.mcp.scanner import scan_project, project_info
        from forgeapi.mcp.examples import get_example
        from forgeapi.mcp.server import mcp

        only_tools = "--tools" in args
        only_cheatsheet = "--cheatsheet" in args

        sep = "─" * 60
        tools = [get_docs, get_example, generate_controller, generate_schema, scan_project, project_info]

        if not only_cheatsheet:
            typer.echo(sep)
            typer.echo("INSTRUCTIONS (sent to Claude on connect)")
            typer.echo(sep)
            typer.echo(mcp.instructions)

            typer.echo(sep)
            typer.echo(f"TOOLS ({len(tools)} registered)")
            typer.echo(sep)
            for fn in tools:
                doc_first = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
                typer.echo(f"  {fn.__name__:<24} {doc_first}")
            typer.echo("")
            typer.echo(f"  Available get_docs topics: {', '.join(_DOCS.keys())}")

        if only_tools:
            return

        typer.echo(sep)
        typer.echo("CHEATSHEET (get_docs('cheatsheet'))")
        typer.echo(sep)
        typer.echo(get_docs("cheatsheet"))

    def _remove(self, scope: str, typer) -> None:
        self._run_claude(
            ["mcp", "remove", "--scope", scope, "forge-kits"],
            typer,
        )
        ui.success(f"forge-kits MCP server removed (scope: {scope}).")

    # ------------------------------------------------------------------

    def _find_mcp_bin(self, typer) -> str:
        found = shutil.which("forgeapi-mcp")
        if found:
            return found

        scripts_dir = Path(sys.executable).parent
        for name in ("forgeapi-mcp.exe", "forgeapi-mcp"):
            candidate = scripts_dir / name
            if candidate.exists():
                return str(candidate)

        ui.warn(
            "forgeapi-mcp not found in PATH or venv. Run: pip install forge-kits[mcp]",
            stderr=True,
        )
        return "forgeapi-mcp"

    @staticmethod
    def _run_claude(cmd_args: list[str], typer) -> None:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            ui.error(
                "claude CLI not found in PATH.",
                hint="Install Claude Code: https://claude.ai/download",
            )
            raise typer.Exit(code=1)

        result = subprocess.run(
            [claude_bin] + cmd_args,
            text=True,
        )
        if result.returncode != 0:
            raise typer.Exit(code=result.returncode)
