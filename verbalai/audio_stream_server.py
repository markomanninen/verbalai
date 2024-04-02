# audio_stream_server.py - A simple Flask server to stream audio files
import os
import threading
import mimetypes
from werkzeug.serving import make_server
from flask import Flask, request, Response, send_file

app = Flask(__name__)

class ServerThread(threading.Thread):
    def __init__(self, host, port, audio_dir):
        threading.Thread.__init__(self)
        self.srv = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()
        full_audio_dir_path = os.path.join(os.getcwd(), audio_dir)
        app.config['AUDIO_FILES_DIRECTORY'] = full_audio_dir_path

    def run(self):
        print(f"Serving audio files from {app.config['AUDIO_FILES_DIRECTORY']} on {self.srv.server_address}")
        self.srv.serve_forever()

    def shutdown(self):
        self.srv.shutdown()

@app.route('/stream_audio')
def stream_audio():
    filename = request.args.get('filename')
    if not filename:
        return "Filename not specified", 400

    file_path = os.path.join(app.config['AUDIO_FILES_DIRECTORY'], filename)
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return "File not found", 404
    
    # Determine the file's MIME type based on its extension
    # Default to 'audio/mpeg' if the MIME type cannot be determined
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = 'audio/mpeg'

    range_header = request.headers.get('Range', None)
    if not range_header:
        return send_file(file_path)

    size = os.path.getsize(file_path)
    _, _, range_spec = range_header.partition('=')
    range_start, _, range_end = range_spec.partition('-')
    range_start = int(range_start) if range_start else 0
    range_end = int(range_end) if range_end else size - 1

    data_length = range_end - range_start + 1
    data = None
    with open(file_path, 'rb') as f:
        f.seek(range_start)
        data = f.read(data_length)

    response = Response(data, 206, mimetype=mime_type, content_type=mime_type, direct_passthrough=True)
    response.headers.add('Content-Range', f'bytes {range_start}-{range_end}/{size}')
    response.headers.add('Accept-Ranges', 'bytes')
    return response
