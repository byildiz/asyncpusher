# aiopusher

aiopusher is an asynchronous python client library for [Pusher](https://pusher.com/channels/)

## Features

- uses well-maintained [aiohttp](https://github.com/aio-libs/aiohttp)'s websocket library
- auto handles reconnection
- asynchronous
- supports Pusher Channels [protocol 7](https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/)

## Install

```
$ python3 -m pip install aiopusher
```

## Usage

```python
import asyncio
import logging
import sys

from aiopusher.channel import Channel
from aiopusher.pusher import Pusher

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


async def handle_event(data):
    logging.info(f"{market} {data}")


async def main():
    loop = asyncio.get_running_loop()

    pusher = Pusher("<PUSHER_APP_KEY>", loop=loop)
    pusher.channels[channel_name] = channel
    await pusher.connect()
    channel_name = "<CHANNEL_NAME>"
    channel = await pusher.subscribe(channel_name)
    channel.bind("diff", handle_event, "usdt_tl")
    await asyncio.sleep(5)
    await pusher.unsubscribe(channel_name)
    await asyncio.sleep(5)
    await pusher.disconnect()


asyncio.run(main())
```