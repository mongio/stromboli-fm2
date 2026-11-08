# FM2 Probability beta 1.13 — integration and tests

## Insertion into the original code

The builder accepts only the original WAV with the SHA-256 expected by the 1.12 dossier, and the logical image:

`daf7052f0483a3bd82958f142d81038aeaec011d6f018de31261b8f5baed5e40`.

The patch point is in the routine that applies a step, `0x0020B7BE`. At `0x0020B7CA` the original code contains:

```asm
ldrh r3, [r4, #6]
mov.w r8, #0
```

These six bytes are checked before being replaced. The patch inserts a jump to its own code at `0x00002000`, in the
FF padding of section FF11. At the end it returns to `0x0020B7D0`, normally re-executing the stride multiplication
and the following original instructions.

The added code decides whether to keep the original mask read from the pattern or to pass zero in the register the
routine uses for the current step. **The mask saved in the pattern is not modified during playback.** So the native
routine handles release, allocation and bookkeeping of the notes, as for a disabled step. The clock stays outside
this change.

The beta adds the panel entry points described below. The builder keeps all the other bytes of the image, except the
application minor 1.13 and the two checksum fields FF00 and FF11. It checks that all five LE16 sums modulo 65536 are
zero again. Format and size remain those of the 1.12 base; the application version is 1.13, marked experimental in
the package. The FM tables, the 32 kernels and the chorus/reverb kernels are not rewritten.

## Memory and CPU context

| Resource | Added use |
|---|---|
| Probability decision, ITCM | 184 bytes from `0x00002000` |
| Panel code, ITCM | 828 bytes from `0x00002400` |
| Jump in the application flash | 6 bytes at `0x0020B7CA` |
| New writable state | 16 bytes in ITCM at `0x00003F00`; no new SRAM allocation |
| Metadata in the existing pattern | 28 bytes, total pattern size unchanged |
| Extra stack of the probability branch | at most 64 bytes, including the call to the native PRNG; not including the native UI path |

The source uses the generator already present at `0x002094A4`. The values 0% and 100%, patterns without a valid
extension, steps already disabled and native rests do not consume random numbers. With intermediate values the
original PRNG advances: its sequence is shared with the native functions that already use it, including the random
arpeggios.

The routine saves and restores the needed context and keeps the stack aligned for calls. The tests check SP and the
eight callee-saved registers. The chosen ITCM space contains FF in the original image; in the tests the native boot
loads exactly the added code. This does not replace a measurement of load and timing deadlines on the hardware.

## Pattern extension

The pattern stays 1,920 bytes long. The extension uses the reserved bytes 1888–1915; the original end marker, bytes
1916–1919, stays intact.

| Absolute offset in the pattern | Bytes | Meaning |
|---:|---:|---|
| 1888 | 4 | ASCII tag `PRB1` |
| 1892 | 16 | One percentage 0–100 per step |
| 1908 | 4 | LE32 complement of the tag: `0xCEBDADAF` |
| 1912 | 4 | FNV-1a-32 of the sixteen values, LE32 |

Before applying a percentage the code checks both tags, the range of all values and the digest. A missing or invalid
extension restores the original behaviour at 100%. The test alters each of the 224 bits of the extension separately
and checks the fallback.

The native copy, SysEx and persistence routines already move the whole 1,920-byte block. The tests confirm that the
extension is kept in all 16 slots, after SysEx reception and after writing/reading back the modelled NOR journal.

## Musical semantics

The decision is one per step: a chord plays entirely or is skipped. MIDI input notes independent of the sequencer are
not subject to the probability. A skipped step keeps its length in the clock flow.

A skip sends the normal releases to the sequencer notes held before, also in the TIE case. Envelope and reverb tails
continue normally: 0% means no new attack, not forced silencing of all audio. Playback resumes at the next step that
passes the filter.

## Tests

Details, addresses and modelled boundaries are in `reports/patch_verification.json`.

- Matrix of 10,100 cases: all percentages 0 to 100 against all results 0–99. Only the PRNG is replaced in this matrix
  to force each result.
- 10,000 passes at 50% with the native PRNG actually executed; each decision and the final state compared with an
  independent formula.
- Original vs patch at 100%, with chords, gate, TIE, mute and rests: events, application state, preserved registers
  and stack.
- Resume after a skipped step, TIE release and ACTIVE STEP scrolling.
- A live MIDI note kept while the internal notes are skipped.
- 16 patterns with different values through SysEx and the NOR journal, with a simulated reboot.
- Profile editor on raw patterns, current SysEx and saved-location SysEx.
- 64 passes with mixed probabilities through the native path to FM, chorus, reverb and software output. The 32,768
  stereo frames match the configured original in every pass, with the corresponding mute mask.
