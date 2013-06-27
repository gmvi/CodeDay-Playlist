import sys, os, threading, socket, urllib, urllib2, json
sys.path.insert(0, "modules")
base = os.path.abspath(os.path.curdir)
from random import choice
from math import ceil
from time import sleep

from vlc import State, EventType, callbackmethod
from libvlc_controller import VLCController
import webpage
from database import DBController
from commands import commands
from util import FORMATS, bufferlist, Socket, get_all

## ADJUSTABLE CONSTANTS
ARTIST_BUFFER_SIZE = 4 # min playlist space betw tracks by same artist.
SONG_BUFFER_SIZE = 30 # min playlist space betw same track twice.
TIME_CUTOFF_MS = 2000 # time away from end of last song to add another to list.
LOOP_PERIOD_SEC = 1
DEBUG = False # enable DEBUG to disable the standard command line controls,
              # for playing around with the program in the python shell.
SHUTDOWN_KEY = "i've made a terrible mistake"

v = None # VLCConstroller instance
session = None # Database read/write client
db_path = None # path to the songs in the database
music_thread = None # thread controlling the queuing system
webpage_s = None
SOCK_PORT = 2148
lan_addr=socket.gethostbyname(socket.gethostname())
artist_buffer = bufferlist(ARTIST_BUFFER_SIZE)
song_buffer = bufferlist(SONG_BUFFER_SIZE)

def load_vlc():
    global v
    v = VLCController()
    
def should_add_another():
    if get_remaining() != 0:
        return False
    media = v.media_player.get_media()
    if media:
        return media.get_duration() - \
               v.media_player.get_time() < TIME_CUTOFF_MS

def get_track():
    #if v.media_player.get_state() == State.Playing:
        if len(song_buffer) == 0:
            return
        elif len(song_buffer) == 1:
            return song_buffer[0]
        else:
            path = v.get_media_path()
            if not path: return
            path = os.path.normpath(path)
            for song in song_buffer[::-1]:
                songpath = os.path.normpath(os.path.abspath(song.path))
                if songpath == path:
                    return song

class BadMediaStateError(ValueError): pass
class TrackNotFoundError(ValueError): pass

def get_remaining():
    path = v.get_media_path()
    if v.media_player.get_state() == State.Stopped or \
       not path:
        raise BadMediaStateError()
    path = os.path.normpath(path)
    for i in range(len(song_buffer)):
        songpath = os.path.normpath(os.path.abspath(song_buffer[-1-i].path))
        if songpath == path:
            return i
    raise TrackNotFoundError()

def load_database(path):
    global session, artists
    print "Reading database."
    session = database.connect(path)
    artists = session.query(database.Artist).all()
    if artists:
        return
    print "Builing database. This may take a while."
    unknown = []
    unknown_artist = database.Artist(path) # this is bad practice
    unknown_artist.name = "Unknown"
    for direc in os.listdir(path):
        node = os.path.join(path, direc)
        if os.path.isfile(node):
            ext = os.path.splitext(node)[1]
            if ext in FORMATS:
                unknown.append(database.Track(node))
        else:
            artist = database.Artist(node)
            artist.name = direc # fix this later
            session.add(artist)
            artists.append(artist)
            for track in get_all(node):
                try:
                    artist.add(database.Track(track))
                except IOError:
                    pass
    if unknown:
        for track in unknown:
            unknown_artist.add(track)
        session.add(unknown_artist)
        artists.append(unknown_artist)
    session.commit()

def choose(artists):

