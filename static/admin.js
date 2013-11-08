/* initial setup */
var state;
var duration;
function loadInfo()
{ $.get('/playlist/position', function(data)
  { state = data.state;
    duration = Math.floor(data.duration);
    setDuration(duration);
    if (state =="playing")
    { $('#play').hide();
      $('#pause').show();
      setPosition(data.position, data.time);
      startTracking();
    }
    else
    { setPosition(data.position);
    }
  });
}

/* controls */
function send_play()
{ $.post('/controls/play');
}
function send_pause()
{ $.post('/controls/pause');
}
function send_stop()
{ $.post('/controls/stop');
}
function send_prev()
{ $.post('/controls/prev');
}
function send_next()
{ $.post('/controls/next');
}
function send_seek(secs)
{ $.post('/controls/position', {'position' : secs});
}

/* playlist */
var current;
function setCurrentlyPlaying(i)
{ if (current != undefined)
    $('#playlist > .entry-wrapper:nth-child('+(current+2)+') > .entry').removeClass('playing');
  current = i;
  if (current != undefined)
    $('#playlist > .entry-wrapper:nth-child('+(current+2)+') > .entry').addClass('playing');
}
function rewindCurrentlyPlaying()
{ setCurrentlyPlaying(current-1);
}
function advanceCurrentlyPlaying()
{ setCurrentlyPlaying(current+1);
}

function reload_playlist()
{ $.getJSON('/playlist', function (playlist)
  { $('#playlist > .entry-wrapper').remove();
    $('#playlist').sortable('disable');
    count = 0;
    for (i=0; i<playlist.list.length; i++)
    { $('#playlist').append('<div class=entry-wrapper></div>');
      request = $.getJSON('/library/song/'+playlist.list[i].song_id);
      request.i = i; //to persist i into the request.done function
      request.done( function (song, status, request)
      { // do the following for all playlist entries
        $('#playlist > div:nth-child('+(request.i+2)+')')
          .append(create_playlist_item(playlist.list[request.i], song));
        // do the following for playlist entry #playlist.current
        if (request.i == playlist.current)
        { setCurrentlyPlaying(playlist.current);
        }
        count++;
        if (count=playlist.list.length)
        { // do the following after the last playlist entry is loaded
          $('#playlist').sortable('enable');
        }
      });
    }
    update_playlist_height();
  });
}
function create_playlist_item(entry, song)
{ return $('<div class="entry"></div>').data('index', entry.index)
                                       .data('entry_id', entry.entry_id)
                                       .data('song', song)
     .append(  '<span class="handle"></span>')
     .append(  '<span class="play-overlay">►</span>')
     .append($('<span class=entry-info-start></span>'))
     .append($('<li class=entry-main></li>')
         .append($('<span class=entry-title></span>')
             .append($('<span class=track></span>').text(song.name))
             .append(  ' - ')
             .append($('<span class=artist></span>').text(song.artist.name))
         )
     )
     .append($('<span class=entry-info-end></span>'));
}
function update_playlist_height()
{ playlist = $('#playlist')
  playlist.height('initial').height(playlist.height());
}

function sort_update(ev, ui)
{ entry_id = ui.item.children('.entry').data('entry_id');
  index = ui.item.index('.entry-wrapper');
  $.post('/playlist', {'entry_id': entry_id,
                       'index'   : index});
}

/* seekbar */
var seekbar;
function seekbarMouseDown()
{ seekbar.data('mousedown', true);
  stopTracking();
}
function seekbarMouseUp()
{ seekbar.data('mousedown', false);
  send_seek(+seekbar.val());
}
function seekbarKeyDown(e)
{ if (37 > e.keyCode || e.keyCode > 40) return;
  seekbar.data('keydown', true);
  stopTracking();
}
function seekbarKeyUp(e)
{ if (37 > e.keyCode || e.keyCode > 40) return;
  seekbar.data('keydown', false);
  send_seek(+seekbar.val());
}
function seekbarChange(e)
{ $('#position').text(format(+e.target.value));
}

function format(secs, def)
{ if (secs == null) return def || "0:00";
  mins = Math.floor(secs/60);
  secs = String(secs-mins*60);
  return mins+":"+((secs.length==1)?"0":"")+secs;
}

var tick;
function tickSeekbar()
{ setPosition(+seekbar.val()+1);
}
function setPosition(position, when)
{ if (when) {position = position + (Date.now()/1000 - when)}
  newVal = Math.round(position);
  $('#seek').val(newVal).change();
}
function setDuration(secs)
{ $('#duration').text(format(duration, "..."));
  $('#seek').attr('max', duration);
}
function startTracking()
{ tick = setInterval(tickSeekbar, 1000);
}
function stopTracking()
{ clearInterval(tick);
}

/* /control socket */

var controlSocket = io.connect('/control');

controlSocket.on('error', function(message)
{ console.log("Error: " + message);
});

controlSocket.on('play', function(message)
{ setPosition(message.position, message.when);
  startTracking();
  state = "playing";
  $('#play').hide();
  $('#pause').show();
});
controlSocket.on('pause', function(message)
{ stopTracking();
  state = "paused";
  $('#play').show();
  $('#pause').hide();
});
controlSocket.on('stop', function(message)
{ stopTracking();
  state = "stopped";
  $('#play').show();
  $('#pause').hide();
  setPosition(0);
});
controlSocket.on('position', function(message)
{ stopTracking();
  setPosition(message.position, message.when);
  if (state == "playing") startTracking();
  else state = "paused";
});
controlSocket.on('moveTo', function(message)
{ console.log('moveTo: ' + message);
  stopTracking();
  loadInfo();
});
controlSocket.on('prev', function(message)
{ stopTracking();
  rewindCurrentlyPlaying();
  loadInfo();
});
controlSocket.on('next', function(message)
{ stopTracking();
  advanceCurrentlyPlaying();
  loadInfo();
});
controlSocket.on('reconnect', function(message)
{ controlSocket.emit('subscribe');
  stopTracking();
  loadInfo();
});

/* main */
$(document).ready( function()
{ seekbar = $('#seek');
  seekbar.mousedown(seekbarMouseDown);
  seekbar.mouseup(seekbarMouseUp);
  seekbar.keydown(seekbarKeyDown);
  seekbar.keyup(seekbarKeyUp);
  seekbar.change(seekbarChange);
  $('#play').click(send_play);
  $('#pause').click(send_pause);
  $('#stop').click(send_stop);
  $('#prev').click(send_prev);
  $('#next').click(send_next);
  $('#playlist').sortable({ handle: ".handle",
                            cursor: "ns-resize",
                            containment: ".sort-boundary",
                            placeholder: "sort-placeholder",
                            items: "> .entry-wrapper",
                            scroll: false,
                            tolerance: "pointer",
                            update: sort_update});
  reload_playlist();
  loadInfo();
  controlSocket.emit('subscribe');
});