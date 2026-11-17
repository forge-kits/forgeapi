"""Which view (tab) a line of ``runserver --dev`` output belongs to."""
from __future__ import annotations

#: View that collects the forgeapi / app logger lines of the server process (broadcast, auth, mail, ...).
LOGS_VIEW = "logs"


def view_for(process: str, logger: str | None) -> str:
    """The view of one line.  Only the server process is split: HTTP requests stay in ``server``, what the
    application and forgeapi log (broadcast, auth, cache, mail, your own ``Log``) goes to ``logs``."""
    if process == "server" and logger and (logger.startswith(("forgeapi.", "app.")) and logger != "forgeapi.access"
                                            and not logger.startswith("forgeapi.access.")):
        return LOGS_VIEW
    return process


def views_for(processes: list[str]) -> list[str]:
    """Names of all views for these processes, in display order."""
    return [*processes, LOGS_VIEW] if "server" in processes else list(processes)
