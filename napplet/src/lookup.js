// Turn candidate prefixes into relay queries, and publish events. Inside a NIP-5D shell the page
// has no network and must use window.napplet.relay; as a standalone file it opens a WebSocket itself.

// grain relays: they answer id and pubkey prefixes. DEFAULT_RELAY takes the cairns the reader publishes;
// LOOKUP_RELAYS are all asked when a row is read, so rows drawn while wss://wheat.oslim.dev was the
// default keep resolving.
export const DEFAULT_RELAY = 'wss://relay.onosendai.tech';
export const LOOKUP_RELAYS = [DEFAULT_RELAY, 'wss://wheat.oslim.dev'];

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
    ws.onopen = () => ws.send(JSON.stringify(['REQ', 'glyphbyte', ...filters]));
    ws.onmessage = m => {
      let msg; try { msg = JSON.parse(m.data); } catch (e) { return; }
      if (msg[0] === 'EVENT' && msg[2] && !seen.has(msg[2].id)) { seen.add(msg[2].id); events.push(msg[2]); }
      else if (msg[0] === 'EOSE') { clearTimeout(timer); ws.send(JSON.stringify(['CLOSE', 'glyphbyte'])); finish(undefined); }
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

export async function lookup(prefixes, { relay = DEFAULT_RELAY, timeoutMs = 8000, nappletRelay = null } = {}) {
  const filters = buildFilters(prefixes);
  if (!filters.length) return { events: [], notices: [], error: 'no prefixes', via: 'none' };
  if (nappletRelay) return viaNapplet(nappletRelay, relay, filters, timeoutMs);
  if (typeof WebSocket === 'undefined') return { events: [], notices: [], error: 'no WebSocket here', via: 'none' };
  return viaWebSocket(relay, filters, timeoutMs);
}

// Send one signed event and wait for the relay's answer (NIP-01 "OK"). Resolves {ok, answered,
// message, via}; never rejects. answered is false when no OK came back (timeout, dropped connection):
// the relay may or may not have stored the event, so look it up before publishing anything again.
// Inside a nostr shell (NIP-5D) the page has no network of its own, and no shell API to publish a
// pre-signed event is settled yet, so this refuses rather than guess.
export async function publishEvent(ev, { relay = DEFAULT_RELAY, timeoutMs = 8000, nappletRelay = null } = {}) {
  if (nappletRelay) return { ok: false, answered: false, message: 'publishing from inside a nostr shell is not supported', via: 'napplet' };
  if (typeof WebSocket === 'undefined') return { ok: false, answered: false, message: 'no WebSocket here', via: 'none' };
  return new Promise(resolve => {
    let ws, done = false;
    const finish = (ok, answered, message) => { if (done) return; done = true; clearTimeout(timer); try { ws && ws.close(); } catch (e) { /* ignore */ } resolve({ ok, answered, message, via: 'websocket' }); };
    const timer = setTimeout(() => finish(false, false, 'the relay did not answer in time'), timeoutMs);
    try { ws = new WebSocket(relay); } catch (e) { return finish(false, false, String(e)); }
    ws.onopen = () => ws.send(JSON.stringify(['EVENT', ev]));
    ws.onmessage = m => {
      let msg; try { msg = JSON.parse(m.data); } catch (e) { return; }
      if (msg[0] === 'OK' && msg[1] === ev.id) finish(msg[2] === true, true, String(msg[3] || ''));
    };
    ws.onerror = () => finish(false, false, 'connection failed');
    ws.onclose = () => finish(false, false, 'the relay closed the connection without answering');
  });
}

// which candidate prefix an event answers to, and how
export function matchPrefix(ev, prefixes) {
  for (const p of prefixes) { const q = p.toLowerCase(); if (ev.id.startsWith(q)) return { prefix: q, how: 'event id' }; if (ev.pubkey.startsWith(q)) return { prefix: q, how: 'pubkey' }; }
  return null;
}


// fetch kind 0 for full pubkeys (the authors of id-matched events)
export async function fetchProfiles(pubkeys, { relay = DEFAULT_RELAY, timeoutMs = 6000, nappletRelay = null } = {}) {
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
// One WebSocket for several REQs in a row: each resolves on its EOSE (or CLOSED) with the events and
// notices that arrived for it. The probe uses it so that testing a relay costs one connection, not
// three: relays limit new connections per IP (relay.onosendai.tech: 30 a minute), and a refused
// connection must never read as "this relay ignores prefixes".
function wsSession(url, timeoutMs) {
  let ws, opened, failed = null, n = 0, cur = null;
  const ready = new Promise(res => {
    try { ws = new WebSocket(url); } catch (e) { failed = String(e); return res(); }
    const t = setTimeout(() => { failed = failed || 'timeout'; res(); }, timeoutMs);
    ws.onopen = () => { clearTimeout(t); opened = true; res(); };
    ws.onerror = () => { clearTimeout(t); failed = failed || 'could not connect; try again in a minute'; res(); if (cur) cur.finish(failed); };
    ws.onclose = () => { if (cur) cur.finish(failed || 'connection closed'); };
    ws.onmessage = m => {
      let msg; try { msg = JSON.parse(m.data); } catch (e) { return; }
      if (!cur) return;
      if (msg[0] === 'EVENT' && msg[1] === cur.id && msg[2]) cur.events.push(msg[2]);
      else if (msg[0] === 'NOTICE') cur.notices.push(String(msg[1]));
      else if (msg[0] === 'EOSE' && msg[1] === cur.id) { try { ws.send(JSON.stringify(['CLOSE', cur.id])); } catch (e) { /* closing anyway */ } cur.finish(); }
      else if (msg[0] === 'CLOSED' && msg[1] === cur.id) { cur.notices.push('CLOSED: ' + msg[2]); cur.finish(); }
    };
  });
  return {
    async req(filters) {
      await ready;
      if (!opened || failed) return { events: [], notices: [], error: failed || 'connection failed' };
      return new Promise(resolve => {
        const id = 'gbprobe' + (++n), t = setTimeout(() => c.finish('timeout'), timeoutMs);
        const c = cur = { id, events: [], notices: [], finish(error) { if (cur !== c) return; cur = null; clearTimeout(t); resolve({ events: c.events, notices: c.notices, error }); } };
        try { ws.send(JSON.stringify(['REQ', id, ...filters])); } catch (e) { c.finish(String(e)); }
      });
    },
    close() { try { ws && ws.close(); } catch (e) { /* gone */ } },
  };
}

// Does the relay answer id and pubkey prefixes? Fetch one event, then ask for it again by an 8-character id
// prefix and by an 8-character author prefix. A query that fails (no connection, timeout) means "could not
// test", never "ignored": only an answered query that leaves the event out says the relay ignores prefixes.
export async function probeRelay(url, { timeoutMs = 6000, nappletRelay = null } = {}) {
  const session = nappletRelay ? null : wsSession(url, timeoutMs);
  const q = f => nappletRelay ? viaNapplet(nappletRelay, url, f, timeoutMs) : session.req(f);
  try {
    const a = await q([{ kinds: [0, 1], limit: 1 }]);
    if (a.error && !a.events.length) return { ok: false, ids: 'unknown', authors: 'unknown', detail: a.error };
    if (!a.events.length) return { ok: false, ids: 'unknown', authors: 'unknown', detail: 'relay returned no events to test with' };
    const ev = a.events[0];
    const refused = r => r.notices.some(n => /CLOSED|error|invalid|too small|bad req/i.test(n));
    const byId = await q([{ ids: [ev.id.slice(0, 8)] }]);
    const byAuthor = await q([{ authors: [ev.pubkey.slice(0, 8)], kinds: [ev.kind], limit: 5 }]);
    const failed = [byId, byAuthor].find(r => r.error && !r.events.length);
    if (failed) return { ok: false, ids: 'unknown', authors: 'unknown', detail: failed.error };
    const ids = refused(byId) ? 'rejected' : byId.events.some(e => e.id === ev.id) ? 'yes' : 'ignored';
    const authors = refused(byAuthor) ? 'rejected' : byAuthor.events.some(e => e.pubkey === ev.pubkey) ? 'yes' : 'ignored';
    const detail = [...byId.notices, ...byAuthor.notices].filter(n => !/matched as prefixes/.test(n))[0] || '';
    return { ok: ids === 'yes' && authors === 'yes', ids, authors, detail };
  } finally { if (session) session.close(); }
}
