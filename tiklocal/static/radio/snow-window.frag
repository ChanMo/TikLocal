// Snow night — TikLocal Radio ambience.
//
// Layers, back to front:
//   street   sky with a warm city glow, soft out-of-focus houses whose lit windows take
//            their tint from the cover art, snowy ground, and a street lamp
//   snow     five parallax layers from pin-point far flakes to large blurred ones near
//            the glass; wind is integrated over time so gusts never jump, and flakes
//            passing through the lamp's cone catch its light
//   sill     snow piled on the window sill, with glints
//   glass    frost creeping in from the corners, flakes that land on the pane and melt,
//            warm room light, vignette and grain
//
// Houses have chimneys with smoke leaning in the wind. The room's rare event (uEvent,
// seconds since it began) is a car passing along the street at night: only its lights
// show, and its beams catch the falling snow.
//
// uDark blends an overcast snowy day (0) into night (1); uIntensity sets how hard it
// snows; uEnergy (0.5 when unknown) lifts the lamp and the windows with the music.

#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec2 uRes;
uniform float uTime;
uniform float uDark;
uniform float uIntensity;
uniform float uEnergy;
uniform float uEvent;
uniform float uEventSeed;
uniform sampler2D uBlur;

const vec3 LAMP_WARM = vec3(1.0, 0.72, 0.42);
const vec3 HEADLIGHT = vec3(1.0, 0.92, 0.78);
const float CAR_SECONDS = 8.0;
const float STREET = 0.165;

float hash21(vec2 p) {
  p = fract(p * vec2(233.34, 851.73));
  p += dot(p, p + 23.45);
  return fract(p.x * p.y);
}

vec2 hash22(vec2 p) {
  float n = hash21(p);
  return vec2(n, hash21(p + n));
}

float valueNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 4; i++) {
    value += amplitude * valueNoise(p);
    p = p * 2.03 + 17.1;
    amplitude *= 0.5;
  }
  return value;
}

float aspect() {
  return uRes.x / uRes.y;
}

// Normalised colour of the cover near uv, used to tint lit windows.
vec3 coverTint(vec2 uv) {
  vec3 c = texture2D(uBlur, uv).rgb;
  return c / max(max(c.r, c.g), max(c.b, 0.05));
}

// Horizontal wind offset: the integral of a gusty wind speed, so it is continuous.
float windDrift(float t) {
  return -2.4 * cos(t * 0.05) - 0.62 * cos(t * 0.13 + 1.7) + 0.05 * t;
}

vec2 lampHead() {
  return vec2(aspect() * 0.8, 0.72);
}

// How much lamp light reaches a point in the air (cone below the head plus halo).
float lampLight(vec2 p) {
  vec2 d = p - lampHead();
  float below = smoothstep(0.02, -0.06, d.y);
  float spread = abs(d.x) / max(-d.y, 0.001);
  float cone = smoothstep(0.62, 0.25, spread) * below / (1.0 + dot(d, d) * 5.0);
  float halo = exp(-length(d) * 10.0) * 1.2 + exp(-length(d) * 3.0) * 0.18;
  return (cone + halo) * uDark * (0.8 + 0.4 * uEnergy);
}

// A soft, out-of-focus row of houses: pitched roofs, gaps, roof snow and glowing windows.
// The passing car: heading (+1 right, -1 left), x of its front, and a fade in and out.
float carHeading() {
  return uEventSeed < 0.5 ? 1.0 : -1.0;
}

float carFront() {
  float a = aspect();
  float x = mix(-0.25, a + 0.25, clamp(uEvent / CAR_SECONDS, 0.0, 1.0));
  return carHeading() > 0.0 ? x : a - x;
}

float carFade() {
  return step(0.0, uEvent) * smoothstep(0.0, 0.8, uEvent) * smoothstep(CAR_SECONDS, CAR_SECONDS - 0.8, uEvent) * uDark;
}

// Headlight reaching a point: a beam widening ahead of the car plus a glow at the lamp.
float carLight(vec2 p) {
  if (uEvent < 0.0) return 0.0;
  vec2 d = p - vec2(carFront(), STREET);
  float ahead = d.x * carHeading();
  float beam = step(0.0, ahead) * smoothstep(0.55, 0.0, ahead) * smoothstep(ahead * 0.3 + 0.012, 0.0, abs(d.y + ahead * 0.03));
  return (beam * 0.9 + exp(-length(d) * 28.0) * 0.8) * carFade();
}

