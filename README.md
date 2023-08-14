asyncpusher is an asynchronous python client library for [Pusher](https://pusher.com/channels/)

## Features

- Uses well-maintained [aiohttp](https://github.com/aio-libs/aiohttp)'s websocket library
- Reliable connection
- Auto handles reconnection
- Asynchronous
- Fast
- Supports Pusher Channels [protocol 7](https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/)
- Supports presence and private channels

## Install

```
$ python3 -m pip install asyncpusher
```

## Usage

```python
import asyncio
import logging
import sys

from asyncpusher.channel import Channel
from asyncpusher.pusher import Pusher

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
    channel.bind("diff", handle_event)
    await asyncio.sleep(5)
    await pusher.unsubscribe(channel_name)
    await asyncio.sleep(1)
    await pusher.disconnect()


asyncio.run(main())
```
