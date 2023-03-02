from django.shortcuts import render

# Create your views here.
def index(request):
    return render(request, "index.html")

def game(request, game_id):
    return render(request, "game.html", {"game_id": game_id})
