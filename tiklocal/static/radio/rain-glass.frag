// Rain on glass — TikLocal Radio ambience.
//
// Layers, back to front:
//   outside  blurred cover art as the city at night, with bokeh lights tinted by it
//   fog      condensation on the glass that softens and lifts the outside
//   drops    resting droplets plus sliding drops that wipe clear trails through the fog;
//            each drop is a tiny lens that shows the outside flipped and sharper
//   room     warm lamp reflection, lightning flash, vignette and grain
//
// Uniforms are driven by radio_scene.js. uDark blends between an overcast day (0)
// and a rainy night (1); uRain (0..1) sets how many drops are on the glass.

#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec2 uRes;
uniform float uTime;
uniform float uDark;
uniform float uRain;
uniform float uFlash;
uniform sampler2D uSharp;
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

float aspect() {
  return uRes.x / uRes.y;
}

// Screen uv -> cover texture uv, cropped like object-fit: cover, with a slow drift.
vec2 coverUv(vec2 uv) {
  vec2 c = uv - 0.5;
  float a = aspect();
  if (a < 1.0) c.x *= a; else c.y /= a;
  c *= 0.86;
  c += 0.025 * vec2(sin(uTime * 0.031), cos(uTime * 0.027));
  return c + 0.5;
}

vec3 bokehLayer(vec2 uv, float scale, float seed, float soft) {
  float a = aspect();
  float drift = uTime * 0.018 * (0.6 + seed * 0.3);
  vec2 q = uv * vec2(a, 1.0) * scale + vec2(drift, 0.0);
  vec2 id = floor(q);
  vec3 acc = vec3(0.0);

  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      vec2 cid = id + vec2(float(i), float(j));
      vec2 r = hash22(cid + seed * 17.0);
      if (r.x < 0.5) continue;

      vec2 center = cid + 0.5 + (hash22(cid + 3.1 + seed) - 0.5) * 0.9;
      float radius = mix(0.2, 0.46, r.y);
      float dist = length(q - center);
      float edge = mix(0.04, 0.55, soft) * radius;
      float disc = smoothstep(radius, radius - edge - 0.01, dist);
      float rim = smoothstep(radius * 0.45, radius, dist) * disc;

      vec2 lightUv = (center - vec2(drift, 0.0)) / scale / vec2(a, 1.0);
      vec3 tint = texture2D(uBlur, coverUv(lightUv)).rgb;
      tint /= max(max(tint.r, tint.g), max(tint.b, 0.05));
      tint = mix(tint, vec3(1.0, 0.76, 0.48), step(0.78, r.x));

      float flicker = 0.78 + 0.22 * sin(uTime * (0.15 + r.y * 0.5) + r.x * 40.0);
      float level = mix(0.22, 0.85, fract(r.x * 7.3)) * flicker;
      acc += tint * (disc * 0.6 + rim * (0.55 - soft * 0.4)) * level;
    }
  }
  return acc;
}

// What is behind the glass. soft = 0 seen through clear water, 1 seen through fog.
vec3 outside(vec2 uv, float soft) {
  vec2 cu = coverUv(uv);
  vec3 blurred = texture2D(uBlur, cu).rgb;
  vec3 sharper = texture2D(uSharp, cu, 2.0).rgb;
  vec3 base = mix(sharper, blurred, soft);
  float luma = dot(base, vec3(0.299, 0.587, 0.114));

  vec3 night = max(mix(vec3(luma), base, 1.3), 0.0) * 0.26;
  vec3 day = mix(vec3(luma), base, 0.5) * 0.5 + vec3(0.43, 0.46, 0.49);
  vec3 col = mix(day, night, uDark);

  float street = smoothstep(1.05, 0.2, uv.y);
  vec3 lights = bokehLayer(uv, 4.2, 1.0, soft) * 0.75 + bokehLayer(uv, 7.5, 2.0, soft) * 0.4;
  col += lights * street * mix(0.28, 1.0, uDark);
  return col;
}

// Resting droplets. xy = lens offset (screen-height units), z = lens mask, w = clear mask.
vec4 restingDrops(vec2 p, float scale, float seed) {
  vec2 q = p * scale;
  vec2 id = floor(q);
  vec2 f = fract(q) - 0.5;
  vec2 r = hash22(id + seed);

  float present = step(1.0 - uRain * 0.55, hash21(id * 1.31 + seed * 3.3));
  float life = fract(uTime * 0.03 + hash21(id * 1.7 + seed));
  float grow = smoothstep(0.0, 0.03, life) * smoothstep(1.0, 0.8, life);
  float radius = mix(0.08, 0.26, r.y) * grow;

  vec2 d = f - (r - 0.5) * 0.4;
  float m = smoothstep(radius, radius * 0.72, length(d)) * present;
  return vec4(d / scale * m, m, m);
}

