import os
import random

import pusher
from aiohttp import web

app_id = os.getenv("PUSHER_APP_ID")
app_key = os.getenv("PUSHER_APP_KEY")
app_secret = os.getenv("PUSHER_APP_SECRET")

client = pusher.Pusher(app_id=app_id, key=app_key, secret=app_secret, cluster="eu", ssl=True)

routes = web.RouteTableDef()


@routes.post("/pusher/auth")
async def authenticate_channel(request):
    data = await request.post()
    channel_name = data["channel_name"]
    if channel_name.startswith("presence-"):
        custom_data = {"user_id": random.randint(0, 1000)}
    else:
        custom_data = None

    auth = client.authenticate(data["channel_name"], data["socket_id"], custom_data=custom_data)
    return web.json_response(auth)


app = web.Application()
app.add_routes(routes)
web.run_app(app)
