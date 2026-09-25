# GlyphByte

Hand-drawn glyphs that carry bytes. One glyph is one byte.

`draft` `v2` `2026-09-25`

## Abstract

GlyphByte is a way to write a short byte string, typically the first bytes of a Nostr event
id or public key, by hand on any surface, so that a phone camera can read it back. Each byte
is one glyph: a square frame holding an upright icon for the first hex digit and up to four
corner dots for the second. A row of glyphs is underlined, and a fat dot marks the start of
the underline. Readers recover the bytes and, when unsure about a glyph, return several
candidate readings rather than one wrong answer. A client then resolves the bytes on a relay
that supports prefix queries.

## Why

QR codes need a printer and read as noise to people. A GlyphByte row can be drawn with a
marker on a wall, chalk on a sidewalk, or a path mown through a field, and a person can read
it too: "star, star, moon, tree, x, fish". It carries enough bits to identify an event or a
pubkey among everything on a relay, and an extra relay query costs nothing, so a reader may
be uncertain and still be useful.

## The byte

| bits | field | values |
|---|---|---|
| 7..4 | icon | index 0 to 15 into the alphabet below |
| 3 | top-left dot | 1 when present |
| 2 | top-right dot | 1 when present |
| 1 | bottom-right dot | 1 when present |
| 0 | bottom-left dot | 1 when present |

`byte = icon << 4 | dots`. The first hex digit names the icon; the second is the sum of the
dots, reading clockwise from the top-left corner: 8, 4, 2, 1. Every byte has exactly one
drawing and every drawing is exactly one byte. All 256 are in `test-vectors.json` under
`bytes` and drawn in `glyphs.svg`.

## The alphabet

Index is the first hex digit. Every icon is drawn upright, with one or two pen strokes.

| hex | name | drawing | what makes it distinct |
|---|---|---|---|
| 0 | house | a square body under a pointed roof | one point on top, flat base |
| 1 | heart | a heart | two lobes and a point below |
| 2 | drop | a teardrop, point up | one point on top, round body |
| 3 | moon | a crescent opening to the right | curved, opens right |
| 4 | crown | a band with three points on top | three points |
| 5 | arrow | a shaft with an open head, pointing up | open lines, a shaft |
| 6 | box | a small square, about a third of the frame | four corners, no point |
| 7 | triangle | a triangle, point up | three corners |
| 8 | pie | a disc with a wedge missing on the left | round, opens left |
| 9 | tree | a circle on a stem | a circle above a line |
| a | plus | a vertical and a horizontal line crossing | two straight lines, parallel to the frame |
| b | flag | a pole with a triangle flying right from its top | a line with a pennant |
| c | x | two diagonal lines crossing, kept small | two straight lines, diagonal to the frame |
| d | bolt | a zigzag lightning bolt, upright | sharp corners, one open stroke |
| e | star | a five-point star in one stroke | five points |
| f | fish | an oval body with a tail on the left | an oval and a tail |

The icons are pen strokes in a unit box, y down, upright, in `glyphs.json`, together with the
frame geometry: the icon's size relative to the frame (`icon_scale`), where the dots sit
(`dot_offset`, `dot_radius`). Readers are not expected to match these strokes literally; they
define the intended drawing and are what reference implementations render and train from.

No two icons differ only by a rotation or a mirror image: people confuse those forms more
than any other, and a sloppy hand turns them anyway. "Up" for the whole row comes from its
underline (see Reading), so a photo taken sideways reads the same as one taken upright.

## Drawing a glyph

1. **Frame first.** Draw a square. Frames should be about the same size across the row, and
   neighbouring frames should not touch: leave a gap of roughly a third of a frame.
2. **Icon in the middle,** upright, about half the frame's width, one or two strokes, touching
   nothing. Keep the box and the x small, well inside the frame: a big box reads as a second
   frame, and the x's arms point at the corner dots.
3. **Corner dots.** A dot is a filled blob about a sixth of the frame across, placed in the
   corner area between the icon and the frame. A dot must touch neither the frame nor the
   icon: a dot that touches a line becomes part of it and is lost.
4. **Keep points pointy.** The house's roof, the crown's points and the triangle's corners are
   the difference between those icons and a box or a band.

## Drawing a row

1. Draw the glyphs left to right in byte order, each in its own frame, on one line.
2. **Underline the whole row** with one stroke, a little below the frames, extending past the
   first and last frame.
3. **Start dot:** a solid dot at the start end of the underline, about a quarter of a frame
   across. The underline tells a reader which way is up; the dot tells it where to start.

A row without an underline is still readable: its glyphs show which way is up. A reader MUST
warn when it had to decide "up" from the glyphs alone, and SHOULD return the runner-up
orientation's reading as a candidate when the glyphs do not agree clearly.

Recommended lengths for Nostr references: **6 bytes** (48 bits) for an event id or pubkey
prefix in ordinary use, **8 bytes** for something meant to stay unambiguous for years, **4
bytes** only where the relay is small. With N candidate objects on a relay the chance that a
random one collides with a k-byte prefix is about N / 2^(8k): for N = 10^8, 4 bytes gives a
2% chance of a collision, 6 bytes about 4 x 10^-7, 8 bytes about 5 x 10^-12.

## Reading

A reader takes a photo and returns byte sequences. The reference readers in this repository
work like this, and a compatible reader MUST produce the same bytes for the same drawing:

