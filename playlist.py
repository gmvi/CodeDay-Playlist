import re, sqlite3, sys, time
from threading import Timer, RLock

if 'modules' not in sys.path: sys.path.append('modules')
from flask import Flask, Response, request, abort, send_file
from socketio import socketio_manage

from util import encode, send_file_partial, BroadcastNamespace
import library
from settings import DEBUG, PLAYLIST_DB_LOCATION

if DEBUG:
    from collections import OrderedDict as dict_factory
else:
    dict_factory = dict

def attach(app):
    for args, kwargs in routes:
        app.add_url_rule(*args, **kwargs)

#### DATABASE SCRIPTS ####
        
SETUP = """
CREATE TABLE IF NOT EXISTS playlist (id INTEGER PRIMARY KEY, i INTEGER, song_id INTEGER);
CREATE TABLE IF NOT EXISTS globals (key TEXT PRIMARY KEY, value GLOB);
"""

CLEAR = """
DELETE FROM playlist;
DELETE FROM globals;
"""

DROP = """
DROP TABLE IF EXISTS playlist;
DROP TABLE IF EXISTS globals;
"""

#### CLASSES ####

class TrackInfoNamespace(BroadcastNamespace):
    record = None
   
    @classmethod
    def update(cls, track):
        cls.record = track
        cls.broadcast('track', cls.record)

    @classmethod
    def clear_track(cls):
        cls.update(None)
       
    def on_subscribe(self):
        self.emit('track', self.record)

class PlaylistNamespace(BroadcastNamespace): pass
#still need to add these

