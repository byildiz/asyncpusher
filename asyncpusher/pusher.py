import asyncio
import hashlib
import hmac
import json
import logging

from asyncpusher.channel import Channel
from asyncpusher.connection import Connection

VERSION = "0.1.0"
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
        secret: str | None = None,
        signer=None,
        user_data=None,
        auto_sub=False,
        log: logging.Logger | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        **kwargs,
    ):
        self._key = key

        self._secret = secret
        self._signer = signer
        self._user_data = user_data if user_data is not None else {}

        self._log = log if log is not None else logging.getLogger(__name__)
        self._loop = loop if loop is not None else asyncio.get_running_loop()

        self.channels: dict[Channel] = {}

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

    async def subscribe(self, channel_name, auth=None):
        if channel_name in self.channels:
            return self.channels[channel_name]

        await self._subscribe(channel_name, auth)

        channel = Channel(channel_name, auth, self.connection, self._log)
        self.channels[channel_name] = channel

        return channel

    async def _subscribe(self, channel_name, auth=None):
        data = {"channel": channel_name}
        if auth is None:
            if channel_name.startswith("presence-"):
                data["auth"] = await self._generate_auth_token(channel_name, is_presence=True)
                data["channel_data"] = json.dumps(self.user_data)
            elif channel_name.startswith("private-"):
                data["auth"] = await self._generate_auth_token(channel_name)
        else:
            data["auth"] = auth

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
                await self._subscribe(channel.name, channel.auth)

    async def _generate_auth_token(self, channel_name: str, is_presence=False):
        if self._secret is None and self._signer is None:
            raise ValueError("One of them has to be provided")

        if self._secret is not None:
            subject = f"{self.connection.socket_id}:{channel_name}"
            if is_presence:
                subject = f"{subject}:{json.dumps(self._user_data)}"
            hasher = hmac.new(self._as_bytes(self._secret), subject.encode(), hashlib.sha256)
            auth = f"{self._key}:{hasher.hexdigest()}"
        else:
            data = {
                "socket_id": self.connection.socket_id,
                "channel_name": channel_name,
            }
            if is_presence:
                data["user_data"] = self._user_data
            auth = await self._signer(data)
        return auth

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
