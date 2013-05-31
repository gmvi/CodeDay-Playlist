import os
from socket import gethostbyname, gethostname
from flask import Flask, request, render_template
app = Flask(__name__)

base = os.path.abspath(os.path.curdir)

@app.route('/shutdown')
def shutdown():
    shut_down()
##    func = request.environ.get('werkzeug.server.shutdown')
##    if func is None:
##        raise RuntimeError('Not running with the Werkzeug Server')
##    func()

@app.route('/')
def hello_world():
    track = get_track()
    try:
        return render_template('track.html', track=track)
    except Exception as e:
        print `e`

def main(get_track_, shut_down_):
    global get_track, shut_down
    get_track = get_track_
    shut_down = shut_down_
    ## ^-- this is fucking ugly, TODO: fix it
    ip_addr = gethostbyname(gethostname())
    app.run(host=ip_addr, port=80)

if __name__ == '__main__':
    main(lambda: None)
