// Page logic. Expects the globals MODELS ({1, 2}: loaded weights), SHAPES and SHAPES_V1; everything else is in this file's scope.
const $ = id => document.getElementById(id);
// site links (the wordmark, the footer's spec link) point into glyphbyte.dev; inside a nostr shell (a frame) "/" would be the shell's own site
if (window.top !== window) for (const a of document.querySelectorAll('a[href^="/"]')) a.removeAttribute('href');   // wordmark, footer
const hexClean = s => s.trim().replace(/[^0-9a-fA-F]/g, '').toLowerCase();
const toBytes = h => { const out = []; for (let i = 0; i + 1 < h.length; i += 2) out.push(parseInt(h.slice(i, i + 2), 16)); return out; };

// three tools on tabs: read (default), draw, publish. The hash names the tool, so glyphbyte.dev/app/#publish
// opens straight onto publishing. The matches below the tools are shared by all three.
const TABS = { read: 'readSection', make: 'cairnSection', draw: 'bytesSection' };
function showTab(name, scroll = true) {
  if (name === 'publish') name = 'make';   // the tab's first name
  if (!TABS[name]) name = 'read';
  for (const [k, id] of Object.entries(TABS)) { $(id).hidden = k !== name; $('tab-' + k).setAttribute('aria-selected', String(k === name)); }
  try { if (location.hash.slice(1) !== name) history.replaceState(null, '', '#' + name); } catch (e) { /* a sandboxed frame may refuse; the tab still shows */ }
  if (scroll) window.scrollTo({ top: 0, behavior: 'smooth' });
}
for (const k of Object.keys(TABS)) $('tab-' + k).addEventListener('click', () => showTab(k));
addEventListener('hashchange', () => showTab(location.hash.slice(1), false));
showTab(location.hash.slice(1), false);
// glyphbyte.dev links here with ?link=...: the link waits in Make, never published until the person says so
try { const l = new URLSearchParams(location.search).get('link'); if (l) { $('cairnText').value = l.slice(0, 2000); showTab('make', false); } } catch (e) { /* no query in a shell */ }

// what the box holds: raw hex, or a NIP-19 entity (npub, note, nevent, nprofile, naddr), optionally nostr:-prefixed
function parseEntry(raw) {
  const v = raw.trim().replace(/^nostr:/i, '');
  if (/^(npub|note|nevent|nprofile|naddr)1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]+$/i.test(v)) {
    try { const d = decodeEntity(v); return { hex: d.hex, entity: d }; } catch (e) { return { hex: '', entity: null, error: `${v.slice(0, 6)}…: ${e.message}` }; }
  }
  return { hex: hexClean(v), entity: null };
}
function drawFormat() { const r = document.querySelector('input[name=fmt]:checked'); return r ? +r.value : 2; }
const shapesFor = fmt => fmt === 1 ? SHAPES_V1 : SHAPES;
const HINTS = {
  2: 'Draw a square frame, the icon upright and small in the middle, and the corner dots so they touch nothing. Underline the row and put a fat dot at the start of the underline, about a quarter of a frame across.',
  1: 'Format v1: draw each pictogram rotated as shown inside its square or circle frame, filled ones scribbled solid. Underline the row and put a fat dot at the start of the underline. The reader still reads v1; v2 is easier to draw.',
};
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
  const bytes = toBytes(h), fmt = drawFormat();
  drawRow($('row'), shapesFor(fmt), bytes, 140); $('row').hidden = false;
  $('describe').innerHTML = bytes.map(b => `<li><code>${b.toString(16).padStart(2, '0')}</code> ${describe(b, fmt)}</li>`).join('');
}
let timer; $('hex').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(renderEncode, 200); });
$('sheetBtn').addEventListener('click', () => { const c = $('sheet'); drawSheet(c, shapesFor(drawFormat()), 56); c.hidden = !c.hidden; });
for (const r of document.querySelectorAll('input[name=fmt]')) r.addEventListener('change', () => {
  $('drawHint').textContent = HINTS[drawFormat()]; renderEncode();
  if (!$('sheet').hidden) drawSheet($('sheet'), shapesFor(drawFormat()), 56);
});

