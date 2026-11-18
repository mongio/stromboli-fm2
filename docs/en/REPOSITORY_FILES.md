# STROMBOLI 1.28: repository files

Not needed to update the FM2: the instructions are in `GUIDE.md`. The technical notes are in this folder, the sources
and scripts in the repository root.

| File | Purpose |
|---|---|
| `verify_128.py` | 1.28 tests: Korg EDIT parameters identical, program block (EDIT, save, program change, journal), WAv and EnG in EDIT, VA engine against the Korg FM and wave models, processor load |
| `TECHNICAL_NOTES_1_28.md` | Korg EDIT hooks, STROMBOLI program block and its flash storage, VA engine |
| `verify_127.py` | 1.27 tests: no waves identical to 1.12, tables, oracle against the Korg engine with the sine table replaced, operators, storage and SysEx, pages, processor load |
| `TECHNICAL_NOTES_1_27.md` | FM operator waveforms: Korg operator routines, hooks, where the wave is stored, table chain, page Wv |
| `verify_126.py` | 1.26 tests: filter off identical to 1.12, sample-by-sample model, frequency response, envelope, LFOs, controls, pages, processor load |
| `TECHNICAL_NOTES_1_26.md` | Per-voice filter: audio point, coefficients, envelope, LFOs, controls |
| `verify_125.py` | 1.25 tests: parts off identical to 1.12, program of the part, split, layer, voices, octave, pan, level, pages, record |
| `TECHNICAL_NOTES_1_25.md` | Three parts: Korg engine, hooks, voices per note, voice limit, storage, pages |
| `verify_124.py` | 1.24 tests: timeline identical to 1.12, ratchet, microtiming, swing, record, pages, LOFI |
| `TECHNICAL_NOTES_1_24.md` | Sequencer clock, ratchet, microtiming and swing, dirtier LOFI, page order |
| `verify_123.py` | 1.23 tests: FUNC + knob 7, direction, mutation, storage and pages |
| `TECHNICAL_NOTES_1_23.md` | Chorus level, more resonant phaser, direction and mutation per pattern |
| `src/fm2_128.S` | ARM/Thumb source of 1.28, audio code (delay, phaser, tremolo) and data, blob in ITCM at 0x2000 |
| `src/fm2_128_sram.S` | Non-audio code (panel, pages, clock, chains), blob in SRAM at 0x200164B0 (free padding of the ff13 section) |
| `src/fm2_128_flash.S` | Chain, MIDI and types-in-pattern code, blob in flash at 0x0020FC40 |
| `verify_122_mod.py` | Phaser and tremolo tests: independent sample-by-sample model, sound, transitions, CPU, pages, types in the pattern |
| `TECHNICAL_NOTES_1_22.md` | Space (code in SRAM), phaser and tremolo instead of the chorus, tape LOFI |
| `verify_122.py`, `verify_122_more.py` | Tests of CR, REC and FUNC during a chain, copy, REC FISSO, Program Change, effect in the pattern |
| `TECHNICAL_NOTES_1_21.md` | CR-only chain, REC and FUNC during a chain, copy, REC FISSO, Program Change, effect in the pattern |
| `TECHNICAL_NOTES_1_19.md` | Korg chain, hooks and how 1.19 works (CH and CC removed in 1.21) |
| `verify_118.py` | Delay tests (with the 1.22 tape LOFI): independent sample-by-sample model, times, ISR, effect changes, tempo, CPU, pages |
| `TECHNICAL_NOTES_1_18.md` | Delay: Korg reverb, buffer, hook in the audio interrupt, algorithm, tempo measure, interface |
| `verify_117.py` | Tests of scales, humanize and random octave |
| `TECHNICAL_NOTES_1_17.md` | Scales: hooks, note maps, sequencer; humanize and octave |
| `verify_116.py` | Tests of the arpeggio modes and MIDI OUT |
| `TECHNICAL_NOTES_1_16.md` | Arpeggiator: generated modes, compatibility, MIDI OUT |
| `verify_115.py` | HOLD tests |
| `TECHNICAL_NOTES_1_15.md` | HOLD: virtual sustain and KEY mode |
| `build_patch.py` | Builds the 1.28 image from the original Korg 1.12, checking every pre-image |
| `build_release.py` | Generates the two WAVs (install 1.28, restore 1.12 with a 1.15 header) |
| `verify_114.py` | Tests of the 1.14 features |
| `verify_patch.py`, `verify_panel.py` | Tests inherited from 1.13 plus the new ones |
| `verify_release.py` | Full check: rebuilds and decodes the WAVs, installs via FSK |
| `probability_format.py` | Formats PRB1 (1.13), PRB2 (1.14/1.15) and PRB3 (1.16–1.22) |
| `edit_probability.py` | Edits the probabilities of a pattern or SysEx dump file (see `README_1_13.md`) |
| `build/`, `reports/`, `dist/` | Generated (not in the repository): image, listing, results, WAVs |
| `reference/` | Put the Korg 1.12 updater downloaded from Korg here (not in the repository); optionally the images of betas 1.13–1.25 for the upgrade tests |
| `release/` | WAV check scripts copied into `dist/` |
| `TECHNICAL_NOTES_1_14.md` | Firmware map (phase 0), format, hooks, semantics, tests |
| `TECHNICAL_NOTES_1_13.md`, `README_1_13.md` | Documentation of beta 1.13 |

To reproduce: Python 3.11+, `pip install -r requirements.txt`, LLVM 18 and `python3 build_release.py`, then
`python3 verify_release.py`.
