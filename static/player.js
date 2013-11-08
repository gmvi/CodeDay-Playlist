var player; // the aroura.js player
var current_song; // the current song being played

function format(secs)
{ mins = Math.floor(secs/60);
  secs = String(secs-mins*60);
  return mins+":"+((secs.length==1)?"0":"")+secs;
}

function play()
{ if (player)
    player.play();
  $('#play').show();
  $('#pause').hide();
}
function pause()
{ if (player)
    player.pause();
  $('#play').hide();
  $('#pause').show();
}
function stop()
{ if (player)
  { seekto(0);
    player.pause();
  }
  $('#play').hide();
  $('#pause').show();
}
callWhenLoaded(f, sec)
{}
function seekto(secs, when)
{ if (!player) return;
  msecs = 1000*secs;
  if (when) msecs += Date.now() - when*1000;
  msecs = Math.floor(msecs);
  if (msecs < 500 && player.currentTime==0) return;
  if (msecs < 0) msecs = 0;
  console.log("trying to seeking to: "+msecs);
  returned = player.seek(msecs);
  while (msecs == returned)
  { msecs += 50; // because if you seek to 0, or anything below a certain value, it will return
                 // that value, and enter an invalid state in which it will not play.
                 // this lets us look through for working positions.
    returned = player.seek(msecs);
  }
  player.seek(returned); // to make sure it actally starts playing sound again.
  console.log("seeked to: "+msecs);
}

var songlocation = '/playlist/data'
function load(songloc)
{ if (typeof(songloc) == "number")
    songlocation = "/library/song/"+songloc+"/data"
  else
    songlocation = songloc||'/playlist/data';
  reload();
}
function reload()
{ if (player)
  { player.pause();
    player.asset.stop();
    try {player.stop();} catch (e) {}
    player.off('progress', progresscallback);
    $('#duration').text("...");
  }
  player = AV.Player.fromURL(songlocation);
  player.volume = $('#volume').val();
  player.once('duration', function(msecs)
  { secs = Math.round(msecs/1000);
    $('#seek').attr('max', secs);
    $('#progress').text("0:00");
    $('#duration').text(format(secs));
    player.on('progress', progresscallback);
  });
  player.preload();
  loadPosition();
}
function progresscallback(msecs)
{ secs = Math.round(msecs/1000);
  if ($('#seek').data('mouse') != 'down') $('#seek').val(secs);
  $('#controls .timelabel:first').text(format(secs));
}

var d;
var margin = 5;
function loadPosition()
{ $.get('/playlist/position', function(data)
  { d = data;
    state = data.state;
    duration = Math.floor(data.duration);
    $('#seek').attr('max', duration)
    $('#duration').text(format(duration));
    if (state =="playing")
    { seekto(data.position - margin, data.time);
      play();
    }
    else
    { seekto(data.position - margin);
      pause();
    }
  });
}

/* /control socket */

var controlSocket = io.connect('/control');

controlSocket.on('error', function(message)
{ console.log("Error: " + message);
});

controlSocket.on('play', function(message)
{ pause();
  seekto(message.position, message.when);
  play();
});
controlSocket.on('pause', function(message)
{ pause();
});
controlSocket.on('stop', function(message)
{ stop();
});
controlSocket.on('position', function(message)
{ seekto(message.position, message.when);
});
controlSocket.on('moveTo', function(message)
{ reload();
});
controlSocket.on('prev', function(message)
{ reload();
});
controlSocket.on('next', function(message)
{ reload();
});
controlSocket.on('reconnect', function(message)
{ controlSocket.emit('subscribe');
  reload();
});

/* main */

$(document).ready( function()
{ $('#volume').change( function(e)
  { if (player) player.volume = +e.target.value;
  });
  controlSocket.emit('subscribe');
  reload();
});