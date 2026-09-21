(function () {
  'use strict';

  function byId(id) { return document.getElementById(id); }

  function fetchJson(url) {
    return fetch(url, { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('Request failed');
        return response.json();
      });
  }

  function apiData(payload) {
    return payload && payload.data ? payload.data : payload;
  }

  function mediaName(item) {
    var raw = String(item.name || '').split('/').pop() || 'Untitled media';
    return raw.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
  }

  function makeIcon(name) {
    var icon = document.createElement('i');
    icon.setAttribute('data-feather', name);
    icon.setAttribute('aria-hidden', 'true');
    return icon;
  }

  function makeMediaTile(item, extraClass) {
    var link = document.createElement('a');
    link.className = 'media-tile' + (extraClass ? ' ' + extraClass : '');
    link.href = item.detail_url || '/library';
    link.setAttribute('aria-label', 'View ' + mediaName(item));

    var image = document.createElement('img');
    image.src = item.thumb_url;
    image.alt = '';
    image.loading = 'lazy';
    image.addEventListener('error', function () { image.style.opacity = '0'; });

    var kind = document.createElement('span');
    kind.className = 'media-kind';
    kind.appendChild(makeIcon(item.type === 'video' ? 'play' : 'image'));

    var copy = document.createElement('span');
    copy.className = 'media-tile-copy';
    copy.textContent = mediaName(item);

    link.appendChild(image);
    link.appendChild(kind);
    link.appendChild(copy);
    return link;
  }

  function renderFlow(items, stats) {
    var collage = byId('home-flow-collage');
    if (!collage) return;
    collage.replaceChildren();
    items.slice(0, 4).forEach(function (item) {
      var image = document.createElement('img');
      image.src = item.thumb_url;
      image.alt = '';
      image.loading = 'eager';
      collage.appendChild(image);
    });
    while (collage.children.length < 4) {
      var placeholder = document.createElement('span');
      placeholder.className = 'flow-collage-placeholder';
      collage.appendChild(placeholder);
    }
    var total = Number(stats && stats.indexed_total) || items.length;
    byId('home-flow-meta').textContent = total ? total.toLocaleString('en') + ' private moments' : 'Mixed media flow';
  }

  function renderRibbon(containerId, items, extraClass) {
    var container = byId(containerId);
    if (!container) return;
    container.replaceChildren();
    if (!items.length) {
      var empty = document.createElement('div');
      empty.className = 'home-empty';
      empty.innerHTML = '<span>It is quiet here for now.<br><a href="/settings/">Add a media source</a> and your library will begin to grow.</span>';
      container.appendChild(empty);
      return;
    }
    items.forEach(function (item) { container.appendChild(makeMediaTile(item, extraClass)); });
  }

  function renderCollections(items) {
    var container = byId('home-collections');
    if (!container) return;
    container.replaceChildren();
    if (!items.length) {
      var empty = document.createElement('a');
      empty.className = 'collection-empty';
      empty.href = '/collections';
      empty.innerHTML = 'No collections yet.<br>Gather favorite moments into a chapter of your own.';
      container.appendChild(empty);
      return;
    }
    items.slice(0, 3).forEach(function (item) {
      var link = document.createElement('a');
      link.className = 'collection-card';
      link.href = item.detail_url || '/collections';

      var preview = document.createElement('span');
      preview.className = 'collection-preview';
      (item.preview_items || []).slice(0, 2).forEach(function (media) {
        var image = document.createElement('img');
        image.src = media.thumb_url;
        image.alt = '';
        image.loading = 'lazy';
        preview.appendChild(image);
      });

      var copy = document.createElement('span');
      copy.className = 'collection-copy';
      var title = document.createElement('strong');
      title.textContent = item.name || 'Untitled collection';
      var count = document.createElement('span');
      count.textContent = (Number(item.item_count) || 0) + ' media items';
      copy.appendChild(title);
      copy.appendChild(count);

      link.appendChild(preview);
      link.appendChild(copy);
      link.appendChild(makeIcon('chevron-right'));
      container.appendChild(link);
    });
  }

  function renderStats(stats) {
    var total = Number(stats.indexed_total) || 0;
    var audio = Number(stats.audios) || 0;
    var summary = total ? total.toLocaleString('en') + ' media items' : 'Waiting for your first media item';
    if (audio) summary += ' · ' + audio.toLocaleString('en') + ' audio tracks';
    byId('home-library-summary').textContent = summary;
  }

  function hydrateRadio() {
    var stationId = localStorage.getItem('radio_station') || 'default';
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem('radio_position') || '{}') || {}; } catch (_) { saved = {}; }

    fetchJson('/api/radio/stations').then(function (payload) {
      var stations = apiData(payload).stations || [];
      var station = stations.find(function (item) { return item.id === stationId; });
      if (station) byId('home-radio-station').textContent = station.name || 'Private Radio';
    }).catch(function () {});

    if (!saved.name) return;
    fetchJson('/api/radio/metadata?uri=' + encodeURIComponent(saved.name)).then(function (payload) {
      var track = apiData(payload);
      byId('home-radio-title').textContent = track.title || mediaName({ name: saved.name });
      byId('home-radio-action').firstChild.nodeValue = 'Keep Listening ';
    }).catch(function () {});
  }

  function updateGreeting() {
    var hour = new Date().getHours();
    var title = 'Where would you like to begin?';
    if (hour >= 18 || hour < 5) title = 'Where would you like to begin tonight?';
    else if (hour < 11) title = 'Good morning. Where would you like to begin?';
    else if (hour < 14) title = 'Where would you like to begin this afternoon?';
    byId('home-title').textContent = title;
  }

  function init() {
    updateGreeting();
    hydrateRadio();

    var statsRequest = fetchJson('/api/library/stats').catch(function () { return {}; });
    var recentRequest = fetchJson('/api/library/items?scope=all&mode=all&offset=0&limit=12').catch(function () { return { data: { items: [] } }; });
    var randomRequest = fetchJson('/api/library/items?scope=all&mode=image_random&offset=0&limit=12').catch(function () { return { data: { items: [] } }; });
    var collectionsRequest = fetchJson('/api/collections').catch(function () { return { data: { items: [] } }; });

    Promise.all([statsRequest, recentRequest, randomRequest, collectionsRequest]).then(function (results) {
      var stats = apiData(results[0]) || {};
      var recent = ((apiData(results[1]) || {}).items || []).filter(function (item) {
        return item.type === 'image' || item.type === 'video';
      });
      var rediscover = (apiData(results[2]) || {}).items || [];
      var collections = (apiData(results[3]) || {}).items || [];

      renderStats(stats);
      renderFlow(recent, stats);
      renderRibbon('home-recent', recent.slice(0, 8), '');
      renderRibbon('home-rediscover', (rediscover.length ? rediscover : recent.slice().reverse()).slice(0, 3), 'rediscover-tile');
      renderCollections(collections);
      if (window.feather) window.feather.replace();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
