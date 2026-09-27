// Hearth — TikLocal Radio ambience.
//
// Layers, back to front:
//   wall     brick firebox lit by the fire's flicker, bent by heat haze, sooty above
//   fire     tapering flame tongues carved by rising turbulence, coloured along a
//            blackbody ramp from deep red to a near-white core
//   logs     charred logs with glowing cracks and two cut ends showing their rings,
//            over a bed of irregular coals that glow and breathe one by one
//   sparks   embers drifting upward and fading
//
// Where flames leave the wood they burn faintly blue. The room's rare event (uEvent,
// seconds since it began) is a log settling: the fire flares and throws up sparks.
//
// uDark blends a daylit, whitewashed hearth (0) into a dark room lit only by the fire
// (1); uIntensity swells the fire slowly; uEnergy (0.5 when unknown) lets it roar
// with the music.

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

// Blackbody-like ramp: 0 = nothing, 0.3 deep red, 0.6 orange, 1 near white.
vec3 fireColor(float heat) {
  vec3 red = vec3(0.75, 0.12, 0.02);
  vec3 orange = vec3(1.0, 0.45, 0.08);
  vec3 yellow = vec3(1.0, 0.82, 0.45);
  vec3 white = vec3(1.0, 0.96, 0.86);
  vec3 col = mix(red, orange, smoothstep(0.2, 0.55, heat));
  col = mix(col, yellow, smoothstep(0.55, 0.8, heat));
  col = mix(col, white, smoothstep(0.85, 1.0, heat));
  return col * smoothstep(0.0, 0.4, heat) * (0.55 + heat * 1.25);
}

// Flare after a log settles: rises quickly, then dies away over a few seconds.
float flare() {
  return uEvent < 0.0 ? 0.0 : smoothstep(0.0, 0.12, uEvent) * exp(-uEvent * 1.3);
}

// Overall brightness of the fire: slow breathing plus a soft, irregular flicker.
float fireLevel(float t) {
  float flicker = 0.86 + 0.1 * valueNoise(vec2(t * 6.0, 1.0)) + 0.06 * valueNoise(vec2(t * 13.0, 7.0));
  return flicker * (0.8 + 0.25 * uIntensity) * (0.85 + 0.3 * uEnergy) * (1.0 + 0.3 * flare());
}

// Smooth maximum: merges neighbouring tongues into one body of flame.
float smax(float a, float b, float k) {
  float h = max(k - abs(a - b), 0.0) / k;
  return max(a, b) + h * h * k * 0.25;
}

// Heat of the flames at q, where q.x is centred on the fire and q.y = 0 at its base.
float flames(vec2 q, float t) {
  if (q.y < -0.05 || q.y > 0.8 || abs(q.x) > 0.5) return 0.0;
  float size = (0.8 + 0.25 * uIntensity) * (0.85 + 0.3 * uEnergy) * (1.0 + 0.25 * flare());
  // Negative outside every tongue, so the turbulence below only reshapes their edges.
  float heat = -1.0;
  for (int i = 0; i < 7; i++) {
    float fi = float(i);
    float seed = hash21(vec2(fi, 4.2));
    float x0 = (fi - 3.0) * 0.045 + 0.012 * sin(t * 0.7 + fi * 1.3);
    float height = (0.17 + 0.17 * seed + 0.05 * sin(t * (0.8 + seed) + fi * 2.1)) * size
      * (1.0 - 0.35 * abs(fi - 3.0) / 3.0);
    float y = q.y / height;
    float sway = (valueNoise(vec2(fi * 3.1, q.y * 5.0 - t * 1.6)) - 0.5) * 0.1 * y;
    float width = 0.085 * (1.0 - 0.72 * clamp(y, 0.0, 1.0)) * (0.8 + 0.4 * seed);
    float across = abs(q.x - x0 - sway) / width;
    // Additive falloff: stays negative away from the tongue in every direction.
    heat = smax(heat, 0.95 - across * 0.9 - y * 0.8, 0.25);
  }
  // A broad, low bed of flame running along the logs.
  heat = smax(heat, 0.9 - abs(q.x) / 0.3 * 0.7 - q.y / 0.1 * 0.8, 0.25);

  // Rising turbulence carves the edges and tears off licks near the top, sparing the base.
  float rising = fbm(vec2(q.x * 7.0, q.y * 5.0 - t * 3.4));
  float fine = valueNoise(vec2(q.x * 18.0, q.y * 12.0 - t * 6.0));
  heat -= (rising - 0.42) * (0.25 + q.y * 1.9) + (fine - 0.5) * 0.1;
  heat += 0.18 * smoothstep(0.12, 0.0, q.y) * exp(-q.x * q.x * 16.0);
  heat *= smoothstep(-0.05, 0.02, q.y);
  return clamp(heat, 0.0, 1.0);
}

