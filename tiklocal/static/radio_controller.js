(function () {
  'use strict';

  var STATION_KEY = 'radio_station';
  var RECENT_KEY = 'radio_recent_tracks';
  var POSITION_KEY = 'radio_position';
  var SLEEP_OPTIONS = [null, 30, 60, 120];

  var audio = new Audio();
  var stations = [];
  var stationId = localStorage.getItem(STATION_KEY) || 'default';
  var upcoming = [];
  var recent = normalizeRecent(readJson(RECENT_KEY, []));
  var currentTrack = null;
  var isPlaying = false;
  var sleepIndex = 0;
  var sleepEnd = null;
  var sleepTickId = null;
  var saveTick = 0;
  var mediaPositionTick = 0;
  var artLoadToken = 0;
  var trackPlayReportedFor = '';
  var trackExitReportedFor = '';
  var trackInfoTimers = [];
  var pendingTrackTitle = '';
  var pendingTrackMeta = '';
  var trackInfoTransitionId = 0;
  var metadataLoadToken = 0;

  var els = {};

  var ICONS = {
    heart: '<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    heartFilled: '<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    moon: '<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>',
  };

  function init() {
    cacheEls();
    bindEvents();
    updateSignalArt(null);
    replaceFeather();
    loadStations()
      .then(function () { return tune({ reset: true, loadFirst: true }); })
      .catch(showLoadError);
  }

  function cacheEls() {
    [
      'radio-page', 'station-name', 'track-title', 'track-meta',
      'progress-bar', 'time-current', 'time-total', 'btn-play', 'btn-next',
      'btn-fav', 'btn-sleep', 'sleep-label',
      'station-options', 'upcoming-preview', 'upcoming-list', 'cover-wave', 'cover-art'
    ].forEach(function (id) {
      els[toCamel(id)] = document.getElementById(id);
    });
  }

  function bindEvents() {
    audio.addEventListener('ended', function () {
      reportPlaybackExit('complete');
      playNext(true);
    });
    audio.addEventListener('error', function () {
      reportPlaybackExit('error');
      playNext(true);
    });
    audio.addEventListener('play', function () {
      isPlaying = true;
      reportTrackPlay();
      updatePlayIcon();
      updateMotion();
      updateMediaSession();
      updateMediaPosition();
    });
    audio.addEventListener('pause', function () {
      isPlaying = false;
      updatePlayIcon();
      updateMotion();
      savePosition();
      updateMediaSessionState();
      updateMediaPosition();
    });
    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('loadedmetadata', function () {
      restoreSavedTimeOnce();
      onTimeUpdate();
      updateMediaPosition();
    });

    els.btnPlay.addEventListener('click', togglePlay);
    els.btnNext.addEventListener('click', function () { playNext(true, { manual: true }); });
    els.btnFav.addEventListener('click', toggleFavorite);
    els.btnSleep.addEventListener('click', cycleSleep);
    els.progressBar.addEventListener('input', function (event) {
      var duration = playableDuration();
      if (!duration) return;
      audio.currentTime = (Number(event.target.value) / 100) * duration;
      updateMediaPosition();
    });
  }

  function loadStations() {
    return fetch('/api/radio/stations')
      .then(readApi)
      .then(function (data) {
        stations = data.stations || [];
        if (!stations.some(function (station) { return station.id === stationId; })) {
          stationId = 'default';
        }
        renderStations();
        updateStationText();
      })
      .catch(function () {
        stations = [{ id: 'default', name: '默认电台', description: '' }];
        stationId = 'default';
        updateStationText();
      });
  }

  function tune(options) {
    options = options || {};
    if (options.reset) {
      upcoming = [];
    }
    var exclude = buildExclude();
    var url = '/api/radio/tune?station=' + encodeURIComponent(stationId)
      + '&limit=12'
      + '&exclude=' + encodeURIComponent(exclude.join(','));

    return fetch(url)
      .then(readApi)
      .then(function (data) {
        var incoming = data.items || [];
        appendUpcoming(incoming);
        loadFirstIfNeeded(options);
      })
      .catch(function () {
        return fetch('/api/radio/items?limit=200')
          .then(readApi)
          .then(function (data) {
            appendUpcoming(shuffleTracks(data.items || []));
            loadFirstIfNeeded(options);
          });
      });
  }

  function appendUpcoming(items) {
    var known = new Set(upcoming.map(function (item) { return item.name; }));
    items.forEach(function (item) {
      if (!known.has(item.name) && (!currentTrack || item.name !== currentTrack.name)) {
        upcoming.push(item);
        known.add(item.name);
      }
    });
    renderUpcoming();
  }

  function loadFirstIfNeeded(options) {
    if (options.loadFirst && !currentTrack) {
      prepareTrack(upcoming.shift() || null);
      renderUpcoming();
    }
  }

  function shuffleTracks(items) {
    var copy = items.slice();
    for (var i = copy.length - 1; i > 0; i -= 1) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = copy[i];
      copy[i] = copy[j];
      copy[j] = tmp;
    }
    return copy;
  }

  function buildExclude() {
    recent = normalizeRecent(recent);
    var names = recent.slice(-30);
    if (currentTrack) names.push(currentTrack.name);
    upcoming.forEach(function (item) { names.push(item.name); });
    return Array.from(new Set(names.filter(Boolean)));
  }

  function prepareTrack(track) {
    currentTrack = track;
    metadataLoadToken += 1;
    if (!track) {
      audio.removeAttribute('src');
      clearTrackInfoTimers();
      els.radioPage.classList.remove('is-changing-track');
      setTrackInfo('暂无音频', '');
      updateSignalArt(null);
      updateFavorite();
      updateMediaSession();
      return;
    }

    audio.src = track.media_url;
    trackPlayReportedFor = '';
    trackExitReportedFor = '';
    transitionTrackInfo(track.title || '未命名音频', buildTrackMeta(track));
    setNeedle();
    updateSignalArt(track);
    updateFavorite();
    updateMediaSession();
    loadTrackMetadata(track);
  }

  function playTrack(track) {
    if (!track) return Promise.resolve();
    prepareTrack(track);
    rememberRecent(track.name);
    return audio.play().catch(function () {
      isPlaying = false;
      reportPlaybackExit('error');
      updatePlayIcon();
    });
  }

  function playNext(autoplay, options) {
    options = options || {};
    if (options.manual) {
      reportPlaybackExit('skip');
      settleControl(els.btnNext);
    }
    if (!upcoming.length) {
      return tune({ reset: false }).then(function () {
        if (!upcoming.length) {
          prepareTrack(null);
          return;
        }
        return playNext(autoplay);
      });
    }
    var next = upcoming.shift();
    renderUpcoming();
    if (upcoming.length < 3) tune({ reset: false });
    return autoplay ? playTrack(next) : (prepareTrack(next), Promise.resolve());
  }

  function togglePlay() {
    if (!currentTrack) {
      playNext(true);
      return;
    }
    if (isPlaying) {
      audio.pause();
    } else {
      rememberRecent(currentTrack.name);
      audio.play().catch(function () {});
    }
  }

  function toggleFavorite() {
    if (!currentTrack) return;
    fetch('/api/favorite/' + encodeURIComponent(currentTrack.name), { method: 'POST' })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        currentTrack.is_favorite = Boolean(data.favorite);
        updateFavorite();
        if (currentTrack.is_favorite) reportFeedback('favorite', currentTrack, playbackRatio());
        settleControl(els.btnFav);
      })
      .catch(function () {});
  }

  function cycleSleep() {
    sleepIndex = (sleepIndex + 1) % SLEEP_OPTIONS.length;
    setSleep(SLEEP_OPTIONS[sleepIndex]);
    settleControl(els.btnSleep);
  }

  function setSleep(minutes) {
    clearInterval(sleepTickId);
    if (!minutes) {
      sleepEnd = null;
      updateSleep();
      return;
    }
    sleepEnd = Date.now() + minutes * 60000;
    sleepTickId = setInterval(tickSleep, 1000);
    updateSleep();
  }

  function tickSleep() {
    if (!sleepEnd) return;
    if (sleepEnd <= Date.now()) {
      clearInterval(sleepTickId);
      sleepEnd = null;
      sleepIndex = 0;
      audio.pause();
    }
    updateSleep();
  }

  function updateSleep() {
    if (!sleepEnd) {
      els.btnSleep.innerHTML = ICONS.moon + '<span id="sleep-label" class="sr-only">定时</span>';
      els.sleepLabel = document.getElementById('sleep-label');
      els.btnSleep.style.color = '';
      els.btnSleep.classList.remove('is-active');
      els.btnSleep.setAttribute('aria-label', '定时');
      els.btnSleep.setAttribute('title', '定时');
      return;
    }
    var minutes = SLEEP_OPTIONS[sleepIndex];
    els.btnSleep.innerHTML = '<span id="sleep-label">' + minutes + '</span>';
    els.sleepLabel = document.getElementById('sleep-label');
    els.btnSleep.style.color = 'var(--radio-accent)';
    els.btnSleep.classList.add('is-active');
    els.btnSleep.setAttribute('aria-label', minutes + ' 分钟后停止');
    els.btnSleep.setAttribute('title', minutes + ' 分钟后停止');
  }

  function renderStations() {
    els.stationOptions.innerHTML = stations.map(function (station) {
      return '<button class="station-option ' + (station.id === stationId ? 'active' : '') + '" type="button" data-station="' + escapeHtml(station.id) + '">'
        + '<strong>' + escapeHtml(station.name) + '</strong>'
        + '<span>' + escapeHtml(station.description) + '</span>'
        + '</button>';
    }).join('');

    els.stationOptions.querySelectorAll('[data-station]').forEach(function (button) {
      button.addEventListener('click', function () {
        var wasPlaying = isPlaying;
        stationId = button.dataset.station || 'default';
        localStorage.setItem(STATION_KEY, stationId);
        updateStationText();
        renderStations();
        audio.pause();
        currentTrack = null;
        tune({ reset: true, loadFirst: true }).then(function () {
          if (wasPlaying && currentTrack) playTrack(currentTrack);
        });
      });
    });
  }

  function renderUpcoming() {
    var preview = upcoming.slice(0, 3);
    els.upcomingPreview.innerHTML = preview.length
      ? preview.map(function (item) { return '<li>' + escapeHtml(item.title || item.name) + '</li>'; }).join('')
      : '<li></li>';

    els.upcomingList.innerHTML = upcoming.length
      ? upcoming.slice(0, 12).map(function (item) {
        return '<li>' + escapeHtml(item.title || item.name) + '</li>';
      }).join('')
      : '<li></li>';
  }

  function updateStationText() {
    var station = stations.find(function (item) { return item.id === stationId; }) || stations[0];
    if (!station) return;
    els.stationName.textContent = station.name;
  }

  function updatePlayIcon() {
    els.btnPlay.setAttribute('aria-label', isPlaying ? '暂停' : '播放');
    els.btnPlay.setAttribute('title', isPlaying ? '暂停' : '播放');
  }

  function updateMotion() {
    els.radioPage.classList.toggle('is-playing', isPlaying);
  }

  function updateFavorite() {
    var active = Boolean(currentTrack && currentTrack.is_favorite);
    els.btnFav.innerHTML = (active ? ICONS.heartFilled : ICONS.heart) + '<span class="sr-only">' + (active ? '已收藏' : '收藏') + '</span>';
    els.btnFav.classList.toggle('is-active', active);
    els.btnFav.style.color = active ? 'var(--radio-accent)' : '';
    els.btnFav.setAttribute('aria-label', active ? '取消收藏' : '收藏');
    els.btnFav.setAttribute('title', active ? '取消收藏' : '收藏');
  }

  function onTimeUpdate() {
    var duration = playableDuration();
    var pct = duration ? (audio.currentTime / duration) * 100 : 0;
    els.progressBar.value = pct;
    els.progressBar.style.background = 'linear-gradient(to right, var(--radio-accent) ' + pct + '%, rgba(127,127,127,0.22) ' + pct + '%)';
    els.timeCurrent.textContent = formatTime(audio.currentTime);
    els.timeTotal.textContent = formatTime(duration);
    if (Date.now() - saveTick > 5000) {
      saveTick = Date.now();
      savePosition();
    }
    if (Date.now() - mediaPositionTick > 3000) {
      mediaPositionTick = Date.now();
      updateMediaPosition();
    }
  }

  function restoreSavedTimeOnce() {
    if (!currentTrack) return;
    var saved = readJson(POSITION_KEY, {});
    var duration = playableDuration();
    if (saved.name === currentTrack.name && saved.time && duration && saved.time < duration - 5) {
      audio.currentTime = saved.time;
    }
  }

  function savePosition() {
    if (!currentTrack) return;
    localStorage.setItem(POSITION_KEY, JSON.stringify({
      name: currentTrack.name,
      time: audio.currentTime || 0,
    }));
  }

  function rememberRecent(name) {
    if (!name) return;
    recent = normalizeRecent(recent);
    recent = recent.filter(function (item) { return item !== name; });
    recent.push(name);
    recent = recent.slice(-30);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
  }

  function updateMediaSession() {
    if (!('mediaSession' in navigator) || !currentTrack) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: currentTrack.title || 'TikLocal Radio',
      artist: currentTrack.artist || getStationName(),
      album: currentTrack.album || 'TikLocal',
      artwork: buildMediaArtwork(currentTrack),
    });
    updateMediaSessionState();
    try {
      navigator.mediaSession.setActionHandler('play', function () { audio.play(); });
      navigator.mediaSession.setActionHandler('pause', function () { audio.pause(); });
      navigator.mediaSession.setActionHandler('nexttrack', function () { playNext(true, { manual: true }); });
      navigator.mediaSession.setActionHandler('seekto', function (details) {
        var duration = playableDuration();
        if (details && typeof details.seekTime === 'number' && duration) {
          audio.currentTime = Math.max(0, Math.min(details.seekTime, duration));
          updateMediaPosition();
        }
      });
    } catch (error) {}
    updateMediaPosition();
  }

  function loadTrackMetadata(track) {
    if (!track || !track.name) return;
    var token = metadataLoadToken;
    fetch('/api/radio/metadata?uri=' + encodeURIComponent(track.name))
      .then(readApi)
      .then(function (metadata) {
        if (token !== metadataLoadToken || !currentTrack || metadata.name !== currentTrack.name) return;
        currentTrack.title = metadata.title || currentTrack.title;
        currentTrack.artist = metadata.artist || '';
        currentTrack.album = metadata.album || '';
        currentTrack.duration = metadata.duration || null;
        queueTrackInfo(currentTrack.title || '未命名音频', buildTrackMeta(currentTrack));
        updateMediaSession();
      })
      .catch(function () {});
  }

  function updateMediaSessionState() {
    if (!('mediaSession' in navigator)) return;
    try {
      navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';
    } catch (error) {}
  }

  function updateMediaPosition() {
    if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return;
    var duration = playableDuration();
    if (!duration) return;
    var position = Math.max(0, Math.min(audio.currentTime || 0, duration));
    try {
      navigator.mediaSession.setPositionState({
        duration: duration,
        playbackRate: audio.playbackRate || 1,
        position: position,
      });
    } catch (error) {}
  }

  function buildMediaArtwork(track) {
    if (!track || (!track.artwork_url && !track.thumb_url)) return [];
    var src = absoluteUrl(track.artwork_url || track.thumb_url);
    return [
      { src: src, sizes: '96x96', type: 'image/png' },
      { src: src, sizes: '128x128', type: 'image/png' },
      { src: src, sizes: '192x192', type: 'image/png' },
      { src: src, sizes: '256x256', type: 'image/png' },
      { src: src, sizes: '384x384', type: 'image/png' },
      { src: src, sizes: '512x512', type: 'image/png' },
    ];
  }

  function absoluteUrl(value) {
    try {
      return new URL(value, window.location.href).href;
    } catch (error) {
      return value;
    }
  }

  function setNeedle() {
    var angle = -42 + Math.floor(Math.random() * 84);
    els.btnPlay.style.setProperty('--needle-angle', angle + 'deg');
  }

  function updateSignalArt(track) {
    var seed = track ? (track.name || track.title || '') : 'tiklocal-radio';
    var colors = paletteFor(seed);
    els.btnPlay.style.setProperty('--radio-art-a', colors[0]);
    els.btnPlay.style.setProperty('--radio-art-b', colors[1]);
    els.btnPlay.style.setProperty('--radio-art-c', colors[2]);

    artLoadToken += 1;
    var token = artLoadToken;
    els.btnPlay.classList.remove('has-cover');
    els.btnPlay.classList.add('no-cover');

    if (!track || !track.thumb_url || !els.coverArt) {
      clearCoverArt();
      return;
    }

    els.coverArt.onload = function () {
      if (token !== artLoadToken) return;
      if (els.coverArt.naturalWidth <= 2 && els.coverArt.naturalHeight <= 2) {
        clearCoverArt();
        return;
      }
      els.btnPlay.classList.remove('no-cover');
      els.btnPlay.classList.add('has-cover');
    };
    els.coverArt.onerror = function () {
      if (token !== artLoadToken) return;
      clearCoverArt();
    };
    els.coverArt.src = track.thumb_url
      + (track.thumb_url.indexOf('?') >= 0 ? '&' : '?')
      + 'v=' + encodeURIComponent(track.name || '');
  }

  function clearCoverArt() {
    if (!els.coverArt) return;
    els.coverArt.removeAttribute('src');
    els.btnPlay.classList.remove('has-cover');
    els.btnPlay.classList.add('no-cover');
  }

  function paletteFor(seed) {
    var palettes = [
      ['#466b61', '#a88756', '#d7d2c4'],
      ['#5c6750', '#b18462', '#d8d3c8'],
      ['#57707a', '#9b8257', '#d2d5ce'],
      ['#675f82', '#9b8b5b', '#d7d1c0'],
      ['#72634e', '#5f8174', '#d8d4c7'],
      ['#4f6f7e', '#a36f5d', '#d5d0c4'],
    ];
    var hash = 0;
    for (var i = 0; i < seed.length; i += 1) {
      hash = ((hash << 5) - hash + seed.charCodeAt(i)) | 0;
    }
    return palettes[Math.abs(hash) % palettes.length];
  }

  function getStationName() {
    var station = stations.find(function (item) { return item.id === stationId; });
    return station ? station.name : '默认电台';
  }

  function showLoadError(error) {
    if (window.console && console.error) {
      console.error('Radio load failed:', error);
    }
    els.trackTitle.textContent = '加载失败';
    if (els.trackMeta) {
      els.trackMeta.textContent = '';
      els.trackMeta.classList.remove('has-meta');
    }
    els.upcomingPreview.innerHTML = '<li></li>';
  }

  function readApi(response) {
    return response.json().then(function (payload) {
      if (!response.ok || payload.success === false) {
        throw new Error(payload.error || 'Request failed');
      }
      return payload.data || payload;
    });
  }

  function readJson(key, fallback) {
    try {
      var value = JSON.parse(localStorage.getItem(key) || 'null');
      return value == null ? fallback : value;
    } catch (error) {
      return fallback;
    }
  }

  function normalizeRecent(value) {
    if (!Array.isArray(value)) return [];
    return value.filter(function (item) {
      return typeof item === 'string' && item;
    }).slice(-30);
  }

  function formatTime(seconds) {
    if (!seconds || !isFinite(seconds)) return '0:00';
    var minutes = Math.floor(seconds / 60);
    var rest = String(Math.floor(seconds % 60)).padStart(2, '0');
    return minutes + ':' + rest;
  }

  function setTrackInfo(title, meta) {
    els.trackTitle.textContent = title;
    if (!els.trackMeta) return;
    els.trackMeta.textContent = meta || '';
    els.trackMeta.classList.toggle('has-meta', Boolean(meta));
  }

  function queueTrackInfo(title, meta) {
    if (els.radioPage.classList.contains('is-changing-track')) {
      pendingTrackTitle = title;
      pendingTrackMeta = meta || '';
      return;
    }
    setTrackInfo(title, meta);
  }

  function buildTrackMeta(track) {
    if (!track) return '';
    var parts = [];
    if (track.artist) parts.push(track.artist);
    if (track.album) parts.push(track.album);
    return parts.join(' · ');
  }

  function transitionTrackInfo(title, meta) {
    clearTrackInfoTimers();
    trackInfoTransitionId += 1;
    var transitionId = trackInfoTransitionId;
    pendingTrackTitle = title;
    pendingTrackMeta = meta || '';
    els.radioPage.classList.remove('is-changing-track');
    void els.radioPage.offsetWidth;
    els.radioPage.classList.add('is-changing-track');
    trackInfoTimers.push(window.setTimeout(function () {
      if (transitionId !== trackInfoTransitionId) return;
      setTrackInfo(pendingTrackTitle, pendingTrackMeta);
    }, 540));
    trackInfoTimers.push(window.setTimeout(function () {
      window.requestAnimationFrame(function () {
        if (transitionId !== trackInfoTransitionId) return;
        els.radioPage.classList.remove('is-changing-track');
        trackInfoTimers = [];
      });
    }, 590));
  }

  function clearTrackInfoTimers() {
    trackInfoTransitionId += 1;
    trackInfoTimers.forEach(function (timer) {
      window.clearTimeout(timer);
    });
    trackInfoTimers = [];
  }

  function reportTrackPlay() {
    if (!currentTrack || trackPlayReportedFor === currentTrack.name) return;
    trackPlayReportedFor = currentTrack.name;
    reportFeedback('play', currentTrack, playbackRatio());
  }

  function reportPlaybackExit(event) {
    if (!currentTrack || trackExitReportedFor === currentTrack.name + ':' + event) return;
    var ratio = playbackRatio();
    var finalEvent = event;
    if (event === 'skip' && ratio >= 0.82) {
      finalEvent = 'complete';
    }
    trackExitReportedFor = currentTrack.name + ':' + finalEvent;
    reportFeedback(finalEvent, currentTrack, ratio);
  }

  function playbackRatio() {
    var duration = playableDuration();
    if (!duration) return null;
    return Math.max(0, Math.min((audio.currentTime || 0) / duration, 1));
  }

  function playableDuration() {
    return audio.duration && isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
  }

  function reportFeedback(event, track, ratio) {
    if (!track || !track.name) return;
    var payload = JSON.stringify({
      name: track.name,
      event: event,
      ratio: ratio,
      _csrf_token: window.TikLocalSecurity && window.TikLocalSecurity.csrfToken || '',
    });
    if (navigator.sendBeacon) {
      try {
        var blob = new Blob([payload], { type: 'application/json' });
        if (navigator.sendBeacon('/api/radio/feedback', blob)) return;
      } catch (error) {}
    }
    fetch('/api/radio/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    }).catch(function () {});
  }

  function settleControl(element) {
    if (!element) return;
    element.classList.remove('is-settling');
    void element.offsetWidth;
    element.classList.add('is-settling');
    window.setTimeout(function () {
      element.classList.remove('is-settling');
    }, 700);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toCamel(id) {
    return id.replace(/-([a-z])/g, function (_, chr) { return chr.toUpperCase(); });
  }

  function replaceFeather() {
    if (window.feather) {
      window.feather.replace();
    }
    updatePlayIcon();
    updateFavorite();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
