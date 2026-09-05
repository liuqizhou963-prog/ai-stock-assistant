import { Renderer, Program, Mesh, Color, Triangle } from 'https://cdn.jsdelivr.net/npm/ogl@1.0.11/+esm';

const vertexShader = `
attribute vec2 uv;
attribute vec2 position;

varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = vec4(position, 0, 1);
}
`;

const fragmentShader = `
precision highp float;

uniform float uTime;
uniform vec3 uResolution;
uniform vec2 uFocal;
uniform vec2 uRotation;
uniform float uStarSpeed;
uniform float uDensity;
uniform float uHueShift;
uniform float uSpeed;
uniform vec2 uMouse;
uniform float uGlowIntensity;
uniform float uSaturation;
uniform bool uMouseRepulsion;
uniform float uTwinkleIntensity;
uniform float uRotationSpeed;
uniform float uRepulsionStrength;
uniform float uMouseActiveFactor;
uniform float uAutoCenterRepulsion;
uniform bool uTransparent;

varying vec2 vUv;

#define NUM_LAYER 4.0
#define STAR_COLOR_CUTOFF 0.2
#define MAT45 mat2(0.7071, -0.7071, 0.7071, 0.7071)
#define PERIOD 3.0

float Hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float tri(float x) {
  return abs(fract(x) * 2.0 - 1.0);
}

float tris(float x) {
  float t = fract(x);
  return 1.0 - smoothstep(0.0, 1.0, abs(2.0 * t - 1.0));
}

float trisn(float x) {
  float t = fract(x);
  return 2.0 * (1.0 - smoothstep(0.0, 1.0, abs(2.0 * t - 1.0))) - 1.0;
}

vec3 hsv2rgb(vec3 c) {
  vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
  vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
  return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float Star(vec2 uv, float flare) {
  float d = length(uv);
  float m = (0.05 * uGlowIntensity) / d;
  float rays = smoothstep(0.0, 1.0, 1.0 - abs(uv.x * uv.y * 1000.0));
  m += rays * flare * uGlowIntensity;
  uv *= MAT45;
  rays = smoothstep(0.0, 1.0, 1.0 - abs(uv.x * uv.y * 1000.0));
  m += rays * 0.3 * flare * uGlowIntensity;
  m *= smoothstep(1.0, 0.2, d);
  return m;
}

vec3 StarLayer(vec2 uv) {
  vec3 col = vec3(0.0);
  vec2 gv = fract(uv) - 0.5;
  vec2 id = floor(uv);

  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 offset = vec2(float(x), float(y));
      vec2 si = id + vec2(float(x), float(y));
      float seed = Hash21(si);
      float size = fract(seed * 345.32);
      float glossLocal = tri(uStarSpeed / (PERIOD * seed + 1.0));
      float flareSize = smoothstep(0.9, 1.0, size) * glossLocal;

      float red = smoothstep(STAR_COLOR_CUTOFF, 1.0, Hash21(si + 1.0)) + STAR_COLOR_CUTOFF;
      float blu = smoothstep(STAR_COLOR_CUTOFF, 1.0, Hash21(si + 3.0)) + STAR_COLOR_CUTOFF;
      float grn = min(red, blu) * seed;
      vec3 base = vec3(red, grn, blu);

      float hue = atan(base.g - base.r, base.b - base.r) / (2.0 * 3.14159) + 0.5;
      hue = fract(hue + uHueShift / 360.0);
      float sat = length(base - vec3(dot(base, vec3(0.299, 0.587, 0.114)))) * uSaturation;
      float val = max(max(base.r, base.g), base.b);
      base = hsv2rgb(vec3(hue, sat, val));

      vec2 pad = vec2(
        tris(seed * 34.0 + uTime * uSpeed / 10.0),
        tris(seed * 38.0 + uTime * uSpeed / 30.0)
      ) - 0.5;

      float star = Star(gv - offset - pad, flareSize);
      vec3 color = base;

      float twinkle = trisn(uTime * uSpeed + seed * 6.2831) * 0.5 + 1.0;
      twinkle = mix(1.0, twinkle, uTwinkleIntensity);
      star *= twinkle;

      col += star * size * color;
    }
  }

  return col;
}

void main() {
  vec2 focalPx = uFocal * uResolution.xy;
  vec2 uv = (vUv * uResolution.xy - focalPx) / uResolution.y;
  vec2 mouseNorm = uMouse - vec2(0.5);

  if (uAutoCenterRepulsion > 0.0) {
    vec2 centerUV = vec2(0.0, 0.0);
    float centerDist = length(uv - centerUV);
    vec2 repulsion = normalize(uv - centerUV) * (uAutoCenterRepulsion / (centerDist + 0.1));
    uv += repulsion * 0.05;
  } else if (uMouseRepulsion) {
    vec2 mousePosUV = (uMouse * uResolution.xy - focalPx) / uResolution.y;
    float mouseDist = length(uv - mousePosUV);
    vec2 repulsion = normalize(uv - mousePosUV) * (uRepulsionStrength / (mouseDist + 0.1));
    uv += repulsion * 0.05 * uMouseActiveFactor;
  } else {
    vec2 mouseOffset = mouseNorm * 0.1 * uMouseActiveFactor;
    uv += mouseOffset;
  }

  float autoRotAngle = uTime * uRotationSpeed;
  mat2 autoRot = mat2(cos(autoRotAngle), -sin(autoRotAngle), sin(autoRotAngle), cos(autoRotAngle));
  uv = autoRot * uv;
  uv = mat2(uRotation.x, -uRotation.y, uRotation.y, uRotation.x) * uv;

  vec3 col = vec3(0.0);
  for (float i = 0.0; i < 1.0; i += 1.0 / NUM_LAYER) {
    float depth = fract(i + uStarSpeed * uSpeed);
    float scale = mix(20.0 * uDensity, 0.5 * uDensity, depth);
    float fade = depth * smoothstep(1.0, 0.9, depth);
    col += StarLayer(uv * scale + i * 453.32) * fade;
  }

  if (uTransparent) {
    float alpha = length(col);
    alpha = smoothstep(0.0, 0.3, alpha);
    alpha = min(alpha, 1.0);
    gl_FragColor = vec4(col, alpha);
  } else {
    gl_FragColor = vec4(col, 1.0);
  }
}
`;

