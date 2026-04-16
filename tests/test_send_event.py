import asyncio
import logging
import unittest
from unittest.mock import patch

from asyncpusher.connection import Connection


async def _noop_callback(channel, event, data):
    pass


def _make_connection():
    loop = asyncio.get_event_loop()
    log = logging.getLogger("asyncpusher.test")
    return Connection(loop, "ws://127.0.0.1:1/fake", _noop_callback, log)


class FakeWebSocket:
    def __init__(self, *, closed: bool = False):
        self.closed = closed
        self.sent: list = []

    async def send_json(self, event):
        self.sent.append(event)


async def _noop_sleep(_delay):
    # Avoid waiting through the retry loop during tests
    return


class SendEventTest(unittest.IsolatedAsyncioTestCase):
    """
    send_event used to silently drop events when the connection was not ready
    or the websocket was closed. It now raises ConnectionError so callers
    (e.g. auto-resubscribe after reconnect) can detect and log failures.
    """

    async def test_sends_when_connected(self):
        conn = _make_connection()
        ws = FakeWebSocket()
        conn._ws = ws
        conn.state = Connection.State.CONNECTED

        payload = {"event": "pusher:subscribe", "data": {"channel": "foo"}}
        await conn.send_event(payload)

        self.assertEqual(ws.sent, [payload])

    async def test_raises_when_state_never_reaches_connected(self):
        conn = _make_connection()
        conn.state = Connection.State.FAILED

        with patch("asyncpusher.connection.asyncio.sleep", new=_noop_sleep):
            with self.assertRaises(ConnectionError):
                await conn.send_event({"event": "test"})

    async def test_raises_when_websocket_is_none(self):
        conn = _make_connection()
        conn.state = Connection.State.CONNECTED
        conn._ws = None

        with self.assertRaises(ConnectionError):
            await conn.send_event({"event": "test"})

    async def test_raises_when_websocket_closed(self):
        conn = _make_connection()
        conn._ws = FakeWebSocket(closed=True)
        conn.state = Connection.State.CONNECTED

        with self.assertRaises(ConnectionError):
            await conn.send_event({"event": "test"})


if __name__ == "__main__":
    unittest.main()
