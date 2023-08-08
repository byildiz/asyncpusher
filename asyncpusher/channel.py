import logging
from collections import defaultdict
from enum import Enum

from asyncpusher.connection import Connection


class Channel:
    class State(Enum):
        UNSUBSCRIBED = 1
        SUBSCRIBED = 2
        FAILED = 3

    def __init__(
        self,
        name,
        connection: Connection,
        log: logging.Logger,
    ):
        self._name = name
        self._connection = connection
        self._log = log

        self._event_callbacks = defaultdict(dict)
        self.state = self.State.UNSUBSCRIBED

        self.bind("pusher_internal:subscription_succeeded", self._handle_success)

    def bind(self, event_name, callback, *args, **kwargs):
        self._event_callbacks[event_name][callback] = (args, kwargs)

    def unbind(self, event_name, callback):
        del self._event_callbacks[event_name][callback]

    async def handle_event(self, event_name, data):
        if event_name not in self._event_callbacks:
            self._log.warning(f"Unhandled event, channel: {self._name}, event: {event_name}, data: {data}")
            return

        for callback, (args, kwargs) in self._event_callbacks[event_name].items():
            try:
                await callback(data, *args, **kwargs)
            except Exception:
                self._log.exception(f"Exception in callback: {data}")

    async def trigger(self, event):
        if not event["event"].startswith("client-"):
            raise ValueError("Client event has to start with client-")

        if not self.is_private() and not self.is_presence():
            raise ValueError("Client event can only be sent on private or presence channels")

        event["channel"] = self._name
        await self._connection.send_event(event)

    def is_private(self):
        return self._name.startswith("private-")

    def is_presence(self):
        return self._name.startswith("presence-")

    async def _handle_success(self, _):
        self.state = self.State.SUBSCRIBED
