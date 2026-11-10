# Technical notes 1.21: simpler chain, FUNC during a chain, copy, REC FISSO, Program Change, effect in the pattern

Base: 1.19. Sources `src/fm2_121.S`, `src/fm2_121_flash.S`; tests `verify_121.py`,
`verify_121_more.py` (`fx_per_pattern`, `add_keeps_step`).

## Effect type in the pattern
- The Korg firmware already saves in the pattern the reverb on/off (bit 2 of byte 0x45) and level (0x49); the chorus
  level is byte 0x48. The STROMBOLI type (`0x3F80`: 0 REVRB, 1 DELAY, 2 LOFI) was global.
- It is now in bit 7 of the probabilities of steps 13–14 of the PRB3 block (field `set_bits`/`block_bits`, first
  index 12; steps 15–16 are still free). The FX page writes the field into the pattern in use.
- Every pattern load (`0x00208900`, 5 calls: `0x00208C7C`, `0x00208CCE`, `0x0020900C` through `chain_load`,
  `0x00209144`, `0x002092AE`) goes through `load_fx` (flash table entry +1C), which after the load sets `0x3F80`
  from the field. No PRB3 block (Korg or older patterns) = REVRB. The type change uses the 1.18 fade and clear.
- dt and Fb stay global (no bits left). Back on the Korg firmware the pattern stays valid (the bits are ignored).

## Adding to a chain without restarting
- `chain_force` called `0x0020C5D6`, which with the chain active sets the pending step (`0x200031A3` = `CLOCK+0xB`)
  to 0xFF: the pattern restarted at every key added (also with CC in 1.19).
- Now, while the sequencer plays, the step is put back: the pattern goes on and the chain moves on at the end of the
  loop. When stopped it stays 0xFF (PLAY starts from the beginning).

## Space
ITCM up to `0x3BD4` (limit `0x3C00`), flash up to `0x0020FF88` (limit `0x0020FFF0`).

Base: 1.19. Sources `src/fm2_121.S` (ITCM) and `src/fm2_121_flash.S` (flash at `0x0020FC40`).
Tests: `verify_121.py` and `verify_121_more.py`; full check `verify_release.py` 95/95.

## Chain: CR only
- Page CR (mode 10; now 11 modes, P → … → Fb → CR → P). The slider writes the same value to `0x1D00+0` (free chain)
  and `+2` (recording on a chain). CR ON → OFF: `+4` = 0 and native chain flag `0x20003E34+0x15` = 0; the current
  pattern goes on.
- Removed: pages CH and CC, capture (`cap_wrap`, hook `0x00208E30`), capture list `0x1C80`, `chain_msg`
  ("CATENA nn"). In 1.19 "CC REC" was capture state 2 (CC ON then PLAY) and "CATENA nn" the message at STOP after a
  capture.
- Key 16 on page CR: `0x1D0F` REC AUTO (0) / REC FISSO (1), messages 28/29; with REC FISSO the page shows
  "CR ON   F".
- State `0x1D00`: +0E pattern played before + 1 (0 = none; written in `chain_next`), +0F REC FISSO.

## REC with CR ON, and saving
- In the Korg firmware REC does nothing while a chain plays (also with the sequencer stopped): this was the
  "REC no longer selectable" of 1.19. With CR ON the panel's "chain active" query answers "no" to the REC handler
  (see below).
- `trans_hook`: with CR ON and a chain, when REC goes from on to off (by hand, after a motion) or PLAY stops with REC
  on, `save_if_modified(CLOCK+6)` (native WRITE `0x20815C` only if the pattern changed).

## FUNC during a chain
- The panel asks "chain active?" through the SRAM veneer `0x200150E0` (literal `0x200150E4`, original
  `0x0020C5D3`: `ldrb r0, [r0, #0x15]`). The literal now points to `chain_q` (ITCM). With CR ON it answers 0 when
  the caller (LR) is one of: REC `0x20011AB0`, FUNC + keys `0x200111D8`, FUNC + MEMORY `0x20011F3C`, WRITE target
  `0x20010B80`, FUNC + PLAY `0x20011A28`, FUNC + EDIT `0x2001207C`, FUNC + SAVE `0x20011D70`. Otherwise (and with
  CR OFF) it answers as Korg.

## Pattern copy (FUNC + MEMORY)
- In `chain_q`, caller FUNC + MEMORY: `copy_previous`. Conditions: REC on, previous pattern known and different
  from the current one, current pattern empty (bytes +24..+29 gates and +43..+107 motion of all 16 steps zero).
- 1920 bytes copied from the RAM bank (`[0x2001D08C] + n·1920`) to the pattern in use `0x2001E12C`, native WRITE
  on the current pattern, reload with `0x208900` keeping the step (`CLOCK+0xB`), message "CPY 03-04". Otherwise
  Korg WRITE.

## REC FISSO
- BL at `0x00209062` (was `0x00208598`, REC off at the end of a motion loop) → flash table entry +18
  (`motion_end`): with `0x1D0F` = 1 it does nothing.

## Program Change in
- The MIDI message dispatcher `0x00207D98` handles only 0x80, 0x90, 0xB0, 0xE0: Program Change is ignored by the
  Korg firmware (checked in the emulator).
- Veneer literal `0x20014F64` (was `0x00207D99`) → flash table entry +0C (`midi_in`): for 0xCn it checks message
  reception (`0x20002F4C+0x1C4`) and the channel (`0x00205C9C`), then `0x200133A4(0x20002A08, PC mod 64, 1)`, the
  same function as the PROGRAM knob (`0x20013458`: current program in `[0x20002A08]`, range 0..63). Other messages
  go to the Korg dispatcher.

## Test on the instrument
Checked in the emulator (panel, clock, journal, MIDI) and on a real volca fm2 (November 2026).
