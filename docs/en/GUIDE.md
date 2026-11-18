# STROMBOLI 1.29 — user guide

Beta firmware patch for the Korg volca fm2 (second generation, with MIDI OUT), applied to the official firmware 1.12.
Independent and unofficial: not a Korg release. 1.21 and 1.22 are tested on a real volca fm2 (November 2026); 1.23
(chorus level fix, stronger phaser, play direction and note mutation) is tested in the emulator; 1.24 (ratchet,
microtiming and swing, dirtier LOFI, page order) in the emulator (`verify_release.py`) and on a real volca fm2. 1.25
(three parts: split and layer), 1.26 (per-voice filter and LFOs), 1.27 (FM operator waveforms) and 1.28 (extended EDIT, VA
engine) and 1.29 (simple VA, Korg-style EDIT labels, effects and filter motion saved in the pattern, FUNC + 3 / 4
effect rotation, filter per part) are tested in the emulator only.

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
6. Play `01_INSTALLA_FM2_1_29_BETA.wav`: `SYS_000` … `SYS_100`, then `End`.
7. Powering on with REC shows version **1.11**: this is intended (it lets the official Korg 1.12 updater always
   install over the beta). To see the beta version: FUNC + EDIT, OCTAVE + twice (mode GL), key 16: `BETA 1.29`.

If `Err_xxxx` appears, start again from step 5, checking volume and notifications.

**Going back to the original**: play `02_RIPRISTINA_ORIGINALE_1_12.wav` (restores Korg 1.12 byte for byte) or the
official Korg updater `volca_fm2_sys_112.wav`, with the same procedure. Patterns stay compatible: extra data is
ignored by the Korg firmware.

## The FUNC + EDIT page

Hold **FUNC** and press **EDIT** to open the page; **FUNC** or **EDIT** closes it. **OCTAVE +/−** moves between
modes; the **VELOCITY slider** sets the value; key **16** is the option key in some modes. PLAY still starts and
stops. While the page is open the EDIT LED stays lit.

Order of the modes:

    P → C → GL → HU → OC → SC → tn → MOD → rt → rS → FX → dt → Fb → dr → Mu → rA → ti → CR → PA → Pb → PC → (back to P)

Since 1.24 the modulation pages (MOD, rt, rS) come before the effect pages (FX, dt, Fb), as in the audio chain:
voices → chorus / phaser / tremolo → reverb / delay (fed with the modulated signal, summed to mono) → output.

| Mode | Display | What it sets |
|---|---|---|
| P | `05 P050` | probability of the selected step (keys 1–16 select the step) |
| C | `05 C 1-2` | condition of the selected step |
| GL | `GL P100` | probability for the whole pattern; keys 1–8 quick commands, key 16 version |
| HU | `HU 07` | humanize (velocity) 0–15 |
| OC | `OC 03` | random octave 0–15 |
| SC | `SC MAG ON` | scale; key 16 = scale also for the sequencer (SEQ SI / SEQ NO) |
| tn | `tn REb` | root note of the scale |
| FX | `FX DELAY` | effect: REVRB / DELAY / LOFI (saved in the pattern) |
| dt | `dt 3-16` / `dt  257ms` | delay time; key 16 = SYNC / LIBERO (free) |
| Fb | `Fb 050 MO` | delay feedback; key 16 = MONO / PING PONG |
| MOD | `PHASER` | modulation instead of the Korg chorus: CHORUS / PHASER / TREMOLO (saved in the pattern); key 16 = STEREO / MONO (phaser), PAN / MONO (tremolo) |
| rt | `rt 1-1` / `rt 2016ms` | phaser / tremolo speed (one cycle); key 16 = SYNC / LIBERO |
| rS / Fo | `rS 050  6` / `Fo 000` | phaser resonance (key 16 = 4 / 6 / 8 stages) / tremolo shape |
| dr | `dr AVANTI` | play direction of the pattern: AVANTI / INDIET / PENDOL / CASO (saved in the pattern) |
| rA | `05 r2 75C` | ratchet of the selected step: 1–4 hits, probability, shape (press the step key again) |
| ti | `05 ti-12` / `SWING 58` | microtiming of the selected step −36…+36 ticks; step key again = swing of the pattern |
| Mu | `Mu 030  3` | note mutation in scale 0–100 %; key 16 = range ±3 / ±7 degrees (saved in the pattern) |
| CR | `CR OFF` | chain: OFF = Korg chain / ON = free chain with recording; key 16 = REC AUTO / REC FISSO |

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

