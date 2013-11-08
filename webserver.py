#system modules
import base64, json, traceback, sys, socket, os
from sqlite3 import OperationalError
if 'modules' not in sys.path: sys.path.append('modules')
#installed modules
from gevent import monkey
from socketio import socketio_manage
from socketio.server import SocketIOServer
from flask import Flask, request, session, redirect, render_template, abort
from werkzeug import secure_filename
from gevent.wsgi import WSGIServer
#local modules
from util import allowed_file, get_song_info, overwrite_metadata, \
                 send_file_partial, WriteWrapper
try:
    import library, playlist#, users, autodj
except OperationalError:
    print "Database is locked"
    raw_input("[enter to exit]")
    exit()
##from util import BroadcastNamespace, Socket
from settings import DEBUG, SHUTDOWN_KEY, SOCK_PORT, REQUIRED_METADATA, COOKIE_SESSION_KEY

##if 'idlelib' not in sys.modules:
##    monkey.patch_all()

app = Flask(__name__)
app.debug = DEBUG
app.secret_key = COOKIE_SESSION_KEY
library.attach(app)
playlist.attach(app)
#users.attach(app)
#autodj.attach(app)

######## ROUTES ########

#### api endpoints ####

#To shut down the server.
@app.route('/api/shutdown', methods =  ['POST'])
def shutdown():
    if request.form['key'] == SHUTDOWN_KEY or DEBUG:
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
    else:
        abort(405)

#### static ####
@app.route('/scripts/<filename>')
def scripts(filename):
    for contraband in ['..', '/', '\\']:
        if contraband in filename:
            abort(404)
    return send_from_directory('scripts', filename)

#### main views

#main view page for the user
@app.route('/')
def track_page():
    #rewrite to access playlist controller
    return render_template('track.html', id=session.get('id'))

#admin view
@app.route('/admin')
def admin_page():
    if not session.get('id') == 'admin': return redirect('/login')
    song = playlist.get_current_song()
    if not song:
        return render_template('admin.html',
                               no_current = True)
    return render_template('admin.html',
                           title = song.name,
                           artist = song.track_performer)

#player
@app.route('/player')
def player_page():
    if not session.get('id') == 'admin': return redirect('/login')
    return render_template('player.html')
#### uploading tracks

#record and save a file
def record_and_save(f):
    #TODO: record a timeout time for the key
    filename = secure_filename(f.filename)
    key = base64.urlsafe_b64encode(os.urandom(9))
    path = os.path.join('temp', key)
    os.mkdir(path)
    filepath = os.path.join(path, filename)
    f.save(filepath)
    return key, filename

#/upload route
@app.route('/upload', methods=['POST'])
def upload():
    if not session.get('id'):
        return redirect('/')
    #get the uploaded file or redirect to http://host/
    if 'file' in request.files:
        f = request.files['file']
    else:
        return redirect("/")
    #allowed_file checks that the extension is in util.FORMATS
    if allowed_file(f.filename):
        #save the file internally in the \temp folder and record a timeout for the file
        key, file_name = record_and_save(f)
        #if the metadata is valid, process the file
        file_path = os.path.join("temp", key, file_name)
        if metadata_are_valid(file_path):
            library.add_song(file_path, delete = True)
            os.rmdir(os.path.join('temp', key))
            return redirect("/")
        else: #get additional info from uploader
            return redirect("/edit_upload?key=%s&filename=%s" % (key, file_name))
    else:
        print f.filename
        return redirect("/?error=extension")

#package up a song's metadata for the /edit_upload form
def package_metadata(path):
    metadata = get_song_info(path)
    packaged = []
    for datum, friendly in (('title', 'title'),
                            ('album', 'album'),
                            ('artist', 'album artist'),
                            ('track_performer', 'track artist')):
        packaged.append({"friendly_name" : friendly,
                          "name"          : datum,
                          "value"         : metadata[datum],
                          "required"      : datum in REQUIRED_METADATA})
    return packaged

#check if metadata is valid (really just checks if the REQUIRED_METADATA are present
def metadata_are_valid(path):
    info = get_song_info(path)
    return all((metadatum in info and info[metadatum] \
                for metadatum in REQUIRED_METADATA
               ))

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
    elif not os.path.exists(os.path.join("temp", key, filename)):
        return NO_SUCH_FILE
    else:
        return GOOD_KEY

#edit metadata of an uploaded song
@app.route('/edit_upload')
def edit_upload():
    if not session.get('id'):
        return redirect('/')
    key = request.args.get("key")
    filename = request.args.get("filename")
    if not key or not filename or check_key(key, filename) != 0:
        return redirect("/")
    path = os.path.join("temp", key, filename)
    metadata = package_metadata(path)
    return render_template('metadata.html', metadata = metadata,
                                            key = key,
                                            filename = filename)

@app.route('/edit_upload', methods=['POST'])
def edit_upload():
    if not session.get('id'):
        return redirect('/')
    key = request.form["key"]
    filename = request.form["filename"]
    if check_key(key, filename) != 0:
        abort(400)
    path = os.path.join("temp", key, filename)
    overwrite_metadata(path,
                       artist = request.form['artist'],
                       performer = request.form['performer'],
                       album = request.form['album'],
                       title = request.form['title'])
    send_upload(key)
    return redirect("/")

@app.route('/login', methods=['GET', 'POST'])
def login():
    message = None
    logged_in = False
    if request.method == 'POST':
        if request.form['password'] == 'banana':
            session['id'] = 'admin'
            return redirect('/admin')
        else:
            message = "Bad password :("
    if session.get('id') == 'admin':
        message = "You are already logged in as admin :)"
        logged_in = True
    return render_template('login.html', message = message, logged_in = logged_in)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    del session['id']
    return redirect('/')


######## START SERVER ########

def transform_message(o):
    if isinstance(o, basestring):
        o = o.rsplit(" \"", 2)[0] + "\n"
        i = o.find(' HTTP/1.1')
        return o[:i]+o[i+9:]
    return o

#127.0.0.1 - - [2013-10-27 20:19:41] "GET /index HTTP/1.1" 200 1778 0.031812\n
def socketioserver_tf_msg(o):
    if isinstance(o, basestring):
        end = '\n' * o.endswith('\n')
        if o.find(' - - ')>=0 and o.find(' HTTP/1.1')>=0:
            return o.replace(" - - ", " - ", 1) \
                    .replace(' HTTP/1.1', '', 1) \
                    .rsplit(" ", 1)[0] \
                   + end
    return o
#127.0.0.1 - [2013-10-27 20:19:41] "GET /index" 200 1778\n

def chop_message(o):
    o = str(o)
    end = '\n' * o.endswith('\n')
    o = "\n".join(map(lambda x: x[:min(80, len(x))], o.splitlines()))
    return o + end

def run():
    ip_addr = socket.gethostbyname(socket.gethostname())
    print "Listening on %s:%d" % (ip_addr, 5000 if DEBUG else 80)
    log = WriteWrapper(sys.stdout, socketioserver_tf_msg)
    server = SocketIOServer(("", 5000 if DEBUG else 80),
                            app,
                            resource="socket.io",
                            log = log)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        disconnect()
        print " Server Killed"

def disconnect():
    playlist.conn.close()
    library.conn.close()

if __name__ == "__main__":
    run()
