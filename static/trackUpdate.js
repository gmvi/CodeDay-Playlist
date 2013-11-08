trackSocket = io.connect('/track');

trackSocket.on('error', function(message)
{ console.log("Error: " + message);
});

trackSocket.on('track', function(track)
{ track = track || {};
  title = track.name || window.trackUpdateDefaultName || "";
  performer = track.track_performer || window.trackUpdateDefaultPerformer || "";
  $("#track-title").text(title);
  $("#track-artist").text(performer);
});

function subscribe()
{ trackSocket.emit('subscribe');
}
subscribe();
trackSocket.on('reconnect', subscribe);