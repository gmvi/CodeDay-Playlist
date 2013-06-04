import vlc, os
from pprint import pprint
from time import sleep
from urllib2 import unquote
from threading import Thread

SOUT_MP3  = '#transcode{acodec=mp3,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_OGG  = '#transcode{acodec=vorbis,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_M4A = '#transcode{acodec=mp3,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_FLAC = '#transcode{acodec=vorbis,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'

class VLCController():
    
    SOUTS = {'.mp3'  : SOUT_MP3,
             '.ogg'  : SOUT_OGG,
             '.m4a'  : SOUT_M4A,
             '.flac' : SOUT_FLAC}
    
    def __init__(self, broadcast = False):
        self.broadcast = broadcast
        self.list_player = vlc.MediaListPlayer()
        self.media_player = vlc.MediaPlayer()
        self.list_player.set_media_player(self.media_player)
        self.media_list = vlc.MediaList()
        self.list_player.set_media_list(self.media_list)
        self.instance = vlc._default_instance
        self.instance.vlm_add_broadcast('main', None, None,
                                        0, None, True, False)

    def should_reset_broadcast(self):
        playing = self.get_media_path()
        broadcast = self.instance.vlm_show_media('main').split('inputs": [\n\t\t"')[1] \
                                                        .split('"')[0]
        if broadcast.startswith('file:///'): broadcast = broadcast[8:]
        broadcast_time = self.instance.vlm_get_media_instance_time('main', 0)/1000
        if playing != broadcast:
            broadcast_len = self.instance.vlm_get_media_instance_length('main', 0)/1000
            time_left = broadcast_len - broadcast_time
            if time_left < 1000 or time_left > 10000: #MAX_MS_LET_STREAM_FINISH
                return True
            else: return False # this is kinda arbitrary...
        playing_time = self.media_player.get_time()
        slide = abs(playing_time - broadcast_time)
        if slide > 20000: #MAX_SLIDE
            return True
        return False

    def set_broadcast(self):
        media_path = self.get_media_path()
        if not media_path.startswith('file:///'):
            media_path = 'file:///' + media_path
        if not media_path:
            raise ValueError("no media available for broadcasting")
        self.instance.vlm_set_input('main', media_path)
        self.instance.vlm_set_output('main', \
            VLCController.SOUTS[os.path.splitext(media_path)[1]])
    
    def reset_broadcast(self, event = None):
        self.instance.vlm_stop_media('main')
        if self.broadcast:
            self.set_broadcast()
            if self.media_player.is_playing():
                self.instance.vlm_play_media('main')
                self.instance.vlm_seek_media('main', \
                    self.media_player.get_position())

    def __getitem__(self, i):
        return self.get(i)

    def get(self, i):
        if i < 0 or i >= len(self.media_list):
            raise IndexError("playlist index out of range")
        else:
            return self.media_list.item_at_index(i).get_mrl()
        #TODO support -i

    def pop(self, i):
        if i < 0 or i >= len(self.media_list):
            raise IndexError("playlist index out of range")
        else:
            mrl = self.media_list.item_at_index(i).get_mrl()
            self.media_list.remove_index(i)
            return mrl

    def add(self, path):
        if os.path.exists(path):
            self.media_list.add_media(path)
        else:
            raise IOError("No such file or directory: '%s'" % path)

    def get_media_path(self):
        media = self.media_player.get_media()
        if not media:
            media = self.media_list[len(self.media_list)-1]
        if not media:
            return None
        path = media.get_mrl()
        if path.startswith("file:///"):
            path = path[8:]
        return unquote(path)

    def play(self):
        self.list_player.play()
        if self.broadcast:
            self.instance.vlm_play_media('main')

    def pause(self):
        self.list_player.pause()
        if self.broadcast:
            self.instance.vlm_pause_media('main')

    def next(self):
        #TODO: check if player has a next, make this better
        self.media_player.set_position(.98)

    def previous(self):
        #TODO: check if player has a previous
        self.list_player.previous()

    def play_last(self):
        l = len(self.media_list)
        if l != 0:
            self.list_player.play_item_at_index(l-1)
        else:
            raise ValueError("No last item to play")

    def stop(self):
        self.list_player.stop()
        self.stop_stream()
        
    def stop_stream(self):
        self.instance.vlm_stop_media('main')

    # def broadcast_on, broadcast_off ?
        
    def get_pos(self):
        return self.media_player.get_position()

    def set_pos(self, num):
        if type(num) is float and num >= 0.0 and num <= 1.0:
            if num > .98: #unnecessary?
                num = .98
            self.media_player.set_position(num)
            if self.broadcast:
                self.instance.vlm_seek_media('main', num)

