import vlc

class VLCController():
    list_player = vlc.MediaListPlayer()
    media_player = vlc.MediaPlayer()
    list_player.set_media_player(media_player)
    media_list = vlc.MediaList()
    list_player.set_media_list(media_list)

    def add(self, path):
        self.media_list.add_media(path)
        #TODO: check that media is real

    def play(self):
        self.list_player.play()

    def pause(self):
        self.list_player.pause()

    def next(self):
        self.list_player.next()

    def play_last(self):
        l = len(self.media_list)
        if l != 0:
            self.list_player.play_item_at_index(l-1)
        else:
            raise ValueError("No last item to play")

    def get_pos(self):
        return self.media_player.get_position()

    def set_pos(self, num):
        if type(num) is float and num >= 0.0 and num <= 1.0:
            if num > .99: #unnecessary?
                num = .99
            self.media_player.set_position(num)

