import base64, json, os, re, socket, sys, threading, time, warnings
if 'modules' not in sys.path: sys.path.insert(0, 'modules')
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
EasyMP3 = lambda filename: MP3(filename, ID3=EasyID3)
from mutagen.easymp4 import EasyMP4
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3NoHeaderError
from mutagen.flac import FLAC
from flask import request, Response, send_file
from socketio.namespace import BaseNamespace
from random import choice
## NOTE: util must be imported before settings, so that settings.py and
##       settings_defauilt.py can be handled properly
try:
  import settings
  del settings
except:
  import settings_default
  sys.modules['settings'] = settings_default
  del settings_default

from settings import DEBUG

######## JSON SETUP ########

PRETTYPRINT = DEBUG

class JSONEncoder(json.JSONEncoder):
  def default(self, o):
    try:
      return o.to_json()
    except AttributeError:
      json.JSONEncoder.default(self, o)
if PRETTYPRINT:
  encoder = JSONEncoder(indent=2, separators=(',', ': '))
else:
  encoder = JSONEncoder()

encode = encoder.encode

def convert_to_jsonable(o):
  try:
    o = o.to_json.__call__()
  except AttributeError:
    pass
  if isinstance(o, dict):
    for key in o:
      o[key] = convert_to_jsonable(o[key])
    return o
  elif hasattr(o, '__iter__') and not isinstance(o, basestring):
    return [convert_to_jsonable(i) for i in o]
  else:
    return o

#### UTILITY METHODS ####

def sleep(seconds, while_true = None, test_interval = .1):
  start = time.time()
  if while_true == None:
    time.sleep(seconds)
    return
  end = start+seconds
  while while_true() and end - time.time() > 0:
    time.sleep(min(test_interval, end - time.time()))

#### audio metadata ####

# files

class UnsupportedFileTypeError(Exception): pass

is_supported = lambda path: os.path.splitext(path)[1] in FORMATS

# audio files

FORMATS = {".mp3"  : EasyMP3,
           ".m4a"  : EasyMP4,
           ".mp4"  : EasyMP4,
           ".ogg"  : OggVorbis,
           ".flac" : FLAC}

def allowed_file(filename):
  split = os.path.splitext(filename)
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

def get_metadatum(audio, metadatum, default = None):
  if audio.has_key(metadatum):
    if type(audio[metadatum]) == bool: return audio[metadatum]
    else: return audio[metadatum][0]
  else: return default

def get_song_info(filepath):
  audio = open_audio_file(filepath)
  artist = get_metadatum(audio, 'artist')
  performer = get_metadatum(audio, 'performer')
  album_artist = performer or artist
  track_artist = artist if artist != album_artist else None
  title = get_metadatum(audio, 'title', os.path.splitext(os.path.split(filepath)[1])[0])
  bitrate = audio.info.bitrate if hasattr(audio.info, 'bitrate') else None
  return {"artist" : album_artist,
          "track_performer" : track_artist,
          "album" : get_metadatum(audio, 'album'),
          "title" : title,
          "length" : audio.info.length,
          "bitrate" : bitrate,
          "mime" : audio.mime[0],
          "size" : os.path.getsize(filepath)}

def overwrite_metadata(filepath, **kwargs):
  audio = open_audio_file(filepath)
  for kwarg in kwargs:
    audio[kwarg] = kwargs[kwarg]
  audio.save()

#### Flask helpers ####

# send_file_partial is inspired in part by other send_file_partial's written by
# Jason A. Donenfeld <http://git.zx2c4.com/zmusic-ng/tree/backend/zmusic/streams.py>
# and  Mark Watkinson <https://github.com/markwatkinson/music/blob/master/lib/http.py>

def partial_file_iter(f, offset = 0, length = -1, chunk=4096):
  if offset < 0 or chunk <= 0 or length == 0:
    return
  f.seek(offset)
  while length != 0:
    if length < 0:
      data = f.read(chunk)
    else:
      size = min(length, chunk)
      length -= size
      data = f.read(size)
    if len(data) == 0:
      return
    else:
      yield data

