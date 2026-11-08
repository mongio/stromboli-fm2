# STROMBOLI 1.19: repository files

Not needed to update the FM2: the instructions are in `GUIDE.md`. The technical notes are in this folder, the sources
and scripts in the repository root.

| File | Purpose |
|---|---|
| `src/fm2_119.S` | ARM/Thumb source of 1.19, blob in ITCM at 0x2000 |
| `src/fm2_119_flash.S` | Chain code (1.19), blob in flash at 0x0020FC40 |
| `verify_119.py` | Tests of CH LIBERA, CC, CR with the journal model |
| `TECHNICAL_NOTES_1_19.md` | Korg chain, hooks and how 1.19 works |
| `verify_118.py` | Delay tests: independent sample-by-sample model, times, ISR, effect changes, tempo, CPU, pages |
| `TECHNICAL_NOTES_1_18.md` | Delay: Korg reverb, buffer, hook in the audio interrupt, algorithm, tempo measure, interface |
| `verify_117.py` | Tests of scales, humanize and random octave |
| `TECHNICAL_NOTES_1_17.md` | Scales: hooks, note maps, sequencer; humanize and octave |
| `verify_116.py` | Tests of the arpeggio modes and MIDI OUT |
| `TECHNICAL_NOTES_1_16.md` | Arpeggiator: generated modes, compatibility, MIDI OUT |
| `verify_115.py` | HOLD tests |
| `TECHNICAL_NOTES_1_15.md` | HOLD: virtual sustain and KEY mode |
| `build_patch.py` | Builds the 1.19 image from the original Korg 1.12, checking every pre-image |
| `build_release.py` | Generates the two WAVs (install 1.19, restore 1.12 with a 1.15 header) |
| `verify_114.py` | Tests of the 1.14 features |
| `verify_patch.py`, `verify_panel.py` | Tests inherited from 1.13 plus the new ones |
| `verify_release.py` | Full check: rebuilds and decodes the WAVs, installs via FSK |
| `probability_format.py` | Formats PRB1 (1.13), PRB2 (1.14/1.15) and PRB3 (1.16–1.19) |
| `edit_probability.py` | Edits the probabilities of a pattern or SysEx dump file (see `README_1_13.md`) |
| `build/`, `reports/`, `dist/` | Generated (not in the repository): image, listing, results, WAVs |
| `reference/` | Put the Korg 1.12 updater downloaded from Korg here (not in the repository); optionally the images of betas 1.13–1.18 for the upgrade tests |
| `release/` | WAV check scripts copied into `dist/` |
| `TECHNICAL_NOTES_1_14.md` | Firmware map (phase 0), format, hooks, semantics, tests |
| `TECHNICAL_NOTES_1_13.md`, `README_1_13.md` | Documentation of beta 1.13 |

To reproduce: Python 3.11+, `pip install -r requirements.txt`, LLVM 18 and `python3 build_release.py`, then
`python3 verify_release.py`.