vec3 houses(vec3 col, vec2 uv, vec2 p, float ground, float scale, float seed, float haze) {
  float width = 0.21 * scale;
  float cell = floor(p.x / width + seed);
  float h = hash21(vec2(cell, 3.7 + seed));
  if (h < 0.3) return col;

  float center = (cell - seed + 0.5) * width + (fract(h * 5.3) - 0.5) * width * 0.35;
  float half_ = width * (0.22 + 0.2 * fract(h * 7.1));
  float eaves = ground + (0.05 + 0.1 * fract(h * 13.3)) * scale;
  float peak = eaves + half_ * (0.35 + 0.45 * fract(h * 3.9));
  float blur = 0.012 * scale;

  float dx = abs(p.x - center);
  float walls = smoothstep(half_ + blur, half_ - blur, dx) * smoothstep(eaves + blur, eaves - blur, uv.y);
  float roofLine = mix(peak, eaves, dx / (half_ + 0.02));
  float roof = smoothstep(half_ + 0.02 + blur, half_ + 0.02 - blur, dx) * smoothstep(roofLine + blur, roofLine - blur, uv.y)
    * step(eaves - blur, uv.y);
  float house = max(walls, roof) * step(ground - 0.02, uv.y);

  vec3 nightHouse = vec3(0.025, 0.028, 0.045);
  vec3 dayHouse = vec3(0.66, 0.68, 0.72);
  col = mix(col, mix(dayHouse, nightHouse, uDark), house * mix(0.75, 0.92, uDark) * (1.0 - haze));

  float snowRoof = roof * smoothstep(roofLine - 0.03, roofLine - 0.006, uv.y);
  col = mix(col, mix(vec3(0.95, 0.96, 0.98), vec3(0.3, 0.32, 0.4), uDark), snowRoof * 0.75);

  // Near houses may have a chimney on the left slope, its smoke leaning with the wind.
  if (haze < 0.01 && fract(h * 21.7) > 0.4) {
    float chimneyX = center - half_ * 0.45;
    float roofAt = mix(peak, eaves, abs(chimneyX - center) / (half_ + 0.02));
    float top = roofAt + 0.028;
    float chimney = smoothstep(0.012, 0.008, abs(p.x - chimneyX)) * step(uv.y, top) * step(roofAt - 0.02, uv.y);
    col = mix(col, mix(dayHouse, nightHouse, uDark), chimney * mix(0.75, 0.92, uDark));

    float rise = uv.y - top;
    if (rise > 0.0 && rise < 0.3) {
      float lean = rise * (0.32 + 0.1 * sin(uTime * 0.05 + h * 9.0));
      float spread = 0.012 + rise * 0.22;
      float across = (p.x - chimneyX - lean) / spread;
      // Soft puffs: a wide body textured by billows that rise and drift apart.
      vec2 puff = vec2(across * 1.6, rise * 10.0 - uTime * 0.4) + h * 10.0;
      float billow = 0.45 + 0.55 * fbm(puff);
      float smoke = smoothstep(1.0, 0.0, abs(across)) * billow
        * smoothstep(0.3, 0.03, rise) * smoothstep(0.0, 0.02, rise);
      col = mix(col, mix(vec3(0.76, 0.77, 0.8), vec3(0.2, 0.21, 0.26), uDark), smoke * mix(0.45, 0.55, uDark));
    }
  }

  // Out-of-focus windows: round glows on a loose grid, lit at random.
  vec2 grid = vec2((p.x - center) / (0.05 * scale), (uv.y - ground - 0.012) / (0.045 * scale));
  vec2 windowId = floor(grid) + cell * 31.0;
  vec2 pane = fract(grid) - 0.5;
  float inside = step(abs(p.x - center) + 0.02, half_) * step(uv.y, eaves - 0.012) * step(ground + 0.015, uv.y);
  float lit = step(mix(0.8, 0.55, uDark), hash21(windowId));
  float glow = exp(-dot(pane, pane) * 14.0);
  float flicker = 0.88 + 0.12 * sin(uTime * (0.2 + hash21(windowId + 2.0)) + windowId.x);
  vec3 tint = mix(LAMP_WARM, coverTint(vec2(fract(cell * 0.37), 0.5)), 0.35);
  tint = mix(tint, vec3(0.55, 0.7, 1.0), step(0.93, hash21(windowId + 9.0)));
  col += tint * glow * inside * lit * walls * flicker * (0.75 + 0.5 * uEnergy) * mix(0.1, 0.75, uDark) * (1.0 - haze * 0.6);
  return col;
}

