# Technical notes 1.18: delay instead of the reverb (selectable)

## The Korg reverb (1.12)
- Audio interrupt in ITCM at `0x0010`, one per stereo frame. State at `0x20000010`: +0x10/+0x14 output, +0x20/+0x24
  voices, +0x28/+0x2C effect pair, +0x50 effect level (follows +0x54 by 1/128 per frame), +1 effect on.
- Chain: voices (`0x10DA`) → chorus (`0x12AC`) → `[+0x28] = L + R` → **reverb `0x1460(r0 = 0x20000038)`**, called
  through the ITCM literal `0x023C` (= `0x1461`) → stereo effect output multiplied by +0x50 and added to the dry
  signal.
- The reverb runs at **half rate** (5-coefficient decimation filter, two alternating phases) on a **48 KiB buffer at
  `0x20029B00..0x20035AFF`** (12,288 words). State at `0x20001A54` (+0 buffer pointer, +0xD0 head).
- On/off: **FUNC + key 4** → `0x200111CC` (FUNC key table) → SRAM veneer `0x20015168` (literal `0x2001516C` =
  `0x0020C8B7`) → bit 2 of pattern byte 0x45 → `0x20453C`: +1 = on, +0x54 = level or 0. FUNC + 3 = chorus.
- Level: parameter 5 (`0x20012F48`), pattern byte 0x49 (also motion and CC), `0x20EA84`: 0..127 → +0x58
  (127 = 0.89 in Q30). The display builds "REVRB nnn" in the buffer `0x20002958` and calls the text routine
  `0x20591C`.
- Sample rate: I2S2 (`0x40003800`) master with MCLK, I2SDIV = 2 → fs = I2SCLK / 1024; PLLI2S N = 200, R = 4,
  PLLM = 12 → I2SCLK = 51.2 MHz if HSE = 12.288 MHz (PLLQ = 9 gives 48 MHz to USB only with this crystal) →
  **fs = 50 kHz**, reverb at 25 kHz. The note pitch in the emulator is consistent with about 50 kHz. If it were
  different, only the milliseconds shown in LIBERO would change (SYNC measures time in frames and stays right).
- Sequencer clock: 72 ticks per 16th; every tick goes through `0x208CF8`, which first calls the arpeggiator tick
  `0x20C40C` (already hooked by 1.16), with any clock source.

## Hooks
| Address | Original | New | Purpose |
|---|---|---|---|
| ITCM `0x023C` (literal) | `0x00001461` | `0x00002059` | effect call in the audio interrupt → `fx_audio` |
| SRAM `0x2001516C` (veneer literal, logical offset `0x2316C`) | `0x0020C8B7` | `0x0000205D` | FUNC + 4 → `fx_toggle` (original + message) |
| `arp_tick` (1.16) | — | `bl tempo_tick` at the entry | measure of frames per 16th |
| `panel_display` | — | "REVRB " → "DELAY "/"LOFI  " in the buffer `0x20002958` | level readout |

`fx_audio` calls the original reverb (type REVRB) or the delay; then the interrupt applies the level and the Korg
on/off as always. No Korg data changes: back on 1.12 a pattern with the effect on plays with the reverb.

## State (ITCM `0x3F80`, 128 bytes, written by the image)
+00 type 0 REVRB 1 DELAY 2 LOFI · +01 active configuration (type | ping-pong<<2, 0 = reverb) · +02 SYNC ·
+03 ping-pong · +04 division 0..8 · +05 LIBERO slider 0..127 · +06 feedback 0..100 · +07 phase · +08 frame counter ·
+0C frame of the last 16th · +10 frames per 16th (6250 = 120 BPM) · +14 frame of the last tick · +18 tick 0..71 ·
+19 change 0/1 fade/2 clear · +1A counter · +1C input low-pass · +20 first sample of the pair · +24 write position ·
+28 delay in samples, 20.12 · +2C/+30 damping L/R · +34..+40 previous/current outputs.
At power-on: REVRB, SYNC, 3-16, LIBERO 64, feedback 50, MONO. Not saved. LOFI table in ITCM `0x1A00` (256 × int16),
texts at `0x1940`.

