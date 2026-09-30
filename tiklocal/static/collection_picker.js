(function (global) {
  'use strict';

  var folderIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>';
  var checkIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
  // Ignore the click that opened the sheet so it does not land on the backdrop and close it again.
  var openGuardMs = 520;

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  async function request(url, options) {
    var response = await fetch(url, options || {});
    var payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok || !(payload && payload.success)) {
      throw new Error((payload && payload.error) || 'Request failed');
    }
    return payload.data || {};
  }

  function sendUris(collectionId, method, uri) {
    return request('/api/collections/' + encodeURIComponent(collectionId) + '/items', {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uris: [uri] }),
    });
  }

  // One "Add to Collection" sheet bound to the media currently on screen.
  function createPicker(opts) {
    var button = opts.button;
    var countEl = opts.countEl;
    var modal = opts.modal;
    var meta = opts.meta;
    var createBtn = opts.createBtn;
    var nameInput = opts.nameInput;
    var list = opts.list;
    var itemClass = opts.itemClass;
    var emptyClass = opts.emptyClass;
    var currentUri = function () { return String(opts.currentUri() || ''); };

    var cache = new Map();
    var catalog = [];
    var selectedIds = new Set();
    var openedAt = 0;

    function showNames(names) {
      var count = names.length;
      var preview = names.slice(0, 2).join(', ');
      var rest = count - 2;
      var label = rest > 0 ? 'In: ' + preview + ' +' + rest : 'In: ' + preview;
      button.classList.toggle('has-collection', count > 0);
      countEl.textContent = count > 99 ? '99+' : String(count);
      button.title = count > 0 ? label : 'Add to Collection';
      if (meta) meta.textContent = count > 0 ? label : 'Not in any collections';
    }

    function showState(state) {
      selectedIds = new Set(state.ids);
      showNames(state.names);
    }

    async function membership(uri, force) {
      if (!force && cache.has(uri)) return cache.get(uri);
      var data = await request('/api/collections/by-media?uri=' + encodeURIComponent(uri));
      var state = { ids: [], names: [] };
      (Array.isArray(data.items) ? data.items : []).forEach(function (entry) {
        var id = String((entry && entry.id) || '').trim();
        var name = String((entry && entry.name) || '').trim();
        if (id) state.ids.push(id);
        if (name) state.names.push(name);
      });
      cache.set(uri, state);
      return state;
    }

    async function sync(uri, force) {
      var key = String(uri || '');
      if (!key) {
        showState({ ids: [], names: [] });
        return;
      }
      var state = { ids: [], names: [] };
      try {
        state = await membership(key, !!force);
      } catch (error) {
        // Unknown membership shows as none rather than a stale collection count.
      }
      if (currentUri() === key) showState(state);
    }

    function isOpen() {
      return modal.classList.contains('active');
    }

    function close() {
      modal.classList.remove('active');
      modal.setAttribute('aria-hidden', 'true');
      createBtn.disabled = false;
      openedAt = 0;
    }

    function showMessage(text) {
      list.innerHTML = '<div class="' + emptyClass + '">' + text + '</div>';
    }

    function render() {
      if (!catalog.length) {
        showMessage('No collections yet. Create one first.');
        return;
      }
      list.innerHTML = catalog.map(function (item) {
        var id = String(item.id || '');
        var count = Number(item.item_count || 0);
        var selected = selectedIds.has(id);
        return '<label class="' + itemClass + (selected ? ' is-selected' : '') + '" data-id="' + escapeHtml(id) + '">'
          + '<span class="coll-icon">' + folderIcon + '</span>'
          + '<span class="coll-name">' + escapeHtml(String(item.name || 'Untitled collection')) + '</span>'
          + '<em class="coll-count">' + (count > 0 ? count : '') + '</em>'
          + '<span class="coll-check">' + checkIcon + '</span>'
          + '<input type="checkbox"' + (selected ? ' checked' : '') + ' />'
          + '</label>';
      }).join('');
    }

    async function open() {
      var uri = currentUri();
      if (!uri) return;
      openedAt = Date.now();
      modal.classList.add('active');
      modal.setAttribute('aria-hidden', 'false');
      showMessage('Loading...');
      try {
        var results = await Promise.all([request('/api/collections'), membership(uri, true)]);
        catalog = Array.isArray(results[0].items) ? results[0].items : [];
        showState(results[1]);
        render();
      } catch (error) {
        showMessage('Failed to load. Please try again.');
      }
    }

    async function create() {
      var name = String(nameInput.value || '').trim();
      if (!name) return;
      createBtn.disabled = true;
      try {
        var created = await request('/api/collections', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name }),
        });
        var createdId = String((created.item && created.item.id) || '').trim();
        var uri = currentUri();
        if (createdId && uri) await sendUris(createdId, 'POST', uri);
        nameInput.value = '';
        await open();
      } catch (error) {
        // The typed name stays in place so it can be retried.
      } finally {
        createBtn.disabled = false;
      }
    }

    async function toggle(collectionId, checked, rowEl, inputEl) {
      var uri = currentUri();
      if (!uri) return;
      rowEl.classList.add('is-pending');
      inputEl.disabled = true;
      try {
        await sendUris(collectionId, checked ? 'POST' : 'DELETE', uri);
        await sync(uri, true);
        catalog = catalog.map(function (entry) {
          if (String((entry && entry.id) || '') !== collectionId) return entry;
          var count = Number(entry.item_count || 0);
          return Object.assign({}, entry, { item_count: checked ? count + 1 : Math.max(0, count - 1) });
        });
        render();
      } catch (error) {
        inputEl.checked = !checked;
      } finally {
        rowEl.classList.remove('is-pending');
        inputEl.disabled = false;
      }
    }

    button.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      open();
    });
    button.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      open();
    });
    opts.closeBtn.addEventListener('click', function (event) {
      event.preventDefault();
      close();
    });
    modal.addEventListener('click', function (event) {
      if (openedAt && Date.now() - openedAt < openGuardMs) return;
      if (event.target === modal) close();
    });
    createBtn.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      create();
    });
    nameInput.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      create();
    });
    list.addEventListener('change', function (event) {
      var inputEl = event.target.closest('input[type="checkbox"]');
      var rowEl = inputEl && inputEl.closest('[data-id]');
      var collectionId = String((rowEl && rowEl.getAttribute('data-id')) || '').trim();
      if (collectionId) toggle(collectionId, !!inputEl.checked, rowEl, inputEl);
    });

    return { sync: sync, open: open, close: close, isOpen: isOpen };
  }

  global.TikLocalCollections = { request: request, createPicker: createPicker };
})(window);
