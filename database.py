import os, sys
if 'modules' not in sys.path: sys.path.insert(0, 'modules')
import util
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, BigInteger, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, backref

Base = declarative_base()
Session = sessionmaker()
class MultipleRootError(Exception): pass
class NoRootError(Exception): pass

def get_contents_hash(path):
    contents = os.listdir(path)
    mr_itchy = md5.md5()
    for node in contents:
        mr_itchy.update(node)
    return mr_itchy.hexdigest()

class Folder(Base):
    __tablename__ = 'folders'

    path = Column(String, primary_key = True)
    root = Column(Boolean)
    folders = relationship("Folder", backref=backref('parent'))
    files = relationship("File", backref=backref('parent'))
    hash = Column(String)

    def __init__(self, path, parent = None):
        self.path = path
        if parent:
            self.parent = parent
        else:
            self.root = True
        self.hash = get_contents_hash(path)

    @classmethod
    def build(path, parent = None):
        folder = Folder(path, parent)
        for node in os.listdir(path):
            node = os.path.join(path, node)
            if os.path.isfile(node):
                node = File(node, folder)
                folder.files.append(node)
            else:
                node = build_folder(node, folder)
                folder.folders.append(node)
        return folder

class File(Base):
    __tablename__ = 'files'

    path = Column(String, primary_key = True)
    supported = Column(Boolean)
    size = Colum(BigInteger)
    
    track = Column(String)
    album = Column(String)
    artist = Column(String)
    album_artist = Column(String)

    def __init__(self, path):
        self.path = path
        if util.is_supported(path):
            self.supported = True
            self.artist, self.album_artist, self.album, self.track \
                = util.get_metadata(path)
        else: self.supported = False
        self.size = os.path.getsize(self.path)

class Artist(Base):
    __tablename__ = 'artists'

    id = Column(Integer, primary_key = True)
    name = Column(String)
    songs = relationship('File', backref = backref('artist_ref'))

    def __init__(self, name):
        self.name = name

class DBController():
    def __init__(self, path):
        self.path = path
        #self.connect()

    def connect():
        os.chdir(self.path)
        self.engine = create_engine('sqlite:///' + \
                                    os.path.join(self.path, 'cdp.db'))
        self.session = Session(bind = self.engine)
        print "Reading database."
        if 'folders' in Base.metadata.tables.keys():
            root_query = session.query(Folder).filter(Folder.root == True)
            if len(root) == 1:
                self.root = root_query[0]
            elif len(root) > 1: raise MultipleRootError()
            else: raise NoRootError()
        else:
            print "Builing database. This may take a while."
            Base.metadata.create_all(self.engine)
            self.root = Folder.build(path)
            session.add(self.root)
            session.commit()
            for song in session.query(File).filter(File.supported == True):
                artist_query = session.query(Artist)\
                                      .filter(Artist.name==song.album_artist)
                if artist_query:
                    artist_query[0].songs.append(song)
                else:
                    artist = Artist(track.album_artist)
                    artist.songs.append(song)
                    session.add(artist)
                    session.commit()

    def get_artists(self):
        return session.query(Artist)

## TODO: stuff to scan for filesystem changes