class Playlist():
    
    GLOBALS = (('length', 0),)
    
    def __init__(self, database):
        if type(database) == sqlite3.Connection:
            self.conn = database
            self.cur = self.conn.cursor()
        elif isinstance(database, basestring):
            self.conn = sqlite3.connect(database,
                                        check_same_thread = False)
            self.cur = self.conn.cursor()
        else:
            raise ValueError()
        self.cur.executescript(SETUP)
        for key, value in Playlist.GLOBALS:
            self.__set_global(key, value, overwrite = False)
        self._current_index = 0
        self._load_current()

    def __len__(self):
        return self.__get_global('length')

    def __get_global(self, key):
        self.cur.execute("SELECT value FROM globals WHERE key = ?", (key,))
        row = self.cur.fetchone()
        return row and row[0]

    def __set_global(self, key, value, overwrite = True):
        if overwrite:
            self.cur.execute("INSERT OR REPLACE INTO globals VALUES (?,?)", (key, value))
        else:
            self.cur.execute("INSERT OR IGNORE INTO globals VALUES (?,?)", (key, value))

    @property
    def current_index(self):
        return self._current_index

    def set_current_index(self, value):
        self._current_index = value
        self._load_current()
        TrackInfoNamespace.update(self.current_song.to_json())

    def initialize(self):
        self.cur.execute('SELECT EXISTS (SELECT * FROM playlist WHERE i = ?)',
                         (0,))
        if not self.cur.fetchone()[0]:
            raise ValueError("playlist empty")
        self.set_current_index(0)

    def get(self, id):
        self.cur.execute('SELECT * FROM playlist WHERE id = ?', (id,))
        row = self.cur.fetchone()
        return row and PlaylistEntry(*row)

    def _load_current(self):
        self.cur.execute('SELECT song_id FROM playlist WHERE i = ? LIMIT 1', (self.current_index,))
        row = self.cur.fetchone()
        if row == None:
            self.current_song = None
        song = library.Song.get(row[0])
        song.load_data()
        self.current_song = song
        
    def insert(self, song_id, index = None):
        if not library.Song.exists(song_id):
            raise ValueError("song not found", 403)
        if index != None:
            if index <= 0 or index > len(self):
                raise IndexError("out of bounds", 403)
            self.cur.execute('UPDATE playlist SET i = i + 1 WHERE i >= ?',
                             (index,))
        else:
            index = len(self)
        self.cur.execute('INSERT INTO playlist (i, song_id) VALUES (?, ?)',
                         (index, song_id))
        entry_id = self.cur.lastrowid
        self.__set_global('length', len(self) + 1)
        self.conn.commit()
        return entry_id

    def remove(self, entry_id):
        self.cur.execute('SELECT i FROM playlist WHERE id = ? LIMIT 1',
                         (entry_id,))
        row = self.cur.fetchone()
        if row == None: raise ValueError(None, 404)
        index = row[0]
        if index <= self.current_index: raise IndexError("Cannot remove", 405)
        self.cur.execute('DELETE FROM playlist WHERE id = ?', (entry_id,))
        self.cur.execute('UPDATE playlist SET i = i - 1 WHERE ? < i',
                         (index,))
        self.__set_global('length', len(self) - 1)
        self.conn.commit()

    def move_entry(self, entry_id, before_entry_id = None):
        self.cur.execute('SELECT i FROM playlist WHERE id = ? LIMIT 1',
                          (entry_id,))
        row = self.cur.fetchone()
        if row == None: raise ValueError(None, 404)
        old_index = row[0]
        if before_entry_id != None:
            self.cur.execute('SELECT i FROM playlist WHERE id = ? LIMIT 1',
                              (before_entry_id,))
            row = self.cur.fetchone()
            if row == None: raise ValueError(None, 404)
            new_index = row[0]
        else:
            new_index = row[0]
        if not (self.current_index < old_index and \
                self.current_index < new_index):
            raise IndexError(None, 405)
        self.cur.exeucte('UPDATE playlist SET i = i - 1 WHERE ? < i <= ?',
                         (old_index, new_index))
        self.cur.exeucte('UPDATE playlist SET i = i + 1 WHERE ? > i >= ?',
                         (old_index, new_index))
        self.cur.execute('UPDATE playlist SET i = ? WHERE id = ?',
                         (new_index, entry_id))
        self.conn.commit()

    def has_next(self):
        return self.current_index+1 < len(self)

    def advance(self):
        next = self.current_index + 1
        if next == len(self):
            raise IndexError("", 403)
        self.set_current_index(next)
        TrackInfoNamespace.update(self.current_song.to_json())
    
    def has_prev(self):
        return self.current_index > 0

    def rewind(self):
        if self.current_index == 0:
            raise IndexError("", 403) #TODO: What Exception?
        self.set_current_index(self.current_index - 1)
        TrackInfoNamespace.update(self.current_song.to_json())

    def move_to(self, id):
        self.cur.execute('SELECT i FROM playlist WHERE id = ?', (id,))
        row = self.cur.fetchone()
        if row:
            self.set_current_index(row[0])
            TrackInfoNamespace.update(self.current_song.to_json())
        else:
            raise ValueError("can't find playlist ID")

    def to_json(self):
        self.cur.execute('SELECT * FROM playlist ORDER BY i')
        entries = [PlaylistEntry(*row) for row in self.cur]
        return dict_factory((
                             ('list', entries),
                             ('current', self.current_index)
                            ))

class PlaylistEntry():
    def __init__(self, id, index, song_id):
        self.id = id
        self.index = index
        self.song_id = song_id

    def to_json(self):
        return dict_factory((
                             ('entry_id', self.id),
                             ('index',       self.index),
                             ('song_id',     self.song_id)
                            ))

    def __repr__(self):
        return "%s(%s, %s, %s)" % (self.__class__.__name__,
                           self.id,
                           self.index,
                           self.song_id)

class ControlNamespace(BroadcastNamespace):
    def on_subscribe(self, message=None):
        self.emit('subscribe', 'subscribed')

