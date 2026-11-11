/* volca FM2 experimental firmware 1.22 - ITCM blob at 0x00002000: entry
 * table and audio code only (effects in the audio ISR). Everything else is
 * in SRAM (src/fm2_122_sram.S, 0x200164B0, original FF padding of the ff13
 * section) and is reached through the trampolines below; the chain code is
 * in flash (src/fm2_122_flash.S).
 * 1.22: modulation effect (CHORUS / PHASER / TREMOLO) instead of the native
 * chorus call (ITCM literal 0x0238), state 0x3B80, phaser coefficients at
 * 0x3A00; LOFI delay with tape character (wow and flutter, darker repeats,
 * low cut in the loop, soft saturation).
 * chain code is a second blob in flash, src/fm2_120_flash.S).
 * 1.20: page CR only (ON = free chain + recording on it, OFF = Korg chain).
 * 1.19: chain options (state 0x1D00); MEMORY press flag.
 * 1.18: DELAY / LOFI delay as an alternative to the reverb (same buffer,
 * same on/off and level), pages FX, dt, Fb; state at 0x3F80..0x3FFF.
 * 1.17: global scale (nearest note, ties up) on keyboard, MIDI in and,
 * optionally, live sequencer playback; humanize and random octave per pattern.
 * Runtime note maps in ITCM 0x1800..0x191F (original FF padding), text and
 * scale tables at 0x1E00. State 0x3F30 scale on, 0x3F31 scale, 0x3F32 tonic,
 * 0x3F33 live sequence option.
 * Base: original Korg 1.12. Extends the 1.13 beta (per-step probability)
 * with Elektron-style step conditions, quick commands and a pattern-wide
 * probability scale.
 *
 * ITCM layout (all original FF padding):
 *   0x2000..0x201F  entry/jump table (fixed addresses used by the builder)
 *   0x2020..        code + literal pools
 *   0x3E00..0x3EFF  read-only text tables (written by the builder)
 *   0x3F00..0x3F1F  writable state
 *     0x3F00 page open flag        0x3F01 selected step
 *     0x3F02 page mode 0=P 1=C 2=G 0x3F03 last quick command + 1 (0 none)
 *     0x3F04 previous key mask     0x3F08 raw key frame
 *     0x3F10 last sequencer step (0xFF = fresh start)
 *     0x3F11 first loop done flag  0x3F12 loop counter (u16, modulo 840)
 *
 * Pattern extension PRB2 in the reserved bytes 1888..1915 (X = pattern+0x760):
 *   X+0         tag 0xA2
 *   X+1..X+16   probability 0..100 per step
 *   X+17..X+24  condition nibbles, step 2k low nibble, 2k+1 high nibble (0..11)
 *   X+25        pattern probability scale 0..100
 *   X+26..X+27  FNV-1a-32 of X+0..X+25 folded to 16 bits, little endian
 * A valid 1.13 PRB1 block is still played (probability only) and is
 * converted to PRB2 on the first edit.
 */
.syntax unified
.thumb

/* 1.18 delay macros.
 * LIMIT reg, tmp: soft knee above +-24576, then 16-bit saturation.
 * ENCODE reg, t1, t2: 16-bit sample -> LOFI byte (sign, 3-bit segment,
 *   4-bit mantissa of |v| >> 4, A-law style).
 * FB_MONO: r0 = tap -> r1 = s16 + fb * damped(tap) (damping +0x2C).
 * FB_PP: r0, r1 = taps L, R -> r11 = s16 + fb * dR, r2 = fb * dL (limited). */
.macro LIMIT reg, tmp
    movw \tmp, #24576
    cmp \reg, \tmp
    itt gt
    subgt \reg, \reg, \tmp
    addgt \reg, \tmp, \reg, asr #2
    cmn \reg, \tmp
    itt lt
    addlt \reg, \reg, \tmp
    rsblt \reg, \tmp, \reg, asr #2
    ssat \reg, #16, \reg
.endm
.macro ENCODE reg, t1, t2
    asr \t1, \reg, #31
    eor \reg, \reg, \t1
    sub \reg, \reg, \t1
    and \t1, \t1, #0x80
    lsr \reg, \reg, #4
    usat \reg, #11, \reg
    clz \t2, \reg
    rsbs \t2, \t2, #27
    itt pl
    lsrpl \reg, \reg, \t2
    addpl \reg, \reg, \t2, lsl #4
    orr \reg, \reg, \t1
