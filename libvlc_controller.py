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
    # VLCController.broadcast_ahead is the value to broadcast ahead of the main
    # output, to account for lag between track playing positions, so that the
    # remote device may be audibly synced with the broadcasting device.
    # I found that 1500ms was the minimum to relibly be able to sync, in my case
    # with under 10ms ping. Your ping may be much higher. Presumably at under
    # 500ms ping you should be able to sync with a quick player. With a slow
    # player or high ping, you may need to raise VLCController.broadcast_ahead
    DEFAULT_BROADCAST_AHEAD = 2000 # miliseconds
    
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
        self.broadcast_ahead = VLCController.DEFAULT_BROADCAST_AHEAD

    def should_reset_broadcast(self):
        if not self.broadcast: return False
        playing = self.get_media_path()
        broadcast = self.instance.vlm_show_media('main').split('inputs": [\n\t\t"')[1] \
                                                        .split('"')[0]
        if broadcast.startswith('file:///'): broadcast = broadcast[8:]
        broadcast_time = self.instance.vlm_get_media_instance_time('main', 0)/1000
        playing_time = self.media_player.get_time()
        if playing != broadcast:
            broadcast_len = self.instance.vlm_get_media_instance_length('main', 0)/1000
            time_left = broadcast_len - broadcast_time
            if time_left < 1000 or time_left > 10000: #MAX_MS_LET_STREAM_FINISH
                return True
            else: return False # this is kinda arbitrary...
        slide = broadcast_time - playing_time - self.broadcast_ahead
        #print "slide: %s" % slide
        if slide < -500:
            return True
        return False

    def set_broadcast(self):
        if not self.broadcast: return
        media_path = self.get_media_path()
        if not media_path.startswith('file:///'):
            media_path = 'file:///' + media_path
        if not media_path:
            raise ValueError("no media available for broadcasting")
        self.instance.vlm_set_input('main', media_path)
        self.instance.vlm_set_output('main', \
            VLCController.SOUTS[os.path.splitext(media_path)[1]])
    
    def reset_broadcast(self, event = None):
        if not self.broadcast: return
        self.instance.vlm_stop_media('main')
        if self.broadcast:
            self.set_broadcast()
            if self.media_player.is_playing():
                self.instance.vlm_play_media('main')
                self.instance.vlm_seek_media('main', \
                    self.media_player.get_position() + \
                    1.0*self.broadcast_ahead / self.media_player.get_length())

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

    def get_media_path(self, last=False):
        media = self.media_player.get_media()
        if not media:
            i = 0
            if last: i = len(self.media_list)-1
            media = self.media_list[i].get_mrl()
        if not media:
            return None
        path = media.get_mrl()
        if path.startswith("file:///"):
            path = path[8:]
        return unquote(path)

    def has_next(self):
        cur_item = self.media_player.get_media()
        if not cur_item: return False
        last = len(self.media_list)-1
        if last == -1: return False
        last_item = self.media_list[last].get_mrl()
        return last_item != cur_item.get_mrl()

    def has_previous(self):
        cur_item = self.media_player.get_media()
        if not cur_item: return False
        first_item = self.media_list[0]
        return first_item and first_item.get_mrl() != cur_item.get_mrl()

    def play(self):
        self.list_player.play()
        if self.broadcast:
            self.instance.vlm_play_media('main')

    def is_playing(self):
        return self.media_player.get_state() == vlc.State.Playing

    def pause(self):
        self.list_player.pause()
        if self.broadcast:
            self.instance.vlm_pause_media('main')

    def next(self):
        self.list_player.next()

    def previous(self):
        #TODO: check if player has a previous, else set_pos(0)
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

