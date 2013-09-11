import os, sys, time, socket, threading, json, warnings, base64
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
    path = path.split("\\")
    path2 = []
    for seg in path:
        path2 += seg.split("/")
    return path2

# audio files

FORMATS = {".mp3"  : EasyMP3,
           ".m4a"  : EasyMP4,
           ".ogg"  : OggVorbis,
           ".flac" : FLAC}

def allowed_file(filename):
    split = filename.rsplit('.', 1)
    return len(split) > 1 and split[1] in FORMATS

def open_audio_file(filepath):
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
    return audio

def get_metadatum(audio, metadatum):
    if audio.has_key(metadatum):
        if type(audio[metadatum]) == bool: return audio[metadatum]
        else: return audio[metadatum][0]
    else: return ""

def get_metadata(filepath):
    audio = open_audio_file(filepath)
    artist = get_metadatum(audio, 'artist')
    return {"artist" : artist,
            "performer" : get_metadatum(audio, 'performer'),
            "album": get_metadatum(audio, 'album'),
            "title" : get_metadatum(audio, 'title')}

def translate(datum):
    if datum == "performer":
        return "album artist"
    return datum

def overwrite_metadata(filepath, **kwargs):
    audio = open_audio_file(filepath)
    for kwarg in kwargs:
        audio[kwarg] = kwargs[kwarg]
    audio.save()

## Utility Classes
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

#TODO: support wait_for(Socket.SIGNAL_CONNECT) and SIGNAL_DISCONNECT
class Socket():
    class SocketException(Exception): pass
    class NotConnectedException(SocketException): pass
    class PortInUseException(SocketException): pass

    __sockets = []
    
    MODE_READY = MODE_NONE = 0
    MODE_LISTENING = 1
    MODE_ACCEPTED = 2
    MODE_CONNECTING = 3
    MODE_CONNECTED = 4
    MODE_ERROR = 5
    MODE_DEAD = 6
    MODES_CAN_SEND = [MODE_ACCEPTED,
                      MODE_CONNECTED]
    SIGNAL_CONNECT = 10
    SIGNAL_DISCONNECT = 11
    SIGNAL_MESSAGE = 12
    
    def can_send(self):
        return self._mode in Socket.MODES_CAN_SEND
    
    def __init__(self):
        self.__sockets.append(self)
        self._sock = None
        self._sock2 = None
        self.message_callback = None
        self.connect_callback = None
        self.disconnect_callback = None
        self._alive = True
        self._mode = Socket.MODE_NONE
        self._thread = None
        self.callbacks = {}
        self.waiting = {}

    def kill(self):
        self._alive = False
        self._mode = Socket.MODE_DEAD

    @classmethod
    def kill_all(cls):
        for socket in cls.__sockets[:]:
            socket.kill()
            cls.__sockets.remove(socket)

    #on_connect callback must take no arguments
    def on_connect(self, callback):
        self.connect_callback = callback
    def remove_on_connect(self):
        self.connect_callback = None

    #on_disconnect callback must take no arguments
    def on_disconnect(self, callback):
        self.disconnect_callback = callback
    def remove_on_disconnect(self):
        self.disconnect = None

    #on_message callback must take a string argument
    def on_message(self, callback):
        self.message_callback = callback
    def remove_on_message(self):
        self.message_callback = None

    #on callback must take a single argument, which may be any valid JSON
    #attribute type (unicode, int, list, or dict)
    def on(self, type, callback):
        if not issubclass(type.__class__, basestring):
            raise TypeError("type should be string")
        self.callbacks[type] = callback
    def remove_on(self, type):
        if type in self.callbacks:
            del self.callbacks[type]

    #on_other callback must take a string argument and a JSON-attribute argument
    def on_other(self, callback):
        self.other_callback = callback
    def remove_on_other(self):
        self.other_callback = None

    def wait_for(self, type):
        key = base64.b64encode(os.urandom(3))
        if type not in self.waiting:
            self.waiting[type] = {}
        self.waiting[type][key] = None
        while self._alive and not self.waiting[type][key]:
            sleep(.5)
        data = self.waiting[type][key]
        del self.waiting[type][key]
        if type == Socket.SIGNAL_CONNECT or \
           type == Socket.SIGNAL_DISCONNECT:
            return
        else:
            return data

    def _handle(self, message):
        if Socket.SIGNAL_MESSAGE in self.waiting:
            for key in self.waiting[Socket.SIGNAL_MESSAGE]:
                self.waiting[Socket.SIGNAL_MESSAGE][key] = message
        if self.message_callback:
            self.message_callback(message)
        try:
            obj = json.loads(message)
        except ValueError:
            return
        if 'type' not in obj or 'data' not in obj:
            return
        type = obj['type']
        data = obj['data']
        if type in self.waiting:
            for key in self.waiting[type]:
                self.waiting[type][key] = data
        if type in self.callbacks:
            self.callbacks[type](data)
        else:
            self.other_callback(type, data)
        
    def listen(self, ip_addr, port):
        if self._mode != Socket.MODE_NONE:
            return ValueError("Socket object already in use.")# Call Socket.reset() to reset Socket")
        self._sock2 = socket.socket()
        try: self._sock2.bind((ip_addr, port))
        except socket.error as e:
            if e.errno == 10048: raise Socket.PortInUseException()
            else: raise e
        self._sock2.listen(1)
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
                if self.connect_callback: self.connect_callback()
                sig = Socket.SIGNAL_CONNECT
                if sig in self.waiting:
                    for key in self.waiting[sig]:
                        self.waiting[sig] = True
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
                        self._handle(message)
                        message = ""
                if self.disconnect_callback: self.disconnect_callback()
                sig = Socket.SIGNAL_DISCONNECT
                if sig in self.waiting:
                    for key in self.waiting[sig]:
                        self.waiting[sig] = True
                self._sock.close()
            self._sock2.close()
        self._thread = threading.Thread(target=accept)
        self._thread.start()

    def connect(self, ip_addr, port):
        if self._mode != Socket.MODE_NONE:
            return ValueError("Socket object already in use.")# Call Socket.reset() to reset Socket")
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
                if self.connect_callback: self.connect_callback()
                sig = Socket.SIGNAL_CONNECT
                if sig in self.waiting:
                    for key in self.waiting[sig]:
                        self.waiting[sig] = True
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
                        self._handle(message)
                        message = ""
                if self.disconnect_callback: self.disconnect_callback()
                sig = Socket.SIGNAL_DISCONNECT
                if sig in self.waiting:
                    for key in self.waiting[sig]:
                        self.waiting[sig] = True
                self._sock = socket.socket()
                self._sock.settimeout(1)
            self._sock.close()
        self._thread = threading.Thread(target=connect)
        self._thread.start()

    def send_message(self, message):
        pos = message.find("\n")
        if pos == -1:
            message += "\n"
        elif pos < len(message)-1:
            raise ValueError("Individual messages must be sent using individual 'send_message' calls.")
        if self._mode in Socket.MODES_CAN_SEND:
            self._sock.send(message)
        else:
            raise Socket.NotConnectedException(self._mode)

    def send(self, type, serializable):
        string = json.dumps({"type" : type,
                             "data" : serializable})
        self.send_message(string)

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
