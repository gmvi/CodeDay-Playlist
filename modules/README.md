Place modules here to make CodeDay-Playlist portable to any computer with python 2.7 (and possibly lower); libvlc.dll and vlc.py are only required to use the local console (console.py) in lieu of the http interface

Modules you should have:
========================
- flask (flask/)
- gevent-socketio (socketio/)
  - gevent (gevent/)
    - greenlet (greenlet.py, greenlet.pyd)
    - libevent (?)
  - geventwebsocket (geventwebsocket/)
- mutagen (mutagen/)
- python bindings for Libvlc (vlc.py)
- libvlc.dll (?)

*More info here later*