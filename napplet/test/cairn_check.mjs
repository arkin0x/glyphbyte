// Checks src/cairn.js: turning typed text into a cairn, and the validity rules of spec/CAIRN.md.
// Run: node test/cairn_check.mjs
import { parseCairnText, cairnTemplate, validateCairn, contentUrls, CAIRN_KIND } from '../src/cairn.js';

let failures = 0;
const check = (ok, what, got) => { if (!ok) { failures++; console.log('FAIL', what, got === undefined ? '' : JSON.stringify(got)); } };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// [typed text, links found, content published]
const TEXT = [
  ['https://example.com/menu?table=4 lunch menu for table 4', ['https://example.com/menu?table=4'], 'https://example.com/menu?table=4 lunch menu for table 4'],
  ['  see https://x.org/a.  ', ['https://x.org/a'], 'see https://x.org/a .'],                             // punctuation moved off the link
  ['is it https://x.org/a?', ['https://x.org/a'], 'is it https://x.org/a ?'],
  ['https://en.wikipedia.org/wiki/Cairn_(disambiguation)', ['https://en.wikipedia.org/wiki/Cairn_(disambiguation)'], 'https://en.wikipedia.org/wiki/Cairn_(disambiguation)'],
  ['(https://en.wikipedia.org/wiki/Cairn_(disambiguation)).', ['https://en.wikipedia.org/wiki/Cairn_(disambiguation)'], '( https://en.wikipedia.org/wiki/Cairn_(disambiguation) ).'],   // brackets moved off both ends
  ['two: https://a.example and https://b.example/x, ok', ['https://a.example', 'https://b.example/x'], 'two: https://a.example and https://b.example/x , ok'],
  ['same https://a.example twice https://a.example', ['https://a.example'], 'same https://a.example twice https://a.example'],
  ['HTTPS://Example.COM/Path', ['HTTPS://Example.COM/Path'], 'HTTPS://Example.COM/Path'],               // stored exactly as typed
  ['no link here', [], 'no link here'],
  ['javascript:alert(1) data:text/html,x ftp://x.org https://', [], 'javascript:alert(1) data:text/html,x ftp://x.org https://'],
  ['<https://x.org/a>', ['https://x.org/a'], '< https://x.org/a >'],
  ['(https://a.example) see also https://b.example', ['https://a.example', 'https://b.example'], '( https://a.example ) see also https://b.example'],   // review: the bracketed link must be publishable
  ['"https://a.example" and https://b.example/x.', ['https://a.example', 'https://b.example/x'], '" https://a.example " and https://b.example/x .'],
  ['line one\u2028https://x.org/a\u2029end', ['https://x.org/a'], 'line one\nhttps://x.org/a\nend'],   // grain refuses U+2028/U+2029
  ['https://a.example/x\u00a0lunch', ['https://a.example/x'], 'https://a.example/x lunch'],               // tokens split at ASCII whitespace only
  ['https://a.example/x\u0085lunch', ['https://a.example/x'], 'https://a.example/x\nlunch'],
  ['https://a.example/x\ufefflunch', ['https://a.example/xlunch'], 'https://a.example/xlunch'],           // U+FEFF is invisible: the link is what the eye sees
  ['bell\u0007 https://x.org\u0001/a\u000b ok\ttab\nline', ['https://x.org/a'], 'bell https://x.org/a ok\ttab\nline'],   // control characters dropped
  ['broken \ud800 half https://x.org', ['https://x.org'], 'broken � half https://x.org'],
];
for (const [text, urls, content] of TEXT) {
  const got = parseCairnText(text);
  check(same(got.urls, urls), `links in ${JSON.stringify(text)}`, got.urls);
  check(got.content === content, `content of ${JSON.stringify(text)}`, got.content);
  for (const url of got.urls) {   // whichever link the person picks, the result is a valid cairn
    const v = validateCairn(cairnTemplate(url, got.content));
    check(v.ok && v.url === url, `valid cairn for ${url} from ${JSON.stringify(text)}`, v.errors);
  }
}

// the spec's rules, one by one
const T = (tags, content = '', kind = CAIRN_KIND) => ({ kind, tags, content, created_at: 0 });
const R = 'https://example.com/menu?table=4';
const CASES = [
  [T([['r', R]]), true, 'r only, empty content'],
  [T([['r', R], ['alt', `Cairn: ${R}`]], `${R} lunch`), true, 'r, alt, content with the URL'],
  [T([['r', R]], 'lunch menu, no link'), true, 'content may omit the URL'],
  [T([['r', R]], `https://other.example ${R}`), true, 'several URLs, one equals r'],
  [T([['r', R]], 'https://other.example lunch'), false, 'content URL that is not r'],
  [T([['r', R]], `${R}. lunch`), false, 'punctuation glued to the URL: tokens compare whole'],
  [T([]), false, 'no r tag'],
  [T([['r', R], ['r', 'https://b.example']]), false, 'two r tags'],
  [T([['r', 'not a url']]), false, 'r is not an absolute URL'],
  [T([['r', R], ['alt', 'Cairn: https://b.example']]), false, 'alt with another URL'],
  [T([['r', R], ['alt', 'a link']]), false, 'alt without the Cairn: form'],
  [T([['r', R]], '', 1), false, 'wrong kind'],
  [T([['r', 'nostr:npub1x']], 'nostr:npub1y'), false, "content token with r's own scheme must equal r"],
  [T([['r', R]], `${R}\u00a0lunch`), false, 'a no-break space does not separate tokens'],
];
for (const [ev, ok, what] of CASES) { const v = validateCairn(ev); check(v.ok === ok, `${what}: expected ${ok ? 'valid' : 'invalid'}`, v.errors); }

for (const [text, blank] of [['\u200b', true], ['\u0007\u0001', true], [' \n\t ', true], ['\ufeff\u2060', true], ['a', false], ['https://x.org', false]])
  check(parseCairnText(text).blank === blank, `blank for ${JSON.stringify(text)}`);
check(same(contentUrls('a https://x.org b http://y.org mailto:z', 'mailto:me'), ['https://x.org', 'http://y.org', 'mailto:z']), 'contentUrls');
check(same(cairnTemplate(R, 'x', 1790000000), { kind: 1738, created_at: 1790000000, content: 'x', tags: [['r', R], ['alt', `Cairn: ${R}`]] }), 'cairnTemplate');

console.log(failures ? `${failures} failed` : `all passed (${TEXT.length} texts, ${CASES.length} rules)`);
process.exit(failures ? 1 : 0);
