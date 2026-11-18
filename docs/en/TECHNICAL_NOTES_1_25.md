# Technical notes 1.25: three parts (split and layer)

Base: 1.24. Sources `src/fm2_125.S` (ITCM), `src/fm2_125_sram.S` (SRAM), `src/fm2_125_flash.S` (flash, unchanged).
New tests `verify_125.py`; full verification `verify_patch.py` and `verify_release.py`.

## Korg engine (analysis)
- DSP voice allocation: `0x00209574(source, note, velocity)`. State `VM = 0x200031C8`: `+7` mode (table
  `0x2000B398`, 10 bytes per mode), `+8` voices per note (1, or 2 / 3 with UNISON), `+0x27C` round-robin index.
  Six `0x34`-byte records at `VREC = 0x2000330C`: `+0` time (`0x00204740`), `+4` state (0 free, 1 on,
  5 releasing), `+5` note, `+6` pitch, `+0x10` index of the voice within the note, `+0x13` velocity. For each
  voice of the note: first free record, else a releasing one, else record number k. Then
  `0x0020E814(voice, pitch, velocity, pan)` (BL at `0x00209746`).
- Arpeggiator: `0x002093FE(source, pitch, velocity)` → mask of the voices started, same number of voices per
  note (BL at `0x00209488`).
- Note-off: `0x00209870(source, note)` releases every record that is on with that note
  (`0x002094E6(mask)` → `0x0020E7C8(voice)`) and marks it as releasing.
- Voice start: `0x0020E6DC(voice, pitch, velocity, pan)`, at once or later from the service `0x0020E8C2` when
  the voice is still sounding (`0x0020E814` fades it and leaves the start pending). At every start:
  `0x0020E518(destination 0x200055A4, program 0x20004F5C, macros 0x20005358)` copies the 128 bytes of the
  program and applies the EG knobs (macros `+0..+3`) to carriers or modulators according to the algorithm,
  **read from the live program** (`0x20004F5C+0x6E`, not from the source), and turns off the operators whose
  macro `+5..+10` is 0. Then transpose, LFO (copied into the voice), `0x0020DF14`. The voice (624 bytes) never
  reads the program again: rendering does not access `0x20004F5C` (checked with a read watch).
- Voice gain: `+0x38` left, `+0x3C` right, written at the start from the pan (sum `0x20000`), used by the
  rendering as linear gains (checked: halving them halves the level).
- Program bank in RAM: pointer at `0x2001D090` (64 × 128 bytes, same format as the live program; name in
  bytes 118–127).

## More of the Korg engine, used by the second part
- `0x0020DF14` (called by `0x0020E6DC`, fifth argument on the stack = voice) writes the LFO depths of the
  program into the voice: `+0x10` pitch sensitivity (table `0x2000B84C`: 0 10 20 33 55 92 153 255), `+0x11`
  pitch depth (PMD × 165 >> 6), `+0x12` amplitude depth. The rendering reads them from the voice at every
  sample (`0x11F2`, `0x11FE`, `0x121A`): writing them is enough to change vibrato and tremolo.
- MIDI dispatcher `0x00207D98(source, message)`, reached through the veneer `0x20014F64`: it only takes the
  channel of the volca (`0x200029FC+9`) and handles 0x80, 0x90, 0xB0 (CC 6, 64, 98–101, 120–124 and those of
  the table `0x2000B377`), 0xE0. CC 1, aftertouch and Program Change are dropped.
- MIDI notes: `0x0020AB2C(note, velocity)` → logical manager `0x0020A78C(source 0x20, …)`, which knows a held
  note by its number alone (same note = retrigger). This is why the notes of the channels of b and C do not go
  through the logical manager.
- Arpeggiator on = `pattern+0x45` bit 0 and `pattern+0x46` ≠ 0 (`0x0020C8DE`).
- Voice record `+0x18`: `0x00209574` writes `FF` at every allocation; read only in the arpeggiator's copy.

