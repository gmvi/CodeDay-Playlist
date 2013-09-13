import sqlite3, sys
if 'modules' not in sys.path: sys.path.append('modules')
from flask import Flask, Response, request, abort
import util, library
from settings import DEBUG

if DEBUG:
    from collections import OrderedDict as dict_factory
else:
    dict_facotry = dict

#### DATABASE DECLARATION AND CONNECTION ####

SETUP = """
CREATE TABLE playlist (id INTEGER PRIMARY KEY, i INTEGER, song_id INTEGER);
CREATE INDEX playlistindex ON playlist (i);
CREATE TABLE globals (key TEXT PRIMARY KEY, value GLOB);
INSERT INTO globals VALUES ('length', 0);
INSERT INTO globals VALUES ('current', null);
"""
CLEAR = """
DELETE FROM playlist;
DELETE FROM globals;
"""

def connect():
    global conn, cur
    conn = sqlite3.connect(':memory:', check_same_thread = False)
    cur = conn.cursor()
    cur.executescript(SETUP)

def attach(app):
    for args, kwargs in routes:
        app.add_url_rule(*args, **kwargs)

#### CLASSES ####

class Playlist():
    def __init__(self, entries):
        self.list = list(entries)

    def to_json(self):
        return dict_factory((
                             ('list', self.list),
                            ))

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, `self.list`)

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
        return "%s(%s)" % (self.__class__.__name__, self.song_id)

#### FUNCTIONS ####

def get_global(key):
    cur.execute("SELECT value FROM globals WHERE key = ?", (key,))
    row = cur.fetchone()
    return row and row[0]

def set_global(key, value):
    cur.execute("INSERT OR REPLACE INTO globals VALUES (?,?)", (key, value))

def insert(song_id, before_playlist_id = None):
    length = get_global('length')
    if before_playlist_id != None:
        cur.execute('SELECT i FROM playlist WHERE id = ? LIMIT 1',
                    (before_playlist_id,))
        row = cur.fetchone()
        if row == None: raise ValueError()
        index = row[0]
        if index <= get_global('current'): raise IndexError('index out of range')
        cur.execute('UPDATE playlist SET i = i + 1 WHERE i >= ?',
                    (index,))
    else:
        index = length
    cur.execute('INSERT INTO playlist (i, song_id) VALUES (?, ?)',
                (index, song_id))
    playlist_id = cur.lastrowid
    set_global('length', length + 1)
    conn.commit()
    return playlist_id

def remove(playlist_id):
    cur.execute('SELECT i FROM playlist WHERE id = ? LIMIT 1',
                (playlist_id,))
    row = cur.fetchone()
    if row == None: raise ValueError()
    index = row[0]
    if index <= get_global('current'): raise IndexError()
    cur.execute('DELETE FROM playlist WHERE id = ?', (playlist_id,))
    cur.execute('UPDATE playlist SET i = i - 1 WHERE i > ?',
                (index,))
    set_global('length', get_global('length') - 1)
    conn.commit()

def get_playlist():
    cur.execute('SELECT * FROM playlist ORDER BY i')
    return Playlist([PlaylistEntry(*row) for row in cur])

def get_playlist_entry(id):
    cur.execute('SELECT * FROM playlist WHERE id = ?', (id,))
    row = cur.fetchone()
    return row and PlaylistEntry(*row)
    
#### FLASK ROUTING ####

def jsonify(data):
    if data == None:
        abort(404)
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

@route("/playlist")
def playlist_endpoint():
    return jsonify(get_playlist())

@route("/playlist", "POST")
def insert_endpoint():
    before_id = request.form.get('before')
    song_id = request.form['song']
    try:
        insert(song_id, before_id)
        return '201 CREATED'
    except IndexError:
        abort(400)
    except ValueError:
        abort(404)

@route("/playlist/<int:id>")
def playlistentry_endpoint(id):
    return jsonify(get_playlist_entry(id))

@route("/playlist/<int:id>", "DELETE")
def remove_endpoint(id):
    try:
        remove(id)
        return '200 OK'
    except IndexError:
        abort(400)
    except ValueError:
        abort(404)

def run():
    app = Flask(__name__)
    app.debug = DEBUG
    library.attach(app)
    attach(app)
    app.run()

connect()
if __name__ == '__main__' and 'idlelib' not in sys.modules:
    run()
