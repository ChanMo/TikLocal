/*
 * Radio ambience — procedural room sound mixed beside the music.
 *
 * The music keeps its own <audio> element; ambience runs in a separate AudioContext,
 * so music playback (and iOS background audio) never depends on Web Audio.
 * Each profile is a handful of looped buffers synthesised once and cached, so nothing
 * needs a timer to keep going in a background tab, and loops of different lengths
 * never line up audibly:
 *
 *   rain   pink-noise wash, low body, light and heavy drops on glass; thunder after lightning
 *   snow   gusting wind, a faint whistle at the window, a quiet room; a car passing
 *   fire   a breathing low roar, a gas hiss, crackles in bursts with pops and snaps;
 *          a log settling
 *   night  crickets with their own rhythms and places, a distant trill, a leafy breeze
 *
 *   var ambience = RadioAmbience.create();
 *   ambience.unlock();                       // inside a user gesture (Safari)
 *   ambience.setProfile('fire');             // crossfades from the previous profile
 *   ambience.setActive(true);                // fade in
 *   ambience.setActive(false, { tail: 25 }); // fade out over 25 s, then suspend
 *   ambience.setIntensitySource(fn);         // fn() -> 0..1 or null for a slow drift
 *   ambience.event('lightning', seed);       // the scene's rare event, if the profile has a sound for it
 *
 * createProfile(context, name, destination) builds one profile on any BaseAudioContext,
 * including an OfflineAudioContext for rendering previews.
 */
