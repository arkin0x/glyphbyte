// Signing nostr events with a key made for one event: BIP-340 Schnorr signatures over secp256k1,
// NIP-01 event ids, and verification. No dependencies: BigInt arithmetic plus the platform's SHA-256
// (crypto.subtle) and random numbers (crypto.getRandomValues), in browsers and in Node 22.
//
// The arithmetic is not constant time, so its timing can leak bits of the key. That is acceptable
// here only because a cairn's key signs a single event and is then thrown away; do not use this
// module for a long-lived key. Checked against every official BIP-340 test vector (test/sign_check.mjs).

const SECP_P = 0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2fn;   // field prime
const SECP_N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;   // group order
const SECP_G = [0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798n,   // generator
                0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8n];

const secpMod = (a, m = SECP_P) => ((a % m) + m) % m;
function secpPow(b, e, m = SECP_P) { let r = 1n; b = secpMod(b, m); for (; e > 0n; e >>= 1n, b = b * b % m) if (e & 1n) r = r * b % m; return r; }
function secpInv(a, m = SECP_P) {   // extended Euclid: s0 * a = r0 (mod m) holds at every step
  let r0 = secpMod(a, m), r1 = m, s0 = 1n, s1 = 0n;
  while (r1 !== 0n) { const q = r0 / r1; [r0, r1] = [r1, r0 - q * r1]; [s0, s1] = [s1, s0 - q * s1]; }
  if (r0 !== 1n) throw new Error('not invertible');
  return secpMod(s0, m);
}
// affine points [x, y]; null is the point at infinity
function secpAdd(p, q) {
  if (!p) return q;
  if (!q) return p;
  const [x1, y1] = p, [x2, y2] = q;
  let l;
  if (x1 === x2) {
    if (secpMod(y1 + y2) === 0n) return null;              // p + (-p)
    l = secpMod(3n * x1 * x1 * secpInv(2n * y1));          // doubling
  } else l = secpMod((y2 - y1) * secpInv(x2 - x1));
  const x3 = secpMod(l * l - x1 - x2);
  return [x3, secpMod(l * (x1 - x3) - y1)];
}
function secpMul(k, p) { let r = null; for (let a = p; k > 0n; k >>= 1n, a = secpAdd(a, a)) if (k & 1n) r = secpAdd(r, a); return r; }
// the point with this x and an even y (BIP-340 lift_x), or null when there is none
function secpLiftX(x) {
  if (x >= SECP_P) return null;
  const c = secpMod(x * x * x + 7n), y = secpPow(c, (SECP_P + 1n) / 4n);
  if (secpMod(y * y) !== c) return null;
  return [x, y & 1n ? SECP_P - y : y];
}

const schHex = b => Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
function schBytes(h) {
  if (typeof h !== 'string' || !/^(?:[0-9a-f]{2})*$/i.test(h)) throw new Error('expected hex');
  return Uint8Array.from(h.match(/../g) || [], x => parseInt(x, 16));
}
function asBytes(v, len) {
  const b = typeof v === 'string' ? schBytes(v) : v;
  if (!(b instanceof Uint8Array)) throw new Error('expected bytes or hex');
  if (len !== undefined && b.length !== len) throw new Error(`expected ${len} bytes, got ${b.length}`);
  return b;
}
const schBig = b => b.length ? BigInt('0x' + schHex(b)) : 0n;
const schBytes32 = n => schBytes(n.toString(16).padStart(64, '0'));
function schConcat(...parts) { const out = new Uint8Array(parts.reduce((s, p) => s + p.length, 0)); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; } return out; }
const schSha256 = async bytes => new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
async function taggedHash(tag, ...parts) { const t = await schSha256(new TextEncoder().encode(tag)); return schSha256(schConcat(t, t, ...parts)); }
function secretScalar(secretKey) {
  const d = schBig(asBytes(secretKey, 32));
  if (d === 0n || d >= SECP_N) throw new Error('secret key out of range');
  return d;
}

