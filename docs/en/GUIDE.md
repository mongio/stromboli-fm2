# STROMBOLI 1.19 — user guide

Beta firmware patch for the Korg volca fm2 (second generation, with MIDI OUT), applied to the official firmware 1.12.
Independent and unofficial: not a Korg release. Tested on a real volca fm2 (1.19, November 2026) and in the
emulator (`verify_release.py`).

> **Only for the volca fm2** (second generation, 2022: 6 voices, MIDI IN and OUT on 3.5 mm TRS minijacks). Not for the
> first volca fm (2016: 3 voices, MIDI IN only, 5-pin DIN): different firmware, do not install it there.

The panel shows Italian words in a few places; a glossary is at the end.

> **The WAV files contain data: never play them on speakers or headphones.** Connect the computer's audio output
> to the volca's **SYNC IN** only.

## Install

1. Back up your patterns and programs via SysEx.
2. Use the power adapter or fresh batteries.
3. Optional: check the files with `VERIFICA_FILE.command` (macOS) or `VERIFICA_FILE.bat` (Windows).
4. On a Mac: turn on Do Not Disturb, turn off sound effects, use QuickTime Player, volume high. Cable from the
   headphone output to SYNC IN.
5. Power on while holding **FUNC + PLAY**: the display shows `uPdatE`.
6. Play `01_INSTALLA_FM2_1_19_BETA.wav`: `SYS_000` … `SYS_100`, then `End`.
7. Powering on with REC shows version **1.11**: this is intended (it lets the official Korg 1.12 updater always
   install over the beta). To see the beta version: FUNC + EDIT, OCTAVE + twice (mode GL), key 16: `BETA 1.19`.

If `Err_xxxx` appears, start again from step 5, checking volume and notifications.

**Going back to the original**: play `02_RIPRISTINA_ORIGINALE_1_12.wav` (restores Korg 1.12 byte for byte) or the
official Korg updater `volca_fm2_sys_112.wav`, with the same procedure. Patterns stay compatible: extra data is
ignored by the Korg firmware.

## The FUNC + EDIT page

Hold **FUNC** and press **EDIT** to open the page; **FUNC** or **EDIT** closes it. **OCTAVE +/−** moves between
modes; the **VELOCITY slider** sets the value; key **16** is the option key in some modes. PLAY still starts and
stops. While the page is open the EDIT LED stays off (normal).

Order of the modes:

    P → C → GL → HU → OC → SC → tn → FX → dt → Fb → CH → CC → CR → (back to P)

| Mode | Display | What it sets |
|---|---|---|
| P | `05 P050` | probability of the selected step (keys 1–16 select the step) |
| C | `05 C 1-2` | condition of the selected step |
| GL | `GL P100` | probability for the whole pattern; keys 1–8 quick commands, key 16 version |
| HU | `HU 07` | humanize (velocity) 0–15 |
| OC | `OC 03` | random octave 0–15 |
| SC | `SC MAG ON` | scale; key 16 = scale also for the sequencer (SEQ SI / SEQ NO) |
| tn | `tn REb` | root note of the scale |
| FX | `FX DELAY` | effect: REVRB / DELAY / LOFI |
| dt | `dt 3-16` / `dt  257ms` | delay time; key 16 = SYNC / LIBERO (free) |
| Fb | `Fb 050 MO` | delay feedback; key 16 = MONO / PING PONG |
| CH | `CH KORG` | chain: KORG / LIBERA (free order) |
| CC | `CC OFF` | live chain capture: OFF / ON (REC while capturing) |
| CR | `CR OFF` | recording while a chain plays: OFF / ON |

## Step probability and conditions (P, C, GL)

- Each step has a probability from 0 to 100%. 100% always plays, 0% never starts new notes. The decision is per step:
  a chord plays or is skipped as a whole. A skipped step keeps its length; held notes (TIE) are released normally.
- **Conditions** play a step only on some passes of the pattern: `1-2` first of every 2 passes, `2-2` second of
  every 2, `1-3` … `3-3`, `1-4` … `4-4`, `1ST` only on the first pass after PLAY, `N1ST` on every pass except the
  first. Order of decision: Korg mute/rest → condition → probability.
- **GL** scales all probabilities of the pattern: effective probability = step probability × GL / 100.
- **Quick commands** in GL (keys 1–8): 1 all steps 100%, 2 all 75%, 3 all 50%, 4 all 25%, 5 random 25/50/75/100%,
  6 copy the selected step's probability and condition to all steps, 7 all conditions off, 8 reset (all 100%,
  no conditions, GL 100). Key 16 shows the
  beta version.
- Saved in the pattern (save with FUNC + MEMORY as usual). The Korg firmware ignores this data.

## HOLD

- **FUNC + OCTAVE +**: HOLD on/off (`HOLD ON` / `HOLD OFF`). It works like a sustain pedal for the keyboard and
  for MIDI notes; the sequencer is not held. Not saved.
- **FUNC + OCTAVE −**: what a key does on a held note: `T RIPARTE` (restarts it; with the arpeggiator, a new chord
  replaces the held one) or `T SPEGNE` (turns that note off). Useful for drones without the arpeggiator.

## Arpeggiator

- The **ARP TYPE** knob has 17 positions: the 10 Korg types, then `UPdn1`–`UPdn3` (up-down over 1–3 octaves),
  `Conv` (converge), `dIvr` (diverge), `PEdL` (pedal: the lowest note between the others), `Chrd` (repeated chord).
- The type is saved in the pattern. In the Korg firmware a pattern with a new mode plays Rise1.
- The arpeggio notes are sent on **MIDI OUT** (3.5 mm TRS jack).

## Scales (SC, tn)

