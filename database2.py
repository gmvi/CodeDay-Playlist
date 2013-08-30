import os, sys, md5, time, json, sqlite3, shutil
if 'modules' not in sys.path: sys.path.append('modules')
from flask import Flask, Response, abort
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
    if len(values) == 0: return "", []
    else: return where[:-4], values

######## DATABASE DECLARATION ########

SETUP = """
CREATE TABLE songs (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    track_performer TEXT,
                    album_id INTEGER, artist_id INTEGER,
                    path TEXT, size INTEGER,
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

CREATE TABLE folderhashes (path TEXT PRIMARY KEY, hash TEXT);

CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE taglinks (id INTEGER PRIMARY KEY, song_id INTEGER NOT NULL,
                       tag_id INTEGER NOT NULL,
                       FOREIGN KEY (song_id) REFERENCES songs (id),
                       FOREIGN KEY (tag_id) REFERENCES tags (id),
                       UNIQUE (song_id, tag_id));
CREATE INDEX songlinksindex ON taglinks (song_id);

CREATE TABLE globals (key TEXT PRIMARY KEY, value GLOB);
"""
RESET = """
DELETE FROM songs;
DELETE FROM artists;
DELETE FROM albums;
DELETE FROM folderhashes;
DELETE FROM taglinks;
"""

######## CLASSES ########

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
            cur.execute("SELECT * FROM artists WHERE name = ?", name)
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
    def delete(id):
        cur.execute("DELETE FROM songs WHERE id = ?", (id,))

    @staticmethod
    def get_tags(id):
        cur.execute("SELECT tag_id FROM taglinks WHERE song_id = ?", (id,))
        return [i[0] for i in cur.fetchall()]

    @staticmethod
    def update_tags(id, tags = []):
        cur.execute("DELETE FROM taglinks WHERE song_id = ?", (id,))
        for tag in tags:
            cur.execute("INSERT INTO taglinks (song_id, tag_id) VALUES (?, ?)", (id, tag))
        conn.commit()

    @staticmethod
    def delete(id):
        row = cur.execute("SELECT artist_id, album_id, path FROM songs WHERE id = ?", (id,))
        if not row: return
        artist_id, album_id, path = row
        update_tags(id)
        cur.execute("DELETE FROM songs WHERE id = ?", (id,))
        #remove artist and album if no longer linked to by any songs
        cur.execute("SELECT EXISTS (SELECT 1 FROM songs WHERE album_id = ?)", (album_id,))
        if not cur.fetchone()[0]:
            cur.execute("DELETE FROM albums WHERE id = ?", (album_id,))
            cur.execute("SELECT EXISTS (SELECT 1 FROM songs WHERE artist_id = ?)", (artist_id,))
            if not cur.fetchone()[0]:
                cur.execute("DELETE FROM albums WHERE id = ?", (artist_id,))
        os.remove(path)
        path = os.path.split(path)[0]
        if path and not os.listdir(path):
            os.remove(path)
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
        cur.execute("SELECT id FROM artists WHERE name = ?", name)
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

######## DATABASE CONNECTION AND SETUP ########

def connect(app = None):
    global conn, cur
    exists = os.path.exists('cdp.db')
    conn = sqlite3.connect('cdp.db', check_same_thread = False)
    cur = conn.cursor()
    if not exists:
        cur.executescript(SETUP)
        rebuild()
    if app: add_url_rules(app)

def rebuild():
    if os.path.exists('music'):
        os.rename('music', 'temp/music')
    tagdict = {}
    cur.execute("SELECT id, name, album_id, artist_id FROM songs")
    for id, name, album, artist in cur.fetchall():
        cur.execute("SELECT tag_id FROM taglinks WHERE song_id = ?", (id,))
        tags = [i[0] for i in cur]
        tagdict[name, album, artist] = tags
    cur.executescript(RESET)
    if os.path.exists('temp/music'):
        errors = add_path('temp/music', delete = True)
        print 'errors: ' + str(errors)
    for (name, album, artist), tagid in tagdict.iteritems():
        artist_id = Artist.get_id(artist)
        album_id = Album.get_id(album, artist_id)
        cur.execute("SELECT id FROM songs WHERE name = ? AND album_id = ? AND artist_id = ? LIMIT 1",
                    (name, album_id, artist_id))
        result = cur.fetchone()
        if result:
            cur.execute("INSERT INTO taglinks (song_id, tag_id) VALUES (?,?)", (result[0], tagid))
    conn.commit()
        