1. Find the frames: closed squares of ink that contain ink, taken in any perspective.
2. Find the row: the frames that share a line and a smooth size trend.
3. Find the underline: a long stroke parallel to the row just outside it, and its fat end.
   "Up" is the side of the underline the frames are on. A photo is never mirrored, so reading
   runs a quarter turn clockwise from up; the dot confirms where the row starts.
4. Check "up" against the glyphs. Every icon except box, plus and x has a top, so the glyphs
   of a row vote on how the row is turned. When the vote clearly disagrees with the underline
   (a ruled line on lined paper, a paper edge), the glyphs win; when it is close, both
   readings are returned as candidates. Without an underline the glyphs alone decide.
5. Rectify each frame into an upright patch from its four corners, and classify the icon
   and each of the four corner dots.
6. Assemble bytes. Where a glyph is uncertain, keep the alternatives and return the most
   probable whole sequences, ranked, so the client can query all of them.

Readers MUST NOT silently drop a glyph they could not read; a missing byte shifts every later
byte. They SHOULD report how many frames they found and any assumption they made.

There is no checksum by design. A wrong candidate simply matches nothing on the relay, and
the person holding the phone can see the alternatives.

## Resolving on Nostr

The bytes are a prefix. A client queries a relay with the prefix in the `ids` list and, for
pubkeys, in the `authors` list, for example:

```
["REQ", "gb", {"ids": ["e8ed3798c6ff"]}, {"authors": ["e8ed3798c6ff"], "kinds": [0]}]
```

Prefix matching in `ids` and `authors` was part of the first NIP-01 and was later removed
from the text; some relay software still honours it. As of 2026-09, grain honours prefixes
of any length in both fields; strfry answers `CLOSED` with "filter item too small"; khatru
returns nothing. A client SHOULD test a relay once by fetching one event and asking for it
again by an 8-character prefix, and tell the user when a relay cannot answer prefix queries.

All candidate readings can go in one REQ. Results are shown with the author's profile, and
the person confirms which one they meant. A prefix is not an identity: a client MUST treat
the resolved full id or pubkey as the reference, never the drawn bytes.

Encoding a NIP-19 entity: `npub` and `nprofile` encode the pubkey, `note` and `nevent` the
event id. An `naddr` has no event id; a row for it encodes the author's pubkey and the
reader's user picks the event by kind and `d` tag among the author's addressable events.

## Test vectors

`test-vectors.json` holds:

- `bytes`: all 256 bytes with the icon, the dots and a one-line description.
- `sequences`: hex strings with their glyph descriptions and a rendered reference row
  (`vectors/row-<hex>.png`), drawn cleanly by the reference renderer.
- `photos`: real photographs of hand-drawn rows with the bytes they carry. v2 starts with none;
  photographs are added as people draw them.

A conforming encoder MUST reproduce `bytes` and the descriptions in `sequences`. A conforming
reader SHOULD return the `expected` bytes of every entry in `photos` as its top reading, and
MUST include them among its candidates.

## Reference implementations

- Python package `glyphbyte`: encoder, renderer, reader, relay lookup, training of the
  classifier from synthetic data. `glyphbyte encode HEX` renders a row; `glyphbyte decode
  PHOTO` reads one.
- JavaScript, in `napplet/src`: the same reader and encoder with no dependencies, bundled
  into a single-file napplet (NIP-5D) that runs on the phone and queries a relay.

## Security considerations

Anyone can draw anything. A GlyphByte row is a pointer, not a proof: clients show what the
prefix resolves to, and the person decides whether that is what they were looking for. A
short prefix on a large relay may resolve to several objects; clients MUST show all of them.
Readers process photos on the device; nothing in this specification requires sending an
image anywhere.

## Changes from v0.1

v0.1 (2026-09-22) spent its eight bits on 16 pictograms, 4 rotations, outline or filled, and
a square or circle frame. v2 keeps one byte per glyph and replaces the parts people found hard
to draw:

| v0.1 | v2 | why |
|---|---|---|
| rotation, 2 bits | corner dots | people confuse rotated and mirrored forms more than any other difference, and drawing a pictogram sideways is slow |
| fill, 1 bit | corner dot | a scribbled fill is slow and smears in chalk and in fields |
| square or circle frame, 1 bit | corner dot | one frame shape to remember |
| hollow letters T, U, L; bookmark, trapezoid, chevron, cloud, snowman | tree, plus, flag, bolt, star, fish, box, x | 6 to 8 corners each, or too close to another icon once rotation is gone |
| pac-man | pie, facing left | a generic name, and it now opens away from the moon |
| mountain | triangle | it is a triangle |

The design follows published evidence on what people draw easily (lines, circles, crosses and
squares are copied by age 4, diagonals and diamonds later), on what they confuse (mirror and
rotated forms), on counting (up to four items are seen at a glance), and on markers that
people draw by hand (blobs that never touch their region's edge). The research notes and the
comparison are in `research/v2/` in the repository.

## License

This specification, the GlyphByte alphabet and its canonical shapes, the sheet, the test
vectors and the reference implementations are licensed under the Creative Commons
Attribution-ShareAlike 4.0 International License (`LICENSE` in the repository,
https://creativecommons.org/licenses/by-sa/4.0/).