- **FUNC + 4** (1.29): rotates OFF → `REVERB` → `DELAY` → `LOFI` → OFF (`FX    OFF`); the name shows while FUNC
  is held, the key 4 LED says on/off.
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
- **LOFI is dirtier** (1.24): tape hiss inside the repeat loop (it builds up with feedback), and with LOFI the
  feedback goes up to **120**: above 100 the repeats grow by themselves (self-oscillation) and the tape saturation
  holds them at a steady level; lower Fb to calm them. DELAY keeps 100 as its maximum.
- **LOFI is a tape delay** (1.22): slight wow (about 0.5 Hz) and flutter (about 7 Hz) on the repeats, each repeat
  darker and without the deepest bass (no boom at high feedback), soft tape saturation instead of the limiter.
- Since 1.29 the **FX** choice and all delay settings are saved in the **pattern** (WRITE, or CR), shared by all
  parts. A pattern saved by 1.21–1.28 gets its stored type back; the rest starts with SYNC 3-16, free time
  halfway, feedback 50.

## Phaser and tremolo (MOD, rt, rS / Fo)

They replace the Korg chorus (one at a time, as the delay replaces the reverb) and use its controls: **FUNC + 3**
(1.29) rotates OFF → `CHORUS` → `PHASER` → `TREMOLO` → OFF, the **chorus level** (FUNC + knob 7) = depth / mix (the readout shows `PHASE nnn` / `TREMO nnn` instead of
`CHORS nnn`). On/off and level are saved in the pattern by the Korg firmware, as for the chorus.

> Fixed in 1.23: from 1.16 to 1.22, FUNC + knob 7 went up to 116 and then jumped back to 013 (the ARP TYPE code took
> the value). It now goes 000–127 as in the Korg firmware.

- **MOD**: `CHORUS` (Korg, unchanged), `PHASER`, `TREMOLO`. Saved in the pattern (with WRITE, or automatically with
  CR) and changing with the pattern, also in a chain; Korg patterns and patterns from before 1.22 start with CHORUS.
  Changing type fades out (5 ms) and fades the new effect in (5 ms), without clicks.
  Key 16: **STEREO** / **MONO** with the phaser (STEREO: right side a quarter cycle ahead, wider), **PAN** / **MONO**
  with the tremolo (PAN: left and right in opposition, like the stereo tremolo of a Rhodes Suitcase).
- **PHASER**: Rhodes-style, made for electric piano and tine / bell sounds. 4, 6 or 8 stages (key 16 on the rS page,
  default 6) sweeping notches between about 100 and 2400 Hz; at full level the mix is half and half (deepest
  notches). MONO runs one phaser on the sum of the two sides (half the CPU).
- **TREMOLO**: the volume pulses; at full level from full to silent.
- **rt**: speed, as the length of one cycle. Key 16: **SYNC** / **LIBERO**. LIBERO: 20000 ms (20 s) to 100 ms
  (`rt 2016ms`). SYNC: `1-16` (one sixteenth), `1-8`, `1-4`, `1-2`, `1-1` (one bar), `2-1`, `4-1` (four bars),
  following the clock in use and restarting with PLAY, so the movement stays aligned to the bar.
- **rS** (phaser): resonance 000–100; since 1.23 it goes much higher (at 100 the phaser sings and whistles), with a
  soft analog-style saturation that keeps the peaks under control. The stage count is shown at the end (`rS 050  6`).
  **Fo** (tremolo): shape 000 (smooth) to 100 (almost on/off). With CHORUS the pages show `rt --` and `rS --`.
- Since 1.29 type, speed, SYNC/LIBERO, STEREO/PAN, resonance, stages and shape are saved in the **pattern**;
  defaults: CHORUS, LIBERO about 2 s, STEREO / PAN, resonance 50, 6 stages, shape 0.
- CPU: the 8-stage STEREO phaser with the reverb is the heaviest combination of the firmware. If the instrument
  clicks or slows down, use 6 or 4 stages or MONO.

## Play direction (dr) and note mutation (Mu)

Both are saved in the pattern (with WRITE, or automatically with CR); Korg patterns and patterns from before 1.23
play AVANTI with Mu 000.

**dr** — direction: `AVANTI` (forward, Korg), `INDIET` (backward, 16 → 1), `PENDOL` (pendulum: one loop forward,
one backward; steps 1 and 16 repeat at the turn), `CASO` (a random step every sixteenth). The step LEDs follow the
played step. A loop is still 16 steps: chains, conditions (1-2, 2-4…) and pattern changes stay on the bar. Motion
(recorded knob moves) follows time, not the direction. With REC on the pattern always plays forward, so you record
in the right place.

