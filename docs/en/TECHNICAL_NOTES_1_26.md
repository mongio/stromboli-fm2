# Technical notes 1.26: per-voice filter and two LFOs

Base: 1.25 (second build). Sources `src/fm2_126.S` (ITCM), `src/fm2_126_sram.S` (SRAM), `src/fm2_126_flash.S`
(flash, unchanged). New tests `verify_126.py`; full verification `verify_patch.py` and `verify_release.py`. The
parts (1.25) are described in `TECHNICAL_NOTES_1_25.md`.

## Processor and time per sample
- Clock setup in the bootloader (`0x0020047C`): RCC_PLLCFGR = `0x0940694C` → HSE 12.288 MHz, PLLM 12, PLLN 421,
  PLLP 2 → SYSCLK ≈ 215.6 MHz, overdrive on (PWR `0x40007000`). It is an STM32F7 (Cortex-M7).
- The audio interrupt (`0x0010`) computes **one sample per call**, at 50 kHz: about 4311 cycles per sample.

## Audio point
- Korg voice loop in ITCM `0x10F0–0x12A2`: for every active voice (`[ip+0xE]` ≠ 0; `[ip+0xD]` = voice number
  0–5) the algorithm kernel leaves the mono output in `r8`; at `0x123E` a smoothed level (`+0x40` towards
  `+0x44`) multiplies it; at `0x1266` `ldrd r2, r3, [ip, #0x38]` loads the left / right gains, then `smull` and
  the sum into the mix (`[sp]`).
- Peak of `r8` measured on several programs at velocity 127: about 2^27.
- From `0x1266` to the next voice the loop only uses `r8`, `r0–r3`, `r5`, `ip`, `sp`: `r4`, `r6`, `r7`,
  `r9–r11` are written again before use for the next voice (checked: with the filter on, voice inputs and Korg
  state are identical to filter off).

## Hooks
| Where | Was | Now |
|---|---|---|
| ITCM `0x1266` | `ldrd r2, r3, [ip, #0x38]` (`dce90e23`) | `bl 0x2090` → `filt_voice` (ITCM) |
| `0x0020E7EA` | `bl 0x00204580` (key-off of the Korg envelopes) | `bl 0x2094` → `filt_keyoff` (SRAM) |
| `multi_gain` (1.25, BL at `0x0020E79E`) | — | also `filt_start(voice, pitch, velocity)` |
| `panel_adc` (prologue `0x002059D0`) | — | FUNC + knob 1 / 3 → `filt_knob` |
| `midi_multi` (1.25) | — | CC 74 / 71 → `filt_set` |
ITCM and SRAM entry tables: 39 entries (+0x90 `filt_voice`, +0x94 `filt_keyoff`, +0x98 `filt_control`).

## Filter (per sample, `filt_voice`)
Trapezoidal SVF (Simper), 12 dB. With v0 = r8 × input gain (Q15) / 65536 (half the input, room for the
resonance):
- v3 = v0 − ic2; v1 = (a1·ic1 + a2·v3) >> 30; v2 = ic2 + (a2·ic1 + a3·v3) >> 30
- ic1 = sat(2·v1 − ic1), ic2 = sat(2·v2 − ic2), saturated to ±2^30
- LP = v2, BP = v1, HP = v0 − (k·v1 >> 29) − v2; output = 2 × sat(y, ±2^27) (at most 2^28 per voice, six voices
  below 2^31)
- amplitude modulation (bit 2): Q16 amplitude moving one step per sample, output × amplitude >> 16.
Active bits `FILT+0x0F` = 0 (power-on): `filt_voice` runs the original instruction only (7 more instructions per
voice).

## Control (every 32 samples per voice, `filt_control`)
- A sample counter (`FILT+0x34`, advanced when the voice number is not above the previous one) decides: voice v
  updates when counter % 32 = 5·v. At most one control step per sample.
- Cutoff in 1/8 semitone: 128 + cutoff × 121 / 16 (notes 16–136, 20 Hz–21 kHz) + envelope × EA × 12 / 65536
  (scaled by vE and the velocity) + (note − 60) × 8 × tr / 100 + LFO (± 381 at depth 127) + aftertouch × 2;
  limited to 0–1088.
- g = tan(π fc / fs) from the table `filt_g` (137 semitones, Q26, fc at most 0.45 fs), linear within the semitone.
- k = 2 − 1.9 × resonance / 127 (Q26; resonance + LFO, 0–127). Input gain = 32767 − 96 × resonance.
- a1 = 1 / (1 + g (g + k)) computed as (2^32 − 1) / D with D in Q16, then Q30; a2 = g·a1, a3 = g·a2 (Q30); k for
  the high pass in Q29.
