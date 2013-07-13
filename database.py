import os, sys, md5, time
if 'modules' not in sys.path: sys.path.append('modules')
import util, organize
from sqlalchemy import create_engine, event
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, backref, \
                           joinedload

Base = declarative_base()
Session = sessionmaker()
class MultipleRootError(Exception):
    def __init__(self, count):
        message = "Error: expected one root Folder entry; found %s." % count
        Exception.__init__(message)

# Paths are stored in cdp.db databases as if cdp.db resided in os.curdir
# In practice, the database is loaded from program.py, two levels above
# the database. This database controller must be aware of that when
# using os.path methods, etc. Thus path from the database root is called 'path'
# and path from os.curdir is called 'rel_path'.
path_to_root = None
root_join = lambda a: os.path.join(path_to_root, a)
artists = []

CONTENTS_HASH_IGNORE = ["cdp.db-journal"]
#safe
def get_contents_hash(path):
    mr_itchy = md5.md5()
    contents = os.listdir(path)
    for node in CONTENTS_HASH_IGNORE:
        if node in contents:
            contents.remove(node)
    for node in contents:
        mr_itchy.update(node)
    return mr_itchy.hexdigest()

#safe
load_listener = lambda target, context: target.on_load()

#externally safe unless stated
class Folder(Base):
    __tablename__ = 'folders'

    path = Column(String, primary_key = True)
    def __eq__(self, other):
        return self.path == other.path
    root = Column(Boolean)
    
    parent_path = Column(String, ForeignKey('folders.path'))
    parent = relationship("Folder",
                          remote_side="Folder.path",
                          backref = "children")
    hash = Column(String)

    #evaluate
    def __init__(self, path, parent = None):
        self.path = path
        self.rel_path = root_join(path)
        if parent:
            self.parent = parent
        else:
            self.root = True
        self.update_hash()

    #evaluate
    @staticmethod
    def build(path = None, parent = None):
        rel_path = root_join(path or ".")
        folder = Folder(path or ".", parent)
        for node in os.listdir(rel_path):
            rel_node = os.path.join(rel_path, node)
            if path: node = os.path.join(path, node)
            if os.path.isfile(rel_node):
                node = File(node, folder)
                folder.files.append(node)
            else:
                node = Folder.build(node, folder)
        return folder

    def update_hash(self):
        self.hash = get_contents_hash(self.rel_path)

    def check_fs(self):
        return os.path.exists(self.rel_path) \
               and self.hash == get_contents_hash(self.rel_path)

    def on_load(self):
        self.rel_path = root_join(self.path)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "<Folder: '%s'>" % self.path

event.listen(Folder, 'load', load_listener)

class File(Base):
    __tablename__ = 'files'

    path = Column(String, primary_key = True)
    def __eq__(self, other):
        return self.path == other.path
    supported = Column(Boolean)
    size = Column(BigInteger)
    
    track = Column(String)
    album = Column(String)
    artist = Column(String)
    album_artist = Column(String)

    artist_id = Column(Integer, ForeignKey("artists.id"))
    parent_path = Column(String, ForeignKey("folders.path"))
    parent = relationship(Folder, backref = "files")

    #evaluate
    def __init__(self, path, parent = None):
        self.path = path
        if parent:
            self.parent = parent
        if util.is_supported(root_join(path)):
            self.supported = True
            tags = util.get_metadata(root_join(path))
            self.artist = tags[0]
            self.album_artist = tags[1]
            self.album = tags[2]
            self.track = tags[3]
        else:
            self.supported = False
        self.size = os.path.getsize(root_join(self.path))

        self.rel_path = root_join(self.path)
        self.change_alerted = False

    #safe
    def get_dict(self):
        return {'track' : self.track,
                'album' : self.album,
                'artist': self.artist}

    #safe
    def check_fs(self):
        return os.path.exists(self.rel_path) \
               and self.supported \
               and os.path.getsize(self.rel_path) == self.size

    #safe
    def on_load(self):
        self.rel_path = root_join(self.path)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "<File: '%s'>" % self.path

event.listen(File, 'load', load_listener)

class Artist(Base):
    __tablename__ = 'artists'

    id = Column(Integer, primary_key = True)
    def __eq__(self, other):
        return self.id == other.id
    name = Column(String)
    songs = relationship("File", backref="artist_ref")

    #evaluate
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return `self`
    
    def __repr__(self):
        return "<Artist \"%s\" with %s song%s>" % (self.name, len(self.songs),
                                           '' if len(self.songs) == 1 else 's')

