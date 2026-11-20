// Crystal glyphs for glyphbyte.dev: each byte as a floating piece of dispersive glass that splits the light
// behind it into a rainbow, catches a moving sun and flares where the light hits an edge.
//
// On a tablet (720 to 999 px wide) a hero canvas with data-tablet="cycle" shows one big glyph instead of the
// row: every 3 seconds it spins hard and lands as the next byte of the row, over and over.
//
// Mounts on every <canvas data-crystals>. The glyph geometry comes from the global GLYPHS (spec/glyphs.json,
// inlined by site/build.py). The bytes come from the page: window.__gbBytes at start, then every
// `gb:bytes` event on document ({detail: {bytes: [..]}}), which site.js sends when the hero row changes.
// Built by `npm run build` in site/three into site/src/vendor/crystals.js.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const G = globalThis.GLYPHS;
const CORNERS = [[-1, -1, 8], [1, -1, 4], [1, 1, 2], [-1, 1, 1]];
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const darkQuery = matchMedia('(prefers-color-scheme: dark)');
const isDark = () => document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : darkQuery.matches;
const PAGE = { light: '#f5f6fb', dark: '#06070d' };   // must equal --bg in style.css, so the canvas has no edge

// ------------------------------------------------------------------ geometry
// a polyline with its corners filleted, so a tube follows it without pinching at the turns
// drop points that repeat the one before (and, when closed, a last point that repeats the first): a zero-length
// step has no direction, and the tube's frames turn into NaN
function dedupe(points, closed) {
  const out = [];
  for (const p of points) { const q = out[out.length - 1]; if (!q || Math.hypot(p[0] - q[0], p[1] - q[1]) > 1e-4) out.push(p); }
  if (closed && out.length > 2 && Math.hypot(out[0][0] - out[out.length - 1][0], out[0][1] - out[out.length - 1][1]) <= 1e-4) out.pop();
  return out;
}
function fillet(points, closed, r) {
  points = dedupe(points, closed);
  const n = points.length, out = [];
  for (let i = 0; i < n; i++) {
    const p = points[i];
    if (!closed && (i === 0 || i === n - 1)) { out.push(p); continue; }
    const a = points[(i - 1 + n) % n], b = points[(i + 1) % n];
    const la = Math.hypot(a[0] - p[0], a[1] - p[1]), lb = Math.hypot(b[0] - p[0], b[1] - p[1]);
    const ra = Math.min(r, la * 0.45), rb = Math.min(r, lb * 0.45);
    const p0 = [p[0] + (a[0] - p[0]) * ra / la, p[1] + (a[1] - p[1]) * ra / la], p1 = [p[0] + (b[0] - p[0]) * rb / lb, p[1] + (b[1] - p[1]) * rb / lb];
    for (let k = 0; k <= 5; k++) { const t = k / 5, u = 1 - t; out.push([u * u * p0[0] + 2 * u * t * p[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * p[1] + t * t * p1[1]]); }
  }
  return dedupe(out, closed);
}

function tube(points, closed, radius) {
  const pts = fillet(points, closed, 0.07);
  if (pts.length < 2) return [];
  // resample evenly so the faceted tube keeps steady facets along its length
  const v = pts.map(([x, y]) => new THREE.Vector3(x, -y, 0));
  const curve = new THREE.CatmullRomCurve3(v, closed, 'catmullrom', 0.05);
  const len = curve.getLength();
  const parts = [new THREE.TubeGeometry(curve, Math.max(12, Math.round(len * 90)), radius, 6, closed).toNonIndexed()];
  if (!closed) for (const e of [v[0], v[v.length - 1]]) { const cap = new THREE.IcosahedronGeometry(radius * 1.02, 0); cap.translate(e.x, e.y, 0); parts.push(cap); }
  return parts;
}

const geomCache = {};
function frameGeometry() {
  return geomCache.frame || (geomCache.frame = mergeGeometries(tube([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], true, 0.068)));
}
function iconGeometry(i) {
  const key = 'icon' + i;
  if (!geomCache[key]) {
    const parts = [];
    for (const st of G.icons[i].strokes) parts.push(...tube(st.points.map(([x, y]) => [x * G.icon_scale, y * G.icon_scale]), st.closed, 0.056));
    geomCache[key] = mergeGeometries(parts);
  }
  return geomCache[key];
}
function dotGeometry() { return geomCache.dot || (geomCache.dot = new THREE.IcosahedronGeometry(G.dot_radius * 1.08, 0)); }

// ------------------------------------------------------------------ light
// the backdrop the glass refracts: the page colour at the edges, a soft prism of light in the middle
function backdrop(dark, base) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 640;
  const x = c.getContext('2d');
  x.fillStyle = base || (dark ? PAGE.dark : PAGE.light); x.fillRect(0, 0, c.width, c.height);
  const blob = (cx, cy, r, col, a) => {
    const g = x.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0, col.replace('A', a)); g.addColorStop(1, col.replace('A', 0));
    x.fillStyle = g; x.fillRect(0, 0, c.width, c.height);
  };
  const k = dark ? 0.4 : 0.3;
  blob(330, 260, 300, 'rgba(90,200,255,A)', k);
  blob(560, 380, 320, 'rgba(160,110,255,A)', k);
  blob(760, 250, 280, 'rgba(255,120,200,A)', k * 0.9);
  blob(520, 200, 220, 'rgba(255,210,120,A)', k * 0.7);
  // a beam of split light across the middle, soft on every side (no canvas filter: Safari lacks it)
  const b = document.createElement('canvas'); b.width = 900; b.height = 200;
  const bx = b.getContext('2d');
  const hues = [[255, 91, 127], [255, 162, 74], [255, 225, 90], [92, 242, 160], [76, 200, 255], [111, 123, 255], [193, 107, 255]];
  const across = bx.createLinearGradient(0, 0, 0, b.height);
  across.addColorStop(0, 'rgba(255,91,127,0)');
  hues.forEach(([r, g2, bl], i) => across.addColorStop(0.12 + 0.76 * i / (hues.length - 1), `rgba(${r},${g2},${bl},1)`));
  across.addColorStop(1, 'rgba(193,107,255,0)');
  bx.fillStyle = across; bx.fillRect(0, 0, b.width, b.height);
  bx.globalCompositeOperation = 'destination-in';
  const along = bx.createLinearGradient(0, 0, b.width, 0);
  along.addColorStop(0, 'rgba(0,0,0,0)'); along.addColorStop(0.35, 'rgba(0,0,0,1)'); along.addColorStop(0.65, 'rgba(0,0,0,1)'); along.addColorStop(1, 'rgba(0,0,0,0)');
  bx.fillStyle = along; bx.fillRect(0, 0, b.width, b.height);
  x.save(); x.translate(512, 330); x.rotate(-0.3); x.globalAlpha = dark ? 0.32 : 0.2;
  x.drawImage(b, -450, -100); x.restore();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// the sky the glass reflects: pearl, a spectral band low down, and three bright softboxes for the glints
