import sys, json, socket, os
#if 'modules' not in sys.path: sys.path.insert(0, 'modules')
from gevent import monkey
from socketio.server import SocketIOServer
from socketio.namespace import BaseNamespace
from socketio.mixins import BroadcastMixin
from socketio import socketio_manage
from flask import Flask, request, render_template, abort
import jinja2
try:
    from util import Track, Socket, TrackInfoNamespace
except:
    import imp
    util = imp.load_package('util', 'modules')

#monkey.patch_all()
app = Flask(__name__)
app.debug = True
sock = Socket()
SOCK_PORT = 2148
DEBUG = False

track = None
#get_track = lambda: Track() # the function to get the current track
SHUTDOWN_KEY = "i've made a terrible mistake"

# Templates
templates = {}
def reload_templates():
    global templates
    templates = {}
    t = file('templates/track.html').read()
    templates['track'] = jinja2.Template(t)
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

# To shut down the server.
@app.route('/shutdown', methods=['POST'])
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
    j = json.loads(message)
    if j['type'] == 'update':
        if DEBUG: print "Now Playing %s by %s" % (j['data']['track'],
                                                  j['data']['artist'])
        TrackInfoNamespace.update_track(j['data'])

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
    server = SocketIOServer((ip_addr, 80), app, resource="socket.io")
    print "running on %s" % ip_addr
    server.serve_forever()

if __name__ == "__main__":
    run()
