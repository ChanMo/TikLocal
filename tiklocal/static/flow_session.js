(function (global) {
  'use strict';

  function toKey(item, keyOf) {
    try {
      var key = keyOf(item);
      return String(key || '');
    } catch (error) {
      return '';
    }
  }

  function createFlowSession(options) {
    var opts = options || {};
    var keyOf = typeof opts.keyOf === 'function'
      ? opts.keyOf
      : function (item) { return String((item && item.name) || ''); };

    var items = [];
    var keys = new Set();
    var index = Number.isInteger(opts.initialIndex) ? opts.initialIndex : -1;
    var hasMore = opts.initialHasMore !== false;
    var loading = false;
    var cursor = opts.initialCursor || null;

    function appendUnique(batch) {
      var list = Array.isArray(batch) ? batch : [];
      var appendedIndices = [];
      for (var i = 0; i < list.length; i += 1) {
        var item = list[i];
        var key = toKey(item, keyOf);
        if (!key || keys.has(key)) continue;
        keys.add(key);
        items.push(item);
        appendedIndices.push(items.length - 1);
      }
      return {
        appended: appendedIndices.length,
        appendedIndices: appendedIndices,
      };
    }

    function currentItem() {
      if (index < 0 || index >= items.length) return null;
      return items[index];
    }

    function setIndex(next) {
      if (!Number.isInteger(next)) return index;
      index = Math.max(-1, Math.min(next, items.length - 1));
      return index;
    }

    function moveTo(next) {
      if (!Number.isInteger(next) || next < 0 || next >= items.length) return null;
      index = next;
      return currentItem();
    }

    function next() {
      if (index < items.length - 1) {
        index += 1;
        return currentItem();
      }
      return null;
    }

    function prev() {
      if (index > 0) {
        index -= 1;
        return currentItem();
      }
      return null;
    }

    function dropHead(count) {
      var removeCount = Math.max(0, Math.min(Number(count) || 0, items.length));
      if (!removeCount) return [];
      var removed = items.splice(0, removeCount);
      for (var i = 0; i < removed.length; i += 1) {
        var key = toKey(removed[i], keyOf);
        if (key) keys.delete(key);
      }
      index = Math.max(-1, index - removeCount);
      if (items.length === 0) index = -1;
      return removed;
    }

    async function loadMore(loader) {
      if (loading || !hasMore || typeof loader !== 'function') {
        return { skipped: true, appended: 0, appendedIndices: [] };
      }

      loading = true;
      try {
        var payload = await loader(cursor);
        var incoming = Array.isArray(payload && payload.items) ? payload.items : [];
        var appendResult = appendUnique(incoming);

        if (payload && Object.prototype.hasOwnProperty.call(payload, 'hasMore')) {
          hasMore = !!payload.hasMore;
        }
        if (payload && Object.prototype.hasOwnProperty.call(payload, 'cursor')) {
          cursor = payload.cursor;
        }

        return {
          skipped: false,
          payload: payload || {},
          appended: appendResult.appended,
          appendedIndices: appendResult.appendedIndices,
        };
      } finally {
        loading = false;
      }
    }

    function reset(next) {
      var conf = next || {};
      items.length = 0;
      keys.clear();
      index = Number.isInteger(conf.index) ? conf.index : -1;
      hasMore = conf.hasMore !== false;
      cursor = Object.prototype.hasOwnProperty.call(conf, 'cursor') ? conf.cursor : null;
    }

    appendUnique(opts.initialItems || []);
    index = Math.max(-1, Math.min(index, items.length - 1));

    return {
      items: items,
      currentItem: currentItem,
      getIndex: function () { return index; },
      setIndex: setIndex,
      moveTo: moveTo,
      next: next,
      prev: prev,
      hasMore: function () { return hasMore; },
      setHasMore: function (next) { hasMore = !!next; },
      isLoading: function () { return loading; },
      getCursor: function () { return cursor; },
      setCursor: function (next) { cursor = next; },
      appendUnique: appendUnique,
      loadMore: loadMore,
      dropHead: dropHead,
      reset: reset,
    };
  }

  global.createFlowSession = createFlowSession;
})(window);
