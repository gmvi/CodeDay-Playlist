import os, threading, urllib, urllib2
base = os.path.abspath(os.path.curdir)
from socket import error as socketerror
from random import choice
from math import ceil
from time import sleep

from vlc import State
from libvlc_controller import VLCController
import webpage
from util import FORMATS, Artist, Track, bufferlist

## ADJUSTABLE CONSTANTS
ARTIST_BUFFER_SIZE = 4 # min playlist space betw tracks by same artist.
SONG_BUFFER_SIZE = 30 # min playlist space betw same track twice.
TIME_CUTOFF_MS = 3000 # time away from end of last song to add another to list.
LOOP_PERIOD_SEC = 2 # does the program really need this? It's awkward.
DEBUG = False # enable DEBUG to disable the standard command line controls,
              # for playing around with the program in the python shell.
SHUTDOWN_KEY = "i've made a terrible mistake"

v = None # VLCConstroller instance
db = None # Database
db_path = None # path to the songs in the database
music_thread = None # thread controlling the queuing system
webpage_thread = None
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
    global db
    db = []
    unknown = []
    for direc in os.listdir(path):
        node = os.path.join(path, direc)
        if os.path.isfile(node):
            unknown.append(Track(node))
        else:
            artist = Artist(direc)
            for track in get_all(node):
                try:
                    artist.add(Track(track))
                except IOError:
                    pass
            db.append(artist)
    unknown_artist = Artist("")
    for track in unknown:
        unknown_artist.add(track)
    db.append(unknown_artist)

def choose():
    global artist_buffer, song_buffer
    artist = None
    while not artist or artist in artist_buffer:
        artist = choice(db)
        songs = artist.songs[:]
        for song in songs[:]:
            if song in song_buffer:
                songs.remove(song)
        if len(songs) == 0:
            artist = None
    artist_buffer.append(artist)
    song = choice(songs)
    song_buffer.append(song)
    return song

class MusicThread():
    RUNNING = True
    def __init__(self):
        self.RUNNING = True
        self.thread = threading.Thread(target=self)
    def __call__(self):
        if v.media_player.get_state() != State.Playing:
            v.add(choose().path)
            v.play()
        while v.media_player.get_state() != State.Playing:
            pass
        while self.RUNNING:
            if should_add_another():
                v.add(choose().path)
                sleep(ceil(TIME_CUTOFF_MS/1000.0))
                if v.media_player.get_state() != State.Playing:
                    v.play_last()
            sleep(LOOP_PERIOD_SEC)
    def start(self):
        self.thread.start()
    def stop(self):
        self.RUNNING = False

def shut_down():
    global v
    music_thread.stop()
    try:
        urllib2.urlopen("http://192.168.0.6/shutdown",
                        data=urllib.urlencode([('key', SHUTDOWN_KEY)]))
    except urllib2.HTTPError:
        pass
    v.stop()
    del v

def start():
    webpage.run()

def main():
    global music_thread, webpage_thread, db_path
    load_vlc()
    db_path = raw_input("music: ")
    print "Constructing Database..."
    load_database(db_path)
    music_thread = MusicThread()
    music_thread.start()
    webpage.attatch_get_track(get_track)
    webpage_thread = threading.Thread(target=start)
    webpage_thread.start()
    if not DEBUG:
        cmd = None
        while True:
            cmd = raw_input()
            if cmd == "next":
                v.set_pos(.98) #shitty hack
            elif cmd == "pause":
                v.pause()
            elif cmd == "play":
                v.play()
            elif cmd == "quit":
                break
            elif cmd == "debug":
                return
            else:
                print "Not a command."
        print "shutting down..."
        shut_down()

if __name__ == '__main__':
    main()