(function () {
  'use strict';

  var LEVEL = 0.4;
  var FADE_IN = 1.8;
  var FADE_OUT = 1.2;
  var PROFILE_FADE = 2.5;
  var INTENSITY_POLL_MS = 2000;

  var PROFILES = {
    rain: rainProfile,
    snow: snowProfile,
    fire: fireProfile,
    night: nightProfile,
  };

  function create() {
    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;

    var context = null;
    var master = null;
    var cache = {};
    var running = {};
    var profileName = null;
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
      master = context.createGain();
      master.gain.value = 0;
      master.connect(context.destination);
      switchProfile(0);
      return context;
    }

    function unlock() {
      var ctx = ensureContext();
      if (ctx.state !== 'running') ctx.resume().catch(function () {});
      if (!active) scheduleSuspend(1);
    }

    function setProfile(name) {
      name = PROFILES[name] ? name : null;
      if (name === profileName) return;
      profileName = name;
      if (context) switchProfile(active ? PROFILE_FADE : 0);
    }

    // Fade the chosen profile in and retire the others; retired sources are stopped
    // once silent, and a profile chosen again before then is simply faded back in.
    function switchProfile(seconds) {
      Object.keys(running).forEach(function (name) {
        if (name !== profileName) retire(name, seconds);
      });
      if (!profileName) return;
      var instance = running[profileName];
      if (!instance) {
        instance = PROFILES[profileName](context, master, cache);
        instance.setIntensity(currentIntensity(), 0);
        running[profileName] = instance;
      }
      clearTimeout(instance.retireTimer);
      instance.fadeTo(1, seconds);
    }

    function retire(name, seconds) {
      var instance = running[name];
      instance.fadeTo(0, seconds);
      clearTimeout(instance.retireTimer);
      instance.retireTimer = setTimeout(function () {
        if (running[name] !== instance || profileName === name) return;
        instance.stop();
        delete running[name];
      }, seconds * 1000 + 200);
    }

    function setActive(value, options) {
      value = Boolean(value);
      if (value === active) return;
      active = value;
      clearTimeout(suspendTimer);

      if (active) {
        var ctx = ensureContext();
        if (ctx.state !== 'running') ctx.resume().catch(function () {});
        eachRunning(function (instance) { instance.setIntensity(currentIntensity(), 0); });
        ramp(ctx, master.gain, LEVEL, FADE_IN);
        startPolling();
        return;
      }

      stopPolling();
      if (!context) return;
      var tail = (options && options.tail) || FADE_OUT;
      ramp(context, master.gain, 0, tail);
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
        var value = currentIntensity();
        eachRunning(function (instance) { instance.setIntensity(value, INTENSITY_POLL_MS / 1000); });
      }, INTENSITY_POLL_MS);
    }

    function stopPolling() {
      clearInterval(pollTimer);
      pollTimer = 0;
    }

    function eachRunning(fn) {
      Object.keys(running).forEach(function (name) { fn(running[name]); });
    }

    function event(type, seed) {
      var instance = profileName && running[profileName];
      if (!active || !instance || !instance.event) return;
      instance.event(type, seed);
    }

    return {
      unlock: unlock,
      setProfile: setProfile,
      setActive: setActive,
      setIntensitySource: setIntensitySource,
      event: event,
    };
  }

  function createProfile(ctx, name, destination) {
    return PROFILES[name](ctx, destination, {});
  }

  // Profiles --------------------------------------------------------------------
  //
  // Each profile owns a bus into `destination` and returns
  // { setIntensity(amount, seconds), fadeTo(level, seconds), stop(), event?(type, seed) }.

  function profileBase(ctx, destination, cache) {
    var bus = ctx.createGain();
    bus.gain.value = 0;
    bus.connect(destination);
    var sources = [];
    return {
      bus: bus,
      buffer: function (key, make) {
        if (!cache[key]) cache[key] = make();
        return cache[key];
      },
      layer: function (buffer, nodes) {
        var source = loop(ctx, buffer);
        sources.push(source);
        var gain = ctx.createGain();
        var last = source;
        (nodes || []).concat([gain]).forEach(function (node) {
          last.connect(node);
          last = node;
        });
        gain.connect(bus);
        return gain;
      },
      // Play a one-shot buffer through `nodes` into the bus, `delay` seconds from now.
      oneShot: function (buffer, nodes, delay, rate) {
        var source = ctx.createBufferSource();
        source.buffer = buffer;
        source.playbackRate.value = rate || 1;
        var last = source;
        nodes.forEach(function (node) {
          last.connect(node);
          last = node;
        });
        last.connect(bus);
        source.start(ctx.currentTime + (delay || 0));
        source.onended = function () { last.disconnect(); };
        return source;
      },
      instance: function (setIntensity, extra) {
        var instance = {
          setIntensity: setIntensity,
          fadeTo: function (level, seconds) { ramp(ctx, bus.gain, level, seconds); },
          stop: function () {
            sources.forEach(function (source) {
              try { source.stop(); } catch (error) { /* already stopped */ }
            });
            bus.disconnect();
          },
        };
        Object.keys(extra || {}).forEach(function (key) { instance[key] = extra[key]; });
        return instance;
      },
    };
  }

  function rainProfile(ctx, destination, cache) {
    var base = profileBase(ctx, destination, cache);
    var washLowpass = filter(ctx, 'lowpass', 6000, 0.4);
    var wash = base.layer(base.buffer('rain-wash', function () { return pinkNoise(ctx, 7.3); }),
      [filter(ctx, 'highpass', 420, 0.5), washLowpass]);
    var body = base.layer(base.buffer('rain-body', function () { return brownNoise(ctx, 11.1); }),
      [filter(ctx, 'lowpass', 280, 0.5)]);
    var light = base.layer(base.buffer('rain-light', function () { return patter(ctx, 9.7, 11, false); }));
    var heavy = base.layer(base.buffer('rain-heavy', function () { return patter(ctx, 13.3, 34, true); }));

    function setIntensity(amount, seconds) {
      var x = clamp(amount, 0, 1);
      glide(ctx, wash.gain, 0.34 + 0.4 * x, seconds);
      glide(ctx, washLowpass.frequency, 4200 + 3600 * x, seconds);
      glide(ctx, body.gain, 0.22 + 0.38 * x, seconds);
      glide(ctx, light.gain, 0.3, seconds);
      glide(ctx, heavy.gain, 0.04 + 0.34 * x * x, seconds);
    }

    // Thunder rolls in a few seconds after the flash.
    function event(type) {
      if (type !== 'lightning') return;
      var buffer = base.buffer('rain-thunder', function () { return rumble(ctx, 8); });
      var gain = ctx.createGain();
      gain.gain.value = 1.1 + Math.random() * 0.5;
      base.oneShot(buffer, [filter(ctx, 'lowpass', 160 + Math.random() * 120, 0.7), gain],
        1.8 + Math.random() * 4.5, 0.8 + Math.random() * 0.3);
    }

    return base.instance(setIntensity, { event: event });
  }

  function snowProfile(ctx, destination, cache) {
    var base = profileBase(ctx, destination, cache);
    var windBand = filter(ctx, 'bandpass', 380, 0.6);
    var wind = base.layer(base.buffer('snow-wind', function () {
      return gusty(pinkNoise(ctx, 23.3), [2, 5], 0.3);
    }), [windBand]);
    var whistle = base.layer(base.buffer('snow-whistle', function () {
      return gusty(pinkNoise(ctx, 17.9), [3, 7], 0.1);
    }), [filter(ctx, 'bandpass', 1050, 9)]);
    var room = base.layer(base.buffer('snow-room', function () { return brownNoise(ctx, 11.1); }),
      [filter(ctx, 'lowpass', 140, 0.5)]);

    function setIntensity(amount, seconds) {
      var x = clamp(amount, 0, 1);
      glide(ctx, wind.gain, 0.9 + 0.8 * x, seconds);
      glide(ctx, windBand.frequency, 300 + 260 * x, seconds);
      glide(ctx, whistle.gain, 0.5 + 1.2 * x * x, seconds);
      glide(ctx, room.gain, 0.25, seconds);
    }

    // A car passing on the snowy street: muffled tyre hiss that swells and fades while
    // it crosses the stereo field, the same way the headlights cross the screen.
    function event(type, seed) {
      if (type !== 'car') return;
      var buffer = base.buffer('snow-car', function () { return tyreHiss(ctx, 8); });
      var lowpass = filter(ctx, 'lowpass', 700, 0.7);
      var gain = ctx.createGain();
      gain.gain.value = 0.9;
      var nodes = [lowpass, gain];
      var now = ctx.currentTime;
      lowpass.frequency.setValueAtTime(450, now);
      lowpass.frequency.linearRampToValueAtTime(1100, now + 3.6);
      lowpass.frequency.linearRampToValueAtTime(420, now + 8);
      if (ctx.createStereoPanner) {
        var panner = ctx.createStereoPanner();
        var from = seed < 0.5 ? -0.85 : 0.85;
        panner.pan.setValueAtTime(from, now);
        panner.pan.linearRampToValueAtTime(-from, now + 7.5);
        nodes.push(panner);
      }
      base.oneShot(buffer, nodes, 0, 1);
    }

    return base.instance(setIntensity, { event: event });
  }

  function fireProfile(ctx, destination, cache) {
    var base = profileBase(ctx, destination, cache);
    var roar = base.layer(base.buffer('fire-roar', function () {
      return gusty(brownNoise(ctx, 13.7), [9, 23], 0.45);
    }), [filter(ctx, 'lowpass', 520, 0.6)]);
    var hiss = base.layer(base.buffer('fire-hiss', function () { return pinkNoise(ctx, 9.1); }),
      [filter(ctx, 'bandpass', 2800, 0.6)]);
    var crackle = base.layer(base.buffer('fire-crackle', function () { return crackles(ctx, 17.3, 1.4, 0.25); }));
    var pops = base.layer(base.buffer('fire-pops', function () { return crackles(ctx, 11.9, 0.5, 0.7); }));

    function setIntensity(amount, seconds) {
      var x = clamp(amount, 0, 1);
      glide(ctx, roar.gain, 0.5 + 0.4 * x, seconds);
      glide(ctx, hiss.gain, 0.05 + 0.05 * x, seconds);
      glide(ctx, crackle.gain, 0.35 + 0.25 * x, seconds);
      glide(ctx, pops.gain, 0.15 + 0.35 * x, seconds);
    }

    // A log settles: a low wooden knock, then a flurry of crackles as sparks fly up.
    function event(type) {
      if (type !== 'burst') return;
      var buffer = base.buffer('fire-settle', function () { return logSettle(ctx, 2.5); });
      var gain = ctx.createGain();
      gain.gain.value = 1.5;
      base.oneShot(buffer, [gain], 0.05, 0.9 + Math.random() * 0.2);
    }

    return base.instance(setIntensity, { event: event });
  }

  function nightProfile(ctx, destination, cache) {
    var base = profileBase(ctx, destination, cache);
    var crickets = base.layer(base.buffer('night-crickets', function () { return cricketChorus(ctx, 13.7, 5); }));
    var trill = base.layer(base.buffer('night-trill', function () { return distantTrill(ctx, 9.1); }),
      [filter(ctx, 'bandpass', 6200, 2)]);
    var breeze = base.layer(base.buffer('night-breeze', function () {
      return gusty(pinkNoise(ctx, 19.3), [2, 5], 0.25);
    }), [filter(ctx, 'lowpass', 900, 0.5)]);

    function setIntensity(amount, seconds) {
      var x = clamp(amount, 0, 1);
      glide(ctx, crickets.gain, 0.3 + 0.25 * x, seconds);
      glide(ctx, trill.gain, 0.2 + 0.3 * x, seconds);
      glide(ctx, breeze.gain, 0.3, seconds);
    }

    return base.instance(setIntensity);
  }

  // Nodes -----------------------------------------------------------------------

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

  function ramp(ctx, param, value, seconds) {
    var now = ctx.currentTime;
    param.cancelScheduledValues(now);
    param.setValueAtTime(param.value, now);
    if (seconds) param.linearRampToValueAtTime(value, now + seconds);
    else param.setValueAtTime(value, now);
  }

  // Synthesis -------------------------------------------------------------------

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

  // Shape a looped buffer with a slow envelope that is periodic in the buffer's length,
  // so gusts come and go without breaking the loop. `cycles` sets how many rises fit.
  function gusty(buffer, cycles, floor) {
    var length = buffer.length;
    var phase = Math.random() * Math.PI * 2;
    for (var c = 0; c < buffer.numberOfChannels; c += 1) {
      var data = buffer.getChannelData(c);
      for (var i = 0; i < length; i += 1) {
        var t = (i / length) * Math.PI * 2;
        var swell = 0.5 + 0.3 * Math.sin(t * cycles[0] + phase) + 0.2 * Math.sin(t * cycles[1] + phase * 1.7);
        data[i] *= floor + (1 - floor) * swell * swell;
      }
    }
    return buffer;
  }

  function stereoBuffer(ctx, seconds) {
    var length = Math.round(seconds * ctx.sampleRate);
    var buffer = ctx.createBuffer(2, length, ctx.sampleRate);
    return {
      buffer: buffer,
      length: length,
      rate: ctx.sampleRate,
      left: buffer.getChannelData(0),
      right: buffer.getChannelData(1),
      // Add a sample at `index` (wrapping, so events past the end loop to the start).
      add: function (index, value, pan) {
        var i = index % length;
        this.left[i] += value * Math.cos((pan + 1) * Math.PI / 4);
        this.right[i] += value * Math.sin((pan + 1) * Math.PI / 4);
      },
      normalize: function (peakTarget) {
        var peak = 0;
        for (var i = 0; i < length; i += 1) peak = Math.max(peak, Math.abs(this.left[i]), Math.abs(this.right[i]));
        var scale = peak > 0 ? peakTarget / peak : 1;
        for (var j = 0; j < length; j += 1) {
          this.left[j] *= scale;
          this.right[j] *= scale;
        }
        return buffer;
      },
    };
  }

  // Drops on glass: short resonant ticks, plus heavier drips when `heavy`.
  function patter(ctx, seconds, perSecond, heavy) {
    var out = stereoBuffer(ctx, seconds);
    var rate = out.rate;
    var count = Math.round(seconds * perSecond);

    for (var d = 0; d < count; d += 1) {
      var drip = heavy && Math.random() < 0.14;
      var start = Math.floor(Math.random() * out.length);
      var pan = Math.random() * 2 - 1;
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
        phase += (2 * Math.PI * frequency * (1 - glideDown * (n / span))) / rate;
        noise = noise * 0.55 + (Math.random() * 2 - 1) * 0.45;
        out.add(start + n, (Math.sin(phase) * 0.65 + noise * 0.35) * envelope * amplitude, pan);
      }
    }
    return out.normalize(0.8);
  }

  // Wood fire: bursts of tiny bright clicks that speed up and fade, plus pops (a click
  // over a short low thump) and, rarely, a sharp snap.
  function crackles(ctx, seconds, burstsPerSecond, popsPerSecond) {
    var out = stereoBuffer(ctx, seconds);
    var rate = out.rate;

    function click(at, amplitude, duration, pan) {
      var span = Math.max(4, Math.round(duration * rate));
      var previous = 0;
      for (var n = 0; n < span; n += 1) {
        var white = Math.random() * 2 - 1;
        var bright = white - previous * 0.85;
        previous = white;
        out.add(at + n, bright * Math.exp(-n / (span * 0.3)) * amplitude, pan);
      }
    }

    var bursts = Math.round(seconds * burstsPerSecond);
    for (var b = 0; b < bursts; b += 1) {
      var at = Math.floor(Math.random() * out.length);
      var pan = (Math.random() * 2 - 1) * 0.7;
      var clicks = 3 + Math.floor(Math.random() * 12);
      var gap = 0.03 + Math.random() * 0.05;
      var level = 0.2 + Math.random() * 0.5;
      for (var c = 0; c < clicks; c += 1) {
        click(at, level * (0.4 + Math.random() * 0.6) * (1 - c / clicks * 0.6), 0.0006 + Math.random() * 0.002,
          pan + (Math.random() - 0.5) * 0.2);
        at += Math.round(gap * rate * (0.4 + Math.random()));
        gap *= 0.88;
      }
    }

    var pops = Math.round(seconds * popsPerSecond);
    for (var p = 0; p < pops; p += 1) {
      var start = Math.floor(Math.random() * out.length);
      var popPan = (Math.random() * 2 - 1) * 0.6;
      var snap = Math.random() < 0.12;
      click(start, snap ? 1.0 : 0.55 + Math.random() * 0.3, snap ? 0.004 : 0.0025, popPan);
      var frequency = 80 + Math.random() * 90;
      var decay = (0.012 + Math.random() * 0.02) * rate;
      for (var n = 0; n < decay * 5; n += 1) {
        out.add(start + n, Math.sin((2 * Math.PI * frequency * n) / rate) * Math.exp(-n / decay) * 0.5, popPan);
      }
    }
    return out.normalize(0.85);
  }

  // A few crickets, each with its own pitch, place, loudness and chirp rhythm.
  function cricketChorus(ctx, seconds, count) {
    var out = stereoBuffer(ctx, seconds);
    var rate = out.rate;
    for (var k = 0; k < count; k += 1) {
      var frequency = 4300 + Math.random() * 900;
      var pan = (Math.random() * 2 - 1) * 0.85;
      var loudness = 0.25 + Math.random() * 0.75;
      var period = 0.55 + Math.random() * 0.55;
      var pulses = 3 + Math.floor(Math.random() * 2);
      var pulseLength = 0.012 * rate;
      var spacing = (0.026 + Math.random() * 0.01) * rate;
      for (var t = Math.random() * period; t < seconds; t += period * (0.95 + Math.random() * 0.1)) {
        var start = Math.round(t * rate);
        for (var p = 0; p < pulses; p += 1) {
          var at = start + Math.round(p * spacing);
          for (var n = 0; n < pulseLength; n += 1) {
            var envelope = Math.sin((Math.PI * n) / pulseLength);
            var tone = Math.sin((2 * Math.PI * frequency * n) / rate) + 0.3 * Math.sin((4 * Math.PI * frequency * n) / rate);
            out.add(at + n, tone * envelope * envelope * loudness, pan);
          }
        }
      }
    }
    return out.normalize(0.7);
  }

  // A soft, continuous trill far away: a buzzing tone whose loudness drifts.
  function distantTrill(ctx, seconds) {
    var out = stereoBuffer(ctx, seconds);
    var rate = out.rate;
    var frequency = 6200 + Math.random() * 400;
    for (var i = 0; i < out.length; i += 1) {
      var t = i / rate;
      var buzz = 0.5 + 0.5 * Math.sin(2 * Math.PI * 42 * t);
      var drift = 0.55 + 0.45 * Math.sin((2 * Math.PI * 3 * i) / out.length);
      var value = Math.sin(2 * Math.PI * frequency * t) * buzz * buzz * drift;
      out.left[i] += value * 0.8;
      out.right[i] += value * 0.6;
    }
    return out.normalize(0.5);
  }

  // Tyres on snow: brown noise under a slow swell that peaks as the car passes.
  function tyreHiss(ctx, seconds) {
    var rate = ctx.sampleRate;
    var length = Math.round(seconds * rate);
    var buffer = ctx.createBuffer(1, length, rate);
    var data = buffer.getChannelData(0);
    var last = 0;
    for (var i = 0; i < length; i += 1) {
      var t = i / length;
      last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
      var swell = Math.pow(Math.sin(Math.PI * Math.min(1, t * 1.05)), 3);
      data[i] = (last * 3.5 + (Math.random() * 2 - 1) * 0.04) * swell;
    }
    var peak = 0;
    for (var j = 0; j < length; j += 1) peak = Math.max(peak, Math.abs(data[j]));
    for (var k = 0; k < length; k += 1) data[k] *= peak > 0 ? 0.7 / peak : 1;
    return buffer;
  }

  // A log settling: a low knock with a short woody body, then a dense flurry of crackles.
  function logSettle(ctx, seconds) {
    var out = stereoBuffer(ctx, seconds);
    var rate = out.rate;
    var knock = 0.02 * rate;
    for (var n = 0; n < knock * 6; n += 1) {
      var body = Math.sin((2 * Math.PI * 72 * n) / rate) + 0.5 * Math.sin((2 * Math.PI * 180 * n) / rate);
      out.add(n, body * Math.exp(-n / knock) * 0.9 + (Math.random() * 2 - 1) * Math.exp(-n / (0.004 * rate)) * 0.5, 0);
    }
    var at = Math.round(0.08 * rate);
    var gap = 0.012;
    for (var c = 0; c < 45; c += 1) {
      var span = Math.round((0.0005 + Math.random() * 0.002) * rate);
      var pan = (Math.random() * 2 - 1) * 0.6;
      var level = (0.3 + Math.random() * 0.7) * Math.exp(-c / 18);
      var previous = 0;
      for (var k = 0; k < span; k += 1) {
        var white = Math.random() * 2 - 1;
        out.add(at + k, (white - previous * 0.85) * Math.exp(-k / (span * 0.3)) * level, pan);
        previous = white;
      }
      at += Math.round(gap * rate * (0.3 + Math.random() * 1.4));
      gap *= 1.06;
    }
    return out.normalize(0.9);
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

  window.RadioAmbience = { create: create, createProfile: createProfile };
})();
