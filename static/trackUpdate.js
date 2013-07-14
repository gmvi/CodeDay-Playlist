trackSocket = io.connect('/track');
trackSocket.on('error', function(message)
{ console.log("Error: " + message);
});
handleTrack = function(data)
{ if (data == 'None')
  { $("#track-heading").text("No Current Track");
    $("#track-title").text("");
    $("#track-artist").text("");
  }
  else
  { track = JSON.parse(data);
    $("#track-heading").text("Current Track");
    $("#track-title").text(track.title);
    $("#track-artist").text(track.artist);
  }
}
trackSocket.on('track', handleTrack);
requestTrack = function(data)
{  trackSocket.emit('request', 'track');
}
trackSocket.on('connect', requestTrack);
$(document).ready(requestTrack);