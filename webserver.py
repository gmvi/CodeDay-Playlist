import sys, json, socket, os, traceback
if 'modules' not in sys.path: sys.path.append('modules')
from socketio import socketio_manage
from socketio.server import SocketIOServer
from socketio.namespace import BaseNamespace
from flask import Flask, request, redirect, render_template, abort
from werkzeug import secure_filename
import base64
import util
from util import BroadcastNamespace, Socket
util.load_settings()
from settings import DEBUG, SHUTDOWN_KEY

app = Flask(__name__)
app.debug = True
sock = Socket()
SOCK_PORT = 2148

def allowed_file(filename):
    split = filename.rsplit('.', 1)
    return len(split) > 1 and split[1] in ['mp3', 'ogg', 'flac', 'm4a']

# To shut down the server.
@app.route('/shutdown', methods=['GET', 'POST'])
def shutdown():
    if str(request.form['key'] == SHUTDOWN_KEY):
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
    else:
        abort(405)

def my_debug(func):
    def debug_func():
        try:
            return func()
        except Exception:
            return traceback.format_exc(50)
    return debug_func

@app.route('/')
def track_page():
    return render_template('track.html',
                           title = TrackInfoNamespace.track['title'],
                           artist = TrackInfoNamespace.track['artist'])

def send_upload(key):
    try:
        sock.sendln(json.dumps({"type":"upload",
                              "data":key}))
    except Socket.NotConnectedException:
        print "No program to signal!\nkey = " + key

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' in request.files:
        file = request.files['file']
    else:
        redirect("/")
    if allowed_file(file.filename):
        filename = secure_filename(file.filename)
        key = base64.urlsafe_b64encode(os.urandom(9))
        path = os.path.join('music', 'temp', key)
        os.mkdir(path)
        path = os.path.join(path, filename)
        file.save(path)
        if valid_metadata(path):
            send_upload(key)
            return redirect("/")
        else:
            return redirect("/metadata?key=%s&filename=%s" % (key, filename))
    else:
        return redirect("/?error=extension")

def translate(datum):
    if datum == "performer":
        datum = "album artist"
    return datum
required = ['title', 'artist']
def get_metadata(path):
    metadata = util.get_metadata(path)
    metadata2 = []
    for datum in metadata:
        metadata2.append({"friendly_name" : translate(datum),
                          "name"          : datum,
                          "value"         : metadata[datum],
                          "required"      : datum in required})
    return metadata2

def valid_metadata(path):
    metadata = util.get_metadata(path)
    return bool(metadata['title'] and metadata['artist'])

class BadKeyError(Exception): pass
def check_key(key, filename):
    if key != secure_filename(key):
        raise BadKeyError("key")
    if filename != secure_filename(filename):
        raise BadKeyError("filename")
    if not os.path.exists(os.path.join("music", "temp", key, filename)):
        raise BadKeyError("path")

@app.route('/metadata', methods=['GET', 'POST'])
def metadata():
    if request.method == "POST":
        key = request.form["key"]
        filename = request.form["filename"]
    else:
        key = request.args.get("key")
        filename = request.args.get("filename")
        if not key or not filename:
            return redirect("/")
    try:
        check_key(key, filename)
    except BadKeyError as e:
        print e
        return redirect("/")

    path = os.path.join("music", "temp", key, filename)
    if request.method == "POST":
        util.overwrite_metadata(path,
                                artist = request.form['artist'],
                                performer = request.form['performer'],
                                album = request.form['album'],
                                title = request.form['title'])
        send_upload(key)
        return redirect("/")
    else:
        metadata = get_metadata(path)
        return render_template('metadata.html', metadata = metadata,
                                                key = key,
                                                filename = filename)

@app.route('/admin')
def admin_page():
    return render_template('admin.html',
                           title = TrackInfoNamespace.track['title'],
                           artist = TrackInfoNamespace.track['artist'])

# Socket endpoint
@app.route('/socket.io/<path:rest>')
def push_stream(rest):
    try:
        socketio_manage(request.environ, {'/track' : TrackInfoNamespace,
                                          '/control' : ControlNamespace}, request)
    except:
        app.logger.error("Exception while handling socketio connection",
                         exc_info=True)
    return ""

class ControlNamespace(BaseNamespace):
    control_socket = None

    def __init__(self, *args, **kwargs):
        if self.control_socket == None:
            raise ValueError("must attatch a control socket first")
        BaseNamespace.__init__(self, *args, **kwargs)

    @classmethod
    def attatch_control(cls, control_sock):
        cls.control_socket = control_sock
            
    def on_command(self, message):
        if DEBUG: print "sending command '%s' to program" % message
        j = json.dumps({"type" : "command",
                        "data" :  message})
        try:
            self.control_socket.sendln(j)
        except ValueError:
            self.emit('error', "no program to control")

class TrackInfoNamespace(BroadcastNamespace):
    track = None
    
    @classmethod
    def update_track(cls, track):
        if track != cls.track:
            cls.track = track
            cls.broadcast('track', json.dumps(track))

    @classmethod
    def clear_track(cls):
        cls.update_track(None)
        
    def on_request(self, message):
        if message == 'track':
            self.emit('track', json.dumps(self.track))
        else:
            self.emit('error', 'Unknown request: %s' % message)


# Communitcation with program.py over localhost Socket
def on_message(message):
    if DEBUG: print "Message: %s" % message.strip()
    try:
        j = json.loads(message)
    except ValueError:
        print "Error: Improperly formatted message"
    try:
        if j['type'] == 'update':
            if DEBUG: print "Now Playing %s by %s" % (j['data']['title'],
                                                      j['data']['artist'])
            TrackInfoNamespace.update_track(j['data'])
    except KeyError:
        print "Error: Improperly formatted message"

def on_connect():
    print "connected to music player."
    sock.sendln(json.dumps({'type' : 'info',
                            'data' : socket.gethostbyname(socket.gethostname())}))

def on_disconnect():
    print "disconnected from music player."
    TrackInfoNamespace.clear_track()

def run():
    ip_addr = socket.gethostbyname(socket.gethostname())
    print "connecting to music player..."
    sock.on_connect(on_connect)
    sock.on_disconnect(on_disconnect)
    sock.connect('localhost', SOCK_PORT, on_message)
    ControlNamespace.attatch_control(sock)
    server = SocketIOServer(("", 80), app, resource="socket.io")
    print "running on %s" % ip_addr
    server.serve_forever()

if __name__ == "__main__":
    run()
