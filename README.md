# CodeDay-Playlist #

Software to handle music at codeday

## Requirements ##

webserver.py requires:
* [Flask](http://flask.pocoo.org/)
* [Gevent-SocketIO](https://github.com/abourget/gevent-socketio/)
* [Mutagen](https://code.google.com/p/mutagen/)

organize.py and fix.py only require [Mutagen](https://code.google.com/p/mutagen/)

console.py requires:
* [VLC](http://www.videolan.org/vlc/) (realy just libvlc.dll)
* The [python bindings](http://git.videolan.org/?p=vlc/bindings/python.git;a=tree) for libvlc

The full list of dependencies, including subdependencies, can be found in /modules/README.md

## Usage ##

This software is intended to be put on a flashdrive or portable harddrive to house a music database for [CodeDay](http://codeday.org) hackathons. The following would get you started using it the way I do:

1. (optional) Dump the project on a clean flashdrive large enough to house a music library.
2. Dump properly tagged music into /automatically_add/.
3. Run webserver.py.
4. The web interface will be at your LAN IP address on port 80.

### Supported file formats ###
* mp3
* m4a
* ogg vorbis
* flac
