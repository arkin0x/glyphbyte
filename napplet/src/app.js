// Page logic. Expects the globals MODEL (loaded weights) and SHAPES to exist; everything else is in this file's scope.
const $ = id => document.getElementById(id);
const hexClean = s => s.trim().replace(/[^0-9a-fA-F]/g, '').toLowerCase();
const toBytes = h => { const out = []; for (let i = 0; i + 1 < h.length; i += 2) out.push(parseInt(h.slice(i, i + 2), 16)); return out; };

// what the box holds: raw hex, or a NIP-19 entity (npub, note, nevent, nprofile, naddr), optionally nostr:-prefixed
function parseEntry(raw) {
  const v = raw.trim().replace(/^nostr:/i, '');
  if (/^(npub|note|nevent|nprofile|naddr)1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]+$/i.test(v)) {
    try { const d = decodeEntity(v); return { hex: d.hex, entity: d }; } catch (e) { return { hex: '', entity: null, error: `${v.slice(0, 6)}…: ${e.message}` }; }
  }
  return { hex: hexClean(v), entity: null };
}
function nBytes() { const r = document.querySelector('input[name=nbytes]:checked'); return r ? +r.value : 6; }
function currentPrefix() {
  const { hex } = parseEntry($('hex').value); const n = nBytes();
  return n ? hex.slice(0, 2 * n) : hex;
}
function renderEncode() {
  const { hex, entity, error } = parseEntry($('hex').value); const n = nBytes(), h = n ? hex.slice(0, 2 * n) : hex;
  const note = $('entity');
  if (error) { note.className = 'warn'; note.textContent = error; }
  else if (entity) {
    const what = entity.type === 'npub' || entity.type === 'nprofile' ? 'pubkey' : entity.type === 'naddr' ? "author's pubkey (an naddr has no event id)" : 'event id';
    note.className = 'muted';
    note.innerHTML = `${entity.type}: ${what} <code>${esc(hex.slice(0, 16))}…</code>, drawing the first ${h.length / 2} bytes` + (entity.relays.length ? ` · relay hint <button id="useHint" data-relay="${esc(entity.relays[0])}">${esc(entity.relays[0])}</button>` : '');
    const b = $('useHint'); if (b) b.addEventListener('click', () => { $('relay').value = b.dataset.relay; $('relay').dispatchEvent(new Event('input')); });
  } else { note.className = 'muted'; note.textContent = hex.length > 2 * n && n ? `drawing the first ${n} of ${hex.length / 2} bytes` : ''; }
  if (h.length < 2) { $('row').hidden = true; $('describe').innerHTML = ''; return; }
  const bytes = toBytes(h);
  drawRow($('row'), SHAPES, bytes, 140); $('row').hidden = false;
  $('describe').innerHTML = bytes.map(b => `<li><code>${b.toString(16).padStart(2, '0')}</code> ${describe(b)}</li>`).join('');
}
let timer; $('hex').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(renderEncode, 200); });
$('sheetBtn').addEventListener('click', () => { const c = $('sheet'); drawSheet(c, SHAPES, 56); c.hidden = !c.hidden; });

$('file').addEventListener('change', () => readFile($('file').files[0]));   // no capture attribute: the phone offers camera and library together
async function readFile(f) {
  if (!f) return;
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
}

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
let lastCandidates = [], profiles = {};
const nappletRelay = () => (typeof window !== 'undefined' && window.napplet && window.napplet.relay) ? window.napplet.relay : null;
const relayUrl = () => $('relay').value.trim();
$('lookupHexBtn').addEventListener('click', () => { const h = currentPrefix(); if (h.length >= 2) runLookup([h]); });
for (const r of document.querySelectorAll('input[name=nbytes]')) r.addEventListener('change', renderEncode);

function placeRelaySection(hasResult) {
  const sec = $('relaySection'), first = document.querySelector('main section');
  if (hasResult) { if (first.nextElementSibling !== sec) first.after(sec); }
  else document.querySelector('main').insertBefore(sec, document.querySelector('main > p.muted'));
}

