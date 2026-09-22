// NIP-19 bech32 encoding: npub, note, nevent, naddr (with relay hints). Encode only.
const CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';
function polymod(values) { const G = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]; let chk = 1;
  for (const v of values) { const b = chk >> 25; chk = ((chk & 0x1ffffff) << 5) ^ v; for (let i = 0; i < 5; i++) if ((b >> i) & 1) chk ^= G[i]; } return chk; }
function hrpExpand(hrp) { const out = []; for (const c of hrp) out.push(c.charCodeAt(0) >> 5); out.push(0); for (const c of hrp) out.push(c.charCodeAt(0) & 31); return out; }
function toWords(bytes) { const out = []; let acc = 0, bits = 0; for (const b of bytes) { acc = (acc << 8) | b; bits += 8; while (bits >= 5) { bits -= 5; out.push((acc >> bits) & 31); } } if (bits > 0) out.push((acc << (5 - bits)) & 31); return out; }
export function bech32Encode(hrp, bytes) {
  const words = toWords(bytes), pm = polymod(hrpExpand(hrp).concat(words, [0, 0, 0, 0, 0, 0])) ^ 1, chk = [];
  for (let i = 0; i < 6; i++) chk.push((pm >> (5 * (5 - i))) & 31);
  return hrp + '1' + words.concat(chk).map(w => CHARSET[w]).join('');
}
const hexBytes = h => Uint8Array.from(h.match(/../g).map(x => parseInt(x, 16)));
const utf8 = s => new TextEncoder().encode(s);
function tlv(items) { const parts = []; for (const [t, v] of items) { parts.push(t, v.length); for (const b of v) parts.push(b); } return Uint8Array.from(parts); }
export const npub = pk => bech32Encode('npub', hexBytes(pk));
export const note = id => bech32Encode('note', hexBytes(id));
export function nevent(id, { relays = [], author = null, kind = null } = {}) {
  const items = [[0, hexBytes(id)]]; for (const r of relays) items.push([1, utf8(r)]);
  if (author) items.push([2, hexBytes(author)]);
  if (kind !== null) items.push([3, Uint8Array.from([(kind >>> 24) & 255, (kind >>> 16) & 255, (kind >>> 8) & 255, kind & 255])]);
  return bech32Encode('nevent', tlv(items));
}
export function naddr(kind, pubkey, d, { relays = [] } = {}) {
  const items = [[0, utf8(d)]]; for (const r of relays) items.push([1, utf8(r)]);
  items.push([2, hexBytes(pubkey)], [3, Uint8Array.from([(kind >>> 24) & 255, (kind >>> 16) & 255, (kind >>> 8) & 255, kind & 255])]);
  return bech32Encode('naddr', tlv(items));
}
export const isAddressable = kind => kind >= 30000 && kind < 40000;

// ---------------------------------------------------------------- decoding
function fromWords(words) { const out = []; let acc = 0, bits = 0; for (const w of words) { acc = (acc << 5) | w; bits += 5; while (bits >= 8) { bits -= 8; out.push((acc >> bits) & 255); } } return Uint8Array.from(out); }
export function bech32Decode(str) {
  const s = str.toLowerCase(), pos = s.lastIndexOf('1');
  if (pos < 1 || pos + 7 > s.length) throw new Error('not bech32');
  const hrp = s.slice(0, pos), data = [];
  for (const c of s.slice(pos + 1)) { const v = CHARSET.indexOf(c); if (v < 0) throw new Error('bad character'); data.push(v); }
  if (polymod(hrpExpand(hrp).concat(data)) !== 1) throw new Error('bad checksum');
  return { hrp, bytes: fromWords(data.slice(0, -6)) };
}
const hex = b => Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
function parseTLV(bytes) { const out = []; let i = 0; while (i + 1 < bytes.length) { const t = bytes[i], l = bytes[i + 1], v = bytes.subarray(i + 2, i + 2 + l); if (v.length < l) break; out.push([t, v]); i += 2 + l; } return out; }
// Returns {type, hex, relays, kind, d, author} for npub, note, nprofile, nevent, naddr; throws otherwise.
export function decodeEntity(str) {
  const { hrp, bytes } = bech32Decode(str.trim().replace(/^nostr:/i, ''));
  if (hrp === 'npub' || hrp === 'note') { if (bytes.length !== 32) throw new Error('wrong length'); return { type: hrp, hex: hex(bytes), relays: [] }; }
  if (hrp === 'nprofile' || hrp === 'nevent' || hrp === 'naddr') {
    const out = { type: hrp, hex: null, relays: [], kind: null, d: null, author: null };
    for (const [t, v] of parseTLV(bytes)) {
      if (t === 0) out.hex = hrp === 'naddr' ? null : hex(v), out.d = hrp === 'naddr' ? new TextDecoder().decode(v) : null;
      else if (t === 1) out.relays.push(new TextDecoder().decode(v));
      else if (t === 2) out.author = hex(v);
      else if (t === 3 && v.length === 4) out.kind = (v[0] << 24 | v[1] << 16 | v[2] << 8 | v[3]) >>> 0;
    }
    if (hrp === 'naddr') out.hex = out.author;   // no event id in an naddr: the author's pubkey is the best prefix we have
    if (!out.hex) throw new Error('missing data');
    return out;
  }
  throw new Error('unsupported: ' + hrp);
}
