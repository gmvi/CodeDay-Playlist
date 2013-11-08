/* seekbar */
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
function seekbarDown(e)
{ if (e.type == 'keydown' && (37 <= a.keyCode && a.keyCode <= 40))
  	stopTracking();
}
function seekbarChange(e)
{ $('#position').text(format(+e.target.value));
}

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
$(document).ready(function()
{ loadInfo();
  controlSocket.emit('subscribe');
  $('#seek').mousedown(seekbarDown).keydown(seekbarDown).change(seekbarChange);
  //seekbar.mousedown(function(e){seekbar.data('mouse', 'down');});
  //seekbar.mouseup(function(e){seekbar.data('mouse', 'up');});
  //seekbar.change(seekbarChangeHandler);
});

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
{ stopTracking();
	loadInfo();
});
controlSocket.on('prev', function(message)
{ stopTracking();
	loadInfo();
});
controlSocket.on('next', function(message)
{ stopTracking();
	loadInfo();
});
controlSocket.on('reconnect', function(message)
{ controlSocket.emit('subscribe');
  stopTracking();
  loadInfo();
});