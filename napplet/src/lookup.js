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

export async function lookup(prefixes, { relay = 'wss://wheat.happytavern.co', timeoutMs = 8000, nappletRelay = null } = {}) {
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