## State (ITCM `0x3900`, 128 bytes)
Sixteen bytes per part (A `+00`, b `+10`, C `+20`): `+0` program (0 OFF, 1–64; not used for A), `+1` low note,
`+2` high note, `+3` octave 0–6 (3 = none), `+4` pan 0–14 (7 = centre), `+5` level 0–100, `+6` voices 0 (free)
/ 1–6, `+8` low velocity, `+9` high velocity, `+10` fade 0–7 (widths 0 8 16 24 32 48 64 96).
`+30` active (a program in b or C, the channels on, or a parameter of A away from its default), `+32` part of
each DSP voice (6), `+38` channel switch, `+39` forced part + 1 (MIDI), `+3A` direct start (MIDI), `+3B`
number of parts of the note being started, `+3C` those parts (3), `+40` their gain (3 × 16 bit: level × fade,
25500 = full), `+48` gain of each DSP voice (6 × 16 bit), `+54` modulation wheel per part (3), `+57`
aftertouch per part (3), `+5A` pitch depth, `+60` amplitude depth, `+66` pitch sensitivity of the program of
each DSP voice (6 each).

## Hooks
| Where | Was | Now | Function |
|---|---|---|---|
| `0x00209574` | `push.w {r4-r11,lr}` | `b.w 0x2074` | `multi_dsp_on`: voices per note = parts that play the note |
| `0x002093FE` | `push.w {r0-r2,r4-r11,lr}` | `b.w 0x2078` | `multi_arp_on`: the same for the arpeggiator |
| `0x00209746` | `bl 0x0020E814` | `bl 0x207C` | `multi_call_a`: part and gain of the voice; mark of the record |
| `0x00209488` | `bl 0x0020E814` | `bl 0x2080` | `multi_call_b`: part and gain of the voice (arpeggiator) |
| `0x0020E6F0` | `bl 0x0020E518` | `bl 0x2084` | `multi_patch`: program, octave and pan of the voice |
| `0x0020E79E` | `bl 0x0020DF14` | `bl 0x2088` | `multi_gain`: LFO depths, controllers, gain of the voice |
| `0x00209870` | `push.w {r3-r11,lr}` | `b.w 0x208C` | `multi_dsp_off`: the Korg note-off leaves the channel notes |
| literal `0x20014F64` | `0x0020FC4D` (1.21) | `midi_multi` | before the Program Change handler and the Korg dispatcher |

With `+30` = 0 the hooks run the original instruction; `multi_gain` also copies the three LFO depths of the
voice into the state and writes them back unchanged (controllers at zero).

## How it works
- `multi_match(note, velocity)`: the parts that play the note, in order, with their gain. A part plays when it
  is on (A always, b and C with a program), the note is in its keyboard zone (not checked for the part forced
  by its MIDI channel, which is then the only one), the velocity is in its velocity zone and its fade is not
  zero.
- `multi_fade`: width W; x = distance from the nearest inner edge (dL when > 1, dH when < 127), limited to W;
  gain = 255 · x (2W − x) / W². Two parts that cross with the same width keep the power between 1.00 and 1.13.
- `multi_dsp_on`: no part → the note is silent. Then `multi_limit` and, when the Korg voices per note are 1,
  `multi_steal` (also with a single part: with layers and channels every record can be on without the Korg
  logical manager having freed one); with more parts `VM+8` = number of parts for the duration of the original
  call. With UNISON `VM+8` is left alone.
- `multi_steal(n)`: while fewer than n records are not on, the oldest one that is on is marked as releasing;
  the Korg allocation takes it and the voice restarts with the original fade.
- `multi_limit`: for every part of the note with a limit, while the records of that part that are on equal the
  limit, the oldest one is released with `0x002094E6`: the same state as a note-off of that note.
- `multi_call_a / b`: part and gain of the voice from the list of the note (UNISON voices beyond the list take
  the first one). A voice started by a part channel marks its record: `+0x18` = `D0` + part.
- `multi_patch` (r7 voice, r5 pitch, r4 pan of the caller): octave × `0xC00` into the pitch, folded by octaves
  into 0..`0x7F00` (only when the octave is not zero); pan = value × 9 + 1 (7 = untouched); for b and C the
  program from the bank, macros = live EG knobs + every operator on, with the algorithm of the part's program
  written to `0x20004F5C+0x6E` while `0x0020E518` runs.
