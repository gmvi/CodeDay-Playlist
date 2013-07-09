import types
commands = {}
import __main__ as program

# this all seems really silly in retrospect

# This decorator is gross.
def cmd(name_or_func):
    def decorator(func):
        if name in commands:
            raise ValueError('command name already used')
        def norm_func(argstring):
            global args
            args = argstring
            return func()
        norm_func.func_name = func.func_name
        commands[name] = norm_func
        return norm_func
    if type(name_or_func) == types.FunctionType:
        func = name_or_func
        name = func.__name__
        return decorator(func)
    else:
        name = name_or_func
        return decorator

@cmd
def help():
    print "commands:"
    for name in commands:
        if name != 'help':
            print "%s: %s" % (name, commands[name].__doc__)

@cmd
def info():
    track = program.get_track(verbose = True)
    if not track:
        return "Error getting current track"
    return "Now Playing: %s by %s" % (track.track, track.artist)

@cmd
def play():
    program.v.play()

@cmd
def pause():
    program.v.pause()

@cmd
def next():
    program._next()

@cmd
def vol():
    error = "vol takes one integer argument between 0 and 200"
    x = args.split(" ")
    if len(x) != 1:
        return error
    try:
        x = int(x[0])
        if x >=0 and x <= 200:
            program.v.media_player.audio_set_volume(x)
            return
    except ValueError:
        pass
    return error

@cmd
def prev():
    program._prev()

@cmd
def last():
    program.v.play_last()
