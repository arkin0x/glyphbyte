import { lookup, matchPrefix } from '../src/lookup.js';
const prefixes = process.argv.slice(2);
const t = Date.now(); const r = await lookup(prefixes, { relay: 'wss://wheat.happytavern.co' });
console.log(`via ${r.via} in ${Date.now() - t} ms, events ${r.events.length}, error ${r.error || '-'}, notices ${JSON.stringify(r.notices)}`);
for (const ev of r.events.slice(0, 8)) {
  const m = matchPrefix(ev, prefixes); let name = '';
  if (ev.kind === 0) { try { const c = JSON.parse(ev.content); name = `${c.name || c.display_name || ''} ${c.nip05 || ''}`; } catch (e) { /* ignore */ } }
  console.log(`  kind ${ev.kind} id ${ev.id.slice(0, 12)} pubkey ${ev.pubkey.slice(0, 12)} ${m ? `<- ${m.prefix} by ${m.how}` : ''} ${name}`);
}