// 32 random bytes that are a valid secret key
export function generateSecretKey() {
  for (;;) { const sk = crypto.getRandomValues(new Uint8Array(32)), d = schBig(sk); if (d > 0n && d < SECP_N) return sk; }
}

// the x-only public key (hex, 64 characters) of a secret key (32 bytes, or hex)
export function schnorrPublicKey(secretKey) { return schHex(schBytes32(secpMul(secretScalar(secretKey), SECP_G)[0])); }

// BIP-340 signature (hex, 128 characters) of a message of any length (bytes, or hex). auxRand is
// 32 bytes mixed into the nonce; it defaults to fresh random bytes, tests pass the vectors' value.
export async function schnorrSign(message, secretKey, auxRand = crypto.getRandomValues(new Uint8Array(32))) {
  const m = asBytes(message), a = asBytes(auxRand, 32), d0 = secretScalar(secretKey);
  const P = secpMul(d0, SECP_G), d = P[1] & 1n ? SECP_N - d0 : d0, px = schBytes32(P[0]);
  const t = schBytes32(d ^ schBig(await taggedHash('BIP0340/aux', a)));
  const k0 = secpMod(schBig(await taggedHash('BIP0340/nonce', t, px, m)), SECP_N);
  if (k0 === 0n) throw new Error('nonce is zero');
  const R = secpMul(k0, SECP_G), k = R[1] & 1n ? SECP_N - k0 : k0, rx = schBytes32(R[0]);
  const e = secpMod(schBig(await taggedHash('BIP0340/challenge', rx, px, m)), SECP_N);
  const sig = schConcat(rx, schBytes32(secpMod(k + e * d, SECP_N)));
  if (!(await schnorrVerify(m, px, sig))) throw new Error('signature failed its own check');   // BIP-340 recommends this
  return schHex(sig);
}

// BIP-340 verification; false for anything malformed, never throws
export async function schnorrVerify(message, publicKey, signature) {
  try {
    const m = asBytes(message), pk = asBytes(publicKey, 32), sig = asBytes(signature, 64);
    const P = secpLiftX(schBig(pk));
    if (!P) return false;
    const r = schBig(sig.subarray(0, 32)), s = schBig(sig.subarray(32));
    if (r >= SECP_P || s >= SECP_N) return false;
    const e = secpMod(schBig(await taggedHash('BIP0340/challenge', sig.subarray(0, 32), pk, m)), SECP_N);
    const R = secpAdd(secpMul(s, SECP_G), secpMul(secpMod(-e, SECP_N), P));
    return !!R && !(R[1] & 1n) && R[0] === r;
  } catch (err) { return false; }
}

// NIP-01 event id: SHA-256 of the JSON array [0, pubkey, created_at, kind, tags, content]
export async function eventId(ev) {
  return schHex(await schSha256(new TextEncoder().encode(JSON.stringify([0, ev.pubkey, ev.created_at, ev.kind, ev.tags, ev.content]))));
}

// sign an event template {kind, created_at, tags, content}; returns the complete event
export async function signEvent(template, secretKey) {
  const ev = {
    kind: template.kind, created_at: template.created_at != null ? template.created_at : Math.floor(Date.now() / 1000),
    tags: template.tags || [], content: template.content || '', pubkey: schnorrPublicKey(secretKey),
  };
  ev.id = await eventId(ev);
  ev.sig = await schnorrSign(ev.id, secretKey);
  return ev;
}

// is the id the hash of the event, and the signature valid for it? (id, pubkey and sig must be
// lowercase hex of the right length, as NIP-01 writes them)
export async function verifyEvent(ev) {
  try {
    return /^[0-9a-f]{64}$/.test(ev.id) && /^[0-9a-f]{64}$/.test(ev.pubkey) && /^[0-9a-f]{128}$/.test(ev.sig) &&
      ev.id === await eventId(ev) && await schnorrVerify(ev.id, ev.pubkey, ev.sig);
  } catch (err) { return false; }
}
