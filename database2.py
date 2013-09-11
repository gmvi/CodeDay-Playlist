import json, md5, os, shutil, sqlite3, sys, threading, time
if 'modules' not in sys.path: sys.path.append('modules')
from flask import Flask, Response, request, abort
import util, organize

# Ignore database files when checking for external changes to the library's
# folder structure.
IGNORE = ["cdp.db", "cdp.db-journal"]

PRETTYPRINT = True

DEBUG = True

######## JSON SETUP ########

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            return o.to_json()
        except AttributeError:
            json.JSONEncoder.default(self, o)
if PRETTYPRINT:
    encoder = JSONEncoder(sort_keys=True, indent=2, separators=(',', ': '))
else:
    encoder = JSONEncoder()

######## UTILITY FUNCTIONS ########

def WHERE(**kwargs):
    where = " WHERE"
    values = []
    for key in kwargs:
        value = kwargs[key]
        if value != None:
            if type(value) in (list, tuple):
                where += " %s IN ? AND" % key
            else:
                where += " %s = ? AND" % key
            values.append(value)
    if len(values) == 0: return "", values
    else: return where[:-4], values

def cull_dict(dictionary):
    for key in dictionary:
        if dictionary[key] == None:
            del dictionary[key]
    return dictionary

######## DATABASE DECLARATION ########

SETUP = """
CREATE TABLE songs (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    track_performer TEXT,
                    album_id INTEGER, artist_id INTEGER,
                    path TEXT,
                    UNIQUE (name, album_id, artist_id),
                    FOREIGN KEY (artist_id) REFERENCES artists (id),
                    FOREIGN KEY (album_id) REFERENCES albums (id));
CREATE INDEX tracknameindex ON songs (name);
CREATE INDEX trackalbumindex ON songs (album_id);
CREATE INDEX trackartistindex ON songs (artist_id);

CREATE TABLE artists (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE INDEX artistnameindex ON artists (name);

CREATE TABLE albums (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                     artist_id INTEGER,
                     UNIQUE (artist_id, name),
                     FOREIGN KEY (artist_id) REFERENCES artists (id));
CREATE INDEX albumnameindex ON albums (name);
CREATE INDEX albumartistindex ON albums (artist_id);

CREATE TABLE fsrecords (path TEXT PRIMARY KEY, size INTEGER, checked BOOLEAN);

CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE taglinks (id INTEGER PRIMARY KEY, song_id INTEGER NOT NULL,
                       tag_id INTEGER NOT NULL,
                       FOREIGN KEY (song_id) REFERENCES songs (id),
                       FOREIGN KEY (tag_id) REFERENCES tags (id),
                       UNIQUE (song_id, tag_id));
CREATE INDEX songlinksindex ON taglinks (song_id);

CREATE TABLE globals (key TEXT PRIMARY KEY, value GLOB);
"""
CLEAR = """
DELETE FROM songs;
DELETE FROM artists;
DELETE FROM albums;
DELETE FROM fsrecords;
DELETE FROM taglinks;
"""
DROP_ALL = """
DROP TABLE songs;
DROP TABLE artists;
DROP TABLE albums;
DROP TABLE fsrecords;
DROP TABLE taglinks;
DROP TABLE globals;
"""

######## DATABASE CONNECTION AND SETUP ########

def connect(app_ = None):
    global app, conn, cur
    app = app_
    exists = os.path.exists('cdp.db')
    conn = sqlite3.connect('cdp.db', check_same_thread = False)
    cur = conn.cursor()
    if not exists:
        cur.executescript(SETUP)
        rebuild()
    if app:
        add_url_rules(app)