## Algorithm (per frame at 50 kHz)
1. Input `x = L + R`; low-pass `lp += (x−lp)/2 + (x−lp)/8` (≈ 7.5 kHz).
2. Odd frame: `lp` is kept, the average of the previous and current output is sent (linear interpolation 25 → 50
   kHz) and the delay moves towards the set value: `D += sat12((T − D) >> 9)`, i.e. at most half a sample per sample
   ("tape" glide).
3. Even frame: 25 kHz sample `s = average >> 13` (16-bit scale). Interpolated read `y = s0 + (s1 − s0)·frac/4096` at
   `w − D`. Damping of the return `d += 3(y − d)/4` (≈ 5.5 kHz per pass), feedback `fb·321/32768` (100 → 0.98).
   Mono: `in = s + fb·d`. Ping-pong: `L ← s + fb·dR`, `R ← fb·dL`. Soft knee above ±24576, then 16-bit saturation.
4. Output `y << 12` (= input/2 → with REVRB 127 the echo is 0.89 of the dry signal).

Memory: DELAY 16 bit, 24,576 samples mono (983 ms) or 12,288 × 2 (491 ms); LOFI 8 bit A-law (sign, 3-bit segment,
4-bit mantissa of |v|>>4): 49,152 (1966 ms) or 24,576 × 2 (983 ms). Margin of 4 samples.

Time: LIBERO `250 + v²·(max − 250)/127²` samples (10 ms .. max). SYNC `frames_per_16·k/12` with k in sixths of a 16th:
3, 4, 6, 8, 9, 12, 16, 18, 24 (1-32, 1-24, 1-16, 1-12, 3-32, 1-8, 1-6, 3-16, 1-4); halved until it fits.

Tempo measure: `tempo_tick` counts every tick; every 72 ticks `period = frame now − frame at the previous 16th`,
accepted between 400 and 200,000 frames. Pause > 25,000 frames between two ticks: counting restarts from that tick.
Without ticks the last value stays (120 BPM at power-on).

Change of type or of MONO/PING PONG: fade of the running effect over 256 frames, buffer cleared at 48 words per frame
(256 frames, output at zero), then state reset and start of the new effect (the reverb restarts from an empty buffer).
Time, feedback, SYNC/LIBERO and division do not interrupt.

## Load (instructions per frame, whole interrupt, 6 voices + chorus, emulator)
| | peak | average |
|---|---|---|
| reverb 1.17 | 2848 | 2818 |
| reverb 1.18 (through fx_audio) | 2876 | 2846 |
| DELAY / ping-pong | 2768 / 2789 | 2756 / 2768 |
| LOFI / ping-pong | 2783 / 2819 | 2763 / 2781 |
| effect change (512 frames) | 2918 | 2809 |

The time computation is in the odd frame and the four formats have dedicated paths, to keep the peak low. Real cycles
(memory waits, pipeline) are not measured.

## Interface
FUNC+EDIT page: P → C → GL → HU → OC → SC → tn → **FX → dt → Fb** → P.
- FX: slider REVRB / DELAY / LOFI ("FX DELAY ").
- dt: SYNC → slider division ("dt 3-16  "); LIBERO → slider time ("dt  257ms"). Key 16: SYNC / LIBERO.
- Fb: slider 0..100, "Fb 050 MO" / "Fb 050 PP". Key 16: MONO / PING PONG.
- FUNC + 4: "REVRB ON/OFF", "DELAY ON/OFF", "LOFI ON/OFF".
- The display has neither the dot nor the "t" useful for dotted notes and triplets: the divisions are fractions of a
  bar, as in the Korg ARP DIV.

## Tests (verify_118.py)
power_on, reverb_unchanged (interrupt output identical to the original in 4 cases), dsp_model (ARM = independent
Python model, sample by sample and final buffer, 8 configurations, over 700,000 frames, with a time change while
echoes play), times (LIBERO, SYNC at 120 BPM, halving, L/R order of ping-pong), isr_integration (effect off = original;
first echo at 2T; decay; level), transitions, tempo (60–240 BPM, restart), cpu, panel_pages, func4_and_label.

Not tested in the emulator: real interrupt timing on the hardware, real listening, clock stopped with the sequencer
stopped (if the internal clock does not run when stopped, SYNC keeps the last measured tempo). The delay was then
used on the instrument (1.18 and 1.19).