- The 15 functional suites of the original dossier run on the modified image, with probability not configured: all
  passed.
- FSK reception, staging, modelled installation, reset and loading of the added code, then 0%/100% test in the same
  CPU instance.

The release check uses the actual original 1.12 image as the installed one, not a synthetic minor. The beta WAV has
a 1.13 header and application. The restore has a 1.14 transport header and the original 1.12 payload. The native
checks compare the transport version with the minor in flash: both directions are accepted. A normal 1.12 header on
beta 1.13, and beta 1.13 on itself, are still rejected with ERR_VER.

The two WAVs on disk are decoded independently and go through the native ARM instructions for FSK reception, parser,
staging, SPI routing, flash compare/erase/write, reset and CPU initialisation. The panel and the 0%/100% step are
tested after installation in the same CPU. The observed installed payload is used as the starting image of the
restore. At the end all 196,608 bytes match the original 1.12. The erased internal sectors are checked; the bootloader
sector stays identical and is not erased. SPI destinations do not reach the user data area. Physical flash/SPI timing
and errors remain outside the model.

## Scope of the delivery

It is a prototype of the behaviour and of its ARM integration, verified with Unicorn and modelled peripherals. No FM2
programming, analog tests, or real-time load/interrupt measurements with the physical panel controls were done. The
two WAVs are meant for the experimental hardware test; the logical binary in the build folder is for analysis and
technical reproduction.

The patch test is separate from the 23 groups that earlier concerned only the original firmware: here the new ARM
bytes are executed and the added probabilistic behaviour is verified.

## Panel integration, beta 1.13

The panel code is assembled at `0x00002400`. The manifest records the size and bytes of every change. A table of six
jumps exposes the entry points for keyboard, buttons, ADC, display, encoder and LEDs. The 16-byte writable state is
at `0x00003F00`: page flag, selected step and key masks. The builder checks that code and state replace only original
FF bytes and do not overlap. The boot copies the whole FF11 section, including the initial zeros.

| Original hook | Change |
|---|---|
| Veneer literal `0x0020FC1C` | Raw keyboard, through the original matrix converter |
| Veneer literal `0x0020FAA4` | Buttons after the native three-scan debounce |
| Veneer literal `0x0020FB24` | Encoder: events consumed while the page is open |
| Prologue `0x002059D0` | ADC parameter 3 changes the probability while the page is open |
| Prologue `0x0020591C` | Text requests keep the modal screen |
| Prologue `0x0020548C` | Blinking LED selection through the native masks |

The original prologues and literals are compared byte by byte before being changed. Outside the page the original
instructions run and execution resumes at the right instruction boundary. Calls between ITCM and code in SRAM use full
Thumb addresses and BLX; direct jumps are within range.

The page opens when EDIT (native id 4) is pressed in FUNC mode `0x12` (FUNC is id 0). Releasing the combination does
not close it. FUNC or EDIT close the page and call the native redraw. Keys still held are filtered until released, to
avoid new attacks on re-entry. PLAY keeps the normal start/stop. The page uses UI state `0x49`; its ITCM flag stays
the reference even if the native stop restores UI state zero.

The quantised ADC 0..127 becomes `(v*100+63)//127`; all 101 values are reachable. The first edit recreates the
metadata if invalid, then updates the single step and the FNV. Entering, selecting and leaving are read-only on the
pattern. The display generates nine characters, e.g. `05 P050  `, through the original ASCII/glyph conversion. The
test also compares the eight rows of the native segment buffer and the LED masks, without replacing those routines.

Four new test groups check all 16 steps, all 128 slider positions, entry/debounce/release/exit, ADC through the native
polling, PLAY, keeping the page, behaviour outside the page, corrupted metadata, NOR with simulated reboot and arrival
of the value at the ARM sequencer. The full test also repeats the V1 regressions and the FSK/install/boot path on the
new image. The physical panel I/O and interrupt timing are not simulated electrically.

## Fixes for the hardware test, and resources

The raw sentinel value 0x80000000 is ignored only if it is the whole frame; frames with that bit and keys present are
processed as the native code does. The MIDI source uses r2=1 in the parameter setter: the probability interception
requires r2=0. So MIDI CC41 keeps changing velocity, even with the page open. Both cases have dedicated ARM tests.

The beta changes only the application minor at offset 0x420D, besides the changes declared by the builder. All the
first 16 KiB of flash are identical to the original base. 9,392 bytes of ITCM padding remain in the image, after
subtracting 184 bytes of probability, 828 bytes of panel and 16 bytes of state from the original 10,420 bytes of
padding. This is a static measurement, not a full certification of free RAM or of real-time audio deadlines.