function environment(renderer) {
  const env = new THREE.Scene();
  const sky = new THREE.Mesh(new THREE.SphereGeometry(10, 48, 24), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false,
    vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }',
    fragmentShader: `varying vec3 vP;
      vec3 spectrum(float h){ return clamp(abs(mod(h*6.+vec3(0.,4.,2.),6.)-3.)-1.,0.,1.); }
      void main(){
        float y = vP.y, a = atan(vP.z, vP.x) / 6.2831853;
        vec3 base = mix(vec3(.82,.84,.92), vec3(1.05,1.05,1.1), smoothstep(-.4,.9,y));
        float band = exp(-pow((y + .05) * 5., 2.));
        vec3 col = base + spectrum(fract(a * 2.)) * band * .9;
        gl_FragColor = vec4(col, 1.);
      }`,
  }));
  env.add(sky);
  const box = (w, h, pos, s) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color().setScalar(s), side: THREE.DoubleSide }));
    m.position.set(...pos); m.lookAt(0, 0, 0); env.add(m);
  };
  box(3, 1.2, [-4, 5, 3], 9);     // the sun: hot enough to bloom
  box(1.5, 4, [6, 1, -2], 3);
  box(4, 0.6, [0, -3, 6], 2.2);
  const pm = new THREE.PMREMGenerator(renderer);
  const tex = pm.fromScene(env, 0.015).texture;
  pm.dispose();
  return tex;
}

function glassMaterial() {
  return new THREE.MeshPhysicalMaterial({
    color: 0xffffff, metalness: 0, roughness: 0.03, transmission: 1, thickness: 0.7, ior: 1.8, dispersion: 9,
    iridescence: 0.85, iridescenceIOR: 1.32, iridescenceThicknessMinimum: 180, iridescenceThicknessMaximum: 720,
    clearcoat: 1, clearcoatRoughness: 0.02, specularIntensity: 1, envMapIntensity: 1.9,
    attenuationColor: new THREE.Color('#eef0ff'), attenuationDistance: 2.5, flatShading: true,
  });
}

