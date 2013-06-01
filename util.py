import os
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
EasyMP3 = lambda filename: MP3(filename, ID3=EasyID3)
from mutagen.easymp4 import EasyMP4
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3NoHeaderError
from mutagen.flac import FLAC
from random import choice

class UnsupportedFileTypeError(Exception): pass

FORMATS = {".mp3"  : EasyMP3,
           ".m4a"  : EasyMP4,
           ".ogg"  : OggVorbis,
           ".flac" : FLAC}

def get_info(audio, info):
    if audio.has_key(info):
        if type(audio[info]) == bool: return audio[info]
        else: return audio[info][0]
    else: return ""

def get_all_info(filepath):
    ext = os.path.splitext(filepath)[1]
    if ext not in FORMATS:
        raise UnsupportedFileTypeError()
    try:
        audio = FORMATS[ext](filepath)
    except ID3NoHeaderError:
        audio = MP3(filepath)
        audio.add_tags()
        audio.save()
        audio = EasyID3(filepath)
    artist = get_info(audio, 'artist')
    album = get_info(audio, 'album')
    title = get_info(audio, 'title')
    return (title,
            album,
            artist)

class Artist():

    songs = None
    name = None
    
    def __init__(self, name, songs = None):
        self.songs = songs
        if not self.songs:
            self.songs = []
        self.name = name

    def add(self, track):
        self.songs.append(track)

    def __eq__(self, other):
        return self.name == other.name

    def __str__(self):
        return "Artist(%s)" % self.name

    def __repr__(self):
        return self.__str__()

class Track():

    path = None
    track = None
    album = None
    artist = None

    def __init__(self, path):
        self.path = path
        self.track, self.album, self.artist = get_all_info(path)

    def __eq__(self, other):
        return self.path == other.path

    def __str__(self):
        return "<Track: %s by %s>" % (self.track, self.artist)

    def __repr__(self):
        return "Track(%s)" % self.path

class bufferlist(list):
    buffer_size = 0
    def insert(index, object): raise Exception()
    def extend(iterable): raise Exception()

    def __init__(self, size):
        list.__init__(self)
        if type(size) != int:
            raise TypeError("size must be int")
        self.buffer_size = size

    def append(self, object):
        list.append(self, object)
        if len(self) > self.buffer_size:
            self.pop(0)
