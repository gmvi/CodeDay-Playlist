from vlc import State
from libvlc_controller import VLCController
import os, time, threading, webpage, subprocess
from socket import error as socketerror
from util import FORMATS, Artist, Track, bufferlist
from random import choice
base = os.path.abspath(os.path.curdir)

ARTIST_BUFFER_SIZE = 4
SONG_BUFFER_SIZE = 30
#VLC_LOC = "C:\\Program Files\\videolan\\vlc"
TIME_CUTOFF_MS = 3000
LOOP_PERIOD_SEC = 2
DEBUG = False

v = None
db = None
music_thread = None
webpage_thread = None
artist_buffer = bufferlist(ARTIST_BUFFER_SIZE)
song_buffer = bufferlist(SONG_BUFFER_SIZE)

def load_vlc():
    global v
    v = VLCController()

def should_add_another():
    media = v.media_player.get_media()
    return media is not None and \
           media.get_duration() - v.media_player.get_time() < TIME_CUTOFF_MS

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

RUNNING = True
def run():
    v.add(choose().path)
    v.play()
    while v.media_player.get_state() != State.Playing:
        pass
    while RUNNING:
        if should_add_another():
            v.add(choose().path)
            if v.media_player.get_state() != State.Playing:
                v.play_last()
        time.sleep(LOOP_PERIOD_SEC)

def get_track(): # Update to get from playlist and compare to db.
    if v.media_player.get_state() == State.Playing:
        if len(song_buffer) > 0:
            return song_buffer[-1]


def shut_down():
    music_thread._Thread__stop()
    webpage_thread._Thread__stop()

def main():
    global music_thread, webpage_thread
    load_vlc()
    path = raw_input("music: ")
    print "Constructing Database..."
    load_database(path)
    webpage_thread = threading.Thread(target=webpage.main,
                                      args=(get_track, shut_down))
    music_thread = threading.Thread(target=run)
    webpage_thread.start()
    music_thread.start()
    if not DEBUG:
        cmd = None
        while True:
            cmd = raw_input()
            if cmd == "next":
                v.set_pos(.98) #shitty hack
            elif cmd == "quit":
                break
            else:
                print "Nope, the only commands are 'next' and 'quit'."
        print "shutting down..."
        shut_down()

if __name__ == '__main__':
    main()
