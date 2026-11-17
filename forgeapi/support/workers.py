"""Switch for the in-app queue worker and scheduler.

``forgeapi runserver --dev`` runs them as separate processes and sets this variable for the
web process, so the same jobs are not executed twice.  Set it yourself when you run
``forgeapi queue:work`` / ``forgeapi schedule:work`` as their own processes (for example in production).
"""
from __future__ import annotations

import os

EXTERNAL_WORKERS_ENV = "FORGEAPI_EXTERNAL_WORKERS"


def workers_run_externally() -> bool:
    """``True`` when the queue worker and scheduler run outside the web process."""
    return os.environ.get(EXTERNAL_WORKERS_ENV, "").strip().lower() in ("1", "true", "yes")
