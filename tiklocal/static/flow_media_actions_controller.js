(function (global) {
  'use strict';

  function noop() {}

  function defaultActions() {
    return global.FlowActionsShared || {};
  }

  function hasContentCaption(payload) {
    if (!payload || typeof payload !== 'object') return false;
    var title = String(payload.title || '').trim();
    var tags = Array.isArray(payload.tags) ? payload.tags : [];
    return !!title || tags.length > 0;
  }

  function createFlowMediaActionsController(options) {
    var opts = options || {};
    var actions = opts.actions || defaultActions();

    var onFavoriteChange = typeof opts.onFavoriteChange === 'function' ? opts.onFavoriteChange : noop;
    var onSourceChange = typeof opts.onSourceChange === 'function' ? opts.onSourceChange : noop;
    var onCaptionClear = typeof opts.onCaptionClear === 'function' ? opts.onCaptionClear : noop;
    var onCaptionRender = typeof opts.onCaptionRender === 'function' ? opts.onCaptionRender : noop;
    var onCaptionLoading = typeof opts.onCaptionLoading === 'function' ? opts.onCaptionLoading : noop;
    var onError = typeof opts.onError === 'function' ? opts.onError : noop;
    var confirmCaptionReplace = typeof opts.confirmCaptionReplace === 'function' ? opts.confirmCaptionReplace : null;

    var favoriteState = new Map();
    var favoriteRequests = new Map();
    var sourceState = new Map();
    var captionCache = new Map();
    var captionRequests = new Map();
    var currentCaptionUri = '';
    var captionRequestId = 0;

    async function syncFavorite(name) {
      var key = String(name || '');
      if (!key) return false;
      if (favoriteState.has(key)) {
        var cached = !!favoriteState.get(key);
        onFavoriteChange(cached, key);
        return cached;
      }
      var value = false;
      if (typeof actions.getFavoriteState === 'function') {
        value = !!(await actions.getFavoriteState(key));
      }
      if (favoriteState.has(key)) value = favoriteState.get(key);
      favoriteState.set(key, value);
      onFavoriteChange(value, key);
      return value;
    }

    function toggleFavorite(name) {
      var key = String(name || '');
      if (!key) return Promise.resolve(false);
      if (favoriteRequests.has(key)) return favoriteRequests.get(key);
      var request = (async function () {
        var before = favoriteState.has(key) ? favoriteState.get(key) : await syncFavorite(key);
        favoriteState.set(key, !before);
        onFavoriteChange(!before, key);
        try {
          var result = await actions.toggleFavorite(key);
          favoriteState.set(key, result);
          onFavoriteChange(result, key);
          return result;
        } catch (error) {
          favoriteState.set(key, before);
          onFavoriteChange(before, key);
          throw error;
        }
      })().finally(function () { favoriteRequests.delete(key); });
      favoriteRequests.set(key, request);
      return request;
    }

    async function syncSource(name) {
      var key = String(name || '');
      if (!key) {
        onSourceChange(null, key);
        return null;
      }
      if (sourceState.has(key)) {
        var cached = sourceState.get(key) || null;
        onSourceChange(cached, key);
        return cached;
      }
      onSourceChange(null, key);
      var source = null;
      if (typeof actions.getSourceMeta === 'function') {
        source = await actions.getSourceMeta(key);
      }
      sourceState.set(key, source || null);
      onSourceChange(source || null, key);
      return source || null;
    }

    function clearCaption() {
      currentCaptionUri = '';
      ++captionRequestId;
      onCaptionLoading(false);
      onCaptionClear();
    }

    async function loadCaption(uri) {
      var key = String(uri || '');
      if (!key) { clearCaption(); return null; }
      currentCaptionUri = key;
      var reqId = ++captionRequestId;
      onCaptionLoading(captionRequests.has(key));
      if (captionCache.has(key)) {
        var cached = captionCache.get(key);
        onCaptionRender(cached, key);
        return cached;
      }
      onCaptionClear();
      try {
        var data = await actions.getImageMetadata(key);
        if (reqId !== captionRequestId || currentCaptionUri !== key || captionRequests.has(key)) return null;
        if (!(data && data.success)) throw new Error((data && data.error) || 'Failed to load the title');
        var payload = data.data || null;
        captionCache.set(key, payload);
        onCaptionRender(payload, key);
        return payload;
      } catch (error) {
        if (reqId === captionRequestId && currentCaptionUri === key && !captionRequests.has(key)) {
          onError('caption_load', error);
        }
        return null;
      }
    }

    function generateCaption(uri, options) {
      var key = String(uri || '');
      if (!key) return Promise.resolve(null);
      if (captionRequests.has(key)) return captionRequests.get(key);
      var request = (async function () {
        var conf = options || {};
        var existing = captionCache.get(key);
        if (conf.confirmExisting && hasContentCaption(existing) && confirmCaptionReplace) {
          if (!(await confirmCaptionReplace(key, existing))) return { skipped: true };
          if (currentCaptionUri !== key) return { skipped: true };
          conf.force = true;
        }
        if (currentCaptionUri === key) onCaptionLoading(true);
        try {
          var data = await actions.generateImageMetadata(key, conf);
          if (!(data && data.success)) throw new Error((data && data.error) || 'Failed to generate the title');
          var payload = data.data || null;
          captionCache.set(key, payload);
          if (currentCaptionUri === key) {
            ++captionRequestId;
            onCaptionRender(payload, key);
          }
          return data;
        } catch (error) {
          if (currentCaptionUri === key) onError('caption_generate', error);
          return null;
        }
      })().finally(function () {
        captionRequests.delete(key);
        if (currentCaptionUri === key) onCaptionLoading(false);
      });
      captionRequests.set(key, request);
      return request;
    }

    return {
      syncFavorite: syncFavorite,
      toggleFavorite: toggleFavorite,
      syncSource: syncSource,
      clearCaption: clearCaption,
      loadCaption: loadCaption,
      generateCaption: generateCaption,
    };
  }

  global.createFlowMediaActionsController = createFlowMediaActionsController;
})(window);