- Envelope 0–65535: linear attack (`filt_att`, 0.5 ms–8 s), exponential decay to the sustain and release
  (`filt_dec`, Q15, 60 dB in 2 ms–10 s). The gate closes with the Korg key-off (`filt_keyoff`): sustain and HOLD
  work as before.
- Amplitude: tremolo 1 − depth × (1 − (value + 1)/2); crossfade A ↔ b with x = 0.5 + value × depth / 2: A = 1 − x²,
  b = x (2 − x), C unchanged. The step per sample is (target − amplitude) / 32.

## LFOs (`filt_lfos`, from the control step)
- They advance by the samples since the previous step (counter `FILT+0x34`); LFO 2 first, since it can move the
  rate of LFO 1 (± 127 table positions).
- Free rate: `filt_lfo_rates` (0.05–30 Hz, phase step per sample). Sync: phase from the sixteenths since the start
  (`0x3B80+0x3C`) and the samples since the last sixteenth (`0x3F80+0x8`, `+0xC`, `+0x10`), as the 1.22
  modulation SYNC; without clock, free at that tempo.
- Waves: sine (parabolic), triangle, saw up / down, square, S&H (new random value every cycle, LCG `FILT+0x30`).

## State (ITCM `0x3700–0x385F`)
Global: `+00` type, `+01` cutoff, `+02` resonance, `+03` EA (63 = 0), `+04–07` A D S R, `+08` tr, `+09` vE, `+0E`
last voice seen, `+0F` active bits, LFO1 `+10` and LFO2 `+18` (wave, rate, depth, destination, sync, division),
`+20/+24` LFO1 phase and value, `+28/+2C` LFO2, `+30` random state, `+34` sample counter, `+38` counter at the last
LFO step, `+3C` S&H values.
Per voice (`+40 + 48 v`): ic1, ic2, a1, a2, a3, k, input gain, amplitude, step, envelope; `+29` envelope stage,
`+2A` note, `+2B` velocity, `+2C` gate.
The settings are global and **not saved** (one free byte is left in the pattern).

## Controls
- FUNC + TRANSPOSE (index 1) / FUNC + VELOCITY (index 3), panel only (r2 = 0) and with FUNC held (`0x0020FA60`):
  the Korg handler is not run; filter off → LP. Display "CUTOF nnn" / "RESO  nnn". FUNC + knobs 7 and 9 stay
  Korg (checked).
- MIDI CC 74 / 71 on an accepted channel (the volca channel, or the part channels with the channels on).
- Pages FL (21) and LF (22) after PC; 23 modes in all. FL: keys 1–10; LF: keys 1–5 (LFO 1) and 9–13 (LFO 2).
  The display has no "+": a positive EA is shown without sign, the saws are `SAu` / `SAd`.

## Space
ITCM: code `0x2000–0x2E74`, filter state `0x3700–0x385F`, parts `0x3900`. SRAM: up to `0x2001A07C` (15308 bytes of
23376, tables included). Flash: unchanged.

## Processor load (`verify_126.py`, instructions per sample of the whole interrupt, six voices, chorus and reverb)
| | mean | max |
|---|---|---|
| Korg 1.12 | 2819 | 2854 |
| STROMBOLI 1.24 | 2855 | 2890 |
| 1.26 filter off | 2897 | 2932 |
| 1.26 LP with envelope | 3197 | 3398 |
| 1.26 LP + two LFOs (cutoff, amplitude) | 3239 | 3465 |
About +15 % on average over 1.12; the maximum includes a control step. At 216 MHz there are about 4311 cycles per
sample; real cycles (waits, pipeline) are not measured: **this is the point to check on the instrument**.

## Tests (`verify_126.py`, 8 groups)
Filter off: identical to 1.12 (also through the interrupt). Model: every sample of every voice equals the model in
LP, BP, HP with envelope, resonance and LFOs; voice inputs and Korg state untouched; mix = sum of the filtered
voices. Coefficients: g and k as expected for 15 combinations; measured response (cross spectrum) equal to the
analog prototype within 1 dB. Envelope: attack and release times, sustain, amount, velocity, key tracking. LFOs:
rates, waves, sync, LFO 2 on the rate of LFO 1, tremolo, A ↔ b crossfade (power 1.00–1.14). Controls: FUNC +
TRANSPOSE / VELOCITY, Korg without FUNC, FUNC + 7 / 9 unchanged, CC 74 / 71. Pages. Processor load.

## Known limits
- Settings not saved; no motion of the cutoff (use CC 74 from an external sequencer).
- One filter for all parts.
- Not tested on the instrument.
