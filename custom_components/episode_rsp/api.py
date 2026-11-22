"""Websocket client for the Episode Response (EA-RSP-xxD) amplifier.

The amp's web UI talks JSON over a websocket at ws://<host>/ws. After a
login message, a single "configure" message returns the whole state, and
changes are sent as "configure" / "put" messages that name one item. The
client must send a heartbeat_request every few seconds.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 5
LOGIN_OK_STATUSES = {200, 300}
# 200 success; 700-702 are mode notices (standby, voltage trigger, audio)
# the amp attaches to normal replies.
OK_STATUSES = {200, 300, 700, 701, 702}
AUTH_STATUSES = {400, 403, 406}


class RspError(Exception):
    """Base error."""


class RspConnectionError(RspError):
    """Could not talk to the amplifier."""


class RspAuthError(RspError):
    """Login was refused."""


class RspCommandError(RspError):
    """The amplifier returned a non-success status."""

    def __init__(self, type_: str, status: Any) -> None:
        super().__init__(f"{type_} failed with status {status}")
        self.status = status


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _at(seq: list, i: int) -> Any:
    return seq[i] if i < len(seq) else None


def parse_configures(cfg: dict[str, Any]) -> dict[str, Any]:
    """Turn the amp's "configures" object into a tidy structure."""
    # The firmware spells the section "amp_setttings" (three t's).
    amp = cfg.get("amp_setttings") or cfg.get("amp_settings") or {}

    def lst(key: str) -> list:
        value = amp.get(key)
        return value if isinstance(value, list) else []

    names = lst("output_name")
    volumes = lst("output_volume")
    count = max(len(names), len(volumes))
    maxv, mutes = lst("max_volume"), lst("output_mute")
    sources, presets = lst("output_source1"), lst("dsp_preset")

    zones = {
        i: {
            "name": _at(names, i) or None,
            "volume": _int(_at(volumes, i)),
            "max_volume": _int(_at(maxv, i)) or 100,
            "mute": _at(mutes, i) == "on",
            "source": _int(_at(sources, i)),
            "dsp_preset": _int(_at(presets, i)),
        }
        for i in range(count)
    }
    return {
        "device": cfg.get("deviceinfo", {}),
        "zones": zones,
        "inputs": {i: str(n or "") for i, n in enumerate(lst("input_name"))},
        "presets": [str(p) for p in lst("dsp_preset_item")],
    }


class EpisodeRspClient:
    """Persistent, auto-reconnecting websocket client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self._session = session
        self._url = f"ws://{host}:{port}/ws"
        self._username = username
        self._password = password
        self._timeout = timeout
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._tasks: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    def add_listener(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Callback gets the parsed state whenever the amp sends it."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    # ---------------------------------------------------------- connection

    async def async_close(self) -> None:
        async with self._lock:
            await self._close()

    async def _ensure_connected(self) -> None:
        if self.connected:
            return
        await self._close()
        try:
            self._ws = await asyncio.wait_for(
                self._session.ws_connect(self._url, heartbeat=None), self._timeout
            )
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as err:
            raise RspConnectionError(f"Cannot connect to {self._url}: {err}") from err

        ws = self._ws
        self._tasks = [
            asyncio.create_task(self._read_loop(ws)),
            asyncio.create_task(self._heartbeat_loop(ws)),
        ]
        login = {
            "type": "login",
            "username": self._username,
            "password": self._password,
        }
        try:
            msg = await self._exchange(login)
        except RspError:
            await self._close()
            raise
        status = msg.get("status")
        # The amp's own login page accepts both 200 and 300 ("repeat
        # operation", i.e. already logged in) as success.
        if status not in LOGIN_OK_STATUSES:
            await self._close()
            if status in AUTH_STATUSES:
                raise RspAuthError(f"Login refused (status {status})")
            raise RspCommandError("login", status)

    async def _close(self) -> None:
        tasks, self._tasks = self._tasks, []
        ws, self._ws = self._ws, None
        for task in tasks:
            if task is not asyncio.current_task():
                task.cancel()
        if ws is not None and not ws.closed:
            try:
                await ws.close()
            except (aiohttp.ClientError, OSError):
                pass
        self._fail_pending()

    def _fail_pending(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RspConnectionError("Connection closed"))
        self._pending.clear()

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            while not ws.closed:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await ws.send_str(json.dumps({"type": "heartbeat_request"}))
        except (aiohttp.ClientError, OSError, ConnectionError):
            if self._ws is ws:
                self._ws = None
            self._fail_pending()

    async def _read_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            async for raw in ws:
                if raw.type != aiohttp.WSMsgType.TEXT:
                    if raw.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
                    continue
                text = raw.data.strip("\x00 \r\n")
                try:
                    msg = json.loads(text)
                except ValueError:
                    _LOGGER.debug("Ignoring non-JSON frame: %s", text[:200])
                    continue
                if isinstance(msg, dict):
                    self._dispatch(msg)
        except (aiohttp.ClientError, OSError):
            pass
        finally:
            if self._ws is ws:
                self._ws = None
            self._fail_pending()

    def _dispatch(self, msg: dict[str, Any]) -> None:
        type_ = msg.get("type")
        fut = self._pending.get(type_) if isinstance(type_, str) else None
        if fut and not fut.done():
            fut.set_result(msg)
        cfg = msg.get("configures")
        if type_ == "configure" and isinstance(cfg, dict):
            state = parse_configures(cfg)
            for cb in list(self._listeners):
                try:
                    cb(state)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Listener failed")

    async def _exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None:
            raise RspConnectionError("Not connected")
        type_ = payload["type"]
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[type_] = fut
        try:
            await self._ws.send_str(json.dumps(payload))
            return await asyncio.wait_for(fut, self._timeout)
        except asyncio.TimeoutError as err:
            await self._close()
            raise RspConnectionError(f"Timed out waiting for {type_}") from err
        except (aiohttp.ClientError, OSError) as err:
            await self._close()
            raise RspConnectionError(str(err)) from err
        finally:
            self._pending.pop(type_, None)

    # ------------------------------------------------------------ commands

    async def _configure(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            await self._ensure_connected()
            msg = await self._exchange(payload)
        status = msg.get("status")
        if status not in OK_STATUSES:
            raise RspCommandError("configure", status)
        return msg

    async def async_get_state(self) -> dict[str, Any]:
        msg = await self._configure(
            {"type": "configure", "direction": "get", "section": "all"}
        )
        cfg = msg.get("configures")
        if not isinstance(cfg, dict):
            raise RspError("Amplifier reply had no configuration data")
        return parse_configures(cfg)

    async def async_put(self, item: str, index: int, value: Any) -> None:
        """Change one item, e.g. async_put("output_volume", 2, 51).

        The amp replies with its full state, which reaches listeners.
        """
        await self._configure(
            {
                "type": "configure",
                "direction": "put",
                "section": "all",
                "changed_item": [item],
                "items": {item: {"index": str(index), "value": str(value)}},
            }
        )