vec3 brickWall(vec2 p, vec2 fireBase, float light, float haze) {
  vec2 b = p * vec2(11.0, 22.0);
  b.x += step(1.0, mod(floor(b.y), 2.0)) * 0.5;
  b.x += haze;
  vec2 cell = floor(b);
  vec2 f = fract(b);
  float mortar = smoothstep(0.0, 0.05, f.x) * smoothstep(1.0, 0.95, f.x)
    * smoothstep(0.0, 0.09, f.y) * smoothstep(1.0, 0.91, f.y);
  float tone = 0.7 + 0.3 * hash21(cell) + 0.16 * (fbm(p * 40.0) - 0.5);

  vec3 nightBrick = vec3(0.24, 0.13, 0.09) * tone;
  vec3 dayBrick = vec3(0.86, 0.8, 0.72) * (0.92 + 0.08 * tone);
  vec3 nightMortar = vec3(0.1, 0.08, 0.07);
  vec3 dayMortar = vec3(0.74, 0.69, 0.62);
  vec3 wall = mix(mix(dayMortar, nightMortar, uDark), mix(dayBrick, nightBrick, uDark), mortar);

  float soot = smoothstep(0.15, 0.9, p.y - fireBase.y) * smoothstep(0.5, 0.0, abs(p.x - fireBase.x));
  wall *= 1.0 - soot * mix(0.25, 0.6, uDark);

  vec3 firelight = vec3(1.0, 0.5, 0.18) * light;
  return mix(wall, wall * (0.02 + firelight * 2.4), uDark) + firelight * mix(0.1, 0.0, uDark);
}

// Distance to a capsule from a to b.
float capsule(vec2 p, vec2 a, vec2 b, float r) {
  vec2 pa = p - a;
  vec2 ba = b - a;
  float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  return length(pa - ba * h) - r;
}

// Voronoi: distance to the nearest point, gap to the second nearest (small along the
// edges between cells), and a random value for the nearest cell.
vec3 voronoi(vec2 p) {
  vec2 cell = floor(p);
  vec2 f = fract(p);
  float first = 8.0;
  float second = 8.0;
  float id = 0.0;
  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      vec2 o = vec2(float(i), float(j));
      float d = length(o + hash22(cell + o) - f);
      if (d < first) {
        second = first;
        first = d;
        id = hash21(cell + o + 13.7);
      } else if (d < second) {
        second = d;
      }
    }
  }
  return vec3(first, second - first, id);
}

float logs(vec2 q) {
  float d1 = capsule(q, vec2(-0.26, 0.012), vec2(0.2, 0.05), 0.036);
  float d2 = capsule(q, vec2(-0.14, 0.07), vec2(0.28, 0.02), 0.032);
  float d3 = capsule(q, vec2(-0.3, 0.035), vec2(-0.02, 0.1), 0.026);
  return min(min(d1, d2), d3);
}

// A sawn log end facing us: growth rings, pale wood, a charred rim that glows at night.
vec3 logEnd(vec3 col, vec2 q, vec2 center, vec2 radius, float level) {
  vec2 e = (q - center) / radius;
  float r = length(e);
  if (r > 1.05) return col;
  float face = smoothstep(1.0, 0.94, r);
  float rings = 0.5 + 0.5 * sin(r * 26.0 + fbm(e * 3.0) * 4.0);
  vec3 wood = mix(vec3(0.3, 0.19, 0.11), vec3(0.45, 0.3, 0.17), rings) * (0.7 + 0.3 * fbm(e * 9.0));
  wood = mix(wood * 1.6, wood * 0.35, uDark);
  float rim = smoothstep(0.72, 0.95, r);
  vec3 ember = fireColor(0.55 + 0.2 * valueNoise(vec2(atan(e.y, e.x) * 3.0, uTime * 0.5))) * level;
  vec3 charredRim = mix(vec3(0.05, 0.035, 0.03), ember * 0.9, uDark * smoothstep(0.35, 0.7, valueNoise(e * 7.0 + 3.0)));
  return mix(col, mix(wood, charredRim, rim), face);
}

