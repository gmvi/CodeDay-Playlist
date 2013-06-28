import sys, os, threading, socket, json, subprocess
if "modules" not in sys.path: sys.path.append("modules")
base = os.path.abspath(".")
from random import choice
from time import sleep

from vlc import State
from libvlc_controller import VLCController
import database
from commands import commands
from util import bufferlist, Socket

## CONSTANTS

ARTIST_BUFFER_SIZE = 4 # min playlist space between tracks by same artist.
SONG_BUFFER_SIZE = 30 # min playlist space between same track.
TIME_CUTOFF_MS = 2000 # time away from end of last song to add another to list.
LOOP_PERIOD_SEC = 1
DEBUG = False # enable DEBUG to disable the standard command line controls,
              # for playing around with the program in the python shell.
BROADCAST = False
SHUTDOWN_KEY = "i've made a terrible mistake"
lan_addr = socket.gethostbyname(socket.gethostname())
IDLE = 'idlelib' in sys.modules

class BadMediaStateError(ValueError): pass
class TrackNotFoundError(ValueError): pass

## GLOBALS

v = VLCController(BROADCAST) # VLCConstroller instance
db_path = None # path to the songs in the database
music_thread = None # thread controlling the queuing system
console_thread = None # thread controlling the console interface
webserver_process = None # container for webserver subprocess
webserver_sock = Socket() # util.Socket to handle communication with the webserver
SOCK_PORT = 2148 # port for the socket
artist_buffer = bufferlist(ARTIST_BUFFER_SIZE)
song_buffer = bufferlist(SONG_BUFFER_SIZE)
logfile = open('weblog.txt', "wb")

### MUSIC CONTROL STUFF

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

def get_remaining():
    path = v.get_media_path()
    if v.media_player.get_state() == State.Stopped or \
       not path:
        raise BadMediaStateError()
    path = os.path.normpath(path)
    for i in range(len(song_buffer)):
        buffer_song_path = os.path.join(db_path, song_buffer[-1-i].path)
        songpath = os.path.normpath(os.path.abspath(buffer_song_path))
        if songpath == path:
            return i
    raise TrackNotFoundError(songpath)

def should_add_another():
    if get_remaining() != 0:
        return False
    media = v.media_player.get_media()
    if media:
        return media.get_duration() - \
               v.media_player.get_time() < TIME_CUTOFF_MS

# This bullshit is entirely because I can't seem to disable the sqlite
# anit-threading safeties in SQLAlchemy.
class MusicThread():
    def __init__(self, db_path):
        self.RUNNING = True
        self.db_built = False
        self.db_path = db_path
        self.thread = threading.Thread(target=self)
        self._add = False
    def start(self):
        self.thread.start()
    def stop(self):
        self.RUNNING = False
        
    def add(self): # because I can only handle database objects from this thread
        self._add = True
        while self._add:
            sleep(.1)
        return
    
    def pick_next(self):
        global artist_buffer, song_buffer
        artists_ = database.get_artists()[:]
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
            song = choice(songs)
        song_buffer.append(song)
        v.add(os.path.join(db_path, song.path))
    
    def __call__(self): # main
        database.connect(self.db_path)
        self.db_built = True
        if not database.get_artists():
            print "No artists!"
            shut_down()
            return
        if v.media_player.get_state() != State.Playing:
            self.pick_next()
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

### WEBSERVER

def webserver_on_message_callback(message):
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
    elif j['type'] == 'info':
        print "webpage running on %s" % j['data']

def webserver_on_connect_callback():
    print "connected to webserver"
    update()

def webserver_on_disconnect_callback():
    print "disconnected from webserver"

def update():
    try:
        track = get_track()
        if track and webserver_sock.can_send():
            webserver_sock.sendln(json.dumps({'type' : 'update',
                                              'data' : track.get_dict()}))
    except Socket.NotConnectedException:
        if DEBUG: print "Error updating: not connected", webserver_sock._mode

def set_up_webserver():
    global webserver_process, webserver_sock
    cmd = 'python ' + os.path.join(base, "webpage.py")
    webserver_process = subprocess.Popen(cmd, shell = True, stdout=logfile, \
                                         stderr=subprocess.STDOUT)
    print "connecting to webserver..."
    webserver_sock.on_connect(webserver_on_connect_callback)
    webserver_sock.on_disconnect(webserver_on_disconnect_callback)
    webserver_sock.listen('localhost', SOCK_PORT, webserver_on_message_callback)

### CONSOLE INTERFACE

def shut_down():
    print "shutting down..."
    # Go through each of the shutdown functions sequentially, ignoring any
    # Exceptions, so that other things get shut down, even if one doesn't.
    # This solution works for various arrangements of threading, subprocessing,
    # and multiprocessing.
    funcs = [logfile.close,
             music_thread.stop,
             webserver_process.terminate,
             v.stop_stream,
             v.stop,
             webserver_sock.reset]
    for func in funcs:
        try:
            func()
        except Exception as e:
            print e
    ##raw_input()
    ##exit()

def console():
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
        elif cmd:
            print "'%s' is not a command." % cmd
    shut_down()
    

### MAIN

def main():
    global music_thread, console_thread, db_path
    db_path = os.path.join("music", raw_input("playlist: "))
    music_thread = MusicThread(db_path)
    music_thread.start()
    set_up_webserver()
    while not music_thread.db_built:
        sleep(1)
    if not IDLE:
        console_thread = threading.Thread(target=console)
        console_thread.start()

if __name__ == '__main__':
    main()
