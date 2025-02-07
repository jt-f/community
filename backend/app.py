from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e8,
    manage_session=False
)

@app.route('/')
def index():
    return 'Server is running!'

@app.route('/message', methods=['POST'])
def receive_message():
    data = request.json
    logger.info(f'Received HTTP message: {data}')
    # Emit the message through Socket.IO
    socketio.emit('message', data)
    return jsonify({'status': 'success'})

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')
    socketio.emit('message', {'from': 'system', 'text': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

@socketio.on('message')
def handle_message(data):
    logger.info(f'Received Socket.IO message: {data}')
    socketio.emit('message', data)

if __name__ == '__main__':
    logger.info("Starting server on http://172.19.36.55:5000")
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True,
        use_reloader=False
    ) 