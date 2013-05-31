# CodeDay-Playlist #

Software to handle music at codeday

## Requirements ##

organize.py and fix.py require [Mutagen](https://code.google.com/p/mutagen/)

program.py requires:
* [Flask](http://flask.pocoo.org/)
* [Mutagen](https://code.google.com/p/mutagen/)
* [VLC](http://www.videolan.org/vlc/) (realy just libvlc)
* The [python bindings](http://git.videolan.org/?p=vlc/bindings/python.git;a=tree) for libvlc

## Usage ##

This software is intended to be put on a flashdrive to house a music database for Seattle [CodeDay](CodeDay.org) hackathons. The following would get you started using it the way I do:

1. (optional) Dump the project on a clean flashdrive large enough to house a music library.
2. Dump music into /music/mainpool.
3. Use organize.py to organize /music/mainpool into /music/main.
4. Check that nothing got screwed up from bad ID3 tags. If anything is organized wrong due to imporper tagging, you can reorganize it yourself, and run fix.py on each artist and album folder directly containing music files. It's not super user-friendly; read the code first.
5. Run program.py, and point it to /music/main. It will take a while to build the database.
6. The web interface will be at your LAN IP address on port 80.
7. (optional) You can create other libraries as /music/*, or point program.py to your another library's root node, provided it follows a &lt;root&gt;/&lt;artist&gt;/&lt;album&gt;/&lt;track&gt; structure. Any filename formatting scheme is fine, provided metadata is present, and artistless files in the root directory or files directly under artist folders will be handled properly as well.

### Supported file formats ##

Currently:  
.mp3  
.m4a  

Comming Soon:  
.ogg  
.flac  