vec3 addLogs(vec3 col, vec2 q, float t, float level) {
  float wood = logs(q);
  float underFire = exp(-q.x * q.x * 9.0);

  // Coal bed: irregular chunks under grey ash. Crevices glow where it is hot, and some
  // chunks glow right through, each breathing at its own pace.
  float lumpy = 0.012 * (valueNoise(vec2(q.x * 14.0, 2.0)) - 0.5);
  float bed = smoothstep(1.0, 0.92, length(vec2(q.x / 0.36, (q.y + 0.035 + lumpy) / 0.075)));
  if (bed > 0.0) {
    vec2 warp = vec2(fbm(q * 7.0), fbm(q * 7.0 + 5.2)) * 2.2;
    vec3 chunk = voronoi(q * vec2(30.0, 44.0) + warp);
    float crevice = smoothstep(0.1, 0.0, chunk.y);
    float breathing = 0.6 + 0.4 * sin(t * (0.3 + chunk.z * 0.6) + chunk.z * 30.0);
    float glowing = smoothstep(0.6, 1.0, chunk.z) * breathing;
    float hot = smoothstep(0.45, 0.8, fbm(q * 6.0 + vec2(t * 0.05, -t * 0.03))) * underFire * underFire;
    float ash = (0.04 + 0.07 * fbm(q * 70.0) + 0.05 * (1.0 - chunk.x)) * (1.0 - crevice * 0.7);
    vec3 crust = vec3(ash * 1.15, ash * 0.95, ash * 0.85);
    float glow = crevice * hot * 1.3 + glowing * (0.15 + hot) * (1.1 - chunk.x) * 0.8;
    vec3 coals = crust + fireColor(0.3 + 0.55 * hot) * glow * level;
    coals = mix(coals + vec3(0.35, 0.32, 0.3) * (1.0 - uDark) * 0.4, coals, uDark);
    col = mix(col, coals, bed);
  }

  float body = smoothstep(0.003, -0.003, wood);
  if (body > 0.0) {
    float grain = fbm(vec2(q.x * 50.0, q.y * 9.0));
    vec3 charred = mix(vec3(0.035, 0.025, 0.022), vec3(0.12, 0.08, 0.06), grain);
    charred = mix(charred * 3.5 + vec3(0.12, 0.09, 0.07), charred, uDark);
    // Cracks glow only on the underside and toward the middle, where the fire is.
    vec3 cracks = voronoi(q * vec2(30.0, 60.0) + 3.0);
    float crack = smoothstep(0.06, 0.0, cracks.y) * smoothstep(0.45, 0.75, valueNoise(q * 28.0));
    float facing = smoothstep(0.01, -0.03, wood + 0.02) * (0.3 + 0.7 * underFire);
    float glowAmount = crack * facing * (0.7 + 0.3 * valueNoise(vec2(q.x * 10.0, t * 0.6)));
    vec3 glow = fireColor(0.45 + 0.35 * glowAmount) * glowAmount * level * 1.4;
    // Round the logs: darker toward their silhouettes, firelit along the top edge.
    float depth = clamp(-wood / 0.03, 0.0, 1.0);
    charred *= 0.45 + 0.55 * sqrt(depth);
    float rim = smoothstep(-0.014, 0.0, wood) * underFire * step(0.0, q.y - 0.03);
    col = mix(col, charred + glow + vec3(1.0, 0.45, 0.12) * rim * 0.3 * level, body);
  }
  col = logEnd(col, q, vec2(0.214, 0.05), vec2(0.017, 0.036), level);
  col = logEnd(col, q, vec2(0.293, 0.02), vec2(0.015, 0.032), level);
  return col;
}

// Sparks thrown up when a log settles: each flies on its own arc with a short trail.
vec3 addBurst(vec3 col, vec2 q) {
  if (uEvent < 0.0) return col;
  for (int i = 0; i < 28; i++) {
    float fi = float(i);
    vec2 r = hash22(vec2(fi, uEventSeed * 91.0));
    float age = uEvent - r.x * 0.45;
    float life = 1.1 + r.y * 1.7;
    if (age < 0.0 || age > life) continue;
    vec2 launch = vec2((r.x - 0.5) * 0.3, 0.3 + r.y * 0.45);
    vec2 velocity = launch + vec2(0.0, -0.12) * age;
    vec2 pos = vec2((r.y - 0.5) * 0.14, 0.07) + launch * age + vec2(0.0, -0.06) * age * age
      + vec2(sin(age * 6.0 + fi) * 0.012, 0.0);
    vec2 dir = normalize(velocity);
    vec2 d = q - pos;
    float along = dot(d, dir);
    float across = length(d - dir * along);
    float trail = smoothstep(0.003, 0.0, across) * smoothstep(-0.035, 0.0, along) * step(along, 0.0);
    float fade = 1.0 - age / life;
    col += vec3(1.0, 0.6, 0.22) * (exp(-length(d) * 170.0) * 1.6 + trail * 0.7) * fade * fade;
  }
  return col;
}