// Photo: one button. On a touch device it opens a small menu, because some phone browsers (Brave on
// Android) offer only files for a plain image picker; "take a photo" asks for the camera explicitly.
// With a mouse there is no camera to offer, so the button opens the file dialog directly.
const closePhotoMenu = () => { $('photoMenu').hidden = true; $('photoBtn').setAttribute('aria-expanded', 'false'); };
$('photoBtn').addEventListener('click', () => {
  if (!matchMedia('(pointer: coarse)').matches) { $('file').click(); return; }
  const m = $('photoMenu'); m.hidden = !m.hidden; $('photoBtn').setAttribute('aria-expanded', String(!m.hidden));
});
document.addEventListener('click', e => { if (!e.target.closest('.picker')) closePhotoMenu(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePhotoMenu(); });
for (const id of ['file', 'fileCam']) $(id).addEventListener('change', () => { closePhotoMenu(); const f = $(id).files[0]; $(id).value = ''; readFile(f); });
// on a computer: drop an image on the zone, or paste one from the clipboard anywhere on the page
if (!matchMedia('(pointer: coarse)').matches) $('dropHint').textContent = 'Click to choose, or drop or paste an image here.';
for (const t of ['dragenter', 'dragover']) $('photoBtn').addEventListener(t, e => { e.preventDefault(); $('photoBtn').classList.add('over'); });
for (const t of ['dragleave', 'drop']) $('photoBtn').addEventListener(t, () => $('photoBtn').classList.remove('over'));
$('photoBtn').addEventListener('drop', e => { e.preventDefault(); const f = Array.from(e.dataTransfer.files || []).find(x => /^image\//.test(x.type)); if (f) readFile(f); });
document.addEventListener('paste', e => {
  if (e.target.closest && e.target.closest('textarea, input')) return;
  const f = Array.from((e.clipboardData && e.clipboardData.files) || []).find(x => /^image\//.test(x.type));
  if (f) { e.preventDefault(); showTab('read'); readFile(f); }
});
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
    const res = readImage(toGray(img.data, cv.width, cv.height), cv.width, cv.height, MODELS, { rgba: img.data });
    show(res, Math.round(performance.now() - t0));
    drawDetection(ctx, res.detection); cv.hidden = false;
  } catch (e) { $('result').innerHTML = `<p class="warn">could not read that image: ${e}</p>`; }
  $('busy').hidden = true;
}

function show(d, ms) {
  let h = '';
  if (!d.sequences.length) h += `<p class="warn">no glyphs found</p>`;
  else {
    h += `<div class="best"><div class="k">Most likely</div><div class="v"><code class="big">${d.best}</code><span class="muted">${d.format === 1 ? 'format v1 · ' : ''}read in ${ms} ms</span></div><canvas id="bestRow" class="render glyphs"></canvas></div>`;
    if (d.sequences.length > 1) h += `<p class="muted">Not sure about some glyphs. Pick the reading that matches what you see, or query all of them:</p>`;
    h += `<div class="seq">` + d.sequences.map(s => `<button data-hex="${s.hex}" data-fmt="${s.format}" title="draw this reading">${s.hex} <span class="muted">${Math.round(s.p * 100)}%${s.format !== d.format ? ' v' + s.format : ''}</span></button>`).join('') + `</div>`;
    h += `<ol class="symbols">` + d.reads.map(r => { const alts = r.candidates.slice(1).map(([b, p]) => `${describe(b, d.format)} (${Math.round(p * 100)}%)`).join('; ');
      return `<li><code>${r.byte.toString(16).padStart(2, '0')}</code> ${describe(r.byte, d.format)} <span class="muted">${Math.round(r.p * 100)}%</span>${alts ? `<div class="alts">or ${alts}</div>` : ''}</li>`; }).join('') + `</ol>`;
  }
  h += d.warnings.map(w => `<p class="warn">${w}</p>`).join('');
  $('result').innerHTML = h;
  if (d.sequences.length) { drawRow($('bestRow'), shapesFor(d.format), toBytes(d.best), 110); runLookup(d.sequences.map(s => s.hex)); }
  // tapping a reading shows it drawn, in the format it was read in
  for (const b of $('result').querySelectorAll('button[data-hex]')) b.addEventListener('click', () => {
    $('hex').value = b.dataset.hex; const fr = document.querySelector(`input[name=fmt][value="${b.dataset.fmt}"]`); if (fr) fr.checked = true;
    $('drawHint').textContent = HINTS[drawFormat()]; renderEncode();
    for (const o of $('result').querySelectorAll('button[data-hex]')) o.classList.toggle('picked', o === b);
    showTab('draw');
  });
}


// ---------------------------------------------------------------- relay lookup
let lastCandidates = [], profiles = {};
const nappletRelay = () => (typeof window !== 'undefined' && window.napplet && window.napplet.relay) ? window.napplet.relay : null;
const relayUrl = () => $('relay').value.trim();
$('lookupHexBtn').addEventListener('click', () => { const h = currentPrefix(); if (h.length >= 2) runLookup([h]); });
for (const r of document.querySelectorAll('input[name=nbytes]')) r.addEventListener('change', renderEncode);


async function runLookup(candidates) {
  lastCandidates = candidates;
  const box = $('lookup'); box.innerHTML = `<p class="muted"><span class="spin" style="display:inline-block;vertical-align:-3px;margin-right:8px"></span>Looking it up…</p>`;
  const opts = { relay: relayUrl(), nappletRelay: nappletRelay() };
  // the relay in the box, plus the others glyphbyte has published to, all at once; results merged by id
  const relays = Array.from(new Set([relayUrl(), ...LOOKUP_RELAYS]));
  const all = await Promise.all(relays.map(u => lookup(candidates, { ...opts, relay: u })));
  const seenId = new Set(), r = { events: [], notices: [], error: all.every(x => x.error) ? all[0].error : undefined, via: all[0].via };
  for (const x of all) { for (const ev of x.events) if (!seenId.has(ev.id)) { seenId.add(ev.id); r.events.push(ev); } }
  // grain answers every prefix query with the same notice; it says nothing a reader needs
  r.notices = all[0].notices.filter(n => !/matched as prefixes/.test(n));
  if (lastCandidates !== candidates) return;
  const authors = Array.from(new Set(r.events.map(e => e.pubkey)));
  for (const ev of r.events) if (ev.kind === 0 && (!profiles[ev.pubkey] || profiles[ev.pubkey].created_at < ev.created_at)) profiles[ev.pubkey] = ev;
  const missing = authors.filter(pk => !profiles[pk]);
  if (missing.length) Object.assign(profiles, await fetchProfiles(missing, opts));
  if (lastCandidates !== candidates) return;
  let h = '';
  if (r.error) h += `<p class="warn">Could not reach the lookup server: ${esc(r.error)}</p>`;
  for (const n of r.notices) h += `<p class="warn">server: ${esc(n)}</p>`;
  if (!r.events.length && !r.error) h += `<p class="muted">Nothing found for ${candidates.length > 1 ? `any of the ${candidates.length} readings` : 'that row'}. Check the glyphs, or try another photo.</p>`;
  const seenPk = new Set(), items = [];
  for (const ev of r.events.filter(e => e.kind === CAIRN_KIND).sort((a, b) => b.created_at - a.created_at)) items.push(ev);
  for (const ev of r.events.filter(e => e.kind === 0).sort((a, b) => b.created_at - a.created_at)) { if (!seenPk.has(ev.pubkey)) { seenPk.add(ev.pubkey); items.push(ev); } }
  for (const ev of r.events.filter(e => e.kind !== 0 && e.kind !== CAIRN_KIND).sort((a, b) => b.created_at - a.created_at).slice(0, 30)) items.push(ev);
  h += items.map((ev, i) => eventCard(ev, i, candidates)).join('');
  if (r.events.length) h += `<p class="muted">${r.events.length} match${r.events.length === 1 ? '' : 'es'} from ${relays.length} server${relays.length === 1 ? '' : 's'}</p>`;
  box.innerHTML = h;
  window.__events = items;
  if (items.length) $('relaySection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function profileOf(pk) { const ev = profiles[pk]; if (!ev) return {}; try { return JSON.parse(ev.content || '{}'); } catch (e) { return {}; } }
// a cairn shows as the link it carries: the website first, the full link, and a button. Never opened by itself.
function linkCard(ev, i, candidates, url) {
  const m = matchPrefix(ev, candidates), note = String(ev.content || '').split(/\s+/).filter(t => t !== url).join(' ').trim();
  return `<div class="ev link" data-i="${i}">
    <button class="dots" data-menu="${i}" aria-label="more"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></button>
    <div class="k">This row opens</div>
    <div class="host">${esc(hostOf(url))}</div>
    <div class="url">${esc(url)}</div>
    ${note ? `<div class="body">${esc(note.slice(0, 280))}</div>` : ''}
    <div class="row" style="margin-bottom:0"><a class="open" href="${esc(url)}" target="_blank" rel="noopener noreferrer nofollow">Open ${esc(hostOf(url))}</a>${m ? `<span class="muted">matches <code>${m.prefix}</code></span>` : ''}</div>
  </div>`;
}
// a text cairn shows its text, as plain text: it has no destination
function textCard(ev, i, candidates, text) {
  const m = matchPrefix(ev, candidates);
  return `<div class="ev link" data-i="${i}">
    <button class="dots" data-menu="${i}" aria-label="more"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></button>
    <div class="k">This row says</div>
    <div class="said">${esc(text.slice(0, 2000))}</div>
    <div class="row" style="margin-bottom:0"><button data-copytext="${i}">Copy the text</button>${m ? `<span class="muted">matches <code>${m.prefix}</code></span>` : ''}</div>
  </div>`;
}
document.addEventListener('click', e => { const b = e.target.closest('button[data-copytext]'); if (b) copyText(window.__events[+b.dataset.copytext].content || ''); });
function eventCard(ev, i, candidates) {
  if (ev.kind === CAIRN_KIND) { const v = validateCairn(ev); if (v.ok) return v.url ? linkCard(ev, i, candidates, v.url) : textCard(ev, i, candidates, v.text); }
  const pr = profileOf(ev.pubkey), m = matchPrefix(ev, candidates), when = new Date(ev.created_at * 1000).toLocaleString();
  const name = pr.display_name || pr.name || ev.pubkey.slice(0, 12) + '…';
  const pic = pr.picture ? `<img src="${esc(String(pr.picture))}" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">` : `<div style="width:44px;height:44px;border-radius:50%;background:var(--card);flex:none"></div>`;
  const body = ev.kind === 0 ? `<span class="sub">${esc(pr.about || '')}</span>` : esc(String(ev.content || '').slice(0, 400));
  return `<div class="ev" data-i="${i}">
    <div class="head">${pic}<div><div class="name">${esc(name)}</div><div class="sub">${pr.nip05 ? esc(pr.nip05) + ' · ' : ''}${when}</div></div></div>
    <button class="dots" data-menu="${i}" aria-label="more"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></button>
    <div class="body"><span class="kind">kind ${esc(String(ev.kind))}${ev.kind === 0 ? ' profile' : ''}</span>${body}</div>
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

// ---------------------------------------------------------------- make glyphs: publish a cairn
// What a person types becomes a kind 1738 cairn (spec/CAIRN.md): with a link, a link cairn that opens
// it; without one, a text cairn that carries the text itself. Either way it is signed with a key made for it and forgotten right after, published
// to DEFAULT_RELAY, looked up again by its first 6 bytes, and drawn in "Bytes to glyphs".
// The signer is a separate script (BigInt): a browser that cannot run it still gets the reader.
$('cairnRelay').textContent = DEFAULT_RELAY;
const hostOf = u => { try { return new URL(u).host; } catch (e) { return u; } };
const cannotPublish = nappletRelay() ? 'Making glyphs for a link works on glyphbyte.dev/app, not inside a nostr app.'
  : (typeof signEvent !== 'function' || typeof BigInt !== 'function' || !(window.crypto && crypto.subtle))
    ? 'This browser is too old to make glyphs for a link. Reading still works.' : '';
let cairnPick = '', cairnBusy = false;
function cairnUrl(urls) { return urls.includes(cairnPick) ? cairnPick : urls[0] || ''; }
function renderCairnInfo() {
  const text = $('cairnText').value, { urls, content, blank } = parseCairnText(text), url = cairnUrl(urls), info = $('cairnInfo');
  if (cannotPublish) info.innerHTML = `<p class="warn">${esc(cannotPublish)}</p>`;
  else if (blank) info.innerHTML = '';
  else if (!urls.length) info.innerHTML = `<p class="muted">No link, so the glyphs will lead to this text itself. Add a link that starts with https:// to make glyphs that open it.</p>`;
  else if (urls.length === 1) info.innerHTML = `<p class="dest">Opens <b>${esc(hostOf(url))}</b> <code>${esc(url)}</code></p>`;
  else info.innerHTML = `<p class="muted" style="margin-bottom:2px">Which link should the glyphs open?</p>` + urls.map(u =>
    `<label class="pick"><input type="radio" name="cairnUrl" value="${esc(u)}"${u === url ? ' checked' : ''}><span><b>${esc(hostOf(u))}</b> <code>${esc(u)}</code></span></label>`).join('');
  if (!cannotPublish && !blank && content !== text.trim()) info.innerHTML += `<p class="muted dest">Saved as <code>${esc(content)}</code>, tidied so that every link stands on its own.</p>`;
  for (const r of info.querySelectorAll('input[name=cairnUrl]')) r.addEventListener('change', () => { cairnPick = r.value; });
  $('cairnBtn').textContent = 'Make glyphs';
  $('cairnBtn').disabled = !!cannotPublish || cairnBusy || blank;
  $('cairnText').readOnly = !!cannotPublish || cairnBusy;   // what is being published cannot change under it
}
$('cairnText').addEventListener('input', renderCairnInfo);
$('cairnBtn').addEventListener('click', publishText);
renderCairnInfo();

async function publishText() {
  const { urls, content, blank } = parseCairnText($('cairnText').value), url = cairnUrl(urls);
  if (cannotPublish || blank || cairnBusy) return;
  const st = $('cairnStatus'), relay = DEFAULT_RELAY, say = (cls, msg) => { st.className = cls; st.textContent = msg; };
  const opts = { relay, nappletRelay: nappletRelay() };
  cairnBusy = true; renderCairnInfo(); $('cairnResult').innerHTML = '';
  let sk = null, published = null;
  try {
    const tpl = cairnTemplate(url, content), check = validateCairn(tpl);
    if (!check.ok) throw new Error(url || !contentUrls(content).length ? check.errors.join('; ') : 'the text has something that looks like an unfinished link; finish it or remove it');
    say('muted', 'Making…');
    sk = generateSecretKey();
    const ev = await signEvent(tpl, sk);
    sk.fill(0);   // the key's only job is done; nothing keeps it
    say('muted', 'Saving…');
    const sent = await publishEvent(ev, opts);
    if (!sent.ok && sent.answered) throw new Error(`the server refused it${sent.message ? ': ' + sent.message : ''}`);
    say('muted', 'Checking it can be found…');
    const back = await lookup([ev.id.slice(0, 2 * CAIRN_MIN_BYTES)], opts), found = back.events.some(e => e.id === ev.id);
    // no OK (timeout, dropped connection): the relay may still have stored it, and only finding it tells
    if (!sent.ok && !found) throw new Error(`${sent.message}, and the server does not have it, so nothing was saved`);
    published = ev;
    say('muted', '');
    $('cairnText').value = ''; cairnPick = '';
    cairnBusy = false; renderCairnInfo();   // before showPublished scrolls, so nothing above the card moves
    showPublished(ev, url, found, relay);
  } catch (e) {
    say('warn', published ? `Saved (id ${published.id.slice(0, 12)}…), but the page failed to show it: ${e.message || e}`
      : `Not saved: ${e.message || e}`);
  } finally {
    if (sk) sk.fill(0);
    cairnBusy = false; renderCairnInfo();
  }
}

// the card for what was just published, and its glyphs in "Bytes to glyphs" (at least 6 bytes: the
// minimum for a cairn, and the recommended prefix length for any event id)
function showPublished(ev, url, found, relay) {
  const prefix = ev.id.slice(0, 2 * CAIRN_MIN_BYTES), chars = Array.from(ev.content), n = 280;
  $('cairnResult').innerHTML = `<div class="ev">
    <div class="${found ? 'ok' : 'warn'}" style="font-size:14px">${found
      ? `Done. Draw these ${CAIRN_MIN_BYTES} glyphs and anyone can read them${url ? ' to open the link' : ' to see the text'}.`
      : `Saved, but the lookup cannot find it yet. Try reading the glyphs again in a minute.`}</div>
    <div class="body dest">${url ? `Opens <b>${esc(hostOf(url))}</b> <code>${esc(url)}</code>`
      : `Leads to the text <b>${esc(chars.slice(0, n).join(''))}${chars.length > n ? '…' : ''}</b>`}</div>
    <canvas id="cairnRow" class="render glyphs"></canvas>
    <div class="sub">id <code>${esc(prefix)}</code>${esc(ev.id.slice(2 * CAIRN_MIN_BYTES, 24))}…</div>
    <div class="row" style="margin-bottom:0"><button id="cairnDraw">Bigger, with a description</button><button id="cairnCopyId">Copy id</button><button id="cairnCopyNevent">Copy nevent</button></div>
  </div>`;
  $('cairnCopyId').addEventListener('click', () => copyText(ev.id));
  $('cairnCopyNevent').addEventListener('click', () => copyText(nevent(ev.id, { relays: [relay], author: ev.pubkey, kind: ev.kind })));
  $('cairnDraw').addEventListener('click', () => showTab('draw'));
  drawRow($('cairnRow'), SHAPES, toBytes(prefix), 110);
  $('hex').value = ev.id;
  if (nBytes() && nBytes() < CAIRN_MIN_BYTES) { const r = document.querySelector(`input[name=nbytes][value="${CAIRN_MIN_BYTES}"]`); if (r) r.checked = true; }
  renderEncode();
  $('cairnResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---------------------------------------------------------------- relay capability probe
let probeTimer, probeSeq = 0;
async function probe() {
  const url = relayUrl(), seq = ++probeSeq, st = $('relayStatus');
  if (!/^wss?:\/\//.test(url)) { st.textContent = ''; return; }
  st.className = 'muted'; st.textContent = 'checking…';
  const r = await probeRelay(url, { nappletRelay: nappletRelay() });
  if (seq !== probeSeq) return;
  if (r.ok) { st.className = 'ok'; st.textContent = 'ready'; }
  else if (r.ids === 'rejected' || r.authors === 'rejected') { st.className = 'bad'; st.textContent = `this relay rejects partial queries${r.detail ? ': ' + r.detail.replace(/^CLOSED: /, '') : ''}`; }
  else if (r.ids === 'ignored' || r.authors === 'ignored') { st.className = 'bad'; st.textContent = 'this server answered, but not to short ids (exact matches only), so rows cannot be looked up on it'; }
  else { st.className = 'warn'; st.textContent = `could not check this server: ${r.detail}`; }
}
$('relay').addEventListener('input', () => { clearTimeout(probeTimer); probeTimer = setTimeout(probe, 700); });
probe();
function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
