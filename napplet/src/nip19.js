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
