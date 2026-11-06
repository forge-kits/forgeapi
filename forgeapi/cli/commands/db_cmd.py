from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from forgeapi.cli import ui
from forgeapi.cli.base import Command


_DB_SUBCOMMANDS = ("init", "makemigrations", "migrate", "downgrade", "history", "heads", "sqlmigrate")


class DbCommand(Command):
    name = "db"
    is_group = True
    help_text = """\
Usage: forgeapi db:<subcommand>

Migration and seed commands.

  db:init              Init tortoise migration config
  db:makemigrations    Generate migration from model changes
  db:migrate           Apply pending migrations
    --force            DROP every table + the migration history, then migrate from scratch
    --yes, -y          Skip the confirmation prompt (with --force)
  db:downgrade <app> <migration>   Roll back to a specific migration (use db:history to list names)
    --fake             Record rollback without executing SQL
    --dry-run          Show SQL without applying changes
  db:history           Show migration history
  db:seed              Run all seeders
  db:seed <Name>       Run specific seeder(s) by name
  db:fresh             TRUNCATE all tables (asks for confirmation)
  db:fresh --force     DROP all tables including structure (irreversible)

Options for db:makemigrations:
  -n <name>   Migration name

Examples:
  forgeapi db:init
  forgeapi db:makemigrations -n add_email
  forgeapi db:migrate
  forgeapi db:migrate --force
  forgeapi db:downgrade models 0001_init
  forgeapi db:downgrade models 0001_init --dry-run
  forgeapi db:seed
  forgeapi db:seed User Post
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        from forgeapi.config import load_config

        if ":" not in cmd:
            self.show_help(cmd)
            return

        subcmd = cmd.split(":", 1)[1]

        if subcmd == "seed":
            from .seed_cmd import SeedCommand
            names = [a for a in args if not a.startswith("-")]
            SeedCommand().handle("db:seed", names)
            return

        if subcmd == "fresh":
            from .fresh_cmd import FreshCommand
            FreshCommand().handle("db:fresh", args)
            return

        if subcmd not in _DB_SUBCOMMANDS:
            self.abort(
                f"unknown db command 'db:{subcmd}'.\n"
                f"  Available: {', '.join(f'db:{s}' for s in _DB_SUBCOMMANDS)}"
            )

        cfg = load_config()
        orm_path = cfg.database.tortoise_orm

        tortoise_bin = self._find_tortoise_bin()
        if tortoise_bin is None:
            self.abort("tortoise binary not found. Install tortoise-orm.")

        if subcmd == "migrate" and "--force" in args:
            if "--dry-run" in args or "--fake" in args:
                self.abort("--force cannot be combined with --dry-run or --fake: it really drops the tables.")
            from .fresh_cmd import FreshCommand

            FreshCommand().drop_everything(assume_yes="--yes" in args or "-y" in args)
            args = [a for a in args if a not in ("--force", "--yes", "-y")]
            ui.info("Running migrations.")

        command = [tortoise_bin, "-c", orm_path, subcmd] + args
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        try:
            result = subprocess.run(command, env=env)
        except OSError as exc:
            self.abort(f"failed to run tortoise binary: {exc}")
        sys.exit(result.returncode)

    @staticmethod
    def _find_tortoise_bin() -> str | None:
        candidates = ["tortoise", "tortoise.exe"]
        scripts_dir = Path(sys.executable).parent
        for name in candidates:
            path = scripts_dir / name
            if path.exists():
                return str(path)
        return shutil.which("tortoise")
