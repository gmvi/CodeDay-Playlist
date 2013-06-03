import os, threading, urllib, urllib2
base = os.path.abspath(os.path.curdir)
from socket import error as socketerror
from random import choice
from math import ceil
from time import sleep

from vlc import State
from libvlc_controller import VLCController
import webpage, database
from commands import commands
from util import FORMATS, bufferlist

## ADJUSTABLE CONSTANTS
ARTIST_BUFFER_SIZE = 4 # min playlist space betw tracks by same artist.
SONG_BUFFER_SIZE = 30 # min playlist space betw same track twice.
TIME_CUTOFF_MS = 3000 # time away from end of last song to add another to list.
LOOP_PERIOD_SEC = 2 # does the program really need this? It's awkward.
DEBUG = False # enable DEBUG to disable the standard command line controls,
              # for playing around with the program in the python shell.
SHUTDOWN_KEY = "i've made a terrible mistake"

v = None # VLCConstroller instance
session = None # Database read/write client
artists = [] # list of database.Artist objects
db_path = None # path to the songs in the database
music_thread = None # thread controlling the queuing system
webpage_thread = None
artist_buffer = bufferlist(ARTIST_BUFFER_SIZE)
song_buffer = bufferlist(SONG_BUFFER_SIZE)

def load_vlc():
    global v
    v = VLCController(True)

def should_add_another():
    if get_remaining() != 0:
        return False
    media = v.media_player.get_media()
    if media:
        return media.get_duration() - \
               v.media_player.get_time() < TIME_CUTOFF_MS

def get_track():
    if v.media_player.get_state() == State.Playing:
        if len(song_buffer) == 0:
            return
        elif len(song_buffer) == 1:
            return song_buffer[0]
        else:
            path = os.path.normpath(v.get_media_path())
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

def get_all(path):
    ret = []
    for node in os.listdir(path):
        node = os.path.join(path, node)
        if os.path.isdir(node):
            ret += get_all(node)
        else:
            if os.path.splitext(node)[1] in FORMATS:
                ret.append(node)
    return ret

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

def choose():
    global artist_buffer, song_buffer
    artists_ = artists[:]
    for artist in artist_buffer: #shorter(artist_buffer, artists_)
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
    song_buffer.append(song)
    return song

class MusicThread():
    RUNNING = True
    def __init__(self, db_path):
        self.RUNNING = True
        self.db_built = False
        self.db_path = db_path
        self.thread = threading.Thread(target=self)
    def choose(self):
        song = choose()
        if not song:
            print "Not enough artists or songs! Lower your " + \
                  "MIN_BETW_REPEAT settings"
            print "Resetting constraints."
            del artist_buffer[:]
            del song_buffer[:]
            song = choose()
        v.add(song.path)
    def __call__(self):
        load_database(self.db_path)
        self.db_built = True
        if not artists:
            print "No artists!"
            shut_down()
            return
        if v.media_player.get_state() != State.Playing:
            self.choose()
            v.play()
        while v.media_player.get_state() != State.Playing:
            pass
        while self.RUNNING:
            if should_add_another():
                self.choose()
                sleep(ceil(TIME_CUTOFF_MS/1000.0))
                if v.media_player.get_state() != State.Playing:
                    v.play_last()
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
        urllib2.urlopen("http://192.168.0.6/shutdown",
                        data=urllib.urlencode([('key', SHUTDOWN_KEY)]))
    except Exception as e:
        print e
    try:
        v.kill_stream()
    except Exception as e:
        print e
    v.stop()

def start():
    webpage.run()

def main():
    global music_thread, webpage_thread, db_path
    load_vlc()
    db_path = raw_input("music: ")
    music_thread = MusicThread(db_path)
    music_thread.start()
    webpage.attatch_get_track(get_track)
    webpage_thread = threading.Thread(target=start)
    webpage_thread.start()
    while not music_thread.db_built:
        sleep(1)
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