**Mu** — mutation in scale, Turing Machine style. `Mu 000`…`100` is the probability that a step changes note each
time it plays; key 16 = range: `3` (up to 3 scale degrees up or down) or `7` (up to an octave), shown at the end
(`Mu 050  3`).
- Each time a step plays, with probability Mu it gets a new random offset of −3…+3 (or −7…+7) degrees from **its own
  note in the pattern** (0 included = back to the original); the offset stays until that step mutates again, so the
  sequence evolves slowly.
- Mutated notes are in the scale and tonic of the SC / tn pages, also with the scale off. Chords move together.
- `Mu 000` locks the sequence as it is; selecting the pattern again (or its return in a chain) restores the original
  notes.
- The pattern is never changed: mutated notes are heard, not saved. Mu and range are saved.

## Ratchet (rA), microtiming and swing (ti)

All saved in the pattern (with WRITE, or automatically with CR); Korg patterns and patterns from before 1.24 have
everything off. With everything off the sequencer is identical to the Korg firmware, tick by tick.

**rA — ratchet.** As on the P and C pages: press the step key, move the slider. 13 positions: 1 hit, then 2, 3 or 4
hits at 25 / 50 / 75 / 100 % probability. The display shows `05 r2 75C` (step 5, 2 hits, 75 %; nothing for 100 %).
The hits divide the sixteenth evenly (2 = 32nds, 3 = triplets, 4 = 64ths), each with a proportionally shorter gate.
**Press the selected step's key again** to change the volume shape: `PARI` (all equal, P), `CALA` (decrescendo, C),
`CRESCE` (crescendo, S). The ratchet only plays when the step plays: probability, conditions and muted steps work
as always, the ratchet probability comes on top.