class MusicThread():
    RUNNING = True
    def __init__(self, db_path):
        self.RUNNING = True
        self.db_built = False
        self.db_path = db_path
        self.thread = threading.Thread(target=self)
        self._add = False
    def add(self):
        self._add = True
        while self._add:
            sleep(.1)
        return
    def pick_next(self):
        global artist_buffer, song_buffer
        artists_ = self.db.get_artists()[:]
        for artist in artist_buffer:
            try: artists_.remove(artist)
            except ValueError: pass
        if not artists_: return None
        artist = None
        while not artist:
            artist = choice(artists_)
            songs = artist.songs[:]
            for song in songs[:]:
                if song in song_buffer:
                    songs.remove(song)
            if len(songs) == 0:
                artists_.remove(artist)
                if not artists_: return None
                artist = None
        artist_buffer.append(artist)
        song = choice(songs)
        if not song:
            print "Not enough artists or songs! Lower your " + \
                  "MIN_BETW_REPEAT settings"
            print "Resetting constraints."
            del artist_buffer[:]
            del song_buffer[:]
            song = choose()
        song_buffer.append(song)
        v.add(song.path)
    def __call__(self):
        self.db = DBController(os.path.join("music", self.db_path))
        self.db.connect()
        self.db_built = True
        if not artists:
            print "No artists!"
            shut_down()
            return
        if v.media_player.get_state() != State.Playing:
            self.choose()
            v.set_broadcast()
            v.play()
        while v.media_player.get_state() != State.Playing:
            pass
        current = ""
        while self.RUNNING:
            if v.get_media_path() != current: #split into another thread?
                update()
                current = v.get_media_path()
            if v.should_reset_broadcast(): v.reset_broadcast()
            if self._add:
                self.pick_next()
                self._add = False
            if should_add_another():
                self.pick_next()
                time_left = (v.media_player.get_length() - v.media_player.get_time())/1000.0
                sleep(time_left)
                if not v.is_playing():
                    v.play_last()
            else:
                sleep(LOOP_PERIOD_SEC)
    def start(self):
        self.thread.start()
    def stop(self):
        self.RUNNING = False

def shut_down():
    try:
        music_thread.stop()
    except Exception as e:
        print e
    try:
        webpage_s.reset()
    except Exception as e:
        print e
    try:
        v.stop_stream()
    except Exception as e:
        print e
    v.stop()

def on_message(message):
    j = json.loads(message)
    if j['type'] == 'command':
        if j['data'] == 'next':
            if not v.has_next():
                music_thread.add()
            v.next()
            update()
        elif j['data'] == 'pause':
            v.pause()
        elif j['data'] == 'previous':
            if v.has_previous():
                v.previous()
                update()
            else:
                v.set_pos(0)

def on_connect():
    print "connected to webserver"
    update()

def on_disconnect():
    print "disconnected from webserver"

def update():
    try:
        track = get_track()
        if track and webpage_s.can_send():
            webpage_s.sendln(json.dumps({'type' : 'update',
                                         'data' : track.get_dict()}))
    except Socket.NotConnectedException:
        if DEBUG: print "Error updating: not connected", webpage_s._mode

# obsolete    
def attatch():
    em = v.list_player.event_manager()
    em.event_attach(EventType.MediaPlayerMediaChanged,
                    lambda *args: update(), None)

def main():
    global music_thread, webpage_s, db_path
    webpage_s = Socket()
    load_vlc()
    db_path = raw_input("music: ")
    music_thread = MusicThread(db_path)
    music_thread.start()
    #sys.spawnprocess('webpage.py')
    while not music_thread.db_built:
        sleep(1)
    print "connecting to webserver..."
    webpage_s.on_connect(on_connect)
    webpage_s.on_disconnect(on_disconnect)
    webpage_s.listen('localhost', SOCK_PORT, on_message)
    if not DEBUG:
        cmd = None
        while True:
            tokens = raw_input().split(" ", 1)
            cmd = tokens[0]
            args = tokens[1] if len(tokens) == 2 else ""
            if cmd == "quit":
                break
            elif cmd in commands:
                p = commands[cmd](v, args)
                if p: print p
            else:
                print "'%s' is not a command." % cmd
        print "shutting down..."
        shut_down()

if __name__ == '__main__':
    main()
