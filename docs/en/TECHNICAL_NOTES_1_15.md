# FM2 1.15 beta: technical notes

Base: 1.14 (see TECHNICAL_NOTES_1_14.md), plus HOLD.

## HOLD = virtual sustain pedal
- The Korg firmware already has a sustain: byte `0x20003C6C+0xE2` (current state) and `+0xE3` (wanted state), with
  bit 0x01 for CC 64 from MIDI DIN and 0x02 from USB (`0x0020AD84`). A note-off with sustain on leaves the voice
  active and clears its "key held" flag (`+2`) (`0x0020A5A4`). The voice tick `0x0020AF08` copies the wanted state
  into the current one and, when it becomes zero, releases the held voices (`0x0020A4F5` and `0x0020A405`).
- 1.15 uses **bit 0x04**. Turning HOLD on sets it in E2 and E3; turning it off clears it only from E3, so the release
  is done by Korg and respects a pedal still pressed.
- Sequencer note-offs (source 0x10, `0x0020AC70`) pass r3=0 and are not subject to sustain: the sequencer is not held.
- Buttons: in `panel_button`, with the page closed, UI state 0x12 (FUNC held) and buttons 6 or 7 pressed. The original
  firmware does nothing with FUNC + OCTAVE (verified).
- KEY mode: hook at the entry of `0x0020A78C` (voice assignment: `2de9f04f` → `b.w 0x2020`), only for sources 0x40
  (keyboard), 0x20 (MIDI DIN) and 0x30 (USB) and only with HOLD on.
  - SPEGNE (turns off): if a held voice plays the same note, it is released with the same calls as Korg and the note
    is not played.
  - RIPARTE (restarts) with the arpeggiator (`0x20002E5B` ≠ 0): if no key is held, the held voices are released
    before playing the new note.
  - RIPARTE without the arpeggiator: native behaviour (pressing the note again restarts it).
- State in ITCM: `0x3F14` HOLD, `0x3F15` KEY mode. Not saved.
- Messages: text table `0x3EAC`–`0x3ED0`.

## Tests (55/55)
The 50 of 1.14 plus 5 for HOLD (`verify_115.py`): on and off with the real debouncer, held drone through the native
tick, respect of the CC 64 pedal, RIPARTE with and without the arpeggiator, SPEGNE, MIDI DIN and USB notes, sequencer
untouched. Release: FSK installation 1.12/1.13/1.14 → 1.15, restore and official Korg WAV over 1.15.
