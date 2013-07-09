import sys, json, socket, os
if 'modules' not in sys.path: sys.path.append('modules')
from gevent import monkey
from socketio.server import SocketIOServer
from socketio.namespace import BaseNamespace
from util import BroadcastNamespace
from socketio import socketio_manage
from flask import Flask, request, render_template, abort
import jinja2
from util import Socket, load_settings
load_settings()
from settings import DEBUG, SHUTDOWN_KEY

#monkey.patch_all()
app = Flask(__name__)
app.debug = True
sock = Socket()
SOCK_PORT = 2148

track = None

# Templates
templates = {}
def reload_templates():
    global templates
    templates = {}
    track_template = file('templates/track.html').read()
    templates['track'] = jinja2.Template(track_template)
reload_templates()

# Socket endpoint
@app.route('/socket.io/<path:rest>')
def push_stream(rest):
    try:
        socketio_manage(request.environ, {'/track': TrackInfoNamespace}, request)
    except:
        app.logger.error("Exception while handling socketio connection",
                         exc_info=True)
    return ""

# It's weird but it works
class TrackInfoNamespace(BroadcastNamespace):
    control_socket = None
    track = None

    def __init__(self, *args, **kwargs):
        if self.control_socket == None:
            raise ValueError("must attatch a control socket first")
        BroadcastNamespace.__init__(self, *args, **kwargs)
    
    @classmethod
    def attatch_control(cls, control_sock):
        cls.control_socket = control_sock
    
    @classmethod
    def update_track(cls, track):
        if track != cls.track:
            cls.track = track
            cls.broadcast('update', json.dumps(track))

    @classmethod
    def clear_track(cls):
        cls.update_track(None)
        
    def on_request(self, message):
        if message == 'track':
            self.emit('track', json.dumps(self.track))
        else:
            self.emit('error', 'improper request')
            
    def on_command(self, message):
        if message in ['next', 'pause', 'previous']:
            if DEBUG: print "sending command '%s' to program" % message
            j = json.dumps({"type" : "command",
                            "data" :  message})
            try:
                self.control_socket.sendln(j)
            except ValueError:
                self.emit('error', "no program to control")
        else:
            self.emit('error', 'not a command')

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

# Main page
@app.route('/')
def hello_world():
    try:
        return file('templates/track.html').read()
    except Exception as e:
        return `e`

def on_message(message):
    if DEBUG: print "Message: %s" % message.strip()
    try:
        j = json.loads(message)
    except ValueError:
        print "Error: Improperly formatted message"
    try:
        if j['type'] == 'update':
            if DEBUG: print "Now Playing %s by %s" % (j['data']['track'],
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
    TrackInfoNamespace.attatch_control(sock)
    server = SocketIOServer(("", 80), app, resource="socket.io")
    print "running on %s" % ip_addr
    server.serve_forever()

if __name__ == "__main__":
    run()
