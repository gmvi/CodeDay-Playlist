########## !IMPORTANT! ##########
# This is a default config file #
#  which will should be copied  #
#   as settings.py and edited   #
#           as needed.          #
#################################

SOCK_PORT = 2148
ARTIST_BUFFER_SIZE = 4 # min playlist space between tracks by same artist.
SONG_BUFFER_SIZE = 30 # min playlist space between same track.
LOOP_PERIOD_SEC = 2
DEBUG = False
BROADCAST = False
SHUTDOWN_KEY = "i've made a terrible mistake"
SERVER_LOG_LOCATION = 'weblog.txt'
LIRARY_DB_LOCATION = "cdp.db"
PLAYLIST_DB_LOCATION = ":memory:"
REQUIRED_METADATA = ['title', 'artist']
