from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import os
from config.database import DatabaseConfig
from socketio_instance import socketio
from routes.auth import auth_bp
from routes.chat import chat_bp
from routes.socket_events import register_socket_events

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Enable CORS
CORS(app)
socketio.init_app(app)

# Initialize database
db_config = DatabaseConfig()
db_config.connect()

app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(chat_bp, url_prefix='/api/chat')
register_socket_events(socketio)

# Serve frontend files
@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')


@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return {'error': 'Resource not found'}, 404

@app.errorhandler(500)
def internal_error(error):
    return {'error': 'Internal server error'}, 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True
    )