# Technical notes 1.23: chorus level, more resonant phaser, direction and mutation per pattern

Base: 1.22. Sources `src/fm2_123.S` (ITCM), `src/fm2_123_sram.S` (SRAM), `src/fm2_123_flash.S` (flash).
New tests `verify_123.py`; `verify_122_mod.py` updated (phaser model); full check `verify_patch.py` 101/101 and
`verify_release.py`.

## FUNC + knob 7 (chorus level)
- The knob scanner `0x00205AB0` calls `0x002059D0(index, value, r2 = 0)`. In the Korg handler, with FUNC held
  (`0x0020FA60` ≠ 0) and r2 = 0, index 7 becomes r2 (= 0, chorus level) and 9 becomes 5 (reverb). Knob 7 is of
  type 1 (ADC >> 5, 0..127).
- The prologue `0x002059D0` is hooked since 1.14 (`panel_adc`); since 1.16 index 7 always went to `arp_knob`
  (17-position ARP TYPE), also with FUNC: the chorus value was recomputed as an arpeggio position (0, 13, 26 …
  116, then 13). This was so since 1.16 for the chorus and therefore also for the phaser and tremolo.
- Now `arp_knob` with r2 = 0 asks `0x0020FA60`: with FUNC it goes to the unchanged Korg handler. Checked over the
  whole knob travel (ADC 0..4095 and back): texts and level identical to 1.12; knob 7 without FUNC identical to
  1.22.

## Phaser
- Loop input: u = x · gin + y_prev · fb (Q15), fb = resonance · 301 (at most 0.92), gin = 1 − fb/2 (`+42`), then
  limited to ±2^24 and soft-saturated u − u³/(3·2^48) (computed on u >> 9: the linear part keeps full
  resolution).
- 4, 6 or 8 stages (`+09` = 0, 1, 2; states 5–8 at `+44..+50` L and `+54..+60` R, cleared on a type change).
- Coefficient table 100 to 2400 Hz. Output = y · (level + level/16) / 2^25 (at most 0.996).
- MONO: a single chain on (L + R)/2, same output on both sides (half the work).
- Page rS: key 16 = stages (phaser only), digit 4/6/8 at the end. At power-on 6 stages, resonance 50.
- CPU (instructions per sample, ISR, 6 voices): 1.12 reverb + chorus 2848; 1.22 phaser 4 stages + reverb 2922
  (tested on the instrument); 1.23 phaser + reverb: 4 stages 2944, 6 stages 2972, 8 stages 2992, 8 stages MONO
  2908; 8 stages + LOFI ping-pong 2939.

## Direction per pattern (page dr, mode 13)
- The clock `0x00208CF8` counts the step in `CLOCK+0xB` (0..15, then 0): loop end, chain, motion and recording
  depend on it. It is not touched.
- BL `0x0020903E` (clock → step routine `0x0020B7BE`) and BL `0x00208E42` (clock → step LED `0x0020FC10`) go
  through `step_map` / `led_map` (table entries 25 and 26), which replace r0 with the step to play (`step_of`):
  AVANTI c, INDIETRO 15 − c, PENDOLO forward and backward on alternate loops (direction flipped when c = 0), CASO
  a random step (native PRNG `0x002094A4`). With REC (`0x20003F8C` bit 1) always forward. Computed once per
  counter value (the LED comes first in the tick), cache `0x3F38`/`0x3F39`, cleared at start.
- `prob_entry` counts loops (conditions) on the counter `CLOCK+0xB`, not on the played step.
- Motion (`0x0020B668`) stays on the counter: it follows time.

## Mutation (page Mu, mode 14)
- In `seq_note` (BL `0x0020BA6E`, note of each voice of the step before live scale, humanize, octave): at the first
  note of each played step (`0x3F3A` set by `step_of`), with probability Mu % the step gets a new offset
  d ∈ [−R, R] (R = 3 or 7, uniform, 0 included) in `0x3F70 + step`.
- The note becomes `scale_walk(note, d)`: snapped up into the scale, then moved by d degrees in the scale and
  tonic of the SC/tn pages (`0x3F31`, `0x3F32`, masks `0x1F70`), also with the scale off; limits 0..127. With
  d = 0 the note stays the pattern's.
- Offsets stay until the next mutation of the same step; they are cleared at every pattern load. The pattern is
  never written.

## Saving dr and Mu
- Bytes 108–111 of step 1 (pattern bytes 188–191): never read by the Korg firmware while playing (checked with a
  read watch on the pattern memory), copied with the pattern by WRITE and loads. Block: `A4`, direction | range
  << 2, Mu, check = xor of the three ^ `5A`. Without a valid block: AVANTI, Mu 0, range 3 (Korg and older
  patterns).
- The pages write the block into the pattern in use (`save_seqx`), `load_types` reads it after every load
  (`load_seqx`).

## Pages and space
- 16 modes: … rS (12), dr (13), Mu (14), CR (15).
- ITCM code `0x2000–0x2C9C`, SRAM up to `0x20018234`, flash up to `0x0020FF74`. 27-entry tables.

## Test on the instrument
Emulator only so far.
