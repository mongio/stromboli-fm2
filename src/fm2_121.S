/* volca FM2 experimental firmware 1.20 - ITCM blob at 0x00002000 (the
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
    b.w prob_entry        @ 0x2000  sequencer step hook
    b.w start_hook        @ 0x2004  transport start (0x002090C0)
    b.w panel_keys        @ 0x2008  keyboard veneer literal
    b.w panel_button      @ 0x200C  button veneer literal
    b.w panel_adc         @ 0x2010  ADC parameter prologue
    b.w panel_display     @ 0x2014  text request prologue
    b.w panel_encoder     @ 0x2018  encoder veneer literal
    b.w panel_led         @ 0x201C  LED prologue
    b.w note_on_hook      @ 0x2020  voice note-on 0x0020A78C (HOLD)
    b.w arp_tick          @ 0x2024  arpeggiator tick 0x0020C40C (new modes)
    b.w arp_start         @ 0x2028  arpeggiator note start 0x0020BDFC
    b.w arp_voice_on      @ 0x202C  arpeggiator voice trigger 0x002097E4 (MIDI out)
    b.w arp_step          @ 0x2030  arpeggiator step 0x0020C1F4 (MIDI out)
    b.w midi_flush        @ 0x2034  MIDI out service 0x00207F2C (main loop)
    b.w kbd_echo_on       @ 0x2038  keyboard / sequencer MIDI echo calls 0x0020AA8E, 0x0020A732
    b.w kbd_q_on          @ 0x203C  keyboard note-on note (BL at 0x0020AA8A)
    b.w kbd_q_off         @ 0x2040  keyboard note-off note (BL at 0x0020AACA)
    b.w din_on            @ 0x2044  MIDI DIN note-on 0x0020AB2C
    b.w din_off           @ 0x2048  MIDI DIN note-off 0x0020AB64
    b.w usb_on            @ 0x204C  USB MIDI note-on 0x0020ABC0
    b.w usb_off           @ 0x2050  USB MIDI note-off 0x0020ABF8
    b.w seq_note          @ 0x2054  sequencer note slot store (BL at 0x0020BA6E)
    b.w fx_audio          @ 0x2058  audio ISR effect call (ITCM literal 0x023C, was reverb 0x1461)
    b.w fx_toggle         @ 0x205C  FUNC+4 reverb toggle veneer literal 0x2001516C (was 0x0020C8B7)

/* ---------------------------------------------------------------- */
/* Sequencer hook: replaces LDRH r3,[r4,#6]; MOV.W r8,#0 at 0x0020B7CA */
prob_entry:
    push.w {r0, r1, r2, r4, r5, r6, r7, lr}
    bl track_loop
    ldr r0, [sp]
    mov r1, r4
    bl decide
    mov r3, r0
    pop.w {r0, r1, r2, r4, r5, r6, r7, lr}
    cmp r3, #0
    beq prob_rejected
    ldrh r3, [r4, #6]
    b prob_resume
prob_rejected:
    movs r3, #0
prob_resume:
    mov.w r8, #0
    ldr r12, =0x0020B7D1
    bx r12

/* Transport start: replaces PUSH {r3-r7,lr}; MOV r6,r2 at 0x002090C0.
 * r2 != 0 restarts the sequence from its beginning: reset loop state. */
start_hook:
    cmp r2, #0
    beq start_continue
    movw r12, #0x3F10
    movs r3, #0xFF
    strb r3, [r12]
    movs r3, #0
    strb r3, [r12, #1]
    strh r3, [r12, #2]
    /* 1.19: the native start reloads the first chain pattern: our chain
     * restarts from its first entry too */
    movw r12, #0x1D00
    strb r3, [r12, #5]
    strb r3, [r12, #6]
start_continue:
    push {r3, r4, r5, r6, r7, lr}
    mov r6, r2
    ldr r12, =0x002090C5
    bx r12

/* r0 = step being applied. A step index not greater than the previous one
 * is a new pass of the pattern. Clobbers r1-r3, r12. */
track_loop:
    movw r12, #0x3F10
    ldrb r1, [r12]
    strb r0, [r12]
    cmp r0, r1
    bhi track_done
    cmp r1, #0xFF
    beq track_done
    ldrh r2, [r12, #2]
    adds r2, #1
    movw r3, #840
    cmp r2, r3
    blo track_store
    movs r2, #0
track_store:
    strh r2, [r12, #2]
    movs r2, #1
    strb r2, [r12, #1]
track_done:
    bx lr

/* r0 = step 0..15, r1 = pattern. Returns 1 to keep the native note mask,
 * 0 to let the ORIGINAL routine process the step as muted. */
decide:
    push {r3, r4, r5, r6, r7, lr}
    cmp r0, #16
    bhs decide_allow
    mov r5, r0
    mov r6, r1
    /* Native muted steps and rests: unchanged, no randomness consumed. */
    ldrh r2, [r6, #6]
    lsrs r2, r5
    tst r2, #1
    beq decide_allow
    movs r2, #112
    mul r2, r2, r5
    add r2, r6
    adds r2, #98
    ldrb r3, [r2]
    ldrb r4, [r2, #1]
    orrs r3, r4
    ldrb r4, [r2, #2]
    orrs r3, r4
    ldrb r4, [r2, #3]
    orrs r3, r4
    ldrb r4, [r2, #4]
    orrs r3, r4
    ldrb r4, [r2, #5]
    orrs r3, r4
    beq decide_allow
    mov r0, r6
    mov r1, r5
    bl load_params
    mov r4, r0
    mov r7, r2
    cmp r1, #0
    beq decide_scale
    mov r0, r1
    bl cond_pass
    cmp r0, #0
    beq decide_deny
decide_scale:
    mul r4, r4, r7
    adds r4, #50
    movs r1, #100
    udiv r4, r4, r1
    cmp r4, #100
    bhs decide_allow
    cmp r4, #0
    beq decide_deny
    movs r0, #100
    ldr r12, =0x002094A5
    blx r12
    cmp r0, r4
    blo decide_allow
decide_deny:
    movs r0, #0
    pop {r3, r4, r5, r6, r7, pc}
decide_allow:
    movs r0, #1
    pop {r3, r4, r5, r6, r7, pc}

/* r0 = condition 1..11. Returns 1 when the step may play on this pass.
 * 1:2 2:2 1:3 2:3 3:3 1:4 2:4 3:4 4:4 FIRST NOT-FIRST; others pass. */
cond_pass:
    movw r12, #0x3F10
    cmp r0, #10
    beq cond_first
    cmp r0, #11
    beq cond_not_first
    cmp r0, #9
    bhi cond_yes
    cmp r0, #2
    bhi cond_b3
    movs r3, #2
    mov r2, r0
    b cond_mod
cond_b3:
    cmp r0, #5
    bhi cond_b4
    movs r3, #3
    subs r2, r0, #2
    b cond_mod
cond_b4:
    movs r3, #4
    subs r2, r0, #5
cond_mod:
    ldrh r1, [r12, #2]
    udiv r0, r1, r3
    mls r0, r0, r3, r1
    subs r2, #1
    cmp r0, r2
    beq cond_yes
    b cond_no
cond_first:
    ldrb r1, [r12, #1]
    cmp r1, #0
    beq cond_yes
    b cond_no
cond_not_first:
    ldrb r1, [r12, #1]
    cmp r1, #0
    bne cond_yes
cond_no:
    movs r0, #0
    bx lr
cond_yes:
    movs r0, #1
    bx lr
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* Profile helpers. X = pattern + 0x760. */

/* r0 = X. Returns FNV-1a-32 of X[0..25] folded to 16 bits. */
prb2_digest:
    ldr r1, =0x811C9DC5
    ldr r2, =0x01000193
    add.w r12, r0, #26
digest_loop:
    ldrb r3, [r0], #1
    eors r1, r3
    mul r1, r1, r2
    cmp r0, r12
    bne digest_loop
    eor r1, r1, r1, lsr #16
    uxth r0, r1
    bx lr

/* r0 = X. Returns 1 for a valid PRB2 block. Read-only. */
prb2_valid:
    push {r4, lr}
    mov r4, r0
    ldrb r1, [r4]
    cmp r1, #0xA2
    beq prb2_tag_ok
    cmp r1, #0xA3
    bne prb2_invalid
prb2_tag_ok:
    movs r2, #0
prb2_prob_loop:
    adds r3, r4, r2
    ldrb r1, [r3, #1]
    and r1, r1, #0x7F
    cmp r1, #100
    bhi prb2_invalid
    adds r2, #1
    cmp r2, #16
    bne prb2_prob_loop
    movs r2, #0
prb2_cond_loop:
    adds r3, r4, r2
    ldrb r1, [r3, #17]
    and r3, r1, #15
    cmp r3, #11
    bhi prb2_invalid
    lsrs r1, r1, #4
    cmp r1, #11
    bhi prb2_invalid
    adds r2, #1
    cmp r2, #8
    bne prb2_cond_loop
    ldrb r1, [r4, #25]
    cmp r1, #100
    bhi prb2_invalid
    mov r0, r4
    bl prb2_digest
    ldrb r1, [r4, #26]
    ldrb r2, [r4, #27]
    orr r1, r1, r2, lsl #8
    cmp r0, r1
    bne prb2_invalid
    movs r0, #1
    pop {r4, pc}
prb2_invalid:
    movs r0, #0
    pop {r4, pc}

/* r0 = X. Returns 1 for a valid 1.13 PRB1 block. Read-only. */
prb1_valid:
    push {r4, lr}
    mov r4, r0
    ldr r1, [r4]
    ldr r2, =0x31425250
    cmp r1, r2
    bne prb1_invalid
    ldr r1, [r4, #20]
    ldr r2, =0xCEBDADAF
    cmp r1, r2
    bne prb1_invalid
    ldr r0, =0x811C9DC5
    ldr r12, =0x01000193
    movs r2, #0
prb1_loop:
    adds r3, r4, r2
    ldrb r1, [r3, #4]
    cmp r1, #100
    bhi prb1_invalid
    eors r0, r1
    mul r0, r0, r12
    adds r2, #1
    cmp r2, #16
    bne prb1_loop
    ldr r1, [r4, #24]
    cmp r0, r1
    bne prb1_invalid
    movs r0, #1
    pop {r4, pc}
prb1_invalid:
    movs r0, #0
    pop {r4, pc}

/* r0 = pattern, r1 = step. Returns r0 = probability, r1 = condition,
 * r2 = pattern scale. Defaults 100/0/100 without a valid block. Read-only. */
load_params:
    push {r4, r5, r6, lr}
    addw r4, r0, #0x760
    mov r5, r1
    mov r0, r4
    bl prb2_valid
    cmp r0, #0
    beq load_try_prb1
    adds r0, r4, r5
    ldrb r0, [r0, #1]
    and r0, r0, #0x7F
    lsrs r1, r5, #1
    add r1, r4
    ldrb r1, [r1, #17]
    tst r5, #1
    beq load_low
    lsrs r1, r1, #4
load_low:
    and r1, r1, #15
    ldrb r2, [r4, #25]
    pop {r4, r5, r6, pc}
load_try_prb1:
    mov r0, r4
    bl prb1_valid
    cmp r0, #0
    beq load_default
    adds r0, r4, r5
    ldrb r0, [r0, #4]
    movs r1, #0
    movs r2, #100
    pop {r4, r5, r6, pc}
load_default:
    movs r0, #100
    movs r1, #0
    movs r2, #100
    pop {r4, r5, r6, pc}

/* Current pattern: guarantee a valid PRB2 block before an edit.
 * PRB1 probabilities are kept; otherwise 100%, no condition, scale 100. */
ensure_prb2:
    push {r4, lr}
    ldr r4, =0x2001E88C
    mov r0, r4
    bl prb2_valid
    cmp r0, #0
    beq ensure_build
    /* A valid 1.14/1.15 block (tag 0xA2) becomes PRB3 (0xA3, bit 7 fields 0). */
    ldrb r0, [r4]
    cmp r0, #0xA3
    beq ensure_done
    movs r0, #0xA3
    strb r0, [r4]
    bl seal
    b ensure_done
ensure_build:
    mov r0, r4
    bl prb1_valid
    cmp r0, #0
    beq ensure_init
    movs r1, #0
ensure_copy:
    adds r2, r4, r1
    ldrb r3, [r2, #4]
    strb r3, [r2, #1]
    adds r1, #1
    cmp r1, #16
    bne ensure_copy
    b ensure_tail
ensure_init:
    movs r1, #0
    movs r3, #100
ensure_fill:
    adds r2, r4, r1
    strb r3, [r2, #1]
    adds r1, #1
    cmp r1, #16
    bne ensure_fill
ensure_tail:
    movs r1, #0
    movs r3, #0
ensure_clear:
    adds r2, r4, r1
    strb r3, [r2, #17]
    adds r1, #1
    cmp r1, #8
    bne ensure_clear
    movs r3, #100
    strb r3, [r4, #25]
    movs r3, #0xA3
    strb r3, [r4]
    bl seal
ensure_done:
    pop {r4, pc}

/* Recompute the check byte of the current pattern's PRB2 block. */
seal:
    push {r4, lr}
    ldr r4, =0x2001E88C
    mov r0, r4
    bl prb2_digest
    strb r0, [r4, #26]
    lsrs r0, r0, #8
    strb r0, [r4, #27]
    pop {r4, pc}

/* r0 = step, r1 = condition. Writes one nibble (no seal). */
put_cond:
    ldr r2, =0x2001E89D
    lsrs r3, r0, #1
    add r2, r3
    ldrb r3, [r2]
    tst r0, #1
    bne put_cond_high
    bic r3, r3, #15
    orr r3, r3, r1
    strb r3, [r2]
    bx lr
put_cond_high:
    and r3, r3, #15
    orr r3, r3, r1, lsl #4
    strb r3, [r2]
    bx lr

/* r0 = step. Returns its condition nibble from a valid PRB2 block. */
get_cond:
    ldr r2, =0x2001E89D
    lsrs r3, r0, #1
    add r2, r3
    ldrb r3, [r2]
    tst r0, #1
    beq get_cond_low
    lsrs r3, r3, #4
get_cond_low:
    and r0, r3, #15
    bx lr

/* r0 = step, r1 = value 0..100 */
set_prob:
    push {r4, r5, r6, lr}
    mov r4, r0
    mov r5, r1
    bl ensure_prb2
    ldr r2, =0x2001E88D
    ldrb r3, [r2, r4]
    and r3, r3, #0x80
    orr r5, r5, r3
    strb r5, [r2, r4]
    bl seal
    pop {r4, r5, r6, pc}
    .align 2
    .ltorg

/* r0 = step, r1 = condition 0..11 */
set_cond:
    push {r4, r5, r6, lr}
    mov r4, r0
    mov r5, r1
    bl ensure_prb2
    mov r0, r4
    mov r1, r5
    bl put_cond
    bl seal
    pop {r4, r5, r6, pc}

/* r0 = pattern scale 0..100 */
set_scale:
    push {r4, lr}
    mov r4, r0
    bl ensure_prb2
    ldr r2, =0x2001E8A5
    strb r4, [r2]
    bl seal
    pop {r4, pc}

/* Fill the 16 probabilities of the current block with r0 (no seal). */
fill_probs:
    push {r4, lr}
    ldr r2, =0x2001E88D
    movs r1, #0
fill_loop:
    ldrb r3, [r2, r1]
    and r3, r3, #0x80
    orr r3, r3, r0
    strb r3, [r2, r1]
    adds r1, #1
    cmp r1, #16
    bne fill_loop
    pop {r4, pc}

/* Clear all condition nibbles (no seal). */
clear_conds:
    ldr r2, =0x2001E89D
    movs r1, #0
    movs r3, #0
clear_loop:
    strb r3, [r2, r1]
    adds r1, #1
    cmp r1, #8
    bne clear_loop
    bx lr

/* Quick command for step key r0 while the page is in mode G:
 * 1 all 100%  2 all 75%  3 all 50%  4 all 25%  5 random 25/50/75/100%
 * 6 copy selected step to all  7 all conditions off  8 reset all
 * 16 show the beta version */
run_command:
    push {r4, r5, r6, lr}
    cmp r0, #15
    beq command_version
    cmp r0, #7
    bhi command_done
    mov r5, r0
    bl ensure_prb2
    cmp r5, #3
    bhi command_more
    movs r1, #25
    mul r1, r1, r5
    rsb r0, r1, #100
    bl fill_probs
    b command_finish
command_more:
    cmp r5, #4
    bne command_copy
    movs r4, #0
command_random:
    movs r0, #4
    ldr r12, =0x002094A5
    blx r12
    adds r0, #1
    movs r1, #25
    mul r0, r0, r1
    ldr r2, =0x2001E88D
    ldrb r3, [r2, r4]
    and r3, r3, #0x80
    orr r0, r0, r3
    strb r0, [r2, r4]
    adds r4, #1
    cmp r4, #16
    bne command_random
    b command_finish
command_copy:
    cmp r5, #5
    bne command_conds
    movw r6, #0x3F00
    ldrb r0, [r6, #1]
    ldr r2, =0x2001E88D
    ldrb r0, [r2, r0]
    and r0, r0, #0x7F
    bl fill_probs
    ldrb r0, [r6, #1]
    bl get_cond
    mov r6, r0
    movs r4, #0
command_copy_loop:
    mov r0, r4
    mov r1, r6
    bl put_cond
    adds r4, #1
    cmp r4, #16
    bne command_copy_loop
    b command_finish
command_conds:
    cmp r5, #6
    bne command_reset
    bl clear_conds
    b command_finish
command_reset:
    movs r0, #100
    bl fill_probs
    bl clear_conds
    ldr r2, =0x2001E8A5
    movs r0, #100
    strb r0, [r2]
command_finish:
    bl seal
    movw r6, #0x3F00
    adds r5, #1
    strb r5, [r6, #3]
command_done:
    pop {r4, r5, r6, pc}
/* Key 16: show the beta version (data unchanged). The application version
 * byte is 11 on purpose so the official Korg 1.12 updater is accepted. */
command_version:
    movw r6, #0x3F00
    movs r5, #9
    strb r5, [r6, #3]
    pop {r4, r5, r6, pc}
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* Panel. Native addresses as in the 1.13 beta. */

panel_keys:
    movw r12, #0x3F00
    ldrb r12, [r12]
    cmp r12, #1
    beq keys_active
    ldr r12, =0x2001180D
    bx r12
keys_active:
    push {r4, r5, r6, lr}
    movw r4, #0x3F00
    cmp r0, #0x80000000
    beq keys_done
    bic r0, r0, #0x80000000
    str r0, [r4, #8]
    movw r12, #0x133F
    movt r12, #0x2001
    blx r12
    ldr r2, [r4, #4]
    str r0, [r4, #4]
    bic r5, r0, r2
    cmp r5, #0
    beq keys_done
    movs r6, #0
keys_find:
    lsrs r5, #1
    bcs keys_select
    adds r6, #1
    b keys_find
keys_select:
    ldrb r0, [r4, #2]
    cmp r0, #2
    bne keys_not_gl
    mov r0, r6
    bl run_command
    bl render
    b keys_done
keys_not_gl:
    cmp r0, #2
    blo keys_step
    /* SC: key 16 toggles the live sequence option. dt: SYNC/LIBERO.
     * Fb: MONO/PING PONG. Other modes: no key. */
    cmp r0, #8
    beq keys_dt
    cmp r0, #9
    beq keys_fb
    cmp r0, #10
    beq keys_cr
    cmp r0, #5
    bne keys_done
    cmp r6, #15
    bne keys_done
    movw r12, #0x3F30
    ldrb r0, [r12, #3]
    eor r0, r0, #1
    strb r0, [r12, #3]
    rsb r0, r0, #17
    strb r0, [r4, #3]
    bl render
    b keys_done
keys_dt:
    cmp r6, #15
    bne keys_done
    movw r12, #0x3F80
    ldrb r0, [r12, #2]
    eor r0, r0, #1
    strb r0, [r12, #2]
    rsb r0, r0, #19
    strb r0, [r4, #3]
    bl render
    b keys_done
keys_fb:
    cmp r6, #15
    bne keys_done
    movw r12, #0x3F80
    ldrb r0, [r12, #3]
    eor r0, r0, #1
    strb r0, [r12, #3]
    adds r0, #20
    strb r0, [r4, #3]
    bl render
    b keys_done
/* 1.20 CR: key 16 toggles REC AUTO (Korg: REC ends with a motion loop)
 * and REC FISSO (REC stays on). Messages 28/29. */
keys_cr:
    cmp r6, #15
    bne keys_done
    movw r12, #0x1D00
    ldrb r0, [r12, #0xF]
    eor r0, r0, #1
    strb r0, [r12, #0xF]
    adds r0, #28
    strb r0, [r4, #3]
    bl render
    b keys_done
keys_step:
    strb r6, [r4, #1]
    bl render
    bl leds
keys_done:
    pop {r4, r5, r6, pc}

panel_button:
    movw r12, #0x3F00
    ldrb r12, [r12]
    cmp r12, #1
    beq button_active
    /* FUNC + OCTAVE +/- : HOLD on/off and TASTO RIPARTE/SPEGNE */
    cmp r0, #6
    beq hold_buttons
    cmp r0, #7
    beq hold_buttons
    cmp r0, #5
    beq scale_button
    /* 1.19: MEMORY pressed: the next keys start a new free chain */
    cmp r0, #1
    bne button_not_memory
    cbz r1, button_not_memory
    push {r0}
    movw r12, #0x1D00
    movs r0, #1
    strb r0, [r12, #7]
    pop {r0}
button_not_memory:
    cmp r0, #4
    bne button_native
    cmp r1, #0
    beq button_native
    ldr r12, =0x200029DA
    ldrb r12, [r12]
    cmp r12, #0x12
    beq enter
button_native:
    ldr r12, =0x20011321
    bx r12
button_active:
    cmp r1, #0
    beq button_done
    cmp r0, #0
    beq leave
    cmp r0, #4
    beq leave
    /* PLAY keeps the native start/stop action. */
    cmp r0, #3
    beq button_native
    /* OCTAVE/OPERATOR +/- select the page mode P -> C -> G. */
    cmp r0, #6
    beq mode_next
    cmp r0, #7
    beq mode_prev
button_done:
    bx lr
mode_next:
    push {r4, lr}
    movw r4, #0x3F00
    ldrb r0, [r4, #2]
    adds r0, #1
    cmp r0, #11
    blo mode_store
    movs r0, #0
    b mode_store
mode_prev:
    push {r4, lr}
    movw r4, #0x3F00
    ldrb r0, [r4, #2]
    cmp r0, #0
    bne mode_dec
    movs r0, #11
mode_dec:
    subs r0, #1
mode_store:
    strb r0, [r4, #2]
    movs r0, #0
    strb r0, [r4, #3]
    bl render
    pop {r4, pc}
enter:
    push {r4, r5, r6, lr}
    movs r0, #0
    movw r12, #0x1369
    movt r12, #0x2001
    blx r12
    movw r12, #0x15B5
    movt r12, #0x2001
    blx r12
    ldr r4, =0x200029F4
    ldr r0, [r4]
    bic r0, r0, #1
    str r0, [r4]
    movw r4, #0x3F00
    movs r0, #0
    str r0, [r4, #4]
    str r0, [r4, #8]
    strb r0, [r4, #1]
    strb r0, [r4, #2]
    strb r0, [r4, #3]
    movs r0, #1
    strb r0, [r4]
    /* Snapshot the actual slider so entering the page does not edit data. */
    movs r0, #3
    ldr r12, =0x002049A5
    blx r12
    lsrs r0, #5
    ldr r1, =0x200029B2
    strh r0, [r1]
    movs r2, #1
    movs r1, #0x49
    ldr r0, =0x200029DA
    ldr r12, =0x00205C2D
    blx r12
    bl render
    bl leds
    pop {r4, r5, r6, pc}
leave:
    push {r4, r5, r6, lr}
    movw r4, #0x3F00
    movs r0, #0
    strb r0, [r4]
    ldr r1, =0x20002890
    ldr r0, [r1, #24]
    lsrs r0, #16
    lsls r0, #16
    str r0, [r1, #24]
    /* Suppress keys still physically held until their release. */
    ldr r2, [r4, #8]
    ldr r1, =0x200029CC
    str r2, [r1, #4]
    movs r1, #0
    movs r2, #1
    ldr r0, =0x200029DA
    ldr r12, =0x00205C2D
    blx r12
    pop {r4, r5, r6, pc}

panel_encoder:
    movw r12, #0x3F00
    ldrb r12, [r12]
    cmp r12, #1
    beq encoder_drain
    ldr r12, =0x20011521
    bx r12
encoder_drain:
    push {r3, lr}
    movw r12, #0x5159
    movt r12, #0x2001
    blx r12
    pop {r3, pc}
    .align 2
    .ltorg

panel_adc:
    cmp r0, #7
    beq arp_knob
    movw r12, #0x3F00
    ldrb r12, [r12]
    cmp r12, #1
    bne adc_native
    /* Native MIDI CC dispatch uses r2=1; only panel ADC (r2=0) edits. */
    cmp r2, #0
    bne adc_native
    cmp r0, #3
    beq adc_value
adc_native:
    push {r4, r5, r6, lr}
    sub sp, #0x18
    mov r4, r0
    ldr r12, =0x002059D7
    bx r12
adc_value:
    push {r4, r5, r6, lr}
    mov r0, r1
    cmp r0, #0
    bge adc_nonnegative
    movs r0, #0
adc_nonnegative:
    cmp r0, #127
    bls adc_inrange
    movs r0, #127
adc_inrange:
    movw r6, #0x3F00
    movs r1, #0
    strb r1, [r6, #3]
    ldrb r5, [r6, #2]
    cmp r5, #1
    beq adc_condition
    cmp r5, #3
    bhs adc_extra
    movs r1, #100
    mul r0, r0, r1
    adds r0, #63
    movs r1, #127
    udiv r1, r0, r1
    cmp r5, #2
    beq adc_scale
    ldrb r0, [r6, #1]
    bl set_prob
    b adc_render
adc_scale:
    mov r0, r1
    bl set_scale
    b adc_render
adc_condition:
    movs r1, #11
    mul r0, r0, r1
    adds r0, #63
    movs r1, #127
    udiv r1, r0, r1
    ldrb r0, [r6, #1]
    bl set_cond
adc_render:
    bl render
    pop {r4, r5, r6, pc}
/* HU / OC: 0..15 per pattern. SC: scale 0..14. tn: tonic 0..11. */
adc_extra:
    cmp r5, #7
    bhs adc_fx
    cmp r5, #5
    beq adc_scale_type
    cmp r5, #6
    beq adc_tonic
    movs r1, #15
    bl adc_map
    cmp r5, #3
    ite eq
    moveq r1, #4
    movne r1, #8
    bl set_bits
    b adc_render
adc_scale_type:
    movs r1, #14
    bl adc_map
    movw r12, #0x3F31
    strb r0, [r12]
    b adc_render
adc_tonic:
    movs r1, #11
    bl adc_map
    movw r12, #0x3F32
    strb r0, [r12]
    b adc_render

/* FX: 0 REVRB, 1 DELAY, 2 LOFI. dt: division 0..8 (SYNC) or raw slider
 * 0..127 (LIBERO). Fb: feedback 0..100. */
adc_fx:
    cmp r5, #10
    bhs adc_chain
    movw r6, #0x3F80
    cmp r5, #8
    beq adc_dt
    bhi adc_fb
    movs r1, #2
    bl adc_map
    strb r0, [r6]
    /* 1.20: the effect type is saved in the pattern (PRB3, steps 13-14) */
    movs r1, #12
    bl set_bits
    b adc_render
adc_dt:
    ldrb r1, [r6, #2]
    cmp r1, #0
    beq adc_dt_free
    movs r1, #8
    bl adc_map
    strb r0, [r6, #4]
    b adc_render
adc_dt_free:
    strb r0, [r6, #5]
    b adc_render
adc_fb:
    movs r1, #100
    bl adc_map
    strb r0, [r6, #6]
    b adc_render

/* 1.20 CR: 0 OFF (Korg chain) 1 ON (free chain + recording on the chain).
 * State 0x1D00: +0 free chain selection and +2 recording follow CR.
 * CR ON -> OFF ends our free chain (the current pattern keeps playing). */
adc_chain:
    movw r6, #0x1D00
    movs r1, #1
    bl adc_map
    ldrb r1, [r6, #2]
    cmp r0, r1
    beq adc_chain_done
    strb r0, [r6]
    strb r0, [r6, #2]
    cbnz r0, adc_chain_done
    ldrb r1, [r6, #4]
    cbz r1, adc_chain_done
    strb r0, [r6, #4]
    ldr r1, =0x20003E34
    strb r0, [r1, #0x15]
adc_chain_done:
    b adc_render

/* r0 = 0..127, r1 = top value: returns (r0 * r1 + 63) / 127. */
adc_map:
    mul r0, r0, r1
    adds r0, #63
    movs r1, #127
    udiv r0, r0, r1
    bx lr

/* r0 = message number (1-based): returns the address of its 9 characters. */
msg_ptr:
    subs r0, #1
    movs r1, #12
    cmp r0, #13
    bhs msg_ptr_new
    mul r0, r0, r1
    movw r1, #0x3E40
    add r0, r1
    bx lr
msg_ptr_new:
    subs r0, #13
    mul r0, r0, r1
    movw r1, #0x1E00
    add r0, r1
    bx lr

panel_display:
    movw r12, #0x3F00
    ldrb r12, [r12]
    cmp r12, #1
    beq render
    /* REVRB level readout while the delay is selected: "DELAY "/"LOFI  ". */
    ldr r12, =0x20002958
    cmp r1, r12
    bne display_arp
    push {r0, r1, r2, r3, r4, lr}
    bl fx_label
    pop {r0, r1, r2, r3, r4, lr}
display_arp:
    /* "tYP Rise1" while a new arpeggio mode is active: show its name. */
    ldr r12, =0x2000AC82
    cmp r1, r12
    bne display_native
    movw r12, #0x3F16
    ldrb r12, [r12]
    cmp r12, #0
    beq display_native
    sub r12, r12, #1
    add r12, r12, r12, lsl #2
    lsl r12, r12, #1
    add r1, r12, #0x3D80
display_native:
    push {r0, r1, r2, r3, r4, r5, r6, lr}
    mov r5, r3
    movs r3, #0
    ldr r12, =0x00205923
    bx r12

/* r0 = value 0..100, r1 = destination of three ASCII digits. */
put3:
    movs r2, #100
    udiv r3, r0, r2
    mls r0, r3, r2, r0
    adds r3, #48
    strb r3, [r1]
    movs r2, #10
    udiv r3, r0, r2
    mls r0, r3, r2, r0
    adds r3, #48
    adds r0, #48
    strb r3, [r1, #1]
    strb r0, [r1, #2]
    bx lr

/* r0 = source, r1 = destination, r2 = count */
copy_text:
    ldrb r3, [r0], #1
    strb r3, [r1], #1
    subs r2, #1
    bne copy_text
    bx lr

/* Draw the modal readout (9 characters) with the native text routine.
 *   P: "05 P050  "   C: "05 C 1-2 "   G: "GL P100  " or a command message */
render:
    push {r4, r5, r6, r7, lr}
    sub sp, #20
    add r4, sp, #4
    movs r0, #0
    str r0, [sp]
    strb r0, [r4, #9]
    movs r0, #32
    movs r1, #0
render_blank:
    strb r0, [r4, r1]
    adds r1, #1
    cmp r1, #9
    bne render_blank
    movw r7, #0x3F00
    ldrb r6, [r7, #1]
    ldr r0, =0x2001E12C
    mov r1, r6
    bl load_params
    mov r5, r0
    str r1, [sp, #16]
    ldrb r3, [r7, #2]
    cmp r3, #2
    beq render_scale
    bhi render_extra
    /* Step number "05" */
    adds r0, r6, #1
    movs r1, #10
    udiv r2, r0, r1
    mls r0, r2, r1, r0
    adds r2, #48
    adds r0, #48
    strb r2, [r4]
    strb r0, [r4, #1]
    cmp r3, #1
    beq render_condition
    movs r0, #80
    strb r0, [r4, #3]
    mov r0, r5
    adds r1, r4, #4
    bl put3
    b render_out
render_condition:
    movs r0, #67
    strb r0, [r4, #3]
    ldr r0, [sp, #16]
    ldr r1, =0x00003E00
    add r0, r1, r0, lsl #2
    adds r1, r4, #5
    movs r2, #4
    bl copy_text
    b render_out
render_scale:
    ldrb r3, [r7, #3]
    cmp r3, #0
    beq render_scale_value
render_message_r3:
    mov r0, r3
    bl msg_ptr
    mov r1, r4
    movs r2, #9
    bl copy_text
    b render_out
render_scale_value:
    movs r0, #71
    strb r0, [r4]
    movs r0, #76
    strb r0, [r4, #1]
    movs r0, #80
    strb r0, [r4, #3]
    mov r0, r2
    adds r1, r4, #4
    bl put3
    b render_out
/* Modes HU, OC, SC, tn (a pending message is shown first). */
render_extra:
    mov r5, r3
    ldrb r3, [r7, #3]
    cmp r3, #0
    bne render_message_r3
    cmp r5, #7
    bhs render_fx
    cmp r5, #5
    beq render_sc
    cmp r5, #6
    beq render_tn
    ldr r0, =0x2001E88C
    bl seq_params
    cmp r5, #3
    itte eq
    moveq r2, #72
    moveq r3, #85
    movne r2, #79
    it ne
    movne r3, #67
    it ne
    movne r0, r1
    strb r2, [r4]
    strb r3, [r4, #1]
    movs r1, #10
    udiv r2, r0, r1
    mls r0, r2, r1, r0
    adds r2, #48
    adds r0, #48
    strb r2, [r4, #3]
    strb r0, [r4, #4]
    b render_out
render_sc:
    movs r0, #83
    strb r0, [r4]
    movs r0, #67
    strb r0, [r4, #1]
    movw r6, #0x3F30
    ldrb r0, [r6, #1]
    cmp r0, #15
    it hs
    movhs r0, #0
    movw r1, #0x1F00
    add r0, r1, r0, lsl #2
    adds r1, r4, #3
    movs r2, #4
    bl copy_text
    ldrb r0, [r6]
    cmp r0, #0
    ite ne
    movne r0, #79
    moveq r0, #45
    ite ne
    movne r1, #78
    moveq r1, #45
    strb r0, [r4, #7]
    strb r1, [r4, #8]
    b render_out
render_tn:
    movs r0, #116
    strb r0, [r4]
    movs r0, #110
    strb r0, [r4, #1]
    movw r6, #0x3F30
    ldrb r0, [r6, #2]
    cmp r0, #12
    it hs
    movhs r0, #0
    movw r1, #0x1F40
    add r0, r1, r0, lsl #2
    adds r1, r4, #3
    movs r2, #4
    bl copy_text
    b render_out
/* FX "FX DELAY ", dt "dt 1-8.  " / "dt  250ms", Fb "Fb 050 PP" */
render_fx:
    cmp r5, #10
    bhs render_chain
    movw r6, #0x3F80
    cmp r5, #8
    beq render_dt
    bhi render_fb
    movs r0, #70
    strb r0, [r4]
    movs r0, #88
    strb r0, [r4, #1]
    ldrb r0, [r6]
    cmp r0, #3
    it hs
    movhs r0, #0
    add r0, r0, r0, lsl #2
    movw r1, #0x1940
    add r0, r1
    adds r1, r4, #3
    movs r2, #5
    bl copy_text
    b render_out
render_dt:
    movs r0, #100
    strb r0, [r4]
    movs r0, #116
    strb r0, [r4, #1]
    ldrb r0, [r6, #2]
    cmp r0, #0
    beq render_dt_free
    ldrb r0, [r6, #4]
    cmp r0, #9
    it hs
    movhs r0, #0
    add r0, r0, r0, lsl #2
    movw r1, #0x194F
    add r0, r1
    adds r1, r4, #3
    movs r2, #5
    bl copy_text
    b render_out
render_dt_free:
    bl fx_ui_key
    bl fx_samples
    movs r1, #25
    udiv r0, r0, r1
    movs r1, #10
    udiv r2, r0, r1
    mls r3, r2, r1, r0
    adds r3, #48
    strb r3, [r4, #6]
    udiv r0, r2, r1
    mls r3, r0, r1, r2
    adds r3, #48
    strb r3, [r4, #5]
    udiv r2, r0, r1
    mls r3, r2, r1, r0
    cmp r2, #0
    it eq
    cmpeq r3, #0
    beq render_dt_ms
    adds r3, #48
    strb r3, [r4, #4]
    cmp r2, #0
    beq render_dt_ms
    adds r2, #48
    strb r2, [r4, #3]
render_dt_ms:
    movs r0, #109
    strb r0, [r4, #7]
    movs r0, #115
    strb r0, [r4, #8]
    b render_out
render_fb:
    movs r0, #70
    strb r0, [r4]
    movs r0, #98
    strb r0, [r4, #1]
    ldrb r0, [r6, #6]
    adds r1, r4, #3
    bl put3
    ldrb r0, [r6, #3]
    cmp r0, #0
    ite ne
    movne r0, #80
    moveq r0, #77
    ite ne
    movne r1, #80
    moveq r1, #79
    strb r0, [r4, #7]
    strb r1, [r4, #8]
    b render_out
/* 1.20: "CR OFF   " "CR ON    " (names at 0x1980, 6 characters each) */
render_chain:
    movw r6, #0x1D00
    movs r0, #67
    strb r0, [r4]
    movs r0, #82
    strb r0, [r4, #1]
    ldrb r0, [r6, #2]
    cmp r0, #2
    it hs
    movhs r0, #0
render_chain_name:
    add r0, r0, r0, lsl #1
    lsls r0, r0, #1
    movw r1, #0x1980
    add r0, r1
    adds r1, r4, #3
    movs r2, #6
    bl copy_text
    ldrb r0, [r6, #0xF]
    cbz r0, render_out
    movs r0, #70
    strb r0, [r4, #8]
render_out:
    ldr r0, =0x20002968
    mov r1, r4
    movs r2, #0
    movs r3, #0
    bl display_native
    add sp, #20
    pop {r4, r5, r6, r7, pc}

leds:
    push {r4, lr}
    ldr r1, =0x20002890
    ldr r0, [r1]
    lsrs r0, #16
    lsls r0, #16
    str r0, [r1]
    ldr r0, [r1, #8]
    lsrs r0, #16
    lsls r0, #16
    str r0, [r1, #8]
    ldr r0, [r1, #16]
    lsrs r0, #16
    lsls r0, #16
    str r0, [r1, #16]
    movs r4, #0
led_loop:
    movs r0, #0
    mov r1, r4
    movs r2, #0
    ldr r12, =0x002058D7
    blx r12
    adds r4, #1
    cmp r4, #16
    bne led_loop
    pop {r4, pc}

panel_led:
    movw r12, #0x3F00
    ldrb r3, [r12]
    cmp r3, #1
    bne led_native
    cmp r1, #15
    bhi led_native
    ldrb r3, [r12, #1]
    movs r0, #3
    movs r2, #0
    cmp r1, r3
    bne led_native
    movs r0, #3
    movs r2, #1
led_native:
    cmp r1, #0x27
    push {r4}
    ldr r12, =0x00205491
    bx r12
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* HOLD (1.15). Virtual damper pedal: bit 0x04 in the native voice
 * manager damper bytes (0x20003C6C + 0xE2 current, + 0xE3 target), next to
 * the MIDI CC64 bits 0x01/0x02. Korg's own code keeps released keyboard and
 * MIDI notes sounding and releases them when all damper bits are clear.
 * State: 0x3F14 HOLD on, 0x3F15 TASTO (0 RIPARTE, 1 SPEGNE). Not saved. */

hold_buttons:
    cmp r1, #0
    beq button_native
    ldr r12, =0x200029DA
    ldrb r12, [r12]
    cmp r12, #0x12
    bne button_native
    push {r4, lr}
    movw r4, #0x3F00
    cmp r0, #7
    beq tasto_toggle
    ldrb r0, [r4, #0x14]
    eor r0, r0, #1
    strb r0, [r4, #0x14]
    ldr r2, =0x20003D4E
    ldrb r3, [r2]
    ldrb r1, [r2, #1]
    cmp r0, #0
    beq hold_release
    orr r3, r3, #4
    orr r1, r1, #4
    strb r3, [r2]
    strb r1, [r2, #1]
    movw r0, #0x3EAC
    b hold_show
hold_release:
    /* Clear only the target bit: the native voice tick releases the held
     * notes when no damper source (HOLD or a CC64 pedal) remains. */
    bic r1, r1, #4
    strb r1, [r2, #1]
    movw r0, #0x3EB8
    b hold_show
tasto_toggle:
    ldrb r0, [r4, #0x15]
    eor r0, r0, #1
    strb r0, [r4, #0x15]
    cmp r0, #0
    ite eq
    movweq r0, #0x3EC4
    movwne r0, #0x3ED0
hold_show:
    bl show_text
    pop {r4, pc}

/* r0 = 9-character text: draw it with the native text routine. */
show_text:
    push {r4, r5, r6, r7, lr}
    sub sp, #20
    add r4, sp, #4
    movs r1, #0
    str r1, [sp]
    strb r1, [r4, #9]
    mov r1, r4
    movs r2, #9
    bl copy_text
    ldr r0, =0x20002968
    mov r1, r4
    movs r2, #0
    movs r3, #0
    bl display_native
    add sp, #20
    pop {r4, r5, r6, r7, pc}

/* Entry of the native voice note-on 0x0020A78C (r0 source, r1 note,
 * r2 velocity, r3 -1). Only keyboard (0x40), MIDI DIN (0x20) and USB (0x30)
 * notes are affected, and only while HOLD is on. */
note_on_hook:
    movw r12, #0x3F14
    ldrb r12, [r12]
    cmp r12, #0
    beq note_on_native
    cmp r0, #0x20
    beq note_on_hold
    cmp r0, #0x30
    beq note_on_hold
    cmp r0, #0x40
    bne note_on_native
note_on_hold:
    push {r0, r1, r2, r3, r4, r5, r6, lr}
    movw r12, #0x3F15
    ldrb r12, [r12]
    cmp r12, #0
    beq hold_riparte
    /* SPEGNE: pressing a held note again releases it and plays nothing. */
    mov r0, r1
    bl find_sustained
    cmp r0, #0
    blt note_on_resume
    bl release_voice
    pop {r0, r1, r2, r3, r4, r5, r6, lr}
    bx lr
hold_riparte:
    /* RIPARTE with the arpeggiator on: a new chord, started with no key
     * held, replaces the held one. Without arpeggiator: native behaviour. */
    ldr r3, =0x20003E11
    ldrb r3, [r3]
    cmp r3, #0
    beq note_on_resume
    bl any_key_held
    cmp r0, #0
    bne note_on_resume
    bl release_sustained
note_on_resume:
    pop {r0, r1, r2, r3, r4, r5, r6, lr}
note_on_native:
    push.w {r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ldr r12, =0x0020A791
    bx r12

/* Voice table 0x20003C6C, 16 bytes per voice: +0 active, +1 source,
 * +2 key still held (0 = kept by the damper), +8 note; count at +0xDC. */

/* r0 = note. Returns the index of a voice kept by the damper, or -1. */
find_sustained:
    ldr r2, =0x20003C6C
    ldrb r3, [r2, #0xDC]
    movs r1, #0
find_loop:
    cmp r1, r3
    bge find_none
    ldrb r12, [r2]
    cmp r12, #0
    beq find_next
    ldrb r12, [r2, #2]
    cmp r12, #0
    bne find_next
    ldrb r12, [r2, #8]
    cmp r12, r0
    beq find_found
find_next:
    adds r1, #1
    adds r2, #16
    b find_loop
find_found:
    mov r0, r1
    bx lr
find_none:
    mov r0, #-1
    bx lr

/* Returns 1 when any active voice still has its key held. */
any_key_held:
    ldr r2, =0x20003C6C
    ldrb r3, [r2, #0xDC]
    movs r1, #0
held_loop:
    cmp r1, r3
    bge held_none
    ldrb r12, [r2]
    cmp r12, #0
    beq held_next
    ldrb r12, [r2, #2]
    cmp r12, #0
    bne held_yes
held_next:
    adds r1, #1
    adds r2, #16
    b held_loop
held_yes:
    movs r0, #1
    bx lr
held_none:
    movs r0, #0
    bx lr

/* r0 = voice index. Same calls as the native damper release (0x0020AF66). */
release_voice:
    push {r4, r5, r6, lr}
    mov r5, r0
    ldr r4, =0x20003C6C
    add r4, r4, r0, lsl #4
    ldrb r0, [r4, #1]
    ldrb r1, [r4, #8]
    mov r2, r5
    ldr r12, =0x0020A4F5
    blx r12
    mov r0, r5
    movs r1, #0
    ldr r12, =0x0020A405
    blx r12
    pop {r4, r5, r6, pc}

/* Release every voice kept by the damper. */
release_sustained:
    push {r4, r5, r6, lr}
    ldr r4, =0x20003C6C
    movs r5, #0
rel_loop:
    ldr r3, =0x20003C6C
    ldrb r3, [r3, #0xDC]
    cmp r5, r3
    bge rel_done
    ldrb r12, [r4]
    cmp r12, #0
    beq rel_next
    ldrb r12, [r4, #2]
    cmp r12, #0
    bne rel_next
    mov r0, r5
    bl release_voice
rel_next:
    adds r5, #1
    adds r4, #16
    b rel_loop
rel_done:
    pop {r4, r5, r6, pc}
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* New arpeggio modes (1.16).
 * The TYPE knob gives 17 values: Off, Rise1-3, Fall1-3, Rand1-3 (Korg) and
 * UPdn1-3, Conv, dIvr, PEdL, Chrd (new = "ext" 1..7). For a new mode the
 * pattern keeps the Korg type 1 (Rise1) in byte 70, so the Korg firmware
 * always reads a valid type; the new mode is stored in PRB3 (bit 7 of the
 * probabilities of steps 1-4). While a new mode is active, entry 1 of the
 * Korg type table 0x2000B420 points to a step table generated in ITCM
 * (0x3C00) for the number of held notes; otherwise to Korg's Rise1.
 * State: 0x3F16 current ext, 0x3F17/0x3F18 ext and note count of the
 * generated table. */

/* r0 = X, r1 = first step index (0 arp mode, 4 humanize, 8 octave).
 * Returns the 4-bit field kept in bit 7 of probabilities first..first+3 of a
 * valid PRB3 block, else 0. */
block_ext:
    movs r1, #0
block_bits:
    push {r4, r5, r6, lr}
    mov r4, r0
    mov r5, r1
    bl prb2_valid
    cmp r0, #0
    beq block_bits_none
    ldrb r0, [r4]
    cmp r0, #0xA3
    bne block_bits_none
    add r4, r5
    movs r0, #0
    movs r1, #0
block_bits_loop:
    adds r2, r4, r1
    ldrb r2, [r2, #1]
    lsrs r2, r2, #7
    lsls r2, r2, r1
    orrs r0, r2
    adds r1, #1
    cmp r1, #4
    bne block_bits_loop
    pop {r4, r5, r6, pc}
block_bits_none:
    movs r0, #0
    pop {r4, r5, r6, pc}

/* r0 = value 0..15, r1 = first step index: store the field in the current
 * pattern (a block is only created for a non-zero value). */
set_ext:
    movs r1, #0
set_bits:
    push {r3, r4, r5, r6, r7, lr}
    mov r5, r0
    mov r7, r1
    ldr r4, =0x2001E88C
    mov r0, r4
    bl block_bits
    cmp r0, r5
    beq set_bits_done
    cmp r5, #0
    bne set_bits_write
    mov r0, r4
    bl prb2_valid
    cmp r0, #0
    beq set_bits_done
set_bits_write:
    bl ensure_prb2
    add r3, r4, r7
    movs r1, #0
set_bits_loop:
    adds r2, r3, r1
    ldrb r0, [r2, #1]
    and r0, r0, #0x7F
    lsr r6, r5, r1
    and r6, r6, #1
    orr r0, r0, r6, lsl #7
    strb r0, [r2, #1]
    adds r1, #1
    cmp r1, #4
    bne set_bits_loop
    bl seal
set_bits_done:
    pop {r3, r4, r5, r6, r7, pc}

/* r0 = X. Returns r0 = humanize 0..15, r1 = octave 0..15 (0 without PRB3). */
seq_params:
    push {r4, lr}
    mov r4, r0
    bl prb2_valid
    cmp r0, #0
    beq seq_params_none
    ldrb r0, [r4]
    cmp r0, #0xA3
    bne seq_params_none
    movs r0, #0
    movs r1, #0
    movs r2, #0
seq_params_loop:
    adds r3, r4, r2
    ldrb r12, [r3, #5]
    lsr r12, r12, #7
    lsl r12, r12, r2
    orr r0, r0, r12
    ldrb r12, [r3, #9]
    lsr r12, r12, #7
    lsl r12, r12, r2
    orr r1, r1, r12
    adds r2, #1
    cmp r2, #4
    bne seq_params_loop
    pop {r4, pc}
seq_params_none:
    movs r0, #0
    movs r1, #0
    pop {r4, pc}
    .align 2
    .ltorg

/* ADC parameter 7 (ARP TYPE), any source: map 0..127 to 17 types. */
arp_knob:
    push {r0, r1, r2, r3, r4, lr}
    mov r4, r1
    cmp r4, #0
    bge arp_knob_pos
    movs r4, #0
arp_knob_pos:
    cmp r4, #127
    bls arp_knob_in
    movs r4, #127
arp_knob_in:
    add r4, r4, r4, lsl #4
    lsrs r4, r4, #7
    cmp r4, #10
    blo arp_knob_korg
    sub r0, r4, #9
    movs r4, #13
    b arp_knob_store
arp_knob_korg:
    /* Smallest raw value that the Korg mapping (v*5)>>6 turns into r4. */
    lsls r4, r4, #6
    adds r4, #4
    movs r0, #5
    udiv r4, r4, r0
    movs r0, #0
arp_knob_store:
    movw r1, #0x3F16
    strb r0, [r1]
    bl set_ext
    str r4, [sp, #4]
    pop {r0, r1, r2, r3, r4, lr}
    b adc_native

/* Entry of the arpeggiator tick 0x0020C40C (r0 = 0x20003E10). */
arp_tick:
    push {r0, r1, r2, r3, r4, lr}
    bl tempo_tick
    bl arp_update
    pop {r0, r1, r2, r3, r4, lr}
    push.w {r4, r5, r6, r7, r8, lr}
    ldr r12, =0x0020C411
    bx r12

/* Entry of 0x0020BDFC (a voice joins the arpeggio): refresh the table
 * first, so the very first step already uses the new mode. */
arp_start:
    push {r0, r1, r2, r3, r4, lr}
    /* Arpeggio starting (+2 == 0xFF): its first note is played by the
     * native voice path, whose MIDI echo is muted while the arpeggiator is
     * on, so queue it here: note = voice +7, velocity = voice +0x13. */
    ldrb r2, [r0, #2]
    cmp r2, #0xFF
    bne arp_start_running
    cmp r1, #6
    bhs arp_start_running
    mov r4, r1
    bl step_tick
    bl midi_release_all
    movw r12, #0x3F22
    ldrb r0, [r12]
    strb r0, [r12, #1]
    ldr r3, =0x200031D4
    movs r2, #0x34
    mla r3, r2, r4, r3
    ldrb r1, [r3, #7]
    ldrb r2, [r3, #0x13]
    and r1, r1, #0x7F
    cmp r2, #1
    it lt
    movlt r2, #1
    push {r1}
    movs r0, #1
    bl midi_enqueue
    pop {r1}
    movw r12, #0x3F28
    strb r1, [r12, r4]
arp_start_running:
    bl arp_update
    pop {r0, r1, r2, r3, r4, lr}
    push {r3, r4, r5, r6, r7, lr}
    mov r4, r0
    ldr r12, =0x0020BE01
    bx r12

arp_update:
    push {r4, r5, r6, lr}
    bl midi_release_gone
    movw r4, #0x3F00
    ldr r0, =0x2001E88C
    bl block_ext
    cmp r0, #7
    bls arp_ext_ok
    movs r0, #0
arp_ext_ok:
    strb r0, [r4, #0x16]
    mov r5, r0
    cmp r5, #0
    beq arp_korg_table
    /* Held notes = arpeggiator voices with +4 == 1 (0x200031D4, 6 x 0x34). */
    ldr r2, =0x200031D4
    movs r6, #0
    movs r1, #0
arp_count:
    ldrb r3, [r2, #4]
    cmp r3, #1
    bne arp_count_next
    adds r6, #1
arp_count_next:
    adds r2, #0x34
    adds r1, #1
    cmp r1, #6
    bne arp_count
    cmp r6, #1
    bge arp_n_low
    movs r6, #1
arp_n_low:
    cmp r6, #6
    ble arp_n_ok
    movs r6, #6
arp_n_ok:
    ldrb r0, [r4, #0x17]
    cmp r0, r5
    bne arp_regen
    ldrb r0, [r4, #0x18]
    cmp r0, r6
    beq arp_point
arp_regen:
    strb r5, [r4, #0x17]
    strb r6, [r4, #0x18]
    mov r0, r5
    mov r1, r6
    bl arp_generate
arp_point:
    ldr r2, =0x2000B424
    movw r3, #0x3C00
    str r3, [r2]
    pop {r4, r5, r6, pc}
arp_korg_table:
    ldr r2, =0x2000B424
    ldr r3, =0x2000B57C
    str r3, [r2]
    pop {r4, r5, r6, pc}

/* r0 = ext 1..7, r1 = notes 1..6. Writes the step table at 0x3C00:
 * header word = number of steps, then one word per step with a 4-bit
 * octave code (3 = base, 4 = +1, 5 = +2) for each of the 6 sorted notes. */
arp_generate:
    push {r4, r5, r6, r7, r8, lr}
    movw r4, #0x3C04
    mov r7, r1
    movs r5, #0
    cmp r0, #3
    bls gen_updown
    cmp r0, #4
    beq gen_converge
    cmp r0, #5
    beq gen_diverge
    cmp r0, #6
    beq gen_pedal
    /* Chrd: every held note together on each step. */
    ldr r2, =0x00333333
    str r2, [r4]
    movs r5, #1
    b gen_done
gen_updown:
    /* Up through r0 octaves, then down without repeating the ends. */
    mov r6, r0
    movs r8, #0
gen_ud_oct:
    movs r1, #0
gen_ud_note:
    add r2, r8, #3
    lsls r3, r1, #2
    lsl r2, r2, r3
    str r2, [r4, r5, lsl #2]
    adds r5, #1
    adds r1, #1
    cmp r1, r7
    blt gen_ud_note
    add r8, r8, #1
    cmp r8, r6
    blt gen_ud_oct
    sub r1, r5, #2
gen_ud_down:
    cmp r1, #1
    blt gen_done
    ldr r2, [r4, r1, lsl #2]
    str r2, [r4, r5, lsl #2]
    adds r5, #1
    subs r1, #1
    b gen_ud_down
gen_converge:
    bl gen_conv_list
    b gen_done
gen_diverge:
    bl gen_conv_list
    /* reverse the converge order */
    movs r1, #0
    sub r2, r5, #1
gen_rev:
    cmp r1, r2
    bge gen_done
    ldr r3, [r4, r1, lsl #2]
    ldr r12, [r4, r2, lsl #2]
    str r12, [r4, r1, lsl #2]
    str r3, [r4, r2, lsl #2]
    adds r1, #1
    subs r2, #1
    b gen_rev
gen_pedal:
    /* lowest note alternating with each of the others */
    cmp r7, #1
    bne gen_pedal_many
    movs r2, #3
    str r2, [r4]
    movs r5, #1
    b gen_done
gen_pedal_many:
    movs r1, #1
gen_pedal_loop:
    movs r2, #3
    str r2, [r4, r5, lsl #2]
    adds r5, #1
    lsls r3, r1, #2
    lsl r2, r2, r3
    str r2, [r4, r5, lsl #2]
    adds r5, #1
    adds r1, #1
    cmp r1, r7
    blt gen_pedal_loop
gen_done:
    movw r2, #0x3C00
    str r5, [r2]
    pop {r4, r5, r6, r7, r8, pc}

/* Converge order for r7 notes into [r4], count in r5: 0, n-1, 1, n-2 ... */
gen_conv_list:
    movs r1, #0
    sub r2, r7, #1
gen_conv_loop:
    cmp r1, r2
    bgt gen_conv_end
    lsls r3, r1, #2
    mov r12, #3
    lsl r12, r12, r3
    str r12, [r4, r5, lsl #2]
    adds r5, #1
    cmp r1, r2
    beq gen_conv_end
    lsls r3, r2, #2
    mov r12, #3
    lsl r12, r12, r3
    str r12, [r4, r5, lsl #2]
    adds r5, #1
    adds r1, #1
    subs r2, #1
    b gen_conv_loop
gen_conv_end:
    bx lr
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* Arpeggio notes on MIDI OUT (1.16).
 * The arpeggiator triggers its notes through 0x002097E4 (voice, note, vel),
 * used only by the arpeggiator. Each note is queued as MIDI note-on; the
 * notes of the previous step are queued as note-off when a new step starts,
 * and when their voice leaves the arpeggio. The queue is sent from the
 * native MIDI OUT service 0x00207F2C (main loop) through the native note
 * senders 0x00207BD4 / 0x00207C74, which handle DIN, USB and the channel.
 * While the arpeggiator is on, the keyboard keys are not echoed on MIDI
 * OUT (the arpeggio is sent instead).
 * State: 0x3F20 head, 0x3F21 tail, 0x3F22 step counter, 0x3F23 last step
 * seen, 0x3F28..0x3F2D MIDI note per arpeggio voice (0xFF none),
 * queue 0x3F40: 16 entries x 3 bytes (kind 1 on / 0 off, note, velocity). */

/* r0 = kind, r1 = note, r2 = velocity. Drops the event if the queue is full. */
midi_enqueue:
    movw r12, #0x3F20
    ldrb r3, [r12]
    push {r4}
    add r4, r3, #1
    and r4, r4, #15
    ldrb r12, [r12, #1]
    cmp r4, r12
    beq enqueue_full
    movw r12, #0x3F40
    add r3, r3, r3, lsl #1
    add r12, r12, r3
    strb r0, [r12]
    strb r1, [r12, #1]
    strb r2, [r12, #2]
    movw r12, #0x3F20
    strb r4, [r12]
enqueue_full:
    pop {r4}
    bx lr

/* Queue note-off for every recorded arpeggio note. */
midi_release_all:
    push {r4, r5, r6, lr}
    movw r4, #0x3F28
    movs r5, #0
release_all_loop:
    ldrb r1, [r4, r5]
    cmp r1, #0xFF
    beq release_all_next
    movs r0, #0
    movs r2, #0
    bl midi_enqueue
    movs r1, #0xFF
    strb r1, [r4, r5]
release_all_next:
    adds r5, #1
    cmp r5, #6
    bne release_all_loop
    pop {r4, r5, r6, pc}

/* Queue note-off for recorded notes whose voice is no longer in the
 * arpeggio (voice +4 != 1). */
midi_release_gone:
    push {r4, r5, r6, lr}
    movw r4, #0x3F28
    ldr r6, =0x200031D4
    movs r5, #0
release_gone_loop:
    ldrb r1, [r4, r5]
    cmp r1, #0xFF
    beq release_gone_next
    ldrb r3, [r6, #4]
    cmp r3, #1
    beq release_gone_next
    movs r0, #0
    movs r2, #0
    bl midi_enqueue
    movs r1, #0xFF
    strb r1, [r4, r5]
release_gone_next:
    adds r6, #0x34
    adds r5, #1
    cmp r5, #6
    bne release_gone_loop
    pop {r4, r5, r6, pc}

/* A new arpeggio step begins. */
step_tick:
    movw r12, #0x3F22
    ldrb r3, [r12]
    adds r3, #1
    strb r3, [r12]
    bx lr

/* Entry of 0x0020C1F4 (arpeggio step). */
arp_step:
    push {r0, r1, r2, r3, r4, lr}
    bl step_tick
    pop {r0, r1, r2, r3, r4, lr}
    push.w {r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ldr r12, =0x0020C1F9
    bx r12

/* Entry of 0x002097E4 (r0 voice, r1 note, r2 velocity). */
arp_voice_on:
    push {r0, r1, r2, r3, r4, r5, r6, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    /* first note of a new step: end the previous step's notes */
    movw r12, #0x3F22
    ldrb r0, [r12]
    ldrb r1, [r12, #1]
    cmp r0, r1
    beq voice_on_same_step
    strb r0, [r12, #1]
    bl midi_release_all
voice_on_same_step:
    cmp r4, #6
    bhs voice_on_native
    movw r12, #0x3F28
    ldrb r1, [r12, r4]
    cmp r1, #0xFF
    beq voice_on_send
    movs r0, #0
    movs r2, #0
    bl midi_enqueue
voice_on_send:
    and r5, r5, #0x7F
    cmp r6, #1
    bge voice_vel_low
    movs r6, #1
voice_vel_low:
    cmp r6, #127
    ble voice_vel_ok
    movs r6, #127
voice_vel_ok:
    movs r0, #1
    mov r1, r5
    mov r2, r6
    bl midi_enqueue
    movw r12, #0x3F28
    strb r5, [r12, r4]
voice_on_native:
    pop {r0, r1, r2, r3, r4, r5, r6, lr}
    push {r3, r4, r5, r6, r7, lr}
    mov r7, r2
    ldr r12, =0x002097E9
    bx r12

/* Entry of the native MIDI OUT service 0x00207F2C (main loop). */
midi_flush:
    push {r0, r1, r2, r3, r4, lr}
    bl midi_release_gone
flush_loop:
    movw r4, #0x3F20
    ldrb r3, [r4, #1]
    ldrb r2, [r4]
    cmp r2, r3
    beq flush_done
    movw r12, #0x3F40
    add r2, r3, r3, lsl #1
    add r12, r12, r2
    adds r3, #1
    and r3, r3, #15
    strb r3, [r4, #1]
    ldrb r0, [r12, #1]
    ldrb r1, [r12, #2]
    ldrb r2, [r12]
    cmp r2, #0
    beq flush_off
    ldr r12, =0x00207BD5
    blx r12
    b flush_loop
flush_off:
    ldr r12, =0x00207C75
    blx r12
    b flush_loop
flush_done:
    pop {r0, r1, r2, r3, r4, lr}
    push.w {r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ldr r12, =0x00207F31
    bx r12

/* Replaces the keyboard's MIDI echo call (0x0020AA8E, r0 note, r1 vel). */
kbd_echo_on:
    ldr r12, =0x20003E11
    ldrb r12, [r12]
    cmp r12, #0
    bne kbd_echo_skip
    ldr r12, =0x00207BD5
    bx r12
kbd_echo_skip:
    bx lr
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* Scales (1.17). Global, not saved: 0x3F30 on, 0x3F31 scale 0..14,
 * 0x3F32 tonic 0..11 (C..B), 0x3F33 live sequence option.
 * Masks at 0x1F70 (bit i = i semitones above the tonic). A note outside the
 * scale goes to the nearest scale note; at equal distance the upper one. */

/* FUNC + SAVE: scale on / off. */
scale_button:
    cmp r1, #0
    beq scale_native
    ldr r12, =0x200029DA
    ldrb r12, [r12]
    cmp r12, #0x12
    bne scale_native
    push {r4, lr}
    movw r4, #0x3F30
    ldrb r0, [r4]
    eor r0, r0, #1
    strb r0, [r4]
    rsb r0, r0, #15
    bl msg_ptr
    bl show_text
    pop {r4, pc}
scale_native:
    ldr r12, =0x20011321
    bx r12

/* r0 = note 0..127. Returns the corrected note. Clobbers r1-r3, r12. */
quantize:
    movw r12, #0x3F30
    ldrb r1, [r12]
    cmp r1, #0
    beq quantize_exit
    cmp r0, #128
    bhs quantize_exit
    ldrb r1, [r12, #1]
    cmp r1, #15
    bhs quantize_exit
    movw r2, #0x1F70
    ldrh r2, [r2, r1, lsl #1]
    ldrb r3, [r12, #2]
    cmp r3, #12
    bhs quantize_exit
    push {r4, r5, r6, lr}
    /* r4 = pitch class relative to the tonic */
    adds r4, r0, #12
    subs r4, r4, r3
    movs r5, #12
    udiv r1, r4, r5
    mls r4, r1, r5, r4
    lsr r1, r2, r4
    tst r1, #1
    bne quantize_done
    movs r3, #1
quantize_loop:
    adds r1, r4, r3
    cmp r1, #12
    it hs
    subhs r1, #12
    lsr r1, r2, r1
    tst r1, #1
    beq quantize_below
    adds r1, r0, r3
    cmp r1, #127
    bhi quantize_below
    mov r0, r1
    b quantize_done
quantize_below:
    subs r1, r4, r3
    it mi
    addmi r1, #12
    lsr r1, r2, r1
    tst r1, #1
    beq quantize_next
    subs r1, r0, r3
    bmi quantize_next
    mov r0, r1
    b quantize_done
quantize_next:
    adds r3, #1
    cmp r3, #12
    blo quantize_loop
quantize_done:
    pop {r4, r5, r6, pc}
quantize_exit:
    bx lr

/* BL at 0x0020AA8A instead of ADDS r4,#5; UXTB r0,r4 (keyboard note-on).
 * r4 = key + 12 * octave, r6 = key, r1 = velocity (kept). The note played is
 * stored per key, so the note-off matches even if the scale changes. */
kbd_q_on:
    push {r1, r2, r3, lr}
    adds r0, r4, #5
    bl quantize
    mov r4, r0
    cmp r6, #32
    bhs kbd_q_on_done
    movw r12, #0x1800
    strb r4, [r12, r6]
kbd_q_on_done:
    uxtb r0, r4
    pop {r1, r2, r3, pc}

/* BL at 0x0020AACA instead of ADDS r4,#5; UXTB r6,r4 (keyboard note-off).
 * r4 = key + 12 * octave, r5 = key. Returns r4 = r6 = note to release. */
kbd_q_off:
    push {r0, r1, r2, r3, r5, lr}
    cmp r5, #32
    bhs kbd_q_off_compute
    movw r12, #0x1800
    ldrb r0, [r12, r5]
    cmp r0, #0xFF
    beq kbd_q_off_compute
    movs r1, #0xFF
    strb r1, [r12, r5]
    mov r4, r0
    b kbd_q_off_done
kbd_q_off_compute:
    adds r0, r4, #5
    bl quantize
    mov r4, r0
kbd_q_off_done:
    uxtb r6, r4
    pop {r0, r1, r2, r3, r5, pc}

/* r0 = incoming note, r2 = map (128 bytes). Returns the note to play and
 * records it. Keeps r1-r3. */
map_on:
    push {r1, r2, r3, r4, r5, lr}
    mov r4, r2
    mov r5, r0
    bl quantize
    cmp r5, #128
    it lo
    strblo r0, [r4, r5]
    pop {r1, r2, r3, r4, r5, pc}

/* r0 = incoming note, r2 = map. Returns the note played by its note-on
 * (or the corrected note if none was recorded) and clears the record. */
map_off:
    push {r1, r2, r3, r4, r5, lr}
    cmp r0, #128
    bhs map_off_compute
    ldrb r3, [r2, r0]
    cmp r3, #0xFF
    beq map_off_compute
    movs r1, #0xFF
    strb r1, [r2, r0]
    mov r0, r3
    pop {r1, r2, r3, r4, r5, pc}
map_off_compute:
    bl quantize
    pop {r1, r2, r3, r4, r5, pc}

/* Entries of the MIDI DIN / USB note-on and note-off (r0 note, r1 velocity). */
din_on:
    push {r1, lr}
    movw r2, #0x1820
    bl map_on
    pop {r1, lr}
    push {r3, r4, r5, lr}
    mov r4, r0
    ldr r12, =0x0020AB31
    bx r12
din_off:
    push {r1, lr}
    movw r2, #0x1820
    bl map_off
    pop {r1, lr}
    push {r3, r4, r5, lr}
    mov r1, r0
    ldr r12, =0x0020AB69
    bx r12
usb_on:
    push {r1, lr}
    movw r2, #0x18A0
    bl map_on
    pop {r1, lr}
    push {r3, r4, r5, lr}
    mov r4, r0
    ldr r12, =0x0020ABC5
    bx r12
usb_off:
    push {r1, lr}
    movw r2, #0x18A0
    bl map_off
    pop {r1, lr}
    push {r3, r4, r5, lr}
    mov r1, r0
    ldr r12, =0x0020ABFD
    bx r12

/* BL at 0x0020BA6E instead of STRB.W r0,[r7,r4,LSL #2]: the sequencer stores
 * the note of a new step in its slot table (r7 = 0x20003DC4, r4 = slot) and
 * then plays it with velocity r1. The slot keeps the note actually played,
 * so the native note-off always matches. Applies the scale (live option),
 * the random octave and humanize (velocity) of the current pattern. */
seq_note:
    push {r2, r3, r4, r5, r6, r7, r12, lr}
    mov r5, r0
    mov r6, r1
    movw r12, #0x3F30
    ldrb r2, [r12, #3]
    cmp r2, #0
    beq seq_note_params
    bl quantize
    mov r5, r0
seq_note_params:
    ldr r0, =0x2001E88C
    bl seq_params
    mov r4, r1
    cmp r0, #0
    beq seq_note_octave
    /* humanize: velocity +- 3 * level */
    add r7, r0, r0, lsl #1
    lsls r0, r7, #1
    adds r0, #1
    ldr r12, =0x002094A5
    blx r12
    subs r0, r0, r7
    adds r6, r6, r0
    cmp r6, #1
    it lt
    movlt r6, #1
    cmp r6, #127
    it gt
    movgt r6, #127
seq_note_octave:
    cmp r4, #0
    beq seq_note_store
    /* random octave: probability level / 15, up or down */
    movs r0, #15
    ldr r12, =0x002094A5
    blx r12
    cmp r0, r4
    bhs seq_note_store
    movs r0, #2
    ldr r12, =0x002094A5
    blx r12
    cmp r0, #0
    beq seq_note_down
    adds r5, #12
    cmp r5, #127
    ble seq_note_store
    subs r5, #24
    b seq_note_store
seq_note_down:
    subs r5, #12
    bge seq_note_store
    adds r5, #24
seq_note_store:
    mov r0, r5
    mov r1, r6
    pop {r2, r3, r4, r5, r6, r7, r12, lr}
    strb.w r0, [r7, r4, lsl #2]
    bx lr
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

/* Same, but a delay layout also while the reverb is selected (display). */
fx_ui_key:
    movw r12, #0x3F80
    ldrb r0, [r12]
    cmp r0, #0
    it eq
    moveq r0, #1
    ldrb r1, [r12, #3]
    orr r0, r0, r1, lsl #2
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

/* Entry of the arpeggiator tick (every clock tick, 72 per 16th, from any
 * clock source): frames per 16th measured with the audio frame counter. */
tempo_tick:
    push {r0, r1, r2, r3, r4, lr}
    movw r4, #0x3F80
    ldr r0, [r4, #8]
    ldr r1, [r4, #0x14]
    str r0, [r4, #0x14]
    subs r1, r0, r1
    movw r2, #25000
    cmp r1, r2
    bls tempo_count
    /* clock (re)started after a pause: count from this tick */
    movs r1, #0
    strb r1, [r4, #0x18]
    str r0, [r4, #0xC]
    b tempo_done
tempo_count:
    ldrb r1, [r4, #0x18]
    adds r1, #1
    cmp r1, #72
    blo tempo_store
    ldr r2, [r4, #0xC]
    str r0, [r4, #0xC]
    subs r2, r0, r2
    movw r3, #400
    cmp r2, r3
    blo tempo_reset
    ldr r3, =200000
    cmp r2, r3
    it ls
    strls r2, [r4, #0x10]
tempo_reset:
    movs r1, #0
tempo_store:
    strb r1, [r4, #0x18]
tempo_done:
    pop {r0, r1, r2, r3, r4, pc}

/* FUNC+4 (native reverb on/off, saved in the pattern): run the native
 * toggle, then show which effect was switched. */
fx_toggle:
    push {r4, lr}
    ldr r12, =0x0020C8B7
    blx r12
    movw r12, #0x3F80
    ldrb r0, [r12]
    cmp r0, #3
    it hs
    movhs r0, #0
    ldr r1, =0x20000011
    ldrb r1, [r1]
    cmp r1, #0
    ite ne
    movne r1, #0
    moveq r1, #1
    add r0, r1, r0, lsl #1
    adds r0, #22
    bl msg_ptr
    bl show_text
    pop {r4, pc}

/* r1 = native text buffer: "REVRB nnn" -> "DELAY nnn" / "LOFI  nnn". */
fx_label:
    movw r12, #0x3F80
    ldrb r0, [r12]
    cbz r0, fx_label_done
    cmp r0, #3
    bhs fx_label_done
    ldr r2, [r1]
    ldr r3, =0x52564552
    cmp r2, r3
    bne fx_label_done
    ldrb r2, [r1, #4]
    cmp r2, #66
    bne fx_label_done
    add r0, r0, r0, lsl #2
    movw r2, #0x1940
    add r0, r2
    movs r2, #5
    b copy_text
fx_label_done:
    bx lr

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
    cbz r0, fx_reset_done
    bl fx_samples
    lsls r0, r0, #12
    str r0, [r4, #0x28]
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
    ldr r1, [r4, #0x28]
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
    FB_MONO
    LIMIT r1, r12
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
    FB_PP
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

/* ---------------------------------------------------------------- */
/* 1.19 chain readouts (the chain logic is in the flash blob). */

/* r0 = 0..99 -> two ASCII digits at r1. */
put2:
    movs r2, #10
    udiv r3, r0, r2
    mls r0, r3, r2, r0
    adds r3, #48
    adds r0, #48
    strb r3, [r1]
    strb r0, [r1, #1]
    bx lr

/* Pattern readout after MEMORY + key (veneer 0x20014FB8, native 0x00208C5C):
 * with a free chain just edited, "CH05  P07" (entries, last pattern added). */
chain_disp:
    movw r12, #0x1D00
    ldrb r1, [r12, #0xD]
    cbnz r1, chain_disp_ours
    ldr r12, =0x00208C5D
    bx r12
chain_disp_ours:
    movs r1, #0
    strb r1, [r12, #0xD]
    push {r4, lr}
    sub sp, #16
    mov r4, r12
    ldr r0, =0x30304843
    str r0, [sp]
    ldr r0, =0x30502020
    str r0, [sp, #4]
    movs r0, #48
    strb r0, [sp, #8]
    ldrb r0, [r4, #3]
    add r1, sp, #2
    bl put2
    ldrb r0, [r4, #3]
    movw r1, #0x1C00
    add r1, r1, r0, lsl #1
    ldrb r0, [r1, #-2]
    adds r0, #1
    add r1, sp, #7
    bl put2
    mov r0, sp
    bl show_text
    add sp, #16
    pop {r4, pc}

    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* 1.20 additions. */

/* Native "is a chain playing" check (0x0020C5D2: ldrb r0, [r0, #0x15]),
 * reached through the SRAM veneer 0x200150E0 only by the panel. With CR ON
 * the panel functions that the Korg firmware blocks during a chain work as
 * without one: REC, FUNC + step keys, FUNC + MEMORY (WRITE, or the copy of
 * the previous pattern), FUNC + PLAY, FUNC + EDIT, FUNC + SAVE. */
chain_q:
    ldrb r0, [r0, #0x15]
    cbz r0, cq_done
    movw r12, #0x1D00
    ldrb r12, [r12, #2]
    cmp r12, #0
    beq cq_done
    push {r4, lr}
    bic r4, lr, #1
    adr r1, unlock_lr
cq_loop:
    ldr r2, [r1], #4
    cbz r2, cq_blocked
    cmp r2, r4
    bne cq_loop
    ldr r2, =0x20011F3C
    cmp r4, r2
    bne cq_open
    bl copy_previous
    pop {r4, pc}
cq_open:
    movs r0, #0
cq_blocked:
    pop {r4, pc}
cq_done:
    bx lr
    .align 2
unlock_lr:
    .word 0x20011AB0     @ REC
    .word 0x200111D8     @ FUNC + step keys
    .word 0x20011F3C     @ FUNC + MEMORY (WRITE / copy)
    .word 0x20010B80     @ WRITE destination
    .word 0x20011A28     @ FUNC + PLAY
    .word 0x2001207C     @ FUNC + EDIT
    .word 0x20011D70     @ FUNC + SAVE
    .word 0

/* FUNC + MEMORY with CR ON, REC on and a chain: if the pattern playing is
 * empty (no note and no motion on any step), copy the pattern played before
 * it into it, save it (native WRITE) and reload it. Returns 1 (copy done,
 * no WRITE) or 0 (native WRITE). */
copy_previous:
    push {r4, r5, r6, r7, lr}
    ldr r0, =0x20003F8C
    ldr r0, [r0]
    tst r0, #2
    beq cp_write
    movw r4, #0x1D00
    ldrb r5, [r4, #0xE]
    cmp r5, #0
    beq cp_write
    subs r5, #1
    ldr r6, =0x20003198
    ldrb r6, [r6, #6]
    cmp r6, #16
    bhs cp_write
    cmp r5, r6
    beq cp_write
    /* empty: bytes +24..+29 (notes on) and +43..+107 (motion) of each step */
    ldr r0, =0x2001E12C
    adds r0, #80
    movs r1, #16
cp_step:
    movs r2, #24
cp_byte:
    ldrb r3, [r0, r2]
    cmp r3, #0
    bne cp_write
    adds r2, #1
    cmp r2, #30
    it eq
    moveq r2, #43
    cmp r2, #108
    blo cp_byte
    adds r0, #112
    subs r1, #1
    bne cp_step
    /* PATTERN <- bank[previous] */
    ldr r0, =0x2001D08C
    ldr r0, [r0]
    movw r2, #1920
    mla r0, r5, r2, r0
    ldr r1, =0x2001E12C
cp_copy:
    subs r2, #4
    ldr r3, [r0, r2]
    str r3, [r1, r2]
    bne cp_copy
    mov r0, r6
    ldr r12, =0x0020815D
    blx r12
    ldr r7, =0x20003198
    ldrb r7, [r7, #0xB]
    mov r0, r6
    movs r1, #0
    ldr r12, =0x00208901
    blx r12
    ldr r0, =0x20003198
    strb r7, [r0, #0xB]
    /* "CPY 03-05" */
    sub sp, #12
    ldr r0, =0x20595043
    str r0, [sp]
    movs r0, #0x2D
    strb r0, [sp, #6]
    adds r0, r5, #1
    add r1, sp, #4
    bl put2
    adds r0, r6, #1
    add r1, sp, #7
    bl put2
    mov r0, sp
    bl show_text
    add sp, #12
    movs r0, #1
    pop {r4, r5, r6, r7, pc}
cp_write:
    movs r0, #0
    pop {r4, r5, r6, r7, pc}

    .align 2
    .ltorg
