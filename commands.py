import types
commands = {}

def cmd(name):
    def decorator(func):
        if name in commands:
            raise ValueError('command name already used')
        def norm_func(vlc, argstring):
            global v, args
            v, args = vlc, argstring
            return func()
        norm_func.func_name = func.func_name
        commands[name] = norm_func
        return norm_func
    if type(name) == types.FunctionType:
        func = name
        name = func.__name__
        return decorator(func)
    else:
        return decorator

@cmd
def play():
    v.play()

@cmd
def pause():
    v.pause()

@cmd
def next():
    v.next()

@cmd
def vol():
    error = "vol takes one integer argument between 0 and 200"
    x = args.split(" ")
    if len(x) != 1:
        return error
    try:
        x = int(x[0])
        if x >=0 and x <= 200:
            v.media_player.audio_set_volume(x)
            return
    except ValueError:
        pass
    return error

@cmd
def prev():
    v.previous()

@cmd
def last():
    v.play_last()
