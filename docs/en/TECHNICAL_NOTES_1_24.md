# Technical notes 1.24: ratchet, microtiming and swing, dirtier LOFI, page order

Base: 1.23. Sources `src/fm2_124.S` (ITCM), `src/fm2_124_sram.S` (SRAM), `src/fm2_124_flash.S` (flash).
New tests `verify_124.py`; `verify_118.py` updated (LOFI model); full check `verify_patch.py` and
`verify_release.py`.

## Sequencer clock (analysis)
- `0x00208CF8(r0, r1)` is called at every internal clock tick with r0 = 0 (72 ticks per sixteenth,
  `CLOCK+0xC` = tick 0..71, `CLOCK = 0x20003198`). With r0 = 1 (sync pulse) it processes the ticks left to the
  step at once. Each tick is one pass of the loop `0x00208D7E … 0x00209096` (r8 = ticks to do).
- At the step boundary (tick 72): release of the normal notes `0x0020BB50` (`0x00208E0C`), counter
  `CLOCK+0xB` + 1, LED `0x0020FC10`, then the step routine `0x0020B7BE` (`0x0020903E`).
- Gate: step voice table `0x20003DC4` (6 × 4 bytes: note, gate, 1 normal / 2 tied, voice); the gate counts in
  units of `CLOCK+0xE` ticks in `0x0020BB28`, note off by `0x0020B774`.

## New hooks
- BL `0x00209096` (was `ADD.W r8, r8, #-1`) → `seq_tick` (entry 27): does the decrement and, at every tick,
  handles the late step, the ratchet hits, the look-ahead and the early step.
- BL `0x00208E0C` (was `0x0020BB50`) → `bnd_release` (entry 28): no release on the boundary when the next step
  has already been played early.
- `step_map` (1.23) now decides: step already played early → nothing; delay > 0 → waiting; otherwise `fire`.

## Microtiming and swing
- Step delay = microtiming of the played step (−36…+36) + swing on odd counters (swing 0…25 → (s·36 + 12)/25
  ticks, i.e. 50…75 %), limited to −36…+66; counter 0 never early.
- Late: `step_map` stores step, counter and tick; `seq_tick` plays it when `CLOCK+0xC` gets there.
- Early: half way through the step (tick 36, if no step is waiting) `seq_tick` computes the next step
  (`step_of`, which also caches it for the LED) and its delay; if negative it plays it at tick 72 + delay, after
  releasing the notes of the current step, and marks the counter (`+27`).
- `prob_entry` counts loops on the counter of the played step (`+22`), not on `CLOCK+0xB`.

## Ratchet
- Per step: 1–4 hits, probability 100/75/50/25 %, shape PARI/CALA/CRESCE. `fire` rolls the probability (native
  PRNG `0x002094A4`) before playing, so the first hit already has the right velocity.
- Spacing = ticks left in the step / hits (72 normally, 72 − delay when late). Each hit: release of the normal
  notes (`0x0020BB50`), step routine with the "hit" flag (`+23`: no new probability/condition decision, no new
  mutation), gates of the new notes × spacing / 72.
- Velocity: CALA v·(n − k)/n, CRESCE v·(k + 1)/n (`rat_vel` in `seq_note`).
- Only if the step was played (`+24` = decision of `prob_entry`).

## Saving
- 35-byte record in bytes 108–111 of steps 2–10 (pattern byte 300…; never read by Korg, see 1.23): `A5`, swing,
  ratchet × 16, microtiming × 16, check = xor of the 34 bytes ^ `5A`. Written by the pages (`save_seq2`), read at
  every load (`load_seq2` from `load_types`); invalid = all off.
- State in ITCM `0x3980` (128 bytes, described in the source before `step_map`).

## LOFI
- Hiss: xorshift32 (`0x3F80+0x58`, seed `0x9E3779B9`), (noise >> 24) · fb / 2^16 added to the written value
  (mono; L and R from different bits in ping-pong), before the saturation.
- Fb up to 120 with LOFI (Fb page: maximum 120 when FX = LOFI): loop gain > 1, limited by the saturation
  x − x³/3 (maximum amplitude 2/3). DELAY limits fb to 100 (`FB_MONO`/`FB_PP`).
- Wow × 2.5 (±0.8 ms), flutter × 2.
- CPU: LOFI ping-pong 2843 instructions per sample (1.12 reverb: 2848).

## Pages
- 18 modes; navigation order from `mode_order`: P C GL HU OC SC tn MOD rt rS FX dt Fb dr Mu rA ti CR (mode
  numbers unchanged, rA = 15, ti = 16, CR = 17).
- rA/ti: the keys select the step as in P/C; the key of the step already selected changes the shape (rA,
  messages PARI/CALA/CRESCE) or switches to the swing (ti).
- The builder now checks that every backward ADR points to a label: llvm-mc 18 assembles an ADR beyond 4095 bytes
  without an error (it happened to `mod_label`).

## Tests (`verify_124.py`)
Note-on/note-off timeline tick by tick identical to 1.12 with everything off (also with REC); 2/3/4 hits,
velocities, releases, probability 25/50/75, no hits on a muted step; late, early, step 1 never early, swing
50/58/75, ratchet after late and early steps, chain on the bar; page order, rA/ti/SWING readouts, record (WRITE,
load, invalid); LOFI: hiss, bounded self-oscillation, Fb 120 with LOFI and 100 with DELAY.

## Test on the instrument
Tested on the instrument by the author on 12/11/2026: all fine.