class PlaylistController():
    
    NONE = 0
    STOPPED = 1
    PAUSED = 2
    PLAYING = 3
    
    def __init__(self, playlist):
        self.state = PlaylistController.NONE
        self.position = None
        self.time = None
        self.playlist = playlist
        self._timer = None
        self._lock = RLock()

    def _initialize(self):
        self.playlist.initialize()
        self.position = 0

    def get_position(self, when = None):
        if when == None: when = time.time()
        if self.state == PlaylistController.NONE:
            return None
        if self.state == PlaylistController.STOPPED:
            return 0
        if self.state == PlaylistController.PAUSED:
            return round(self.position, 3)
        if self.state == PlaylistController.PLAYING:
            return round(self.position + when - self.time, 3)

    def get_duration(self):
        return self.playlist.current_song and self.playlist.current_song.length

    def _set_timer(self):
        now = time.time()
        if self._timer != None:
            self._timer.cancel()
        when = self.time + self.playlist.current_song.length \
               - self.position - now
        print "timer set for " + str(when)
        self._timer = Timer(when,
                            self._trigger_next_track)
        self._timer.start()

    def _cancel_timer(self):
        print "timer cleared"
        if self._timer != None:
            self._timer.cancel()
            self._timer = None

    def _trigger_next_track(self):
        print "alarm: ",
        try:
            self.playlist.advance()
            self.set_pos(0)
            print "moveTo next track"
            ControlNamespace.broadcast('next', {'when' : self.time})
        except:
            self.stop()
            print "stopped"
    
    def play(self):
        self._lock.acquire()
        if self.state == PlaylistController.PLAYING: return
        if self.state == PlaylistController.NONE:
            self._initialize()
        if self.state == PlaylistController.STOPPED:
            TrackInfoNamespace.update(self.playlist.current_song)
        self.state = PlaylistController.PLAYING
        self.time = time.time() + 0 # + give clients time to receive signal?
        ControlNamespace.broadcast('play', {'position' : self.position,
                                            'when' : self.time})
        self._set_timer()
        self._lock.release()

    def pause(self):
        self._lock.acquire()
        now = time.time()
        if self.state == PlaylistController.PAUSED: return
        if self.state == PlaylistController.NONE:
            self._initialize()
        if self.state == PlaylistController.STOPPED:
            TrackInfoNamespace.update(self.playlist.current_song)
        self.position = self.get_position(now)
        self.state = PlaylistController.PAUSED
        self.time = None
        ControlNamespace.broadcast('pause')
        self._cancel_timer()
        self._lock.release()

    def stop(self):
        self._lock.acquire()
        if self.state == PlaylistController.STOPPED: return
        if self.state == PlaylistController.NONE:
            self._initialize()
        self.state = PlaylistController.STOPPED
        self.position = 0
        self.time = None
        print "sending message"
        ControlNamespace.broadcast('stop', 'message')
        TrackInfoNamespace.clear_track()
        self._cancel_timer()
        self._lock.release()

    def set_pos(self, pos, when = None, entry_id = None):
        if when == None: when = time.time()
        self._lock.acquire()
        self._cancel_timer()
        if entry_id: self.playlist.move_to(entry_id)
        self.time = when
        self.position = pos
        if self.state == PlaylistController.NONE:
            self._initialize()
            self.state = PlaylistController.PAUSED
        if self.state == PlaylistController.STOPPED:
            self.state = PlaylistController.PAUSED
        ControlNamespace.broadcast('position', {'position': self.position,
                                           'when' : self.time})
        self._set_timer()
        self._lock.release()

    def prev(self):
        self._lock.acquire()
        if self.playlist.has_prev():
            self._cancel_timer()
            self.playlist.rewind()
            self.position = 0
            self.time = None
            if self.state == PlaylistController.PLAYING:
                self.time = time.time()
                self._set_timer()
            ControlNamespace.broadcast('prev', {'when' : self.time})
        self._lock.release()

    def next(self):
        self._lock.acquire()
        if self.playlist.has_next():
            self._cancel_timer()
            self.playlist.advance()
            self.position = 0
            self.time = None
            if self.state == PlaylistController.PLAYING:
                self.time = time.time()
                self._set_timer()
            ControlNamespace.broadcast('next', {'when' : self.time})
        self._lock.release()

def setup():
    global conn, playlist, controller, \
           insert, remove, get_current_song
    conn = sqlite3.connect(PLAYLIST_DB_LOCATION, check_same_thread = False)
    playlist = Playlist(conn)
    insert = playlist.insert
    remove = playlist.remove
    def get_current_song():
        return playlist.current_song
    controller = PlaylistController(playlist)

#### FLASK ROUTING ####

