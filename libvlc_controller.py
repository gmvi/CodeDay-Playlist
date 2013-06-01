import vlc, os
from urllib2 import unquote

class VLCController():
    def __init__(self):
        self.list_player = vlc.MediaListPlayer()
        self.media_player = vlc.MediaPlayer()
        self.list_player.set_media_player(self.media_player)
        self.media_list = vlc.MediaList()
        self.list_player.set_media_list(self.media_list)

    def __getitem__(self, i):
        return self.get(i)

    def __contains__(self, value):
        pass #TODO

    def get(self, i):
        if i < 0 or i >= len(self.media_list):
            raise IndexError("playlist index out of range")
        else:
            return self.media_list.item_at_index(i).get_mrl()

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

    def pause(self):
        self.list_player.pause()

    def next(self):
        #TODO: check if player has a next
        self.list_player.next()

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

