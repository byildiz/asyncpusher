import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from enum import Enum
from random import random
from typing import Any

import aiohttp

MAX_WAIT_SECONDS = 120


class Connection:
    """
    Implements pusher protocol 7 described in https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/
    """

    class State(Enum):
        IDLE = 1
        CONNECTED = 2
        FAILED = 3
        CLOSED = 4

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        url: str,
        callback: Callable[[str, Any, str], Awaitable[None]],
        log: logging.Logger,
        **kwargs,
    ):
        self._loop = loop
        self._url = url
        self._callback = callback
        self._log = log
        self._websocket_params = kwargs

        self._event_callbacks = defaultdict(dict)

        self._connection_attempts = 0
        # stop signal to break infinite loop in _run_forever
        self._stop = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self.socket_id = None
        # https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/#recommendations-for-client-libraries
        self._activity_timeout = 120
        self._pong_timeout = 30
        self.state = self.State.IDLE

        self.bind("pusher:connection_established", self._handle_connection)
        self.bind("pusher:connection_failed", self._handle_failure)
        self.bind("pusher:error", self._handle_error)

    async def open(self):
        self._loop.create_task(self._run_forever())

        while self.state != self.State.CONNECTED:
            await asyncio.sleep(1)

    async def close(self):
        self._stop = True
        if self.state == self.State.CONNECTED:
            if self._ws is not None:
                await self._ws.close()

    async def _run_forever(self):
        async with aiohttp.ClientSession() as session:
            while not self._stop:
                try:
                    await self._connect(session)
                except aiohttp.ClientError:
                    self._log.exception("Exception while connecting to web socket")
                    self._connection_attempts += 1
        self._log.info("End of forever")

    async def _connect(self, session: aiohttp.ClientSession):
        self._log.info("Pusher connecting...")

        wait_seconds = self._get_wait_time(self._connection_attempts)
        self._log.info(f"Waiting for {wait_seconds}s, # attempts: {self._connection_attempts}")
        await asyncio.sleep(wait_seconds)

        async with session.ws_connect(self._url, heartbeat=self._activity_timeout, **self._websocket_params) as ws:
            # internally aiohttp.ClientWebSocketResponse uses heartbeat/2 as pong timeout but pusher protocol advise 30s
            ws._pong_heartbeat = self._pong_timeout
            self._ws = ws
            await self._dispatch(ws)

    async def _dispatch(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            msg = await ws.receive()
            self._log.debug(f"Websocket message: {msg}")
            if msg.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(msg.data)
                await self._handle_event(event)
            else:
                self.state = self.State.CLOSED
                self._log.info(f"Exiting dispatch with message: {msg}")
                if msg.type == aiohttp.WSMsgType.CLOSE:
                    if isinstance(msg.data, int):
                        code = msg.data
                        # 4000-4099: The connection SHOULD NOT be re-established unchanged.
                        if code >= 4000 and code < 4100:
                            self._stop = True
                        # 4100-4199: The connection SHOULD be re-established after backing off.
                        # The back-off time SHOULD be at least 1 second in duration and MAY be
                        # exponential in nature on consecutive failures.
                        elif code >= 4100 and code < 4200:
                            self._connection_attempts += 1
                        # 4200-4299: The connection SHOULD be re-established immediately.
                        elif code >= 4200 and code < 4300:
                            self._connection_attempts = 0
                    else:
                        # Unknown closing, it sometimes happens. Try to reconnect anyway
                        self._connection_attempts = 0
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self._log.error(f"Error received {ws.exception()}")
                    self._connection_attempts = 0
                break

    async def _handle_event(self, event):
        if "event" not in event:
            self._log.warning(f"Unexpected event: {event}")
            return

        event_name = event["event"]
        event_data = event.get("data")
        try:
            event_data = json.loads(event_data)
        except TypeError:
            pass

        if "channel" in event:
            await self._callback(event["channel"], event_name, event_data)
            return

        if event_name in self._event_callbacks:
            for callback, (args, kwargs) in self._event_callbacks[event_name].items():
                try:
                    await callback(event_data, *args, **kwargs)
                except Exception:
                    self._log.exception(f"Exception in callback: {event_data}")
            return

        self._log.warning(f"Unhandled event: {event}")

    async def send_event(self, event):
        retry_count = 5
        while retry_count > 0 and self.state != self.State.CONNECTED:
            await asyncio.sleep(1)
            retry_count -= 1
        if self.state == self.State.CONNECTED:
            if self._ws is not None:
                await self._ws.send_json(event)

    async def _handle_connection(self, data):
        self.socket_id = data["socket_id"]
        self._activity_timeout = data["activity_timeout"]
        # force to update heartbeat
        if self._ws is not None:
            self._ws._heartbeat = self._activity_timeout
        self.state = self.State.CONNECTED
        self._log.info(f"Connection established: {data}")

    async def _handle_failure(self, data):
        self.state = self.State.FAILED
        self._log.error(f"Connection failed: {data}")

    async def _handle_error(self, data):
        self._log.error(f"Pusher error: {data}")

    def bind(self, event_name, callback, *args, **kwargs):
        self._event_callbacks[event_name][callback] = (args, kwargs)

    def unbind(self, event_name, callback):
        del self._event_callbacks[event_name][callback]

    def is_connected(self):
        return self.state == self.State.CONNECTED

    @staticmethod
    def _get_wait_time(num_attempts):
        if num_attempts <= 0:
            return 0
        # wait time should at least 1 seconds
        seconds = round(random() * (2 ** (num_attempts) - 1)) + 1
        return min(seconds, MAX_WAIT_SECONDS)
