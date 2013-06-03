import vlc, os
from urllib2 import unquote
from threading import Thread

SOUT_MP3  = '#transcode{acodec=mp3,ab=128,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_OGG  = '#transcode{acodec=vorbis,ab=128,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_MP4A = '#transcode{acodec=mp4a,ab=128,channels=2,samplerate=44100}:http{mux=mp4,dst=:8090/stream}'
SOUT_FLAC = '#transcode{acodec=vorbis,ab=128,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'

class VLCController():
    def __init__(self, broadcast = False):
        self.list_player = vlc.MediaListPlayer()
        self.media_player = vlc.MediaPlayer()
        self.list_player.set_media_player(self.media_player)
        self.media_list = vlc.MediaList()
        self.list_player.set_media_list(self.media_list)
        self.instance = vlc._default_instance
        if broadcast:
            self.instance.vlm_add_broadcast('main', None, SOUT_MP3, 0, None, True, False)
            #self.thread = Thread(target=self.run)

    def __getitem__(self, i):
        return self.get(i)

    def __contains__(self, value):
        pass #TODO

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
            self.instance.vlm_add_input('main', path)

    def get_media_path(self):
        path = self.media_player.get_media().get_mrl()
        if path.startswith("file:///"):
            path = path[8:]
        return unquote(path)

    def play(self):
        self.list_player.play()
        self.instance.vlm_play_media()

    def pause(self):
        self.list_player.pause()
        self.instance.vlm_pause_media()

    def next(self):
        #TODO: check if player has a next
        self.media_player.set_pos(.98)

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
        
    def get_pos(self):
        return self.media_player.get_position()

    def set_pos(self, num):
        if type(num) is float and num >= 0.0 and num <= 1.0:
            if num > .99: #unnecessary?
                num = .99
            self.media_player.set_position(num)