vec3 street(vec2 uv, vec2 p) {
  float ground = 0.2;
  vec3 nightSky = mix(vec3(0.11, 0.08, 0.1), vec3(0.018, 0.024, 0.05), smoothstep(0.15, 0.95, uv.y));
  vec3 daySky = mix(vec3(0.87, 0.88, 0.89), vec3(0.74, 0.77, 0.82), smoothstep(0.15, 0.95, uv.y));
  vec3 sky = mix(daySky, nightSky, uDark);
  vec3 col = sky;

  // Far blocks, barely darker than the sky, with a few pin-point lights.
  float farCell = floor(p.x / 0.09);
  float farTop = ground + 0.12 + 0.16 * hash21(vec2(farCell, 8.1));
  float far = smoothstep(farTop + 0.02, farTop - 0.02, uv.y) * step(0.3, hash21(vec2(farCell, 1.3)));
  col = mix(col, mix(vec3(0.78, 0.8, 0.84), vec3(0.05, 0.05, 0.08), uDark), far * 0.55);
  vec2 dotGrid = p * vec2(70.0, 60.0);
  vec2 dotCell = floor(dotGrid);
  float dotShape = smoothstep(0.22, 0.05, length(fract(dotGrid) - 0.5));
  float dots = step(0.985, hash21(dotCell)) * dotShape * far * uDark;
  col += LAMP_WARM * dots * 0.25;

  col = houses(col, uv, p, ground + 0.012, 0.7, 0.43, 0.45);
  col = houses(col, uv, p, ground, 1.0, 0.0, 0.0);

  // Snowy ground, brighter in the lamp's pool of light.
  vec2 head = lampHead();
  float groundMask = smoothstep(ground + 0.006, ground - 0.006, uv.y);
  vec3 snowGround = mix(vec3(0.93, 0.94, 0.96), vec3(0.15, 0.17, 0.23), uDark);
  snowGround *= 0.94 + 0.06 * fbm(p * vec2(3.0, 12.0));
  float pool = exp(-pow(p.x - head.x, 2.0) * 18.0) * smoothstep(0.0, ground, uv.y) * uDark;
  col = mix(col, snowGround + LAMP_WARM * pool * 0.55 * (0.8 + 0.4 * uEnergy), groundMask);

  // The passing car: a low dark body, a headlight in front, a red tail light behind,
  // and the snow on the road lit ahead of it.
  if (uEvent >= 0.0) {
    float fade = carFade();
    float heading = carHeading();
    vec2 c = p - vec2(carFront() - heading * 0.055, STREET + 0.012);
    vec2 body = abs(c) - vec2(0.055, 0.011);
    float bodyMask = smoothstep(0.006, 0.0, length(max(body, 0.0)) + min(max(body.x, body.y), 0.0) - 0.006);
    vec2 cabin = abs(c - vec2(-heading * 0.008, 0.017)) - vec2(0.03, 0.008);
    bodyMask = max(bodyMask, smoothstep(0.006, 0.0, length(max(cabin, 0.0)) - 0.005));
    col = mix(col, vec3(0.01, 0.012, 0.018), bodyMask * fade * 0.85);
    vec2 front = p - vec2(carFront(), STREET + 0.008);
    vec2 back = p - vec2(carFront() - heading * 0.11, STREET + 0.01);
    col += HEADLIGHT * exp(-length(front) * 90.0) * 2.0 * fade;
    col += vec3(1.0, 0.12, 0.08) * exp(-length(back) * 160.0) * 1.2 * fade;
    col += HEADLIGHT * carLight(p) * groundMask * 0.35;
  }

  // Lamp post with a small head, soft like everything beyond the glass.
  vec2 d = p - head;
  float post = smoothstep(0.006, 0.002, abs(d.x)) * step(d.y, 0.0) * step(ground - 0.01, uv.y);
  float cap = smoothstep(0.026, 0.016, length((d - vec2(0.0, 0.01)) * vec2(1.0, 2.2)));
  vec3 iron = mix(vec3(0.5, 0.52, 0.56), vec3(0.012), uDark);
  col = mix(col, iron, max(post, cap) * mix(0.4, 0.92, uDark));
  col += LAMP_WARM * lampLight(p) * 0.22;
  col += LAMP_WARM * exp(-length(d) * 40.0) * 1.4 * uDark;

  // Distance haze.
  col = mix(col, mix(daySky, nightSky * 1.4, uDark), 0.16);
  return col;
}