// ------------------------------------------------------------------ sparkles: tiny four-point stars that twinkle near the glass
function sparkles(count, dark) {
  const pos = new Float32Array(count * 3), seed = new Float32Array(count), col = new Float32Array(count * 3);
  const hue = new THREE.Color();
  for (let i = 0; i < count; i++) {
    pos.set([(Math.random() - 0.5) * 2, (Math.random() - 0.5) * 2, (Math.random() - 0.3) * 0.8], i * 3);
    seed[i] = Math.random();
    hue.setHSL(Math.random(), 0.9, dark ? 0.75 : 0.55); col.set([hue.r, hue.g, hue.b], i * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
  g.setAttribute('tint', new THREE.BufferAttribute(col, 3));
  const m = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: dark ? THREE.AdditiveBlending : THREE.NormalBlending,
    uniforms: { uTime: { value: 0 }, uScale: { value: 1 }, uSize: { value: new THREE.Vector2(1, 1) } },
    vertexShader: `attribute float seed; attribute vec3 tint; uniform float uTime, uScale; uniform vec2 uSize; varying float vA; varying vec3 vC;
      void main(){
        vec3 p = position * vec3(uSize, 1.);
        p.y += sin(uTime * .3 + seed * 20.) * .05;
        vec4 mv = modelViewMatrix * vec4(p, 1.);
        float tw = pow(max(0., sin(uTime * (0.6 + seed) + seed * 40.)), 12.);
        vA = tw; vC = tint;
        gl_PointSize = (9. + seed * 15.) * tw * uScale * (6. / -mv.z);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `varying float vA; varying vec3 vC;
      void main(){
        vec2 c = gl_PointCoord * 2. - 1.;
        float s = max(0., 1. - abs(c.x) * 9.) * max(0., 1. - abs(c.y)) + max(0., 1. - abs(c.y) * 9.) * max(0., 1. - abs(c.x));
        float core = exp(-dot(c, c) * 18.);
        float a = clamp(s + core, 0., 1.) * vA;
        if (a < .01) discard;
        gl_FragColor = vec4(mix(vC, vec3(1.), core * .7), a);
      }`,
  });
  const p = new THREE.Points(g, m); p.frustumCulled = false;
  return p;
}

// ------------------------------------------------------------------ one canvas
function mount(canvas) {
  if (!G) return;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
  } catch (e) { canvas.closest('[data-crystal-host]')?.classList.add('no-3d'); return; }
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;   // the backdrop must come out exactly the page colour; glints clip to white and bloom
  const host = canvas.closest('[data-crystal-host]') || canvas.parentElement;
  host.classList.add('has-3d');

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);
  const material = glassMaterial();
  // single: one glyph laid exactly over an SVG whose viewBox is 1.8 units square (the byte builder)
  const single = canvas.dataset.crystals === 'single';
  const tabletQuery = matchMedia('(min-width: 720px) and (max-width: 999px)');
  let cycle = canvas.dataset.tablet === 'cycle' && tabletQuery.matches;   // one glyph that spins into the next
  let cycleIdx = 0, cycleK = -1, swapped = false;
  const baseFor = d => canvas.dataset.bg === 'solid' ? (d ? '#10121d' : '#ffffff') : null;   // --solid in style.css
  let dark = isDark();
  scene.background = backdrop(dark, baseFor(dark));
  scene.environment = environment(renderer);

  const sun = new THREE.DirectionalLight(0xffffff, 3.2); sun.position.set(-3, 4, 5); scene.add(sun);
  scene.add(new THREE.AmbientLight(0xffffff, 0.4));

  const world = new THREE.Group(); if (!single) world.rotation.set(-0.12, -0.22, 0.03); scene.add(world);
  const sparks = sparkles(single ? 14 : 40, dark); world.add(sparks);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), dark ? 0.6 : 0.38, 0.28, dark ? 0.9 : 1.0);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  // ---- glyphs
  let live = [], leaving = [], layout = { cols: 1, rows: 1 }, bytes = [], row = [];
  function makeGlyph(byte, i) {
    // each crystal a slightly different pale colour, so a row reads as a spectrum
    const mat = material.clone(), hue = single ? (byte >> 4) / 16 : (i / Math.max(1, bytes.length)) * 0.85 + 0.52;
    mat.attenuationColor = new THREE.Color().setHSL(hue % 1, 0.75, 0.82); mat.attenuationDistance = 0.9;
    const g = new THREE.Group();
    g.add(new THREE.Mesh(frameGeometry(), mat));
    g.add(new THREE.Mesh(iconGeometry(byte >> 4), mat));
    for (const [dx, dy, v] of CORNERS) if (byte & v) {
      const d = new THREE.Mesh(dotGeometry(), mat);
      d.position.set(dx * G.dot_offset, -dy * G.dot_offset, 0); d.rotation.set(Math.random() * 3, Math.random() * 3, 0); g.add(d);
    }
    g.userData = { mat, byte, phase: Math.random() * 6.28 + i, s: 0, target: 1, born: performance.now() / 1000 + i * 0.09, spin: single ? 0 : (Math.random() - 0.5) * 2.4 };
    g.scale.setScalar(0.001);
    world.add(g);
    return g;
  }
  function place() {
    const n = Math.max(1, live.length), w = host.clientWidth, h = host.clientHeight, aspect = w / Math.max(1, h);
    // the grid that lets the glyphs be biggest in this box
    let cols = n, best = 0;
    for (let c = 1; c <= n; c++) { const r = Math.ceil(n / c), s = Math.min(aspect / c, 1 / r); if (s > best + 1e-6) { best = s; cols = c; } }
    const rows = Math.ceil(n / cols), pitch = 1.42;
    layout = { cols, rows };
    live.forEach((g, i) => {
      const r = Math.floor(i / cols), c = i % cols, inRow = Math.min(cols, n - r * cols);
      g.userData.home = new THREE.Vector3((c - (inRow - 1) / 2) * pitch, ((rows - 1) / 2 - r) * pitch, 0);
    });
    // fit the camera to the arrangement, with room to float
    const bw = cols * pitch + 0.6, bh = rows * pitch + 0.6, vfov = THREE.MathUtils.degToRad(camera.fov);
    const distH = (bh / 2) / Math.tan(vfov / 2), distW = (bw / 2) / (Math.tan(vfov / 2) * aspect);
    camera.position.set(0, 0, single ? 0.9 / Math.tan(vfov / 2) : Math.max(distH, distW) * (cycle ? 0.95 : 1.32));
    camera.lookAt(0, 0, 0);
    sparks.material.uniforms.uSize.value.set(bw * 0.6, bh * 0.6);
  }
  function setBytes(next, force = false) {
    next = (next || []).slice(0, 16);
    if (!force && next.length === row.length && next.every((b, i) => b === row[i])) return;
    row = next; cycleIdx = 0;
    show(cycle ? row.slice(0, 1) : row);
  }
  // swap the glyph in place, mid-spin: no rise, no fade, the spin hides the change
  function swapTo(byte) {
    const old = live[0];
    if (old) { world.remove(old); old.userData.mat.dispose(); }
    bytes = [byte];
    const g = makeGlyph(byte, 0);
    g.userData.born = -1e9; g.userData.phase = old ? old.userData.phase : g.userData.phase; g.userData.home = old ? old.userData.home : undefined;
    live = [g];
  }
  function show(next) {
    bytes = next;
    for (const g of live) { if (single) { world.remove(g); g.userData.mat.dispose(); } else { g.userData.target = 0; leaving.push(g); } }
    live = bytes.map((b, i) => makeGlyph(b, i));
    place();
    kick();
  }

  // ---- size, visibility, pointer
  let visible = true, raf = 0, last = performance.now(), slow = 0, frames = 0;
  const pointer = new THREE.Vector2(), pointerTarget = new THREE.Vector2();
  function resize() {
    const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return;
    const dpr = Math.min(devicePixelRatio || 1, w < 700 ? 1.5 : 2) * (slow > 2 ? 0.7 : 1);
    renderer.setPixelRatio(dpr); renderer.setSize(w, h, false); composer.setPixelRatio(dpr); composer.setSize(w, h);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    sparks.material.uniforms.uScale.value = dpr * Math.min(1.2, h / 600);
    place(); kick();
  }
  new ResizeObserver(resize).observe(host);
  tabletQuery.addEventListener('change', () => {
    const c = canvas.dataset.tablet === 'cycle' && tabletQuery.matches;
    if (c !== cycle) { cycle = c; if (!c) bloom.strength = dark ? 0.6 : 0.38; setBytes(row, true); }
  });
  new IntersectionObserver(es => { visible = es[0].isIntersecting; kick(); }, { threshold: 0 }).observe(host);
  document.addEventListener('visibilitychange', kick);
  addEventListener('pointermove', e => {
    const r = host.getBoundingClientRect();
    pointerTarget.set(((e.clientX - r.left) / r.width - 0.5) * 2, ((e.clientY - r.top) / r.height - 0.5) * 2).clampScalar(-1.5, 1.5);
  }, { passive: true });
  const onTheme = () => { const d = isDark(); if (d === dark) return; dark = d; scene.background.dispose(); scene.background = backdrop(dark, baseFor(dark)); bloom.strength = dark ? 0.6 : 0.38; bloom.threshold = dark ? 0.9 : 1.0; sparks.material.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending; kick(); };
  darkQuery.addEventListener('change', onTheme);
  new MutationObserver(onTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  // ---- animation
  const ease = t => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);
  function frame(now) {
    raf = 0;
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    const still = reducedMotion.matches, t = still ? 0 : now / 1000;
    pointer.lerp(still ? pointer.set(0, 0) : pointerTarget, 0.05);
    let moving = !still;
    // cycle: hold for 2.3 s, then two full turns in 0.7 s; at the edge-on moment the glyph becomes the next byte
    let spin = 0, spinPulse = 0;
    if (cycle && !still && row.length > 1 && live.length) {
      const tt = now / 1000, k = Math.floor(tt / 3), p = tt - k * 3;
      if (k !== cycleK) { cycleK = k; swapped = false; }
      if (p > 2.3) {
        const s = Math.min(1, (p - 2.3) / 0.7), e = s < 0.5 ? 4 * s * s * s : 1 - Math.pow(-2 * s + 2, 3) / 2;
        spin = e * Math.PI * 4; spinPulse = Math.sin(Math.PI * s);
        if (!swapped && e >= 0.625) { swapped = true; cycleIdx = (cycleIdx + 1) % row.length; swapTo(row[cycleIdx]); }
      }
    }
    if (cycle) bloom.strength = (dark ? 0.6 : 0.38) + spinPulse * 0.9;
    live.forEach((g, i) => {
      const u = g.userData, age = now / 1000 - u.born;
      u.s = still ? 1 : single ? 0.82 + 0.18 * ease(age / 0.35) : ease(age / 0.9);
      if (u.s < 1) moving = true;
      g.scale.setScalar(Math.max(0.001, u.s * (1 - spinPulse * 0.1)));
      const home = u.home || new THREE.Vector3();
      const a = single ? 0.3 : 1;   // the builder's glyph floats less, so its dots stay under the corners you tap
      g.position.set(home.x, home.y + Math.sin(t * 0.8 + u.phase) * 0.07 * a - (single ? 0 : (1 - u.s) * 0.6), home.z + Math.sin(t * 0.55 + u.phase) * 0.12 * a);
      g.rotation.set((Math.sin(t * 0.5 + u.phase) * 0.14 - pointer.y * 0.28) * a, (Math.sin(t * 0.37 + u.phase * 1.3) * 0.22 + pointer.x * 0.4) * a + (1 - u.s) * u.spin + spin, Math.sin(t * 0.3 + u.phase) * 0.04 * a);
    });
    leaving = leaving.filter(g => {
      const s = g.scale.x * Math.pow(0.0008, dt * 2.2);
      g.scale.setScalar(s); g.rotation.y += dt * 4; g.position.y += dt * 0.8;
      if (s < 0.02) { world.remove(g); g.userData.mat.dispose(); return false; }
      moving = true; return true;
    });
    // the sun walks around the glass, so glints run along the edges and the rainbow inside shifts
    sun.position.set(Math.cos(t * 0.35) * 5, 3 + Math.sin(t * 0.5) * 1.5, 4 + Math.sin(t * 0.35) * 2);
    scene.environmentRotation.set(0, t * 0.18, Math.sin(t * 0.2) * 0.25);
    scene.backgroundRotation?.set(0, 0, 0);
    sparks.material.uniforms.uTime.value = t;
    composer.render(dt);
    // a device that cannot keep up gets fewer pixels and, after that, no bloom
    frames++;
    if (dt > 0.034 && frames > 30) { slow++; frames = 0; if (slow === 3) resize(); if (slow > 6) bloom.enabled = false; }
    if (moving && visible && document.visibilityState === 'visible') raf = requestAnimationFrame(frame);
  }
  function kick() { if (!raf && visible && document.visibilityState === 'visible') { last = performance.now(); raf = requestAnimationFrame(frame); } }

  resize();
  if (single) { setBytes(window.__gbBuilder || [0xe8]); document.addEventListener('gb:builder', e => setBytes(e.detail.bytes)); }
  else { setBytes(window.__gbBytes || [0xe8, 0xed, 0x37, 0x98, 0xc6, 0xff]); document.addEventListener('gb:bytes', e => setBytes(e.detail.bytes)); }
}

// start after the page has painted and gone idle: compiling the glass shaders can hold the main thread for a
// moment, and the drawn rows and text should never wait for the 3D
const start = () => document.querySelectorAll('canvas[data-crystals]').forEach(mount);
if ('requestIdleCallback' in window) requestIdleCallback(start, { timeout: 1200 }); else setTimeout(start, 200);
