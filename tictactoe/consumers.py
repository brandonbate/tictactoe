import json
import random
import string
import time

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from tictactoe.models import AvailablePlayer

def random_string(n):
    return ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits, k=n))

def find_available_player():
    available_player = AvailablePlayer.objects.first()
    if(available_player):
        available_player_channel_name = available_player.channel_name
        # We remove this player from the database.
        available_player.delete()
        # AvailablePlayer.objects.filter(channel_name = available_player_channel_name).delete()

        return available_player_channel_name
    
    return None
    
# Given a set of moves, this function identifies a winner and how they won via an
# index to the winning_positions array.
def find_winner(moves):
    winning_positions = [[(0,0),(0,1),(0,2)],[(1,0),(1,1),(1,2)],[(2,0),(2,1),(2,2)],
                         [(0,0),(1,0),(2,0)],[(0,1),(1,1),(2,1)],[(0,2),(1,2),(2,2)],
                         [(0,0),(1,1),(2,2)],[(2,0),(1,1),(0,2)]]
                         
    X_moves = [(move['x'],move['y']) for move in moves if move['played_piece'] == 'X']
    O_moves = [(move['x'],move['y']) for move in moves if move['played_piece'] == 'O']
    
    for idx, win_pos in enumerate(winning_positions):
        if(all(moves in X_moves for moves in win_pos)):
            return ('X',idx)
        if(all(moves in O_moves for moves in win_pos)):
            return ('O',idx)

    if(len(moves)==9):
        return ('T',-1)

    return None


class GameConsumer(AsyncWebsocketConsumer):

    def add_channel_name_to_db(self):
        # Before adding the channel_name, we do a bit of housekeeping. We may sure that the
        # channel_name isn't already on the database due to a glitch.
        AvailablePlayer.objects.filter(channel_name = self.channel_name).delete()
        player = AvailablePlayer(channel_name = self.channel_name)
        player.save()

    async def connect(self):
 
        # We check if there any available players.
        available_player = await sync_to_async(find_available_player)()
        
        if(available_player):
            # This is an indentifier used by channels for game communication.
            self.game_id = random_string(10)

            # Assign X and O randomly to players.
            (available_player_piece, current_player_piece) = ('X','O') if random.uniform(0, 1) < 0.5 else ('O','X')
            
            # Create an attribute so GameConsumer can remember which piece the current_player is using.
            self.playing = current_player_piece
            
            # Send message to available_player with game_id over channel_layer.
            # The GameConsumer for available_player will receive this data via the start_game function.
            new_game_data_for_available_player = {"type": "start_game", 
                                                  "game_id": self.game_id,
                                                  "your_piece": available_player_piece}
            await self.channel_layer.send(available_player, new_game_data_for_available_player);

            self.game_id_name = "game_%s" % self.game_id
            self.moves = []
            await self.channel_layer.group_add(self.game_id_name, self.channel_name)

            # Accepts all WebSocket traffic from user.
            await self.accept()
    
            # Send message to current_player through WebSocket.
            new_game_data_for_current_player = {"type": "start_game", 
                                                "game_id": self.game_id,
                                                "your_piece": current_player_piece}
            await self.send(text_data=json.dumps(new_game_data_for_current_player))
        else:
            # Accepts all WebSocket traffic from user.
            await self.accept()

            # Adds players channel_name to the database.
            await sync_to_async(self.add_channel_name_to_db)()
    
    # This function should only be called on the consumer for the player who first arrives
    # at the server. The second player does this setup in the connect function.
    async def start_game(self, game_data):
            
        self.game_id = game_data["game_id"]
        self.playing = game_data["your_piece"]
        self.game_id_name = "game_%s" % self.game_id
        self.moves = []
        await self.channel_layer.group_add(self.game_id_name, self.channel_name)
        await self.send(text_data=json.dumps(game_data))
        
        
    async def disconnect(self, close_code):
        # TODO: Delete self from database.
        await self.channel_layer.group_discard(self.game_id_name, self.channel_name)
        
    
    # The receive function is receives WebSocket communication, not channel communication!
    async def receive(self, text_data):
        # game_data will be a dictionary with and x and y coordinate for where player
        # clicked in the grid.
        move_data = json.loads(text_data)

        if(not hasattr(self,'game_id_name')):
            return
        
        # We pass the game_data, along with additional info, to the channel layer.
        # Consumers for both players will read this message.
        await self.channel_layer.group_send(
            self.game_id_name, {"type": "game_move", 
                                "played_piece": self.playing,
                                "x": move_data["x"],
                                "y": move_data["y"]}
        )
    
    async def game_move(self, move_data):
    
        # X must go first.
        if len(self.moves) == 0 and move_data['played_piece'] == 'O':
            return;
        
        # Check if game is over
        if len(self.moves) > 0 and 'winner' in self.moves[-1]:
            return
        
        # We prevent users from going out of turn.
        if len(self.moves) > 0 and self.moves[-1]['played_piece'] == move_data['played_piece']:
            return;
   
        # Check if square already occupied.
        if (move_data['x'], move_data['y']) in [(move['x'],move['y']) for move in self.moves]:
            return;
   
        # If here, then a valid move.
        self.moves.append(move_data)

        # Check if there is a winer.
        result = await sync_to_async(find_winner)(self.moves)
        if(result):
            (winner, winning_move) = result
            self.moves[-1]['winner'] = winner
            self.moves[-1]['winning_move'] = winning_move

        # Send move to client over websocket.
        await self.send(text_data=json.dumps(move_data))