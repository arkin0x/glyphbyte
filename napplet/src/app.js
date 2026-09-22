// Page logic. Expects the globals MODEL (loaded weights) and SHAPES to exist; everything else is in this file's scope.
const $ = id => document.getElementById(id);
const hexClean = s => s.trim().replace(/[^0-9a-fA-F]/g, '').toLowerCase();
const toBytes = h => { const out = []; for (let i = 0; i + 1 < h.length; i += 2) out.push(parseInt(h.slice(i, i + 2), 16)); return out; };

function renderEncode() {
  const h = hexClean($('hex').value);
  if (h.length < 2) { $('row').hidden = true; $('describe').innerHTML = ''; return; }
  const bytes = toBytes(h);
  drawRow($('row'), SHAPES, bytes, 140); $('row').hidden = false;
  $('describe').innerHTML = bytes.map(b => `<li><code>${b.toString(16).padStart(2, '0')}</code> ${describe(b)}</li>`).join('');
}
let timer; $('hex').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(renderEncode, 200); });
$('sheetBtn').addEventListener('click', () => { const c = $('sheet'); drawSheet(c, SHAPES, 56); c.hidden = !c.hidden; });

$('file').addEventListener('change', async () => {
  const f = $('file').files[0]; if (!f) return;
  $('busy').hidden = false; $('result').innerHTML = '';
  try {
    let bmp;
    try { bmp = await createImageBitmap(f, { imageOrientation: 'from-image' }); } catch (e) { bmp = await createImageBitmap(f); }
    const m = Math.max(bmp.width, bmp.height), s = Math.min(1, 1600 / m);
    const cv = $('photo'); cv.width = Math.round(bmp.width * s); cv.height = Math.round(bmp.height * s);
    const ctx = cv.getContext('2d'); ctx.drawImage(bmp, 0, 0, cv.width, cv.height);
    const img = ctx.getImageData(0, 0, cv.width, cv.height);
    await new Promise(r => setTimeout(r, 20));
    const t0 = performance.now();
    const res = readImage(toGray(img.data, cv.width, cv.height), cv.width, cv.height, MODEL);
    show(res, Math.round(performance.now() - t0));
    drawDetection(ctx, res.detection); cv.hidden = false;
  } catch (e) { $('result').innerHTML = `<p class="warn">could not read that image: ${e}</p>`; }
  $('busy').hidden = true;
});

function show(d, ms) {
  let h = '';
  if (!d.sequences.length) h += `<p class="warn">no symbols found</p>`;
  else {
    h += `<p>Most likely: <code class="big">${d.best}</code> <span class="muted">${ms} ms</span></p>`;
    if (d.sequences.length > 1) h += `<p class="muted">Not sure about some symbols. Pick the reading that matches what you see, or query all of them:</p>`;
    h += `<div class="seq">` + d.sequences.map(s => `<button data-hex="${s.hex}">${s.hex} <span class="muted">${Math.round(s.p * 100)}%</span></button>`).join('') + `</div>`;
    h += `<ol class="symbols">` + d.reads.map(r => { const alts = r.candidates.slice(1).map(([b, p]) => `${describe(b)} (${Math.round(p * 100)}%)`).join('; ');
      return `<li><code>${r.byte.toString(16).padStart(2, '0')}</code> ${describe(r.byte)} <span class="muted">${Math.round(r.p * 100)}%</span>${alts ? `<div class="alts">or ${alts}</div>` : ''}</li>`; }).join('') + `</ol>`;
  }
  h += d.warnings.map(w => `<p class="warn">${w}</p>`).join('');
  $('result').innerHTML = h;
  if (d.sequences.length) runLookup(d.sequences.map(s => s.hex));
  for (const b of $('result').querySelectorAll('button[data-hex]')) b.addEventListener('click', () => { $('hex').value = b.dataset.hex; renderEncode(); b.textContent = b.dataset.hex + ' ✓'; window.scrollTo({ top: 0, behavior: 'smooth' }); });
}


// ---------------------------------------------------------------- relay lookup
let lastCandidates = [];
const nappletRelay = () => (typeof window !== 'undefined' && window.napplet && window.napplet.relay) ? window.napplet.relay : null;
$('lookupHexBtn').addEventListener('click', () => { const h = hexClean($('hex').value); if (h.length >= 2) runLookup([h]); });
async function runLookup(candidates) {
  lastCandidates = candidates;
  const box = $('lookup'); box.innerHTML = `<p class="muted">asking ${$('relay').value.trim()}…</p>`;
  const r = await lookup(candidates, { relay: $('relay').value.trim(), nappletRelay: nappletRelay() });
  if (lastCandidates !== candidates) return;   // a newer lookup superseded this one
  let h = '';
  if (r.error) h += `<p class="warn">${r.error}${r.via === 'websocket' ? ' (in a napplet shell the relay must be reached through the shell)' : ''}</p>`;
  for (const n of r.notices) h += `<p class="warn">relay: ${n}</p>`;
  if (!r.events.length) h += `<p class="muted">nothing matched ${candidates.length} candidate${candidates.length > 1 ? 's' : ''}.</p>`;
  const profiles = r.events.filter(e => e.kind === 0).sort((a, b) => b.created_at - a.created_at), others = r.events.filter(e => e.kind !== 0).sort((a, b) => b.created_at - a.created_at);
  const seenPk = new Set();
  for (const ev of profiles) {
    if (seenPk.has(ev.pubkey)) continue; seenPk.add(ev.pubkey);
    let c = {}; try { c = JSON.parse(ev.content || '{}'); } catch (e) { /* ignore */ }
    const m = matchPrefix(ev, candidates);
    h += `<div class="card">${c.picture ? `<img src="${String(c.picture).replace(/"/g, '')}" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">` : '<div style="width:56px;height:56px"></div>'}<div><div class="who">${esc(c.display_name || c.name || '(no name)')}</div>${c.nip05 ? `<div class="muted">${esc(c.nip05)}</div>` : ''}<div class="muted"><code>${ev.pubkey.slice(0, 16)}…</code></div>${m ? `<div class="hit">matches ${m.prefix} by ${m.how}</div>` : ''}</div></div>`;
  }
  for (const ev of others.slice(0, 20)) {
    const m = matchPrefix(ev, candidates);
    h += `<div class="card"><div><div>kind ${ev.kind} <span class="muted">${new Date(ev.created_at * 1000).toLocaleString()}</span></div><div class="muted"><code>${ev.id.slice(0, 16)}…</code> by <code>${ev.pubkey.slice(0, 12)}…</code></div><div>${esc(String(ev.content || '').slice(0, 160))}</div>${m ? `<div class="hit">matches ${m.prefix} by ${m.how}</div>` : ''}</div></div>`;
  }
  h += `<p class="muted">via ${r.via}, ${r.events.length} event${r.events.length === 1 ? '' : 's'}</p>`;
  box.innerHTML = h;
}
function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
