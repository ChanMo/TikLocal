// Summer night — TikLocal Radio ambience.
//
// Layers, back to front:
//   sky      indigo night with twinkling stars and a crescent moon, and a last glow at
//            the horizon tinted by the cover art
//   land     three hill silhouettes fading with distance, a tree line, and mist
//   life     fireflies wandering over the meadow, each flashing on its own rhythm,
//            some behind and some in front of the grass
//   grass    blades swaying in the breeze, a few carrying seed heads
//
// uDark blends a golden-hour meadow with drifting pollen (0) into night (1);
// uIntensity sets how many fireflies are out; uEnergy (0.5 when unknown) brightens them.

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
uniform sampler2D uBlur;

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

vec3 coverTint() {
  vec3 c = texture2D(uBlur, vec2(0.5, 0.45)).rgb + texture2D(uBlur, vec2(0.3, 0.6)).rgb;
  return c / max(max(c.r, c.g), max(c.b, 0.05));
}

// A breeze that comes and goes; used to sway the grass.
float breeze(float x, float t) {
  return sin(t * 0.9 + x * 1.7) * 0.5 + sin(t * 1.7 + x * 3.1) * 0.25 + (valueNoise(vec2(x * 0.8, t * 0.35)) - 0.5) * 1.2;
}

vec3 sky(vec2 uv, vec2 p) {
  float a = aspect();
  float h = smoothstep(0.2, 1.0, uv.y);
  vec3 afterglow = mix(vec3(0.95, 0.5, 0.3), coverTint(), 0.3);

  vec3 night = mix(vec3(0.1, 0.13, 0.22), vec3(0.02, 0.028, 0.075), h);
  night += vec3(0.06, 0.12, 0.16) * smoothstep(0.5, 0.3, uv.y);
  night += afterglow * 0.22 * exp(-pow((uv.x - 0.78) * 2.2, 2.0)) * smoothstep(0.55, 0.24, uv.y);

  vec3 day = mix(vec3(1.0, 0.8, 0.58), vec3(0.58, 0.7, 0.86), smoothstep(0.2, 0.95, uv.y));
  day += vec3(1.0, 0.75, 0.45) * 0.35 * exp(-length((p - vec2(a * 0.78, 0.33)) * vec2(1.0, 1.6)) * 3.0);
  vec3 col = mix(day, night, uDark);

  // Stars, fading toward the horizon.
  vec2 cell = floor(p * 90.0);
  vec2 spot = fract(p * 90.0) - 0.2 - hash22(cell) * 0.6;
  float bright = hash21(cell + 7.0);
  float star = step(0.972, hash21(cell)) * smoothstep(0.12 + 0.1 * bright, 0.0, length(spot));
  float twinkle = 0.6 + 0.4 * sin(uTime * (1.0 + hash21(cell + 1.0) * 3.0) + hash21(cell) * 40.0);
  col += vec3(0.85, 0.9, 1.0) * star * twinkle * smoothstep(0.35, 0.75, uv.y) * uDark * 0.9;

  // Crescent moon with a soft halo.
  vec2 moon = vec2(a * 0.2, 0.82);
  float disc = smoothstep(0.036, 0.032, length(p - moon));
  float bite = smoothstep(0.032, 0.036, length(p - moon - vec2(0.014, 0.008)));
  col += vec3(1.0, 0.96, 0.85) * disc * bite * uDark * 0.9;
  col += vec3(0.6, 0.65, 0.8) * exp(-length(p - moon) * 9.0) * 0.12 * uDark;
  return col;
}

vec3 land(vec3 col, vec2 uv, vec2 p) {
  float t = uTime;
  vec3 hazeNight = vec3(0.08, 0.09, 0.16);
  vec3 hazeDay = vec3(0.95, 0.78, 0.6);
  for (int i = 0; i < 3; i++) {
    float fi = float(i);
    float base = 0.36 - fi * 0.065;
    float ridge = base + 0.06 * fbm(vec2(p.x * (1.2 + fi * 0.6) + fi * 13.0, fi));
    if (i == 1) ridge += 0.03 * smoothstep(0.35, 0.8, fbm(vec2(p.x * 9.0, 4.0)));
    float hill = smoothstep(ridge + 0.004, ridge - 0.004, uv.y);
    float distance_ = 1.0 - fi / 2.0;
    vec3 night = mix(vec3(0.03, 0.04, 0.06), hazeNight * 1.3, distance_ * 0.75);
    vec3 day = mix(vec3(0.2, 0.2, 0.12), hazeDay, distance_ * 0.7);
    vec3 tone = mix(day, night, uDark);
    if (i == 2) {
      // The meadow itself: streaks of grass catching moonlight or low sun.
      float field = fbm(vec2(p.x * 40.0, uv.y * 6.0)) * 0.6 + fbm(vec2(p.x * 90.0, uv.y * 3.0)) * 0.4;
      tone *= 0.75 + 0.5 * field;
      tone += mix(vec3(0.3, 0.2, 0.08), vec3(0.03, 0.045, 0.08), uDark) * smoothstep(0.05, ridge, uv.y) * 0.5;
    }
    col = mix(col, tone, hill);
  }
  // Mist lying in the valley, drifting slowly.
  float mist = smoothstep(0.12, 0.0, abs(uv.y - 0.27)) * fbm(vec2(p.x * 2.0 - t * 0.02, uv.y * 6.0));
  col = mix(col, mix(vec3(1.0, 0.86, 0.7), vec3(0.2, 0.22, 0.32), uDark), mist * 0.4);
  return col;
}

