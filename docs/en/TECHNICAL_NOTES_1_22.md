# Technical notes 1.22: space, phaser and tremolo instead of the chorus, tape LOFI

Base: 1.21. Sources `src/fm2_122.S` (ITCM, audio code), `src/fm2_122_sram.S` (SRAM, non-audio code, new),
`src/fm2_122_flash.S` (flash at `0x0020FC40`). Tests: `verify_122_mod.py` (new), `verify_118.py` (LOFI model
updated), `verify_122.py`, `verify_122_more.py`; full check `verify_patch.py` 97/97 and `verify_release.py`.

## Space: non-audio code in SRAM
- In 1.21 the ITCM was full (code up to `0x3BD4`, limit `0x3C00`).
- The Korg loader copies `0xC000` bytes of the ff13 section to `0x20010000`. Its tail `0x200164B0–0x2001C000`
  (22.4 KB) is FF padding: no reference in the firmware and no runtime write (checked in the emulator).
  `build_patch.py` checks it is still all FF before using it.
- The code that does not run in the audio interrupt (panel, pages, readouts, keys, clock, chains, start) is in
  `src/fm2_122_sram.S` at `0x200164B0`, with a table of 25 `b.w` in the same order as the ITCM one. The non-audio
  ITCM entries are trampolines `ldr pc, =0x200164B0+4k+1`: the hooks in the firmware do not change. From SRAM the
  ITCM functions are called with `ICALL` (`ldr r12, =sym; blx r12`); the ITCM symbols are exported to
  `itcm_symbols.inc` at build time.
- ITCM keeps the audio code (delay, modulation) and the data: code `0x2000–0x2A48`, phaser table `0x3A00`,
  modulation state `0x3B80`, delay state `0x3F80`. SRAM up to `0x20017EB4`; flash up to `0x0020FF74` (limit
  `0x0020FFF0`).

## Modulation: CHORUS / PHASER / TREMOLO
- The audio interrupt (ITCM `0x0010`) calls the Korg chorus `0x12AC` through the ITCM literal `0x0238` (`0x12AD`)
  with r0, r1 = voices L, R >> 8 and adds the result (<< 8) to the dry signal. The chorus is always called, also
  when off (target level 0): same cost on or off.
- Literal `0x0238` is now `0x2061` (ITCM table entry 24, `mod_audio`). With type 0 and no transition: direct jump
  to `0x12AD` (output identical to 1.12, checked on the whole ISR).
- State `0x3B80`: +00 requested type, +01 active type, +02 SYNC, +03 STEREO/PAN, +04 SYNC division 0..6,
  +05 LIBERO slider, +06 resonance, +07 shape, +08 transition (0 running, 1 fade out, 2 clear, 3 fade in),
  +0A counter, +0C LFO phase, +10 LIBERO increment, +14..+30 allpass states L/R, +34/+38 last output L/R,
  +3C sixteenths since start, +40 resonance Q15.
- Level and on/off are those of the Korg chorus (state `0x200011D0`: +40 smoothed level, +44 target
  0..`0x1E00000`; FUNC + 3 sets the target to 0). `mod_common` smooths the level as the Korg chorus does.
- Type change: wet signal faded out over 256 samples (5 ms), Korg chorus lines `0x20000070–0x200011CF` (1112
  words, 8 per sample) cleared only when going back to the chorus, phaser states cleared, 256-sample fade in.
- LFO: LIBERO, phase += 2^32 / (50 · period in ms), period from a table (20000 ms · 0.005^(v/127), 20 s to
  100 ms). SYNC: phase = ((sixteenths & (k−1)) · f16 + e) · ⌊(2^32−1)/(k · f16)⌋, k = 2^division sixteenths
  per cycle, f16 = samples per sixteenth measured by the delay (1.18), e = samples since the last sixteenth;
  without clock for more than two sixteenths it free-runs at the same rate. The sixteenth counter (`+3C`) is
  incremented by `tempo_tick` and cleared at start.
- Parabolic sine: s = x · (32768 − |x|) / 2^13, x = phase >> 16.
- **Phaser**: 4 first-order allpasses per channel, y = a·x + s, s = x − a·y (`smmla`/`smmls` Q31), coefficient
  a = (tan(πfc/fs) − 1)/(tan(πfc/fs) + 1) from a 65-entry table (fc 120 to 1600 Hz, exponential) interpolated
  linearly on the sine; feedback from the channel output, resonance 0..100 ×180 (Q15, at most 0.55); with STEREO
  the R channel phase is +90°. Output = y · level / 2^25 (at most 0.94): added to the dry signal it makes the
  phaser notches.
- **Tremolo**: depth = normalised level (0..65535, at most 1); u = sine · (16 + shape·41/64) / 16 saturated
  (shape 100 = almost square), 0..65535; PAN: uR = 65535 − uL. Output = −x · depth · u / 2^24: added to the dry
  signal it gives a gain from 1 to 1 − depth.
- The type is saved in the pattern in bit 7 of steps 15–16 of PRB3: steps 13–16 are now one 4-bit field (bits 0–1
  effect REVRB/DELAY/LOFI, bits 2–3 modulation), written by `set_fxmod` and read at every load by `load_types`
  (called by `load_fx` in flash). With this the free pattern bits are used up. No block = REVRB and CHORUS.
- Pages 10 MOD, 11 rt, 12 rS/Fo, 13 CR (14 modes). New messages 30 STEREO, 31 PAN. The level readout
  "CHORS nnn" becomes "PHASE nnn" / "TREMO nnn" (`mod_label`).

## Tape LOFI
- In the light sample of the pair (1.18) the read position `+44` = D + wow + flutter is computed: wow 0.54 Hz
  ±16 slots (±0.64 ms), flutter 6.8 Hz ±0.25 slots, limited to the line. DELAY reads at D.
- Feedback: damping d += (y − d)/2 (about 2.8 kHz at 25 kHz), low cut h += (d − h)/64 (about 60 Hz), output
  d − h; soft saturation x − x³/(3·2^30) on the written value (instead of the limiter).
- State `0x3F80`: +44 read position, +48/+4C low cut L/R, +50/+54 wow and flutter phases.

## CPU load (instructions per sample, whole ISR, 6 voices)
1.12 reverb + chorus 2848; 1.22: CHORUS + REVRB 2884 (reverb wrapper, as since 1.18), PHASER + REVRB 2922,
TREMOLO + REVRB 2854, PHASER + LOFI ping-pong 2869, PHASER + DELAY ping-pong 2835. Phaser + reverb is the heaviest
combination: +2.6% over 1.12, +1.3% over 1.21 (tested on the instrument). To be checked on the instrument (TESTS).

## New tests (`verify_122_mod.py`)
Table and initial state; phaser and tremolo equal to the Python model sample by sample (STEREO/MONO, PAN,
LIBERO/SYNC, resonance, shape, changing level); phaser notches, tremolo depth and period, SYNC phase; CHORUS
identical to 1.12 on the whole ISR; transitions (lengths, chorus lines cleared, no click); CPU; pages and readouts;
types in the pattern (selection, chain, pages writing only their own bits); FUNC + 3 and level. The delay model
(`verify_118.py`) includes the tape LOFI.

## Test on the instrument
Emulator only so far.