// Drops sliding down in columns, creeping then running, leaving a trail of beads.
vec4 slidingDrops(vec2 p, float scale, float seed, float t) {
  vec2 cell = vec2(1.0, 3.0);
  vec2 q = p * scale;
  q.y += t * 0.32;

  vec2 g = q / cell;
  vec2 id = floor(g);
  vec2 st = (fract(g) - 0.5) * cell;

  float h = hash21(id + seed);
  float active = step(1.0 - (0.25 + uRain * 0.45), h);
  float h2 = hash21(id * 2.3 + seed);
  float h3 = hash21(id * 3.7 + seed);

  // Creep (rise in cell space, which is slow descent on screen), then run.
  float travel = cell.y * 0.5 - 0.3;
  float speed = mix(0.055, 0.085, h2);
  float phase = fract(t * speed + h * 7.0);
  float run = 0.86;
  float y = phase < run
    ? mix(-travel, travel, phase / run)
    : mix(travel, -travel, smoothstep(run, 1.0, phase));

  float laneX = (h3 - 0.5) * 0.36;
  float dropX = laneX + sin(y * 2.7 + h * 20.0) * 0.08 + sin(y * 7.1 + h2 * 9.0) * 0.02;
  float pathX = laneX + sin(st.y * 2.7 + h * 20.0) * 0.08 + sin(st.y * 7.1 + h2 * 9.0) * 0.02;

  float radius = mix(0.1, 0.15, h2);
  float running = smoothstep(run, run + 0.02, phase) * (1.0 - smoothstep(0.97, 1.0, phase));
  vec2 d = st - vec2(dropX, y);
  d.y *= mix(1.0, 0.72, running);
  float drop = smoothstep(radius, radius * 0.75, length(d));

  float above = st.y - y;
  float trailWidth = radius * 0.5;
  float trail = smoothstep(trailWidth, trailWidth * 0.35, abs(st.x - pathX))
    * smoothstep(0.0, radius, above)
    * smoothstep(travel * 1.3, 0.0, above);

  vec2 bead = vec2(st.x - pathX, (fract(st.y * 5.0) - 0.5) / 5.0);
  float beadRadius = radius * 0.32 * smoothstep(radius * 1.5, radius * 2.5, above);
  float beads = smoothstep(beadRadius, beadRadius * 0.6, length(bead)) * trail;

  vec2 offset = (d * drop + bead * beads) / scale;
  float lens = max(drop, beads);
  return vec4(offset, lens, max(trail, lens)) * active;
}

vec4 glass(vec2 p) {
  vec4 a = restingDrops(p, 22.0, 1.3);
  vec4 b = restingDrops(p + 3.7, 41.0, 2.1);
  vec4 c = slidingDrops(p, 3.4, 4.2, uTime);
  vec4 d = slidingDrops(p + vec2(0.37, 0.0), 5.6, 7.9, uTime * 1.08);
  vec4 sum = vec4(a.xy + b.xy + c.xy + d.xy, 0.0, 0.0);
  sum.z = max(max(a.z, b.z), max(c.z, d.z));
  sum.w = max(max(a.w, b.w), max(c.w, d.w));
  return sum;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float a = aspect();
  vec2 p = uv * vec2(a, 1.0);

  vec4 g = glass(p);
  float lens = clamp(g.z, 0.0, 1.0);
  float clear = clamp(g.w, 0.0, 1.0);

  float condensation = valueNoise(p * 2.2 + vec2(uTime * 0.01, 0.0)) * 0.6
    + valueNoise(p * 5.3 - uTime * 0.012) * 0.4;
  condensation = mix(0.45, 1.0, condensation) * mix(0.8, 1.0, smoothstep(0.7, 0.0, uv.y));

  vec3 glassTint = mix(vec3(0.82, 0.84, 0.86), vec3(0.1, 0.11, 0.12), uDark);
  vec3 fogView = outside(uv, 1.0);
  fogView = mix(fogView, glassTint, 0.32 * condensation);
  vec3 col = fogView;

  if (clear > 0.001) {
    vec2 refracted = uv - g.xy * vec2(1.0 / a, 1.0) * 3.2;
    vec3 clearView = outside(refracted, 0.3) * (1.0 + lens * mix(0.02, 0.35, uDark)) + lens * 0.025 * uDark;
    float rimShade = lens * (1.0 - lens) * 4.0;
    clearView *= 1.0 - rimShade * mix(0.3, 0.18, uDark);
    vec2 dir = g.xy / (length(g.xy) + 1e-5);
    float glint = pow(max(dot(dir, vec2(-0.6, 0.8)), 0.0), 6.0) * rimShade;
    clearView += glint * mix(0.14, 0.55, uDark);
    col = mix(fogView, clearView, clear);
  }

  vec2 lampPos = (uv - vec2(0.1, 0.06)) * vec2(a, 1.0);
  col += vec3(1.0, 0.6, 0.28) * 0.08 * smoothstep(0.9, 0.0, length(lampPos)) * uDark;

  col += uFlash * (vec3(0.72, 0.78, 0.95) * 0.3 + fogView * 0.9) * mix(0.35, 1.0, uDark);

  float vignette = smoothstep(1.25, 0.3, length((uv - 0.5) * vec2(a, 1.0)));
  col *= mix(1.0, vignette, mix(0.18, 0.5, uDark));

  col += (hash21(gl_FragCoord.xy + fract(uTime * 7.13) * 100.0) - 0.5) * 0.03;
  gl_FragColor = vec4(col, 1.0);
}
