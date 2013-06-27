import os, sys, md5
if 'modules' not in sys.path: sys.path.append('modules')
import util
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, ForeignKey
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
    
    parent_path = Column(String, ForeignKey('folders.path'))
    parent = relationship("Folder", remote_side = 'Folder.path',
                                    backref = 'children')
    hash = Column(String)

    def __init__(self, path, parent = None):
        self.path = path
        if parent:
            self.parent = parent
        else:
            self.root = True
        self.hash = get_contents_hash(path)

    @staticmethod
    def build(path = None, parent = None):
        path = path or "."
        folder = Folder(path, parent)
        for node in os.listdir(path):
            node = os.path.join(path, node)
            if os.path.isfile(node):
                node = File(node, folder)
                folder.files.append(node)
            else:
                node = Folder.build(node, folder)
        return folder

class File(Base):
    __tablename__ = 'files'

    path = Column(String, primary_key = True)
    supported = Column(Boolean)
    size = Column(BigInteger)
    
    track = Column(String)
    album = Column(String)
    artist = Column(String)
    album_artist = Column(String)

    artist_id = Column(Integer, ForeignKey("artists.id"))
    artist_ref = relationship("Artist", backref='songs')
    parent_path = Column(String, ForeignKey("folders.path"))
    parent = relationship("Folder", backref = 'files')

    def __init__(self, path, parent = None):
        self.path = path
        if parent:
            self.parent = parent
        if util.is_supported(path):
            self.supported = True
            tags = util.get_metadata(path)
            self.artist = tags[0]
            self.album_artist = tags[1]
            self.album = tags[2]
            self.track = tags[3]
        else:
            self.supported = False
        self.size = os.path.getsize(self.path)

    def get_dict(self):
        return {'track' : self.track,
                'album' : self.album,
                'artist': self.artist}

class Artist(Base):
    __tablename__ = 'artists'

    id = Column(Integer, primary_key = True)
    name = Column(String)

    def __init__(self, name):
        self.name = name

def connect(path_):
    global root, path, session, engine
    path = path_
    os.chdir(path)
    engine = create_engine('sqlite:///cdp.db')
    session = Session(bind = engine)
    Base.metadata.bind = engine
    Base.metadata.create_all()
    print "Reading database."
    root_query = session.query(Folder).filter(Folder.root == True)
    if root_query[:1]:
        root = root_query[0]
    else:
        Base.metadata.create_all()
        print "Builing database. This may take a while."
        root = Folder.build()
        session.add(root)
        session.commit()
        for song in session.query(File).filter(File.supported == True):
            artist_query = session.query(Artist)\
                                   .filter(Artist.name == song.album_artist)
            if artist_query[:1]:
                artist_query[0].songs.append(song)
            else:
                artist = Artist(song.album_artist)
                artist.songs.append(song)
                session.add(artist)
                session.commit()

def get_artists():
    return session.query(Artist)

## TODO: stuff to scan for filesystem changes
