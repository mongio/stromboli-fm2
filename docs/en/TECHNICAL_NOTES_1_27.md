# Technical notes 1.27: FM operator waveforms

Base: 1.26. Sources `src/fm2_127.S` (ITCM, no new code), `src/fm2_127_sram.S` (SRAM, new code at the end),
`src/fm2_127_flash.S` (flash, unchanged). New checks `verify_127.py`; full checks `verify_patch.py` and
`verify_release.py`. Filter and LFOs: `TECHNICAL_NOTES_1_26.md`; parts: `TECHNICAL_NOTES_1_25.md`.

## How Korg computes the operators
- The 32 algorithms (table at ITCM `0x105A`, kernels `0x0C60–0x1058`) are sequences of `bl` to **eleven operator
  routines** (`0x0250`, `0x0350`, `0x0430`, `0x0510`, `0x05F0`, `0x06E0`, `0x07C0`, `0x08C0`, `0x09A0`, `0x0A80`,
  `0x0B60`) ending with `b 0x123A`. They differ only in the modulation input (feedback, `sb`, `sl`) and the output
  (`r8` audio, `sb`, `sl`, feedback history `[ip+4/8]`).
- Each routine: phase increment from the exponential table `[ip+0x58]`, envelope (`[r7+4]`, segments from
  `[r7+0x18]`), amplitude from `[ip+0x5C]`/`[ip+0x50]`, then the sine: `ldr.w r2,[ip,#0x54]`, index = phase bits
  14–23 (1024 entries), 8-byte entry (value, slope), output = value + (14-bit fraction × slope) >> 14.
- Korg sine table: `0x20006810`, 1024 × (value, slope), amplitude 2^24, slope = next value − value (wrapping).
  The sine LFO (ITCM `0x1172`) reads it through `[ip+0x54]` too.
- Operator record: voice + `0x90` + 0x50·i, i = 0–5. Program block i (17 bytes, block 0 is OP6) goes to record i
  (checked). Word `+0x14` of the record is never used by Korg: it survives note start, the note and the release
  (checked with a sentinel).

## Hooks
| Where | Was | Now |
|---|---|---|
| ITCM `0x030A 0x03FC 0x04DC 0x05BA 0x069C 0x078A 0x087A 0x096A 0x0A4C 0x0B2A 0x0C1A` | `ldr.w r2,[ip,#0x54]` (`dcf85420`) | `ldr.w r2,[r7,#0x14]` (`d7f81420`) |
| `multi_gain` (BL at `0x0020E79E`) | — | `wave_voice(program, voice)` before the Korg call |
| veneer literal `0x20015170` (logical `0x23174`) | `0x0020F019` (DX7 voice import) | `wave_dx7` |
| `panel_keys` | — | `wave_build` at the first key scan |
Same instruction, size and cycles: the voices cost exactly as before (counted: 2456.3 instructions per sample in
the voice loop, Korg 1.12 = 1.27 with and without waves).

## Where the wave is stored
Bit 7 of bytes 11, 12, 13 of each operator block (wave = b11 | b12 << 1 | b13 << 2, 0–7).
- Korg ignores them: tested byte by byte (bit 7 set on each of the 128 program bytes, voice state and audio
  compared) → in the operator blocks bytes 11, 12, 13 and 15 are ignored; elsewhere 110, 111, 116 and the name.
  Still free: bit 7 of byte 15 of each operator, 110, 111, 116, 118–127.
- A DX7 SysEx cannot set them (7-bit MIDI data).
- The DX7 voice import (`0x0020F018`) writes the fields with `bfi` into the bytes of the current program, keeping
  bit 7: `wave_dx7` clears them before calling Korg.
- Save (`0x0020EF20`), program change (`0x0020E456`), Korg program dump and receive (8 bits packed into 7) keep
  the bits (checked).
- `0x0020E518` (program of the voice with the MODULATOR/CARRIER knobs) copies 128 bytes and changes only bytes 0–3,
  5, 6 and 14.
