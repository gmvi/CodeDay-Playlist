import os
from flask import Flask, request, render_template
app = Flask(__name__)

base = os.path.abspath(os.path.curdir)

@app.route('/shutdown')
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

@app.route('/')
def hello_world():
    track = status()
    try:
        return render_template('track.html', track=track)
    except Exception as e:
        print `e`

def main(get_status):
    global status
    status = get_status
    app.run(host='0.0.0.0', port=80)

if __name__ == '__main__':
    main(lambda: None)