def add_path(path, delete = False, errors = []):
    if os.path.isdir(path):
        update_folderhash(path)
        for node in os.listdir(path):
            node = os.path.join(path, node)
            errors += add_path(node, delete, errors)
        if delete and not os.listdir(path):
            os.rmdir(path)
    elif os.path.splitext(path)[1] in util.FORMATS:
##        try:
        id = add_song(*get_song_info(path))
##        except Exception:
##            errors += "duplicate",
##            return errors
        file_path, e = organize.moveFile(path, "music", delete)
        if e:
            errors += (path, file_path, e)
            return errors
        size = os.path.getsize(file_path)
        cur.execute("UPDATE songs SET path = ?, size = ? WHERE id = ?",
                    (file_path, size, id))
    return errors

def add_song(name, album, track_performer, artist):
    cur.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)", (artist,))
    cur.execute("SELECT id FROM artists WHERE name = ?", (artist,))
    artist_id = cur.fetchone()[0]
    cur.execute("INSERT OR IGNORE INTO albums (name, artist_id) VALUES (?, ?)", (album, artist_id))
    cur.execute("SELECT id FROM albums WHERE name = ?", (album,))
    album_id = cur.fetchone()[0]
    cur.execute("INSERT INTO songs (name, album_id, track_performer, artist_id) VALUES (?,?,?,?)",
                (name, album_id, track_performer, artist_id))
    return cur.lastrowid
    
def get_song_info(path):
    tags = util.get_metadata(path)
    track_performer = tags['artist']
    artist = tags['performer'] or track_performer
    album = tags['album']
    name = tags['title'] or os.path.splitext(os.path.split(path)[1])[0]
    return (name, album, track_performer, artist)

######## GETTERS AND UPDATERS ########

def jsonify(data):
    return Response(encoder.encode(data),
                    mimetype = 'application/json')

def JSON(function):
    def func(*args, **kwargs):
        data = function(*args, **kwargs)
        if data == None:
            abort(404)
        resp = jsonify(data)
        resp.status_code=200
        return resp
    func.__name__ = function.__name__
    func.__doc__ = function.__doc__
    return func

def update_folderhash(path):
    mr_itchy = md5.md5()
    contents = os.listdir(path)
    for node in contents:
        if node not in IGNORE:
            mr_itchy.update(node)
    hash = mr_itchy.hexdigest()
    cur.execute("INSERT OR REPLACE INTO folderhashes VALUES (?, ?)", (path, hash))

@JSON
def get_artists():
    return Query.artists()

@JSON
def get_artists_query():
    return Query.artists()

@JSON
def get_artist(id):
    return Artist.get(id)

@JSON
def get_albums():
    return Query.albums()

@JSON
def get_album(id):
    return Album.get(id)

@JSON
def get_songs():
    return Query.songs()

@JSON
def get_song(id):
    return Song.get(id)

def delete_song(id):
    Song.delete(id)
@JSON
def get_tags(id):
    return Song.get_tags(id)

def remove_tags(id):
    Song.update_tags(id)

def add_url_rules(app):
    app.add_url_rule('/library', 'get_artists', get_artists)
    app.add_url_rule('/library/artist', 'get_artists_query', get_artists_query)
    app.add_url_rule('/library/artist/<int:id>', 'get_artist', get_artist)
    app.add_url_rule('/library/album', 'get_albums', get_albums)
    app.add_url_rule('/library/album/<int:id>', 'get_album', get_album)
    app.add_url_rule('/library/song', 'get_songs', get_songs)
    app.add_url_rule('/library/song/<int:id>', 'get_song', get_song)
##    app.add_url_rule('/library/song/<int:id>', update_song,
##                     methods = ['PATCH'])
    app.add_url_rule('/library/song/<int:id>', 'delete_song', delete_song,
                     methods = ['DELETE'])
    app.add_url_rule('/library/songs/<int:id>/tags', 'get_tags', get_tags)
##    app.add_url_rule('/library/songs/<int:id>/tags', update_tags,
##                     methods = ['PUT'])
    app.add_url_rule('/library/songs/<int:id>/tags', 'remove_tags', remove_tags,
                     methods = ['DELETE'])

if __name__ == '__main__':
    app = Flask(__name__)
    app.debug = DEBUG
    connect(app)
    app.run()
