# FM2 — step probability, experimental beta 1.13

3 November 2026. Base: original Korg volca FM2 firmware 1.12. (Historical document of the first beta; file names
refer to the 1.13 package.)

In the test of 10,000 passes at 50%, the native PRNG produced 4,956 plays and 5,044 skips, with every decision
matching the independent model.

This is a first real modification of the **internal sequencer**: an ARM patch compiled and tested by running the
modified image on the computer. It is not an external sequencer sending notes over MIDI.

The beta identified itself as **1.13**; it is an independent experimental modification, not a Korg update. The
restore file reinstalls the original 1.12 content byte for byte, with a 1.14 transport header so that it is accepted
after the beta.

## Behaviour

- Each step has an integer probability from 0 to 100%.
- 100% always plays the step; 0% does not start its notes.
- An intermediate value is evaluated at every pass, for the whole chord.
- The step advances even when its notes are skipped. Clock and motion continue.
- If the step is skipped, the previous sequencer notes, including those held with TIE, get the normal release. MIDI
  notes played live stay independent.
- Patterns without a valid extension follow the original behaviour, at 100%.

The probability is saved in the pattern using 28 bytes that the 1.12 format reserves. Saving, simulated reboot and
SysEx transfer of the 16 patterns are verified. The beta adds a native page on the panel.

## Panel controls

1. Hold **FUNC**, then press **EDIT**: the probability page opens.
2. Release the buttons. Touch a key **1–16** to select the step: its LED blinks, the display shows e.g. `05 P050`.
3. Move the **VELOCITY/VALUE** slider: the value goes from **0 to 100%**. Touching a step or opening the page does
   not change the pattern.
4. **PLAY** starts and stops playback also inside the page.
5. Press **FUNC** or **EDIT** to leave. Then save the pattern as usual with **FUNC + MEMORY**, followed by the
   location **1–16**.

| Display | Meaning |
|---|---|
| `05 P050` | Step 5, probability 50% |
| `12 P100` | Step 12, probability 100% |
| `03 P000` | Step 3, no new attack, length kept |

The value is the set percentage. The slider changes only that percentage while this page is open; the native
velocity parameter stays unchanged. The PROGRAM encoder is consumed without changing program while the page is open.
The other editing/memory buttons are suspended: leave the page before recording, loading or saving. The original
controls keep working outside the page. At the first slider movement the value takes the current physical position.
The selection stays independent of the step being played.

A missing or corrupted profile is shown at 100%, consistent with playback. The first edit initialises a valid
profile; all other steps start at 100% when the previous metadata were not valid.

## Preparing values

Steps are numbered 1 to 16 in the commands. For example, starting from a sequence dump, the following command sets
step 2 to 50% and step 6 to 0%:

```sh
python edit_probability.py sequence.syx sequence_probability.syx --set 2=50 --set 6=0
```

To see the values present:

```sh
python edit_probability.py sequence_probability.syx
```

To apply a profile of 16 values:

```sh
python edit_probability.py sequence.syx sequence_probability.syx --profile examples/profilo_16_step.json
```

The tool keeps the file type and the dump header. It creates a separate file and does not transmit MIDI. The
original firmware ignores the extension.

## Status at the time

Probability, panel page, persistence, 1.13 WAV packaging and exact restore to 1.12 were implemented. Resources added:
184 bytes for the probability branch, 828 bytes for the panel, 16 bytes of writable state in ITCM. No new application
SRAM allocation.
