import vlc

lp = vlc.MediaListPlayer()
p = vlc.MediaPlayer()
lp.set_media_player(p)
l = vlc.MediaList()
lp.set_media_list(l)

m1 = vlc.Media("music/Space.mp3")
m2 = vlc.Media("music/Blackout.mp3")
m3 = vlc.Media("music/Eamon.wav")
