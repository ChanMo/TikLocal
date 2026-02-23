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
    var sourceState = new Map();
    var captionCache = new Map();
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
      favoriteState.set(key, value);
      onFavoriteChange(value, key);
      return value;
    }

    async function toggleFavorite(name) {
      var key = String(name || '');
      if (!key) return false;
      var before = favoriteState.has(key) ? !!favoriteState.get(key) : await syncFavorite(key);
      var optimistic = !before;
      favoriteState.set(key, optimistic);
      onFavoriteChange(optimistic, key);
      try {
        var result = optimistic;
        if (typeof actions.toggleFavorite === 'function') {
          result = !!(await actions.toggleFavorite(key));
        }
        favoriteState.set(key, result);
        onFavoriteChange(result, key);
        return result;
      } catch (error) {
        favoriteState.set(key, before);
        onFavoriteChange(before, key);
        throw error;
      }
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

    function clearCaption(resetUri) {
      var shouldReset = resetUri !== false;
      if (shouldReset) currentCaptionUri = '';
      onCaptionClear(shouldReset);
    }

    async function loadCaption(uri) {
      var key = String(uri || '');
      if (!key) {
        clearCaption(true);
        return null;
      }
      if (captionCache.has(key)) {
        currentCaptionUri = key;
        var cached = captionCache.get(key) || null;
        onCaptionRender(cached, key);
        return cached;
      }

      clearCaption(true);
      currentCaptionUri = key;
      var reqId = ++captionRequestId;
      try {
        var data = null;
        if (typeof actions.getImageMetadata === 'function') {
          data = await actions.getImageMetadata(key);
        }
        if (reqId !== captionRequestId || currentCaptionUri !== key) return null;
        if (!(data && data.success)) {
          onError('caption_load', data);
          return null;
        }
        var payload = data.data || null;
        captionCache.set(key, payload);
        onCaptionRender(payload, key);
        return payload;
      } catch (error) {
        if (reqId !== captionRequestId || currentCaptionUri !== key) return null;
        onError('caption_load', error);
        return null;
      }
    }

    async function generateCaption(uri, options) {
      var key = String(uri || '');
      if (!key) return null;

      var conf = options || {};
      var confirmExisting = !!conf.confirmExisting;
      var existing = captionCache.get(key) || null;
      if (confirmExisting && hasContentCaption(existing) && confirmCaptionReplace) {
        var accepted = await confirmCaptionReplace(key, existing);
        if (!accepted) return { skipped: true };
      }

      onCaptionLoading(true);
      try {
        var data = null;
        if (typeof actions.generateImageMetadata === 'function') {
          data = await actions.generateImageMetadata(key);
        }
        if (!(data && data.success)) {
          onError('caption_generate', data);
          return null;
        }
        var payload = data.data || null;
        captionCache.set(key, payload);
        if (currentCaptionUri === key) {
          onCaptionRender(payload, key);
        }
        return payload;
      } catch (error) {
        onError('caption_generate', error);
        return null;
      } finally {
        onCaptionLoading(false);
      }
    }

    function markCaptionCurrent(uri) {
      currentCaptionUri = String(uri || '');
    }

    function getCaptionCurrentUri() {
      return currentCaptionUri;
    }

    return {
      syncFavorite: syncFavorite,
      toggleFavorite: toggleFavorite,
      syncSource: syncSource,
      clearCaption: clearCaption,
      loadCaption: loadCaption,
      generateCaption: generateCaption,
      markCaptionCurrent: markCaptionCurrent,
      getCaptionCurrentUri: getCaptionCurrentUri,
    };
  }

  global.createFlowMediaActionsController = createFlowMediaActionsController;
})(window);
