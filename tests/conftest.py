import pytest
from forgeapi.events.bus import EventBus
from forgeapi.pagination.paginator import Paginator
from tortoise import Tortoise


# Restrict anyio async tests to asyncio only (trio has incompatible version installed)
@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


# NOTE: Do NOT use @listen at module level in test files.
# Decorators applied at module level register against the singleton that exists
# at import time.  reset_event_bus() creates a NEW singleton, so those handlers
# would be invisible to post-reset dispatches.  Always register inside test
# bodies or fixtures.
@pytest.fixture(autouse=True)
def reset_event_bus():
    EventBus.reset()
    yield
    EventBus.reset()


# Both attributes are saved before yield so that a test calling configure()
# and then raising an exception still gets fully reset.
# Tests MUST use Paginator.configure() rather than mutating DEFAULT_LIMIT /
# MAX_LIMIT directly — configure() is the single mutation point and this
# fixture's cleanup depends on it.
@pytest.fixture(autouse=True)
def reset_paginator():
    default = Paginator.DEFAULT_LIMIT
    maximum = Paginator.MAX_LIMIT
    yield
    Paginator.DEFAULT_LIMIT = default
    Paginator.MAX_LIMIT = maximum