- Korg RANDOM (`0x0020EBD8`) starts from the saved copy `0x2000524C` and writes masked fields.

## Tables (`wave_build`)
A chain of 12 quarter periods of 256 entries (24576 bytes) at `0x20035B00–0x2003BB00`: RAM after the reverb/delay
buffer (`0x20029B00 + 0xC000`) and before the SysEx buffer `0x2003C000` (used up to `0x2003D000` in the checks).
No Korg reference to that area (literals `0x2003xxxx` searched; no writes in the memory, SysEx, storage and
effects checks).

Quarter types (exact Korg values): 0 zero, 1 rising (sine 0–255), 2 falling (256–511), 3 below zero (512–767),
4 double-frequency hump (sine 0, 2, …, 510), 5 negative hump.

Chain: `3 0 3 0 1 2 0 4 4 0 0 5`. Each wave is a window of four consecutive quarters (1024 entries):

| Wave | Name | First quarter | Quarters |
|---|---|---|---|
| 0 | SIN | — | Korg table |
| 1 | HAL | 3 | 0 1 2 0 |
| 2 | 3-4 | 2 | 3 0 1 2 |
| 3 | PUL | 0 | 3 0 3 0 |
| 4 | ALt | 1 | 0 3 0 1 |
| 5 | dbL | 8 | 4 0 0 5 |
| 6 | dbA | 6 | 0 4 4 0 |
| 7 | HAb | 4 | 1 2 0 4 |

Slope = next chain entry − entry; the last goes to 0. At the last entry of a window the slope points to the next
chain quarter instead of the start of the window: a difference only in the last 1/1024 of the period, and only
where the two values differ. Free RAM is not enough for separate full tables (8 KB each).

Build: 51049 instructions (~0.25 ms), once per power-on, at the first key scan (`WV+4` = 1). If needed earlier,
`wave_voice` builds at the first operator with wave ≠ 0.

## Note start (`wave_voice`)
Called by `multi_gain` **before** `0x0020DF14`: `0x0020E6DC` has already switched the voice off (`+0x0E` = 0), so
the audio interrupt never reads a half-written pointer. Per record: wave 0 → `0x20006810`, else
`0x20035B00 + first_quarter × 2048`. 113 instructions. A note on a voice that still sounds is queued by
`0x0020E814` and started by the service routine `0x0020E8C2` after the fade, also through `0x0020E6DC` (checked).

## Page Wv (mode 23)
After LF (24 modes, `mode_order` … 21 22 23). Keys 1–6 (OP1–OP6, block 5 − n), slider 0–127 → wave 0–7
(`adc_map`), written into the current program `0x20004F5C`; sounding voices of part A (all, with parts off) take
the new pointers at once. Display `OP3 dbL`.

## State
ITCM `0x3880` (`WV`, 16 bytes, zero in the image): +4 chain built.

## Checks (`verify_127.py`)
- **off_identical**: 32 algorithms, two voices, sample by sample = Korg 1.12; pointers = sine; interrupt with six
  voices, chorus and reverb = Korg 1.12.
- **tables**: 3072 entries equal to the model; built once; peak 2^24.
- **oracle**: all operators on wave w = Korg 1.12 with its sine table replaced by window w (LFO not on the sine),
  algorithms 1, 5, 7, 16, 32: identical sample by sample; different from the sine.
- **operators**: block i → record i, mixed waves, next note with the new program.
- **storage**: save, program change, Korg program SysEx, DX7 import (bits cleared, the rest as Korg).
- **pages**: 6 operators × 8 waves, display, program, sounding voices, keys 7–16, order LF → Wv → P.
- **cpu**: voice loop identical (2456.3 instructions per sample) with and without waves.

Earlier checks compare the voice state with Korg leaving out word `+0x14` of the operator records
(`verify_125.vdata`, `verify_114.ram`, `verify_patch.core_snapshot`).
