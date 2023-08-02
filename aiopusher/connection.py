import logging
import asyncio
import json
import aiohttp
from random import random
from collections import defaultdict
from collections.abc import Callable, Awaitable
from typing import Any
from enum import Enum


class Connection:
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

        self._num_reconnect = 0
        # stop signal to break infinite loop in _run_forever
        self._stop = False
        self._ws: aiohttp.ClientWebSocketResponse = None
        self.socket_id = None
        # https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/#recommendations-for-client-libraries
        self._activity_timeout = 120
        self._pong_timeout = 30
        self.state = self.State.IDLE

        self.bind("pusher:connection_established", self._handle_connection)
        self.bind("pusher:connection_failed", self._handle_failure)
        self.bind("pusher:pong", self._handle_pong)
        self.bind("pusher:ping", self._handle_ping)
        self.bind("pusher:error", self._handle_error)

    async def open(self):
        self._loop.create_task(self._run_forever())

        while self.state != self.State.CONNECTED:
            await asyncio.sleep(1)

    async def close(self):
        self._stop = True
        if self.state == self.State.CONNECTED:
            await self._ws.close()

    async def _run_forever(self):
        async with aiohttp.ClientSession() as session:
            while not self._stop:
                await self._connect(session)
        self._log.info("End of forever")

    async def _connect(self, session: aiohttp.ClientSession):
        self._log.info("Pusher connecting...")

        self._num_reconnect += 1
        wait_seconds = self._get_reconnect_wait(self._num_reconnect)
        self._log.info(f"Waiting for {wait_seconds}s")
        await asyncio.sleep(wait_seconds)
        self._log.info("End of wait")

        async with session.ws_connect(
            self._url, heartbeat=self._activity_timeout, **self._websocket_params
        ) as ws:
            # internally ws uses heartbeat/2 as pong timeout but pusher protocol advise 30s
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
                if msg.type == aiohttp.WSMsgType.CLOSE:
                    await ws.close()
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self._log.error(f"Error received {ws.exception()}")
                self._state = self.State.CLOSED
                self._log.info(f"Exiting dispatch with message: {msg}")
                break

    async def _handle_event(self, event):
        if "event" not in event:
            self._log.warning(f"Unexpected event: {event}")
            return

        event_name = event["event"]
        event_data = json.loads(event.get("data", "{}"))

        if "channel" in event:
            await self._callback(event["channel"], event_name, event_data)
            return

        if event_name in self._event_callbacks:
            for callback, (args, kwargs) in self._event_callbacks[event_name].items():
                try:
                    await callback(event_data, *args, **kwargs)
                except:
                    self._log.exception(f"Exception in callback: {event_data}")
            return

        self._log.warning(f"Unhandled event: {event}")

    async def _send_pong(self):
        await self.send_event({"event": "pusher:pong", "data": ""})

    async def send_event(self, event):
        retry_count = 5
        while retry_count > 0 and self.state != self.State.CONNECTED:
            await asyncio.sleep(1)
            retry_count -= 1
        await self._ws.send_json(event)

    async def _handle_connection(self, data):
        self.socket_id = data["socket_id"]
        self._activity_timeout = data["activity_timeout"]
        # force to update heartbeat
        self._ws._heartbeat = self._activity_timeout
        self.state = self.State.CONNECTED
        self._log.info(f"Connection established: {data}")

    async def _handle_failure(self, data):
        self.state = self.State.FAILED
        self._log.error(f"Connection failed: {data}")

    async def _handle_pong(self, data):
        # TODO: reset inactivity timer
        self._log.info(f"Pong received: {data}")

    async def _handle_ping(self, data):
        await self._send_pong()
        self._log.info(f"Ping received: {data}")

    async def _handle_error(self, data):
        self.state = self.State.CLOSED
        self._log.error(f"Connection error: {data}")

    def bind(self, event_name, callback, *args, **kwargs):
        self._event_callbacks[event_name][callback] = (args, kwargs)

    def unbind(self, event_name, callback):
        del self._event_callbacks[event_name][callback]

    def is_connected(self):
        return self.state == self.State.CONNECTED

    def _get_reconnect_wait(self, attempts):
        return round(random() * min(self._activity_timeout, 2 ** (attempts - 1) - 1))
