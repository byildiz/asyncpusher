import asyncio
import logging
import unittest

from asyncpusher.connection import Connection


async def _noop_callback(channel, event, data):
    pass


def _make_connection():
    loop = asyncio.get_event_loop()
    log = logging.getLogger("asyncpusher.test")
    return Connection(loop, "ws://127.0.0.1:1/fake", _noop_callback, log)


class ConnectionOpenTest(unittest.IsolatedAsyncioTestCase):
    """
    Regression tests for the `open()` hang bug: if _run_forever ever exits
    without the server sending pusher:connection_established, open() used to
    poll state == CONNECTED forever. It now waits on an Event that is
    guaranteed to be set, and raises ConnectionError if state never reaches
    CONNECTED.
    """

    async def test_open_returns_when_connection_established(self):
        conn = _make_connection()

        async def fake_connect(_session):
            await conn._handle_connection({"socket_id": "1.2", "activity_timeout": 120})
            conn._stop = True

        conn._connect = fake_connect

        await asyncio.wait_for(conn.open(), timeout=2.0)
        self.assertEqual(conn.state, Connection.State.CONNECTED)

    async def test_open_raises_when_stop_is_set_without_connecting(self):
        conn = _make_connection()

        async def fake_connect(_session):
            conn._stop = True

        conn._connect = fake_connect

        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(conn.open(), timeout=2.0)

    async def test_open_raises_on_pusher_connection_failed(self):
        conn = _make_connection()

        async def fake_connect(_session):
            await conn._handle_failure({"code": 4001, "message": "bad app key"})
            conn._stop = True

        conn._connect = fake_connect

        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(conn.open(), timeout=2.0)
        self.assertEqual(conn.state, Connection.State.FAILED)

    async def test_open_raises_when_run_forever_crashes(self):
        conn = _make_connection()

        async def fake_connect(_session):
            raise RuntimeError("boom")

        conn._connect = fake_connect

        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(conn.open(), timeout=2.0)


if __name__ == "__main__":
    unittest.main()