// Fireflies (night) or pollen (day) in one depth layer; checks neighbouring cells so
// glows may cross cell borders.
vec3 lights(vec2 p, float scale, float seed, float depth) {
  vec3 acc = vec3(0.0);
  vec2 q = p * scale;
  vec2 id = floor(q);
  float count = 0.4 + 0.5 * uIntensity;
  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      vec2 cell = id + vec2(float(i), float(j));
      float h = hash21(cell + seed);
      if (h > count) continue;
      vec2 r = hash22(cell + seed * 3.1);
      vec2 wander = vec2(sin(uTime * (0.15 + r.x * 0.2) + r.y * 20.0), sin(uTime * (0.12 + r.y * 0.18) + r.x * 30.0));
      vec2 center = cell + 0.5 + (r - 0.5) * 0.4 + wander * 0.35;
      float d = length(q - center);

      float period = 2.5 + 3.5 * fract(h * 17.0);
      float phase = fract(uTime / period + r.x);
      float flash = smoothstep(0.0, 0.12, phase) * smoothstep(0.42, 0.18, phase);
      float night = (flash * 0.95 + 0.05) * (0.8 + 0.4 * uEnergy);
      float day = 0.35 + 0.25 * sin(uTime * 2.0 + h * 50.0);
      float level = mix(day, night, uDark);

      // Near layers are out of focus: a soft disc instead of a point.
      float focus = clamp(depth - 1.0, 0.0, 1.0);
      float bokeh = smoothstep(0.2, 0.15, d) * (0.16 + 0.14 * smoothstep(0.08, 0.18, d));
      float core = mix(exp(-d * d * 900.0 / (scale * 0.2)), bokeh, focus);
      float glow = exp(-d * mix(7.0, 5.0, focus)) * mix(0.45, 0.2, focus);
      vec3 tone = mix(vec3(1.0, 0.85, 0.55), vec3(0.78, 1.0, 0.38), uDark);
      acc += tone * (core * 1.4 + glow * uDark) * level * min(depth, 1.0);
    }
  }
  return acc;
}

// Grass silhouettes: blades curving with the breeze, a few with seed heads.
float grass(vec2 p, float spacing, float tall, float seed, out float tip) {
  float coverage = 0.0;
  tip = 0.0;
  float column = floor(p.x / spacing);
  for (int k = -2; k <= 2; k++) {
    float c = column + float(k);
    float h = hash21(vec2(c, seed));
    float height = tall * (0.45 + 0.75 * h) * (0.9 + 0.2 * valueNoise(vec2(c * 0.1, seed)));
    if (p.y > height + 0.02) continue;
    float y = clamp(p.y / height, 0.0, 1.0);
    float lean = (fract(h * 7.3) - 0.5) * 0.06 + breeze(c * spacing, uTime) * 0.018 * (0.6 + h);
    float x = (c + 0.5 + (fract(h * 3.1) - 0.5) * 0.8) * spacing + lean * y * y * 3.0;
    float width = spacing * 0.28 * (1.0 - y) + 0.0006;
    float blade = smoothstep(width, width * 0.4, abs(p.x - x)) * step(p.y, height) * step(0.0, p.y);
    coverage = max(coverage, blade);
    if (fract(h * 11.0) > 0.86) {
      float seedHead = smoothstep(0.006, 0.003, length((p - vec2(x, height)) * vec2(1.8, 0.7)));
      tip = max(tip, seedHead);
    }
  }
  return max(coverage, tip);
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float a = aspect();
  vec2 p = uv * vec2(a, 1.0);

  vec3 col = sky(uv, p);
  col = land(col, uv, p);
  col += lights(p, 7.0, 1.0, 0.6) * smoothstep(0.42, 0.25, uv.y);

  float tip;
  float backGrass = grass(p + vec2(0.37, 0.0), 0.011, 0.14, 2.0, tip);
  vec3 backNight = vec3(0.022, 0.03, 0.05);
  vec3 backDay = vec3(0.3, 0.27, 0.15);
  col = mix(col, mix(backDay, backNight, uDark), backGrass * 0.9);

  col += lights(p, 4.0, 5.0, 1.0) * smoothstep(0.62, 0.1, uv.y);

  col += lights(p, 2.2, 9.0, 1.9) * smoothstep(0.75, 0.2, uv.y) * mix(0.5, 0.8, uDark);

  float frontGrass = grass(p, 0.016, 0.24, 7.0, tip);
  vec3 frontNight = vec3(0.008, 0.011, 0.02);
  vec3 frontDay = vec3(0.14, 0.13, 0.07);
  vec3 rim = mix(vec3(1.0, 0.72, 0.4) * 0.35, vec3(0.2, 0.25, 0.4) * 0.12, uDark);
  col = mix(col, mix(frontDay, frontNight, uDark) + rim * tip, frontGrass);

  float vignette = smoothstep(1.3, 0.3, length((uv - vec2(0.5, 0.45)) * vec2(a, 1.0)));
  col *= mix(1.0, vignette, mix(0.2, 0.5, uDark));
  col += (hash21(gl_FragCoord.xy + fract(uTime * 7.13) * 100.0) - 0.5) * 0.025;
  gl_FragColor = vec4(col, 1.0);
}
