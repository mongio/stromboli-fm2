# FM2 1.16 beta: technical notes

Base: 1.15. New: generated arpeggio modes and arpeggio on the MIDI output.

## Korg arpeggiator (analysis)
- Type saved in the pattern at byte 70 (69 and 71 nearby, 71 = DIV); type requested at runtime at `0x20003E11`,
  active type at `0x20003E10`; copy for the interface at `0x20002E5B`. The TYPE knob (ADC parameter 7) uses the index
  `(v·5)>>6` (`0x20012EA0`).
- The types are tables in SRAM: pointers at `0x2000B420`. Each table has a header (number of steps, bit 8 = reverse
  order) and one step per word, with one nibble for each of the 6 places of the chord sorted by pitch (3 = base
  octave, 4 = +1, 5 = +2). The arpeggio voices are at `0x200031D4` (6 × 0x34, +4 = 1 if active, +7 note,
  +0x13 velocity).
- The Korg pattern validator does not check byte 70: a type ≥10 would make the Korg firmware read past the table.

## New modes
- The knob gives 17 positions, `(v·17)>>7`: 0–9 are the Korg types, 10–16 the new modes 1–7 (UPdn1–3, Conv, dIvr,
  PEdL, Chrd). Hook in the ADC handler already hooked: for a new mode it passes Korg the value of Rise1 (13), for Korg
  types the smallest value that the Korg mapping turns into the wanted index. Works for the panel and MIDI CC.
- **Compatibility**: byte 70 always stays a valid Korg type (Rise1 for the new modes). The new mode goes into the
  **PRB3** block: tag `0xA3`, bit 7 of the probabilities of steps 1–4. PRB3 has the same format as PRB2 (the
  probabilities use 7 bits); PRB2 blocks are read and converted at the first edit.
- **Generated table** in ITCM at `0x3C00` for the mode and the number of notes (1–6). While a new mode is active,
  entry 1 of the Korg table points there; otherwise it goes back to `0x2000B57C` (Korg Rise1).
- Update: at the entry of the tick `0x0020C40C` and at the entry of `0x0020BDFC` (a voice enters the arpeggio). It is
  regenerated only when the mode or the number of notes change.
- Names: the text hook `0x0020591C` replaces "tYP Rise1" (`0x2000AC82`) with the name of the active mode (table at
  `0x3D80`).

## Arpeggio on MIDI OUT
- The arpeggio notes go through `0x002097E4` (voice, note, velocity), used only by the arpeggiator, plus the first
  note at start (`0x0020BDFC` with +2 = 0xFF, read from the voice). Hook at the entry: a note-on is queued; when a new
  step starts (`0x0020C1F4`, counter `0x3F22`) the note-offs of the previous step's notes are queued.
- Note-offs also when a voice leaves the arpeggio (+4 ≠ 1), checked at the tick and in the MIDI service.
- SPSC queue of 16 events at `0x3F40`, emptied at the entry of the native MIDI OUT service `0x00207F2C` (main loop)
  with the native functions `0x00207BD5` / `0x00207C75` (DIN, USB, channel, tracking of the notes sent).
- With the arpeggiator on (`0x20003E11` ≠ 0) the MIDI echo of the keyboard (BL at `0x0020AA8E`) and that of the
  sequencer (BL at `0x0020A732`, source 0x10) are skipped; the native note-offs stay (Korg sends the off only for the
  notes actually sent).
- HOLD: the RIPARTE rule with the arpeggiator now uses `0x20003E11`.

## Tests (62/62)
The 55 of 1.15 plus 7 of 1.16 (`verify_116.py`):
- 42 cases of mode × number of notes compared with the model, plus the chord;
- 128 knob positions, with names and MIDI CC;
- Korg compatibility: a pattern with a new mode plays Rise1 on the original image, and the Korg table is restored;
- PRB2 → PRB3 conversion;
- arpeggio notes on MIDI, on/off pairs and release when the arpeggio stops;
- keyboard echo with the arpeggiator on and off.

Release: FSK installation from 1.12/1.13/1.14/1.15, restore and official Korg WAV.