// One layer of flakes. Returns coverage 0..1.
float snowLayer(vec2 p, float scale, float fall, float drift, float radius, float softness, float seed, float density) {
  vec2 q = p * scale;
  q.y += uTime * fall * scale;
  q.x -= drift * scale;
  vec2 id = floor(q);
  vec2 f = fract(q) - 0.5;
  float h = hash21(id + seed);
  if (h > density) return 0.0;

  vec2 j = hash22(id + seed * 7.1) - 0.5;
  float phase = h * 6.2831;
  vec2 flutter = vec2(sin(uTime * (0.6 + j.x) + phase), cos(uTime * (0.45 + j.y) + phase * 1.3)) * 0.12;
  vec2 center = j * 0.45 + flutter;
  float r = radius * (0.6 + 0.8 * fract(h * 13.7));
  return smoothstep(r, r * softness, length(f - center));
}

vec3 addSnow(vec3 col, vec2 p, float drift, float near) {
  float density = 0.3 + uIntensity * 0.6;
  vec3 ambient = mix(vec3(0.99, 0.995, 1.0), vec3(0.4, 0.44, 0.56), uDark);
  vec3 lit = ambient + LAMP_WARM * lampLight(p) * 2.4 + HEADLIGHT * carLight(p) * 2.2;

  if (near < 0.5) {
    float far = snowLayer(p, 44.0, 0.05, drift * 0.35, 0.1, 0.2, 1.0, density);
    float mid = snowLayer(p, 26.0, 0.08, drift * 0.55, 0.1, 0.25, 2.0, density);
    float close = snowLayer(p, 15.0, 0.12, drift * 0.8, 0.1, 0.3, 3.0, density);
    col = mix(col, lit, far * 0.55);
    col = mix(col, lit, mid * 0.75);
    col = mix(col, lit, close * 0.9);
  } else {
    float nearFlakes = snowLayer(p, 8.0, 0.2, drift * 1.1, 0.1, 0.05, 4.0, density * 0.8);
    float bokeh = snowLayer(p, 4.0, 0.32, drift * 1.5, 0.11, 0.0, 5.0, density * 0.35);
    col = mix(col, lit, nearFlakes * 0.7);
    col = mix(col, lit, bokeh * 0.28);
  }
  return col;
}

vec3 addSill(vec3 col, vec2 uv, vec2 p) {
  float top = 0.06 + 0.025 * fbm(vec2(p.x * 2.5, 3.0)) + 0.008 * valueNoise(vec2(p.x * 14.0, 1.0));
  float sill = smoothstep(top + 0.003, top - 0.003, uv.y);
  float shade = smoothstep(top, top - 0.05, uv.y);
  vec3 day = mix(vec3(0.97, 0.98, 1.0), vec3(0.8, 0.84, 0.92), shade);
  vec3 night = mix(vec3(0.32, 0.35, 0.46), vec3(0.12, 0.13, 0.19), shade);
  vec3 snow = mix(day, night, uDark) + LAMP_WARM * 0.08 * uDark * smoothstep(0.6, 0.0, p.x);

  // Glints: tiny round sparkles that twinkle on and off.
  vec2 q = p * 90.0;
  vec2 cell = floor(q);
  vec2 spot = fract(q) - 0.5 - (hash22(cell) - 0.5) * 0.5;
  float twinkle = pow(max(0.0, sin(uTime * 1.7 + hash21(cell + 4.0) * 60.0)), 16.0);
  float glint = step(0.975, hash21(cell)) * smoothstep(0.16, 0.0, length(spot)) * twinkle;
  snow += glint * sill * mix(0.6, 1.0, uDark);
  return mix(col, snow, sill);
}

