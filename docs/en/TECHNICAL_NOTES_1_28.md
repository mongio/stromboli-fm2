# Technical notes 1.28: extended EDIT, VA engine, STROMBOLI program block

Base: 1.27. Sources `src/fm2_128.S` (ITCM: VA engine), `src/fm2_128_sram.S` (SRAM: EDIT, program block),
`src/fm2_128_flash.S` (unchanged). Checks `verify_128.py`; full checks `verify_patch.py`, `verify_release.py`.
Waveforms: `TECHNICAL_NOTES_1_27.md`; filter: `TECHNICAL_NOTES_1_26.md`.

## Korg EDIT
State E = `0x20002A08`: +0 current program, +2 operator parameter, +3 ALL parameter, +4 operator 0–5 (OP1–OP6)
or 6 (ALL). EDIT mode = `[0x200029DA]` 0x16. PROGRAM knob: `0x200114B8` → step `0x20012978` (operators
0..0x15, ALL 0x16..0x26). VELOCITY slider: `0x20012C50` → setter `0x20012A2C(E, 0..127)`. Values: `0x20012F78`
(current program), `0x2001302C` (stored copy `0x2000524C`), text `0x200101D4` (5-char name from `0x2000AB78`,
2-digit value, edited mark 0x15).

Hooks (first instructions replaced by `b.w`, replayed on the way out): getters, setter and text; step limits
`0x20012996/0x2001299A` 0x15 → 0x16 (WAv) and `0x20012982/0x20012986` 0x26 → 0x4A.
- Operator, 0x16 **WAv**: waveform (bit 7 of bytes 11–13, 1.27).
- ALL, 0x27 **EnG**: engine, bit 7 of program byte 110 (FM/VA).
- ALL, 0x28–0x4A: the 35 parameters of the block (table `ext_desc`: name, block byte, maximum, readout kind).
  Readout `A FCu 064`, edited mark at position 5.

## STROMBOLI program block (48 bytes)
`0 'S'  1 version 1  2–11 filter (FILT+0..9)  12–17 LFO 1  18–23 LFO 2  24–28 FX (0x3F80 +0 +2 +4 +5 +6)
29–36 MOD (0x3B80 +0 +2 +3 +4 +5 +6 +7 +9)  37–46 0  47 check = (sum 0..46) ^ 0xA5`.

RAM: block of the current program `0x2001B3C0`, 64 blocks `0x2001B400–0x2001C000` (FF padding of the SRAM
section, defaults written by the builder). SRAM code ends before `0x2001B3C0`.

Flash: the Korg journal writes programs in groups of 16 in one 4 KB sector (`0x20013ACC`: header, 16 × 128
bytes at +0x010, 16 × 12 bytes of metadata at +0x810; the rest is 0xFF and the whole sector is written). The
16 blocks go to +0x900–0xBFF: `ext_sector` replaces the final call (b.w at `0x20013B0A`). Boot: after the
metadata copy (BL at `0x20013982`, state 6) `ext_sector_load` reads the 768 bytes of the same sector
(synchronous SPI read `0x20015218`) and checks each block; a block without 'S', version or right check
(sector written by Korg or an earlier beta) = defaults. Factory programs (no journal sector) = defaults.

Program: load `0x0020E456` (BL at `0x0020E490` → `ext_load`: bank block → current block → filter, LFO and
effect state); save `0x0020EF20` (BL at `0x0020EF36` → `ext_save`: current block → bank, with the check; Korg
then marks the group). Korg program SysEx received (`0x0020F33C`, BL at `0x0020F346` → `ext_sysex`): that
program's block to defaults. DX7 voice import: current block to defaults.

FUNC+EDIT pages (MOD rt rS FX dt Fb FL LF), FUNC + TRANSPOSE / VELOCITY and CC 74 / 71 change the state as
before and then copy it into the current block (`ext_capture`). A pattern load no longer sets the effect types
(`load_types`), the pages no longer write them into the pattern (`set_fxmod`): bits of steps 13–16 (PRB3) are
free.

## VA engine
Bit 7 of program byte 110 (ignored by Korg, kept by save, program change and Korg program SysEx; cleared by
the DX7 import). At note start `va_kernel_of` (BL at `0x0020DFA8`, was the kernel table `0x00204578`) picks
`va_kernels`: one kernel per algorithm with the same sequence of operator types as the Korg kernels (derived
by the builder and checked). Each operator: Korg pitch, envelope and level code (copy of `0x0510–0x05B5`),
then a wave routine instead of the sine: SAu SQR P25 P12 TRI SIN NOI S-H. Record word +0x14: routine (bits
0–13) and held S-H value (bits 14–31); 0 = operator off (output level 0). Saw and pulses with polyBLEP (alias
at 1760 Hz: −30 dB against −14 dB for the naive wave). Pulses: stackless fast path away from the edges.

## Processor (instructions per sample, whole interrupt, six voices)
| Case | max | mean |
|---|---|---|
| Korg 1.12 | 2854 | 2819 |
| FM 1.28 | 2932 | 2897 |
| FM + filter + 2 LFOs | 3465 | 3239 |
| VA 2 SAu | 2164 | 2108 |
| VA 2 SQR + filter + LFOs | 2790 | 2531 |
| VA 6 SAu + filter + LFOs | 3887 | 3631 |
| VA 6 SQR + filter + LFOs | 4255 | 3969 |
| VA 6 P12 + filter + LFOs | 4245 | 3923 |
Budget: ~4311 cycles per sample. The VA worst case is close to the limit (instructions, not cycles): to be
checked on the instrument.

## Checks (`verify_128.py`)
edit_native (148 Korg parameters identical), block_edit (35 parameters: readouts, setter, getters, edited mark,
state), block_program (save with check, program change, FUNC + knob and CC into the block, pattern not changing
the types, SysEx and DX7 import → defaults), block_journal (sectors with blocks, reload, Korg sector →
defaults, bad check → defaults for that program only), edit_wave, edit_engine, va_sine (VA all SIN = Korg FM
sample by sample, 32 algorithms), va_waves (every routine against an independent model, alias), va_storage,
va_off, cpu.
