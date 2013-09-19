import sqlite3, sys, time
from threading import Timer, Lock

if 'modules' not in sys.path: sys.path.append('modules')
from flask import Flask, Response, request, abort, send_file

import util, library
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

class Playlist():
    
    GLOBALS = (('length', 0),
               ('current', None))
    
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
        return self.__get_global('current')
    @current_index.setter
    def current_index(self, value):
        self.__set_global('current', value)
        self.conn.commit()

    def initialize(self):
        self.cur.execute('SELECT EXISTS (SELECT * FROM playlist WHERE i = ?)',
                         (0,))
        if not self.cur.fetchone()[0]:
            raise ValueError("playlist empty")
        self.current_index = 0
        self.current_length = library.Song.get(playlist.get_current().song_id).length

    def get(self, id):
        self.cur.execute('SELECT * FROM playlist WHERE id = ?', (id,))
        row = self.cur.fetchone()
        return row and PlaylistEntry(*row)

    def get_current(self):
        self.cur.execute('SELECT * FROM playlist WHERE i = ? LIMIT 1', (self.current_index,))
        row = self.cur.fetchone()
        return row and PlaylistEntry(*row)
        
    def insert(self, song_id, before_playlist_id = None):
        if not library.Song.exists(song_id):
            raise ValueError("song not found")
        if before_playlist_id != None:
            self.cur.execute('SELECT i FROM playlist WHERE id = ? LIMIT 1',
                             (before_playlist_id,))
            row = self.cur.fetchone()
            if row == None: raise ValueError("invalid PlaylistEntry ID")
            index = row[0]
            if index <= self.current_index: raise IndexError()
            self.cur.execute('UPDATE playlist SET i = i + 1 WHERE i >= ?',
                             (index,))
        else:
            index = len(self)
        self.cur.execute('INSERT INTO playlist (i, song_id) VALUES (?, ?)',
                         (index, song_id))
        playlist_id = self.cur.lastrowid
        self.__set_global('length', len(self) + 1)
        self.conn.commit()
        return playlist_id

    def remove(self, playlist_id):
        self.cur.execute('SELECT i FROM playlist WHERE id = ? LIMIT 1',
                         (playlist_id,))
        row = self.cur.fetchone()
        if row == None: raise ValueError(None, 404)
        index = row[0]
        if index <= self.current_index: raise IndexError("Cannot remove", 405)
        self.cur.execute('DELETE FROM playlist WHERE id = ?', (playlist_id,))
        self.cur.execute('UPDATE playlist SET i = i - 1 WHERE i > ?',
                         (index,))
        self.__set_global('length', len(self) - 1)
        self.conn.commit()

    def advance(self):
        if self.current_index + 1 == len(self):
            raise Exception()
        self.current_index += 1
        self.current_length = library.Song.get(playlist.get_current().song_id).length

    def rewind(self):
        if self.current_index == 0:
            raise Exception() #TODO: What Exception?
        self.current_index -= 1
        self.current_length = library.Song.get(playlist.get_current().song_id).length

    def move_to(self, id):
        self.cur.execute('SELECT i FROM playlist WHERE id = ?', (id,))
        row = self.cur.fetchone()
        if row:
            self.current_index = row[0]
        else:
            raise ValueError("can't find playlist ID")
        self.current_length = library.Song.get(playlist.get_current().song_id).length

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
                             ('playlist_id', self.id),
                             ('index',       self.index),
                             ('song_id',     self.song_id)
                            ))

    def __repr__(self):
        return "%s(%s, %s, %s)" % (self.__class__.__name__,
                           self.id,
                           self.index,
                           self.song_id)

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
        self.timer = None
        self.lock = Lock()

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

    def _set_timer(self):
        self._cancel_timer()
        self.timer = Timer(self.time + playlist.current_length \
                            - self.position - time.time(),
                           self._trigger_next_track)
        self.timer.start()

    def _cancel_timer(self):
        if self.timer != None:
            self.timer.cancel()
            self.timer = None

    def _trigger_next_track(self):
        try:
            self.playlist.advance()
        except:
            self.stop()
        else:
            self.set_pos(0)
    
    def play(self):
        self.lock.acquire()
        if self.state == PlaylistController.PLAYING: return
        if self.state == PlaylistController.NONE:
            self._initialize()
        self.state = PlaylistController.PLAYING
        self.time = time.time() # + give clients time to receive signal?
        self._set_timer()
        self.lock.release()

    def pause(self):
        self.lock.acquire()
        now = time.time()
        if self.state == PlaylistController.PAUSED: return
        if self.state == PlaylistController.NONE:
            self._initialize()
        self.position = self.get_position(now)
        self.state = PlaylistController.PAUSED
        self.time = None
        self._cancel_timer()
        self.lock.release()

    def stop(self):
        self.lock.acquire()
        now = time.time()
        if self.state == PlaylistController.STOPPED: return
        if self.state == PlaylistController.NONE:
            self._initialize()
        self.position = self.get_position(now)
        self.state = PlaylistController.STOPPED
        self.position = 0
        self.time = None
        self._cancel_timer()
        self.lock.release()

    def set_pos(self, pos, when = None):
        self.lock.acquire()
        if when == None:
            when = time.time()
        self.time = when
        self._cancel_timer()
        self.position = pos
        if self.state == PlaylistController.NONE:
            self._initialize()
            self.state = PlaylistController.PAUSED
        if self.state == PlaylistController.STOPPED:
            self.state = PlaylistController.PAUSED
        self._set_timer()
        self.lock.release()

playlist = Playlist(PLAYLIST_DB_LOCATION)
controller = PlaylistController(playlist)

#### FLASK ROUTING ####

def jsonify(data, null = 404):
    if null and data == None:
        abort(null)
    else:
        return Response(util.encode(data),
                        mimetype = 'application/json')

def route(location, *methods, **kwargs):
    def decorator(func):
        global routes
        try:
            routes
        except NameError:
            routes = []
        if 'methods' not in kwargs and methods:
            kwargs['methods'] = methods
        routes.append(((location, func.__name__, func), kwargs))
        return func
    return decorator

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
#@errors
def insert_endpoint():
    before_id = request.form.get('before')
    song_id = request.form['song']
    playlist_id = playlist.insert(song_id, before_id)
    return jsonify(playlist_id)

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
    return jsonify(playlist.get_current(), False)

@route("/playlist/current/data")
def data_endpoint():
    song = library.Song.get(playlist.get_current().song_id)
    return send_file(song.path, song.mime)

@route("/playlist/current/position")
def position_endpoint():
    now = time.time()
    translate = {0:'none',1:'stopped',2:'paused',3:'playing'}
    data = (('state', translate[controller.state]),
            ('time', now),
            ('position', controller.get_position(now)))
    return jsonify(dict_factory(data))

@route("/api/controls/play", "POST")
@errors
def play_endpoint():
    controller.play()
    return "200 OK"

@route("/api/controls/pause", "POST")
@errors
def pause_endpoint():
    controller.pause()
    return "200 OK"

@route("/api/controls/stop", "POST")
@errors
def stop_endpoint():
    controller.stop()
    return "200 OK"

#### MAIN ####

def run():
    app = Flask(__name__)
    app.debug = DEBUG
    library.attach(app)
    attach(app)
    app.run()

if __name__ == '__main__' and 'idlelib' not in sys.modules:
    run()
