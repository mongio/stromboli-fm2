# Technical notes 1.19: evolved chain

## Korg chain (1.12, verified in the emulator with the journal model)
- 16 patterns of 1920 bytes, RAM copy at `[0x2001D08C]` = `0x20020000`; loading `0x208900(n)` reads from there; the
  NOR journal writes them later.
- Selection: panel in mode `0x13` (MEMORY held) → `0x20011886` → SRAM veneer `0x20014FC0` (literal `0x20014FC4` =
  `0x0020C611`) → `0x20C610(chain, keys held, keys held before)`. Range from the lowest to the highest key; with REC
  (`0x20DB70(0x20003F8C)`, state 2 or 3) one pattern only. It loads the first at once (`0x208CB8`). Then `0x20014FB8`
  (→ `0x208C5C`) shows the pattern.
- Structure `0x20003E34`: +0 switch step, +2 mask, +4 list[16], +0x14 count, +0x15 chain mode, +0x18 position.
- Clock `0x208CF8` (CLOCK `0x20003198`: +6 current pattern, +0xB step): at step `chain+0` → `0x20C5B0` (advance) →
  `0x208900` (load) → `0x20C5D6` (new switch step). After the load the step restarts from 0.
- Transport state `0x20003F8C`: bit 0 PLAY, bit 1 REC. Every change goes through the veneer `0x20FA68` (literal
  `0x20FA6C` = `0x20010B11`).
- Native WRITE `0x20815C(n)`: `0x200134EC(PATTERN, n)` (copy into RAM and mark the journal), CLOCK+6 = n. The firmware
  also calls it from the clock (pending WRITE, CLOCK+0x1A).
- Start from the beginning `0x2090C0(..., r2 = 1)`: in chain mode it resets the position and reloads the first pattern
  of the list.
- Motion: recording a knob sets `0x20003638` to the starting step; back at that step the firmware leaves REC
  (`0x208598`).

## Code
- ITCM (`src/fm2_119.S`): CH/CC/CR pages, MEMORY-pressed flag (`panel_button`), reset of entry/repeat on the start
  from the beginning (`start_hook`), texts `chain_disp` ("CH05  P07") and `chain_msg` ("CATENA nn"), names at
  `0x1980`.
- Flash (`src/fm2_119_flash.S`, block at `0x0020FC40`, in the FF padding of the application section; 6 jump
  entries):

| Hook | Original | New |
|---|---|---|
| literal `0x20014FC4` (selection veneer) | `0x0020C611` | `chain_build` |
| BL `0x00209006` | `0x20C5B0` | `chain_next` |
| BL `0x0020900C` | `0x208900` | `chain_load` |
| `0x00208E30` (`ldrsb.w r3,[r4,#0xb]`) | — | BL `cap_wrap` |
| literal `0x0020FA6C` (transport veneer) | `0x20010B11` | `trans_hook` |
| BL `0x0020C666` (REC check in the selection) | `0x20DB70` | `cr_check` |
| literal `0x20014FBC` (pattern readout veneer) | `0x00208C5D` | `chain_disp` (ITCM) |

- Data in ITCM: list `0x1C00` (64 × {pattern, repeats}), capture `0x1C80`, state `0x1D00` (+0 CH, +1 CC 0/1/2,
  +2 CR, +3 entries, +4 our chain active, +5 entry, +6 repeat, +7 MEMORY pressed, +8 captured entries, +9 pattern of
  the captured pass, +0xA last transport state, +0xB skip the next load, +0xC pass in progress, +0xD our readout).
  All zero at power-on.

## How it works
- **CH LIBERA**: the keys pressed (new compared to before) are appended in order; the same pattern in a row increases
  the repeats (max 99), max 64 entries. The first key goes through the Korg single-key selection (loads the pattern).
  With more than one pass: native chain mode forced (native list = first 16 entries, mask, count ≥ 2, `0x20C5D6`),
  and `chain_next` returns the next pattern of our list. Repeat of the same pattern: `chain_load` skips the load. With
  CH KORG the selection is the native one and ends our chain. In REC without CR it stays one pattern.
- **CC**: armed (1) → PLAY starts it (2). `cap_wrap` sees the start of every pass (step 0 after a start or a load, or
  step > 15) and logs the pattern of the finished pass, then samples `CLOCK+6`. At STOP: a pass stopped on its last
  step counts; the capture becomes the list, CC = 0, first pattern loaded, chain forced, "CATENA nn". No complete
  pass: it stays armed.
- **CR**: `cr_check` returns "not in REC" to the native selection, so the Korg chain stays whole in REC; the free
  chain also accepts entries. In `chain_next` and at STOP (if REC was on and there is a chain): if the pattern in
  memory (`0x2001E12C`) differs from its RAM copy → `0x20815C`.

## Tests (verify_119.py)
power_on; korg_unchanged (selection and playback identical to the original in 5 cases, reduction in REC);
free_chain (order, repeats, skipped load, reload on return, new session, single key, more than 16 entries, limit 64,
restart, back to KORG); free_chain_rec; capture (Korg patterns changed by hand, Korg chain playing, partial pass,
empty capture, CC off); cr_save (CR OFF as Korg; CR ON: saving at the change and at STOP, no saving of unchanged
patterns, persistence in the NOR journal, other patterns intact); panel_memory (real path MEMORY + keys, readout, KORG
path identical to the original); pages.

Tested on the instrument by the user (November 2026).
