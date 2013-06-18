import os
import util
from sqlalchemy import create_engine, ForeignKey, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, backref

Base = declarative_base()

class Artist(util.Artist, Base):
    __tablename__ = 'artists'
    
    id = Column(Integer, primary_key = True)
    name = Column(String)
    path = Column(String)

class Track(util.Track, Base):
    __tablename__ = 'tracks'

    id = Column(Integer, primary_key = True)
    artist_id = Column(Integer, ForeignKey(Artist.id))
    artist_ref = relationship(Artist, backref=backref('songs'))
    
    path = Column(String)
    track = Column(String)
    album = Column(String)
    artist = Column(String)

def connect(path):
    engine = create_engine('sqlite:///' + os.path.join(path, 'cdp.db'))
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    return Session()
    # integrate session as global for class access

# def remove_track()

# add initialization code

## TODO: stuff to scan for filesystem changes

## TODO: move program.choose code into this module,
##       perhaps 'recently played' queues as well?

# let's not have session even be given to program by default.
# what use would it have for direct control over session anyway?
# For now, it just needs database.load(path) and database.choose_next().
# Later I can add database.record_skipped() and database.record_liked()
# database.py can even control deletion of frequently skipped tracks, and
# integration of track pools into their main directories.

## TODO: handle differences between artist and album artist
