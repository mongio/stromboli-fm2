# Mario Texture's STROMBOLI

*Erupts on time, never the same way twice.*

**A beta firmware patch for the Korg volca fm2** (second generation, with MIDI OUT). It is unofficial and applies to the official firmware 1.12:
step probability and conditions, HOLD, new arpeggiator modes and arpeggio on MIDI OUT, musical scales, humanize and random octave, a delay as an alternative to the reverb, and an evolved chain (free order with
repeats, live chain capture, recording while a chain plays).

> [!WARNING]
> **Only for the volca fm2** (the second-generation volca fm, 2022: 6 voices, MIDI IN **and OUT** on 3.5 mm TRS
> minijacks, chorus and reverb). It is **not** for the first volca fm (2016: 3 voices, MIDI IN only, 5-pin DIN), which has a different
> firmware and updater. Do not try to install it on the first volca fm.

*[Versione italiana: LEGGIMI.md](LEGGIMI.md)* — a few panel words are Italian; the guide has a glossary.

> Unofficial: not made or endorsed by Korg. This repository holds **only the patch and the tools**: no Korg firmware,
> no ready-made update WAVs. You build the WAVs yourself from the official updater you download from Korg. Going back
> is always possible with the official Korg 1.12 updater (or the restore WAV built here). Use at your own risk.

Version **1.23 beta** (chorus level fix, stronger phaser, play direction and note mutation per pattern): tested in the emulator; 1.21 and 1.22 are tested on a real volca fm2.

## What it adds

| Feature | How |
|---|---|
| Step probability, conditions (1-2, 2-4, 1ST, …), global probability, quick commands | FUNC + EDIT page, modes P, C, GL |
| HOLD (virtual sustain), key restarts / stops | FUNC + OCTAVE +, FUNC + OCTAVE − |
| 7 new arpeggio modes (up-down 1–3 octaves, converge, diverge, pedal, chord), arpeggio on MIDI OUT | ARP TYPE knob |
| 15 scales with root note, also for the sequencer | FUNC + SAVE, modes SC, tn |
| Humanize (velocity) and random octave, per pattern | modes HU, OC |
| Delay or lo-fi delay instead of the reverb (choice saved in the pattern): tempo sync or free time, feedback, mono / ping-pong | modes FX, dt, Fb; FUNC + 4 on/off |
| Free-order chain with repeats (up to 64 entries), recording on a chain with auto-save, FUNC functions and REC during a chain, pattern copy, REC stays on after a motion | mode CR; FUNC + MEMORY |
| Program Change in: changes the program (PC mod 64) | MIDI IN |
| Rhodes-style phaser or tremolo (stereo / pan) instead of the chorus, saved in the pattern; free or tempo-synced speed | modes MOD, rt, rS / Fo; FUNC + 3 on/off |
| Tape-style LOFI delay: wow and flutter, darker repeats, soft saturation | mode FX = LOFI |
| Play direction per pattern: forward, backward, pendulum, random | mode dr |
| Note mutation in scale (Turing Machine style), per pattern | mode Mu |

Everything is described in the **[user guide](docs/en/GUIDE.md)**, with the [test checklist](docs/en/TESTS_1_23.txt);
the technical notes for each version are in [`docs/en/`](docs/en/REPOSITORY_FILES.md). The Italian originals are in
`docs/` (`GUIDA_1_23.txt`, `PROVE_1_23.txt`, `NOTE_TECNICHE_1_xx.md`).

## Build the update WAVs

Requirements: Python 3.11+, LLVM 18 tools (`llvm-mc`, `llvm-objcopy`, `llvm-readobj`, `llvm-nm`), and
`pip install -r requirements.txt` (numpy, unicorn, capstone, keystone-engine).

1. Download the official **volca fm2 System Updater 1.12** from
   [Korg](https://www.korg.com/us/support/download/software/0/892/4964/) and put `volca_fm2_updater_0112.zip`,
   unchanged, in `reference/`.
2. `python3 build_release.py` → in `dist/`: `01_INSTALLA_FM2_1_23_BETA.wav` (install),
   `02_RIPRISTINA_ORIGINALE_1_12.wav` (restore the exact original 1.12), `SHA256SUMS.txt` and the guides
   (`GUIDE_EN.md`, `LEGGIMI.txt`).
3. Optional but recommended: `python3 verify_release.py` (about 10 minutes) runs the whole test suite and writes
   `dist/ESITO_VERIFICHE.txt`.

The build is reproducible: the same updater gives the same WAVs. Install with the Korg procedure (power on holding
FUNC + PLAY, play the WAV into SYNC IN). **The WAVs are data: never play them on speakers or headphones.**

## How it is made and tested

- `build_patch.py` rebuilds the Korg image from the updater, checks every byte it touches against the original, adds
  the patch code (`src/fm2_123.S` in ITCM, `src/fm2_123_sram.S` in unused SRAM padding, `src/fm2_123_flash.S` in a free flash area) and fixes the section
  checksums. The bootloader and the updater receiver are never changed; the beta reports application version 1.11, so
  the official Korg 1.12 WAV is always accepted to go back.
- The `verify_*.py` suites execute the real firmware code in an ARM emulator (Unicorn): sequencer, chain, journal and
  flash model, audio interrupt (the delay, phaser and tremolo are compared sample by sample with an independent Python model), panel, MIDI,
  and the full WAV → FSK → install → boot path, including the return to the original with the official Korg WAV.
- Not covered by the emulator: real timing on the hardware, listening. Those are checked on the instrument with the
  [test checklist](docs/en/TESTS_1_23.txt); 1.21 and 1.22 are tested on a real volca fm2, 1.23 not yet.

## Licence

The patch and the tools are free software under the GNU GPL version 3 only (`LICENSE`); see
[LICENSING.md](LICENSING.md). The Korg firmware is not included and is covered by Korg's own licence.
