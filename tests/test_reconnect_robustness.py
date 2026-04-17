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


class RunForeverTest(unittest.IsolatedAsyncioTestCase):
    """
    _run_forever used to only catch aiohttp.ClientError, so any other
    exception (asyncio.TimeoutError, OSError from DNS, JSONDecodeError,
    internal-handler KeyError, ...) killed the reconnect loop silently.
    """

    async def test_continues_after_non_client_error(self):
        conn = _make_connection()
        call_count = 0

        async def fake_connect(_session):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("boom")
            conn._stop = True

        conn._connect = fake_connect

        await asyncio.wait_for(conn._run_forever(), timeout=2.0)

        self.assertEqual(call_count, 3)
        self.assertEqual(conn._connection_attempts, 2)

    async def test_cancelled_error_is_not_swallowed(self):
        conn = _make_connection()

        async def fake_connect(_session):
            await asyncio.sleep(10)

        conn._connect = fake_connect

        task = asyncio.create_task(conn._run_forever())
        # yield so the task enters the fake_connect sleep
        await asyncio.sleep(0.05)
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task


class HandleConnectionResetTest(unittest.IsolatedAsyncioTestCase):
    """
    _handle_connection did not reset _connection_attempts, so backoff
    accumulated across the full lifetime of the client: connecting after
    5 failed attempts and then getting disconnected would start the next
    reconnect from attempt #6, waiting tens of seconds unnecessarily.
    """

    async def test_resets_connection_attempts_on_success(self):
        conn = _make_connection()
        conn._connection_attempts = 7

        await conn._handle_connection({"socket_id": "42.1", "activity_timeout": 120})

        self.assertEqual(conn._connection_attempts, 0)
        self.assertEqual(conn.state, Connection.State.CONNECTED)


if __name__ == "__main__":
    unittest.main()
