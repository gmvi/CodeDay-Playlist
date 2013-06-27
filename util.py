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

class UnsupportedFileTypeError(Exception): pass

FORMATS = {".mp3"  : EasyMP3,
           ".m4a"  : EasyMP4,
           ".ogg"  : OggVorbis,
           ".flac" : FLAC}

is_supported = lambda path: os.path.splitext(path)[1] in FORMATS

def get_info(audio, info):
    if audio.has_key(info):
        if type(audio[info]) == bool: return audio[info]
        else: return audio[info][0]
    else: return ""
    

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
    album_artist = get_info(audio, 'performer') or artist
    album = get_info(audio, 'album')
    title = get_info(audio, 'title')
    return (artist,
            album_artist,
            album,
            track)

class Artist():
    
    def __init__(self, path, name = None):
        self.path = path
        self.name = name

    def add(self, track):
        self.songs.append(track)

    def remove(self, track):
        self.songs.remove(track)

    def __eq__(self, other):
        return self.name == other.name

    def __str__(self):
        return "<Artist: %s>" % self.name

    def __repr__(self):
        return "Artist(%s)" % self.path

class Track():

    def __init__(self, path):
        self.path = path
        if path == None:
            self.track = None
            self.album = None
            self.artist= None
        else:
            self.track, self.album, self.artist = get_all_info(path)

    def __eq__(self, other):
        return self.path == other.path

    def __str__(self):
        return "<Track: %s by %s>" % (self.track, self.artist)

    def __repr__(self):
        return "Track(%s)" % self.path

    def get_dict(self):
        return {'track' : self.track,
                'album' : self.album,
                'artist': self.artist}

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

class Socket():
    class NotConnectedException(Exception): pass
    MODE_READY = MODE_NONE = 0
    MODE_LISTENING = 1
    MODE_ACCEPTED = 2
    MODE_CONNECTING = 3
    MODE_CONNECTED = 4
    MODE_ERROR = 5
    CAN_SEND_MODES = [MODE_ACCEPTED,
                      MODE_CONNECTED]
    
    def can_send(self):
        return self._mode in Socket.CAN_SEND_MODES
    
    def __init__(self, verbose = False):
        self._verbose = verbose
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
            pass
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
            self._sock2.settimeout(5)
            while self._alive:
                self._mode = Socket.MODE_LISTENING
                try:
                    self._sock, address = self._sock2.accept()
                except socket.timeout:
                    continue
                self._sock.settimeout(5)
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
            self._sock.settimeout(5)
            while self._alive:
                self._mode = Socket.MODE_CONNECTING
                try:
                    self._sock.connect((ip_addr, port))
                except socket.timeout:
                    continue
                except socket.error:
                    time.sleep(5)
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
                self._sock.settimeout(5)
        self._thread = threading.Thread(target=connect)
        self._thread.start()

    def send(self, message):
        if self._mode in (Socket.MODE_ACCEPTED, Socket.MODE_CONNECTED):
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

class TrackInfoNamespace(BroadcastNamespace):
    control_socket = None
    track = 'no track'

    def __init__(self, *args, **kwargs):
        if self.control_socket == None:
            raise ValueError("must attatch a control socket first")
        BroadcastNamespace.__init__(self, *args, **kwargs)
    
    @classmethod
    def attatch_control(self, control_sock):
        self.control_socket = control_sock
    
    @classmethod
    def update_track(self, track):
        self.track = track
        self.broadcast('update', json.dumps(track))
        
    def on_request(self, message):
        if message == 'track':
            self.emit('track', json.dumps(self.track))
        else:
            self.emit('error', 'improper request')
            
    def on_command(self, message):
        if message in ['next', 'pause', 'previous']:
            j = json.dumps({"type" : "command",
                            "data" :  message})
            try:
                self.control_socket.sendln(j)
            except ValueError:
                self.emit('error', "no program to control")
        else:
            self.emit('error', 'not a command')

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
##       """docstring"""
##       pass

def hide_arg_tooltip(func): return _function(func)

class _function:
	def __init__(self, func):
		self.func = func
		self.__doc__ = func.__doc__
	def __call__(self, *args, **kwargs):
		return self.func(*args, **kwargs)
	def __repr__(self):
            hex_id = hex(id(self))
            hex_id = hex_id[:2] + hex_id[2:].upper()
            return "<%s %s at %s>" % (self.__class__.__name__, \
                                      self.func.__name__, hex_id)
        def __str__(self):
            return `self`
