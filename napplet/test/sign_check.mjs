// Checks src/sign.js: every official BIP-340 test vector, interoperability with nak (a Go nostr
// implementation), and the example event in spec/CAIRN.md. Run: node test/sign_check.mjs
//
// bip340-vectors.csv is bitcoin/bips bip-0340/test-vectors.csv, unchanged (BSD-2-Clause).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { schnorrSign, schnorrVerify, schnorrPublicKey, eventId, signEvent, verifyEvent, generateSecretKey } from '../src/sign.js';
import { validateCairn } from '../src/cairn.js';

const here = p => fileURLToPath(new URL(p, import.meta.url));
let failures = 0;
const check = (ok, what) => { if (!ok) { failures++; console.log('FAIL', what); } };

// 1. BIP-340: signing (where the vector has a secret key) must reproduce the signature byte for byte,
//    and verification must give the vector's expected result (vectors 5-14 are forgeries and edge cases)
const rows = readFileSync(here('./bip340-vectors.csv'), 'utf8').trim().split(/\r?\n/).slice(1).map(l => l.split(','));
for (const [i, sk, pk, aux, msg, sig, result] of rows) {
  if (sk) {
    check(schnorrPublicKey(sk) === pk.toLowerCase(), `vector ${i}: public key`);
    check(await schnorrSign(msg, sk, aux) === sig.toLowerCase(), `vector ${i}: signature`);
  }
  check(await schnorrVerify(msg, pk, sig) === (result === 'TRUE'), `vector ${i}: verify should be ${result}`);
}

// 2. nak (Go) signed this cairn with BIP-340 vector 1's key. Its content has quotes, a backslash, a
//    tab, a line break, non-ASCII and HTML characters, which every serializer must write the same way.
const SK = 'b7e151628aed2a6abf7158809cf4f3c762e7160f38b4da56a784d9045190cfef';
const NAK = {"kind":1738,"id":"e022844c9ced7791bbed868de3d63e2643f20f6d58354773dc80f51ce4275874","pubkey":"dff1d77f2a671c5f36183726db2341be58feae1da2deced843240f7b502ba659","created_at":1790000000,"tags":[["r","https://example.com/a?b=1"],["alt","Cairn: https://example.com/a?b=1"]],"content":"https://example.com/a?b=1 \"quoted\" back\\slash\ttab\nnew line é ☕ 🪨 <&>","sig":"bffc8c5b41278bb762ce084d80845b904a54260511191bf8f54fd74f65c91cf13a57b21ab393686275d257c7c28712f985b40d29c72be75d2c5412a3b3d0630e"};
check(await eventId(NAK) === NAK.id, 'nak event: same id');
check(await verifyEvent(NAK), 'nak event: its signature verifies');
const mine = await signEvent({ kind: NAK.kind, created_at: NAK.created_at, tags: NAK.tags, content: NAK.content }, SK);
check(mine.id === NAK.id && mine.pubkey === NAK.pubkey, 'signing the same template gives the same id and pubkey');
check(await verifyEvent(mine), 'our signature verifies');   // nak verify accepted it too when this test was written
check(!(await verifyEvent({ ...mine, content: mine.content + '!' })), 'a changed content fails');
check(!(await verifyEvent({ ...mine, pubkey: mine.pubkey.toUpperCase() })), 'uppercase hex is not NIP-01');
check(!(await verifyEvent({ ...mine, sig: mine.sig.slice(0, -2) + (mine.sig.endsWith('00') ? '01' : '00') })), 'a changed signature fails');

// 3. the example in spec/CAIRN.md is a real, valid, signed cairn
const spec = readFileSync(here('../../spec/CAIRN.md'), 'utf8');
const example = JSON.parse(spec.slice(spec.indexOf('## Example')).match(/```json\n([\s\S]*?)```/)[1]);
check(await verifyEvent(example), 'spec example: id and signature');
check(validateCairn(example).ok, 'spec example: a valid cairn');

// 4. fresh keys: in range, and they sign events that verify
for (let n = 0; n < 3; n++) {
  const ev = await signEvent({ kind: 1738, tags: [['r', 'https://glyphbyte.dev/']], content: '' }, generateSecretKey());
  check(/^[0-9a-f]{64}$/.test(ev.id) && await verifyEvent(ev), `fresh key ${n}`);
}

console.log(failures ? `${failures} failed` : `all passed (${rows.length} BIP-340 vectors, nak, spec example, fresh keys)`);
process.exit(failures ? 1 : 0);
