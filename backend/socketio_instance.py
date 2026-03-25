from flask_socketio import SocketIO

# Threading mode avoids extra runtime dependencies for local dev.
socketio = SocketIO(cors_allowed_origins='*', async_mode='threading')