def send_file_partial(path, mimetype, attachment_filename = None):
  range_header = request.headers.get('Range', None)
  size = os.path.getsize(path)
  if not range_header:
    rv = send_file(path, mimetype)
    rv.headers.add('Content-Length', size)
  else:    
    byte1, byte2 = 0, None
    
    m = re.search('(\d+)-(\d*)', range_header)
    g = m.groups()
    
    if g[0]: byte1 = int(g[0])
    if g[1]: byte2 = int(g[1])

    length = size - byte1
    if byte2 is not None:
      length = byte2 - byte1

    f = open(path, 'rb')

    rv = Response(partial_file_iter(f, byte1, length), 
                  206,
                  mimetype=mimetype, 
                  direct_passthrough=True)
    rv.headers.add('Content-Range', 'bytes {0}-{1}/{2}'.format(byte1, byte1 + length - 1, size))
    rv.headers.add('Content-Length', length)
  rv.headers.add('Accept-Ranges', 'bytes')
  if attachment_filename:
    rv.headers.add('Content-Disposition', 'attachment', filename=attachment_filename)

  return rv

def partial_data_iter(data, offset = 0, length = -1, chunk=4096):
  if offset < 0 or chunk <= 0 or length == 0:
    return
  sent = 0
  if length == None or length > len(data) - offset:
    length = length, len(data) - offset
  while sent < length-chunk:
    send = data[offset+sent:offset+sent+chunk]
    sent += chunk
    yield send
  yield data[offset+sent:offset+length]


## print_headers is a function wrapper which causes all headers to be printed
## to stdout for debugging. must be wrapped with any routing
def print_headers(func):
  def wrapped_func(*args, **kwargs):
    print "Request Headers:"
    for item in request.headers.iteritems():
      print '%s: %s' % item
    response = func(*args, **kwargs)
    print 'Response Headers:'
    for item in response.headers.iteritems():
      print '%s: %s' % item
    return response
  return wrapped_func

#### Utility Classes ####
class ForgetfulList(list):
  buffer_size = 0
  def append(self, obj): raise NotImplementedError()
  def extend(self, iterable): raise NotImplementedError()

  def __init__(self, size, iterable = None):
    if iterable != None:
      list.__init__(self, iterable)
      if len(self) > self.buffer_size:
        del self[self.buffer_size:]
    else: list.__init__(self)
    if type(size) != int:
      raise TypeError("size must be int")
    self.buffer_size = size

  def __repr__(self):
    return "%s(%s, %s)" % (self.__class__.__name__,
                 self.buffer_size,
                 list.__repr__(self))

  def insert(self, index, obj):
    list.insert(self, index, obj)
    if len(self) > self.buffer_size:
      del self[self.buffer_size:]

class WriteWrapper:
  """WriteWrapper wraps around a writable object (an object which has a 'write'
function). When something is written to the WriteWrapper, it is passed
through the provided filter function before being written to the writable.

For example, to limit all lines printed to stdout to at most 80 characters:
  def trunc_80(o):
    o = str(o)
    end = '\n' * o.endswith('\n')
    o = "\n".join(map(lambda x: x[:min(80, len(x))], o.splitlines()))
    return o + end
  sys.stdout = WriteWrapper(sys.stdout, trunc_80)
"""
  def __init__(self, writable, filter_function):
    if not hasattr(writable, "write") or not hasattr(writable.write, '__call__'):
      raise ValueError("writable must have a 'write' attribute, and it must be callable")
    self.__wrapped = writable
    self.__write = filter_function
  def __getattr__(self, attr):
    return self.__wrapped.__getattribute__(attr)
  def write(self, o):
    self.__wrapped.write(self.__write(o))

#TODO: support wait_for(Socket.SIGNAL_CONNECT) and wait_for(SIGNAL_DISCONNECT)
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
  #attribute type (unicode, int, list, dict, or None)
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
      time.sleep(.5)
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
  def on_connect(self):
    self.__class__.sockets.append(self)
  def disconnect(self, silent = False):
    if self in self.sockets:
      self.sockets.remove(self)
    BaseNamespace.disconnect(self, silent)
  @classmethod
  def broadcast(cls, event, message = None):
    print "broadcasting: %s, %s" % (event, message)
    for socket in cls.sockets:
      socket.emit(event, convert_to_jsonable(message))
  def emit(self, *args, **kwargs):
    if len(args) == 2:
      args = (args[0], convert_to_jsonable(args[1]))
    if self not in self.sockets:
      self.sockets.append(self)
    BaseNamespace.emit(self, *args, **kwargs)
