# FM2 1.14 beta: technical notes

7 November 2026. Base: Korg volca FM2 firmware 1.12. 1.14 extends the 1.13 beta (step probability, tested on the FM2
by the user on 7/11/2026).

## Phase 0: firmware map

**Pattern (1,920 bytes)**
- 0–79: header. 0 `PTST`, 4 tag `E8 4E`, 6 active/muted steps mask, 12 ACTIVE STEP mask, 15 number of active steps,
  16–41 motion flags of the lanes.
- 80 + 112·i: step i. 0–11 notes (6×u16), 12–17 per-voice field, 18–23 velocity (all zero = rest), 24–29 gate,
  30–42 parameters, 43–107 motion (13 lanes × 5 points), 108–111 not written by the legacy-format conversion.
- **1872–1887: used by the Korg firmware**, one flag per step written at `0x20012904` (`pattern[0x750 + step] = 1`).
  They are not free.
- 1888–1915: reserved, free. 1.13 used them for PRB1, 1.14 for PRB2.
- 1916–1919: `PTED`.

The per-step bytes 31 and 108–111 are not written by the legacy conversion. They might be free, but nobody has proven
it: to be evaluated in phase 2.

**Buttons** (ids of the dispatcher `0x20012184`): 0 FUNC, 3 PLAY, 4 EDIT, 6 OCTAVE/OPERATOR + (calls `0x20015260`
with +1), 7 OCTAVE/OPERATOR − (calls with −1). Ids 1, 2 and 5 correspond to SAVE/EXPORT, MEMORY and REC, not yet
assigned with certainty.

**Sequencer**: `0x00208CF8` is the clock. The current step is at `CLOCK+0xB` (`0x200031A3`). The only caller of the
step routine `0x0020B7BE` is the clock (`0x0020903E`). Transport start is `0x002090C0`, reached from `0x00209190`
(r2=1, start from the beginning: sets the step to 0xFF) and from `0x00209174` (r2=0, continue). It is hooked to reset
the pass counter.

**Updater**: the bootloader accepts only a transport version greater than the installed version byte (`0x420D`).
Besides the bootloader, that byte is read only by the version screen with REC (`0x20012294`) and by the header of
exported SysEx dumps (`0x20013EF8`, `0x20013F22`). No code uses it to convert or reject data.

**Choice for 1.14**: the installed version byte is **11** and the install WAV header is 1.14. As a result:
- the **official Korg 1.12** WAV (unchanged) is accepted over the beta. Tested with a complete FSK installation of
  the file taken from the Korg archive;
- the beta installs over 1.12 and 1.13, and over itself;
- powering on with REC shows 1.11. In GL mode, key 16 shows "BETA 1.14".

The package's restore file (1.15 header, Korg 1.12 payload) is needed only for those with 1.13, which declared 13.
Future betas must keep the byte at 11 and use a transport header greater than 12.

**Free ITCM**: from `0x174C` to `0x3FFF` it is all FF padding. The original firmware contains no literal or `movw`
pointing into that range: the only constants found are arithmetic values.

## Implementation

A single ITCM blob at `0x2000` (1,988 bytes), assembled with **llvm-mc**:

| Address | Content |
|---|---|
| `0x2000..0x201F` | table of 8 `B.W` (step, start, keys, buttons, ADC, display, encoder, LED) |
| `0x2020..0x27C3` | code and literal pool |
| `0x3E00..0x3EFF` | texts: conditions (12×4) and command messages (8×12) |
| `0x3F00..0x3F1F` | state: page, step, mode, message, keys, last step, first pass, pass counter |

The hooks are the same as 1.13, plus a new one: `0x002090C0` (`f8b5 1646` → `b.w 0x2004`). Every pre-image is
compared before the replacement. The bootloader sector stays identical.

**Keystone bug**: with several literal pools, Keystone computes jumps to absolute addresses wrongly (`bl #0x2094A4`
assembled as `0x2094CC`, with errors up to 0x62 bytes). In 1.13 it did not happen because each file had a single
pool, at the end. 1.14 uses no absolute jumps: all external addresses go through literals
(`ldr r12,=addr; blx/bx r12`) and the assembler is llvm-mc. All literals and jumps of the blob were re-checked with
capstone.

## PRB2 format (bytes 1888–1915)

| Offset | Content |
|---|---|
| +0 | tag `0xA2` |
| +1..+16 | probability 0–100 per step |
| +17..+24 | conditions as nibbles (step 2k low nibble, 2k+1 high nibble), values 0–11 |
| +25 | pattern probability 0–100 |
| +26..+27 | FNV-1a-32 of +0..+25 folded to 16 bits, little endian |

An invalid block means 100%, no conditions, pattern 100. A valid PRB1 (1.13) is read, for the probabilities only, and
converted at the first edit. The single-bit test covers all 224 bits: they all fall back to 100%. A first version with
an 8-bit check let one collision in 256 through, and was replaced.

## Semantics

- Decision order: native rest or muted step → condition → probability.
- Effective probability = (p·pattern + 50) / 100. At 0% and 100% no random numbers are consumed, nor when a
  condition is false.
- Pass: a step with an index not greater than the previous one opens a new pass. The counter goes from 0 to 839
  (multiple of 2, 3 and 4); "first pass" is a separate flag.
- Condition A:B is true when pass mod B = A−1. 1ST holds only on pass 0, N1ST on all later passes.

## Tests (49/49)

- 33 groups from 1.13 (PRB1 playback, native regressions, panel in P mode, boot, FSK installation) run on the 1.14
  image.
- 10 new groups (`verify_114.py`): conditions with the native clock over 25 passes, ACTIVE STEP mask, reset with the
  native PLAY, probability × pattern matrix (3,600 cases), fail-open over 224 bits, modes and slider (128 positions
  each), PRB1 conversion, quick commands, NOR journal with reboot, +/− keys outside the page compared with the
  original, page open during playback.
- Release: version and CRC guards, recovery, 6-voice audio with the page open, real FSK installation 1.12 → 1.14 and
  1.13 → 1.14, restore 1.14 → 1.12 identical byte for byte, both with the package file and with the original
  **official Korg 1.12 WAV**.

Real interrupt timing and the physical panel controls remain untested here.
