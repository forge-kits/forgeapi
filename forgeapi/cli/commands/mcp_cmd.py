from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from forgeapi.cli.base import Command


class McpCommand(Command):
    name = "mcp:install"
    aliases = ("mcp:remove", "mcp:status", "mcp:debug")
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
        typer.echo("")
        typer.echo("Install scope:")
        typer.echo("  1. local    — this machine only (default)")
        typer.echo("  2. user     — all projects on this machine (--global)")
        typer.echo("  3. project  — .mcp.json committed to git (--project)")
        typer.echo("")
        choices = {
            "1": "local", "2": "user", "3": "project",
            "local": "local", "user": "user", "project": "project",
        }
        while True:
            raw = typer.prompt("Choose [1/2/3]", default="1")
            scope = choices.get(raw.strip().lower())
            if scope:
                return scope
            typer.echo("  Invalid choice. Enter 1, 2, or 3.", err=True)

    def _install(self, scope: str, typer) -> None:
        mcp_bin = self._find_mcp_bin(typer)
        self._run_claude(
            ["mcp", "add", "--scope", scope, "forge-kits", mcp_bin],
            typer,
        )

    def _status(self, typer) -> None:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            typer.echo("  Error: claude CLI not found in PATH.", err=True)
            raise typer.Exit(code=1)

        result = subprocess.run(
            [claude_bin, "mcp", "list"],
            text=True,
            capture_output=True,
        )
        lines = (result.stdout or "").splitlines()
        forge_lines = [l for l in lines if "forge-kits" in l]

        if forge_lines:
            for l in forge_lines:
                typer.echo(l)
        else:
            typer.echo("  forge-kits: not installed")
            typer.echo("  Run: forgeapi mcp:install")

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

        typer.echo(
            "  Warning: forgeapi-mcp not found in PATH or venv. "
            "Run: pip install forge-kits[mcp]",
            err=True,
        )
        return "forgeapi-mcp"

    @staticmethod
    def _run_claude(cmd_args: list[str], typer) -> None:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            typer.echo(
                "  Error: claude CLI not found in PATH. "
                "Install Claude Code: https://claude.ai/download",
                err=True,
            )
            raise typer.Exit(code=1)

        result = subprocess.run(
            [claude_bin] + cmd_args,
            text=True,
        )
        if result.returncode != 0:
            raise typer.Exit(code=result.returncode)