.endm
.macro CLIP3 reg, t1
    /* 1.22 tape saturation: y = x - x^3 / (3 * 2^30), x clamped to 16 bit */
    ssat \reg, #16, \reg
    smulbb \t1, \reg, \reg
    smulwb \t1, \t1, \reg
    movw r12, #21845
    smulwb \t1, \t1, r12
    sub \reg, \reg, \t1, asr #14
.endm
/* 1.22 LOFI feedback: damping (y - d) / 2, low cut d - h, h += (d - h) / 64 */
.macro TAPE_DAMP tap, d_off, h_off, out, t1
    ldr \out, [r4, #\d_off]
    sub \t1, \tap, \out
    add \out, \out, \t1, asr #1
    str \out, [r4, #\d_off]
    ldr \t1, [r4, #\h_off]
    sub \out, \out, \t1
    add \t1, \t1, \out, asr #6
    str \t1, [r4, #\h_off]
.endm
.macro FB_MONO
    ldr r1, [r4, #0x2C]
    sub r2, r0, r1
    add r2, r2, r2, lsl #1
    add r1, r1, r2, asr #2
    str r1, [r4, #0x2C]
    ldrb r2, [r4, #6]
    movw r12, #321
    mul r2, r2, r12
    mul r1, r1, r2
    add r1, r6, r1, asr #15
.endm
.macro FB_PP
    ldr r2, [r4, #0x2C]
    sub r7, r0, r2
    add r7, r7, r7, lsl #1
    add r2, r2, r7, asr #2
    str r2, [r4, #0x2C]
    ldr r11, [r4, #0x30]
    sub r7, r1, r11
    add r7, r7, r7, lsl #1
    add r11, r11, r7, asr #2
    str r11, [r4, #0x30]
    ldrb r7, [r4, #6]
    movw r12, #321
    mul r7, r7, r12
    mul r11, r11, r7
    add r11, r6, r11, asr #15
    LIMIT r11, r12
    mul r2, r2, r7
    asr r2, r2, #15
    LIMIT r2, r12
.endm

table:
    b.w tr_prob_entry     @ 0x2000  sequencer step hook
    b.w tr_start_hook     @ 0x2004  transport start (0x002090C0)
    b.w tr_panel_keys     @ 0x2008  keyboard veneer literal
    b.w tr_panel_button   @ 0x200C  button veneer literal
    b.w tr_panel_adc      @ 0x2010  ADC parameter prologue
    b.w tr_panel_display  @ 0x2014  text request prologue
    b.w tr_panel_encoder  @ 0x2018  encoder veneer literal
    b.w tr_panel_led      @ 0x201C  LED prologue
    b.w tr_note_on_hook   @ 0x2020  voice note-on 0x0020A78C (HOLD)
    b.w tr_arp_tick       @ 0x2024  arpeggiator tick 0x0020C40C (new modes)
    b.w tr_arp_start      @ 0x2028  arpeggiator note start 0x0020BDFC
    b.w tr_arp_voice_on   @ 0x202C  arpeggiator voice trigger 0x002097E4 (MIDI out)
    b.w tr_arp_step       @ 0x2030  arpeggiator step 0x0020C1F4 (MIDI out)
    b.w tr_midi_flush     @ 0x2034  MIDI out service 0x00207F2C (main loop)
    b.w tr_kbd_echo_on    @ 0x2038  keyboard / sequencer MIDI echo calls 0x0020AA8E, 0x0020A732
    b.w tr_kbd_q_on       @ 0x203C  keyboard note-on note (BL at 0x0020AA8A)
    b.w tr_kbd_q_off      @ 0x2040  keyboard note-off note (BL at 0x0020AACA)
    b.w tr_din_on         @ 0x2044  MIDI DIN note-on 0x0020AB2C
    b.w tr_din_off        @ 0x2048  MIDI DIN note-off 0x0020AB64
    b.w tr_usb_on         @ 0x204C  USB MIDI note-on 0x0020ABC0
    b.w tr_usb_off        @ 0x2050  USB MIDI note-off 0x0020ABF8
    b.w tr_seq_note       @ 0x2054  sequencer note slot store (BL at 0x0020BA6E)
    b.w fx_audio          @ 0x2058  audio ISR effect call (ITCM literal 0x023C, was reverb 0x1461)
    b.w tr_fx_toggle      @ 0x205C  FUNC+4 reverb toggle veneer literal 0x2001516C (was 0x0020C8B7)
    b.w mod_audio         @ 0x2060  1.22 audio ISR chorus call (ITCM literal 0x0238, was 0x12AD)

/* Trampolines to the SRAM entry table (same order, 4 bytes per entry). */
tr_prob_entry:
    ldr pc, =0x200164b1
tr_start_hook:
    ldr pc, =0x200164b5
tr_panel_keys:
    ldr pc, =0x200164b9
tr_panel_button:
    ldr pc, =0x200164bd
tr_panel_adc:
    ldr pc, =0x200164c1
tr_panel_display:
    ldr pc, =0x200164c5
tr_panel_encoder:
    ldr pc, =0x200164c9
tr_panel_led:
    ldr pc, =0x200164cd
tr_note_on_hook:
    ldr pc, =0x200164d1
tr_arp_tick:
    ldr pc, =0x200164d5
tr_arp_start:
    ldr pc, =0x200164d9
tr_arp_voice_on:
    ldr pc, =0x200164dd
tr_arp_step:
    ldr pc, =0x200164e1
tr_midi_flush:
    ldr pc, =0x200164e5
tr_kbd_echo_on:
    ldr pc, =0x200164e9
tr_kbd_q_on:
    ldr pc, =0x200164ed
tr_kbd_q_off:
    ldr pc, =0x200164f1
tr_din_on:
    ldr pc, =0x200164f5
tr_din_off:
    ldr pc, =0x200164f9
tr_usb_on:
    ldr pc, =0x200164fd
tr_usb_off:
    ldr pc, =0x20016501
tr_seq_note:
    ldr pc, =0x20016505
tr_fx_toggle:
    ldr pc, =0x2001650d
    .align 2
    .ltorg

/* ================================================================ */
/* 1.18: delay as an alternative to the reverb.
 * The audio ISR (ITCM 0x0010) calls the effect through the literal at
 * 0x023C with r0 -> {mono input L+R, out R}: it expects the wet stereo pair
 * back in [r0], [r0+4] and then applies the native REVRB level (pattern
 * byte 0x49, smoothed, 0 when FUNC+4 has the effect off). fx_audio runs
 * either the native reverb (0x1460) or the delay, on the same 48 KiB
 * buffer 0x20029B00..0x20035AFF. A change of type or layout fades the wet
 * signal out (256 frames), clears the buffer (48 words per frame) and only
 * then starts the new effect.
 *
 * State 0x3F80:
 *   +00 type requested 0 REVRB 1 DELAY 2 LOFI   +01 active layout key
 *   +02 SYNC (1) / LIBERO (0)  +03 ping-pong  +04 division 0..8
 *   +05 free slider 0..127     +06 feedback 0..100   +07 half-rate phase
 *   +08 frame counter  +0C frame of the last 16th  +10 frames per 16th
 *   +14 frame of the last clock tick  +18 tick count 0..71
 *   +19 transition 0 run 1 fade 2 clear   +1A transition counter
 *   +1C input lowpass  +20 first half sample  +24 write slot
 *   +28 delay in slots, 20.12   +2C/+30 feedback damping L/R
 *   +34/+38 previous output L/R  +3C/+40 current output L/R
 * Layout key = type | ping-pong << 2 (0 for the reverb).
 * Rate: the delay line runs at fs/2 (25 kHz), like the reverb. Slots:
 * DELAY 16 bit 24576 (mono) / 12288 x 2 (ping-pong); LOFI 8 bit companded
 * 49152 / 24576 x 2. */

/* r0 = layout key requested by the settings (0 = reverb). */
fx_req_key:
    movw r12, #0x3F80
    ldrb r0, [r12]
    cbz r0, fx_req_key_done
    ldrb r1, [r12, #3]
    orr r0, r0, r1, lsl #2
fx_req_key_done:
    bx lr

/* r0 = layout key -> r0 = number of slots per channel. */
fx_slots:
    and r1, r0, #3
    cmp r1, #2
    ite eq
    moveq r1, #49152
    movne r1, #24576
    ubfx r0, r0, #2, #1
    lsr r0, r1, r0
    bx lr

/* r0 = layout key -> r0 = delay length in slots (25 kHz samples).
 * SYNC: frames per 16th x (k / 6) / 2, halved until it fits.
 * LIBERO: 250 + v^2 (max - 250) / 127^2 (10 ms .. max). */
fx_samples:
    push {r4, lr}
    bl fx_slots
    sub r4, r0, #4
    movw r12, #0x3F80
    ldrb r0, [r12, #2]
    cbz r0, fx_samples_free
    ldr r0, [r12, #0x10]
    ldrb r1, [r12, #4]
    cmp r1, #9
    it hs
    movhs r1, #0
    adr r2, fx_div_k
    ldrb r1, [r2, r1]
    mul r0, r0, r1
    movs r1, #12
    udiv r0, r0, r1
fx_samples_fit:
    cmp r0, r4
    bls fx_samples_min
    lsrs r0, r0, #1
    b fx_samples_fit
fx_samples_min:
    cmp r0, #16
    it lo
    movlo r0, #16
    pop {r4, pc}
fx_samples_free:
    ldrb r0, [r12, #5]
    mul r0, r0, r0
    sub r1, r4, #250
    mul r0, r0, r1
    movw r1, #16129
    udiv r0, r0, r1
    add r0, r0, #250
    pop {r4, pc}
    .align 2
/* sixths of a 16th: 1/32 1/16T 1/16 1/8T 1/16. 1/8 1/4T 1/8. 1/4 */
fx_div_k:
    .byte 3, 4, 6, 8, 9, 12, 16, 18, 24
    .align 1

/* Audio ISR effect call (replaces the reverb 0x1460). r0 -> io pair. */
fx_audio:
    push {r4, r5, r6, r7, lr}
    movw r4, #0x3F80
    mov r5, r0
    ldr r0, [r4, #8]
    adds r0, #1
    str r0, [r4, #8]
    ldrb r6, [r4, #0x19]
    cmp r6, #2
    beq fx_clear
    cbnz r6, fx_run
    bl fx_req_key
    ldrb r1, [r4, #1]
    cmp r0, r1
    beq fx_run
    movs r6, #1
    strb r6, [r4, #0x19]
    mov r0, #256
    strh r0, [r4, #0x1A]
fx_run:
    ldrb r0, [r4, #1]
    cbnz r0, fx_run_delay
    mov r0, r5
    ldr r12, =0x00001461
    blx r12
    b fx_after
fx_run_delay:
    bl fx_delay
fx_after:
    cmp r6, #1
    bne fx_exit
    ldrh r0, [r4, #0x1A]
    ldr r1, [r5]
    asrs r1, r1, #8
    mul r1, r1, r0
    str r1, [r5]
    ldr r1, [r5, #4]
    asrs r1, r1, #8
    mul r1, r1, r0
    str r1, [r5, #4]
    subs r0, #1
    strh r0, [r4, #0x1A]
    bne fx_exit
    movs r0, #2
    strb r0, [r4, #0x19]
fx_exit:
    pop {r4, r5, r6, r7, pc}
fx_clear:
    ldrh r0, [r4, #0x1A]
    ldr r1, =0x20029B00
    add r1, r1, r0, lsl #2
    movs r2, #0
    movs r3, #0
    movs r7, #0
    mov r12, #0
    movs r6, #12
fx_clear_loop:
    stmia r1!, {r2, r3, r7, r12}
    subs r6, #1
    bne fx_clear_loop
    adds r0, #48
    strh r0, [r4, #0x1A]
    movw r1, #12288
    cmp r0, r1
    blo fx_clear_out
    bl fx_reset
fx_clear_out:
    movs r0, #0
    str r0, [r5]
    str r0, [r5, #4]
    pop {r4, r5, r6, r7, pc}

/* Buffer cleared: start the requested effect from silence. */
fx_reset:
    push {r4, lr}
    movw r4, #0x3F80
    bl fx_req_key
    strb r0, [r4, #1]
    movs r2, #0
    strb r2, [r4, #0x19]
    strh r2, [r4, #0x1A]
    strb r2, [r4, #7]
    str r2, [r4, #0x1C]
    str r2, [r4, #0x20]
    str r2, [r4, #0x24]
    str r2, [r4, #0x2C]
    str r2, [r4, #0x30]
    str r2, [r4, #0x34]
    str r2, [r4, #0x38]
    str r2, [r4, #0x3C]
    str r2, [r4, #0x40]
    str r2, [r4, #0x48]
    str r2, [r4, #0x4C]
    str r2, [r4, #0x50]
    str r2, [r4, #0x54]
    cbz r0, fx_reset_done
    bl fx_samples
    lsls r0, r0, #12
    str r0, [r4, #0x28]
    str r0, [r4, #0x44]
fx_reset_done:
    pop {r4, pc}

/* Delay, one frame. r4 = state, r5 = io pair. */
fx_delay:
    push {r6, r7, r8, r9, r10, r11, lr}
    ldr r0, [r5]
    ldr r1, [r4, #0x1C]
    sub r2, r0, r1
    add r1, r1, r2, asr #1
    add r1, r1, r2, asr #3
    str r1, [r4, #0x1C]
    ldrb r2, [r4, #7]
    eors r2, r2, #1
    strb r2, [r4, #7]
    beq fx_delay_tick
    /* first frame of the pair: keep the input, output the midpoint */
    str r1, [r4, #0x20]
    ldr r0, [r4, #0x34]
    ldr r1, [r4, #0x3C]
    asrs r0, r0, #1
    add r0, r0, r1, asr #1
    str r0, [r5]
    ldr r0, [r4, #0x38]
    ldr r1, [r4, #0x40]
    asrs r0, r0, #1
    add r0, r0, r1, asr #1
    str r0, [r5, #4]
    /* delay length glides to the target, at most 0.5 slot per slot (done
     * here, in the light frame of the pair, to keep the peak load low) */
    ldrb r0, [r4, #1]
    bl fx_samples
    lsls r0, r0, #12
    ldr r1, [r4, #0x28]
    subs r2, r0, r1
    asrs r2, r2, #9
    ssat r2, #12, r2
    add r1, r2
    str r1, [r4, #0x28]
    /* 1.22: LOFI reads at D + wow and flutter (two sine LFOs), limited to
     * the line; the other layouts read at D. */
    ldrb r0, [r4, #1]
    and r0, r0, #3
    cmp r0, #2
    bne fx_deff_store
    ldr r2, [r4, #0x50]
    movw r3, #0x6A39
    movt r3, #0x0001
    add r2, r3
    str r2, [r4, #0x50]
    asrs r2, r2, #16
    eor r3, r2, r2, asr #31
    rsb r3, r3, #32768
    mul r2, r2, r3
    asrs r2, r2, #13
    add r1, r1, r2, lsl #1
    ldr r2, [r4, #0x54]
    movw r3, #0xD25F
    movt r3, #0x0011
    add r2, r3
    str r2, [r4, #0x54]
    asrs r2, r2, #16
    eor r3, r2, r2, asr #31
    rsb r3, r3, #32768
    mul r2, r2, r3
    asrs r2, r2, #13
    add r1, r1, r2, asr #5
    ldrb r0, [r4, #1]
    tst r0, #4
    ite eq
    moveq r2, #49152
    movne r2, #24576
    sub r2, r2, #4
    cmp r1, r2, lsl #12
    it gt
    lslgt r1, r2, #12
    cmp r1, #16384
    it lt
    movlt r1, #16384
fx_deff_store:
    str r1, [r4, #0x44]
    pop {r6, r7, r8, r9, r10, r11, pc}
fx_delay_tick:
    ldr r0, [r4, #0x20]
    asrs r0, r0, #1
    add r6, r0, r1, asr #1
    asrs r6, r6, #13
    ldrb r7, [r4, #1]
    /* slots per channel */
    and r0, r7, #3
    cmp r0, #2
    ite eq
    moveq r8, #49152
    movne r8, #24576
    tst r7, #4
    it ne
    lsrne r8, r8, #1
    /* read position: i0 = w - D (integer part), i1 = i0 - 1, frac 12 bit */
    ldr r9, [r4, #0x24]
    ldr r1, [r4, #0x44]
    lsrs r2, r1, #12
    ubfx r10, r1, #0, #12
    subs r11, r9, r2
    it mi
    addmi r11, r8
    subs r12, r11, #1
    it mi
    addmi r12, r8
    ldr r0, [r4, #0x3C]
    str r0, [r4, #0x34]
    ldr r0, [r4, #0x40]
    str r0, [r4, #0x38]
    ldr r3, =0x20029B00
    and r0, r7, #3
    cmp r0, #2
    beq fx_tick8
    tst r7, #4
    bne fx_pp16
/* DELAY mono: int16 per slot */
    ldrsh.w r0, [r3, r11, lsl #1]
    ldrsh.w r1, [r3, r12, lsl #1]
    sub r1, r1, r0
    mul r1, r1, r10
    add r0, r0, r1, asr #12
    FB_MONO
    LIMIT r1, r12
    strh.w r1, [r3, r9, lsl #1]
    lsls r0, r0, #12
    mov r1, r0
    b fx_tail
/* DELAY ping-pong: L, R int16 pairs */
fx_pp16:
    add lr, r3, #2
    ldrsh.w r0, [r3, r11, lsl #2]
    ldrsh.w r1, [r3, r12, lsl #2]
    sub r1, r1, r0
    mul r1, r1, r10
    add r0, r0, r1, asr #12
    ldrsh.w r1, [lr, r11, lsl #2]
    ldrsh.w r2, [lr, r12, lsl #2]
    sub r2, r2, r1
    mul r2, r2, r10
    add r1, r1, r2, asr #12
    FB_PP
    strh.w r11, [r3, r9, lsl #2]
    strh.w r2, [lr, r9, lsl #2]
    lsls r0, r0, #12
    lsls r1, r1, #12
    b fx_tail
/* LOFI: companded bytes, decoded by the table at 0x1A00 */
fx_tick8:
    movw lr, #0x1A00
    tst r7, #4
    bne fx_pp8
    ldrb r0, [r3, r11]
    ldrsh.w r0, [lr, r0, lsl #1]
    ldrb r1, [r3, r12]
    ldrsh.w r1, [lr, r1, lsl #1]
    sub r1, r1, r0
    mul r1, r1, r10
    add r0, r0, r1, asr #12
    TAPE_DAMP r0, 0x2C, 0x48, r1, r2
    ldrb r2, [r4, #6]
    movw r12, #321
    mul r2, r2, r12
    mul r1, r1, r2
    add r1, r6, r1, asr #15
    CLIP3 r1, r2
    ENCODE r1, r2, r12
    strb r1, [r3, r9]
    lsls r0, r0, #12
    mov r1, r0
    b fx_tail
fx_pp8:
    lsls r11, r11, #1
    lsls r12, r12, #1
    ldrb r0, [r3, r11]
    ldrsh.w r0, [lr, r0, lsl #1]
    ldrb r1, [r3, r12]
    ldrsh.w r1, [lr, r1, lsl #1]
    sub r1, r1, r0
    mul r1, r1, r10
    add r0, r0, r1, asr #12
    adds r11, #1
    adds r12, #1
    ldrb r1, [r3, r11]
    ldrsh.w r1, [lr, r1, lsl #1]
    ldrb r2, [r3, r12]
    ldrsh.w r2, [lr, r2, lsl #1]
    sub r2, r2, r1
    mul r2, r2, r10
    add r1, r1, r2, asr #12
    TAPE_DAMP r0, 0x2C, 0x48, r2, r7
    TAPE_DAMP r1, 0x30, 0x4C, r11, r7
    ldrb r7, [r4, #6]
    movw r12, #321
    mul r7, r7, r12
    mul r11, r11, r7
    add r11, r6, r11, asr #15
    CLIP3 r11, r10
    mul r2, r2, r7
    asr r2, r2, #15
    CLIP3 r2, r10
    ENCODE r11, r10, r12
    ENCODE r2, r10, r12
    add r12, r3, r9, lsl #1
    strb r11, [r12]
    strb r2, [r12, #1]
    lsls r0, r0, #12
    lsls r1, r1, #12
fx_tail:
    str r0, [r4, #0x3C]
    str r1, [r4, #0x40]
    str r0, [r5]
    str r1, [r5, #4]
    adds r9, #1
    cmp r9, r8
    it hs
    movhs r9, #0
    str r9, [r4, #0x24]
    pop {r6, r7, r8, r9, r10, r11, pc}
    .align 2
    .ltorg

/* ================================================================ */
/* 1.22: modulation effect instead of the native chorus.
 * The audio ISR calls the chorus through the ITCM literal 0x0238 with
 * r0, r1 = voices L, R >> 8 and adds the returned pair (<< 8) to the dry
 * signal. Type 0 = native chorus (unchanged, direct jump when idle).
 * Level and on/off are the native chorus ones (state 0x200011D0: +0x40
 * smoothed level, +0x44 target, 0..0x1E00000), smoothed here as natively.
 *
 * State 0x3B80:
 *   +00 type requested 0 CHORUS 1 PHASER 2 TREMOLO   +01 active type
 *   +02 SYNC (1) / LIBERO (0)  +03 stereo (phaser) / pan (tremolo)
 *   +04 SYNC division 0..6 = 1, 2, 4 .. 64 sixteenths  +05 LIBERO slider
 *   +06 resonance 0..100  +07 shape 0..100
 *   +08 transition 0 run 1 fade out 2 clear 3 fade in  +0A counter
 *   +0C LFO phase  +10 LIBERO phase increment
 *   +14..+20 phaser allpass states L  +24..+30 R  +34 / +38 last output L / R
 *   +3C sixteenths since the transport start  +40 feedback Q15 (resonance)
 * A type change fades the wet signal out (256 frames), clears the chorus
 * delay lines when going back to the chorus (8 words per frame), resets the
 * phaser and fades the new effect in (256 frames). */
mod_audio:
    movw r12, #0x3B80
    ldrh r2, [r12]
    ldrb r3, [r12, #8]
    adds r2, r2, r3, lsl #16
    bne mod_dispatch
    ldr r12, =0x000012AD
    bx r12
    /* running (no transition): straight to the effect */
mod_dispatch:
    movw r3, #0x0101
    cmp r2, r3
    beq mod_ph_run
    cmp r2, r3, lsl #1
    bne mod_full
    push {r4, r5, r7, r8, r9, r10, r11, lr}
    mov r4, r12
    bl tremolo
    pop {r4, r5, r7, r8, r9, r10, r11, pc}
mod_ph_run:
    push {r4, r5, r7, r8, r9, r10, r11, lr}
    mov r4, r12
    bl phaser
    pop {r4, r5, r7, r8, r9, r10, r11, pc}
mod_full:
    push {r4, r5, r6, r7, r8, r9, r10, r11, lr}
    movw r4, #0x3B80
    ldrb r6, [r4, #8]
    cmp r6, #2
    beq mod_clear
    cbnz r6, mod_run
    ldrb r2, [r4]
    ldrb r3, [r4, #1]
    cmp r2, r3
    beq mod_run
    movs r6, #1
    strb r6, [r4, #8]
    mov r2, #256
    strh r2, [r4, #0xA]
mod_run:
    ldrb r3, [r4, #1]
    cbnz r3, mod_ours
    ldr r12, =0x000012AD
    blx r12
    b mod_after
mod_ours:
    cmp r3, #1
    bne mod_trem_call
    bl phaser
    b mod_after
mod_trem_call:
    bl tremolo
mod_after:
    cbz r6, mod_exit
    ldrh r2, [r4, #0xA]
    asrs r0, r0, #8
    mul r0, r0, r2
    asrs r1, r1, #8
    mul r1, r1, r2
    cmp r6, #1
    bne mod_fadein
    subs r2, #1
    strh r2, [r4, #0xA]
    bne mod_exit
    movs r2, #2
    strb r2, [r4, #8]
    b mod_exit
mod_fadein:
    adds r2, #1
    strh r2, [r4, #0xA]
    cmp r2, #256
    blo mod_exit
    movs r2, #0
    strb r2, [r4, #8]
mod_exit:
    pop {r4, r5, r6, r7, r8, r9, r10, r11, pc}
mod_clear:
    ldrb r2, [r4]
    cbnz r2, mod_switch
    /* back to the chorus: clear its delay lines 0x20000070..0x200011CF */
    ldrh r3, [r4, #0xA]
    ldr r5, =0x20000070
    add r5, r5, r3, lsl #2
    movs r0, #0
    movs r1, #0
    movs r2, #0
    movs r7, #0
    stmia r5!, {r0, r1, r2, r7}
    stmia r5!, {r0, r1, r2, r7}
    adds r3, #8
    strh r3, [r4, #0xA]
    movw r2, #1112
    cmp r3, r2
    blo mod_silence
mod_switch:
    ldrb r2, [r4]
    strb r2, [r4, #1]
    movs r0, #0
    add r1, r4, #0x14
    movs r2, #10
mod_zero:
    str r0, [r1], #4
    subs r2, #1
    bne mod_zero
    movs r2, #3
    strb r2, [r4, #8]
    strh r0, [r4, #0xA]
mod_silence:
    movs r0, #0
    movs r1, #0
    pop {r4, r5, r6, r7, r8, r9, r10, r11, pc}

/* Level smoothing (as the native chorus) and LFO. r4 = state.
 * Returns r2 = smoothed level, r3 = LFO phase (0 = start of the cycle).
 * Clobbers r0, r1, r12. */
mod_common:
    ldr r12, =0x200011D0
    ldr r2, [r12, #0x40]
    ldr r1, [r12, #0x44]
    subs r0, r2, r1
    it pl
    rsbpl r0, r0, #0
    asr r0, r0, #7
    it pl
    rsbpl r0, r0, #0
    sub r2, r2, r0
    str r2, [r12, #0x40]
    ldrb r0, [r4, #2]
    cbnz r0, mc_sync
    ldr r3, [r4, #0xC]
    ldr r0, [r4, #0x10]
    add r3, r0
    str r3, [r4, #0xC]
    bx lr
    /* SYNC: phase from the sixteenths counted since the start and the
     * frames since the last one; free-running at that rate without clock. */
mc_sync:
    push {r5, r6, r7}
    movw r12, #0x3F80
    ldr r0, [r12, #8]
    ldr r1, [r12, #0xC]
    ldr r5, [r12, #0x10]
    subs r0, r0, r1
    ldrb r1, [r4, #4]
    movs r6, #1
    lsl r6, r6, r1
    mul r7, r5, r6
    mov r1, #-1
    udiv r1, r1, r7
    cmp r0, r5, lsl #1
    bhi mc_sync_free
    cmp r0, r5
    it hi
    movhi r0, r5
    ldr r3, [r4, #0x3C]
    subs r6, #1
    and r3, r3, r6
    mla r0, r3, r5, r0
    mul r3, r0, r1
    str r3, [r4, #0xC]
    pop {r5, r6, r7}
    bx lr
mc_sync_free:
    ldr r3, [r4, #0xC]
    add r3, r1
    str r3, [r4, #0xC]
    pop {r5, r6, r7}
    bx lr

/* LFO phase -> sine, Q15 (parabolic approximation). */
.macro SINE out, ph, t
    asr \out, \ph, #16
    eor \t, \out, \out, asr #31
    rsb \t, \t, #32768
    mul \out, \out, \t
    asr \out, \out, #13
    ssat \out, #16, \out
.endm

/* Phase in r0 -> allpass coefficient in r0 (Q31, table 0x3A00, 65 entries
 * from 120 Hz to 1600 Hz, linear between entries). Clobbers r1-r3. */
.macro PH_COEF
    SINE r1, r0, r2
    add r1, r1, #32768
    lsr r2, r1, #10
    ubfx r1, r1, #0, #10
    movw r3, #0x3A00
    add r3, r3, r2, lsl #2
    ldr r0, [r3]
    ldr r2, [r3, #4]
    sub r2, r2, r0
    asr r2, r2, #10
    mla r0, r2, r1, r0
.endm

/* One first-order allpass: x in r1, state in \st, a in r0. */
.macro AP st
    lsl lr, r1, #1
    smmla lr, r0, lr, \st
    lsl \st, lr, #1
    smmls \st, r0, \st, r1
    mov r1, lr
.endm

/* Four stages with feedback. r1 = input, r2 = last output, r5 = states.
 * Returns r1 = output. */
.macro PH_CHAIN
    ldrh r3, [r4, #0x40]
    smulwb r3, r2, r3
    add r1, r1, r3, lsl #1
    ssat r1, #26, r1
    ldm r5, {r2, r3, r7, r12}
    AP r2
    AP r3
    AP r7
    AP r12
    stm r5, {r2, r3, r7, r12}
.endm

/* Rhodes-style phaser: 4 allpass stages per channel swept from 120 Hz to
 * 1600 Hz by a sine LFO, feedback = resonance, R LFO 90 degrees ahead
 * when STEREO. Wet = allpass output x level / 2^25 (max 0.94: deep notches
 * against the dry signal). r0, r1 = L, R in, out. */
phaser:
    push {lr}
    mov r10, r0
    mov r11, r1
    bl mod_common
    mov r9, r2
    mov r8, r3
    mov r0, r8
    PH_COEF
    add r5, r4, #0x14
    mov r1, r10
    ldr r2, [r4, #0x34]
    PH_CHAIN
    str r1, [r4, #0x34]
    smull r2, r1, r1, r9
    lsls r1, r1, #7
    orr r10, r1, r2, lsr #25
    ldrb r0, [r4, #3]
    cmp r0, #0
    ite ne
    addne r0, r8, #0x40000000
    moveq r0, r8
    PH_COEF
    add r5, r4, #0x24
    mov r1, r11
    ldr r2, [r4, #0x38]
    PH_CHAIN
    str r1, [r4, #0x38]
    smull r2, r1, r1, r9
    lsls r1, r1, #7
    orr r1, r1, r2, lsr #25
    mov r0, r10
    pop {pc}

/* Tremolo: gain 1 - depth x u, u = shaped sine 0..1 (shape 0 = sine,
 * 100 = almost square); depth = level (max 1). PAN: R in opposition.
 * Wet = -x * depth * u. r0, r1 = L, R in, out. */
tremolo:
    push {lr}
    mov r10, r0
    mov r11, r1
    bl mod_common
    lsr r2, r2, #6
    movw r12, #8738
    mul r2, r2, r12
    lsr r9, r2, #16
    ldrb r12, [r4, #7]
    movs r0, #41
    mul r12, r12, r0
    lsr r12, r12, #6
    add r12, r12, #16
    SINE r1, r3, r2
    mul r1, r1, r12
    asr r1, r1, #4
    ssat r1, #16, r1
    add r1, r1, #32768
    movw r2, #65535
    ldrb r0, [r4, #3]
    cmp r0, #0
    ite ne
    subne r2, r2, r1
    moveq r2, r1
    mul r1, r9, r1
    lsr r1, r1, #8
    mul r2, r9, r2
    lsr r2, r2, #8
    smull r3, r0, r10, r1
    lsls r0, r0, #8
    orr r0, r0, r3, lsr #24
    rsbs r0, r0, #0
    smull r3, r1, r11, r2
    lsls r1, r1, #8
    orr r1, r1, r3, lsr #24
    rsbs r1, r1, #0
    pop {pc}
    .align 2
    .ltorg

