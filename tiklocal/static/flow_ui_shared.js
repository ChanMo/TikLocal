(function (global) {
  'use strict';

  function formatTime(seconds) {
    if (!seconds || Number.isNaN(seconds) || seconds === Infinity || seconds < 0) return '00:00';
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function getContainRect(el, naturalW, naturalH) {
    if (!el) return null;
    var rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;

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

  function getImageContainRect(imgEl) {
    var naturalW = imgEl && imgEl.naturalWidth ? imgEl.naturalWidth : 0;
    var naturalH = imgEl && imgEl.naturalHeight ? imgEl.naturalHeight : 0;
    return getContainRect(imgEl, naturalW, naturalH);
  }

  function getVideoContainRect(videoEl) {
    var naturalW = videoEl && videoEl.videoWidth ? videoEl.videoWidth : 0;
    var naturalH = videoEl && videoEl.videoHeight ? videoEl.videoHeight : 0;
    return getContainRect(videoEl, naturalW, naturalH);
  }

  function setMagnifierPosition(lensEl, x, y) {
    if (!lensEl) return;
    lensEl.style.left = String(x) + 'px';
    lensEl.style.top = String(y) + 'px';
  }

  function ensureLensCanvas(lensEl) {
    if (!lensEl) return null;
    var canvas = lensEl.querySelector('.magnifier-canvas');
    if (canvas) return canvas;

    canvas = document.createElement('canvas');
    canvas.className = 'magnifier-canvas';
    canvas.style.position = 'absolute';
    canvas.style.inset = '0';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.borderRadius = 'inherit';
    canvas.style.display = 'none';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '0';

    lensEl.insertBefore(canvas, lensEl.firstChild);
    return canvas;
  }

  function hideLensCanvas(lensEl) {
    if (!lensEl) return;
    var canvas = lensEl.querySelector('.magnifier-canvas');
    if (!canvas) return;
    canvas.style.display = 'none';
  }

  function updateMagnifierContent(options) {
    var opts = options || {};
    var imgEl = opts.imageEl;
    var lensEl = opts.lensEl;
    var centerX = Number(opts.centerX || 0);
    var centerY = Number(opts.centerY || 0);
    var zoomLevel = Number(opts.zoomLevel || 2.5);
    if (!imgEl || !lensEl) return false;

    hideLensCanvas(lensEl);

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

  function updateVideoMagnifierContent(options) {
    var opts = options || {};
    var videoEl = opts.videoEl;
    var lensEl = opts.lensEl;
    var centerX = Number(opts.centerX || 0);
    var centerY = Number(opts.centerY || 0);
    var zoomLevel = Number(opts.zoomLevel || 2.5);
    var maxPixelRatio = Number(opts.maxPixelRatio || 2);

    if (!videoEl || !lensEl) return false;
    if (!videoEl.videoWidth || !videoEl.videoHeight) return false;

    var rect = getVideoContainRect(videoEl);
    if (!rect || !rect.width || !rect.height) return false;

    var relX = Math.max(0, Math.min(1, (centerX - rect.left) / rect.width));
    var relY = Math.max(0, Math.min(1, (centerY - rect.top) / rect.height));

    var canvas = ensureLensCanvas(lensEl);
    if (!canvas) return false;

    var dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, maxPixelRatio));
    var displayW = Math.max(1, lensEl.clientWidth || lensEl.offsetWidth || 1);
    var displayH = Math.max(1, lensEl.clientHeight || lensEl.offsetHeight || 1);
    var pixelW = Math.max(1, Math.round(displayW * dpr));
    var pixelH = Math.max(1, Math.round(displayH * dpr));
    if (canvas.width !== pixelW || canvas.height !== pixelH) {
      canvas.width = pixelW;
      canvas.height = pixelH;
    }
    canvas.style.display = 'block';

    var ctx = canvas.getContext('2d');
    if (!ctx) return false;

    // Base sample size should match lens coverage at 1x, then shrink by zoom.
    var srcW = (displayW * videoEl.videoWidth / rect.width) / zoomLevel;
    var srcH = (displayH * videoEl.videoHeight / rect.height) / zoomLevel;
    srcW = Math.max(1, Math.min(srcW, videoEl.videoWidth));
    srcH = Math.max(1, Math.min(srcH, videoEl.videoHeight));
    var srcX = relX * videoEl.videoWidth - (srcW / 2);
    var srcY = relY * videoEl.videoHeight - (srcH / 2);
    srcX = Math.max(0, Math.min(srcX, videoEl.videoWidth - srcW));
    srcY = Math.max(0, Math.min(srcY, videoEl.videoHeight - srcH));

    lensEl.style.backgroundImage = 'none';
    lensEl.style.backgroundSize = '';
    lensEl.style.backgroundPosition = '';

    ctx.clearRect(0, 0, pixelW, pixelH);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    try {
      ctx.drawImage(videoEl, srcX, srcY, srcW, srcH, 0, 0, pixelW, pixelH);
      return true;
    } catch (error) {
      return false;
    }
  }

  global.FlowUIShared = {
    formatTime: formatTime,
    getImageContainRect: getImageContainRect,
    getVideoContainRect: getVideoContainRect,
    setMagnifierPosition: setMagnifierPosition,
    updateMagnifierContent: updateMagnifierContent,
    updateVideoMagnifierContent: updateVideoMagnifierContent,
  };
})(window);
