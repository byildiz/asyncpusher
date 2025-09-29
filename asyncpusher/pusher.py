import asyncio
import logging

from asyncpusher.channel import Channel
from asyncpusher.connection import Connection

VERSION = "0.2.2"
PROTOCOL = 7
DEFAULT_CLIENT = "asyncpusher"


class Pusher:
    def __init__(
        self,
        key: str,
        cluster: str | None = None,
        secure=True,
        custom_host: str | None = None,
        custom_port: int | None = None,
        custom_client: str | None = None,
        channel_authenticator=None,
        user_authenticator=None,
        auto_sub=False,
        log: logging.Logger | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        **kwargs,
    ):
        self._key = key

        self._channel_authenticator = channel_authenticator
        self._user_authenticator = user_authenticator

        self._log = log if log is not None else logging.getLogger(__name__)
        self._loop = loop if loop is not None else asyncio.get_running_loop()

        self.channels: dict[str, Channel] = {}

        if custom_host is not None and cluster is not None:
            raise ValueError("Could not provide both cluster and custom host")

        self._url = self._build_url(custom_host, custom_client, custom_port, cluster, secure)
        self.connection = Connection(self._loop, self._url, self._handle_event, self._log, **kwargs)

        if auto_sub:
            self.connection.bind("pusher:connection_established", self._resubscribe)

    async def connect(self):
        await self.connection.open()

    async def disconnect(self):
        await self.connection.close()

    async def _handle_event(self, channel_name, event_name, data):
        if channel_name not in self.channels:
            self._log.warning(f"Unsubscribed event, channel: {channel_name}, event: {event_name}, data: {data}")
            return
        await self.channels[channel_name].handle_event(event_name, data)

    async def subscribe(self, channel_name):
        if channel_name in self.channels:
            return self.channels[channel_name]

        channel = Channel(channel_name, self.connection, self._log)
        await self._subscribe(channel)

        self.channels[channel_name] = channel

        return channel

    async def _subscribe(self, channel: Channel):
        data = {"channel": channel._name}
        if channel.is_private() or channel.is_presence():
            auth = await self._authenticate_channel(channel)
            data["auth"] = auth["auth"]
            if channel.is_presence():
                data["channel_data"] = auth["channel_data"]
        event = {"event": "pusher:subscribe", "data": data}
        await self.connection.send_event(event)

    async def unsubscribe(self, channel_name):
        if channel_name in self.channels:
            data = {"channel": channel_name}
            event = {"event": "pusher:unsubscribe", "data": data}
            await self.connection.send_event(event)

            del self.channels[channel_name]

    async def _resubscribe(self, _):
        if len(self.channels) > 0:
            self._log.info("Resubscribing channels...")
            for channel in self.channels.values():
                await self._subscribe(channel)

    async def _authenticate_channel(self, channel: Channel):
        if self._channel_authenticator is None:
            raise ValueError("channel_authenticator has to be provided")

        data = {
            "socket_id": self.connection.socket_id,
            "channel_name": channel._name,
        }
        return await self._channel_authenticator(data)

    def _build_url(self, custom_host, custom_client, custom_port, cluster, secure):
        self._protocol = "wss" if secure else "ws"

        if custom_host is not None:
            self._host = custom_host
        elif cluster is not None:
            self._host = f"ws-{cluster}.pusher.com"
        else:
            self._host = "ws.pusherapp.com"

        if custom_port is not None:
            self._port = custom_port
        else:
            self._port = 443 if secure else 80

        self._client = custom_client if custom_client is not None else DEFAULT_CLIENT

        self._path = f"/app/{self._key}?client={self._client}&version={VERSION}&protocol={PROTOCOL}"

        return f"{self._protocol}://{self._host}:{self._port}{self._path}"

    def _as_bytes(self, token: str):
        return token.encode()
