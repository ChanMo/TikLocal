(function (global) {
  'use strict';

  function encodeName(name) {
    return encodeURIComponent(String(name || ''));
  }

  async function readJsonResponse(response) {
    try {
      return await response.json();
    } catch (error) {
      return null;
    }
  }

  async function getFavoriteState(name) {
    var encoded = encodeName(name);
    if (!encoded) return false;
    var response = await fetch('/api/favorite/' + encoded);
    var data = await readJsonResponse(response);
    if (!response.ok || !data || typeof data.favorite !== 'boolean') {
      throw new Error((data && data.error) || '收藏操作失败，请重试。');
    }
    return data.favorite;
  }

  async function toggleFavorite(name) {
    var encoded = encodeName(name);
    if (!encoded) return false;
    var response = await fetch('/api/favorite/' + encoded, { method: 'POST' });
    var data = await readJsonResponse(response);
    if (!response.ok || !data || typeof data.favorite !== 'boolean') {
      throw new Error((data && data.error) || '收藏操作失败，请重试。');
    }
    return data.favorite;
  }

  async function getSourceMeta(name) {
    var encoded = encodeName(name);
    if (!encoded) return null;
    var response = await fetch('/api/source?file=' + encoded);
    var data = await readJsonResponse(response);
    if (!response.ok || !(data && data.success)) return null;
    return (data.data && data.data.source) || null;
  }

  async function getImageMetadata(uri) {
    var encoded = encodeName(uri);
    if (!encoded) return { success: false, error: 'missing uri' };
    var response = await fetch('/api/image/metadata?uri=' + encoded);
    var data = await readJsonResponse(response);
    if (!response.ok || !data || !data.success) throw new Error((data && data.error) || '标题请求失败');
    return data;
  }

  async function generateImageMetadata(uri, options) {
    var conf = options || {};
    if (!uri) return { success: false, error: 'missing uri' };
    var response = await fetch('/api/image/metadata', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri: uri, force: conf.force !== false, prompt_override: conf.promptOverride }),
    });
    var data = await readJsonResponse(response);
    if (!response.ok || !data || !data.success) throw new Error((data && data.error) || '标题请求失败');
    return data;
  }

  global.FlowActionsShared = {
    getFavoriteState: getFavoriteState,
    toggleFavorite: toggleFavorite,
    getSourceMeta: getSourceMeta,
    getImageMetadata: getImageMetadata,
    generateImageMetadata: generateImageMetadata,
  };
})(window);
