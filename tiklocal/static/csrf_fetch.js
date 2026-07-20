(function (global) {
  'use strict';

  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? String(meta.content || '') : '';
  var originalFetch = global.fetch.bind(global);
  var unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

  global.TikLocalSecurity = {
    csrfToken: token,
  };

  if (!token) return;

  global.fetch = function (resource, options) {
    var init = Object.assign({}, options || {});
    var requestMethod = resource instanceof Request ? resource.method : 'GET';
    var method = String(init.method || requestMethod || 'GET').toUpperCase();
    var requestUrl = resource instanceof Request ? resource.url : String(resource || '');
    var target = new URL(requestUrl, global.location.href);

    if (target.origin === global.location.origin && unsafeMethods.has(method)) {
      var requestHeaders = resource instanceof Request ? resource.headers : undefined;
      var headers = new Headers(init.headers || requestHeaders || {});
      headers.set('X-CSRF-Token', token);
      init.headers = headers;
    }
    return originalFetch(resource, init);
  };
})(window);
