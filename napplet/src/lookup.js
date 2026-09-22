// Turn candidate prefixes into relay queries. Inside a NIP-5D shell the page has no network
// and must use window.napplet.relay; as a standalone file it opens a WebSocket itself.

export function buildFilters(prefixes, kinds0Only = true) {
  const ps = Array.from(new Set(prefixes.map(p => p.toLowerCase()).filter(p => /^[0-9a-f]{2,64}$/.test(p))));
  if (!ps.length) return [];
  const f = [{ ids: ps }, { authors: ps, kinds: [0] }];
  if (!kinds0Only) f.push({ authors: ps, limit: 20 });
  return f;
}

function viaWebSocket(url, filters, timeoutMs) {
  return new Promise(resolve => {
    const events = [], seen = new Set(); let notices = [], done = false, ws;
    const finish = (error) => { if (done) return; done = true; try { ws && ws.close(); } catch (e) { /* ignore */ } resolve({ events, notices, error, via: 'websocket' }); };
    try { ws = new WebSocket(url); } catch (e) { return finish(String(e)); }
    const timer = setTimeout(() => finish('timeout'), timeoutMs);
    ws.onopen = () => ws.send(JSON.stringify(['REQ', 'symple', ...filters]));
    ws.onmessage = m => {
      let msg; try { msg = JSON.parse(m.data); } catch (e) { return; }
      if (msg[0] === 'EVENT' && msg[2] && !seen.has(msg[2].id)) { seen.add(msg[2].id); events.push(msg[2]); }
      else if (msg[0] === 'EOSE') { clearTimeout(timer); ws.send(JSON.stringify(['CLOSE', 'symple'])); finish(undefined); }
      else if (msg[0] === 'NOTICE') notices.push(String(msg[1]));
      else if (msg[0] === 'CLOSED') { notices.push('CLOSED: ' + msg[2]); clearTimeout(timer); finish(undefined); }
    };
    ws.onerror = () => { clearTimeout(timer); finish('connection failed'); };
    ws.onclose = () => { clearTimeout(timer); finish(undefined); };
  });
}

async function viaNapplet(relayApi, url, filters, timeoutMs) {
  // NAP-RELAY: query(filters) on the shell's pool; subscribe(filters, {relay}) can target one relay
  try {
    if (typeof relayApi.subscribe === 'function' && url) {
      return await new Promise(resolve => {
        const events = [], seen = new Set(); let sub;
        const timer = setTimeout(() => { try { sub && sub.close && sub.close(); } catch (e) { /* ignore */ } resolve({ events, notices: [], error: 'timeout', via: 'napplet' }); }, timeoutMs);
        try {
          sub = relayApi.subscribe(filters, { relay: url });
          const onEvent = r => { const ev = r && r.event ? r.event : r; if (ev && ev.id && !seen.has(ev.id)) { seen.add(ev.id); events.push(ev); } };
          const onEose = () => { clearTimeout(timer); try { sub.close && sub.close(); } catch (e) { /* ignore */ } resolve({ events, notices: [], via: 'napplet' }); };
          if (typeof sub.on === 'function') { sub.on('event', onEvent); sub.on('eose', onEose); }
          else if (typeof sub.addEventListener === 'function') { sub.addEventListener('event', e => onEvent(e.detail || e)); sub.addEventListener('eose', onEose); }
          else if (sub && typeof sub.then === 'function') { sub.then(res => { (res || []).forEach(onEvent); onEose(); }); }
          else { sub.onevent = onEvent; sub.oneose = onEose; }
        } catch (e) { clearTimeout(timer); resolve({ events: [], notices: [], error: String(e), via: 'napplet' }); }
      });
    }
    const res = await relayApi.query(filters);
    const events = (res || []).map(r => (r && r.event) ? r.event : r).filter(e => e && e.id);
    return { events, notices: [], via: 'napplet' };
  } catch (e) { return { events: [], notices: [], error: String(e), via: 'napplet' }; }
}

export async function lookup(prefixes, { relay = 'wss://wheat.oslim.dev', timeoutMs = 8000, nappletRelay = null } = {}) {
  const filters = buildFilters(prefixes);
  if (!filters.length) return { events: [], notices: [], error: 'no prefixes', via: 'none' };
  if (nappletRelay) return viaNapplet(nappletRelay, relay, filters, timeoutMs);
  if (typeof WebSocket === 'undefined') return { events: [], notices: [], error: 'no WebSocket here', via: 'none' };
  return viaWebSocket(relay, filters, timeoutMs);
}

// which candidate prefix an event answers to, and how
export function matchPrefix(ev, prefixes) {
  for (const p of prefixes) { const q = p.toLowerCase(); if (ev.id.startsWith(q)) return { prefix: q, how: 'event id' }; if (ev.pubkey.startsWith(q)) return { prefix: q, how: 'pubkey' }; }
  return null;
}


// fetch kind 0 for full pubkeys (the authors of id-matched events)
export async function fetchProfiles(pubkeys, { relay = 'wss://wheat.oslim.dev', timeoutMs = 6000, nappletRelay = null } = {}) {
  const pks = Array.from(new Set(pubkeys)).filter(p => /^[0-9a-f]{64}$/.test(p));
  if (!pks.length) return {};
  const filters = [{ authors: pks, kinds: [0] }];
  const r = nappletRelay ? await viaNapplet(nappletRelay, relay, filters, timeoutMs) : await viaWebSocket(relay, filters, timeoutMs);
  const out = {};
  for (const ev of r.events) if (ev.kind === 0 && (!out[ev.pubkey] || out[ev.pubkey].created_at < ev.created_at)) out[ev.pubkey] = ev;
  return out;
}

// does this relay honor partial ids and partial authors? Fetch one real event, then ask for it
// by an 8-character prefix of its id and of its pubkey.
export async function probeRelay(url, { timeoutMs = 6000, nappletRelay = null } = {}) {
  const q = f => nappletRelay ? viaNapplet(nappletRelay, url, f, timeoutMs) : viaWebSocket(url, f, timeoutMs);
  const a = await q([{ kinds: [0, 1], limit: 1 }]);
  if (a.error && !a.events.length) return { ok: false, ids: 'unknown', authors: 'unknown', detail: a.error };
  if (!a.events.length) return { ok: false, ids: 'unknown', authors: 'unknown', detail: 'relay returned no events to test with' };
  const ev = a.events[0];
  const verdict = r => (r.notices.some(n => /CLOSED|error|invalid|too small|bad req/i.test(n)) ? 'rejected' : r.events.some(e => e.id === ev.id) ? 'yes' : 'ignored');
  const byId = await q([{ ids: [ev.id.slice(0, 8)] }]);
  const byAuthor = await q([{ authors: [ev.pubkey.slice(0, 8)], kinds: [ev.kind], limit: 5 }]);
  const ids = verdict(byId), authors = byAuthor.notices.some(n => /CLOSED|error|invalid|too small|bad req/i.test(n)) ? 'rejected' : byAuthor.events.some(e => e.pubkey === ev.pubkey) ? 'yes' : 'ignored';
  const detail = [...byId.notices, ...byAuthor.notices].filter(Boolean)[0] || '';
  return { ok: ids === 'yes' && authors === 'yes', ids, authors, detail };
}
