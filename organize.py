error = False
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3
import os, glob, shutil

class FileAlreadyExistsError(Exception): pass
class UnsupportedFileTypeError(Exception): pass

## SETTINGS/

AUTO_ORGANIZE = False
PATTERNS = [("music/2ampool", "music/2am"),
            ("music/mainpool", "music/main")]

## /SETTINGS

EasyMP3 = lambda filename: MP3(filename, ID3=EasyID3)

FORMATS = {".mp3" : EasyMP3,
           ".m4a" : EasyMP4}

trackFormat = lambda number: "0"*(len(number)==1) + number

def sanitize(string):
    string = string.strip()
    string = string.replace("/", "-").replace("\\", "-").replace("*", "-")
    string = string.replace(":", "_").replace("?", "_").replace("|", "_")
    string = string.replace('"', "'")
    return unicode_to_string(string)

def unicode_to_string(u):
    try:
        return str(u)
    except UnicodeEncodeError:
        return "".join(map(lambda u: chr(ord(u)), u))

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
    date = get_info(audio, 'date')
    tracknumber = get_info(audio, 'tracknumber')
    title = get_info(audio, 'title')
    is_compil = get_info(audio, 'compilation') or False
    return (sanitize(artist),
            sanitize(album),
            sanitize(date),
            sanitize(trackFormat(tracknumber)),
            sanitize(title),
            ext,
            is_compil)

def moveFile(src, dst):
    def year_from_folder(folder):
        if is_compil:
            return int(os.path.split(folder)[1][:-1].split('(')[1])
        else:
            return int(os.path.split(folder)[1][1:].split(')')[0])
    if not os.path.exists(dst): os.mkdir(dst)
    try:
        (artist, album, date, tracknum, title, ext, is_compil) = get_all_info(src)
    except UnsupportedFileTypeError:
        return
    date = date.split('-')[0]
    tracknum = tracknum.split('/')[0].split('-')[0]
    if tracknum: tracknum += " "
    if not title:
        title = os.path.splitext(os.path.split(src)[1])[0]
    name = tracknum + title + ext
    if artist:
        if not is_compil and artist.lower() not in map(str.lower, os.listdir(dst)):
            os.mkdir(os.path.join(dst, artist))
        if not is_compil: dst = os.path.join(dst, artist)
        if album:
            if is_compil: album_already_exists = glob.glob(os.path.join(dst, album + bool(date)*" (*)").replace("[", "*"))
            else: album_already_exists = glob.glob(os.path.join(dst, bool(date)*"(*) " + album).replace("[", "*"))
            if album_already_exists and (not(date) or year_from_folder(album_already_exists[0]) >= int(date)):
                dst = album_already_exists[0]
            else:
                if is_compil: dst = os.path.join(dst, album + bool(date)*(" (%s)"%date))
                else: dst = os.path.join(dst, bool(date)*("(%s) "%date) + album)
                os.mkdir(dst)
    if not os.path.exists(os.path.join(dst, name)):
        shutil.move(src, os.path.join(dst, name))

def handle(f, dst):
    global error
    if os.path.splitext(f)[1] in FORMATS:
        try: moveFile(f, dst)
        except Exception as e:
            print e
            error = True

def handle_dir(src, dst):
    for f in map(lambda f: os.path.join(src, f), os.listdir(src)):
        if os.path.isdir(f):
            handle_dir(f, dst)
            if not os.listdir(f):
                os.rmdir(f)
        else:
            handle(f, dst)

def main():
##    map(handle, [f for f in os.listdir("\\")
##                 if os.path.isfile(f)
##                 and os.path.splitext(f)[1] in FORMATS])
##    handle_dir("\\.input")
    src = raw_input("src dir: ")
    out = raw_input("out dir: ")
    if src and out:
        handle_dir(src, out)
    else:
        raw_input("bad input")

main()

if error: raw_input("Something unusual happened.")
else: print "DONE"
