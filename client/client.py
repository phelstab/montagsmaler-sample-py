import socket
import json
import tkinter as tk
from tkinter import messagebox, simpledialog
import threading
from shared.common import *

class PictionaryClient:
    def __init__(self, master):
        self.master = master
        master.title("Pictionary Game")
        master.resizable(False, False)
        master.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Network
        self.socket = None
        self.connected = False
        self.receiver_thread = None
        
        # Game state
        self.is_drawer = False
        self.players = []
        self.word = None
        self.game_state = STATE_WAITING
        
        # Drawing variables
        self.drawing = False
        self.last_x = 0
        self.last_y = 0
        self.line_width = 2
        self.line_color = "black"
        
        # Build the UI
        self.setup_ui()
        
        # Connect to server
        self.connect_to_server()
    
    def setup_ui(self):
        """Create the user interface"""
        # Main frame
        self.main_frame = tk.Frame(self.master)
        self.main_frame.pack(padx=10, pady=10)
        
        # Status label
        self.status_label = tk.Label(self.main_frame, text="Connecting to server...", 
                                     font=("Arial", 12))
        self.status_label.pack(pady=5)
        
        # Canvas (whiteboard)
        self.canvas_frame = tk.Frame(self.main_frame, bd=2, relief=tk.SUNKEN)
        self.canvas_frame.pack(pady=10)
        
        self.canvas = tk.Canvas(self.canvas_frame, width=CANVAS_SIZE, height=CANVAS_SIZE, 
                               bg="white", cursor="pencil")
        self.canvas.pack()
        
        # Canvas bindings for drawing
        self.canvas.bind("<Button-1>", self.start_draw)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.stop_draw)
        
        # Player info frame
        self.players_frame = tk.Frame(self.main_frame)
        self.players_frame.pack(fill=tk.X, pady=5)
        
        self.players_label = tk.Label(self.players_frame, text="Players: ", font=("Arial", 10))
        self.players_label.pack(anchor=tk.W)
        
        # Controls frame
        self.controls_frame = tk.Frame(self.main_frame)
        self.controls_frame.pack(fill=tk.X, pady=5)
        
        # Clear button (only for drawer)
        self.clear_button = tk.Button(self.controls_frame, text="Clear Canvas", 
                                     command=self.clear_canvas)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        self.clear_button["state"] = tk.DISABLED
        
        # Guessing frame
        self.guess_frame = tk.Frame(self.main_frame)
        self.guess_frame.pack(fill=tk.X, pady=5)
        
        self.guess_label = tk.Label(self.guess_frame, text="Your guess: ", font=("Arial", 10))
        self.guess_label.pack(side=tk.LEFT)
        
        self.guess_entry = tk.Entry(self.guess_frame, width=30)
        self.guess_entry.pack(side=tk.LEFT, padx=5)
        self.guess_entry.bind("<Return>", self.send_guess)
        
        self.guess_button = tk.Button(self.guess_frame, text="Guess", command=self.send_guess)
        self.guess_button.pack(side=tk.LEFT)
        
        # Word display (for drawer)
        self.word_frame = tk.Frame(self.main_frame)
        self.word_frame.pack(fill=tk.X, pady=5)
        
        self.word_label = tk.Label(self.word_frame, text="", font=("Arial", 12, "bold"))
        self.word_label.pack()
        
        # Chat frame - displays guesses
        self.chat_frame = tk.Frame(self.main_frame)
        self.chat_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.chat_label = tk.Label(self.chat_frame, text="Chat:", font=("Arial", 10))
        self.chat_label.pack(anchor=tk.W)
        
        self.chat_display = tk.Text(self.chat_frame, width=50, height=10, state=tk.DISABLED)
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        # Update UI based on initial state
        self.update_controls()
    
    def connect_to_server(self):
        """Connect to the game server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((HOST, PORT))
            self.connected = True
            self.status_label.config(text="Connected to server")
            
            # Start thread to receive messages
            self.receiver_thread = threading.Thread(target=self.receive_messages)
            self.receiver_thread.daemon = True
            self.receiver_thread.start()
            
        except Exception as e:
            self.status_label.config(text=f"Connection error: {e}")
            messagebox.showerror("Connection Error", 
                               f"Could not connect to server at {HOST}:{PORT}\n{str(e)}")
    
    def receive_messages(self):
        """Receive and process messages from the server"""
        try:
            buffer = ""
            while self.connected:
                data = self.socket.recv(4096)
                if not data:
                    break
                
                buffer += data.decode('utf-8')
                
                # Process complete messages
                while "\n" in buffer:
                    # Split at the newline
                    message_str, buffer = buffer.split("\n", 1)
                    try:
                        message = json.loads(message_str)
                        # Process the message in the main thread
                        self.master.after(0, lambda m=message: self.handle_message(m))
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                    except Exception as e:
                        print(f"Error processing message: {e}")
        except Exception as e:
            if self.connected:  # Only show error if we didn't disconnect intentionally
                print(f"Connection error: {e}")
                self.master.after(0, lambda: self.status_label.config(
                    text=f"Connection lost: {e}"))
        finally:
            self.connected = False
            self.master.after(0, lambda: self.status_label.config(
                text="Disconnected from server"))
        
    def handle_message(self, message):
        """Process a message from the server"""
        msg_type = message["type"]
        msg_data = message["data"]
        
        if msg_type == MSG_STATE:
            # Update game state
            self.game_state = msg_data.get("state", STATE_WAITING)
            self.players = msg_data.get("players", [])
            self.is_drawer = msg_data.get("is_drawer", False)
            
            if "word" in msg_data:
                self.word = msg_data["word"]
                self.word_label.config(text=f"Word to draw: {self.word}")
            
            self.update_players_display()
            self.update_controls()
            
            # Update status message
            if self.game_state == STATE_WAITING:
                self.status_label.config(text="Waiting for players...")
            elif self.game_state == STATE_COUNTDOWN:
                self.status_label.config(text="Game starting soon...")
            elif self.game_state == STATE_PLAYING:
                if self.is_drawer:
                    self.status_label.config(text="You are drawing!")
                else:
                    self.status_label.config(text="Guess the word!")
            elif self.game_state == STATE_ROUND_END:
                self.status_label.config(text="Round ended")
        
        elif msg_type == MSG_DRAW:
            # Draw on canvas
            if not self.is_drawer:  # Only process draw messages if we're not the drawer
                x1, y1, x2, y2 = msg_data["x1"], msg_data["y1"], msg_data["x2"], msg_data["y2"]
                self.canvas.create_line(x1, y1, x2, y2, width=self.line_width, 
                                       fill=self.line_color, capstyle=tk.ROUND, smooth=True)
        
        elif msg_type == MSG_CLEAR:
            # Clear the canvas
            self.canvas.delete("all")
        
        elif msg_type == MSG_GUESS:
            # Display guess in chat
            player = msg_data["player"]
            guess = msg_data["guess"]
            self.add_to_chat(f"{player}: {guess}")
        
        elif msg_type == MSG_COUNTDOWN:
            # Update countdown display
            seconds = msg_data["seconds"]
            self.status_label.config(text=f"Game starting in {seconds}...")
        
        elif msg_type == MSG_RESULT:
            # Display round result
            if "winner" in msg_data:
                winner = msg_data["winner"]
                word = msg_data["word"]
                self.status_label.config(text=f"{winner} guessed correctly: {word}")
                self.add_to_chat(f"*** {winner} guessed the word: {word} ***")
            elif "error" in msg_data:
                error = msg_data["error"]
                word = msg_data.get("word", "")
                self.status_label.config(text=f"Round ended: {error}")
                if word:
                    self.add_to_chat(f"*** Round ended: {error}. The word was: {word} ***")
                else:
                    self.add_to_chat(f"*** Round ended: {error} ***")
    
    def update_players_display(self):
        """Update the display of player information"""
        player_text = "Players: "
        for player in self.players:
            name = player["name"]
            score = player["score"]
            is_drawer = player["is_drawer"]
            
            player_info = f"{name} ({score})"
            if is_drawer:
                player_info += " (Drawing)"
            
            player_text += player_info + ", "
        
        # Remove trailing comma and space
        if player_text.endswith(", "):
            player_text = player_text[:-2]
            
        self.players_label.config(text=player_text)
    
    def update_controls(self):
        """Update control states based on game state and player role"""
        if self.is_drawer and self.game_state == STATE_PLAYING:
            # Drawer can draw and clear
            self.canvas.config(cursor="pencil")
            self.clear_button["state"] = tk.NORMAL
            self.guess_entry["state"] = tk.DISABLED
            self.guess_button["state"] = tk.DISABLED
            self.word_label.pack(fill=tk.X)
        else:
            # Non-drawer or not playing
            self.canvas.config(cursor="arrow")
            self.clear_button["state"] = tk.DISABLED
            
            if self.game_state == STATE_PLAYING and not self.is_drawer:
                # Guesser can guess during play
                self.guess_entry["state"] = tk.NORMAL
                self.guess_button["state"] = tk.NORMAL
            else:
                # Not playing or round ended
                self.guess_entry["state"] = tk.DISABLED
                self.guess_button["state"] = tk.DISABLED
            
            # Hide word for non-drawers
            if not self.is_drawer:
                self.word_label.config(text="")
    
    def start_draw(self, event):
        """Handle mouse down event for drawing"""
        if self.is_drawer and self.game_state == STATE_PLAYING:
            self.drawing = True
            self.last_x = event.x
            self.last_y = event.y
    
    def draw(self, event):
        """Handle mouse drag event for drawing"""
        if self.drawing and self.is_drawer and self.game_state == STATE_PLAYING:
            x, y = event.x, event.y
            # Draw line on canvas
            self.canvas.create_line(self.last_x, self.last_y, x, y, 
                                   width=self.line_width, fill=self.line_color, 
                                   capstyle=tk.ROUND, smooth=True)
            
            # Send drawing data to server
            draw_data = {
                "x1": self.last_x,
                "y1": self.last_y,
                "x2": x,
                "y2": y
            }
            self.send_message(MSG_DRAW, draw_data)
            
            # Update last position
            self.last_x = x
            self.last_y = y
    
    def stop_draw(self, event):
        """Handle mouse up event for drawing"""
        self.drawing = False
    
    def clear_canvas(self):
        """Clear the drawing canvas"""
        if self.is_drawer and self.game_state == STATE_PLAYING:
            self.canvas.delete("all")
            self.send_message(MSG_CLEAR, {})
    
    def send_guess(self, event=None):
        """Send a word guess to the server"""
        if not self.is_drawer and self.game_state == STATE_PLAYING:
            guess = self.guess_entry.get().strip()
            if guess:
                self.send_message(MSG_GUESS, {"guess": guess})
                self.guess_entry.delete(0, tk.END)
    
    def add_to_chat(self, message):
        """Add a message to the chat display"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, message + "\n")
        self.chat_display.see(tk.END)  # Scroll to bottom
        self.chat_display.config(state=tk.DISABLED)
    
    def send_message(self, msg_type, data):
        """Send a message to the server"""
        if self.connected:
            try:
                message = encode_message(msg_type, data)
                self.socket.send(message)
            except Exception as e:
                print(f"Error sending message: {e}")
                self.status_label.config(text=f"Error sending message: {e}")
    
    def on_closing(self):
        """Handle window close event"""
        # Clean disconnect
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    client = PictionaryClient(root)
    root.mainloop()