import os, sys
if 'modules' not in sys.path: sys.path.insert(0, 'modules')
import util
from sqlalchemy import create_engine
from sqlalchemy import ForeignKey, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, backref

Base = declarative_base()
session = None
root = None

class Folder(Base):
    __tablename__ = 'folders'

    path = Column(String, primary_key = True)
    root = Column(Boolean)
    folders = relationship("Folder", backref=backref('parent'))
    files = relationship("File", backref=backref('parent'))

    def __init__(self, path, parent = None):
        self.path = path
        if parent:
            self.parent = parent
        else:
            self.root = True

class File(Base):
    __tablename__ = 'files'

    path = Column(String, primary_key = True)
    supported = Column(Boolean)
    
    track = Column(String)
    album = Column(String)
    artist = Column(String)

    def __init__(self, path, parent):
        self.path = path
        self.parent = parent

class Artist(Base):
    __tablename__ = 'artists'

    id = Column(Integer, primary_key = True)
    name = Column(String)
    songs = relationship('File', backref = backref('artist'))

def connect(path):
    global session, engine, root
    root = path
    os.chdir(path)
    engine = create_engine('sqlite:///' + os.path.join(root, 'cdp.db'))
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    session = Session()

def build():
    global session, engine, root
    print "Reading database."
    session = database.connect(path)
    if engine.dialect.has_table(engine.connect(), "folders"):
        root = session.query(Folder)
        return root
    else:
        print "Builing database. This may take a while."
        root = build_folder(path)
        session.add(root)
        session.commit()
        #[compile artists table here, by album artist if available]

def build_folder(path, parent = None):
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
    
# def remove_track() #<-- later

## TODO: stuff to scan for filesystem changes

## TODO: move program.choose code into this module,
##       'recently played' queues as well.

# let's not have session even be given to program by default.
# what use would it have for direct control over session anyway?
# For now, it just needs database.load(path) and database.choose_next().
# Later I can add database.record_skipped() and database.record_liked()
# database.py can even control deletion of frequently skipped tracks, and
# integration of track pools into their main directories.

## TODO: handle differences between artist and album artist