async function runLookup(candidates) {
  lastCandidates = candidates;
  const box = $('lookup'); box.innerHTML = `<p class="muted">asking ${esc(relayUrl())}…</p>`;
  const opts = { relay: relayUrl(), nappletRelay: nappletRelay() };
  const r = await lookup(candidates, opts);
  if (lastCandidates !== candidates) return;
  const authors = Array.from(new Set(r.events.map(e => e.pubkey)));
  for (const ev of r.events) if (ev.kind === 0 && (!profiles[ev.pubkey] || profiles[ev.pubkey].created_at < ev.created_at)) profiles[ev.pubkey] = ev;
  const missing = authors.filter(pk => !profiles[pk]);
  if (missing.length) Object.assign(profiles, await fetchProfiles(missing, opts));
  if (lastCandidates !== candidates) return;
  let h = '';
  if (r.error) h += `<p class="warn">${esc(r.error)}${r.via === 'websocket' ? ' (inside a napplet shell the relay is reached through the shell)' : ''}</p>`;
  for (const n of r.notices) h += `<p class="warn">relay: ${esc(n)}</p>`;
  if (!r.events.length) h += `<p class="muted">nothing matched ${candidates.length} candidate${candidates.length > 1 ? 's' : ''}.</p>`;
  const seenPk = new Set(), items = [];
  for (const ev of r.events.filter(e => e.kind === 0).sort((a, b) => b.created_at - a.created_at)) { if (!seenPk.has(ev.pubkey)) { seenPk.add(ev.pubkey); items.push(ev); } }
  for (const ev of r.events.filter(e => e.kind !== 0).sort((a, b) => b.created_at - a.created_at).slice(0, 30)) items.push(ev);
  h += items.map((ev, i) => eventCard(ev, i, candidates)).join('');
  h += `<p class="muted">via ${r.via}, ${r.events.length} event${r.events.length === 1 ? '' : 's'}</p>`;
  box.innerHTML = h;
  window.__events = items;
  placeRelaySection(items.length > 0);
  if (items.length) $('relaySection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function profileOf(pk) { const ev = profiles[pk]; if (!ev) return {}; try { return JSON.parse(ev.content || '{}'); } catch (e) { return {}; } }
function eventCard(ev, i, candidates) {
  const pr = profileOf(ev.pubkey), m = matchPrefix(ev, candidates), when = new Date(ev.created_at * 1000).toLocaleString();
  const name = pr.display_name || pr.name || ev.pubkey.slice(0, 12) + '…';
  const pic = pr.picture ? `<img src="${esc(String(pr.picture))}" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">` : `<div style="width:44px;height:44px;border-radius:50%;background:var(--card);flex:none"></div>`;
  const body = ev.kind === 0 ? `<span class="sub">${esc(pr.about || '')}</span>` : esc(String(ev.content || '').slice(0, 400));
  return `<div class="ev" data-i="${i}">
    <div class="head">${pic}<div><div class="name">${esc(name)}</div><div class="sub">${pr.nip05 ? esc(pr.nip05) + ' · ' : ''}${when}</div></div></div>
    <button class="dots" data-menu="${i}" aria-label="more">⋯</button>
    <div class="body"><span class="kind">kind ${ev.kind}${ev.kind === 0 ? ' profile' : ''}</span>${body}</div>
    ${m ? `<div class="ok" style="font-size:13px">matches <code>${m.prefix}</code> by ${m.how}</div>` : ''}
  </div>`;
}

document.addEventListener('click', e => {
  const open = document.querySelector('.ev .menu'); if (open && !open.contains(e.target)) open.remove();
  const b = e.target.closest('button[data-menu]'); if (!b) return;
  const ev = window.__events[+b.dataset.menu], card = b.closest('.ev'), d = dTag(ev), relays = [relayUrl()];
  const menu = document.createElement('div'); menu.className = 'menu';
  const items = [
    ['copy event id', () => copyText(ev.id)],
    ['copy nevent (with relay hint)', () => copyText(nevent(ev.id, { relays, author: ev.pubkey, kind: ev.kind }))],
    isAddressable(ev.kind) ? ['copy naddr (with relay hint)', () => copyText(naddr(ev.kind, ev.pubkey, d, { relays }))] : null,
    ['copy pubkey (hex)', () => copyText(ev.pubkey)],
    ['copy npub', () => copyText(npub(ev.pubkey))],
    ['copy content', () => copyText(ev.content || '')],
    ['copy raw event', () => copyText(JSON.stringify(ev))],
    ['view raw event', () => showModal(`kind ${ev.kind} · ${ev.id.slice(0, 16)}…`, JSON.stringify(ev, null, 2))],
  ].filter(Boolean);
  for (const [label, fn] of items) { const bt = document.createElement('button'); bt.textContent = label; bt.addEventListener('click', ev2 => { ev2.stopPropagation(); menu.remove(); fn(); }); menu.appendChild(bt); }
  card.appendChild(menu); e.stopPropagation();
});
function dTag(ev) { const t = (ev.tags || []).find(t => t[0] === 'd'); return t ? (t[1] || '') : ''; }
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast('copied'); }
  catch (e) { showModal('copy this', text); }
}
function toast(msg) { const t = document.createElement('div'); t.textContent = msg; t.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:8px 14px;border-radius:8px;z-index:30;font-size:14px'; document.body.appendChild(t); setTimeout(() => t.remove(), 1200); }
function showModal(title, body) { $('modalTitle').textContent = title; $('modalBody').textContent = body; $('modal').hidden = false; }
$('modalClose').addEventListener('click', () => { $('modal').hidden = true; });
$('modal').addEventListener('click', e => { if (e.target === $('modal')) $('modal').hidden = true; });

// ---------------------------------------------------------------- relay capability probe
let probeTimer, probeSeq = 0;
async function probe() {
  const url = relayUrl(), seq = ++probeSeq, st = $('relayStatus');
  if (!/^wss?:\/\//.test(url)) { st.textContent = ''; return; }
  st.className = 'muted'; st.textContent = 'checking partial-id support…';
  const r = await probeRelay(url, { nappletRelay: nappletRelay() });
  if (seq !== probeSeq) return;
  if (r.ok) { st.className = 'ok'; st.textContent = 'partial ids and pubkeys: supported'; }
  else if (r.ids === 'rejected' || r.authors === 'rejected') { st.className = 'bad'; st.textContent = `this relay rejects partial queries${r.detail ? ': ' + r.detail.replace(/^CLOSED: /, '') : ''}`; }
  else if (r.ids === 'ignored' || r.authors === 'ignored') { st.className = 'bad'; st.textContent = 'this relay ignores partial queries (exact matches only); try wss://wheat.oslim.dev'; }
  else { st.className = 'warn'; st.textContent = `could not test: ${r.detail}`; }
}
$('relay').addEventListener('input', () => { clearTimeout(probeTimer); probeTimer = setTimeout(probe, 700); });
probe();
function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