vec3 addSparks(vec3 col, vec2 q, float t, float level) {
  for (int layer = 0; layer < 2; layer++) {
    float fl = float(layer);
    vec2 s = vec2(q.x * (16.0 + fl * 10.0), (q.y - t * (0.12 + fl * 0.05)) * (5.0 + fl * 3.0));
    vec2 cell = floor(s);
    float h = hash21(cell + fl * 11.0);
    if (h < 0.84) continue;
    vec2 f = fract(s) - 0.5;
    float wobble = sin(q.y * 14.0 + h * 40.0 + t) * 0.25;
    vec2 d = vec2(f.x - (hash21(cell + 3.0) - 0.5) * 0.5 - wobble, f.y * 0.6);
    float spark = exp(-dot(d, d) * 420.0);
    float fade = smoothstep(0.7, 0.12, q.y) * smoothstep(0.02, 0.12, q.y) * exp(-q.x * q.x * 14.0);
    float blink = 0.6 + 0.4 * sin(t * 9.0 + h * 50.0);
    col += vec3(1.0, 0.55, 0.18) * spark * fade * blink * level * 1.6;
  }
  return col;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float a = aspect();
  vec2 p = uv * vec2(a, 1.0);
  float t = uTime;

  vec2 fireBase = vec2(a * 0.5, 0.1);
  // Size the fire to the screen height, but keep it inside narrow portrait screens.
  vec2 q = (p - fireBase) / (1.35 * min(1.0, a * 1.25));
  float level = fireLevel(t);

  float distance_ = length((q - vec2(0.0, 0.14)) * vec2(0.8, 1.0));
  float light = level * (exp(-distance_ * 3.2) * 0.9 + exp(-distance_ * 1.2) * 0.12);
  float hazeMask = smoothstep(0.7, 0.2, q.y) * smoothstep(0.0, 0.15, q.y) * exp(-q.x * q.x * 10.0);
  float haze = sin(q.y * 38.0 - t * 5.0 + q.x * 6.0) * 0.12 * hazeMask;

  vec3 col = brickWall(p, fireBase, light, haze);

  // Hearth floor in front of the firebox.
  float floorMask = smoothstep(0.012, -0.012, q.y + 0.045);
  vec3 stone = mix(vec3(0.8, 0.76, 0.7), vec3(0.08, 0.06, 0.05), uDark) * (0.9 + 0.1 * fbm(p * vec2(6.0, 30.0)));
  stone += vec3(1.0, 0.5, 0.18) * light * 0.35 * uDark;
  col = mix(col, stone, floorMask);

  float heat = clamp(flames(q, t) * level, 0.0, 1.0);
  vec3 flameCol = fireColor(heat);
  // At night flames add light; by day they are laid over the pale wall so they keep colour.
  vec3 overWall = mix(col, flameCol / max(max(flameCol.r, flameCol.g), 0.001) * vec3(1.0, 0.95, 0.9),
    smoothstep(0.02, 0.35, heat) * 0.85);
  col = mix(overWall + flameCol * 0.2, col + flameCol * 1.25, uDark);

  // Blue roots where the flames leave the wood: just outside a log, with a log below.
  float wood = logs(q);
  float root = smoothstep(0.022, 0.004, wood) * step(0.0, wood) * step(logs(q - vec2(0.0, 0.025)), 0.0)
    * smoothstep(0.08, 0.35, heat) * (0.7 + 0.3 * valueNoise(vec2(q.x * 30.0, t * 3.0)));
  col += vec3(0.1, 0.25, 0.95) * root * mix(0.12, 0.35, uDark);

  col = addLogs(col, q, t, level);
  col = addSparks(col, q, t, level);
  col = addBurst(col, q);

  // Soft bloom around the flames.
  col += vec3(1.0, 0.42, 0.12) * exp(-length((q - vec2(0.0, 0.12)) * vec2(1.4, 1.0)) * 5.0) * 0.25 * level * uDark;

  float vignette = smoothstep(1.3, 0.25, length((uv - vec2(0.5, 0.4)) * vec2(a, 1.0)));
  col *= mix(1.0, vignette, mix(0.2, 0.65, uDark));
  col += (hash21(gl_FragCoord.xy + fract(t * 7.13) * 100.0) - 0.5) * 0.025;
  gl_FragColor = vec4(col, 1.0);
}