- `multi_gain`: calls `0x0020DF14`, then keeps the LFO depths of the program of the voice, applies the
  controllers (`multi_ctrl_voice`) and, with the parts active, multiplies `+0x38` and `+0x3C` by gain / 25500.
- `multi_ctrl_voice`: pitch depth = program + 2 × max(wheel, aftertouch); amplitude depth = program + 2 ×
  aftertouch; pitch sensitivity at least 33 (PMS 3) while a controller is up. At zero it writes the values of
  the program back.
- `midi_multi` (reception on, source ≤ 2): channel of the volca → part A; with the channels on the next one →
  b, the one after → C (`multi_next_ch`: +1 modulo 16, channel 10 skipped). CC 1 and 0xD0: controller of the
  part (of all of them with the channels off), then every voice. With the channels on: notes on the channel of
  the volca → Korg dispatcher with part A forced; on the channels of b and C (with a program): note-on →
  `0x00209574` with the part forced and the arpeggiator switch of the pattern off for the duration of the
  call; note-off → `multi_release` (records that are on with that mark and that note, `0x002094E6`,
  releasing); Program Change → program of the part; CC 120 / 123 → every note of the part. Everything else
  goes to the Program Change handler in flash (`0x0020FC4C`) and to the Korg dispatcher.
- `multi_dsp_off`: for the duration of the Korg note-off the records that are on with mark `D1` / `D2` have
  state `0x41`.

## Storage
Record in bytes 108–111 of steps 11–16 (never read or written by Korg): `A7`, 21 bytes of bit stream (for
every part the fields with 7 7 7 3 4 7 3 – 7 7 3 bits, least significant first, then the channel switch: 166
bits), check = xor of the 22 bytes ^ `5A`; the last byte is free. Missing, invalid or with an out-of-range
value = parts off. The record of the first 1.25 build (`A6`, six bytes per part) is still read.

## Pages
21 modes: PA (18), Pb (19), PC (20) after CR. Keys 1–11 = Pr Lo Hi Oc Pn LE Vo Ch dL dH dF (keys 12–16 do
nothing; a step chosen in another page counts as key 1), slider = value. Readouts: `APr LIVE`, `bPr OFF`,
`b05 Disto`, `bLo DO  4`, `bOc -1`, `bPn L3`, `bLE 050`, `bVo --`, `bCh OFF` / `bCh 03` (channel of the part),
`bdL 064`, `bdF --` / `bdF 32`. Changing Ch sets the controllers of the parts back to zero.

## Space
ITCM: code `0x2000–0x2D68`, state `0x3900–0x397F`. SRAM: up to `0x200192DC` (11820 bytes of 23376).
Flash: unchanged (the Program Change handler stays, called by `midi_multi`).

## Tests (`verify_125.py`, 15 groups)
Parts off: voices, records and samples identical to 1.12. Program of the part identical to the Korg voice.
Split, layer (sum of the voices), steal, voice limit (equal to note-off + note-on). Octave, pan, level.
Velocity: zones, fade gains for every width, power of the crossfade, a part at zero uses no voice. Channels:
same note on three channels with separate note-offs; voice of the channel identical to the Korg voice of the
program; channels for every volca channel (10 skipped, wrap after 16); Program Change and CC 123 per part;
arpeggiator on; limits and steals; 600 random events on three channels with no stuck note. Controllers: wheel,
aftertouch, new voice, back at zero identical, per part with the channels, Korg sustain intact. Pages, record
(also that of the first 1.25 build), sequencer.

## Known limits
- Channels of b and C: no sustain, pitch bend, arpeggiator, MIDI OUT, sequencer recording.
- With the arpeggiator on, its voices can take those of a channel note.
- The voice limit does not apply to the notes of the arpeggiator.
- No LFO crossfade between parts (it needs a periodic update of the gains).

## Test on the instrument
Emulator only so far.
