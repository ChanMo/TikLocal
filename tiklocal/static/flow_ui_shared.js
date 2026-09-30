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

  // A draggable lens over the current image or video. `target()` returns
  // { type: 'image' | 'video', el } for the media on screen, or null.
  function createMagnifier(opts) {
    var lens = opts.lens;
    var toggleBtn = opts.toggle;
    var zoomOptions = opts.zoomOptions;
    var zoomButtons = Array.prototype.slice.call(opts.zoomButtons || []);
    var activeClass = opts.activeClass || 'active';
    var active = false;
    var x = 0;
    var y = 0;
    var zoom = 2.5;
    var frame = null;

    function currentVideo() {
      var target = opts.target();
      return target && target.type === 'video' ? target.el : null;
    }

    function draw() {
      var target = opts.target();
      if (!target || !target.el) return;
      if (target.type === 'video') {
        updateVideoMagnifierContent({ videoEl: target.el, lensEl: lens, centerX: x, centerY: y, zoomLevel: zoom, maxPixelRatio: 2 });
      } else {
        updateMagnifierContent({ imageEl: target.el, lensEl: lens, centerX: x, centerY: y, zoomLevel: zoom });
      }
    }

    function cancelFrame() {
      if (!frame) return;
      if (frame.kind === 'rvfc') {
        try {
          frame.videoEl.cancelVideoFrameCallback(frame.id);
        } catch (error) {
          // The element may already be gone.
        }
      } else if (frame.kind === 'raf') {
        cancelAnimationFrame(frame.id);
      } else {
        clearTimeout(frame.id);
      }
      frame = null;
    }

    // Redraw a video lens on every presented frame; poll slowly while paused.
    function followVideo(videoEl) {
      cancelFrame();
      if (!videoEl) return;
      function tick() {
        frame = null;
        if (!active || currentVideo() !== videoEl) return;
        draw();
        if (videoEl.paused || videoEl.ended) {
          frame = { kind: 'timeout', id: setTimeout(function () { followVideo(videoEl); }, 120) };
          return;
        }
        followVideo(videoEl);
      }
      if (typeof videoEl.requestVideoFrameCallback === 'function') {
        frame = { kind: 'rvfc', id: videoEl.requestVideoFrameCallback(tick), videoEl: videoEl };
      } else {
        frame = { kind: 'raf', id: requestAnimationFrame(tick) };
      }
    }

    function showUI(visible) {
      toggleBtn.classList.toggle(activeClass, visible);
      zoomOptions.classList.toggle('show', visible);
      lens.classList.toggle('active', visible);
    }

    // Mirrors the state controller: another mode turning the lens off hides it here.
    function onStateChange(enabled) {
      active = !!enabled;
      if (active) return;
      cancelFrame();
      showUI(false);
    }

    function toggle(enable) {
      active = !!opts.setMagnifying(enable);
      if (!active) {
        cancelFrame();
        showUI(false);
        return;
      }
      showUI(true);
      var target = opts.target();
      var rect = null;
      if (target && target.type === 'video') rect = getVideoContainRect(target.el);
      else if (target) rect = getImageContainRect(target.el);
      x = rect ? rect.left + rect.width / 2 : window.innerWidth / 2;
      y = rect ? rect.top + rect.height / 2 : window.innerHeight / 2;
      setMagnifierPosition(lens, x, y);
      draw();
      if (target && target.type === 'video') followVideo(target.el);
      else cancelFrame();
    }

    function applyZoom(level) {
      zoom = level;
      opts.badge.textContent = level + 'x';
      zoomButtons.forEach(function (btn) {
        btn.classList.toggle('active', Number.parseFloat(btn.dataset.level || '2.5') === level);
      });
      lens.classList.toggle(opts.largeClass, level >= 5);
      if (active) setTimeout(draw, 40);
    }

    toggleBtn.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      toggle(!active);
    });
    zoomButtons.forEach(function (btn) {
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        applyZoom(Number.parseFloat(btn.dataset.level || '2.5'));
      });
    });

    var pan = new global.Hammer(lens);
    pan.get('pan').set({ direction: global.Hammer.DIRECTION_ALL, threshold: 0 });
    var startX = 0;
    var startY = 0;
    pan.on('panstart', function () {
      startX = x;
      startY = y;
      lens.style.transition = 'none';
    });
    pan.on('panmove', function (event) {
      x = startX + event.deltaX;
      y = startY + event.deltaY;
      setMagnifierPosition(lens, x, y);
      draw();
    });
    pan.on('panend', function () {
      lens.style.transition = opts.settleTransition || '';
    });

    global.addEventListener('resize', function () {
      if (active) draw();
    });

    applyZoom(zoom);

    return {
      isActive: function () { return active; },
      toggle: toggle,
      onStateChange: onStateChange,
      // Video elements call these so a playing or seeking video keeps the lens current.
      onVideoPlay: function (videoEl) {
        if (active && currentVideo() === videoEl) followVideo(videoEl);
      },
      onVideoSeeked: function (videoEl) {
        if (active && currentVideo() === videoEl) draw();
      },
    };
  }

  global.FlowUIShared = {
    formatTime: formatTime,
    createMagnifier: createMagnifier,
  };
})(window);
