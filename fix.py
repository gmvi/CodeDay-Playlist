from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

print "Quick ID3 Tag Fixer by George Matter VI"
print "Point program to a folder of mp3 or m4a files representing an album " + \
      "to quickly fix poor tagging."
print "Note: doesn't support tag removal."
src = raw_input('dir: ')
##while True:
##    deep = raw_input('overwrite (y/n): ')
##    if deep.lower() in ['y','n']: break
##deep = deep == 'y'
deep = False
#TODO: support overwrite mode, which checks everything w/ a way to remove tags
artist = raw_input('default artist or [ENTER]: ')
album = raw_input('default album or [ENTER]: ')
date = raw_input('default date or [ENTER]: ')
a = os.listdir(src)
for i in a:
    if os.path.splitext(a)[1] == '.mp3':
        audio = MP3(src+a, ID3=EasyID3)
    elif os.path.splitext(a)[1] in ['.m4a', '.mp4']:
        
    print a
    if deep or 'title' not in audio:
        title_ = raw_input('title: ')
        if deep or title_: audio['title'] = title_
    if deep or 'tracknumber' not in audio:
        trk_ = raw_input('trk: ')
        if deep or trk_: audio['tracknumber'] = trk_
    if deep or 'artist' not in audio:
        artist_ = artist or raw_input('artist: ')
        if deep or artist_: audio['artist'] = artist_
    if deep or 'album' not in audio:
        album_ = album or raw_input('album: ')
        if deep or album_: audio['album'] = album_
    if deep or 'date' not in audio:
        date_ = date or raw_input('date: ')
        if deep or date_: audio['date'] = date_
    audio.save()
