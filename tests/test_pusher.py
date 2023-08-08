import asyncio
import logging
import os
import sys
import unittest

import aiohttp

from asyncpusher.channel import Channel
from asyncpusher.connection import Connection
from asyncpusher.pusher import Pusher

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

app_key = os.getenv("PUSHER_APP_KEY")
auth_url = "http://localhost:8080/pusher/auth"


class PusherTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pusher = Pusher(app_key, cluster="eu", channel_authenticator=self._authenticate_channel)
        await self.pusher.connect()

    async def asyncTearDown(self):
        await self.pusher.disconnect()

    async def _authenticate_channel(self, data):
        async with aiohttp.ClientSession() as session:
            response = await session.post(auth_url, data=data)
            return await response.json()

    async def test_authenticate_channel(self):
        channel_name = "private-channel"
        data = {"socket_id": "158404.1277021", "channel_name": channel_name}
        auth = await self._authenticate_channel(data)
        signature = auth["auth"].split(":")[1]
        self.assertEqual(signature, "16c3a0394b2fa86ab3150289d5a8541cfc005e682361990e3e58c03694a2356d")

    async def test_subscribe_presence(self):
        channel_name = "presence-channel"
        await self.pusher.subscribe(channel_name)
        while self.pusher.channels[channel_name].state != Channel.State.SUBSCRIBED:
            await asyncio.sleep(1)

    async def test_subscribe_private(self):
        channel_name = "private-channel"
        await self.pusher.subscribe(channel_name)
        while self.pusher.channels[channel_name].state != Channel.State.SUBSCRIBED:
            await asyncio.sleep(1)
