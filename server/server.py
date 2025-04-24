import socket
import select
import random
import time
import json
import threading
from shared.common import *

class PictionaryServer:
    def __init__(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(5)
        
        self.clients = {}  # socket -> player info
        self.sockets = [self.server_socket]
        
        # Game state
        self.game_state = STATE_WAITING
        self.drawer = None
        self.current_word = None
        self.countdown_timer = None
        self.drawing_data = []
        
        print(f"Server started on {HOST}:{PORT}")
        
    def run(self):
        """Main server loop"""
        while True:
            # Wait for activity on sockets
            readable, _, exceptional = select.select(self.sockets, [], self.sockets, 0.1)
            
            for sock in readable:
                if sock == self.server_socket:
                    # New connection
                    self.accept_connection()
                else:
                    # Client message
                    self.handle_client_message(sock)
            
            # Handle disconnected clients
            for sock in exceptional:
                self.handle_disconnect(sock)
            
            # Check game state
            self.update_game_state()
    
    def accept_connection(self):
        """Handle new client connection"""
        client_socket, address = self.server_socket.accept()
        print(f"New connection from {address}")
        
        # Add to clients with a random player name
        player_name = f"Player_{random.randint(1000, 9999)}"
        self.clients[client_socket] = {
            "name": player_name,
            "address": address,
            "score": 0,
            "is_drawer": False
        }
        self.sockets.append(client_socket)
        
        # Send current game state to the new client
        self.send_game_state_to_client(client_socket)
        
        # Update all clients with the new player list
        self.broadcast_game_state()
    
    def handle_client_message(self, client_socket):
        """Process messages from clients"""
        try:
            data = client_socket.recv(4096)
            if data:
                # Split received data by newline and process each message
                messages = data.decode('utf-8').split('\n')
                for message_str in messages:
                    if not message_str.strip():
                        continue  # Skip empty strings
                        
                    try:
                        message = json.loads(message_str)
                        msg_type = message["type"]
                        msg_data = message["data"]
                        
                        if msg_type == MSG_DRAW and self.clients[client_socket].get("is_drawer", False):
                            # Forward drawing data to all clients
                            self.drawing_data.append(msg_data)
                            self.broadcast(encode_message(MSG_DRAW, msg_data), exclude=None)
                        
                        elif msg_type == MSG_CLEAR and self.clients[client_socket].get("is_drawer", False):
                            # Clear canvas for all clients
                            self.drawing_data = []
                            self.broadcast(encode_message(MSG_CLEAR, {}), exclude=None)
                        
                        elif msg_type == MSG_GUESS and not self.clients[client_socket].get("is_drawer", False):
                            # Handle word guess
                            guess = msg_data["guess"].lower().strip()
                            player_name = self.clients[client_socket]["name"]
                            
                            # Broadcast the guess to all clients
                            self.broadcast(encode_message(MSG_GUESS, {
                                "player": player_name, 
                                "guess": guess
                            }), exclude=None)
                            
                            # Check if guess is correct
                            if self.game_state == STATE_PLAYING and guess == self.current_word:
                                # Award points to guesser
                                self.clients[client_socket]["score"] += 10
                                
                                # Award points to drawer
                                if self.drawer in self.clients:
                                    self.clients[self.drawer]["score"] += 5
                                
                                # End round
                                self.game_state = STATE_ROUND_END
                                self.broadcast(encode_message(MSG_RESULT, {
                                    "winner": player_name,
                                    "word": self.current_word
                                }))
                                
                                # Broadcast updated game state
                                self.broadcast_game_state()
                                
                                # Start new round after a delay
                                threading.Timer(3, self.start_new_round).start()
                    except json.JSONDecodeError as json_err:
                        print(f"Error decoding JSON: {json_err} - Raw data: {message_str[:50]}...")
                    except Exception as msg_err:
                        print(f"Error processing message: {msg_err}")
            else:
                # Empty data means client disconnected
                self.handle_disconnect(client_socket)
        
        except Exception as e:
            print(f"Error handling client message: {e}")
            self.handle_disconnect(client_socket)
    
    def handle_disconnect(self, client_socket):
        """Handle client disconnection"""
        if client_socket in self.clients:
            print(f"Client {self.clients[client_socket]['name']} disconnected")
            
            # Check if this was the drawer
            was_drawer = self.clients[client_socket].get("is_drawer", False)
            
            # Remove from collections
            self.sockets.remove(client_socket)
            del self.clients[client_socket]
            client_socket.close()
            
            # If drawer disconnected and game was in progress, end round
            if was_drawer and self.game_state == STATE_PLAYING:
                self.game_state = STATE_WAITING
                if self.clients:  # If we still have clients
                    self.broadcast(encode_message(MSG_RESULT, {
                        "error": "Drawer disconnected",
                        "word": self.current_word
                    }))
            
            # Update game state for remaining clients
            self.broadcast_game_state()
            
            # Reset game if not enough players
            if len(self.clients) < MIN_PLAYERS:
                self.game_state = STATE_WAITING
                self.drawer = None
                self.current_word = None
                self.drawing_data = []
    
    def update_game_state(self):
        """Check and update game state as needed"""
        if self.game_state == STATE_WAITING and len(self.clients) >= MIN_PLAYERS:
            # Start countdown when we have enough players
            self.game_state = STATE_COUNTDOWN
            self.countdown_timer = COUNTDOWN_SECONDS
            
            # Broadcast the updated game state to all clients
            self.broadcast_game_state()  # Add this line to notify clients
            
            # Start the countdown
            self.broadcast_countdown()
    
    def broadcast_countdown(self):
        """Broadcast countdown to all clients"""
        if self.countdown_timer > 0:
            print(f"Countdown: {self.countdown_timer}")  # Add debugging
            self.broadcast(encode_message(MSG_COUNTDOWN, {"seconds": self.countdown_timer}))
            self.countdown_timer -= 1
            
            # Use a more reliable approach than threading.Timer
            threading.Timer(1, self.broadcast_countdown).start()
        else:
            print("Countdown finished, starting game")  # Add debugging
            # Countdown finished, start the game
            self.start_new_round()

    
    def start_new_round(self):
        """Start a new game round"""
        if len(self.clients) < MIN_PLAYERS:
            self.game_state = STATE_WAITING
            self.broadcast_game_state()
            return
        
        print("Starting new round")  # Debug
        
        # Reset drawing data
        self.drawing_data = []
        
        # Choose a random drawer and word
        self.drawer = random.choice(list(self.clients.keys()))
        self.current_word = random.choice(WORDS)
        
        print(f"Selected drawer: {self.clients[self.drawer]['name']}")  # Debug
        print(f"Selected word: {self.current_word}")  # Debug
        
        # Update client roles
        for client in self.clients:
            self.clients[client]["is_drawer"] = (client == self.drawer)
        
        # Set game state to playing
        self.game_state = STATE_PLAYING
        
        # Send game state to all clients
        self.broadcast_game_state()
        
        # Send the word only to the drawer - THIS PART MAY BE BUGGY
        if self.drawer in self.clients:
            try:
                # Instead of sending a separate message, ensure the word is included in the game state
                # for the drawer when we call broadcast_game_state()
                print(f"Sending word to drawer: {self.current_word}")  # Debug
            except Exception as e:
                print(f"Error sending word to drawer: {e}")
    
    def send_game_state_to_client(self, client):
        """Send current game state to a specific client"""
        client_is_drawer = self.clients[client].get("is_drawer", False)
        
        state_data = {
            "state": self.game_state,
            "players": [{"name": player["name"], "score": player["score"], 
                        "is_drawer": player["is_drawer"]} 
                        for player in self.clients.values()],
            "is_drawer": client_is_drawer
        }
        
        # Add word if this client is the drawer
        if client_is_drawer and self.current_word:
            state_data["word"] = self.current_word
            print(f"Including word in state for drawer: {self.current_word}")  # Debug
        
        # Send the game state
        try:
            client.send(encode_message(MSG_STATE, state_data))
            print(f"Sent game state to {self.clients[client]['name']}")  # Debug
        except Exception as e:
            print(f"Error sending game state: {e}")
            self.handle_disconnect(client)
        
        # Send existing drawing data
        for draw_data in self.drawing_data:
            try:
                client.send(encode_message(MSG_DRAW, draw_data))
            except:
                self.handle_disconnect(client)
    
    def broadcast_game_state(self):
        """Broadcast game state to all clients"""
        for client in self.clients:
            self.send_game_state_to_client(client)
    
    def broadcast(self, message, exclude=None):
        """Send message to all clients except excluded one"""
        for client in self.clients:
            if client != exclude:
                try:
                    client.send(message)
                except:
                    self.handle_disconnect(client)

if __name__ == "__main__":
    server = PictionaryServer()
    try:
        server.run()
    except KeyboardInterrupt:
        print("Server shutting down")