import os, sys, time, socket, threading, json
if 'modules' not in sys.path: sys.path.insert(0, 'modules')
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
EasyMP3 = lambda filename: MP3(filename, ID3=EasyID3)
from mutagen.easymp4 import EasyMP4
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3NoHeaderError
from mutagen.flac import FLAC
from socketio.namespace import BaseNamespace
from random import choice

## Utility Methods

def load_settings():
    try: import settings
    except:
        import settings_default
        sys.modules['settings'] = settings_default

# Do I even use this anymore? maybe in Socket?
def sleep(seconds, while_true = None, test_interval = .1):
    if while_true == None:
        time.sleep(seconds)
        return
    start = time.time()
    end = start+seconds
    remaining = lambda: end - time.time()
    while while_true() and remaining() >= 0:
        time.sleep(min(test_interval, remaining()))

# files

class UnsupportedFileTypeError(Exception): pass

is_supported = lambda path: os.path.splitext(path)[1] in FORMATS    

def get_all(path):
    ret = []
    for node in os.listdir(path):
        node = os.path.join(path, node)
        if os.path.isdir(node):
            ret += get_all(node)
        else:
            if os.path.splitext(node)[1] in FORMATS:
                ret.append(node)
    return ret

def path_relative_to(root, rel_path):
	root = split(root)
	rel_path = split(rel_path)
	if rel_path[:len(root)] == root:
		return os.path.sep.join(rel_path[len(root):])
	else:
		raise ValueError()

def split(path):
    if type(path) is str:
        path = [path]
    first_split = os.path.split(path[0])
    if first_split[0] == '':
        return path
    path[:1] = os.path.split(path[0])
    return split(path)

# audio files

FORMATS = {".mp3"  : EasyMP3,
           ".m4a"  : EasyMP4,
           ".ogg"  : OggVorbis,
           ".flac" : FLAC}

def get_info(audio, info):
    if audio.has_key(info):
        if type(audio[info]) == bool: return audio[info]
        else: return audio[info][0]
    else: return ""

def get_metadata(filepath):
    ext = os.path.splitext(filepath)[1]
    if ext not in FORMATS:
        raise UnsupportedFileTypeError()
    try:
        audio = FORMATS[ext](filepath)
    except ID3NoHeaderError:
        audio = MP3(filepath)
        audio.add_tags()
        audio.save()
        audio = EasyMP3(filepath)
    artist = get_info(audio, 'artist')
    album_artist = get_info(audio, 'performer') or artist
    album = get_info(audio, 'album')
    title = get_info(audio, 'title')
    return (artist,
            album_artist,
            album,
            title)

## Utility Classes

###obsolete
##class Artist():
##    
##    def __init__(self, path, name = None):
##        self.path = path
##        self.name = name or ""
##        self.songs = []
##
##    @staticmethod
##    def convert(object):
##        try:
##            a = Artist(object.path)
##            a.name = object.name
##            a.songs = object.songs
##        except:
##            raise Exception("failed")
##
##    def add(self, track):
##        self.songs.append(track)
##
##    def remove(self, track):
##        self.songs.remove(track)
##
##    def __eq__(self, other):
##        return (self.name, self.path) == (other.name, other.path)
##
##    def __str__(self):
##        return "<Artist: %s>" % self.name
##
##    def __repr__(self):
##        return "Artist(%s)" % self.path
##
###obsolete
##class Track():
##
##    def __init__(self, path = None):
##        self.path = path
##        if path == None:
##            self.track = None
##            self.album = None
##            self.artist= None
##        else:
##            self.track, self.album, self.artist = get_all_info(path)
##
##    @staticmethod
##    def convert(object):
##        try:
##            t = Track()
##            t.path, t.track, t.album, t.artist = (object.path,
##                                                  object.track,
##                                                  object.album,
##                                                  object.artist)
##        except:
##            raise Exception("failed")
##
##    def __eq__(self, other):
##        return self.path == other.path
##
##    def __str__(self):
##        return "<Track: %s by %s>" % (self.track, self.artist)
##
##    def __repr__(self):
##        return "Track(%s)" % self.path
##
##    def get_dict(self):
##        return {'track' : self.track,
##                'album' : self.album,
##                'artist': self.artist}

class bufferlist(list):
    buffer_size = 0
    def insert(index, object): raise NotImplementedError()
    def extend(iterable): raise NotImplementedError()

    def __init__(self, size):
        list.__init__(self)
        if type(size) != int:
            raise TypeError("size must be int")
        self.buffer_size = size

    def append(self, object):
        list.append(self, object)
        if len(self) > self.buffer_size:
            self.pop(0)

