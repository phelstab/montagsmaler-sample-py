import json

# Network settings
HOST = "localhost"
PORT = 5555

# Game settings
CANVAS_SIZE = 500
COUNTDOWN_SECONDS = 5
MIN_PLAYERS = 2

# Message types
MSG_JOIN = "JOIN"
MSG_DRAW = "DRAW"
MSG_CLEAR = "CLEAR"
MSG_GUESS = "GUESS"
MSG_STATE = "STATE"
MSG_COUNTDOWN = "COUNTDOWN"
MSG_RESULT = "RESULT"

# Game states
STATE_WAITING = "waiting"
STATE_COUNTDOWN = "countdown"
STATE_PLAYING = "playing"
STATE_ROUND_END = "round_end"

# Words to guess (simplified list)
WORDS = ["apple", "house", "car", "dog", "cat", "book", "tree", "sun", "moon", "computer"]

def encode_message(msg_type, data):
    """Encode a message to be sent over the network"""
    message = {"type": msg_type, "data": data}
    # Add a newline as a message delimiter
    return (json.dumps(message) + "\n").encode('utf-8')

def decode_message(data):
    """Decode a message received from the network"""
    return json.loads(data.decode('utf-8'))