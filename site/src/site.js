// glyphbyte.dev page script. Expects GLYPHS (spec/glyphs.json), inlined by site/build.py. Draws glyphs as SVG in the page's ink colour (currentColor), either clean
// like the reference renderer or with a steady hand-drawn wobble, and wires the interactive parts of the
// landing page: the hero row, the byte builder and the copy buttons. Every part is optional: a page
// without the element simply skips it.
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const hex2 = b => b.toString(16).padStart(2, '0');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const CORNERS = [[-1, -1, 8, 'top-left'], [1, -1, 4, 'top-right'], [1, 1, 2, 'bottom-right'], [-1, 1, 1, 'bottom-left']];

  function el(name, attrs = {}, parent) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  // small seeded generator, so a glyph wobbles the same way every time it is drawn
  function rng(seed) {
    let a = seed >>> 0;
    return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }

  // a polyline as SVG path data; with `hand`, resampled and pushed sideways by a slow, smooth wobble
  function pathData(points, closed, hand, rand, amp) {
    const pts = points.slice();
    if (closed) pts.push(points[0]);
    if (!hand) return 'M' + pts.map(p => p[0].toFixed(3) + ' ' + p[1].toFixed(3)).join('L') + (closed ? 'Z' : '');
    const out = [], f1 = 2 + rand() * 3, f2 = 5 + rand() * 4, p1 = rand() * 6.28, p2 = rand() * 6.28;
    let total = 0;
    const segs = [];
    for (let i = 1; i < pts.length; i++) { const [x0, y0] = pts[i - 1], [x1, y1] = pts[i]; const len = Math.hypot(x1 - x0, y1 - y0); segs.push([x0, y0, x1, y1, len]); total += len; }
    let run = 0;
    segs.forEach(([x0, y0, x1, y1, len], si) => {
      const n = Math.max(2, Math.ceil(len / 0.035)), nx = -(y1 - y0) / (len || 1), ny = (x1 - x0) / (len || 1);
      for (let k = si ? 1 : 0; k <= n; k++) {
        const t = k / n, s = (run + len * t) / (total || 1);
        const w = amp * (Math.sin(s * f1 * 6.28 + p1) * 0.7 + Math.sin(s * f2 * 6.28 + p2) * 0.3);
        out.push([x0 + (x1 - x0) * t + nx * w, y0 + (y1 - y0) * t + ny * w]);
      }
      run += len;
    });
    // a closed hand-drawn shape ends a little past where it started, the way a pen does
    if (closed && segs.length) { const [x0, y0, x1, y1, len] = segs[0], e = 0.025 / (len || 1); out.push([x0 + (x1 - x0) * e * 1.6, y0 + (y1 - y0) * e * 1.6]); }
    return 'M' + out.map(p => p[0].toFixed(3) + ' ' + p[1].toFixed(3)).join('L');
  }

  // one glyph centred on (cx, cy) in a cell of side 1 (scaled by the caller), appended to `g`.
  // opts: hand (bool), seed, draw (animation delay base in s, or null), lw, icon (override icon index),
  // dots (override 4-bit dot mask), frame (bool)
  function glyph(g, byte, opts = {}) {
    const G = GLYPHS, rand = rng((opts.seed || 1) * 7919 + byte * 31 + 3), hand = !!opts.hand, amp = hand ? 0.012 : 0;
    const icon = opts.icon != null ? opts.icon : byte >> 4, dots = opts.dots != null ? opts.dots : byte & 15;
    const lw = opts.lw || 0.05, cx = opts.cx || 0, cy = opts.cy || 0, d0 = opts.draw;
    const grp = el('g', { transform: `translate(${cx} ${cy})`, class: 'glyph' }, g);
    let step = 0;
    const stroke = (points, closed) => {
      const p = el('path', { d: pathData(points, closed, hand, rand, amp), fill: 'none', stroke: 'currentColor', 'stroke-width': lw, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', pathLength: 1 }, grp);
      if (d0 != null) { p.classList.add('ink'); p.style.setProperty('--d', (d0 + step++ * 0.12).toFixed(2) + 's'); }
      return p;
    };
    if (opts.frame !== false) {
      const j = () => hand ? (rand() - 0.5) * 0.03 : 0, h = 0.5;
      stroke([[-h + j(), -h + j()], [h + j(), -h + j()], [h + j(), h + j()], [-h + j(), h + j()]], true);
    }
    for (const st of G.icons[icon].strokes) stroke(st.points.map(([x, y]) => [x * G.icon_scale, y * G.icon_scale]), st.closed);
    CORNERS.forEach(([dx, dy, v]) => {
      if (!(dots & v)) return;
      const r = G.dot_radius * (hand ? 0.95 + rand() * 0.15 : 1);
      const c = el('circle', { cx: dx * G.dot_offset + (hand ? (rand() - 0.5) * 0.02 : 0), cy: dy * G.dot_offset + (hand ? (rand() - 0.5) * 0.02 : 0), r, fill: 'currentColor' }, grp);
      if (d0 != null) { c.classList.add('dot'); c.style.setProperty('--d', (d0 + step++ * 0.12).toFixed(2) + 's'); }
    });
    return grp;
  }

  // a whole row as the reference renderer lays it out: pitch 1.35, underline 0.72 below the centres,
  // fat start dot at its left end. Returns the <svg>.
  function row(svg, bytes, opts = {}) {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const n = bytes.length, pitch = 1.35, m = 0.42, labels = !!opts.labels;
    const W = m * 2 + pitch * (n - 1) + 1 + 0.5, top = -0.6, H = labels ? 1.85 : 1.55;
    svg.setAttribute('viewBox', `${-0.5 - m - 0.25} ${top} ${W} ${H}`);
    const g = el('g', {}, svg), stagger = opts.draw ? Math.min(0.32, 1.6 / Math.max(1, n)) : 0;
    bytes.forEach((b, i) => glyph(g, b, { cx: i * pitch, hand: opts.hand, seed: (opts.seed || 1) + i, draw: opts.draw ? i * stagger : null, lw: opts.lw }));
    if (opts.baseline !== false && n) {
      const y = 0.72, x0 = -0.5 - m * 0.75, x1 = (n - 1) * pitch + 0.5 + m * 0.75, rand = rng((opts.seed || 1) * 13 + n);
      const pts = []; for (let k = 0; k <= 12; k++) pts.push([x0 + (x1 - x0) * k / 12, y]);
      const line = el('path', { d: pathData(pts, false, opts.hand, rand, opts.hand ? 0.02 : 0), fill: 'none', stroke: 'currentColor', 'stroke-width': opts.lw || 0.05, 'stroke-linecap': 'round', pathLength: 1 }, g);
      const dot = el('circle', { cx: x0, cy: y, r: 0.13, fill: 'currentColor', class: 'start' }, g);
      if (opts.draw) { line.classList.add('ink', 'slow'); line.style.setProperty('--d', (n * stagger + 0.2).toFixed(2) + 's'); dot.classList.add('dot'); dot.style.setProperty('--d', (n * stagger + 0.1).toFixed(2) + 's'); }
    }
    if (labels) bytes.forEach((b, i) => {
      const t = el('text', { x: i * pitch, y: 1.16, 'text-anchor': 'middle', class: 'lbl' }, g);
      el('tspan', { class: 'hi' }, t).textContent = hex2(b)[0];
      el('tspan', { class: 'lo' }, t).textContent = hex2(b)[1];
    });
    svg.classList.remove('drawn'); void svg.getBoundingClientRect(); svg.classList.add('drawn');
    return svg;
  }

  // the name of a byte in words, as the reader says it
  function describe(b) {
    const name = GLYPHS.icons[b >> 4].name, on = CORNERS.filter(c => (b & 15) & c[2]).map(c => c[3]);
    return on.length ? `${name}, ${on.length === 1 ? 'dot' : 'dots'} ${on.join(', ')}` : `${name}, no dots`;
  }

  // ------------------------------------------------------------------ hero: a link goes to the reader; a real row floats
  // 5e357efdbca5: a cairn on relay.onosendai.tech and wheat.oslim.dev (published 2026-11-20) whose link is left for readers to find
  const hero = $('#heroRow');
  if (hero) {
    const bytes = [0x5e, 0x35, 0x7e, 0xfd, 0xbc, 0xa5];
    const render = animate => {
      row(hero, bytes, { hand: true, draw: animate && !reduced, seed: 5 });
      const fb = $('#heroFallback'); if (fb) row(fb, bytes, { lw: 0.06 });
      // the crystals (site/three/crystals.js) follow the same bytes
      window.__gbBytes = bytes;
      document.dispatchEvent(new CustomEvent('gb:bytes', { detail: { bytes } }));
    };
    // "Make my glyphs" makes them: the text goes to the reader through this tab's sessionStorage, and the
    // reader publishes it on arrival. Only this form can do that; a shared ?link= address only fills the box.
    $('#heroForm').addEventListener('submit', e => {
      e.preventDefault();
      const v = $('#heroLink').value.trim();
      let handed = false;
      if (v) try { sessionStorage.setItem('gb-make', JSON.stringify({ text: v.slice(0, 2000), at: Date.now() })); handed = true; } catch (err) { /* storage off */ }
      location.href = '/app/' + (v && !handed ? '?link=' + encodeURIComponent(v) : '') + '#make';
    });
    render(false);
    if (!reduced && 'IntersectionObserver' in window) {
      const io = new IntersectionObserver(es => { if (es[0].isIntersecting) { io.disconnect(); render(true); } }, { threshold: 0.3 });
      io.observe(hero);
    }
  }

  // ------------------------------------------------------------------ byte builder: pick an icon, tap corners
  const big = $('#builderGlyph');
  if (big) {
    let icon = 0xe, dots = 0x8;
    const out = { byte: $('#bByte'), bin: $('#bBin'), words: $('#bWords'), sum: $('#bSum'), name: $('#bName'), hi: $('#bHi') };
    const picker = $('#iconGrid');
    GLYPHS.icons.forEach((ic, i) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'icon-card'; b.dataset.i = i; b.setAttribute('aria-pressed', String(i === icon));
      b.setAttribute('aria-label', `${i.toString(16)}: ${ic.name}`);
      const s = el('svg', { viewBox: '-0.62 -0.62 1.24 1.24', 'aria-hidden': 'true' }, b);
      glyph(s, i << 4, { lw: 0.055 });
      b.insertAdjacentHTML('beforeend', `<span class="lab"><span class="hx">${i.toString(16)}</span><span class="nm">${ic.name}</span></span>`);
      b.addEventListener('click', () => { icon = i; update(true); });
      picker.appendChild(b);
    });
    const draw = (animate) => {
      while (big.firstChild) big.removeChild(big.firstChild);
      big.setAttribute('viewBox', '-0.9 -0.9 1.8 1.8');
      glyph(big, (icon << 4) | dots, { hand: false, lw: 0.04, draw: animate && !reduced ? 0 : null });
      // corner switches: a ring when off, the dot itself when on, and the value each corner adds
      CORNERS.forEach(([dx, dy, v, name]) => {
        const on = !!(dots & v), g = el('g', { class: 'corner' + (on ? ' on' : ''), tabindex: 0, role: 'switch', 'aria-checked': String(on), 'aria-label': `${name} dot, adds ${v}` }, big);
        const x = dx * GLYPHS.dot_offset, y = dy * GLYPHS.dot_offset;
        el('circle', { cx: x, cy: y, r: 0.15, class: 'hit' }, g);
        if (!on) el('circle', { cx: x, cy: y, r: GLYPHS.dot_radius, class: 'ghost' }, g);
        const t = el('text', { x: dx * 0.72, y: dy * 0.72 + 0.045, 'text-anchor': 'middle', class: 'cv' }, g); t.textContent = v;
        const toggle = () => { dots ^= v; update(false); const again = $$('.corner', big)[CORNERS.findIndex(c => c[2] === v)]; if (again) again.focus(); };
        g.addEventListener('click', toggle);
        g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      });
      big.classList.remove('drawn'); void big.getBoundingClientRect(); big.classList.add('drawn');
    };
    const update = (animate) => {
      const b = (icon << 4) | dots;
      draw(animate);
      $$('.icon-card', picker).forEach(c => c.setAttribute('aria-pressed', String(+c.dataset.i === icon)));
      out.byte.innerHTML = `<span class="hi">${hex2(b)[0]}</span><span class="lo">${hex2(b)[1]}</span>`;
      out.bin.innerHTML = `<span class="hi">${(b >> 4).toString(2).padStart(4, '0')}</span> <span class="lo">${(b & 15).toString(2).padStart(4, '0')}</span>`;
      out.name.textContent = GLYPHS.icons[icon].name;
      out.hi.textContent = icon.toString(16);
      const parts = CORNERS.filter(c => dots & c[2]).map(c => c[2]);
      out.sum.textContent = !parts.length ? '0, no dots' : parts.length === 1 ? String(dots) : `${parts.join(' + ')} = ${dots}` + (dots > 9 ? ` = ${dots.toString(16)}` : '');
      window.__gbBuilder = [b];
      document.dispatchEvent(new CustomEvent('gb:builder', { detail: { bytes: [b] } }));
      out.words.textContent = describe(b);
    };
    $('#bRandom') && $('#bRandom').addEventListener('click', () => { const a = new Uint8Array(1); crypto.getRandomValues(a); icon = a[0] >> 4; dots = a[0] & 15; update(true); });
    update(false);
  }

  // ------------------------------------------------------------------ static glyphs: <svg data-glyph="e8" data-hand ...>
  $$('svg[data-glyph]').forEach(s => {
    const b = parseInt(s.dataset.glyph, 16);
    if (!s.getAttribute('viewBox')) s.setAttribute('viewBox', '-0.62 -0.62 1.24 1.24');
    glyph(s, b, { hand: 'hand' in s.dataset, seed: +(s.dataset.seed || 1), lw: +(s.dataset.lw || 0.05) });
  });
  $$('svg[data-row]').forEach(s => {
    const h = s.dataset.row, bytes = []; for (let i = 0; i + 1 < h.length; i += 2) bytes.push(parseInt(h.slice(i, i + 2), 16));
    row(s, bytes, { hand: 'hand' in s.dataset, seed: +(s.dataset.seed || 1), labels: 'labels' in s.dataset, lw: +(s.dataset.lw || 0.05) });
  });
  // draw-on for marked rows when they scroll into view
  if (!reduced && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (!e.isIntersecting) return; io.unobserve(e.target);
      const s = e.target, h = s.dataset.row, bytes = []; for (let i = 0; i + 1 < h.length; i += 2) bytes.push(parseInt(h.slice(i, i + 2), 16));
      row(s, bytes, { hand: 'hand' in s.dataset, seed: +(s.dataset.seed || 1), labels: 'labels' in s.dataset, lw: +(s.dataset.lw || 0.05), draw: true });
    }), { threshold: 0.4 });
    $$('svg[data-row][data-animate]').forEach(s => io.observe(s));
  }

  // ------------------------------------------------------------------ drawing guide: a row with numbered marks
  const guide = $('#guideRow');
  if (guide) {
    const bytes = [0xe8, 0xa6, 0x37];
    row(guide, bytes, { hand: true, seed: 11, lw: 0.045 });
    guide.setAttribute('viewBox', '-1.25 -1.12 4.6 2.5');
    const g = el('g', {}, guide), off = GLYPHS.dot_offset;
    const mark = (n, mx, my, tx, ty) => {
      el('path', { d: `M${mx} ${my}L${tx} ${ty}`, class: 'lead-line' }, g);
      el('circle', { cx: tx, cy: ty, r: 0.025, fill: 'var(--accent)' }, g);
      const m = el('g', { class: 'mark' }, g);
      el('circle', { cx: mx, cy: my, r: 0.11 }, m);
      const t = el('text', { x: mx, y: my + 0.052, 'text-anchor': 'middle' }, m); t.textContent = n;
    };
    mark(1, -0.62, -0.92, -0.5, -0.5);            // the frame
    mark(2, 1.35, -0.92, 1.35, -0.22);            // the icon
    mark(3, 3.12, -0.92, 2.7 + off, -off);        // a corner dot
    mark(4, 0.675, -0.92, 0.675, 0);              // the gap
    mark(5, 2.1, 1.2, 2.1, 0.72);                 // the underline
    mark(6, -0.82, 1.2, -0.815, 0.72);            // the start dot
  }

  // ------------------------------------------------------------------ do and don't: <svg data-mistake="...">
  const MISTAKES = {
    'dots-ok': { byte: 0x1f },
    'dots-touch': { byte: 0x1f, dotOffset: 0.405 },
    'roof-ok': { byte: 0x00 },
    'roof-flat': { byte: 0x00, icon: [[-0.34, 0.42], [-0.34, -0.22], [0, -0.3], [0.34, -0.22], [0.34, 0.42]] },
    'start-ok': { row: [0x50, 0xd2], start: 0.13 },
    'start-thin': { row: [0x50, 0xd2], start: 0.035 },
  };
  $$('svg[data-mistake]').forEach(s => {
    const m = MISTAKES[s.dataset.mistake]; if (!m) return;
    if (m.row) {
      row(s, m.row, { hand: true, seed: 3, lw: 0.06 });
      const dot = s.querySelector('.start'); if (dot) dot.setAttribute('r', m.start);
      return;
    }
    s.setAttribute('viewBox', '-0.62 -0.62 1.24 1.24');
    const saved = { off: GLYPHS.dot_offset, icon: GLYPHS.icons[m.byte >> 4].strokes };
    if (m.dotOffset) GLYPHS.dot_offset = m.dotOffset;
    if (m.icon) GLYPHS.icons[m.byte >> 4].strokes = [{ points: m.icon, closed: true }];
    glyph(s, m.byte, { hand: true, seed: 2, lw: 0.06 });
    GLYPHS.dot_offset = saved.off; GLYPHS.icons[m.byte >> 4].strokes = saved.icon;
  });

  // ------------------------------------------------------------------ copy buttons and code tabs
  $$('[data-copy]').forEach(b => b.addEventListener('click', async () => {
    const src = $(b.dataset.copy), text = src ? src.textContent : '';
    try { await navigator.clipboard.writeText(text.trim()); b.classList.add('done'); setTimeout(() => b.classList.remove('done'), 1400); } catch (e) { /* the text stays selectable */ }
  }));
  $$('.tabs').forEach(tabs => {
    const btns = $$('[role=tab]', tabs);
    btns.forEach(b => b.addEventListener('click', () => {
      btns.forEach(x => { const on = x === b; x.setAttribute('aria-selected', String(on)); $('#' + x.getAttribute('aria-controls')).hidden = !on; });
    }));
  });

  // the nav gains a hairline once the page scrolls
  const top = $('.topbar');
  if (top) { const f = () => top.classList.toggle('scrolled', scrollY > 8); addEventListener('scroll', f, { passive: true }); f(); }
})();