def rebuild():
    if os.path.exists('music') and os.listdir('music'):
        try:
            os.rename('music', 'temp/music')
        except WindowsError:
            time.sleep(.5)
            os.rename('music', 'temp/music')
    tagdict = {}
    cur.execute("SELECT id, name, album_id, artist_id FROM songs")
    for id, name, album, artist in cur.fetchall():
        cur.execute("SELECT tag_id FROM taglinks WHERE song_id = ?", (id,))
        tags = [i[0] for i in cur]
        tagdict[name, album, artist] = tags
    cur.executescript(CLEAR)
    if os.path.exists('temp/music'):
        errors = add_path('temp/music', delete = True)
        print 'errors: ' + str(errors)
    update_fsrecords('music')
    for (name, album, artist), tagid in tagdict.iteritems():
        artist_id = Artist.get_id(artist)
        album_id = Album.get_id(album, artist_id)
        cur.execute("SELECT id FROM songs WHERE name = ? AND album_id = ? AND artist_id = ? LIMIT 1",
                    (name, album_id, artist_id))
        result = cur.fetchone()
        if result:
            cur.execute("INSERT INTO taglinks (song_id, tag_id) VALUES (?,?)", (result[0], tagid))
    conn.commit()

def scan(wait_seconds = 0.1):
    try:
        _scan("music", wait_seconds)
        cur.execute("SELECT path FROM fsrecords WHERE checked = 0 LIMIT 1")
        row = cur.fetchone()
        if row:
            path = row[0]
            node_type = "directory" if os.path.isdir(path) else "file"
            raise FSChangedException("Missing %s: %s" % (node_type, path))
        cur.execute("UPDATE fsrecords SET checked = 0")
        conn.commit()
    except FSChangedException as e:
        print "[ERROR] " + e.message
        print "Library files have been modified outside of this program!"
        raw_input("[ENTER] to rebuild library (may fuck with http client, and will clear playlist)")
        rebuild()

def add_song(path, delete = False):
    if os.path.isdir(path):
        raise ValueError("path must be file, not directory")
    elif os.path.splitext(path)[1] not in util.FORMATS:
        raise ValueError("filetype not supported: %s" % path)
    id = add_song_record(*get_song_info(path))
    file_path, e = organize.moveFile(path, 'music', delete)
    if e:
        Song.delete(id)
        raise e
    update_fsrecord(file_path)
    pnode = os.path.split(file_path)[0]
    if pnode != 'music':
        update_fsrecord(pnode)
        pnode = os.path.split(file_path)[0]
        if pnode != 'music':
            update_fsrecord(pnode)
    conn.commit()

# the following are helper functions and may make changes to the database
# without commiting them.

def add_path(path, delete = False, errors = []):
    if os.path.isdir(path):
        for node in os.listdir(path):
            node = os.path.join(path, node)
            errors += add_path(node, delete, errors)
        if delete and not os.listdir(path):
            os.rmdir(path)
    elif os.path.splitext(path)[1] in util.FORMATS:
        try:
            id = add_song_record(*get_song_info(path))
        except Duplicate as e:
            errors += (path, e),
            return errors
        file_path, e = organize.moveFile(path, "music", delete)
        if e:
            Song.delete(id)
            errors += (path, e)
            return errors
        else:
            Song.update(id, path = file_path)
    return errors

class Duplicate(Exception): pass
def add_song_record(name, album, track_performer, artist, size):
    cur.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)",
                (artist,))
    cur.execute("SELECT id FROM artists WHERE name = ?",
                (artist,))
    artist_id = cur.fetchone()[0]
    
    cur.execute("INSERT OR IGNORE INTO albums (name, artist_id) VALUES (?, ?)",
                (album, artist_id))
    cur.execute("SELECT id FROM albums WHERE name = ? and artist_id = ?",
                (album, artist_id))
    album_id = cur.fetchone()[0]

    #TODO: check for duplicate
    cur.execute("INSERT INTO songs (name, album_id, track_performer, artist_id, size) VALUES (?,?,?,?,?)",
                (name, album_id, track_performer, artist_id, size))
    return cur.lastrowid
    
def get_song_info(path):
    tags = util.get_metadata(path)
    track_performer = tags['artist']
    artist = tags['performer'] or track_performer
    album = tags['album']
    name = tags['title'] or os.path.splitext(os.path.split(path)[1])[0]
    return (name, album, track_performer, artist, os.path.getsize(path))

def update_fsrecords(path):
    update_fsrecord(path)
    if os.path.isdir(path):
        for node in os.listdir(path):
            update_fsrecords(os.path.join(path, node))

