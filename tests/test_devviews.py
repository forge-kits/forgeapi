import pytest

from forgeapi.cli.devviews import LOGS_VIEW, view_for, views_for


@pytest.mark.parametrize("process,logger,view", [
    ("server", None, "server"),                                  # uvicorn lines, no logger
    ("server", "forgeapi.access", "server"),                     # HTTP requests stay with the server
    ("server", "forgeapi.broadcasting.provider", LOGS_VIEW),
    ("server", "forgeapi.mail.provider", LOGS_VIEW),
    ("server", "app.orders", LOGS_VIEW),                         # your own Log.channel("orders")
    ("server", "uvicorn.error", "server"),
    ("queue", "forgeapi.queue", "queue"),                        # other processes are never split
    ("schedule", "app.report", "schedule"),
])
def test_view_for(process, logger, view):
    assert view_for(process, logger) == view


def test_views_for():
    assert views_for(["server", "queue", "schedule"]) == ["server", "queue", "schedule", "logs"]
    assert views_for(["queue"]) == ["queue"]