function startGalaxyBackground() {
  const container = document.getElementById('galaxyLayer');
  if (!container || container.dataset.ready === '1') return;
  container.dataset.ready = '1';

  const prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const targetMousePos = { x: 0.5, y: 0.5 };
  const smoothMousePos = { x: 0.5, y: 0.5 };
  let targetMouseActive = 0.0;
  let smoothMouseActive = 0.0;
  let rafId = 0;
  let renderer;
  let program;
  let gl;
  let cleanup = () => {};

  try {
    renderer = new Renderer({ alpha: true, premultipliedAlpha: false });
    gl = renderer.gl;
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    gl.canvas.style.width = '100%';
    gl.canvas.style.height = '100%';
    gl.canvas.style.display = 'block';
    gl.canvas.style.pointerEvents = 'none';
    container.appendChild(gl.canvas);

    const geometry = new Triangle(gl);
    program = new Program(gl, {
      vertex: vertexShader,
      fragment: fragmentShader,
      uniforms: {
        uTime: { value: 0 },
        uResolution: { value: new Color(1, 1, 1) },
        uFocal: { value: new Float32Array([0.5, 0.5]) },
        uRotation: { value: new Float32Array([1.0, 0.0]) },
        uStarSpeed: { value: 0.45 },
        uDensity: { value: 0.92 },
        uHueShift: { value: 205.0 },
        uSpeed: { value: 1.0 },
        uMouse: { value: new Float32Array([0.5, 0.5]) },
        uGlowIntensity: { value: 0.18 },
        uSaturation: { value: 0.10 },
        uMouseRepulsion: { value: true },
        uTwinkleIntensity: { value: 0.18 },
        uRotationSpeed: { value: 0.05 },
        uRepulsionStrength: { value: 1.6 },
        uMouseActiveFactor: { value: 0.0 },
        uAutoCenterRepulsion: { value: 0.0 },
        uTransparent: { value: true }
      }
    });

    const mesh = new Mesh(gl, { geometry, program });

    function resize() {
      const width = container.clientWidth || window.innerWidth;
      const height = container.clientHeight || window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      renderer.setSize(Math.max(1, Math.round(width * dpr)), Math.max(1, Math.round(height * dpr)));
      gl.canvas.style.width = '100%';
      gl.canvas.style.height = '100%';
      program.uniforms.uResolution.value = new Color(
        gl.canvas.width,
        gl.canvas.height,
        gl.canvas.width / gl.canvas.height
      );
    }

    function handleMouseMove(e) {
      const rect = container.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const y = 1.0 - (e.clientY - rect.top) / rect.height;
      targetMousePos.x = Math.max(0, Math.min(1, x));
      targetMousePos.y = Math.max(0, Math.min(1, y));
      targetMouseActive = 1.0;
    }

    function handleMouseLeave() {
      targetMouseActive = 0.0;
    }

    function update(t) {
      if (!prefersReduced) {
        rafId = requestAnimationFrame(update);
      }

      if (!prefersReduced) {
        program.uniforms.uTime.value = t * 0.001;
        program.uniforms.uStarSpeed.value = (t * 0.001 * 0.45) / 10.0;
      }

      const lerpFactor = prefersReduced ? 0.08 : 0.05;
      smoothMousePos.x += (targetMousePos.x - smoothMousePos.x) * lerpFactor;
      smoothMousePos.y += (targetMousePos.y - smoothMousePos.y) * lerpFactor;
      smoothMouseActive += (targetMouseActive - smoothMouseActive) * lerpFactor;

      program.uniforms.uMouse.value[0] = smoothMousePos.x;
      program.uniforms.uMouse.value[1] = smoothMousePos.y;
      program.uniforms.uMouseActiveFactor.value = smoothMouseActive;

      renderer.render({ scene: mesh });
    }

    resize();
    window.addEventListener('resize', resize, false);
    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    window.addEventListener('blur', handleMouseLeave);
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) handleMouseLeave();
    });

    if (!prefersReduced) {
      rafId = requestAnimationFrame(update);
    } else {
      renderer.render({ scene: mesh });
    }

    cleanup = function () {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize, false);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('blur', handleMouseLeave);
      if (gl && gl.canvas && gl.canvas.parentNode === container) {
        container.removeChild(gl.canvas);
      }
      gl?.getExtension('WEBGL_lose_context')?.loseContext();
    };
  } catch (error) {
    console.warn('Galaxy background failed to initialize', error);
    cleanup = function () {};
  }

  window.addEventListener('pagehide', cleanup, { once: true });
}

startGalaxyBackground();