def update_fsrecord(path):
    size = os.path.getsize(path) if os.path.isfile(path) else None
    cur.execute("INSERT OR REPLACE INTO fsrecords VALUES (?, ?, ?)",
                (path, size, None))

def remove_fsrecord(path):
    cur.execute("DELETE FROM fsrecords WHERE path = ?", (path,))

class FSChangedException(Exception): pass
def _scan(path, wait):
    isdir = os.path.isdir(path)
    cur.execute("SELECT * FROM fsrecords WHERE path = ? LIMIT 1", (path,))
    row = cur.fetchone()
    if not row:
        node_type = "directory" if isdir else "file"
        raise FSChangedException("Unexpected %s: %s" % (node_type, path))
    cur.execute("UPDATE fsrecords SET checked = 1 WHERE path = ?", (path,))
    if isdir:
        for node in os.listdir(path):
            if wait: time.sleep(wait)
            _scan(os.path.join(path, node), wait)
    else:
        if row[1] != os.path.getsize(path):
            raise FSChangedException("File changed: %s" % path)

######## CLASSES, GETTERS, AND UPDATERS ########

class Query():
    def __init__(self):
        self.artists = None
        self.albums = None
        self.songs = None

    def to_json(self):
        d = {}
        if self.artists:
            d['artists'] = self.artists
        if self.albums:
            d['albums'] = self.albums
        if self.songs:
            d['songs'] = self.songs
        return d

    @classmethod
    def artists(Cls, name = None):
        self = Cls()
        if name:
            cur.execute("SELECT * FROM artists WHERE name = ?", (name,))
        else:
            cur.execute("SELECT * FROM artists")
        self.artists = [ShortArtist(*tup) for tup in cur.fetchall()]
        return self

    @classmethod
    def albums(Cls, name = None, artist = None):
        self = Cls()
        if artist: artist = Artist.get_id(artist)
        where, values = WHERE(name = name, artist = artist)
        cur.execute("SELECT id, name FROM albums" + where, values)
        self.albums = [ShortAlbum(*tup) for tup in cur.fetchall()]
        return self
    
    @classmethod
    def songs(Cls, name = None, album = None, artist = None, track_performer = None):
        self = Cls()
        if artist: artist = Artist.get_id(artist)
        if album: album = Album.get_ids(album)
        where, values = WHERE(name = name, album = album, artist = artist, track_performer = track_performer)
        cur.execute("SELECT id, name FROM songs" + where, values)
        self.songs = [ShortSong(*tup) for tup in cur.fetchall()]
        return self

class Item():
    def __init__(self, id, name):
        self.id = id
        self.name = name

    def to_json(self):
        return {"id" : self.id,
                "name" : self.name}

class ShortArtist(Item):
    @classmethod
    def get(Cls, id):
        cur.execute("SELECT name FROM artists WHERE id = ?", (id,))
        name = cur.fetchone()
        if name:
            return Cls(id, name[0])
        
class ShortAlbum(Item):
    @classmethod
    def get(Cls, id):
        cur.execute("SELECT name FROM albums WHERE id = ?", (id,))
        name = cur.fetchone()
        if name:
            return Cls(id, name[0])
        
class ShortSong(Item):
    @classmethod
    def get(Cls, id):
        cur.execute("SELECT name FROM songs WHERE id = ?", (id,))
        name = cur.fetchone()
        if name:
            return Cls(id, name[0])

