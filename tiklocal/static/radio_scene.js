/*
 * Radio scene — a full-screen fragment shader behind the Radio page.
 *
 * Plain WebGL 1 with no dependencies: one triangle covering the screen, one shader
 * loaded from a .frag file, and two textures made from the current cover art
 * (a small sharp copy with mipmaps and a heavily blurred copy).
 *
 *   var scene = RadioScene.create(canvas, { shaderUrl: '...', onReady: fn, onFail: fn });
 *   scene.setRunning(true);        // animate; false eases to a stop and holds a still frame
 *   scene.setCover(imgOrNull);     // null falls back to the palette
 *   scene.setPalette(['#466b61', '#a88756', '#d7d2c4']);
 *   scene.setDark(true);
 *
 * create() returns null when WebGL is unavailable; onFail fires for later failures
 * (shader fetch or compile errors, lost context) so the caller can fall back.
 */
(function () {
  'use strict';

  var MAX_FPS = 30;
  var MAX_PIXELS = 1000000;
  var SHARP_SIZE = 256;
  var BLUR_SIZE = 64;
  var COVER_FADE_MS = 2600;
  var SPEED_EASE_MS = 1400;
  var DARK_EASE_MS = 900;

  var VERTEX_SHADER = [
    'attribute vec2 aPosition;',
    'void main() { gl_Position = vec4(aPosition, 0.0, 1.0); }',
  ].join('\n');

  function create(canvas, options) {
    options = options || {};
    var gl = getContext(canvas);
    if (!gl) return null;

    var program = null;
    var uniforms = {};
    var sharpTexture = null;
    var blurTexture = null;
    var shaderSource = '';
    var failed = false;
    var destroyed = false;

    var running = false;
    var speed = 0;
    var sceneTime = 180 + Math.random() * 600;
    var dark = 1;
    var darkTarget = 1;
    var frameId = 0;
    var lastTick = 0;
    var lastDraw = 0;
    var flashStart = -1;
    var nextFlashAt = 0;

    var palette = ['#466b61', '#a88756', '#d7d2c4'];
    var hasCover = false;
    var art = createArtCanvases();
    var fade = null;

    var stats = options.stats ? createStats(canvas) : null;

    canvas.addEventListener('webglcontextlost', onContextLost);
    canvas.addEventListener('webglcontextrestored', onContextRestored);
    window.addEventListener('resize', requestFrame);

    renderArt(drawPalette(art.target, palette));
    commitArt(1);

    fetch(options.shaderUrl)
      .then(function (response) {
        if (!response.ok) throw new Error('Shader request failed: ' + response.status);
        return response.text();
      })
      .then(function (source) {
        shaderSource = source;
        setupGl();
        if (options.onReady) options.onReady();
        requestFrame();
      })
      .catch(fail);

    function setupGl() {
      program = buildProgram(gl, VERTEX_SHADER, shaderSource);
      gl.useProgram(program);

      var buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      var position = gl.getAttribLocation(program, 'aPosition');
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

      ['uRes', 'uTime', 'uDark', 'uRain', 'uFlash', 'uSharp', 'uBlur'].forEach(function (name) {
        uniforms[name] = gl.getUniformLocation(program, name);
      });

      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      sharpTexture = createTexture(gl, true);
      blurTexture = createTexture(gl, false);
      uploadArt();

      gl.uniform1i(uniforms.uSharp, 0);
      gl.uniform1i(uniforms.uBlur, 1);
    }

    function uploadArt() {
      if (!sharpTexture) return;
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, sharpTexture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, art.sharp);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, blurTexture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, art.blur);
    }

    function fail(error) {
      if (failed || destroyed) return;
      failed = true;
      stop();
      if (window.console && console.warn) console.warn('Radio scene unavailable:', error);
      if (options.onFail) options.onFail(error);
    }

    function onContextLost(event) {
      event.preventDefault();
      program = null;
      sharpTexture = null;
      blurTexture = null;
      fail(new Error('WebGL context lost'));
    }

    function onContextRestored() {
      if (destroyed || !shaderSource) return;
      try {
        setupGl();
        failed = false;
        if (options.onReady) options.onReady();
        requestFrame();
      } catch (error) {
        fail(error);
      }
    }

    // Cover art ----------------------------------------------------------------

    function setCover(image) {
      var usable = Boolean(image && image.naturalWidth);
      if (!usable && !hasCover) return;
      hasCover = usable;
      if (usable) drawCover(art.target, image);
      startFade();
    }

    function setPalette(colors) {
      if (!colors || !colors.length) return;
      palette = colors.slice(0, 3);
      if (!hasCover) startFade();
    }

    function startFade() {
      if (!hasCover) drawPalette(art.target, palette);
      renderArt(art.target);
      fade = { start: now() };
      requestFrame();
    }

    function renderArt(source) {
      // Snapshot what is on screen now, then prepare the incoming sharp and blurred art.
      art.fromSharpCtx.clearRect(0, 0, SHARP_SIZE, SHARP_SIZE);
      art.fromSharpCtx.drawImage(art.sharp, 0, 0);
      art.fromBlurCtx.clearRect(0, 0, BLUR_SIZE, BLUR_SIZE);
      art.fromBlurCtx.drawImage(art.blur, 0, 0);

      art.toSharpCtx.clearRect(0, 0, SHARP_SIZE, SHARP_SIZE);
      art.toSharpCtx.drawImage(source, 0, 0, SHARP_SIZE, SHARP_SIZE);
      art.toBlurCtx.clearRect(0, 0, BLUR_SIZE, BLUR_SIZE);
      art.toBlurCtx.drawImage(source, 0, 0, BLUR_SIZE, BLUR_SIZE);
      blurCanvas(art.toBlurCtx, BLUR_SIZE, 5, 3);
      return source;
    }

    function commitArt(progress) {
      var eased = progress * progress * (3 - 2 * progress);
      blend(art.sharpCtx, art.fromSharp, art.toSharp, SHARP_SIZE, eased);
      blend(art.blurCtx, art.fromBlur, art.toBlur, BLUR_SIZE, eased);
      uploadArt();
    }

    // Loop ----------------------------------------------------------------------

    function setRunning(value) {
      running = Boolean(value);
      requestFrame();
    }

    function setDark(value) {
      darkTarget = value ? 1 : 0;
      requestFrame();
    }

    function requestFrame() {
      if (destroyed || failed || frameId) return;
      frameId = window.requestAnimationFrame(tick);
    }

    function stop() {
      if (frameId) window.cancelAnimationFrame(frameId);
      frameId = 0;
      lastTick = 0;
    }

    function tick(timestamp) {
      frameId = 0;
      if (!program) return;

      var elapsed = lastTick ? Math.min(timestamp - lastTick, 100) : 0;
      if (lastTick && timestamp - lastDraw < 1000 / MAX_FPS - 2 && needsAnotherFrame()) {
        frameId = window.requestAnimationFrame(tick);
        return;
      }
      lastTick = timestamp;
      lastDraw = timestamp;

      var target = running ? 1 : 0;
      speed = approach(speed, target, elapsed / SPEED_EASE_MS);
      dark = approach(dark, darkTarget, elapsed / DARK_EASE_MS);
      sceneTime += (elapsed / 1000) * speed;

      if (fade) {
        var progress = Math.min(1, (now() - fade.start) / COVER_FADE_MS);
        commitArt(progress);
        if (progress >= 1) fade = null;
      }

      draw(timestamp);
      if (stats) stats.frame(canvas);
      if (needsAnotherFrame()) frameId = window.requestAnimationFrame(tick);
      else lastTick = 0;
    }

    function needsAnotherFrame() {
      return running || speed > 0.001 || Boolean(fade) || flashStart >= 0 || Math.abs(dark - darkTarget) > 0.001;
    }

    function draw(timestamp) {
      resize();
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uniforms.uRes, canvas.width, canvas.height);
      gl.uniform1f(uniforms.uTime, sceneTime);
      gl.uniform1f(uniforms.uDark, dark);
      gl.uniform1f(uniforms.uRain, rainAmount(sceneTime));
      gl.uniform1f(uniforms.uFlash, lightning(timestamp));
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    function resize() {
      var ratio = Math.min(Math.max((window.devicePixelRatio || 1) * 0.6, 0.6), 1.2);
      var width = Math.max(1, canvas.clientWidth * ratio);
      var height = Math.max(1, canvas.clientHeight * ratio);
      var scale = Math.min(1, Math.sqrt(MAX_PIXELS / (width * height)));
      width = Math.round(width * scale);
      height = Math.round(height * scale);
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
    }

    // Rain slowly swells and eases so long sessions never settle into one density.
    function rainAmount(t) {
      return clamp(0.56 + 0.2 * Math.sin(t / 97) + 0.12 * Math.sin(t / 41 + 1.3), 0.2, 0.95);
    }

    // A distant flash every minute or two, only at night and only while playing.
    function lightning(timestamp) {
      if (flashStart < 0) {
        if (!running || dark < 0.6 || speed < 0.9) {
          nextFlashAt = 0;
          return 0;
        }
        if (!nextFlashAt) nextFlashAt = timestamp + randomBetween(45000, 150000);
        if (timestamp < nextFlashAt) return 0;
        flashStart = timestamp;
        nextFlashAt = 0;
      }
      var t = (timestamp - flashStart) / 1000;
      if (t > 1.2) {
        flashStart = -1;
        return 0;
      }
      return pulse(t, 0, 0.55) + pulse(t, 0.13, 0.3) + pulse(t, 0.34, 0.42);
    }

    function destroy() {
      destroyed = true;
      stop();
      canvas.removeEventListener('webglcontextlost', onContextLost);
      canvas.removeEventListener('webglcontextrestored', onContextRestored);
      window.removeEventListener('resize', requestFrame);
      if (stats) stats.remove();
    }

    return {
      setRunning: setRunning,
      setCover: setCover,
      setPalette: setPalette,
      setDark: setDark,
      destroy: destroy,
    };
  }

  // Helpers -------------------------------------------------------------------

  function getContext(canvas) {
    var attributes = {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      preserveDrawingBuffer: false,
      powerPreference: 'low-power',
    };
    try {
      return canvas.getContext('webgl', attributes) || canvas.getContext('experimental-webgl', attributes);
    } catch (error) {
      return null;
    }
  }

  function buildProgram(gl, vertexSource, fragmentSource) {
    var program = gl.createProgram();
    gl.attachShader(program, compileShader(gl, gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error('Shader link failed: ' + gl.getProgramInfoLog(program));
    }
    return program;
  }

  function compileShader(gl, type, source) {
    var shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error('Shader compile failed: ' + gl.getShaderInfoLog(shader));
    }
    return shader;
  }

  function createTexture(gl, mipmapped) {
    var texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mipmapped ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    return texture;
  }

  function createArtCanvases() {
    var art = {};
    [['sharp', SHARP_SIZE], ['blur', BLUR_SIZE], ['fromSharp', SHARP_SIZE], ['fromBlur', BLUR_SIZE],
      ['toSharp', SHARP_SIZE], ['toBlur', BLUR_SIZE], ['target', SHARP_SIZE]].forEach(function (entry) {
      var canvas = document.createElement('canvas');
      canvas.width = entry[1];
      canvas.height = entry[1];
      art[entry[0]] = canvas;
      art[entry[0] + 'Ctx'] = canvas.getContext('2d', { willReadFrequently: entry[0] === 'toBlur' });
    });
    return art;
  }

  // Square crop from the middle of the image, like object-fit: cover.
  function drawCover(canvas, image) {
    var ctx = canvas.getContext('2d');
    var side = Math.min(image.naturalWidth, image.naturalHeight);
    var sx = (image.naturalWidth - side) / 2;
    var sy = (image.naturalHeight - side) / 2;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, sx, sy, side, side, 0, 0, canvas.width, canvas.height);
    return canvas;
  }

  // Soft color fields from the track palette when there is no cover.
  function drawPalette(canvas, colors) {
    var ctx = canvas.getContext('2d');
    var size = canvas.width;
    var base = ctx.createLinearGradient(0, 0, size, size);
    base.addColorStop(0, colors[0]);
    base.addColorStop(1, colors[1] || colors[0]);
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, size, size);
    [[0.25, 0.7, colors[1]], [0.75, 0.3, colors[2]], [0.6, 0.85, colors[0]]].forEach(function (blob) {
      if (!blob[2]) return;
      var glow = ctx.createRadialGradient(blob[0] * size, blob[1] * size, 0, blob[0] * size, blob[1] * size, size * 0.45);
      glow.addColorStop(0, blob[2]);
      glow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, size, size);
    });
    return canvas;
  }

  function blend(ctx, from, to, size, amount) {
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, size, size);
    ctx.drawImage(from, 0, 0);
    ctx.globalAlpha = amount;
    ctx.drawImage(to, 0, 0);
    ctx.globalAlpha = 1;
  }

  // Repeated box blur approximates a gaussian; the canvas is tiny so this is cheap.
  function blurCanvas(ctx, size, radius, passes) {
    var image = ctx.getImageData(0, 0, size, size);
    var data = image.data;
    var scratch = new Uint8ClampedArray(data.length);
    for (var pass = 0; pass < passes; pass += 1) {
      boxBlur(data, scratch, size, radius, 4, size * 4);
      boxBlur(scratch, data, size, radius, size * 4, 4);
    }
    ctx.putImageData(image, 0, 0);
  }

  // One-dimensional blur along `step`, repeated for every line along `lineStep`.
  function boxBlur(source, target, size, radius, step, lineStep) {
    var span = radius * 2 + 1;
    for (var line = 0; line < size; line += 1) {
      var origin = line * lineStep;
      for (var channel = 0; channel < 4; channel += 1) {
        var sum = 0;
        for (var k = -radius; k <= radius; k += 1) {
          sum += source[origin + clampIndex(k, size) * step + channel];
        }
        for (var i = 0; i < size; i += 1) {
          target[origin + i * step + channel] = sum / span;
          sum += source[origin + clampIndex(i + radius + 1, size) * step + channel];
          sum -= source[origin + clampIndex(i - radius, size) * step + channel];
        }
      }
    }
  }

  function clampIndex(index, size) {
    return index < 0 ? 0 : (index >= size ? size - 1 : index);
  }

  function createStats(canvas) {
    var node = document.createElement('div');
    node.style.cssText = 'position:fixed;left:8px;top:8px;z-index:9999;padding:4px 6px;'
      + 'font:11px/1.2 ui-monospace,monospace;color:#fff;background:rgba(0,0,0,.55);border-radius:4px;'
      + 'pointer-events:none';
    document.body.appendChild(node);
    var frames = 0;
    var windowStart = now();
    return {
      frame: function () {
        frames += 1;
        var elapsed = now() - windowStart;
        if (elapsed < 1000) return;
        node.textContent = Math.round((frames * 1000) / elapsed) + ' fps · ' + canvas.width + '×' + canvas.height;
        frames = 0;
        windowStart = now();
      },
      remove: function () { node.remove(); },
    };
  }

  function pulse(t, at, strength) {
    return t < at ? 0 : strength * Math.exp(-(t - at) * 13);
  }

  function approach(value, target, step) {
    if (value < target) return Math.min(target, value + step);
    return Math.max(target, value - step);
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function randomBetween(min, max) {
    return min + Math.random() * (max - min);
  }

  function now() {
    return window.performance && performance.now ? performance.now() : Date.now();
  }

  window.RadioScene = { create: create };
})();
