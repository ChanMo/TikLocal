(function (global) {
  'use strict';

  function formatTime(seconds) {
    if (!seconds || Number.isNaN(seconds) || seconds === Infinity || seconds < 0) return '00:00';
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function getImageContainRect(imgEl) {
    if (!imgEl) return null;
    var rect = imgEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;

    var naturalW = imgEl.naturalWidth || 0;
    var naturalH = imgEl.naturalHeight || 0;
    if (!naturalW || !naturalH) {
      return {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      };
    }

    var containerRatio = rect.width / rect.height;
    var imageRatio = naturalW / naturalH;
    var drawWidth = rect.width;
    var drawHeight = rect.height;

    if (imageRatio > containerRatio) {
      drawHeight = rect.width / imageRatio;
    } else {
      drawWidth = rect.height * imageRatio;
    }

    var offsetX = (rect.width - drawWidth) / 2;
    var offsetY = (rect.height - drawHeight) / 2;
    return {
      left: rect.left + offsetX,
      top: rect.top + offsetY,
      width: drawWidth,
      height: drawHeight,
    };
  }

  function setMagnifierPosition(lensEl, x, y) {
    if (!lensEl) return;
    lensEl.style.left = String(x) + 'px';
    lensEl.style.top = String(y) + 'px';
  }

  function updateMagnifierContent(options) {
    var opts = options || {};
    var imgEl = opts.imageEl;
    var lensEl = opts.lensEl;
    var centerX = Number(opts.centerX || 0);
    var centerY = Number(opts.centerY || 0);
    var zoomLevel = Number(opts.zoomLevel || 2.5);
    if (!imgEl || !lensEl) return false;

    var rect = getImageContainRect(imgEl);
    if (!rect || !rect.width || !rect.height) return false;

    var relX = Math.max(0, Math.min(1, (centerX - rect.left) / rect.width));
    var relY = Math.max(0, Math.min(1, (centerY - rect.top) / rect.height));

    lensEl.style.backgroundImage = "url('" + String(imgEl.src || '').replace(/'/g, "\\'") + "')";
    lensEl.style.backgroundSize = String(rect.width * zoomLevel) + 'px ' + String(rect.height * zoomLevel) + 'px';

    var magWidth = lensEl.offsetWidth;
    var magHeight = lensEl.offsetHeight;
    var bgX = -(relX * rect.width * zoomLevel - magWidth / 2);
    var bgY = -(relY * rect.height * zoomLevel - magHeight / 2);
    lensEl.style.backgroundPosition = String(bgX) + 'px ' + String(bgY) + 'px';
    return true;
  }

  global.FlowUIShared = {
    formatTime: formatTime,
    getImageContainRect: getImageContainRect,
    setMagnifierPosition: setMagnifierPosition,
    updateMagnifierContent: updateMagnifierContent,
  };
})(window);
