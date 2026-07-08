import pytest
from forgeapi.events.bus import EventBus
from forgeapi.pagination.paginator import Paginator
from tortoise import Tortoise


# Restrict anyio async tests to asyncio only (trio has incompatible version installed)
@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


@pytest.fixture(autouse=True)
def reset_event_bus():
    EventBus.reset()
    yield
    EventBus.reset()


@pytest.fixture(autouse=True)
def reset_paginator():
    default = Paginator.DEFAULT_LIMIT
    maximum = Paginator.MAX_LIMIT
    yield
    Paginator.DEFAULT_LIMIT = default
    Paginator.MAX_LIMIT = maximum



