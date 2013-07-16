import types
commands = {}
import __main__ as program

def run():
    cmd = None
    while True:
        tokens = raw_input().split(" ", 1)
        cmd = tokens[0]
        args = tokens[1] if len(tokens) == 2 else ""
        if cmd == "quit":
            break
        elif cmd in commands:
            p = run_cmd(cmd, args)
            if p: print p
        elif cmd:
            print "'%s' is not a command." % cmd
    program.shut_down()

def run_cmd(command, args=None):
    return commands[command](args)

# This decorator is gross.
def cmd(name_or_func):
    def decorator(name, func):
        if name in commands:
            raise ValueError('command name already used')
        def norm_func(argstring):
            try:
                args = argstring
                return func()
            except:
                return func(argstring)
        norm_func.func_name = func.func_name
        commands[name] = norm_func
        return norm_func
    if type(name_or_func) == types.FunctionType:
        func = name_or_func
        name = func.__name__
        return decorator(name, func)
    else:
        name = name_or_func
        return lambda func: decorator(name, func)

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
    program.next()

@cmd
def vol(args):
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
    program.prev()

@cmd
def last():
    program.v.play_last()