// Frost: fern-like veins over a cloudy base, growing from the corners with a ragged edge.
vec3 addFrost(vec3 col, vec2 uv, vec2 p) {
  float a = aspect();
  vec2 corner = vec2(uv.x < 0.5 ? 0.0 : a, uv.y < 0.5 ? 0.0 : 1.0);
  float r = length(p - corner);

  float reach = (0.25 + 0.03 * sin(uTime * 0.012)) * min(1.0, a * 1.4);
  float ragged = (fbm(p * 4.0 + 5.0) - 0.5) * 0.2;
  float mask = smoothstep(reach, reach - 0.16, r + ragged);
  float edgeBand = smoothstep(0.035, 0.0, min(uv.y, 1.0 - uv.y) + (fbm(p * 8.0) - 0.5) * 0.03) * 0.35;
  mask = max(mask, edgeBand);
  if (mask < 0.001) return col;

  // Ridges of domain-warped noise branch like frost ferns; a cloudy base fills between.
  vec2 warped = p * 26.0 + vec2(fbm(p * 7.0), fbm(p * 7.0 + 4.1)) * 3.0;
  float veins = pow(1.0 - abs(2.0 * fbm(warped) - 1.0), 9.0);
  float cloud = fbm(p * 12.0 + 2.0);
  float density = mask * (0.3 + 0.25 * cloud + 0.4 * veins);

  vec3 frostCol = mix(vec3(0.98, 0.99, 1.0), vec3(0.58, 0.62, 0.72), uDark);
  frostCol += LAMP_WARM * 0.14 * uDark * smoothstep(0.8, 0.0, length(uv * vec2(a, 1.0)));
  return mix(col, frostCol, clamp(density, 0.0, 0.85));
}

// Flakes that land on the pane: a six-armed crystal that slowly melts into a droplet.
vec3 addGlassFlakes(vec3 col, vec2 p) {
  float scale = 7.0;
  vec2 cell = floor(p * scale);
  float h = hash21(cell + 40.0);
  if (h > 0.2 + 0.25 * uIntensity) return col;

  vec2 center = (cell + 0.5 + (hash22(cell + 41.0) - 0.5) * 0.6) / scale;
  vec2 d = p - center;
  float life = fract(uTime / 30.0 + fract(h * 7.0));
  float melt = smoothstep(0.08, 0.85, life);
  float present = smoothstep(0.0, 0.004, life) * smoothstep(1.0, 0.9, life);
  float size = mix(0.017, 0.006, melt) * (0.7 + 0.6 * fract(h * 3.3));

  float r = length(d);
  float angle = atan(d.y, d.x) + h * 6.28;
  float arms = pow(abs(cos(angle * 3.0)), mix(14.0, 0.5, melt));
  float twigs = 0.45 * pow(abs(cos(angle * 9.0)), 8.0) * step(0.35 * size, r) * (1.0 - melt);
  float reach = size * (0.18 + 0.82 * max(arms, twigs));
  float crystal = smoothstep(reach, reach * 0.7, r);
  float core = smoothstep(size * 0.22, size * 0.1, r);

  vec3 ice = mix(vec3(1.0), vec3(0.72, 0.78, 0.9), uDark);
  float amount = max(crystal, core) * present * mix(0.75, 0.4, melt);
  return mix(col, ice, amount);
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float a = aspect();
  vec2 p = uv * vec2(a, 1.0);
  float drift = windDrift(uTime) * 0.35;

  vec3 col = street(uv, p);
  col = addSnow(col, p, drift, 0.0);
  col = addSill(col, uv, p);
  col = addSnow(col, p, drift, 1.0);
  col = addFrost(col, uv, p);
  col = addGlassFlakes(col, p);

  vec2 lampPos = (uv - vec2(0.08, 0.05)) * vec2(a, 1.0);
  col += LAMP_WARM * 0.07 * smoothstep(0.9, 0.0, length(lampPos)) * uDark;

  float vignette = smoothstep(1.25, 0.3, length((uv - 0.5) * vec2(a, 1.0)));
  col *= mix(1.0, vignette, mix(0.15, 0.45, uDark));
  col += (hash21(gl_FragCoord.xy + fract(uTime * 7.13) * 100.0) - 0.5) * 0.025;
  gl_FragColor = vec4(col, 1.0);
}
