"""Argument binding for project commands: the typed signature of ``Command.run``."""
from pathlib import Path

import pytest

from forgeapi.cli.arguments import ArgumentError, bind, help_text


def _bind(func, *args: str):
    return bind(func, list(args))


def test_positional_option_and_flag():
    def run(report_id: int, to: str = "me", dry_run: bool = False): ...

    assert _bind(run, "42") == ([42], {})
    assert _bind(run, "42", "--to", "bob", "--dry-run") == ([42], {"to": "bob", "dry_run": True})
    assert _bind(run, "--to=bob", "7") == ([7], {"to": "bob"})          # options may come first


def test_conversion_to_declared_types():
    def run(n: int, ratio: float = 1.0, path: Path | None = None): ...

    values, kwargs = _bind(run, "3", "--ratio", "0.5", "--path", "a/b")
    assert values == [3] and kwargs == {"ratio": 0.5, "path": Path("a/b")}


def test_negative_numbers_are_values_not_options():
    def run(delta: int, offset: int = 0): ...

    assert _bind(run, "-5", "--offset", "-2") == ([-5], {"offset": -2})


def test_double_dash_ends_options():
    def run(*names: str, flag: bool = False): ...

    assert _bind(run, "--flag", "--", "--weird", "x") == (["--weird", "x"], {"flag": True})


def test_variadic_and_repeatable_list_option():
    def run(first: str, *rest: int, tag: list[str] = ()): ...

    assert _bind(run, "a", "1", "2", "--tag", "x", "--tag", "y") == (["a", 1, 2], {"tag": ["x", "y"]})


def test_default_true_bool_has_a_negated_flag():
    def run(color: bool = True): ...

    assert _bind(run) == ([], {})
    assert _bind(run, "--no-color") == ([], {"color": False})
    assert _bind(run, "--color") == ([], {"color": True})


def test_keyword_only_without_default_is_a_required_option():
    def run(*, to: str): ...

    assert _bind(run, "--to", "bob") == ([], {"to": "bob"})
    with pytest.raises(ArgumentError, match="missing required option --to"):
        _bind(run)


@pytest.mark.parametrize("args, message", [
    ([], "missing argument <n>"),
    (["1", "2"], "unexpected argument '2'"),
    (["1", "--nope"], "unknown option --nope"),
    (["1", "-x"], "unknown option -x"),
    (["abc"], "<n>: 'abc' is not a valid int"),
    (["1", "--to"], "option --to needs a value"),
    (["1", "--to", "--dry-run"], "option --to needs a value"),
    (["1", "--dry-run=yes"], "option --dry-run takes no value"),
    (["1", "--limit", "x"], "--limit: 'x' is not a valid int"),
])
def test_errors(args, message):
    def run(n: int, to: str = "", dry_run: bool = False, limit: int = 0): ...

    with pytest.raises(ArgumentError, match=message):
        bind(run, args)


def test_kwargs_are_rejected():
    def run(**kwargs): ...

    with pytest.raises(TypeError):
        _bind(run)


def test_generated_help_lists_arguments_and_options():
    def run(report_id: int, *emails: str, to: str = "me", dry_run: bool = False):
        """Email the weekly report.

        Longer text that is not shown.
        """

    text = help_text(run, "send:report")
    assert text.startswith("Usage: forgeapi send:report <report_id> [<emails>...] [--to TO] [--dry-run]")
    assert "Email the weekly report." in text and "Longer text" not in text
    assert "<report_id>" in text and "--to TO" in text and "default: me" in text and "--dry-run" in text


# ── through the real CLI ──────────────────────────────────────────────────────

def _write_command(project: Path, body: str) -> None:
    folder = project / "app" / "commands"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").touch()
    (folder / "report_command.py").write_text(body)


def test_cli_passes_typed_arguments_to_async_run(cmd_project):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    _write_command(cmd_project, (
        "from __future__ import annotations\n"
        "from forgeapi.cli.base import Command\n\n"
        "class ReportCommand(Command):\n"
        "    name = 'send:report'\n"
        "    description = 'Email the report'\n\n"
        "    async def run(self, report_id: int, *emails: str, to: str = 'me', dry_run: bool = False) -> None:\n"
        "        print(f'id={report_id!r} emails={emails!r} to={to!r} dry={dry_run!r}')\n"
    ))
    runner = CliRunner()
    out = runner.invoke(app, ["send:report", "42", "a@x.com", "--to=bob", "--dry-run"])
    assert out.exit_code == 0, out.output
    assert "id=42 emails=('a@x.com',) to='bob' dry=True" in out.output

    listing = runner.invoke(app, [])
    assert "send:report" in listing.output and "Email the report" in listing.output


def test_cli_reports_bad_input_and_prints_generated_help(cmd_project):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    _write_command(cmd_project, (
        "from forgeapi.cli.base import Command\n\n"
        "class ReportCommand(Command):\n"
        "    name = 'send:report'\n\n"
        "    def run(self, report_id: int, to: str = 'me') -> None:\n"
        "        raise AssertionError('must not run on bad input')\n"
    ))
    runner = CliRunner()
    bad = runner.invoke(app, ["send:report", "abc"])
    assert bad.exit_code == 1
    assert "<report_id>: 'abc' is not a valid int" in bad.output and "forgeapi send:report -h" in bad.output

    missing = runner.invoke(app, ["send:report"])
    assert missing.exit_code == 1 and "missing argument <report_id>" in missing.output

    helped = runner.invoke(app, ["send:report", "-h"])
    assert helped.exit_code == 0
    assert "forgeapi send:report <report_id> [--to TO]" in helped.output


def test_raw_handle_commands_still_work(cmd_project):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    _write_command(cmd_project, (
        "from forgeapi.cli.base import Command\n\n"
        "class ReportCommand(Command):\n"
        "    name = 'raw'\n\n"
        "    def handle(self, cmd, args):\n"
        "        print('raw:', args)\n"
    ))
    out = CliRunner().invoke(app, ["raw", "--x", "1"])
    assert out.exit_code == 0 and "raw: ['--x', '1']" in out.output
