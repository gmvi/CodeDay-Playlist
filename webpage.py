from socket import gethostbyname, gethostname
from flask import Flask, request, render_template, abort
import jinja2
app = Flask(__name__) # the app
process = None # the process to handle app.run()
get_track = None # the function to get the current track
SHUTDOWN_KEY = "i've made a terrible mistake"

# In case the process gets out of hand.
# Will require a hard-coded password at release.
@app.route('/shutdown', methods=['POST'])
def shutdown():
    if str(request.form['key'] == SHUTDOWN_KEY):
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
    else:
        abort(405)

track_template = jinja2.Template(file('templates/track.html').read())

# Main page (should be the only non-admin page)
@app.route('/')
def hello_world():
    try:
        track = get_track()
        return track_template.render(track=track)
    except Exception as e:
        return `e`

def attatch_get_track(func):
    global get_track
    get_track = func

def run():
    ip_addr = gethostbyname(gethostname())
    app.run(host=ip_addr, port=80)#, debug=True, use_reloader = False)
