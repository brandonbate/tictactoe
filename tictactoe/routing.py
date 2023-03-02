from django.urls import re_path

from tictactoe import consumers

websocket_urlpatterns = [
    re_path(r"ws/play/$", consumers.GameConsumer.as_asgi()),
]