from vlcclient import VLCClient
import os, time, threading, webpage, subprocess
from socket import error as socketerror
from util import FORMATS, Artist, Track, bufferlist
from random import choice
base = os.path.abspath(os.path.curdir)

ARTIST_BUFFER_SIZE = 4
SONG_BUFFER_SIZE = 30
VLC_LOC = "C:\\Program Files\\videolan\\vlc"
AUTO_START_VLC

vlc = None
vlc_process = None
db = None
artist_buffer = bufferlist(ARTIST_BUFFER_SIZE)
song_buffer = bufferlist(SONG_BUFFER_SIZE)

def load_vlc():
    global vlc, vlc_process
    vlc = VLCClient("::1")
    first = True
    while True:
        try:
            vlc.connect()
            break
        except socketerror:
            vlc.disconnect()
            if AUTO_START_VLC and first:
                try:
                    vlc_process = subprocess.Popen("\"%s\\vlc\" --intf telnet" % VLC_LOC)
                except Exception as e:
                    print "Error trying to start VLC"
                    print e
                first = False
                time.sleep(1)
            else:
                raw_input("Cannot connect to VLC. [ENTER] to try again.")
    vlc.clear()
    vlc.volume(100)

def play():
    if status[2] != 'playing': vlc.play()

def pause():
    if status[2] == 'playing': vlc.pause()

def status():
    ret = [None, None, None]
    string = vlc.status().split('\r\n')
    if len(string) == 3:
        ret[0] = string[0][13:-2]
    ret[1] = int(string[-2][16:-2])
    ret[2] = string[-1][8:-2]
    return tuple(ret)

def add(path):
    vlc.add(os.path.join(base, path))
    vlc.play()

def get_all(path):
    ret = []
    for node in os.listdir(path):
        node = os.path.join(path, node)
        if os.path.isdir(node):
            ret += get_all(node)
        else:
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
                artist.add(Track(track))
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
    while RUNNING:
        if status()[2] != 'playing':
            add(choose().path)
        time.sleep(2)

def get_track(): # Update to check database. Also update database to make this possible.
    if status()[2] == 'playing':
        if len(song_buffer) > 0:
            return song_buffer[-1]

def main():
    load_vlc()
    path = raw_input("music: ")
    print "Constructing Database..."
    load_database(path)
    webpage_thread = threading.Thread(target=webpage.main, args=(get_track,))
    music_thread = threading.Thread(target=run)
    webpage_thread.start()
    music_thread.start()
    cmd = None
    while cmd != "quit":
        cmd = raw_input()
    print "shutting down..."
    music_thread._Thread__stop()
    webpage_thread._Thread__stop()
    if vlc_process:
        vlc_process.terminate()

if __name__ == '__main__':
    main()
