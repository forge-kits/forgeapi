import asyncio
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable

from forgeapi.logging import log
from .base import BroadcastDriver

_log = log.channel("broadcasting.redis")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class RedisDriver(BroadcastDriver):
    """Redis transport driver.

    Supports two modes passed at construction time:
    - ``mode="pubsub"``  — fire-and-forget via Redis Pub/Sub
    - ``mode="stream"``  — persistent via Redis Streams (XADD / XREADGROUP)

    Stream mode requires ``group`` and ``consumer``.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        namespace: str = "forge",
        mode: str = "pubsub",
        group: str | None = None,
        consumer: str | None = None,
        maxlen: int | None = None,
    ) -> None:
        if mode == "stream" and (not group or not consumer):
            raise ValueError("Redis stream mode requires group and consumer")
        self._url = url
        self._namespace = namespace
        self._mode = mode
        self._group = group
        self._consumer = consumer
        self._maxlen = maxlen
        self._handlers: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}
        self._redis: Any = None
        self._bg_tasks: set[asyncio.Task] = set()

    @property
    def has_listeners(self) -> bool:
        return bool(self._handlers)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, channel: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        handlers = self._handlers.setdefault(channel, [])
        fqn = f"{handler.__module__}.{handler.__qualname__}"
        if any(f"{h.__module__}.{h.__qualname__}" == fqn for h in handlers):
            handlers[:] = [h for h in handlers if f"{h.__module__}.{h.__qualname__}" != fqn]
        handlers.append(handler)
        _log.debug("broadcast.on('%s') → %s.%s", channel, handler.__module__, handler.__qualname__)

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if self._redis is not None:
            return
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError("RedisDriver requires redis. Install: pip install forge-kits[redis]")
        self._redis = aioredis.from_url(
            self._url,
            decode_responses=True,
            health_check_interval=15,
            socket_keepalive=True,
            retry_on_timeout=True,
            socket_connect_timeout=10,
        )
        _log.info("connected  url=%s  namespace=%s  mode=%s", self._url, self._namespace, self._mode)

    async def disconnect(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            _log.info("disconnected  namespace=%s", self._namespace)

    # ── Emit ──────────────────────────────────────────────────────────────────

    async def emit(self, channel: str, payload: dict) -> None:
        if self._redis is None:
            raise RuntimeError("RedisDriver is not connected.")
        key = f"{self._namespace}:{channel}"
        if self._mode == "stream":
            fields = {k: json.dumps(v, default=_json_default) for k, v in payload.items()}
            await self._redis.xadd(key, fields, maxlen=self._maxlen, approximate=True)
            _log.debug("emit  stream=%s  data=%s", key, payload)
        else:
            await self._redis.publish(key, json.dumps(payload, default=_json_default))
            _log.debug("emit  pubsub=%s  data=%s", key, payload)

    # ── Listen ────────────────────────────────────────────────────────────────

    async def listen(self) -> None:
        if self._mode == "stream":
            await self._listen_stream()
        else:
            await self._listen_pubsub()

    async def _listen_pubsub(self) -> None:
        if self._redis is None:
            raise RuntimeError("RedisDriver is not connected.")
        pattern = f"{self._namespace}:*"
        reconnect_delay = 1.0
        while True:
            pubsub = self._redis.pubsub()
            ping_task: asyncio.Task | None = None
            try:
                await pubsub.psubscribe(pattern)
                _log.info("pubsub listening  pattern=%s", pattern)
                reconnect_delay = 1.0
                ping_task = asyncio.create_task(
                    self._keepalive_ping(pubsub), name="broadcast:pubsub:ping"
                )
                while True:
                    if ping_task.done():
                        raise ConnectionError("pubsub keepalive ping failed — reconnecting")
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg is not None and msg.get("type") == "pmessage":
                        await self._dispatch_pubsub(msg)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.warning("pubsub error (%s), reconnecting in %.0fs…", exc, reconnect_delay)
            finally:
                if ping_task is not None:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except (asyncio.CancelledError, Exception):
                        pass
                try:
                    await pubsub.punsubscribe(pattern)
                    await pubsub.aclose()
                except Exception:
                    pass
            try:
                await asyncio.sleep(reconnect_delay)
            except asyncio.CancelledError:
                break
            reconnect_delay = min(reconnect_delay * 2, 60.0)
        _log.info("pubsub stopped")

    async def _keepalive_ping(self, pubsub: Any, interval: float = 30.0) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await pubsub.ping()
                _log.debug("pubsub keepalive ping sent")
            except Exception as exc:
                _log.warning("pubsub keepalive ping failed: %s", exc)
                break

    async def _listen_stream(self) -> None:
        if self._redis is None:
            raise RuntimeError("RedisDriver is not connected.")

        stream_keys = [f"{self._namespace}:{ch}" for ch in self._handlers]
        if not stream_keys:
            raise RuntimeError(
                "No channels registered via @broadcast.on(). "
                "Import your listeners before calling connect()."
            )

        streams = {key: ">" for key in stream_keys}

        async def _ensure_groups() -> None:
            for key in stream_keys:
                try:
                    await self._redis.xgroup_create(key, self._group, id="0", mkstream=True)
                    _log.debug("group '%s' created on '%s'", self._group, key)
                except Exception as exc:
                    if "BUSYGROUP" not in str(exc):
                        _log.error("xgroup_create failed for '%s': %s", key, exc)

        await _ensure_groups()
        _log.info(
            "stream listening  group=%s  consumer=%s  keys=%s",
            self._group, self._consumer, stream_keys,
        )

        try:
            while True:
                try:
                    results = await self._redis.xreadgroup(
                        groupname=self._group,
                        consumername=self._consumer,
                        streams=streams,
                        count=10,
                        block=2000,
                    )
                    for stream_name, messages in (results or []):
                        key = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                        channel = key.removeprefix(f"{self._namespace}:")
                        for msg_id, raw_fields in messages:
                            await self._dispatch_stream(channel, key, msg_id, raw_fields)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if "NOGROUP" in str(exc):
                        _log.warning("stream key deleted, recreating groups…")
                        await _ensure_groups()
                    else:
                        _log.error("stream error, retrying in 1s: %s", exc)
                        await asyncio.sleep(1)
        except asyncio.CancelledError:
            _log.info("stream stopped  group=%s  consumer=%s", self._group, self._consumer)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def _dispatch_pubsub(self, message: dict) -> None:
        raw_channel = message["channel"]
        if isinstance(raw_channel, bytes):
            raw_channel = raw_channel.decode()
        channel = raw_channel.removeprefix(f"{self._namespace}:")
        handlers = self._handlers.get(channel)
        if not handlers:
            _log.debug("pubsub message on '%s' — no handlers, skipping", channel)
            return
        try:
            data = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            _log.error("failed to parse pubsub message  channel=%s", channel)
            return
        _log.debug("pubsub received  channel=%s  data=%s", channel, data)
        for handler in handlers:
            t = asyncio.create_task(self._safe_call(handler, data), name=f"broadcast:{channel}")
            self._bg_tasks.add(t)
            t.add_done_callback(self._bg_tasks.discard)

    async def _dispatch_stream(self, channel: str, stream_key: str, msg_id: Any, raw_fields: dict) -> None:
        data: dict[str, Any] = {}
        for k, v in raw_fields.items():
            k = k.decode() if isinstance(k, bytes) else k
            v = v.decode() if isinstance(v, bytes) else v
            try:
                data[k] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                data[k] = v
        handlers = self._handlers.get(channel)
        if handlers:
            _log.debug("stream received  channel=%s  msg_id=%s  data=%s", channel, msg_id, data)
            for handler in handlers:
                t = asyncio.create_task(self._safe_call(handler, data), name=f"broadcast:{channel}")
                self._bg_tasks.add(t)
                t.add_done_callback(self._bg_tasks.discard)
        else:
            _log.debug("stream message on '%s' — no handlers, skipping", channel)
        await self._redis.xack(stream_key, self._group, msg_id)

    async def _safe_call(self, handler: Callable, data: dict) -> None:
        try:
            await handler(data)
        except Exception as exc:
            _log.error("handler '%s' raised: %s", handler.__qualname__, exc, exc_info=exc)

    async def wait_bg_tasks(self) -> None:
        if self._bg_tasks:
            await asyncio.gather(*list(self._bg_tasks), return_exceptions=True)