#safe
def connect(root_path, db_path = None):
    global root, path_to_root, engine, artists
    path_to_root = root_path
    if not db_path:
        db_path = 'sqlite:///' + root_join('cdp.db')
    engine = create_engine(db_path)
    engine.text_factory = str
    session = Session(bind = engine)
    Base.metadata.bind = engine
    Base.metadata.create_all()
    print "Reading database."
    root = get_root(session)
    if not root:
        print "Builing database. This may take a while."
        build(session)
        root = get_root(session)
        session.commit()
    artists = load_artists(session)
    session.close()
    session = None

# must be called after tables have been created
#internal
def build(session):
    root = Folder.build()
    session.add(root)
    for song in session.query(File).filter(File.supported == True):
        add_to_artist(session, song)

def add_to_artist(session, file_object):
        artist_query = session.query(Artist) \
                              .filter(Artist.name == file_object.album_artist)
        if artist_query.count():
            artist_query.one().songs.append(file_object)
        else:
            artist = Artist(file_object.album_artist)
            artist.songs.append(file_object)
            session.add(artist)

#internal
def add_dir(src, delete = False):
    session = Session()
    root = get_root(session)
    def handle(src, errors = []):
        for f in map(lambda f: os.path.join(src, f), os.listdir(src)):
            if os.path.isdir(f):
                errors = handle(f, errors)
                if not os.listdir(f):
                    os.rmdir(f)
            elif os.path.splitext(f)[1] in util.FORMATS:
                file_path, e = organize.moveFile(f, path_to_root, delete)
                if e:
                    errors += (f, file_path, e)
                else:
                    build_structure(session, file_path, root = root)
        return errors
    errors = handle(src)
    session.commit()
    session.close()
    return errors

#internal
#rename
def build_structure(session, file_path, root = None):
    if not root: root = get_root(session)
    path = util.path_relative_to(path_to_root, file_path)
    pathsplit = util.split(path)
    file_segment = pathsplit.pop()
    cumulative_path = ""
    root.update_hash()
    parent = root
    for segment in pathsplit:
        cumulative_path = os.path.join(cumulative_path, segment)
        folder_q = session.query(Folder) \
                   .filter(Folder.path == cumulative_path)
        if folder_q.count():
            folder = folder_q.one()
            folder.update_hash()
            parent = folder
        else:
            parent = Folder(cumulative_path, parent)
    f = File(path, parent)
    add_to_artist(session, f)

#external
def remove(file_object):
    """Removes a file from the database. Updates the filesystem accordingly"""
    if type(file_object) is not File:
        raise TypeError("file_object must be of type database.File")
    session = Session()
    file_object = session.query(File).filter(File.path == file_object.path).one()
    parent = file_object.parent
    parent.files.remove(file_object)
    artist = file_object.artist_ref
    artist.songs.remove(file_object)
    os.remove(file_object.rel_path)
    session.delete(file_object)
    parent = remove_if_empty(session, parent)
    if parent: parent.update_hash() # parent is only none if root is removed
    if len(artist.songs) == 0:
        session.delete(artist)
    session.commit()
    session.close()

#internal
def remove_if_empty(session, folder_object):
    """Returns the parent of the highest-up removed folder.
Returns the folder itself if not empty.
Returns None if root is removed, which it shouldn't be."""
    while len(os.listdir(folder_object.rel_path)) == 0:
        parent = folder_object.parent
        os.rmdir(folder_object.rel_path)
        session.delete(folder_object)
        folder_object = parent
        if not folder_object: # This shouldn't happen, root is never empty
            break             # because of cdp.db file.
    return folder_object

#internal
def get_root(session):
    query = session.query(Folder).filter(Folder.root == True) \
##                                 .options(joinedload("*"),
##                                          joinedload("*.*")
##                                          )
    count = query.count()
    if count == 1:
        return query.one()
    elif count > 1:
        raise MultipleRootError(query.count())

#internal
def load_artists(session):
    query = session.query(Artist).options(joinedload("songs"))
    if query.count(): return query.all()

#external
def hard_reset():
    global root
    session = Session()
    print "Rebuilding database from scratch. This may take a while."
    Base.metadata.drop_all()
    session.commit()
    Base.metadata.create_all()
    build(session)
    session.commit()
    artists = load_artists(session)
    root = get_root(session)
    session.close()

#safe
def scan(wait_seconds = (0.1)):
    session = Session()
    def scan(item, dirty = []):
        if (type(item) != File or item.supported) \
           and not item.check_fs():
            dirty.append(item)
        time.sleep(wait_seconds)
        if type(item) == Folder:
            for i in item.children + item.files:
                scan(i, dirty)
        return dirty
    dirty = scan(get_root(session))
    session.close()
    return dirty
