# GlyphByte

Hand-drawn glyphs that carry bytes. One glyph is one byte.

`draft` `v0.1` `2026-09-22`

## Abstract

GlyphByte is a way to write a short byte string, typically the first bytes of a Nostr event
id or public key, by hand on any surface, so that a phone camera can read it back. Each byte
is one glyph drawn inside a frame. A row of glyphs is underlined, and a fat dot marks the
start of the underline. Readers recover the bytes and, when unsure about a glyph, return
several candidate readings rather than one wrong answer. A client then resolves the bytes on
a relay that supports prefix queries.

The alphabet was designed so that every glyph stays distinct from every other glyph in all
four rotations and whether it is filled or not, using only features that survive sloppy
handwriting: silhouettes and counts, never small appendages.

## Why

QR codes need a printer and read as noise to people. A GlyphByte row can be drawn with a
marker on a wall, a sticker, a menu, a cast, and a person can read it too: "trapezoid,
trapezoid, crown, heart, snowman, pac-man". It carries enough bits to identify an event or a
pubkey among everything on a relay, and an extra relay query costs nothing, so a reader may
be uncertain and still be useful.

## The byte

| bits | field | values |
|---|---|---|
| 7..4 | symbol | index 0 to 15 into the alphabet below |
| 3..2 | rotation | quarter turns **clockwise** from the upright glyph: 0, 90, 180, 270 degrees |
| 1 | fill | 0 outline, 1 filled |
| 0 | frame | 0 square frame, 1 circle frame |

`byte = symbol << 4 | rotation << 2 | fill << 1 | frame`. Every byte has exactly one drawing
and every drawing is exactly one byte. The 16 x 4 x 2 x 2 = 256 combinations are in
`test-vectors.json` under `bytes`.

## The alphabet

Index is the high nibble. "Upright" is the orientation drawn in `glyphs.svg` under rotation 0.

| index | name | upright description | what makes it distinct |
|---|---|---|---|
| 0 | house | a square with a pointed roof | one point, flat base |
| 1 | chevron | a house whose base is cut by a chevron, an upward notch | pointed both ends, same direction |
| 2 | bookmark | a rectangle with a chevron cut into its bottom | flat top, notched bottom |
| 3 | crown | a rectangle with three points on top | three points |
| 4 | drop | a teardrop, point up | one point, round body |
| 5 | tee | the letter T in block form | a bar on a stem |
| 6 | u | the letter U in block form | one open side, square corners |
| 7 | mountain | a triangle whose apex is split into two peaks | two peaks, slanted sides |
| 8 | arrow | a chevron head on a shaft, pointing up | a shaft |
| 9 | heart | a heart | two lobes and a point |
| 10 | crescent | a thick crescent lying like a bowl, horns up | thin, curved, open |
| 11 | cloud | a dome with three scallops underneath | scallops |
| 12 | snowman | a small circle merged onto a larger circle, small one on top | two round lobes of different size |
| 13 | l | the letter L in block form | one corner, two unequal arms |
| 14 | trapezoid | narrow top, wide bottom | four corners, two parallel sides of different length |
| 15 | pacman | a disc with a wedge bitten out of the top | a fat disc with a bite |

The canonical shapes are polygons in a unit box, y down, upright, in `glyphs.json`. Readers
are not expected to match these polygons literally; they define the intended silhouette and
are what reference implementations render and train from.

Rotation is a property of the glyph, not of the photo: readers determine "up" from the row's
underline (see Reading), so a photo taken sideways reads the same as one taken upright.

## Drawing a glyph

1. **Frame first.** Draw a square or a circle. Frames should be about the same size across the
   row, and neighbouring frames should not touch: leave a gap of roughly a third of a frame.
2. **Glyph inside.** Draw the glyph in the frame's middle at about six tenths of the frame's
   width, without touching the frame. Rotate it as the byte requires.
3. **Fill.** For a filled byte, scribble the whole inside so it reads as a solid blob. For an
   outline byte, one clean stroke. A filled glyph must keep its silhouette; that is why the
   alphabet has no glyph whose rotation cue lives inside it.
4. **Keep points pointy.** The house's roof, the crown's points and the mountain's peaks are
   the whole difference between those glyphs and a square or a rectangle. Make points at
   least a third of the glyph tall.
5. **Snowman:** the small circle must be clearly smaller, about half the diameter of the big
   one, or it reads as a pac-man.

## Drawing a row

1. Draw the glyphs left to right in byte order, each in its own frame, on one line.
2. **Underline the whole row** with one stroke, a little below the frames, extending past the
   first and last frame.
3. **Start dot:** a solid dot at the start end of the underline, about a quarter of a frame
   across. The underline tells a reader which way is up; the dot tells it where to start.

A row without an underline is readable only if the photo is upright and left to right; a
reader MUST warn when it had to assume that. A row with an underline but no dot has two
readings, forward and reversed; a reader SHOULD return both.

Recommended lengths for Nostr references: **6 bytes** (48 bits) for an event id or pubkey
prefix in ordinary use, **8 bytes** for something meant to stay unambiguous for years, **4
bytes** only where the relay is small. With N candidate objects on a relay the chance that a
random one collides with a k-byte prefix is about N / 2^(8k): for N = 10^8, 4 bytes gives a
2% chance of a collision, 6 bytes about 4 x 10^-7, 8 bytes about 5 x 10^-12.

## Reading

A reader takes a photo and returns byte sequences. The reference readers in this repository
work like this, and a compatible reader MUST produce the same bytes for the same drawing:

1. Find the frames: closed rings of ink that contain a compact blob of ink. Square or circle
   is decided from the frame's shape; it is the frame bit.
2. Find the row: the frames that share a line and a smooth size trend.
3. Find the underline: a long stroke parallel to the row just outside it, and its fat end.
   "Up" is the side of the underline the frames are on; reading order starts at the dot.
4. Rectify each frame into an upright patch and classify the glyph, its rotation and its
   fill.
5. Assemble bytes. Where a glyph is uncertain, keep the alternatives and return the most
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

- `bytes`: all 256 bytes with symbol, rotation, fill, frame and a one-line description.
- `sequences`: hex strings with their glyph descriptions and a rendered reference row
  (`vectors/row-<hex>.png`), drawn cleanly by the reference renderer.
- `photos`: real photographs with the bytes they carry. `vectors/photo-01.jpg` is a marker
  drawing of `e8ed3798c6ff` in a notebook, the first six bytes of the author's pubkey; the
  reference readers return it as the top reading.

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

## License

This specification, the GlyphByte alphabet and its canonical shapes, the sheet, the test
vectors and the reference implementations are licensed under the Creative Commons
Attribution-ShareAlike 4.0 International License (`LICENSE` in the repository,
https://creativecommons.org/licenses/by-sa/4.0/).