class Socket():
    class NotConnectedException(Exception): pass
    MODE_READY = MODE_NONE = 0
    MODE_LISTENING = 1
    MODE_ACCEPTED = 2
    MODE_CONNECTING = 3
    MODE_CONNECTED = 4
    MODE_ERROR = 5
    MODES_CAN_SEND = [MODE_ACCEPTED,
                      MODE_CONNECTED]
    
    def can_send(self):
        return self._mode in Socket.MODES_CAN_SEND
    
    def __init__(self):
        self._sock = None
        self._sock2 = None
        self.message_callback = None
        self.connect_callback = None
        self.disconnect_callback = None
        self._alive = True
        self._mode = Socket.MODE_NONE
        self._thread = None

    def reset(self):
        self.message_callback = None
        self._alive = False
        while self._thread and self._thread.isAlive():
            sleep(.5)
        self._alive = True
        self._mode = Socket.MODE_NONE
        self._sock = None
        self._sock2 = None
        self._thread = None

    def on_connect(self, connect_callback):
        self.connect_callback = connect_callback

    def on_disconnect(self, disconnect_callback):
        self.disconnect_callback = disconnect_callback
        
    def listen(self, ip_addr, port, on_message = None):
        if self._mode != Socket.MODE_NONE:
            return ValueError("Socket object already in use. Call Socket.reset() to reset Socket")
        self._sock2 = socket.socket()
        self._sock2.bind((ip_addr, port))
        self._sock2.listen(1)
        if on_message != None: self.message_callback = on_message
        def accept():
            self._sock2.settimeout(1)
            while self._alive:
                self._mode = Socket.MODE_LISTENING
                try:
                    self._sock, address = self._sock2.accept()
                except socket.timeout:
                    continue
                self._sock.settimeout(1)
                self._mode = Socket.MODE_ACCEPTED
                if self.connect_callback != None: self.connect_callback()
                message = ""
                while self._alive:
                    try:
                        r = self._sock.recv(1)
                    except socket.timeout:
                        continue
                    except socket.error:
                        break
                    message += r
                    if r == "":
                        break
                    if r == "\n":
                        if self.message_callback != None: self.message_callback(message)
                        message = ""
                self.disconnect_callback()
        self._thread = threading.Thread(target=accept)
        self._thread.start()

    def connect(self, ip_addr, port, on_message = None):
        if self._mode != Socket.MODE_NONE:
            return ValueError("Socket object already in use. Call Socket.reset() to reset Socket")
        if on_message != None: self.message_callback = on_message
        def connect():
            self._sock = socket.socket()
            self._sock.settimeout(1)
            while self._alive:
                self._mode = Socket.MODE_CONNECTING
                try:
                    self._sock.connect((ip_addr, port))
                except socket.timeout:
                    continue
                except socket.error:
                    sleep(5, while_true = lambda: self._alive)
                    continue
                self._mode = Socket.MODE_CONNECTED
                if self.connect_callback != None: self.connect_callback()
                message = ""
                while self._alive:
                    try:
                        r = self._sock.recv(1)
                    except socket.timeout:
                        continue
                    except socket.error:
                        break
                    message += r
                    if r == "":
                        break
                    if r == "\n":
                        if self.message_callback != None:
                            self.message_callback(message)
                        message = ""
                self.disconnect_callback()
                self._sock = socket.socket()
                self._sock.settimeout(1)
        self._thread = threading.Thread(target=connect)
        self._thread.start()

    def send(self, message):
        if self._mode in Socket.MODES_CAN_SEND:
            self._sock.send(message)
        else:
            raise Socket.NotConnectedException(self._mode)

    def sendln(self, message = ""):
        self.send(message+"\n")

class BroadcastNamespace(BaseNamespace):
    sockets = []
    def recv_connect(self):
        self.sockets.append(self)
    def disconnect(self, silent = False):
        self.sockets.remove(self)
        BaseNamespace.disconnect(self, silent)
    @classmethod
    def broadcast(self, event, message):
        for socket in self.sockets:
            socket.emit(event, message)

## Other

## hide_arg_tooltip is a silly little thing.
##
## You can use hide_arg_tooltip(func) to get an object which will act like a
## function, but will not have an argument tooltip in IDLE. The docstring will
## still be shown, however. This is similar to how the default help and quit
## objects work.
##
## You can also use it as a decorator, like this:
##   @hide_arg_tooltip
##   def a():
##      """docstring"""
##      pass

def hide_arg_tooltip(func): return _function(func)

class _function:
    def __init__(self, func):
        self.func = func
        self.__doc__ = func.__doc__
    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)
    def __repr__(self):
        hex_id = hex(id(self))
        hex_id = hex_id[:2] + hex_id[2:].upper().rjust(8,'0')
        return "<%s %s at %s>" % (self.__class__.__name__, \
                                  self.func.__name__, hex_id)
    def __str__(self):
        return `self`
