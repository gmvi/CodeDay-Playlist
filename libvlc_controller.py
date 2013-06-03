import vlc, os
from urllib2 import unquote
from threading import Thread

SOUT_MP3  = '#transcode{acodec=mp3,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_OGG  = '#transcode{acodec=vorbis,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_M4A = '#transcode{acodec=mp3,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'
SOUT_FLAC = '#transcode{acodec=vorbis,ab=192,channels=2,samplerate=44100}:http{mux=ogg,dst=:8090/stream}'

SOUTS = {'.mp3'  : SOUT_MP3,
         '.ogg'  : SOUT_OGG,
         '.m4a'  : SOUT_M4A,
         '.flac' : SOUT_FLAC}


class VLCController():
    def __init__(self, broadcast = False):
        self.broadcast = broadcast
        self.list_player = vlc.MediaListPlayer()
        self.media_player = vlc.MediaPlayer()
        self.list_player.set_media_player(self.media_player)
        self.media_list = vlc.MediaList()
        self.list_player.set_media_list(self.media_list)
        self.instance = vlc._default_instance
        self.instance.vlm_add_broadcast('main', None, SOUT_MP3,
                                        0, None, True, False)
        em = self.media_player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerMediaChanged,
                        self.reset_broadcast)

    def reset_broadcast(self, event):
        self.instance.vlm_stop_media('main')
        if self.broadcast:
            media_path = self.get_media_path()
            self.instance.vlm_change_media('main', media_path,
                                           SOUTS[os.path.split(media_path)[1]],
                                           0, None, True, False)
            self.instance.vlm_play_media('main')

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

    def get_media_path(self):
        path = self.media_player.get_media().get_mrl()
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

