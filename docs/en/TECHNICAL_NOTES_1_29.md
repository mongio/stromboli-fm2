# Technical notes 1.29: simple VA, Korg-style EDIT labels, effects and filter motion in the pattern, filter per part

Base: 1.28. Sources `src/fm2_129.S` (ITCM), `src/fm2_129_sram.S` (SRAM), `src/fm2_129_flash.S` (flash).
Checks `verify_129.py` (includes the updated 1.28 checks); full checks `verify_patch.py`, `verify_release.py`.

## Why
On 1.28 the VA engine with phaser and delay froze the instrument with more than two or three notes: the CPU
check counted instructions, not the cycles of taken branches. `verify_cpu` now estimates cycles (instructions +
2 × taken branches) with the heaviest effects (8-stage phaser + delay, filter, two LFOs) and requires at most
4000 cycles per sample (budget ~4311).

## Simple VA (ITCM)
One kernel `va_simple` for every algorithm (`va_kernel_of` at `0x209C`, BL at `0x0020DFA8`); the 32 kernels and
operator types of 1.28 are gone. Korg operator records (`ip+0x90+0x50·i`, OP1 = record 5):
- OP1 = OSC 1, OP2 = OSC 2: wave (SA Sq PU tr Si), ratio/detune, Korg level and envelope (`va_body`).
- OP3 = sub / noise (S1 one octave below OSC 1, S2 two octaves, no noise), level = amount (`va_env`).
- OP4 = pulse width of PU (PWM, `va_env`), OP5 = pitch of OSC 2 up to +1 octave (`va_env`), OP6 unused.
- ALGORITHM & 7: 1 MIX, 2 SYNC, 3 RING, 4 FM (OSC 2 → phase of OSC 1), 5 SYNC+FM, 6 MIX with OSC 2 an
  octave up, 7 RING + SUB, 8 CROSS (OSC 1 → OSC 2); from 9 the modes repeat.
- Record 0: `+0x14` mode (bits 0–2), OSC 1 wrap (bit 3), sub counter (bits 4–5); `+0x10` last OSC 1 output.
  Records 1..5: wave + 1, 0 = off (output level 0); OSC 1 always runs (the sub follows its phase).

## EDIT (SRAM)
- Korg-style 4-letter labels, values 0–99: `A CUtF 64`, edited mark at position 6, value at 7–8. 0..max →
  0..99 rounded; EnvA 0..126 → 50 = zero; divisions (`L1dv`) raw; choices as 2 letters. `EnGn` FM/VA; `WAvE`
  with 2-letter names (FM: Si HA 34 PU AL db dA Hb; VA: SA Sq PU tr Si / S1 S2 no / PW / Pi / --).
- Page A: EnGn then the 22 parameters of the program block (filter, two LFOs), step up to `0x3D`. Effects left
  the EDIT and the program block (bytes 24–36 unused).

## FUNC+EDIT pages
FL (21) and LF (22) removed: 21 pages. MOD rt rS FX dt Fb as before. EDIT LED lit steadily on the pages.

## STROMBOLI pattern block (52 bytes)
`0 'P'  1 version 1  2–6 FX (0x3F80 +0 +2 +4 +5 +6)  7–14 MOD (0x3B80 +0 +2 +3 +4 +5 +6 +7 +9)  15 bit 0
cutoff motion, bit 1 resonance motion, bit 7 types from the PRB3 bits  16–31 cutoff per step  32–47 resonance
per step  48–50 0  51 check = (sum 0..50) ^ 0x5A`.
- RAM: live block `0x2001B040`, 16 blocks `0x2001B074–0x2001B3B4` (FF padding).
- Flash: one pattern per journal sector (`0x20013A9A`, 1920 bytes at +0x010); the block goes to +0x800
  (`pat_sector`, b.w at `0x20013ABC`). Boot (state 2, BL at `0x200138D8`): `pat_sector_load` reads and checks
  it; factory data, Korg or earlier beta sector = defaults.
- Native WRITE (veneer literal `0x0020FA94`): live block → slot block, sealed. Pattern load (`load_fx` passes
  the number) → `load_types`: slot block → live → effect state; defaults with bit 7 take the types from the
  PRB3 bits as in 1.21–1.27. Pattern SysEx received (BL at `0x20014AC8`): slot block to defaults. FUNC + MEMORY
  copy copies the block; CR chain auto-save also saves a changed block.
- The effect pages write the live block (`pat_capture`); PRB3 bits no longer written. Program change leaves
  the effects alone.

## FUNC + 3 / FUNC + 4
Veneer literals `0x002232F4` (was the chorus switch `0x0020C88B`) and `0x0022316C` (reverb switch
`0x0020C8B7`): OFF → CHORUS → PHASER → TREMOLO → OFF and OFF → REVERB → DELAY → LOFI → OFF. On/off stays the
Korg pattern bit (with its LED), the type is in the block. Message on the display while FUNC is held.

## Filter motion
Recording (`filt_set`: FUNC + TRANSPOSE / VELOCITY, CC 74 / 71) with PLAY and REC on: value on the step being
played (`0x3F3B`); the first one fills all 16 steps. Playback: `fire` calls `pm_play(step)`. FUNC + 14 (Korg
motion clear, veneer literal `0x00223254`) clears it too.

## Filter per part
`filt_control` reads the settings from `filt_params(voice)`: FILT for part A, the block of the program of part
b / C. Type per voice at state `+0x2D`, used by `filt_voice` (0 = no filter). LFOs stay those of part A.

## CPU (estimated cycles per sample, whole interrupt, six voices)
Korg 1.12 3346; FM 3494; FM + filter + LFOs + phaser 8 + delay 3896; VA 2 oscillators 2903; VA all on + filter +
LFOs + phaser 8 + delay: CROSS 3992, SYNC+FM 3999.