def jsonify(data, null = 404):
    if null and data == None:
        abort(null)
    else:
        return Response(encode(data),
                        mimetype = 'application/json')

# @route may be applied to a function multiple times
def route(location, *methods, **kwargs):
    def decorator(func):
        global routes
        try: routes
        except NameError: routes = []
        if 'methods' not in kwargs and methods:
            kwargs['methods'] = methods
        try: func.routed
        except AttributeError: func.routed = 0
        desc = func.__name__ if not func.routed else \
               func.__name__ + str(func.routed+1)
        routes.append(((location, desc, func), kwargs))
        func.routed += 1
        return func
    return decorator

# @errors must be wrapped directly around a function,
# rather than around a routed function
def errors(func):
    def wrapped_func(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (IndexError, ValueError) as e:
            if len(e.args) > 1 and type(e.args[1]) == int:
                abort(e.args[1], e.args[0])
            else:
                raise e
    wrapped_func.__name__ = func.__name__
    wrapped_func.__doc__ = func.__doc__
    return wrapped_func

@route("/playlist")
def playlist_endpoint():
    return jsonify(playlist)

@route("/playlist", "POST")
@errors
def insert_endpoint():
    entry_id = request.form.get('entry_id')
    if entry_id:
        entry_id = int(entry_id)
        index = request.form.get('index')
        if index: index = int(index)
        playlist.move_entry(entry_id, index)
        return ""
    if not entry_id:
        song_id = int(request.form['song_id'])
        index = request.form.get('index')
        if index: index = int(index)
        entry_id = playlist.insert(song_id, index)
        return jsonify({'entry_id' : entry_id})

@route("/playlist/<int:id>")
def playlistentry_endpoint(id):
    return jsonify(playlist.get(id))

@route("/playlist/<int:id>", "DELETE")
@errors
def remove_endpoint(id):
    playlist.remove(id)
    return '200 OK'

@route("/playlist/current")
def current_endpoint():
    return jsonify(playlist.current_song, False)

@route("/playlist/data")
@route("/playlist/current/data")
def data_endpoint():
    song = playlist.current_song
    if not song: abort(404)
    return send_file_partial(song.path, song.mime)

@route("/playlist/datafile")
def datafile_endpoint():
    if not playlist.current_song: abort(404)
    return send_file(playlist.current_song.path, playlist.current_song.mime)

@route("/playlist/position")
@route("/playlist/current/position")
def position_endpoint():
    now = time.time()
    translate = {0:'none',
                 1:'stopped',
                 2:'paused',
                 3:'playing'}
    data = (('state', translate[controller.state]),
            ('time', now),
            ('position', controller.get_position(now)),
            ('duration', controller.get_duration()))
    return jsonify(dict_factory(data))

@route("/playlist/clear", "POST")
def reset_endpoint():
    playlist.reset()
    return "200 OK"

@route("/controls/play", "POST")
@errors
def play_endpoint():
    controller.play()
    return "200 OK"

@route("/controls/pause", "POST")
@errors
def pause_endpoint():
    controller.pause()
    return "200 OK"

@route("/controls/stop", "POST")
@errors
def stop_endpoint():
    controller.stop()
    return "200 OK"

@route("/controls/prev", "POST")
@errors
def prev_endpoint():
    controller.prev()
    return "200 OK"

@route("/controls/next", "POST")
@errors
def next_endpoint():
    controller.next()
    return "200 OK"

@route("/controls/position", "POST")
@errors
def pos_endpoint():
    position = int(request.form['position'])
    #when = request.get('time')
    controller.set_pos(position)#, when)
    return "200 OK"

#socketio endpoint
@route('/socket.io/<path:rest>')
def socketio_endpoint(rest):
    socketio_manage(request.environ, {'/playlist' : PlaylistNamespace,
                                      '/track' : TrackInfoNamespace,
                                      '/control' : ControlNamespace})

#### MAIN ####

def run():
    app = Flask(__name__)
    app.debug = DEBUG
    app.secret_key = COOKIE_SESSION_KEY
    library.attach(app)
    attach(app)
    app.run(use_reloader = False)

setup()
if __name__ == '__main__' and 'idlelib' not in sys.modules:
    run()