- **FUNC + SAVE**: scale on/off (`SCALA ON` / `SCALA OFF`). Keyboard and MIDI notes snap to the nearest note of
  the scale (on a tie, the higher one). Recording stores the corrected note.
- 15 scales: CROM (chromatic), MAG (major), MIN (natural minor), ARM (harmonic minor), DOR, FRI (Phrygian),
  LID (Lydian), MIS (Mixolydian), PMA / PMI (major / minor pentatonic), BLU (blues), TON (whole tone),
  HIR (Hirajoshi), INS (In Sen), ARA (double harmonic).
- **tn**: root note, shown with flats (`REb` = C#/Db, `MIb`, `SOLb`, `LAb`, `SIb`; DO RE MI FA SOL LA SI = C D E F G
  A B), because the display has no sharp sign.
- Key 16 in SC: `SEQ SI` also corrects the sequencer while it plays (the pattern is not changed), `SEQ NO` leaves
  it alone.
- Global, not saved: at power-on the scale is off, MAG, DO, SEQ NO.

## Humanize and random octave (HU, OC)

- **HU** 0–15: random velocity ± 3 × level on sequencer notes.
- **OC** 0–15: each sequencer note jumps one octave up or down with probability level/15 (stays in scale).
- Saved in the pattern.

## Delay (FX, dt, Fb)

The Korg reverb stays; you can choose a delay instead. They share the same memory, so only one works at a time.

- **FUNC + 4**: effect on/off, as for the Korg reverb (saved in the pattern). The display says which: `REVRB ON`,
  `DELAY OFF`, `LOFI ON`…
- **Level**: the Korg reverb level control is the delay mix (the readout shows `DELAY nnn` / `LOFI nnn`). At maximum
  the echo is almost as loud as the dry sound.
- **FX**: `REVRB` (Korg reverb), `DELAY` (clean 16-bit: up to 0.98 s mono or 0.49 s per side ping-pong), `LOFI`
  (dirty 8-bit: up to 1.97 s mono or 0.98 s per side).
- **dt**: delay time. Key 16 switches **SYNC** / **LIBERO** (free).
  - SYNC follows the clock in use (internal, SYNC IN or MIDI clock): `1-32`, `1-24` (16th triplet), `1-16`, `1-12`
    (8th triplet), `3-32` (dotted 16th), `1-8`, `1-6` (quarter triplet), `3-16` (dotted 8th), `1-4`. A division too
    long for the memory at slow tempos is halved. Before the clock first runs it assumes 120 BPM.
  - LIBERO: from 10 ms to the maximum, shown in ms (`dt  257ms`).
- **Fb**: feedback 000–100; the display also shows MO (mono) or PP (ping-pong). Key 16: **MONO** / **PING PONG**
  (first repeat left, second right…).
- Repeats get a little darker every time, like a tape delay; a soft limiter keeps feedback 100 under control.
  Changing the time while it plays glides like tape. Changing FX or MONO/PING PONG fades out, clears the memory
  and restarts clean (about 10 ms).
- Global, not saved: at power-on REVRB, SYNC 3-16, free time halfway, feedback 50, MONO.

## Chain (CH, CC, CR)

Three independent options. With CH KORG, CC OFF, CR OFF the volca behaves exactly like the Korg firmware. Not saved:
at power-on everything is off. The chain itself, like the Korg chain, is lost at power-off.

**CH LIBERA — free-order chain**
- Hold MEMORY and press the pattern keys in the order you want. The same key pressed again right after = a repeat.
  Example: 1, 1, 2, 1, 3 → plays 1 1 2 1 3, then again.
- The display shows `CH05  P03`: 5 entries in the chain, last pattern added 3.
- Up to 64 entries, each repeated up to 99 times. Every new press of MEMORY starts a new chain. A single key = a
  single pattern, as in the Korg firmware. The LEDs show the first 16 patterns of the chain.
- A repeated pattern is not reloaded, so manual tweaks stay for all its repeats; a different pattern is loaded from
  memory, as the Korg chain does. STOP and PLAY from the start go back to the first entry.
- With CH KORG the chain is the usual range between two keys, and a Korg selection ends the free chain.

**CC — live chain capture**
1. Set CC to ON (`CC ON`).
2. Press PLAY: capture starts (`CC REC` on the page).
3. Play and change patterns as you like (MEMORY + key, Korg or free chains). The volca notes every pass with the
   pattern that was playing.
4. STOP: the sequence becomes a free chain, already compacted (e.g. 1 ×4, 2 ×2, 1 ×4). The display shows
   `CATENA nn` (nn = entries) and CC goes back to OFF.
5. PLAY: you hear it again, the same.

Only complete passes count: a pass cut by STOP is not counted (stopping exactly on the last step counts). With no
complete pass, CC stays ON. Up to 64 entries.

**CR — recording while the chain plays**
- With CR ON, REC no longer reduces the chain to its first pattern (Korg or free chain). You record into the pattern
  that is playing; when the chain moves on, the pattern just recorded is saved to its memory location (like WRITE),
  if it changed. The same happens at STOP.
- **Warning**: this overwrites saved patterns and cannot be undone. Back up via SysEx first.
- It saves only during REC and only patterns that changed. Korg behaviour that stays: recording a knob movement
  (motion) makes the volca leave REC by itself after one pass.

## Glossary of the panel words

| Display | Meaning |
|---|---|
| `LIBERA`, `LIBERO` | free (free chain, free delay time) |
| `CATENA` | chain |
| `SCALA` | scale |
| `SEQ SI` / `SEQ NO` | sequencer yes / no |
| `T RIPARTE` / `T SPEGNE` | key restarts / key turns off |
| `RESET ALL`, `COPY ALL`, `COND OFF`, `RANDOM`, `ALL 75` | quick commands (GL) |
| `DO RE MI FA SOL LA SI` | C D E F G A B; `b` = flat |