class Song(Item):
    def __init__(self, id, name, track_performer, album, artist, path, size):
        Item.__init__(self, id, name)
        self.album = album
        self.artist = artist
        self.track_performer = track_performer
        self.path = path
        self.change_alerted = False

    def __repr__(self):
        return "Song(id = %s)" % self.id
        
    def check_fs(self):
        return os.path.exists(self.rel_path) \
               and os.path.getsize(self.rel_path) == self.size

    def to_json(self):
        return {"id" : self.id,
                "name" : self.name,
                "album" : self.album,
                "artist" : self.artist,
                "track_performer" : self.track_performer}

    @classmethod
    def get(Cls, id):
        cur.execute("SELECT * FROM songs WHERE id = ?", (id,))
        row = cur.fetchone()
        if not row: return
        id, name, track_performer, album, artist, path, size = row
        if album: album = ShortAlbum.get(album)
        if artist: artist = ShortArtist.get(artist)
        return Cls(id, name, track_performer, album, artist, path, size)

    @staticmethod
    def update(id, **kwargs):
        if not kwargs: return False
        statement = "UPDATE songs SET"
        values = []
        for key, value in kwargs.iteritems():
            statement += " %s = ?" % key
            values.append(value)
        values.append(id)
        cur.execute(statement + " WHERE id = ?", values)

    @staticmethod
    def get_tags(id):
        cur.execute("SELECT tag_id FROM taglinks WHERE song_id = ?", (id,))
        return [i[0] for i in cur.fetchall()]

    @staticmethod
    def update_tags(id, tags = []):
        cur.execute("DELETE FROM taglinks WHERE song_id = ?", (id,))
        for tag in tags:
            cur.execute("INSERT OR IGNORE INTO taglinks (song_id, tag_id) VALUES (?, ?)", (id, tag))
        conn.commit()

    @staticmethod
    def delete(id):
        cur.execute("SELECT artist_id, album_id, path FROM songs WHERE id = ?", (id,))
        row = cur.fetchone()
        if not row: return
        print "row == " + str(row)
        artist_id, album_id, path = row
        Song.update_tags(id)
        cur.execute("DELETE FROM songs WHERE id = ?", (id,))
        #remove artist and album if no longer linked to by any songs
        cur.execute("SELECT EXISTS (SELECT 1 FROM songs WHERE album_id = ?)", (album_id,))
        if not cur.fetchone()[0]:
            cur.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        cur.execute("SELECT EXISTS (SELECT 1 FROM songs WHERE artist_id = ?)", (artist_id,))
        if not cur.fetchone()[0]:
            cur.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
        os.remove(path) #remove song
        remove_fsrecord(path)
        path = os.path.split(path)[0]
        if path and not os.listdir(path) and path != 'music':
            os.rmdir(path) #remove album folder
            remove_fsrecord(path)
            path = os.path.split(path)[0]
            if path and not os.listdir(path) and path != 'music':
                os.rmdir(path) #remove artist folder
                remove_fsrecord(path)
        conn.commit()

class Artist(Item):
    def __init__(self, id, name, albums, songs):
        Item.__init__(self, id, name)
        self.albums = [ShortAlbum(*tup) for tup in albums]
        self.songs = [ShortSong(*tup) for tup in songs]

    def to_json(self):
        return {"id" : self.id,
                "name" : self.name,
                "albums" : self.albums}

    @classmethod
    def get(Cls, id):
        cur.execute("SELECT name FROM artists WHERE id = ? LIMIT 1", (id,))
        row = cur.fetchone()
        if not row: return
        name, = row
        cur.execute("SELECT id, name FROM albums WHERE artist_id = ?", (id,))
        albums = cur.fetchall()
        cur.execute("SELECT id, name FROM songs WHERE artist_id = ? and album_id ISNULL", (id,))
        songs = cur.fetchall()
        return Cls(id, name, albums, songs)

    @staticmethod
    def get_id(name):
        cur.execute("SELECT id FROM artists WHERE name = ?", (name,))
        id = cur.fetchone()
        if id: return id[0]
    

class Album(Item):
    def __init__(self, id, name, artist, songs):
        Item.__init__(self, id, name)
        if artist: self.artist = ShortArtist.get(artist)
        else: self.artist = None
        self.songs = [ShortSong(*tup) for tup in songs]

    def to_json(self):
        return {"id" : self.id,
                "name" : self.name,
                "artist" : self.artist,
                "songs" : self.songs}

    @classmethod
    def get(Cls, id):
        cur.execute("SELECT name, artist_id FROM albums WHERE id = ? LIMIT 1", (id,))
        row = cur.fetchone()
        if not row: return
        name, artist = row
        cur.execute("SELECT id, name FROM SONGS WHERE album_id = ?", (id,))
        songs = cur.fetchall()
        return Cls(id, name, artist, songs)

    @staticmethod
    def get_id(name, artist_id):
        cur.execute("SELECT id FROM albums WHERE name = ? AND artist_id = ?",
                    (name, artist_id))
        row = cur.fetchone()
        if row:
            return row[0]
    
    @staticmethod
    def get_ids(name):
        cur.execute("SELECT id FROM albums WHERE name = ?", (name,))
        return [i[0] for i in cur.fetchall()]