**ti — microtiming.** Select a step, the slider moves it from −36 to +36 ticks (a sixteenth is 72 ticks):
`05 ti-12` early, `05 ti 20` late. **Press the selected step's key again** for the **swing** of the pattern:
`SWING 50` (straight) to `SWING 75`; it delays the 2nd, 4th, 6th… sixteenth of every bar (66 ≈ triplet feel) and
adds to the step microtiming. Pressing another step goes back to the microtiming.
- The first step of a loop cannot be early (the next pattern of a chain loads on the bar).
- Ratchet hits fit in the time left until the next step (a late step's hits are closer together).
- Motion is not moved. With a play direction (dr) the microtiming follows the step, the swing follows the position
  in the bar.

## Parts: split and layer (PA, Pb, PC)

1.25 makes the volca multitimbral: up to three different sounds at once.

| Part | Sound |
|---|---|
| **A** | the program you play and edit as always (knobs, EDIT, motion) |
| **b** | a program of the internal bank (1–64) |
| **C** | another program of the internal bank |

Every part has a keyboard zone. A note plays every part whose zone holds it: zones side by side are a **split**
(bass below, pad above), zones that overlap are a **layer** (two or three sounds on the same note), and you can
mix the two. With b and C off and A left as it is, the volca plays exactly as with 1.24.

Three pages after CR: `PA`, `Pb`, `PC`. On each page keys 1–11 choose the parameter and the slider sets it; the
first letter on the display is the part.

| Key | Readout | Parameter |
|---|---|---|
| 1 | `Pr` | program. b and C: `OFF`, or 1–64 with the start of the name (`b05 Disto`). A: `APr LIVE` |
| 2 | `Lo` | lowest note of the zone (`bLo DO  4`) |
| 3 | `Hi` | highest note of the zone |
| 4 | `Oc` | octave, −3 to +3 |
| 5 | `Pn` | pan, `L7` (hard left) to `R7`; `C` = centre |
| 6 | `LE` | level, 000 to 100 |
| 7 | `Vo` | voices: `--` = free, or 1–6 |
| 8 | `Ch` | MIDI channels: `OFF`, or the channel of the part (`bCh 03`). One switch for the three parts |
| 9 | `dL` | lowest velocity the part plays (0–127) |
| 10 | `dH` | highest velocity the part plays |
| 11 | `dF` | fade: `--` = hard switch, or 08 16 24 32 48 64 96 velocities |

Notes are shown as DO RE MI FA SOL LA SI (C D E F G A B) with the octave number; `DO 4` is middle C (MIDI note
60). The slider covers all 128 notes, one semitone per step. Part b or C plays only when it has a program; part A
always plays in its zone (to silence it, set Lo above Hi). A note outside every zone is silent.

The volca keyboard has 27 keys, from an F to a G: with OCTAVE in the middle it runs from `FA 3` to `SOL 5`
(`DO 4` is the eighth key), and each OCTAVE step moves it by an octave. Zones are fixed on the notes.

**Velocity zones and fades.** `dL` and `dH` are the velocity zone of the part: it plays only the notes whose
velocity is between the two (MIDI keyboard, sequencer, arpeggiator; the volca keyboard has no velocity). `dF`
adds a fade: near the inner edge of the zone (`dL` when above 1, `dH` when below 127) the sound fades over the
chosen width instead of switching. Example, a crossfade from A to b: PA `dH 096`, `dF 32`; Pb `dL 064`,
`dF 32`. Between 64 and 96 both play, one going out and one coming in, at about constant power. A part at level
zero uses no voice.

**MIDI channel per part.** Key 8 (`Ch`) on any of the three pages, slider to the right. From MIDI IN the channel
of the volca plays part A, the next channel part b, the one after part C. Channel 10 is skipped (usually drums):
with the volca on 9 the parts are on 9, 11 and 12; on 16 they are on 16, 1 and 2. With the channels on, each part
plays over the whole keyboard (Lo / Hi do not apply to MIDI notes) and has its own note-off, so the same note
can sound on two parts. On the channel of b or C: Program Change chooses the program of the part, CC 123 / 120
silence that part only, modulation wheel and aftertouch act on the voices of that part only. No sustain pedal,
pitch bend or arpeggiator on those two channels (the pitch bend of the volca channel moves every voice), and
their notes are not sent to MIDI OUT or recorded. The volca keyboard, the sequencer and the arpeggiator still
follow the zones.

**Modulation wheel and aftertouch.** The Korg firmware ignored them. Now the modulation wheel (CC 1) opens the
vibrato (LFO pitch depth) and channel aftertouch opens vibrato and tremolo (LFO pitch and amplitude depth), on
top of what the program already has; speed and waveform are those of the program's LFO. A program with no pitch
sensitivity gets a medium one while the controller is up; the tremolo is heard only on programs whose operators
have amplitude sensitivity. With the controllers at zero the sound is identical to before. They work without the
parts too.

**Voices.** There are still six voices in all, one for every sound of a note: six notes with one part, three
with two layered parts, two with three. When more voices are needed than are free, the oldest ones go; the new
note always plays complete. `Vo` limits the voices of a part: when the part needs one more it releases its own
oldest note (as if you lifted the finger) and never takes voices from the other parts. Limits that add up to six
are reserved voices: 3 + 3, 2 + 4 (two-voice bass, four-voice chords), 2 + 2 + 2, or 1 for a monophonic part.

**Good to know.** Knobs and EDIT work on part A; the ATTACK and DECAY knobs act on all parts. Chorus / phaser /
tremolo and reverb / delay are common to all parts. Sequencer, arpeggiator, keyboard and MIDI IN play the parts
by the zone of the note. With UNISON the voices per note stay those of UNISON. The `Vo` limit does not apply to
arpeggiator notes. The parts, the velocity zones and the channel switch are saved in the pattern (WRITE, or
CR); Korg patterns and patterns from earlier versions have the parts off. Not there yet: LFO crossfade between
parts.

## Filter and LFOs — 1.26, in EDIT since 1.29

Every voice has its own 12 dB filter (LP, bP, HP) with an envelope, plus two LFOs. Settings are program
parameters, edited in **EDIT** page A (see "EDIT and the program") and saved with SAVE. With parts, every part
uses the filter of its own program (b and C: the one saved in the bank); the filter LFOs are those of part A.

- **FUNC + TRANSPOSE**: cutoff (`CUTOF 000-127`); **FUNC + VELOCITY**: resonance (`RESO 000-127`). Moving one with
  the filter off turns on the low pass. MIDI: CC 74 cutoff, CC 71 resonance. Aftertouch opens the cutoff.
- **Filter motion** (1.29): with PLAY and REC on, cutoff and resonance moves (FUNC + TRANSPOSE / VELOCITY, CC 74 /
  71) are recorded on the steps like Korg motion (the first move fills every step) and saved with the pattern.
  FUNC + 14 (motion clear) clears it too.
- The pages FL and LF are gone (1.29).
- CPU: the filter is the heaviest addition (about 15 % more with six voices, filter and two LFOs).

## Operator waveforms (WAvE) — 1.27

Every FM operator can use one of eight waveforms instead of the sine only (as on the Yamaha TX81Z and DX11).
In **EDIT**: choose the operator with OPERATOR +/−, turn the PROGRAM knob to its last parameter, **WAvE** (after
dEtU); the VELOCITY slider chooses the wave. Sounding voices change at once. Readout `3 WAvE db` = operator 3,
wave db.

| Wave | Shape |
|---|---|
| `Si` | sine (as always) |
| `HA` | half sine (positive half only) |
| `34` | three quarters of a sine |
| `PU` | quarter-sine pulses, two per period |
| `AL` | alternating quarter sines, one positive and one negative |
| `db` | a whole sine at twice the frequency, then silence |
| `dA` | two positive half waves at twice the frequency, then silence |
| `Hb` | half sine and a half wave at twice the frequency |

The waves change the sound most on modulators; on carriers the waves with silence sound like an organ or a narrow
pulse. They are saved in the program like the other parameters (save the program as usual); changing program
without saving loses them, as any edit. The Korg program SysEx (backup, Sound Librarian) keeps them. A DX7 voice
imported by SysEx always starts with six sines (the DX7 format has no waveforms), so it sounds exactly as before;
exporting to Dexed or a DX7 loses them. Parts b and C play the waves saved in their bank program. The processor
works exactly as with the sine: the waves cost nothing more. At power-on the volca prepares the tables once
(a quarter of a millisecond, before anything can play).

## EDIT and the program — 1.29

The Korg EDIT: EDIT to enter, OPERATOR +/− chooses operator 1–6 or A (whole program), the PROGRAM knob the
parameter, the VELOCITY slider the value; you play the keyboard while editing; SAVE as usual. Labels and values
follow the Korg style: 4 letters and 0–99 (`A CUtF 64`), 50 = zero where a sign is needed; a mark between label
and value means "changed from the saved program".

Operators 1–6: after the Korg parameters, `WAvE` (waveform). Page A, after the program name:

| Label | Setting |
|---|---|
| `EnGn` | engine: FM / VA |
| `FLtr` | filter: OF (off) LP bP HP |
| `CUtF` `rESo` | cutoff, resonance |
| `EnvA` | envelope amount (above 50 opens, below 50 closes) |
| `FAtK` `FdEC` `FSUS` `FrEL` | filter envelope: attack, decay, sustain, release |
| `FtrK` | key tracking (99 = full) |
| `FvEL` | velocity on the envelope amount |
| `L1Fr` | LFO 1 wave: Si tr SU (saw up) Sd (down) Sq (square) SH (random) |
| `L1rt` | rate (0.05–30 Hz) |
| `L1dP` | depth |
| `L1to` | destination: Cu cutoff, rE resonance, AM volume, XF crossfade between parts A and b |
| `L1Sy` | sync to the tempo: OF / On |
| `L1dv` | with sync: one cycle every 00=1 01=2 02=4 … 06=64 sixteenths |
| `L2Fr` … `L2dv` | LFO 2 (destination also L1 = rate of LFO 1) |

**Program** (SAVE): Korg parameters, waveforms, engine, filter and its LFOs. Programs saved by Korg or by earlier
betas start with the filter off; a Korg program SysEx dump does not carry the filter (it goes back to the
defaults), nor does a DX7 import.

**Pattern** (WRITE, CR): besides the Korg data, every effect setting (types, sync, times, feedback, phaser and
tremolo) and the filter motion. Program changes leave the effects alone.

## VA engine — 1.29

EDIT page A, `EnGn` = VA. A two-oscillator synth:

| Operator | Role |
|---|---|
| OP1 | oscillator 1 — WAvE `SA` saw, `Sq` square, `PU` pulse, `tr` triangle, `Si` sine; ratio/detune, level, envelope |
| OP2 | oscillator 2 — same waves |
| OP3 | sub / noise — `S1` one octave below OSC 1, `S2` two octaves, `no` noise; level = amount |
| OP4 | PWM — pulse width of `PU`, with its envelope |
| OP5 | pitch of OSC 2 — its envelope raises OSC 2 up to one octave |
| OP6 | unused |

ALGORITHM: 1 MIX, 2 SYNC (OSC 2 restarts with OSC 1), 3 RING, 4 FM (OSC 2 modulates OSC 1), 5 SYNC+FM, 6 MIX with
OSC 2 an octave up, 7 RING + SUB, 8 CROSS (OSC 1 modulates OSC 2); 9 onwards repeat. Saved in the program; a DX7
import is always FM; parts b and C use the engine of their program. VA costs less CPU than FM.

## Chain (CR)

One page, **CR**. With **CR OFF** the volca behaves exactly like the Korg firmware (chain = range between two keys).
With **CR ON** you get the free chain and recording while it plays. Not saved: at power-on CR OFF, REC AUTO. The
chain itself, like the Korg chain, is lost at power-off. Switching from CR ON to OFF ends the free chain; the pattern
that is playing goes on. (1.19 had three pages, CH, CC and CR: CH and CC were removed in 1.21.)

**Free chain (CR ON)**
- Hold MEMORY and press the pattern keys in the order you want. The same key pressed again right after = a repeat.
  Example: 1, 1, 2, 1, 3 → plays 1 1 2 1 3, then again.
- The display shows `CH05  P03`: 5 entries in the chain, last pattern added 3.
- Up to 64 entries, each repeated up to 99 times. Every new press of MEMORY starts a new chain. A single key = a
  single pattern. The LEDs show the first 16 patterns of the chain.
- A repeated pattern is not reloaded, so manual tweaks stay for all its repeats. STOP and PLAY from the start go
  back to the first entry.
- Adding patterns while the chain plays does not restart the current pattern: it goes on and the chain moves on at
  the end of the loop.

**Recording while the chain plays (CR ON)**
- REC goes on and off whenever you like, also while the chain plays and without stopping. The pattern you recorded
  into is saved to its memory location (like WRITE), if it changed: when the chain moves on, when REC goes off (by
  hand or after a motion) and at STOP. Without REC nothing is saved.
- **Warning**: this overwrites saved patterns and cannot be undone. Back up via SysEx first.

**FUNC during a chain (CR ON)**: the Korg firmware ignores FUNC + keys 1–16, FUNC + MEMORY (WRITE), FUNC + PLAY
(ACTIVE STEP) and REC while a chain plays. With CR ON they work as without a chain.

**Pattern copy — FUNC + MEMORY (CR ON, REC on)**: on an empty pattern (no notes, no motion) of the chain, FUNC +
MEMORY copies the pattern played before it, with everything (notes, motion, program, parameters, effects,
probabilities, arpeggio, humanize, random octave), and saves it. The display shows `CPY 01-02`; the sequence goes on
from the same step. On a pattern that is not empty, or without REC, FUNC + MEMORY is the Korg WRITE.

**REC FISSO (page CR, key 16)**: `REC AUTO` = Korg, after a motion recording the volca leaves REC after one pass;
`REC FISSO` = REC stays on until you press REC or STOP. With REC FISSO the page shows `CR ON   F`.

## Program Change (MIDI in)

The volca receives Program Change on its MIDI channel and changes the program (the sound), as the PROGRAM knob
does; patterns do not change. PC 0–63 → programs 1–64; PC 64–127 start again from the first (64 = program 1). MIDI
reception (Korg global setting, key 7 at power-on with FUNC) must be on. The Korg firmware ignores Program Change.

## Glossary of the panel words

| Display | Meaning |
|---|---|
| `LIBERO` | free (free delay time or modulation speed) |
| `PHASE nnn`, `TREMO nnn` | level of the phaser / tremolo (the Korg chorus level) |
| `rt`, `rS`, `Fo` | rate (speed), resonance, shape (forma) |
| `dr`, `AVANTI`, `INDIET`, `PENDOL`, `CASO` | direction: forward, backward (indietro), pendulum (pendolo), random (caso) |
| `Mu` | mutation |
| `rA`, `r2`, `PARI` / `CALA` / `CRESCE` (P / C / S) | ratchet, hits, volume shape: even / falling / rising |
| `ti`, `SWING` | microtiming (tick), swing |
| `REC FISSO` / `REC AUTO` | REC stays on / REC ends by itself after a motion (Korg) |
| `CPY 01-02` | pattern 1 copied onto pattern 2 |
| `SCALA` | scale |
| `SEQ SI` / `SEQ NO` | sequencer yes / no |
| `T RIPARTE` / `T SPEGNE` | key restarts / key turns off |
| `RESET ALL`, `COPY ALL`, `COND OFF`, `RANDOM`, `ALL 75` | quick commands (GL) |
| `DO RE MI FA SOL LA SI` | C D E F G A B; `b` = flat |
