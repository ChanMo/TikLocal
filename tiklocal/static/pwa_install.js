(function (global) {
  'use strict';

  var deferredPrompt = null;
  var workerState = 'idle';
  var workerError = '';
  var currentScript = document.currentScript;
  var scriptUrl = new URL(currentScript && currentScript.src || global.location.href, global.location.href);
  var appVersion = scriptUrl.searchParams.get('v') || 'dev';
  var userAgent = global.navigator.userAgent || '';
  var isAppleMobile = /iphone|ipad|ipod/i.test(userAgent)
    || (global.navigator.platform === 'MacIntel' && global.navigator.maxTouchPoints > 1);
  var isMac = /macintosh|mac os x/i.test(userAgent) && !isAppleMobile;
  var isChromium = /chrome|chromium|crios|edg|opr/i.test(userAgent);
  var isSafari = /safari/i.test(userAgent) && !isChromium && !/android/i.test(userAgent);

  function isInstalled() {
    return global.matchMedia('(display-mode: standalone)').matches
      || global.navigator.standalone === true;
  }

  function browserName() {
    if (isAppleMobile) return 'ios';
    if (isSafari && isMac) return 'safari';
    if (isChromium) return 'chromium';
    return 'other';
  }

  function status() {
    var protocol = global.location.protocol;
    var secure = global.isSecureContext === true;
    var installed = isInstalled();
    var browser = browserName();
    var reason = 'manual';
    if (installed) reason = 'installed';
    else if (!secure) reason = protocol === 'https:' ? 'untrusted-certificate' : 'insecure-http';
    else if (deferredPrompt) reason = 'ready';
    else if (browser === 'safari') reason = 'safari-menu';
    else if (browser === 'ios') reason = 'share-menu';
    else if (browser === 'chromium') reason = 'chromium-waiting';

    return {
      installed: installed,
      canPrompt: Boolean(deferredPrompt),
      secure: secure,
      protocol: protocol,
      browser: browser,
      reason: reason,
      workerState: workerState,
      workerError: workerError,
      guideUrl: '/install',
    };
  }

  function announce() {
    global.dispatchEvent(new CustomEvent('tiklocal:pwa-status', { detail: status() }));
  }

  global.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferredPrompt = event;
    announce();
  });

  global.addEventListener('appinstalled', function () {
    deferredPrompt = null;
    announce();
  });

  global.TikLocalPWA = {
    status: status,
    install: async function () {
      if (isInstalled()) return { outcome: 'installed' };
      if (!deferredPrompt) return { outcome: 'guide', url: '/install' };
      await deferredPrompt.prompt();
      var choice = await deferredPrompt.userChoice;
      deferredPrompt = null;
      announce();
      return choice;
    },
  };

  if (global.isSecureContext && 'serviceWorker' in global.navigator) {
    workerState = 'registering';
    global.navigator.serviceWorker.register('/service-worker.js?v=' + encodeURIComponent(appVersion), { scope: '/' })
      .then(function () {
        workerState = global.navigator.serviceWorker.controller ? 'active' : 'installed';
        announce();
      })
      .catch(function (error) {
        workerState = 'error';
        workerError = String(error && error.message || error || 'registration failed');
        announce();
      });
    global.navigator.serviceWorker.addEventListener('controllerchange', function () {
      workerState = 'active';
      announce();
    });
  } else {
    workerState = global.isSecureContext ? 'unsupported' : 'blocked';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', announce, { once: true });
  } else {
    announce();
  }
})(window);
