# Technical notes 1.17: scales, humanize, random octave

## Scale (global, not saved)
State in ITCM: 0x3F30 scale on, 0x3F31 scale 0..14, 0x3F32 root 0..11 (C..B), 0x3F33 option "live sequences in
scale". At power-on: off, MAG, DO (C), option NO. Not saved: no safe space was found in the Korg global settings.

Correction (`quantize`): pitch class of the note relative to the root; if it is not in the scale mask (table at
0x1F70, bit i = i semitones above the root) the minimum distance d = 1..11 is searched, first above then below, so on
a tie the note above wins. Limits 0..127 respected.

Scales: CROM, MAG (Ionian), MIN (Aeolian), ARM (harmonic minor), DOR, FRI, LID, MIS, PMA (major pentatonic), PMI
(minor pentatonic), BLU (hexatonic blues), TON (whole tone), HIR (Hirajoshi 0 2 3 7 8), INS (In Sen 0 1 5 7 10),
ARA (double harmonic 0 1 4 5 7 8 11).

## Hooks
| Address | Original | New | Purpose |
|---|---|---|---|
| 0x20AA8A | `adds r4,#5; uxtb r0,r4` | BL 0x203C | keyboard note-on: corrected note in r4/r0, saved per key (0x1800, 32 bytes) |
| 0x20AACA | `adds r4,#5; uxtb r6,r4` | BL 0x2040 | keyboard note-off: note saved for that key |
| 0x20AB2C / 0x20AB64 | prologue | B.W 0x2044 / 0x2048 | MIDI DIN note-on/off, map input note → played note at 0x1820 (128 bytes) |
| 0x20ABC0 / 0x20ABF8 | prologue | B.W 0x204C / 0x2050 | USB MIDI, map at 0x18A0 |
| 0x20BA6E | `strb.w r0,[r7,r4,lsl #2]` | BL 0x2054 | sequencer: note saved in the slot (0x20003DC4) = played note |

The maps are in the original FF padding of the ITCM (0x1800..0x191F, 0xFF = no note), never written by the image.

Everything downstream gets the corrected note: voice (0x20A78C), MIDI echo (0x207BD4/0x207C74), arpeggiator note list
(0x20A4A8), HOLD and **recording**: the recorder 0x20B480 (slot at 0x20003D54) gets the note passed to the voice;
real-time recording then writes the slot into the pattern (0x20B384). Verified in the emulator by calling the native
functions (v117/recording_note).

Sequencer: the step note is transformed when it enters the slot; note-on (0x20AC54), MIDI echo and note-off
(0x20B774 → 0x20AC70, and the voice release 0x20A4F4) use the slot, so they always match. The pattern is never
modified. Two chord notes that end up on the same scale note behave like a double note in the step (the Korg voice
manager reuses the voice).

## Humanize and random octave (per pattern, in PRB3)
Bit 7 of the probabilities of steps 5–8 (humanize) and 9–12 (octave), 0..15. Applied in the same sequencer hook
(0x20BA6E), only to sequencer notes:
- humanize: velocity ± 3·level (level 15 = ±45), limited to 1..127;
- octave: probability level/15 per note, up or down at random (half and half); if it would leave 0..127 it jumps the
  other way. With the scale on, the note stays in scale (the octave jump keeps the pitch class).
Generator: the native PRNG 0x2094A4, as for the probabilities.

## Interface
FUNC+EDIT page, modes P → C → GL → HU → OC → SC → tn (OCTAVE +/−). HU/OC: slider 0..15 ("HU 07"). SC: slider =
scale ("SC MAG ON", "--" if off), key 16 toggles the option ("SEQ SI"/"SEQ NO"). tn: slider = root ("tn REb"; the
sharp has no glyph on the display, so flats). FUNC + SAVE (outside the page): scale on/off ("SCALA ON"/"SCALA OFF");
the release of SAVE goes to the Korg code as before. In the emulator the RAM after FUNC+SAVE matches the original
apart from the display buffers.

## Tests (verify_117.py)
scale_keyboard (15 scales × 12 roots × 27 keys, with MIDI echo; scale off identical to the original),
release_after_change, midi_in (DIN and USB, 128 notes), sequencer_live (option off identical to the original),
humanize_octave, recording_note, panel_modes, func_save.
