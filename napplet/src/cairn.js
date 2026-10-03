// Cairns (kind 1738, spec/CAIRN.md): a regular event that carries one URL, so that the URL can be
// found again from the first bytes of the event's id. This module builds a cairn from what a person
// typed and checks the validity rules every reader applies; signing is in sign.js.

export const CAIRN_KIND = 1738;
export const CAIRN_MIN_BYTES = 6;   // readers never resolve a cairn from fewer bytes of its id

// The URLs in a cairn's content, by the spec's rule: tokens separated by ASCII whitespace (space,
// tab, line feed, form feed, carriage return) that begin with "http://" or "https://", or with the
// r URL's scheme followed by ":". Tokens are compared whole.
export function contentUrls(content, rUrl = '') {
  const i = String(rUrl).indexOf(':'), own = i > 0 ? String(rUrl).slice(0, i + 1) : null;
  return String(content || '').split(/[\t\n\f\r ]+/).filter(t => t && (t.startsWith('http://') || t.startsWith('https://') || (own && t.startsWith(own))));
}

const isAbsoluteUri = s => { try { new URL(s); return /^[a-z][a-z0-9+.-]*:/i.test(s); } catch (err) { return false; } };
const isWebUrl = s => { try { const u = new URL(s); return (u.protocol === 'http:' || u.protocol === 'https:') && !!u.hostname; } catch (err) { return false; } };

// Is this event a valid cairn? {ok, url, errors}. Checks the shape rules of spec/CAIRN.md: kind,
// exactly one r tag holding an absolute URL, the content rule, the alt rule. The id and signature
// are verifyEvent's job (sign.js).
export function validateCairn(ev) {
  const errors = [], tags = (ev && Array.isArray(ev.tags)) ? ev.tags : [];
  if (!ev || ev.kind !== CAIRN_KIND) errors.push(`the kind is not ${CAIRN_KIND}`);
  const r = tags.filter(t => t[0] === 'r');
  if (r.length !== 1) errors.push(`a cairn has exactly one r tag, this has ${r.length}`);
  const url = r.length === 1 && r[0][1] != null ? String(r[0][1]) : '';
  if (r.length === 1 && !isAbsoluteUri(url)) errors.push('the r tag is not an absolute URL');
  const inContent = contentUrls(ev && ev.content, url);
  if (url && inContent.length && !inContent.includes(url)) errors.push('the content has URLs but none of them equals the r URL');
  if (tags.some(t => t[0] === 'alt' && t[1] !== `Cairn: ${url}`)) errors.push('the alt tag is not "Cairn: " followed by the r URL');
  return { ok: !errors.length, url: errors.length ? null : url, errors };
}

// "https://x.org/a)." -> ["https://x.org/a", ")."]: sentence punctuation stuck to the end of a link.
// A closing bracket stays when the link itself opened one, as in https://en.wikipedia.org/wiki/Cairn_(disambiguation).
const CLOSERS = { ')': '(', ']': '[', '>': '<' };
function splitTrailing(tok) {
  const count = (s, c) => s.split(c).length - 1;
  let end = tok.length;
  while (end > 0) {
    const c = tok[end - 1], s = tok.slice(0, end);
    if (`.,;:!?'"`.includes(c) || (CLOSERS[c] && count(s, CLOSERS[c]) < count(s, c))) end--;
    else break;
  }
  return [tok.slice(0, end), tok.slice(end)];
}

// Text is cleaned before it is signed, so that every nostr implementation computes the same id and
// every reader splits it into the same tokens:
// - control characters other than tab, line feed and carriage return are dropped: JavaScript clients
//   (JSON.stringify, as NIP-01 says) and Go clients (nak, grain) write them differently when hashing;
// - line and paragraph separators (U+2028, U+2029, U+0085) become line feeds: Go's JSON encoder
//   always escapes U+2028 and U+2029, so relays built on it (grain, wss://wheat.oslim.dev) compute
//   another id and refuse the event; Apple keyboards type U+2028 for a soft line break;
// - other Unicode spaces (no-break space and the like) become plain spaces and U+FEFF is dropped,
//   because the spec separates tokens by ASCII whitespace only and languages disagree on the rest;
// - half of a broken surrogate pair becomes U+FFFD, as a relay would read it.
const CONTROL_CHARS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g;
const LINE_SEPARATORS = /[\u0085\u2028\u2029]/g;
const UNICODE_SPACES = /[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]/g;
const wellFormed = s => Array.from(s, ch => (ch.length === 1 && ch >= '\ud800' && ch <= '\udfff') ? '\ufffd' : ch).join('');
const INVISIBLE = /[\s\u200b-\u200d\u2060\ufeff]/g;

// From what a person typed: the web links in it, in order, the content to publish, and whether the
// text has anything visible at all (blank). Every link is made a token of its own: punctuation stuck
// to either end of it ("(https://x.org/a)." or "https://x.org/a,") is moved off with a space, so the
// link's token in the content equals the r URL exactly (readers compare whole tokens and never strip
// punctuation; the spec asks publishers for whitespace after a URL). Apart from that and the cleaning
// above, the text is published as typed.
export function parseCairnText(text) {
  const urls = [];
  const clean = wellFormed(String(text || '').replace(CONTROL_CHARS, '').replace(LINE_SEPARATORS, '\n').replace(UNICODE_SPACES, ' ').replace(/\ufeff/g, ''));
  const content = clean.trim().replace(/[^\t\n\r ]+/g, tok => {
    const m = /^([("'<[]*)(https?:\/\/[^\t\n\r ]*)$/i.exec(tok);
    if (!m) return tok;
    const [head, tail] = splitTrailing(m[2]);
    if (!isWebUrl(head)) return tok;
    if (!urls.includes(head)) urls.push(head);
    return (m[1] ? m[1] + ' ' : '') + head + (tail ? ' ' + tail : '');
  });
  return { urls, content, blank: !content.replace(INVISIBLE, '') };
}

// the unsigned cairn for a URL (one of parseCairnText's urls) and its content
export function cairnTemplate(url, content = '', createdAt = Math.floor(Date.now() / 1000)) {
  return { kind: CAIRN_KIND, created_at: createdAt, content, tags: [['r', url], ['alt', `Cairn: ${url}`]] };
}