def get_folderhash(path):
    mr_itchy = md5.md5()
    contents = os.listdir(path)
    for node in contents:
        if node not in IGNORE:
            mr_itchy.update(node)
    return mr_itchy.hexdigest()

def jsonify(data):
    if data == None:
        abort(404)
    else:
        return Response(encoder.encode(data),
                        mimetype = 'application/json')

routes = []

def route(location, *methods, **kwargs):
    def decorator(func):
        global routes
        if 'methods' not in kwargs and methods:
            kwargs['methods'] = methods
        routes.append(((location, func.__name__, func), kwargs))
        return func
    return decorator

@route('/library')
def get_artists():
    return jsonify(Query.artists())

@route('/library/artist')
def get_artists_query():
    name = request.args.get("name")
    return jsonify(Query.artists(name))

@route('/library/artist/<int:id>')
def get_artist(id):
    return jsonify(Artist.get(id))

@route('/library/album')
def get_albums():
    name = request.args.get("name")
    return jsonify(Query.albums(name))

@route('/library/album/<int:id>')
def get_album(id):
    return jsonify(Album.get(id))

song_keys = ['name', 'artist', 'album', 'track_performer']

@route('/library/song')
def get_songs():
    restrictions = {}
    for key in song_keys:
        if request.args.get(key) != None:
            restrictions[key] = request.args.get(key)
    return jsonify(Query.songs(**restrictions))

@route('/library/song/<int:id>')
def get_song(id):
    return jsonify(Song.get(id))

@route('/library/song/<int:id>', 'PATCH')
def update_song(id):
    changes = {}
    for key in song_keys:
        changes[key] = request.args.get(key)
    Song.update(id, **cull_dictionary(changes))
    return "200 OK"

@route('/library/song/<int:id>', 'DELETE')
def delete_song(id):
    Song.delete(id)
    return "200 OK"

@route('/library/song/<int:id>/tags')
def get_song_tags(id):
    return jsonify(Song.get_tags(id))

@route('/library/song/<int:id>/tags', 'PUT')
def update_song_tags(id):
    cur.execute("SELECT id FROM tags")
    valid_tags = [row[0] for row in cur]
    tags = request.form['tags']
    tags = tags.split(',')
    for i in xrange(len(tags)-1, -1, -1):
        try:
            tags[i] = int(tags[i])
        except:
            del tags[i]
        if tags[i] not in valid_tags:
            abort(400)
    Song.update_tags(id, tags)
    return "200 OK"

@route('/library/song/<int:id>/tags', 'DELETE')
def remove_song_tags(id):
    Song.update_tags(id)
    return "200 OK"

@route('/library/tags')
def get_tags():
    cur.execute("SELECT * FROM tags")
    return jsonify([{'id':row[0],'name':row[1]} for row in cur])

@route('/library/tags', 'POST')
def new_tag():
    name = request.form['name']
    cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
    conn.commit()
    return '200 OK'

@route('/library/tags/<int:id>', 'DELETE')
def del_tag(id):
    cur.execute("DELETE FROM taglinks WHERE tag_id = ?", (id,))
    cur.execute("DELETE FROM tags WHERE id = ?", (id,))
    conn.commit()
    return '200 OK'

@route('/api/rebuild_database', 'POST')
def rebuild_endpoint():
    rebuild()
    return '200 OK'

def add_url_rules(app):
    for args, kwargs in routes:
        app.add_url_rule(*args, **kwargs)

def run():
    app = Flask(__name__)
    app.debug = DEBUG
    connect(app)
    app.run()

if __name__ == '__main__':
    if 'idlelib' not in sys.modules:
        run()
    else:
        connect()
