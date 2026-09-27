// Resume points for long videos, stored on the server so any device can pick up where another stopped.
// TikLocalResume.track(video, uri, position) after a video element gets a new source; the server
// decides what is worth keeping (long videos, not the first or last seconds).
(function () {
  var states = new WeakMap();
  var tracked = new Set();
  // Positions saved during this page's life win over the (possibly stale) ones the page was rendered with.
  var latest = new Map();

  function clock(seconds) {
    var s = Math.floor(seconds);
    var parts = [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60];
    if (!parts[0]) parts.shift();
    return parts.map(function (n, i) { return i ? String(n).padStart(2, '0') : String(n); }).join(':');
  }

  function save(state, beacon) {
    if (!state.ready || !Number.isFinite(state.duration)) return;
    state.savedAt = Date.now();
    var uri = state.uri;
    var time = state.time;
    var body = JSON.stringify({ uri: uri, position: time, duration: state.duration });
    if (beacon) {
      navigator.sendBeacon('/api/playback', new Blob([body], { type: 'application/json' }));
      return;
    }
    fetch('/api/playback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body, keepalive: true })
      .then(function (response) { return response.json(); })
      .then(function (data) { latest.set(uri, data.saved ? time : 0); })
      .catch(function () {});
  }

  function listen(video) {
    function sample(event) {
      var state = states.get(video);
      if (!state || !state.ready) return;
      // A pause that arrives after the source was removed saves the last sampled position.
      if (Number.isFinite(video.duration)) {
        state.time = event.type === 'ended' ? video.duration : video.currentTime;
        state.duration = video.duration;
      }
      if (event.type !== 'timeupdate' || (!video.paused && Date.now() - state.savedAt > 5000)) save(state, false);
    }
    video.addEventListener('timeupdate', sample);
    video.addEventListener('pause', sample);
    video.addEventListener('ended', sample);
  }

  function track(video, uri, position) {
    if (!video) return;
    if (latest.has(uri)) position = latest.get(uri);
    var previous = states.get(video);
    if (!previous) listen(video);
    else if (previous.uri !== uri) save(previous, false);
    var state = { uri: uri, ready: false, time: 0, duration: NaN, savedAt: 0 };
    states.set(video, state);
    tracked.add(video);

    function apply() {
      if (states.get(video) !== state) return;
      if (position > 0 && video.currentTime < 1) {
        video.currentTime = position;
        if (window.TikLocalUI) {
          TikLocalUI.toast('Resumed at ' + clock(position), 'info', {
            label: 'Start over',
            run: function () {
              video.currentTime = 0;
              video.play().catch(function () {});
            },
          });
        }
      }
      state.ready = true;
    }
    if (video.readyState >= 1) apply();
    else video.addEventListener('loadedmetadata', apply, { once: true });
  }

  window.addEventListener('pagehide', function () {
    tracked.forEach(function (video) {
      var state = states.get(video);
      if (state && !video.paused) save(state, true);
    });
  });

  window.TikLocalResume = { track: track };
})();
