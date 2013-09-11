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
app.debug = DEBUG
SOCK_PORT = 2148


######## ROUTES ########

#### utility pages

#To shut down the server.
@app.route('/shutdown', methods = ['GET', 'POST'] if DEBUG else ['POST'])
def shutdown():
    if request.form['key'] == SHUTDOWN_KEY or DEBUG:
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
    else:
        abort(405)


#### main views

#main view page for the user
@app.route('/')
def track_page():
    return render_template('track.html',
                           title = TrackInfoNamespace.track['title'],
                           artist = TrackInfoNamespace.track['artist'])

#admin view
@app.route('/admin')
def admin_page():
    return render_template('admin.html',
                           title = TrackInfoNamespace.track['title'],
                           artist = TrackInfoNamespace.track['artist'])

#### uploading tracks

#function to tell the main program to handle a new song uploaded to the temp folder
def add_file(key):
    try:
        sock.sendln(json.dumps({"type":"upload",
                                "data":key}))
    except Socket.NotConnectedException:
        print "No program to signal!\nkey = " + key

#record and save a file
def record_and_save(f):
    #TODO: record a timeout time for the key
    filename = secure_filename(f.filename)
    key = base64.urlsafe_b64encode(os.urandom(9))
    path = os.path.join('music', 'temp', key)
    os.mkdir(path)
    filepath = os.path.join(path, filename)
    f.save(filepath)
    return key, filename

#/upload route
@app.route('/upload', methods=['POST'])
def upload():
    #get the uploaded file or redirect to http://host/
    if 'file' in request.files:
        f = request.files['file']
    else:
        redirect("/")
    #util.allowed_file checks that the extension is in util.FORMATS
    if util.allowed_file(f.filename):
        #save the file internally in the \temp folder and record a timeout for the file
        key, filename = record_and_save(f)
        #if the metadata is valid, process the file
        if metadata_is_valid(filepath):
            add_file(key)
            return redirect("/")
        else: #get additional info from uploader
            return redirect("/edit_upload?key=%s&filename=%s" % (key, filename))
    else:
        return redirect("/?error=extension")

#package up a songs metadata for the /edit_upload form
def package_metadata(path):
    metadata = util.get_metadata(path)
    packaged = []
    for datum in metadata:
        packaged.append({"friendly_name" : util.translate(datum),
                          "name"          : datum,
                          "value"         : metadata[datum],
                          "required"      : datum in REQUIRED_METADATA})
    return packaged

#check if metadata is valid (really just checks if the REQUIRED_METADATA is present
def metadata_is_valid(path):
    metadata = util.get_metadata(path)
    return all((metadatum in metadata for metadatum in REQUIRED_METADATA))

#check that an upload key-set (key and filename) is good
GOOD_KEY = 0
BAD_KEY = 1
BAD_FILENAME = 2
NO_SUCH_FILE = 3
def check_key(key, filename):
    if key != secure_filename(key):
        return BAD_KEY
    elif filename != secure_filename(filename):
        return BAD_FILENAME
    elif not os.path.exists(os.path.join("music", "temp", key, filename)):
        return NO_SUCH_FILE
    else:
        return GOOD_KEY

#edit metadata of an uploaded song
@app.route('/edit_upload', methods=['GET', 'POST'])
def edit_upload():
    if request.method == "POST":
        key = request.form["key"]
        filename = request.form["filename"]
        #if either of the above don't exist, a 400 BAD REQUEST will automatically be returned
    else:
        key = request.args.get("key")
        filename = request.args.get("filename")
        if not key or not filename:
            #redirect to / instead of returning a 400 BAD REQUEST if GET
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
        metadata = package_metadata(path)
        return render_template('metadata.html', metadata = metadata,
                                                key = key,
                                                filename = filename)

#socketio endpoint
@app.route('/socket.io/<path:rest>')
def push_stream(rest):
    try:
        socketio_manage(request.environ, {'/track' : TrackInfoNamespace,
                                          '/control' : ControlNamespace}, request)
    except:
        app.logger.error("Exception while handling socketio connection",
                         exc_info=True)
    return ""

######## SOKETIO ENDPOINT NAMESPACES ########

# Control namespace. Passed commands to program over server-program socket
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

# namespace for sending out track updates
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



######## SERVER_TO_PROGRAM COMM ########

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

######## START SERVER ########

def main():
    global sock
    ip_addr = socket.gethostbyname(socket.gethostname())
    sock = Socket()
    print "connecting to music player..."
    sock.on_connect(on_connect)
    sock.on_disconnect(on_disconnect)
    sock.connect('localhost', SOCK_PORT, on_message)
    ControlNamespace.attatch_control(sock)
    server = SocketIOServer(("", 80), app, resource="socket.io")
    print "running on %s" % ip_addr
    server.serve_forever()

if __name__ == "__main__":
    main()
