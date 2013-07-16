import sys, os, threading, socket, json, subprocess
if "modules" not in sys.path: sys.path.append("modules")
base = os.path.abspath(".")
from random import choice
from time import sleep

from vlc import State
from libvlc_controller import VLCController
import database, console
from util import bufferlist, Socket, load_settings
load_settings()

## CONSTANTS

from settings import *
lan_addr = socket.gethostbyname(socket.gethostname())
IDLE = 'idlelib' in sys.modules

class BadMediaStateError(ValueError): pass
class TrackNotFoundError(ValueError): pass

## GLOBALS

v = VLCController(BROADCAST) # VLCConstroller instance
db_path = None # path to the songs in the database
RUNNING = True
console_thread = None # thread controlling the console interface
webserver_process = None # container for webserver subprocess
webserver_sock = Socket() # util.Socket to handle communication with the webserver
SOCK_PORT = 2148 # port for the socket
artist_buffer = bufferlist(ARTIST_BUFFER_SIZE)
song_buffer = bufferlist(SONG_BUFFER_SIZE)
logfile = open(LOG_LOCATION, "wb")

# hax
NONE = 0
NEXT = 1
PREV = 2
do = NONE

### MUSIC CONTROL STUFF

def get_track(verbose = False):
    if len(song_buffer) == 0:
        if verbose and DEBUG:
            print "get_track() failed: no songs in song_buffer"
        return
    elif len(song_buffer) == 1:
        return song_buffer[0]
    else:
        path = v.get_media_path()
        if not path:
            if verbose and DEBUG:
                print "get_track() failed: no current song in VLCController"
                return
        path = os.path.normpath(path)
        for song in song_buffer[::-1]:
            songpath = os.path.normpath(os.path.abspath(song.rel_path))
            if songpath == path:
                return song
        if verbose and DEBUG:
            print "VLCController path not in song_buffer"

def get_remaining():
    path = v.get_media_path()
    if v.media_player.get_state() == State.Stopped or not path:
        raise BadMediaStateError()
    path = os.path.normpath(path)
    for i in range(len(song_buffer)):
        buffer_song_path = os.path.join(db_path, song_buffer[-1-i].path)
        songpath = os.path.normpath(os.path.abspath(buffer_song_path))
        if songpath == path:
            return i
    raise TrackNotFoundError(songpath)

def should_add_another():
    return get_remaining() == 0

def pick_next():
    global artist_buffer, song_buffer
    artists = database.artists[:]
    for artist in artist_buffer:
        try: artists.remove(artist)
        except ValueError: pass
    if not artists: return None
    artist = None
    while not artist:
        artist = choice(artists)
        songs = artist.songs[:]
        for song in songs[:]:
            if song in song_buffer:
                songs.remove(song)
        if len(songs) == 0:
            artists.remove(artist)
            if not artists: return None
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

#To do: leverage gevent, since I'm already using it for socket-io?
def music_picker_loop():
    global RUNNING, do
    if not database.artists:
        print "No artists!"
        shut_down()
        return
    print "starting playback"
    if v.media_player.get_state() != State.Playing:
        pick_next()
        v.set_broadcast()
        v.play()
    while v.media_player.get_state() != State.Playing:
        pass
    current = ""
    while RUNNING:
        if v.get_media_path() != current:
            update()
            current = v.get_media_path()
        if v.should_reset_broadcast():
            v.reset_broadcast()
        if should_add_another():
            pick_next()
        sleep(LOOP_PERIOD_SEC)

def next():
    if not v.has_next():
        pick_next()
    v.next()
    update()

def _next():
    global do
    do = NEXT

def prev():
    if v.has_previous():
        v.previous()
        update()
    else:
        v.set_pos(0)

def _prev():
    global do
    do = PREV

### WEBSERVER

admin_commands = {'next' : next,
                  'pause' : v.pause,
                  'previous' : prev,
                  'last' : v.play_last}

def webserver_on_message_callback(message):
    j = json.loads(message)
    if j['type'] == 'command':
        if DEBUG: print "recieved command %s" % j['data']
        if j['data'] in admin_commands:
            admin_commands[j['data']]()
    elif j['type'] == 'info':
        print "webserver running on %s" % j['data']

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
    cmd = 'python ' + os.path.join(base, "webserver.py")
    webserver_sock.on_connect(webserver_on_connect_callback)
    webserver_sock.on_disconnect(webserver_on_disconnect_callback)
    webserver_sock.listen('localhost', SOCK_PORT, webserver_on_message_callback)
    print "starting webserver"
    webserver_process = subprocess.Popen(cmd, shell = True, stdout=logfile, \
                                         stderr=subprocess.STDOUT)

# command to restart webserver

### CONSOLE INTERFACE

def shut_down():
    global RUNNING, webserver_sock
    print "shutting down..."
    # Go through each of the shutdown functions sequentially, ignoring any
    # Exceptions, so that other things get shut down, even if one doesn't.
    # This solution works for various arrangements of threading, subprocessing,
    # and multiprocessing.
    RUNNING = False
    sleep(LOOP_PERIOD_SEC)
    funcs = [v.stop_stream,
             v.stop,
             webserver_sock.reset,
             logfile.close]
    if webserver_process: funcs.insert(-1, webserver_process.terminate)
    for func in funcs:
        try: func()
        except Exception as e:
            print e
    del webserver_sock
    if DEBUG: raw_input()
    exit()

### MAIN

illegal_chars = ["/", "\\"]
def validate(path):
    if not path: return False
    for character in set(path):
        if character in illegal_chars:
            return False
    return True

def main():
    global console_thread, db_path
    path = ""
    while not path:
        path = raw_input("playlist: ")
        if not validate(path):
            print "Bad playlist identifier!"
            path = ""
    db_path = os.path.join("music", path)
    database.connect(db_path)
    set_up_webserver()
    music_thread = threading.Thread(target=music_picker_loop)
    music_thread.start()
    console.run()

if __name__ == '__main__':
    main()
