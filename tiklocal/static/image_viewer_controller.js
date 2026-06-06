(function (global) {
  'use strict';

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function createImageViewerController(options) {
    var stage = options.stage;
    var image = options.image;
    var zoomInButton = options.zoomInButton || null;
    var zoomOutButton = options.zoomOutButton || null;
    var resetButton = options.resetButton || null;
    var zoomLabel = options.zoomLabel || null;
    var minScale = Number(options.minScale || 1);
    var maxScale = Number(options.maxScale || 6);
    var wheelFactor = Number(options.wheelFactor || 0.14);
    var doubleTapScale = Number(options.doubleTapScale || 2.5);

    var state = {
      scale: 1,
      x: 0,
      y: 0,
      dragging: false,
      dragStartX: 0,
      dragStartY: 0,
      startX: 0,
      startY: 0
    };

    function updateLabel() {
      if (zoomLabel) {
        zoomLabel.textContent = Math.round(state.scale * 100) + '%';
      }
      if (stage) {
        stage.classList.toggle('is-zoomed', state.scale > minScale + 0.001);
      }
    }

    function applyTransform() {
      image.style.transform = 'translate(' + state.x + 'px, ' + state.y + 'px) scale(' + state.scale + ')';
      updateLabel();
    }

    function clampPan() {
      var rect = stage.getBoundingClientRect();
      var imageRect = image.getBoundingClientRect();
      var naturalWidth = imageRect.width / state.scale;
      var naturalHeight = imageRect.height / state.scale;
      var scaledWidth = naturalWidth * state.scale;
      var scaledHeight = naturalHeight * state.scale;
      var maxX = Math.max(0, (scaledWidth - rect.width) / 2);
      var maxY = Math.max(0, (scaledHeight - rect.height) / 2);
      state.x = clamp(state.x, -maxX, maxX);
      state.y = clamp(state.y, -maxY, maxY);
    }

    function setScale(nextScale, anchorX, anchorY) {
      var previous = state.scale;
      nextScale = clamp(nextScale, minScale, maxScale);
      if (Math.abs(nextScale - previous) < 0.001) return;

      var rect = stage.getBoundingClientRect();
      var px = Number.isFinite(anchorX) ? anchorX - rect.left - rect.width / 2 : 0;
      var py = Number.isFinite(anchorY) ? anchorY - rect.top - rect.height / 2 : 0;
      var ratio = nextScale / previous;
      state.x = px - (px - state.x) * ratio;
      state.y = py - (py - state.y) * ratio;
      state.scale = nextScale;
      if (state.scale <= minScale + 0.001) {
        state.scale = minScale;
        state.x = 0;
        state.y = 0;
      } else {
        clampPan();
      }
      applyTransform();
    }

    function zoomBy(factor, anchorX, anchorY) {
      setScale(state.scale * factor, anchorX, anchorY);
    }

    function zoomIn() {
      zoomBy(1.35);
    }

    function zoomOut() {
      zoomBy(1 / 1.35);
    }

    function reset() {
      state.scale = minScale;
      state.x = 0;
      state.y = 0;
      applyTransform();
    }

    function onWheel(event) {
      event.preventDefault();
      var factor = event.deltaY < 0 ? 1 + wheelFactor : 1 / (1 + wheelFactor);
      zoomBy(factor, event.clientX, event.clientY);
    }

    function onPointerDown(event) {
      if (state.scale <= minScale + 0.001) return;
      state.dragging = true;
      state.dragStartX = event.clientX;
      state.dragStartY = event.clientY;
      state.startX = state.x;
      state.startY = state.y;
      stage.classList.add('is-dragging');
      try {
        stage.setPointerCapture(event.pointerId);
      } catch (err) {
        // Ignore capture failures on older browsers.
      }
    }

    function onPointerMove(event) {
      if (!state.dragging) return;
      event.preventDefault();
      state.x = state.startX + event.clientX - state.dragStartX;
      state.y = state.startY + event.clientY - state.dragStartY;
      clampPan();
      applyTransform();
    }

    function stopDragging(event) {
      state.dragging = false;
      stage.classList.remove('is-dragging');
      if (event && typeof event.pointerId !== 'undefined') {
        try {
          stage.releasePointerCapture(event.pointerId);
        } catch (err) {
          // Ignore capture failures on older browsers.
        }
      }
    }

    function onDoubleClick(event) {
      event.preventDefault();
      if (state.scale > minScale + 0.001) {
        reset();
      } else {
        setScale(doubleTapScale, event.clientX, event.clientY);
      }
    }

    stage.addEventListener('wheel', onWheel, { passive: false });
    stage.addEventListener('pointerdown', onPointerDown);
    stage.addEventListener('pointermove', onPointerMove);
    stage.addEventListener('pointerup', stopDragging);
    stage.addEventListener('pointercancel', stopDragging);
    stage.addEventListener('dblclick', onDoubleClick);
    zoomInButton && zoomInButton.addEventListener('click', zoomIn);
    zoomOutButton && zoomOutButton.addEventListener('click', zoomOut);
    resetButton && resetButton.addEventListener('click', reset);
    image.addEventListener('load', reset);

    reset();

    return {
      zoomIn: zoomIn,
      zoomOut: zoomOut,
      reset: reset,
      setScale: setScale,
      getState: function () {
        return {
          scale: state.scale,
          x: state.x,
          y: state.y
        };
      }
    };
  }

  global.createImageViewerController = createImageViewerController;
})(window);
