/*
 * Radio rain sound — procedural rain mixed beside the music.
 *
 * The music keeps its own <audio> element; rain runs in a separate AudioContext, so
 * music playback (and iOS background audio) never depends on Web Audio.
 * Every layer is a looped buffer synthesised once, so nothing needs a timer to keep
 * going in a background tab, and loops of different lengths never line up audibly:
 *   wash     stereo pink noise, band-limited      the steady hiss of rain
 *   body     brown noise under ~300 Hz            rain on roofs and the street
 *   patter   two drop loops (light and heavy)     drops tapping on the glass
 *   thunder  one-shot rumble                      a few seconds after a lightning flash
 *
 *   var rain = RadioRainSound.create();
 *   rain.unlock();                        // inside a user gesture (Safari)
 *   rain.setActive(true);                 // fade in
 *   rain.setActive(false, { tail: 25 });  // fade out over 25 s, then suspend
 *   rain.setIntensitySource(fn);          // fn() -> 0..1 or null for a slow drift
 *   rain.thunder();
 *
 * createGraph(context, destination) builds the same mix on any BaseAudioContext,
 * including an OfflineAudioContext for rendering previews.
 */
(function () {
  'use strict';

  var LEVEL = 0.4;
  var FADE_IN = 1.8;
  var FADE_OUT = 1.2;
  var INTENSITY_POLL_MS = 2000;

  function create() {
    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;

    var context = null;
    var graph = null;
    var active = false;
    var suspendTimer = 0;
    var pollTimer = 0;
    var intensitySource = null;

    document.addEventListener('visibilitychange', function () {
      // iOS interrupts the context while locked; pick it back up when we return.
      if (!document.hidden && active && context && context.state !== 'running') {
        context.resume().catch(function () {});
      }
    });

    function ensureContext() {
      if (context) return context;
      try {
        if (navigator.audioSession) navigator.audioSession.type = 'playback';
      } catch (error) {
        // Older Safari: the ringer switch may mute Web Audio; the music is unaffected.
      }
      context = new AudioContextClass({ latencyHint: 'playback' });
      graph = createGraph(context, context.destination);
      graph.setIntensity(currentIntensity(), 0);
      return context;
    }

    function unlock() {
      var ctx = ensureContext();
      if (ctx.state !== 'running') ctx.resume().catch(function () {});
      if (!active) scheduleSuspend(1);
    }

    function setActive(value, options) {
      value = Boolean(value);
      if (value === active) return;
      active = value;
      clearTimeout(suspendTimer);

      if (active) {
        var ctx = ensureContext();
        if (ctx.state !== 'running') ctx.resume().catch(function () {});
        graph.setIntensity(currentIntensity(), 0);
        graph.fadeTo(LEVEL, FADE_IN);
        startPolling();
        return;
      }

      stopPolling();
      if (!graph) return;
      var tail = (options && options.tail) || FADE_OUT;
      graph.fadeTo(0, tail);
      scheduleSuspend(tail + 0.5);
    }

    function scheduleSuspend(seconds) {
      clearTimeout(suspendTimer);
      suspendTimer = setTimeout(function () {
        if (!active && context && context.state === 'running') context.suspend().catch(function () {});
      }, seconds * 1000);
    }

    function setIntensitySource(source) {
      intensitySource = source;
    }

    function currentIntensity() {
      var value = intensitySource ? intensitySource() : null;
      if (typeof value === 'number' && isFinite(value)) return clamp(value, 0, 1);
      var minutes = Date.now() / 60000;
      return clamp(0.55 + 0.2 * Math.sin(minutes / 1.6) + 0.1 * Math.sin(minutes / 0.7 + 1.3), 0.2, 0.95);
    }

    function startPolling() {
      stopPolling();
      pollTimer = setInterval(function () {
        if (graph) graph.setIntensity(currentIntensity(), INTENSITY_POLL_MS / 1000);
      }, INTENSITY_POLL_MS);
    }

    function stopPolling() {
      clearInterval(pollTimer);
      pollTimer = 0;
    }

    function thunder() {
      if (!active || !graph) return;
      graph.thunder(1.8 + Math.random() * 4.5);
    }

    return {
      unlock: unlock,
      setActive: setActive,
      setIntensitySource: setIntensitySource,
      thunder: thunder,
    };
  }

  // Graph ---------------------------------------------------------------------

  function createGraph(ctx, destination) {
    var master = ctx.createGain();
    master.gain.value = 0;
    master.connect(destination);

    var washHighpass = filter(ctx, 'highpass', 420, 0.5);
    var washLowpass = filter(ctx, 'lowpass', 6000, 0.4);
    var washGain = ctx.createGain();
    loop(ctx, pinkNoise(ctx, 7.3)).connect(washHighpass);
    washHighpass.connect(washLowpass);
    washLowpass.connect(washGain);
    washGain.connect(master);

    var bodyLowpass = filter(ctx, 'lowpass', 280, 0.5);
    var bodyGain = ctx.createGain();
    loop(ctx, brownNoise(ctx, 11.1)).connect(bodyLowpass);
    bodyLowpass.connect(bodyGain);
    bodyGain.connect(master);

    var lightGain = ctx.createGain();
    loop(ctx, patter(ctx, 9.7, 11, false)).connect(lightGain);
    lightGain.connect(master);

    var heavyGain = ctx.createGain();
    loop(ctx, patter(ctx, 13.3, 34, true)).connect(heavyGain);
    heavyGain.connect(master);

    var thunderBuffer = null;

    function setIntensity(amount, seconds) {
      var x = clamp(amount, 0, 1);
      glide(ctx, washGain.gain, 0.34 + 0.4 * x, seconds);
      glide(ctx, washLowpass.frequency, 4200 + 3600 * x, seconds);
      glide(ctx, bodyGain.gain, 0.22 + 0.38 * x, seconds);
      glide(ctx, lightGain.gain, 0.3, seconds);
      glide(ctx, heavyGain.gain, 0.04 + 0.34 * x * x, seconds);
    }

    function fadeTo(level, seconds) {
      var now = ctx.currentTime;
      master.gain.cancelScheduledValues(now);
      master.gain.setValueAtTime(master.gain.value, now);
      master.gain.linearRampToValueAtTime(level, now + seconds);
    }

    function thunder(delay) {
      if (!thunderBuffer) thunderBuffer = rumble(ctx, 8);
      var source = ctx.createBufferSource();
      source.buffer = thunderBuffer;
      source.playbackRate.value = 0.8 + Math.random() * 0.3;
      var lowpass = filter(ctx, 'lowpass', 160 + Math.random() * 120, 0.7);
      var gain = ctx.createGain();
      gain.gain.value = 1.1 + Math.random() * 0.5;
      source.connect(lowpass);
      lowpass.connect(gain);
      gain.connect(master);
      source.start(ctx.currentTime + delay);
      source.onended = function () { gain.disconnect(); };
    }

    return { setIntensity: setIntensity, fadeTo: fadeTo, thunder: thunder, master: master };
  }

  function filter(ctx, type, frequency, q) {
    var node = ctx.createBiquadFilter();
    node.type = type;
    node.frequency.value = frequency;
    node.Q.value = q;
    return node;
  }

  function loop(ctx, buffer) {
    var source = ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    source.start(0, Math.random() * buffer.duration);
    return source;
  }

  function glide(ctx, param, value, seconds) {
    var now = ctx.currentTime;
    if (!seconds) {
      param.cancelScheduledValues(now);
      param.setValueAtTime(value, now);
      return;
    }
    param.setTargetAtTime(value, now, seconds / 3);
  }

  // Synthesis -----------------------------------------------------------------

  function pinkNoise(ctx, seconds) {
    return seamless(ctx, seconds, 2, function (channel, length) {
      var b0 = 0;
      var b1 = 0;
      var b2 = 0;
      for (var i = 0; i < length; i += 1) {
        var white = Math.random() * 2 - 1;
        b0 = 0.99765 * b0 + white * 0.099046;
        b1 = 0.963 * b1 + white * 0.2965164;
        b2 = 0.57 * b2 + white * 1.0526913;
        channel[i] = b0 + b1 + b2 + white * 0.1848;
      }
      normalizeRms(channel, 0.2);
    });
  }

  function brownNoise(ctx, seconds) {
    return seamless(ctx, seconds, 1, function (channel, length) {
      var last = 0;
      for (var i = 0; i < length; i += 1) {
        last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
        channel[i] = last;
      }
      normalizeRms(channel, 0.25);
    });
  }

  // Fill `seconds` plus a short overlap, then crossfade the overlap into the start so
  // the loop point is inaudible.
  function seamless(ctx, seconds, channels, fill) {
    var rate = ctx.sampleRate;
    var length = Math.round(seconds * rate);
    var overlap = Math.round(0.08 * rate);
    var buffer = ctx.createBuffer(channels, length, rate);
    for (var c = 0; c < channels; c += 1) {
      var scratch = new Float32Array(length + overlap);
      fill(scratch, scratch.length);
      for (var i = 0; i < overlap; i += 1) {
        var t = i / overlap;
        scratch[i] = scratch[i] * Math.sqrt(t) + scratch[length + i] * Math.sqrt(1 - t);
      }
      buffer.getChannelData(c).set(scratch.subarray(0, length));
    }
    return buffer;
  }

  // Drops on glass: short resonant ticks, plus heavier drips when `heavy`.
  // Drops that run past the end wrap to the start, so the loop is seamless.
  function patter(ctx, seconds, perSecond, heavy) {
    var rate = ctx.sampleRate;
    var length = Math.round(seconds * rate);
    var buffer = ctx.createBuffer(2, length, rate);
    var left = buffer.getChannelData(0);
    var right = buffer.getChannelData(1);
    var count = Math.round(seconds * perSecond);

    for (var d = 0; d < count; d += 1) {
      var drip = heavy && Math.random() < 0.14;
      var start = Math.floor(Math.random() * length);
      var pan = Math.random() * 2 - 1;
      var gainL = Math.cos((pan + 1) * Math.PI / 4);
      var gainR = Math.sin((pan + 1) * Math.PI / 4);
      var amplitude = drip ? 0.5 + Math.random() * 0.5 : 0.08 + Math.pow(Math.random(), 2) * 0.6;
      var frequency = drip ? 500 + Math.random() * 900 : 1800 + Math.random() * 3800;
      var decay = (drip ? 0.025 + Math.random() * 0.035 : 0.003 + Math.random() * 0.012) * rate;
      var glideDown = drip ? 0.35 : 0.08;
      var span = Math.round(decay * 6);
      var attack = 0.0006 * rate;
      var phase = Math.random() * Math.PI * 2;
      var noise = 0;

      for (var n = 0; n < span; n += 1) {
        var envelope = Math.exp(-n / decay) * Math.min(1, n / attack);
        var f = frequency * (1 - glideDown * (n / span));
        phase += (2 * Math.PI * f) / rate;
        noise = noise * 0.55 + (Math.random() * 2 - 1) * 0.45;
        var sample = (Math.sin(phase) * 0.65 + noise * 0.35) * envelope * amplitude;
        var index = (start + n) % length;
        left[index] += sample * gainL;
        right[index] += sample * gainR;
      }
    }

    var peak = 0;
    for (var i = 0; i < length; i += 1) {
      peak = Math.max(peak, Math.abs(left[i]), Math.abs(right[i]));
    }
    var scale = peak > 0 ? 0.8 / peak : 1;
    for (var j = 0; j < length; j += 1) {
      left[j] *= scale;
      right[j] *= scale;
    }
    return buffer;
  }

  // Distant thunder: a slow swell of brown noise with a lumpy, rolling decay.
  function rumble(ctx, seconds) {
    var rate = ctx.sampleRate;
    var length = Math.round(seconds * rate);
    var buffer = ctx.createBuffer(1, length, rate);
    var data = buffer.getChannelData(0);
    var last = 0;
    var roll = 0;
    var rollTarget = 1;
    for (var i = 0; i < length; i += 1) {
      var t = i / rate;
      last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
      if (i % Math.round(rate * 0.12) === 0) rollTarget = 0.35 + Math.random() * 0.65;
      roll += (rollTarget - roll) * 0.0004;
      var swell = Math.min(1, t / 0.9);
      data[i] = last * swell * swell * Math.exp(-Math.max(0, t - 0.9) / 1.9) * roll;
    }
    var peak = 0;
    for (var j = 0; j < length; j += 1) peak = Math.max(peak, Math.abs(data[j]));
    for (var k = 0; k < length; k += 1) data[k] *= peak > 0 ? 0.9 / peak : 1;
    return buffer;
  }

  function normalizeRms(channel, target) {
    var sum = 0;
    for (var i = 0; i < channel.length; i += 1) sum += channel[i] * channel[i];
    var rms = Math.sqrt(sum / channel.length);
    if (!rms) return;
    var scale = target / rms;
    for (var j = 0; j < channel.length; j += 1) channel[j] *= scale;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  window.RadioRainSound = { create: create, createGraph: createGraph };
})();
