import { npub, nevent, naddr, note } from '../src/nip19.js';
const pk = 'e8ed3798c6ffebffa08501ac39e271662bfd160f688f94c45d692d8767dd345a';
const got = npub(pk), want = 'npub1arkn0xxxll4llgy9qxkrncn3vc4l69s0dz8ef3zadykcwe7ax3dqrrh43w';
console.log('npub', got === want ? 'OK' : `MISMATCH ${got}`);
const ne = nevent('36f988e43ff1'.padEnd(64, '0'), { relays: ['wss://wheat.happytavern.co'], author: pk, kind: 0 });
console.log('nevent', ne.slice(0, 20) + '…', ne.length, 'chars');
console.log('naddr', naddr(30023, pk, 'hello', { relays: ['wss://wheat.happytavern.co'] }).slice(0, 24) + '…');
console.log('note', note(pk).slice(0, 12) + '…');
process.exit(got === want ? 0 : 1);
