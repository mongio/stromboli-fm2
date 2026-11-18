/* volca FM2 experimental firmware 1.28 - SRAM blob at 0x200164B0 (original
 * FF padding of the ff13 section, copied to RAM by the Korg loader with the
 * whole section and not used at runtime). Panel, pages, sequencer, scales,
 * arpeggiator and MIDI code moved out of the ITCM in 1.22 to make room for
 * the audio effects. Entered through the ITCM trampolines (same table order).
 * Calls into the ITCM use ICALL (BL cannot reach).
 * 1.27: waves of the FM operators (end of file); 1.28: in the Korg EDIT,
 * engine FM / VA (parameter of ALL). */
.syntax unified
.thumb
.include "itcm_symbols.inc"

.macro ICALL sym
    ldr r12, =\sym
    blx r12
.endm

stable:
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
    b.w sram_unused       @ 0x2058  audio ISR effect call (ITCM literal 0x023C, was reverb 0x1461)
    b.w fx_toggle         @ 0x205C  FUNC+4 reverb toggle veneer literal 0x2001516C (was 0x0020C8B7)
    b.w sram_unused       @ 0x2060  (mod_audio stays in the ITCM)
    b.w step_map          @ 0x2064  1.23 clock -> step routine (direction)
    b.w led_map           @ 0x2068  1.23 clock -> step LED (direction)
    b.w seq_tick          @ 0x206C  1.24 end of every clock tick (microtiming, ratchet)
    b.w bnd_release       @ 0x2070  1.24 step boundary note release
    b.w multi_dsp_on      @ 0x2074  1.25 DSP voice allocation 0x00209574
    b.w multi_arp_on      @ 0x2078  1.25 arpeggiator voice start 0x002093FE
    b.w multi_call_a      @ 0x207C  1.25 voice start (BL at 0x00209746)
    b.w multi_call_b      @ 0x2080  1.25 arpeggiator voice start (BL at 0x00209488)
    b.w multi_patch       @ 0x2084  1.25 program of the voice (BL at 0x0020E6F0)
    b.w multi_gain        @ 0x2088  1.25 level of the voice (BL at 0x0020E79E)
    b.w multi_dsp_off     @ 0x208C  1.25 DSP note-off 0x00209870 (notes of the part channels stay)
    b.w filt_unused       @ 0x2090  1.26 (ITCM only: filter of the voice)
    b.w filt_keyoff       @ 0x2094  1.26 key-off of the voice (BL at 0x0020E7EA)
    b.w filt_control      @ 0x2098  1.26 control step of the filter of a voice
    b.w filt_unused       @ 0x209C  1.28 (ITCM only: kernel of the voice)
    b.w ext_load          @ 0x20A0  1.28 program load: STROMBOLI block (BL at 0x0020E490)
    b.w ext_save          @ 0x20A4  1.28 program save: STROMBOLI block (BL at 0x0020EF36)
    b.w ext_sysex         @ 0x20A8  1.28 Korg program SysEx received: default block (BL at 0x0020F346)

sram_unused:
    bx lr


/* ---------------------------------------------------------------- */
/* Sequencer hook: replaces LDRH r3,[r4,#6]; MOV.W r8,#0 at 0x0020B7CA */
prob_entry:
    push.w {r0, r1, r2, r4, r5, r6, r7, lr}
    /* 1.24: a ratchet hit repeats the step as decided: no new decision */
    movw r12, #0x3980
    ldrb r0, [r12, #0x23]
    cbnz r0, prob_retrig
    /* 1.23: loops are counted on the clock counter of the step (1.24: the
     * counter the step belongs to, also when played early or late), not
     * on the played step (which follows the pattern direction) */
    ldrb r0, [r12, #0x22]
    bl track_loop
    ldr r0, [sp]
    mov r1, r4
    bl decide
    movw r12, #0x3980
    strb r0, [r12, #0x24]
    mov r3, r0
    pop.w {r0, r1, r2, r4, r5, r6, r7, lr}
    cmp r3, #0
    beq prob_rejected
    ldrh r3, [r4, #6]
    b prob_resume
prob_rejected:
    movs r3, #0
    b prob_resume
prob_retrig:
    pop.w {r0, r1, r2, r4, r5, r6, r7, lr}
    ldrh r3, [r4, #6]
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
    /* 1.22: modulation SYNC counts sixteenths from here */
    movw r12, #0x3B80
    str r3, [r12, #0x3C]
    /* 1.23: direction restarts (ping-pong forward first, no cached step) */
    movw r12, #0x3F30
    movs r3, #1
    strb r3, [r12, #7]
    movs r3, #0xFF
    strb r3, [r12, #8]
    /* 1.24: no late, early or ratchet hit pending */
    movw r12, #0x3980
    strb r3, [r12, #0x25]
    strb r3, [r12, #0x27]
    strb r3, [r12, #0x32]
    movs r3, #0
    strb r3, [r12, #0x28]
    strb r3, [r12, #0x29]
    strb r3, [r12, #0x30]
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
    /* 1.27: the wave chain is built at the first key scan after power-on
     * (silence), before any note can use it */
    movw r12, #0x3880
    ldrb r12, [r12, #4]
    cmp r12, #0
    bne pk_ready
    push {r0, r1, r2, r3, r4, lr}
    bl wave_build
    pop {r0, r1, r2, r3, r4, lr}
pk_ready:
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
    /* 1.25 PA Pb PC (18..20): keys 1..11 select the parameter of the part. */
    cmp r0, #18
    bhs keys_multi
    /* SC: key 16 toggles the live sequence option. dt: SYNC/LIBERO.
     * Fb: MONO/PING PONG. Other modes: no key. */
    cmp r0, #8
    beq keys_dt
    cmp r0, #9
    beq keys_fb
    cmp r0, #17
    beq keys_cr
    cmp r0, #15
    bhs keys_seqstep
    cmp r0, #10
    beq keys_mo
    cmp r0, #11
    beq keys_rt
    cmp r0, #12
    beq keys_rs
    cmp r0, #14
    beq keys_mu
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
/* 1.22 modulation type page: key 16 = STEREO / MONO (phaser) or PAN /
 * MONO (tremolo); rt page: key 16 = SYNC / LIBERO. */
keys_mo:
    cmp r6, #15
    bne keys_done
    movw r12, #0x3B80
    ldrb r1, [r12]
    cmp r1, #0
    beq keys_done
    ldrb r0, [r12, #3]
    eor r0, r0, #1
    strb r0, [r12, #3]
    cbz r0, keys_mo_mono
    cmp r1, #1
    ite eq
    moveq r0, #30
    movne r0, #31
    b keys_mo_show
keys_mo_mono:
    movs r0, #20
keys_mo_show:
    strb r0, [r4, #3]
    bl render
    b keys_done
/* 1.23 rS page, phaser: key 16 = 4 / 6 / 8 stages. Mu page: key 16 =
 * mutation range +-3 / +-7 scale degrees (saved in the pattern). */
keys_rs:
    cmp r6, #15
    bne keys_done
    movw r12, #0x3B80
    ldrb r1, [r12]
    cmp r1, #1
    bne keys_done
    ldrb r0, [r12, #9]
    adds r0, #1
    cmp r0, #3
    it hs
    movhs r0, #0
    strb r0, [r12, #9]
    bl render
    b keys_done
keys_mu:
    cmp r6, #15
    bne keys_done
    movw r12, #0x3F30
    ldrb r0, [r12, #6]
    eor r0, r0, #1
    strb r0, [r12, #6]
    bl save_seqx
    bl render
    b keys_done
keys_rt:
    cmp r6, #15
    bne keys_done
    movw r12, #0x3B80
    ldrb r0, [r12, #2]
    eor r0, r0, #1
    strb r0, [r12, #2]
    rsb r0, r0, #19
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
/* 1.24 rA (15) / ti (16): keys select the step, as in P / C. The selected
 * step's key again: rA = volume shape PARI / CALA / CRESCE of that step,
 * ti = step microtiming <-> swing of the pattern. */
keys_seqstep:
    ldrb r1, [r4, #1]
    cmp r1, r6
    bne keys_seqsel
    movw r12, #0x3980
    cmp r0, #16
    beq keys_ti_swing
    ldrb r2, [r12, r6]
    ubfx r3, r2, #4, #2
    adds r3, #1
    cmp r3, #3
    it hs
    movhs r3, #0
    bfi r2, r3, #4, #2
    strb r2, [r12, r6]
    adds r3, #32
    strb r3, [r4, #3]
    bl save_seq2
    bl render
    b keys_done
keys_ti_swing:
    ldrb r2, [r12, #0x21]
    eor r2, r2, #1
    strb r2, [r12, #0x21]
    bl render
    b keys_done
keys_seqsel:
    movw r12, #0x3980
    movs r2, #0
    strb r2, [r12, #0x21]
keys_step:
    strb r6, [r4, #1]
    bl render
    bl leds
keys_done:
    pop {r4, r5, r6, pc}
keys_multi:
    cmp r0, #21
    bhs keys_filt
    cmp r6, #10
    bhi keys_done
    b keys_step
/* 1.26 FL, LF (21, 22): keys 1..13 */
keys_filt:
    cmp r6, #12
    bhi keys_done
    b keys_step

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
/* 1.24: the pages follow the audio chain: modulation (MOD rt rS) before
 * the effect (FX dt Fb); mode numbers unchanged, order from mode_order. */
mode_next:
    push {r4, lr}
    movw r4, #0x3F00
    ldrb r0, [r4, #2]
    bl mode_pos
    adds r0, #1
    cmp r0, #21
    it hs
    movhs r0, #0
    b mode_from_pos
mode_prev:
    push {r4, lr}
    movw r4, #0x3F00
    ldrb r0, [r4, #2]
    bl mode_pos
    cmp r0, #0
    it eq
    moveq r0, #21
    subs r0, #1
mode_from_pos:
    adr r1, mode_order
    ldrb r0, [r1, r0]
mode_store:
    strb r0, [r4, #2]
    movs r0, #0
    strb r0, [r4, #3]
    movw r12, #0x3980
    strb r0, [r12, #0x21]
    bl render
    pop {r4, pc}
/* r0 = mode -> r0 = its position in the page order */
mode_pos:
    adr r1, mode_order
    movs r2, #0
mode_pos_loop:
    ldrb r3, [r1, r2]
    cmp r3, r0
    beq mode_pos_found
    adds r2, #1
    cmp r2, #21
    blo mode_pos_loop
    movs r2, #0
mode_pos_found:
    mov r0, r2
    bx lr
    .align 2
mode_order:
    /* 1.29: FL (21) and LF (22) left the pages: filter and LFOs are in EDIT */
    .byte 0, 1, 2, 3, 4, 5, 6, 10, 11, 12, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20, 0
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
    /* 1.26: FUNC + TRANSPOSE (1) = cutoff, FUNC + VELOCITY (3) = resonance
     * (panel only, r2 = 0; the native handler is skipped) */
    cbnz r2, pa_korg
    cmp r0, #1
    it ne
    cmpne r0, #3
    bne pa_korg
    push {r0, r1, r2, r3, r4, lr}
    ldr r12, =0x0020FA61
    blx r12
    cmp r0, #0
    pop {r0, r1, r2, r3, r4, lr}
    bne filt_knob
pa_korg:
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
    bl ext_capture
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
    cmp r5, #21
    bhs adc_filter
    cmp r5, #18
    bhs adc_multi
    cmp r5, #17
    bhs adc_chain
    cmp r5, #15
    bhs adc_rat
    cmp r5, #13
    bhs adc_seqx
    cmp r5, #10
    bhs adc_mod
    movw r6, #0x3F80
    cmp r5, #8
    beq adc_dt
    bhi adc_fb
    movs r1, #2
    bl adc_map
    strb r0, [r6]
    /* the effect type is saved in the pattern (PRB3, steps 13-14) */
    movs r1, #0
    bl set_fxmod
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
    /* 1.24: LOFI feedback up to 120 (self-oscillation), DELAY 100 */
    ldrb r1, [r6]
    cmp r1, #2
    ite eq
    moveq r1, #120
    movne r1, #100
    bl adc_map
    strb r0, [r6, #6]
    b adc_render

/* 1.22 modulation pages. Type: 0 CHORUS 1 PHASER 2 TREMOLO (saved in the
 * pattern, PRB3 steps 15-16). rt: SYNC division 0..6 or LIBERO slider (the
 * phase increment is computed here). rS / Fo: resonance (phaser) or shape
 * (tremolo) 0..100. */
adc_mod:
    movw r6, #0x3B80
    cmp r5, #11
    beq adc_rt
    bhi adc_param
    movs r1, #2
    bl adc_map
    strb r0, [r6]
    movs r1, #2
    bl set_fxmod
    b adc_render
adc_rt:
    ldrb r1, [r6, #2]
    cbz r1, adc_rt_free
    movs r1, #6
    bl adc_map
    strb r0, [r6, #4]
    b adc_render
adc_rt_free:
    strb r0, [r6, #5]
    bl rt_inc
    b adc_render
adc_param:
    movs r1, #100
    bl adc_map
    ldrb r1, [r6]
    cmp r1, #1
    beq adc_res
    cmp r1, #2
    bne adc_render
    strb r0, [r6, #7]
    b adc_render
adc_res:
    strb r0, [r6, #6]
    bl set_res
    b adc_render

/* 1.23 resonance 0..100 -> feedback Q15 (x301, max 0.92) at +40 and the
 * input gain 1 - feedback / 2 at +42. r0 = resonance. */
set_res:
    movw r12, #0x3B80
    movw r1, #301
    mul r0, r0, r1
    strh r0, [r12, #0x40]
    movw r1, #32767
    sub r0, r1, r0, lsr #1
    strh r0, [r12, #0x42]
    bx lr

/* 1.24 rA (15): selected step 1, 2, 3, 4 hits, 2-4 with probability 25 50
 * 75 100 (13 slider positions); ti (16): selected step -36..+36 ticks, or
 * the swing of the pattern 0..25 (= 50..75 %). Saved in the pattern. */
adc_rat:
    movw r6, #0x3980
    movw r12, #0x3F00
    ldrb r3, [r12, #1]
    cmp r5, #16
    beq adc_ti
    movs r1, #12
    bl adc_map
    ldrb r2, [r6, r3]
    and r2, r2, #0x30
    cbz r0, adc_rat_store
    subs r0, #1
    lsrs r1, r0, #2
    adds r1, #1
    and r0, r0, #3
    rsb r0, r0, #3
    orr r2, r2, r1
    orr r2, r2, r0, lsl #2
adc_rat_store:
    strb r2, [r6, r3]
    bl save_seq2
    b adc_render
adc_ti:
    ldrb r1, [r6, #0x21]
    cbnz r1, adc_swing
    movs r1, #72
    bl adc_map
    subs r0, #36
    add r3, r3, #0x10
    strb r0, [r6, r3]
    bl save_seq2
    b adc_render
adc_swing:
    movs r1, #25
    bl adc_map
    strb r0, [r6, #0x20]
    bl save_seq2
    b adc_render

/* 1.24 pattern record (35 bytes in step 2..10 bytes 108..111, not used by
 * the Korg firmware): A5, swing, ratchet x16, microtiming x16, check =
 * xor of the 34 bytes ^ 5A. r0 = record byte -> r0 = its address. */
rec_addr:
    lsrs r1, r0, #2
    and r0, r0, #3
    add r0, r0, r1, lsl #7
    sub r0, r0, r1, lsl #4
    ldr r1, =0x2001E258
    add r0, r0, r1
    bx lr

save_seq2:
    push {r4, r5, r6, lr}
    movw r4, #0x3980
    movs r5, #0
    movs r6, #0x5A
save_seq2_loop:
    cmp r5, #34
    beq save_seq2_chk
    cmp r5, #1
    blo save_seq2_tag
    beq save_seq2_swing
    sub r0, r5, #2
    ldrb r2, [r4, r0]
    b save_seq2_put
save_seq2_tag:
    movs r2, #0xA5
    b save_seq2_put
save_seq2_swing:
    ldrb r2, [r4, #0x20]
save_seq2_put:
    eor r6, r6, r2
    mov r0, r5
    bl rec_addr
    strb r2, [r0]
    adds r5, #1
    b save_seq2_loop
save_seq2_chk:
    mov r0, r5
    bl rec_addr
    strb r6, [r0]
    pop {r4, r5, r6, pc}

/* Pattern load: ratchet, microtiming and swing from the record; none or an
 * invalid one = all off. */
load_seq2:
    push {r4, r5, r6, lr}
    movw r4, #0x3980
    movs r0, #0
    bl rec_addr
    ldrb r2, [r0]
    cmp r2, #0xA5
    bne load_seq2_clear
    movs r5, #0
    movs r6, #0x5A
load_seq2_xor:
    mov r0, r5
    bl rec_addr
    ldrb r2, [r0]
    eor r6, r6, r2
    adds r5, #1
    cmp r5, #34
    blo load_seq2_xor
    mov r0, r5
    bl rec_addr
    ldrb r2, [r0]
    cmp r2, r6
    bne load_seq2_clear
    movs r0, #1
    bl rec_addr
    ldrb r2, [r0]
    cmp r2, #25
    bhi load_seq2_clear
    strb r2, [r4, #0x20]
    movs r5, #2
load_seq2_copy:
    mov r0, r5
    bl rec_addr
    ldrsb r2, [r0]
    cmp r5, #18
    bhs load_seq2_mic
    cmp r2, #0
    blt load_seq2_clear
    ubfx r3, r2, #4, #4
    cmp r3, #2
    bhi load_seq2_clear
    b load_seq2_store
load_seq2_mic:
    cmp r2, #36
    bgt load_seq2_clear
    cmn r2, #36
    blt load_seq2_clear
load_seq2_store:
    sub r0, r5, #2
    strb r2, [r4, r0]
    adds r5, #1
    cmp r5, #34
    blo load_seq2_copy
    pop {r4, r5, r6, pc}
load_seq2_clear:
    movs r0, #0
    movs r1, #0
load_seq2_zero:
    strb r1, [r4, r0]
    adds r0, #1
    cmp r0, #0x22
    blo load_seq2_zero
    pop {r4, r5, r6, pc}
    .align 2
    .ltorg

/* 1.23 dr (13): direction 0 AVANTI 1 INDIETRO 2 PENDOLO 3 CASO.
 * Mu (14): mutation 0..100. Both saved in the pattern (save_seqx). */
adc_seqx:
    movw r6, #0x3F30
    cmp r5, #13
    bne adc_mu
    movs r1, #3
    bl adc_map
    strb r0, [r6, #4]
    bl save_seqx
    b adc_render
adc_mu:
    movs r1, #100
    bl adc_map
    strb r0, [r6, #5]
    bl save_seqx
    b adc_render

/* Direction, mutation and range -> pattern in use, step 1 bytes 108..111
 * (pattern bytes 188..191, not used by the Korg firmware): tag 0xA4,
 * direction | range << 2, mutation, check = xor of the three ^ 0x5A. */
save_seqx:
    movw r12, #0x3F30
    ldrb r0, [r12, #4]
    ldrb r1, [r12, #6]
    orr r0, r0, r1, lsl #2
    ldrb r1, [r12, #5]
    ldr r2, =0x2001E1E8
    movs r3, #0xA4
    strb r3, [r2]
    strb r0, [r2, #1]
    strb r1, [r2, #2]
    eor r3, r3, r0
    eor r3, r3, r1
    eor r3, r3, #0x5A
    strb r3, [r2, #3]
    bx lr

/* Pattern load: direction, mutation, range from the block (defaults
 * without a valid one); mutated notes back to the pattern's. */
load_seqx:
    movw r12, #0x3F30
    movs r0, #0
    movs r1, #0
    movs r2, #0
    ldr r3, =0x2001E1E8
    push {r4, r5}
    ldrb r4, [r3]
    cmp r4, #0xA4
    bne load_seqx_set
    ldrb r5, [r3, #1]
    eor r4, r4, r5
    ldrb r5, [r3, #2]
    eor r4, r4, r5
    eor r4, r4, #0x5A
    ldrb r5, [r3, #3]
    cmp r4, r5
    bne load_seqx_set
    ldrb r5, [r3, #1]
    cmp r5, #8
    bhs load_seqx_set
    ldrb r4, [r3, #2]
    cmp r4, #100
    bhi load_seqx_set
    and r0, r5, #3
    lsr r2, r5, #2
    mov r1, r4
load_seqx_set:
    strb r0, [r12, #4]
    strb r1, [r12, #5]
    strb r2, [r12, #6]
    movs r0, #0
    add r12, r12, #0x40
    str r0, [r12]
    str r0, [r12, #4]
    str r0, [r12, #8]
    str r0, [r12, #12]
    pop {r4, r5}
    bx lr

/* LIBERO slider (state +05) -> phase increment (+10) = 2^32 / (50 x period
 * in ms), period table rt_ms. */
rt_inc:
    movw r12, #0x3B80
    ldrb r0, [r12, #5]
    adr r1, rt_ms
    ldrh r0, [r1, r0, lsl #1]
    ldr r1, =85899346
    udiv r1, r1, r0
    str r1, [r12, #0x10]
    bx lr

/* r0 = value 0..3, r1 = 0 (effect type) or 2 (modulation type): the 4-bit
 * field of steps 13-16 holds both. */
set_fxmod:
    /* 1.28: the effect types belong to the program, not to the pattern */
    bx lr
    push {r4, r5, r6, lr}
    mov r4, r0
    mov r5, r1
    ldr r0, =0x2001E88C
    movs r1, #12
    bl block_bits
    movs r2, #3
    lsl r2, r2, r5
    bic r0, r0, r2
    lsl r4, r4, r5
    orr r0, r0, r4
    movs r1, #12
    bl set_bits
    pop {r4, r5, r6, pc}

/* 1.29 STROMBOLI block of every pattern (52 bytes), in the free space of
 * the pattern's journal sector (Korg uses +0x010..+0x78F, the block goes
 * to +0x800). Layout:
 *   0 'P'  1 version 1  2..6 FX (0x3F80 +0 +2 +4 +5 +6)
 *   7..14 MOD (0x3B80 +0 +2 +3 +4 +5 +6 +7 +9)
 *   15 flags: bit 0 cutoff motion, bit 1 resonance motion, bit 7 types
 *      from PRB3 (patterns of 1.21-1.27, block never written)
 *   16..31 cutoff per step  32..47 resonance per step  48..50 0
 *   51 check = (sum of bytes 0..50) ^ 0x5A */
.equ PAT_N, 52
.equ pat_live, 0x2001B040
.equ pat_bank, 0x2001B074
.equ SEQSTATE, 0x20003F8C

/* r0 = pattern 0..15 -> r0 = its block in the bank */
pat_bank_of:
    movs r1, #PAT_N
    ldr r2, =pat_bank
    mla r0, r0, r1, r2
    bx lr

/* r0 = block -> r0 = check byte */
pat_check:
    movs r1, #0
    movs r2, #0
pck_loop:
    ldrb r3, [r0, r2]
    add r1, r1, r3
    adds r2, #1
    cmp r2, #(PAT_N-1)
    blo pck_loop
    and r0, r1, #0xFF
    eor r0, r0, #0x5A
    bx lr

/* r0 = block: Z set if valid */
pat_valid:
    push {r4, lr}
    mov r4, r0
    ldrb r1, [r4]
    cmp r1, #0x50
    bne pv_out
    ldrb r1, [r4, #1]
    cmp r1, #1
    bne pv_out
    bl pat_check
    ldrb r1, [r4, #(PAT_N-1)]
    cmp r0, r1
pv_out:
    pop {r4, pc}

/* After every pattern load (flash load_fx, r0 = pattern): its block ->
 * live block -> effect state. */
load_types:
    push {r4, lr}
    cmp r0, #16
    bhs lt_apply
    bl pat_bank_of
    mov r1, r0
    ldr r0, =pat_live
    movs r2, #PAT_N
    bl ext_copy
lt_apply:
    bl pat_apply
    bl load_seqx
    bl load_seq2
    bl load_multi
    pop {r4, pc}

/* live block -> effect state */
pat_apply:
    push {r4, r5, r6, lr}
    ldr r4, =pat_live
    adr r5, pat_map
    movs r2, #2
pap_loop:
    sub r3, r2, #2
    ldrh r3, [r5, r3, lsl #1]
    ldrb r1, [r4, r2]
    strb r1, [r3]
    adds r2, #1
    cmp r2, #15
    blo pap_loop
    ldrb r0, [r4, #15]
    tst r0, #0x80
    beq pap_set
    /* block never written: types from PRB3 as in 1.21-1.27 (none =
     * REVRB and CHORUS, as in the Korg firmware) */
    ldr r0, =0x2001E88C
    movs r1, #12
    bl block_bits
    and r1, r0, #3
    cmp r1, #3
    it eq
    moveq r1, #0
    movw r2, #0x3F80
    strb r1, [r2]
    ubfx r1, r0, #2, #2
    cmp r1, #3
    it eq
    moveq r1, #0
    movw r2, #0x3B80
    strb r1, [r2]
pap_set:
    bl rt_inc
    movw r12, #0x3B80
    ldrb r0, [r12, #6]
    bl set_res
    pop {r4, r5, r6, pc}

/* effect state -> live block (FUNC + EDIT pages, FUNC + 3 / 4) */
pat_capture:
    ldr r0, =pat_live
    adr r1, pat_map
    movs r2, #2
pcp_loop:
    sub r3, r2, #2
    ldrh r3, [r1, r3, lsl #1]
    ldrb r3, [r3]
    strb r3, [r0, r2]
    adds r2, #1
    cmp r2, #15
    blo pcp_loop
    ldrb r3, [r0, #15]
    bic r3, r3, #0x80
    strb r3, [r0, #15]
    bx lr

/* r0 = pattern: live block differs from the bank one? -> r0 (flash
 * save_if_modified, CR chain) */
pat_dirty:
    push {r4, lr}
    cmp r0, #16
    bhs pdy_no
    bl pat_bank_of
    ldr r1, =pat_live
    movs r2, #0
pdy_loop:
    ldrb r3, [r0, r2]
    ldrb r4, [r1, r2]
    cmp r3, r4
    bne pdy_yes
    adds r2, #1
    cmp r2, #(PAT_N-1)
    blo pdy_loop
pdy_no:
    movs r0, #0
    pop {r4, pc}
pdy_yes:
    movs r0, #1
    pop {r4, pc}

/* Native pattern WRITE (veneer 0x0020FA90, was 0x200134ED; r0 = pattern
 * in use, r1 = slot): then the live block -> the slot's block, sealed */
pat_write:
    push {r1, r4, r5, lr}
    mov r4, r1
    ldr r12, =0x200134ED
    blx r12
    mov r5, r0
    cmp r4, #16
    bhs pw_out
    ldr r0, =pat_live
    bl pat_check
    ldr r1, =pat_live
    strb r0, [r1, #(PAT_N-1)]
    mov r0, r4
    bl pat_bank_of
    ldr r1, =pat_live
    movs r2, #PAT_N
    bl ext_copy
pw_out:
    mov r0, r5
    pop {r1, r4, r5, pc}

/* 1.29 ALGORITHM knob with notes sounding: Korg sets the kernel of the 6
 * voices again (BL at 0x20014B10 in place of 0x20015190, r0 = algorithm,
 * r4 = voice). In VA the voice keeps va_simple and only takes the new
 * mode: a Korg FM kernel on VA records froze the instrument. */
alg_kernel:
    push {r4, lr}
    ldr r12, =0x20015191
    blx r12
    ldr r1, =LIVE
    ldrb r1, [r1, #110]
    tst r1, #0x80
    beq ak_out
    ldr r0, =0x200040BC+0x90
    mov r2, #0x270
    mla r0, r4, r2, r0
    ldr r1, =LIVE
    ldrb r1, [r1, #110]
    and r1, r1, #7
    str r1, [r0, #0x14]
    ldr r0, =va_simple
ak_out:
    pop {r4, pc}

/* Pattern dump received (SysEx, BL at 0x20014AC8 in place of 0x200134EC;
 * r0 = pattern, r1 = slot): the dump does not carry the block, so the
 * slot's block back to the defaults (types from the PRB3 bits). */
pat_sysex:
    push {r1, r4, r5, lr}
    mov r4, r1
    ldr r12, =0x200134ED
    blx r12
    mov r5, r0
    cmp r4, #16
    bhs psx_out
    mov r0, r4
    bl pat_bank_of
    adr r1, pat_defaults
    movs r2, #PAT_N
    bl ext_copy
psx_out:
    mov r0, r5
    pop {r1, r4, r5, pc}

/* Journal: pattern sector built by 0x20013A9A; its copy of the 1920 bytes
 * ends in this tail call (b.w at 0x20013ABC): r0 = sector + 0x10, r1 =
 * pattern in the RAM bank, r2 = 0x780. Then the block to +0x800. */
pat_sector:
    push {r0, r1, r4, lr}
    ldr r12, =0x20015421
    blx r12
    pop {r0, r1}
    ldr r2, =ROOT
    ldr r2, [r2]
    subs r1, r1, r2
    mov r2, #0x780
    udiv r1, r1, r2
    add r4, r0, #(0x800-0x10)
    mov r0, r1
    bl pat_bank_of
    mov r1, r0
    mov r0, r4
    movs r2, #PAT_N
    bl ext_copy
    pop {r4, pc}

/* Journal load, state 2 (BL at 0x200138D8 in place of 0x20014A88, pattern
 * [ROOT+0x99] from the sector buffer): then its block from +0x800 of the
 * same sector, checked; factory data or a bad block = defaults. */
pat_sector_load:
    push {r4, r5, r6, lr}
    ldr r12, =0x20014A89
    blx r12
    ldr r4, =ROOT
    ldrb r5, [r4, #0x99]
    mov r0, r5
    bl pat_bank_of
    mov r6, r0
    ldrb r0, [r4, #0x92]
    cbnz r0, psl_default
    ldr r1, =JOURNAL
    add r1, r1, r5, lsl #3
    ldrb r0, [r1, #0x20]
    cbz r0, psl_default
    ldrb r1, [r1, #0x21]
    adds r1, #0x40
    lsls r1, r1, #12
    add r1, r1, #0x800
    mov r0, r6
    movs r2, #PAT_N
    ldr r12, =0x20015219
    blx r12
    mov r0, r6
    bl pat_valid
    beq psl_out
psl_default:
    mov r0, r6
    adr r1, pat_defaults
    movs r2, #PAT_N
    bl ext_copy
psl_out:
    pop {r4, r5, r6, pc}

/* FUNC + 3 (veneer, was the Korg chorus switch 0x0020C88B): OFF -> CHORUS
 * -> PHASER -> TREMOLO -> OFF. FUNC + 4 (was the reverb switch
 * 0x0020C8B7): OFF -> REVERB -> DELAY -> LOFI -> OFF. */
rot_mod:
    push {r4, r5, r6, lr}
    movw r4, #0x3B80
    ldr r5, =0x0020C88B
    adr r6, rot_mod_text
    ldr r12, =0x002088B1
    b rot_go
rot_fx:
    push {r4, r5, r6, lr}
    movw r4, #0x3F80
    ldr r5, =0x0020C8B7
    adr r6, rot_fx_text
    ldr r12, =0x002088D9
rot_go:
    blx r12
    cbz r0, rot_on
    ldrb r0, [r4]
    cmp r0, #2
    bhs rot_off
    adds r0, #1
    strb r0, [r4]
    b rot_show
rot_off:
    movs r0, #0
    strb r0, [r4]
    blx r5
    bl pat_capture
    mov r0, r6
    bl show_text
    pop {r4, r5, r6, pc}
rot_on:
    strb r0, [r4]
    blx r5
rot_show:
    bl pat_capture
    ldrb r0, [r4]
    add r0, r0, #1
    add r0, r0, r0, lsl #3
    add r0, r0, r6
    bl show_text
    pop {r4, r5, r6, pc}
/* runtime address of block bytes 2..14 */
pat_map:
    .hword 0x3F80, 0x3F82, 0x3F84, 0x3F85, 0x3F86
    .hword 0x3B80, 0x3B82, 0x3B83, 0x3B84, 0x3B85, 0x3B86, 0x3B87, 0x3B89
rot_mod_text:
    .ascii "MOD   OFFCHORUS   PHASER   TREMOLO  "
rot_fx_text:
    .ascii "FX    OFFREVERB   DELAY    LOFI     "
    .align 2

/* Filter motion. r0 = 1 cutoff / 3 resonance, r1 = value: while the
 * sequencer plays in REC, the value of the step being played (0x3F3B);
 * the first one fills the whole pattern. */
pm_record:
    ldr r2, =SEQSTATE
    ldr r2, [r2]
    and r2, r2, #3
    cmp r2, #3
    it ne
    bxne lr
    push {r4, lr}
    ldr r2, =pat_live
    movs r3, #1
    add r12, r2, #16
    cmp r0, #1
    itt ne
    movne r3, #2
    addne r12, r12, #16
    ldrb r4, [r2, #15]
    tst r4, r3
    bne pmr_put
    orr r4, r4, r3
    strb r4, [r2, #15]
    movs r0, #15
pmr_fill:
    strb r1, [r12, r0]
    subs r0, #1
    bpl pmr_fill
pmr_put:
    movw r0, #0x3F3B
    ldrb r0, [r0]
    and r0, r0, #15
    strb r1, [r12, r0]
    pop {r4, pc}

/* r0 = step being played (fire): the recorded values to the filter */
pm_play:
    ldr r2, =pat_live
    ldrb r3, [r2, #15]
    tst r3, #3
    it eq
    bxeq lr
    and r0, r0, #15
    add r1, r2, r0
    movw r12, #0x3700
    tst r3, #1
    itt ne
    ldrbne r2, [r1, #16]
    strbne r2, [r12, #1]
    tst r3, #2
    itt ne
    ldrbne r2, [r1, #32]
    strbne r2, [r12, #2]
    bx lr

/* FUNC + 14 motion clear (veneer, was 0x0020A225): the filter motion too */
pm_clear:
    push {r4, lr}
    ldr r12, =0x0020A225
    blx r12
    ldr r1, =pat_live
    ldrb r2, [r1, #15]
    bic r2, r2, #3
    strb r2, [r1, #15]
    pop {r4, pc}

pat_defaults:
    .byte 0x50, 1, 0, 1, 7, 64, 50, 0, 0, 1, 4, 55, 50, 0, 1, 0x80
    .space 35
    .byte 0xE0
    .align 2
    .ltorg

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
    cmp r5, #21
    bhs render_filter
    cmp r5, #18
    bhs render_multi
    cmp r5, #17
    bhs render_chain
    cmp r5, #15
    bhs render_rat
    cmp r5, #13
    bhs render_seqx
    cmp r5, #10
    bhs render_mod
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
    ICALL fx_samples
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
/* 1.22: "CHORUS   " / "PHASER   " / "TREMOLO  "; "rt 1-4   " / "rt 2016ms"
 * ("rt --" with the chorus); "rS 030" (phaser) / "Fo 000" (tremolo). */
render_mod:
    movw r6, #0x3B80
    ldrb r7, [r6]
    cmp r7, #3
    it hs
    movhs r7, #0
    cmp r5, #11
    beq render_rt
    bhi render_param
    adr r0, mod_names
    add r0, r0, r7, lsl #3
    mov r1, r4
    movs r2, #7
    bl copy_text
    b render_out
render_rt:
    movs r0, #114
    strb r0, [r4]
    movs r0, #116
    strb r0, [r4, #1]
    cmp r7, #0
    beq render_mod_none
    ldrb r0, [r6, #2]
    cbz r0, render_rt_free
    ldrb r0, [r6, #4]
    cmp r0, #7
    it hs
    movhs r0, #0
    adr r1, rt_names
    add r0, r1, r0, lsl #2
    adds r1, r4, #3
    movs r2, #4
    bl copy_text
    b render_out
render_rt_free:
    ldrb r0, [r6, #5]
    adr r1, rt_ms
    ldrh r0, [r1, r0, lsl #1]
    movs r1, #10
    add r2, r4, #6
render_rt_digit:
    udiv r3, r0, r1
    mls r12, r3, r1, r0
    add r12, r12, #48
    strb r12, [r2], #-1
    mov r0, r3
    cmp r0, #0
    bne render_rt_digit
    movs r0, #109
    strb r0, [r4, #7]
    movs r0, #115
    strb r0, [r4, #8]
    b render_out
render_param:
    cmp r7, #2
    ite eq
    moveq r0, #70
    movne r0, #114
    strb r0, [r4]
    ite eq
    moveq r0, #111
    movne r0, #83
    strb r0, [r4, #1]
    cmp r7, #0
    beq render_mod_none
    cmp r7, #2
    ite eq
    ldrbeq r0, [r6, #7]
    ldrbne r0, [r6, #6]
    adds r1, r4, #3
    bl put3
    /* 1.23 phaser: stages 4 / 6 / 8 at the end ("rS 050  6") */
    cmp r7, #1
    bne render_out
    ldrb r0, [r6, #9]
    cmp r0, #3
    it hs
    movhs r0, #0
    lsls r0, r0, #1
    adds r0, #52
    strb r0, [r4, #8]
    b render_out
/* 1.24 rA "05 r2 75C" (step, hits, probability if < 100, shape P C S);
 * ti "05 ti-12" (step, ticks) or "SWING 58" (pattern swing %). */
render_rat:
    movw r6, #0x3980
    movw r12, #0x3F00
    ldrb r7, [r12, #1]
    cmp r5, #16
    beq render_ti
    adds r0, r7, #1
    mov r1, r4
    bl put2
    movs r0, #114
    strb r0, [r4, #3]
    ldrb r2, [r6, r7]
    and r0, r2, #3
    adds r0, #49
    strb r0, [r4, #4]
    ands r0, r2, #3
    beq render_out
    ubfx r0, r2, #2, #2
    cbz r0, render_rat_shape
    rsb r0, r0, #4
    movs r1, #25
    mul r0, r0, r1
    adds r1, r4, #6
    bl put2
render_rat_shape:
    ldrb r2, [r6, r7]
    ubfx r0, r2, #4, #2
    adr r1, ramp_chars
    ldrb r0, [r1, r0]
    strb r0, [r4, #8]
    b render_out
render_ti:
    ldrb r0, [r6, #0x21]
    cbnz r0, render_swing
    adds r0, r7, #1
    mov r1, r4
    bl put2
    movs r0, #116
    strb r0, [r4, #3]
    movs r0, #105
    strb r0, [r4, #4]
    add r7, r7, #0x10
    ldrsb r0, [r6, r7]
    cmp r0, #0
    bge render_ti_pos
    movs r1, #45
    strb r1, [r4, #5]
    rsbs r0, r0, #0
render_ti_pos:
    adds r1, r4, #6
    bl put2
    b render_out
render_swing:
    adr r0, swing_text
    mov r1, r4
    movs r2, #6
    bl copy_text
    ldrb r0, [r6, #0x20]
    adds r0, #50
    adds r1, r4, #6
    bl put2
    b render_out
    .align 2
ramp_chars:
    .ascii "PCS\0"
swing_text:
    .ascii "SWING \0\0"
/* 1.23 dr "dr AVANTI" / "dr INDIET" / "dr PENDOL" / "dr CASO", Mu "Mu 050  3" */
render_seqx:
    movw r6, #0x3F30
    cmp r5, #14
    beq render_mu
    movs r0, #100
    strb r0, [r4]
    movs r0, #114
    strb r0, [r4, #1]
    ldrb r0, [r6, #4]
    and r0, r0, #3
    adr r1, dir_names
    add r0, r1, r0, lsl #3
    adds r1, r4, #3
    movs r2, #6
    bl copy_text
    b render_out
render_mu:
    movs r0, #77
    strb r0, [r4]
    movs r0, #117
    strb r0, [r4, #1]
    ldrb r0, [r6, #5]
    adds r1, r4, #3
    bl put3
    ldrb r0, [r6, #6]
    cmp r0, #0
    ite eq
    moveq r0, #51
    movne r0, #55
    strb r0, [r4, #8]
    b render_out
    .align 2
dir_names:
    .ascii "AVANTI\0\0INDIET\0\0PENDOL\0\0CASO  \0\0"
render_mod_none:
    movs r0, #45
    strb r0, [r4, #3]
    strb r0, [r4, #4]
    b render_out
    .align 2
mod_names:
    .ascii "CHORUS \0PHASER \0TREMOLO\0"
rt_names:
    .ascii "1-161-8 1-4 1-2 1-1 2-1 4-1 "
rt_ms:
    .short 20000, 19183, 18399, 17647, 16926, 16234, 15571, 14935, 14325, 13739, 13178, 12639, 12123, 11628, 11153, 10697
    .short 10260, 9841, 9438, 9053, 8683, 8328, 7988, 7661, 7348, 7048, 6760, 6484, 6219, 5965, 5721, 5487
    .short 5263, 5048, 4842, 4644, 4454, 4272, 4098, 3930, 3770, 3616, 3468, 3326, 3190, 3060, 2935, 2815
    .short 2700, 2590, 2484, 2382, 2285, 2192, 2102, 2016, 1934, 1855, 1779, 1706, 1637, 1570, 1506, 1444
    .short 1385, 1328, 1274, 1222, 1172, 1124, 1078, 1034, 992, 951, 913, 875, 840, 805, 772, 741
    .short 710, 681, 654, 627, 601, 577, 553, 531, 509, 488, 468, 449, 431, 413, 396, 380
    .short 364, 350, 335, 322, 308, 296, 284, 272, 261, 250, 240, 230, 221, 212, 203, 195
    .short 187, 179, 172, 165, 158, 152, 146, 140, 134, 128, 123, 118, 113, 109, 104, 100
    .align 1

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
    /* 1.29: EDIT LED lit steadily on the pages */
    movs r0, #3
    movs r1, #0x20
    movs r2, #0
    ldr r12, =0x20014F71
    blx r12
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
    /* 1.29: EDIT LED (0x20) lit steadily on the FUNC + EDIT pages */
    cmp r1, #0x20
    itt eq
    moveq r0, #3
    moveq r2, #0
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

/* 1.29: Korg LED driver veneer (literal at 0x20014F74, was 0x002058D7;
 * r0 0 off / 3 on, r1 LED, r2 blink): EDIT LED (0x20) lit steadily on
 * the FUNC + EDIT pages */
led_filter:
    cmp r1, #0x20
    bne lf_go
    movw r12, #0x3F00
    ldrb r3, [r12]
    cmp r3, #1
    itt eq
    moveq r0, #3
    moveq r2, #0
lf_go:
    ldr r12, =0x002058D7
    bx r12
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
    /* 1.23 fix: with FUNC held the Korg firmware turns knob 7 into the
     * chorus level (r2 = 0): leave it to the native handler. */
    cbnz r2, arp_knob_go
    ldr r12, =0x0020FA61
    blx r12
    cbz r0, arp_knob_go
    pop {r0, r1, r2, r3, r4, lr}
    b adc_native
arp_knob_go:
    ldr r1, [sp, #4]
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
    bl mutate
    mov r0, r5
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
    bl rat_vel
    mov r0, r5
    mov r1, r6
    pop {r2, r3, r4, r5, r6, r7, r12, lr}
    strb.w r0, [r7, r4, lsl #2]
    bx lr
    .align 2
    .ltorg

/* 1.23 mutation (Turing style). r5 = note of the step being played
 * (in/out). At the first note of each played step, with probability Mu %
 * the step gets a new offset of -R..+R scale degrees (R = 3 or 7) from
 * its own note in the pattern (0 included); the offset stays until the
 * next mutation of that step or the next pattern load (Mu 0 = locked).
 * Chord notes move together. Scale and tonic of the SC / tn pages, also
 * with the scale off. Clobbers r0-r4, r7, r12. */
mutate:
    push {lr}
    movw r12, #0x3F30
    ldrb r0, [r12, #0xB]
    cmp r0, #16
    bhs mutate_done
    movw r1, #0x3980
    ldrb r1, [r1, #0x23]
    cbnz r1, mutate_apply
    ldrb r1, [r12, #0xA]
    cbz r1, mutate_apply
    movs r1, #0
    strb r1, [r12, #0xA]
    ldrb r7, [r12, #5]
    cbz r7, mutate_apply
    mov r4, r0
    movs r0, #100
    ldr r12, =0x002094A5
    blx r12
    cmp r0, r7
    bhs mutate_step
    movw r12, #0x3F30
    ldrb r1, [r12, #6]
    cmp r1, #0
    ite eq
    moveq r7, #3
    movne r7, #7
    lsls r0, r7, #1
    adds r0, #1
    ldr r12, =0x002094A5
    blx r12
    subs r0, r0, r7
    movw r12, #0x3F70
    strb r0, [r12, r4]
mutate_step:
    mov r0, r4
mutate_apply:
    movw r12, #0x3F70
    ldrsb r1, [r12, r0]
    cbz r1, mutate_done
    mov r0, r5
    bl scale_walk
    mov r5, r0
mutate_done:
    pop {pc}

/* r0 = note, r1 = scale degrees (signed): the note snapped up into the
 * scale of the SC / tn pages, then moved by r1 degrees (stops at 0..127). */
scale_walk:
    push {r4, r5, r6, r7, lr}
    movw r12, #0x3F30
    ldrb r2, [r12, #1]
    ldrb r3, [r12, #2]
    movw r4, #0xFFF
    cmp r2, #15
    bhs scale_walk_chrom
    cmp r3, #12
    bhs scale_walk_chrom
    movw r4, #0x1F70
    ldrh r4, [r4, r2, lsl #1]
    b scale_walk_go
scale_walk_chrom:
    movw r4, #0xFFF
    movs r3, #0
scale_walk_go:
    mov r5, r1
    bl sw_member
    cbnz r7, scale_walk_loop
    movs r6, #1
    bl sw_step
    cbnz r7, scale_walk_loop
    mov r6, #-1
    bl sw_step
scale_walk_loop:
    cmp r5, #0
    beq scale_walk_done
    ite gt
    movgt r6, #1
    movle r6, #-1
    sub r5, r5, r6
    bl sw_step
    cmp r7, #0
    bne scale_walk_loop
scale_walk_done:
    pop {r4, r5, r6, r7, pc}

/* r0 = note, r3 = tonic, r4 = scale mask: r7 = 1 if the note is in it. */
sw_member:
    add r7, r0, #132
    sub r7, r7, r3
    mov r12, #12
    udiv r12, r7, r12
    add r12, r12, r12, lsl #1
    sub r7, r7, r12, lsl #2
    lsr r7, r4, r7
    and r7, r7, #1
    bx lr

/* Move r0 by r6 (+-1) until it is in the scale: r7 = 1, or r7 = 0 and r0
 * unchanged at the end of the range. */
sw_step:
    push {lr}
    mov r1, r0
    movs r2, #12
sw_step_loop:
    add r0, r0, r6
    cmp r0, #127
    bhi sw_step_fail
    bl sw_member
    cbnz r7, sw_step_ok
    subs r2, #1
    bne sw_step_loop
sw_step_fail:
    mov r0, r1
    movs r7, #0
sw_step_ok:
    pop {pc}

/* 1.23 direction. The clock keeps counting 0..15 (loops, chains, motion
 * and conditions unchanged); the step routine and the step LED get the
 * step to play: AVANTI c, INDIETRO 15 - c, PENDOLO forward and backward on
 * alternate loops, CASO a random step. Always forward while recording.
 * One step per counter value (the LED call comes first in the clock tick).
 * State 0x3F34 direction, 0x3F37 ping-pong backward, 0x3F38 / 0x3F39
 * counter / step cached, 0x3F3A mutation decision pending, 0x3F3B step
 * being played. */
step_of:
    push {r4, lr}
    movw r4, #0x3F30
    ldrb r1, [r4, #8]
    cmp r1, r0
    bne step_of_new
    ldrb r0, [r4, #9]
    pop {r4, pc}
step_of_new:
    strb r0, [r4, #8]
    movs r1, #1
    strb r1, [r4, #0xA]
    ldr r1, =0x20003F8C
    ldrb r1, [r1]
    tst r1, #2
    bne step_of_store
    ldrb r1, [r4, #4]
    cmp r1, #1
    beq step_of_rev
    cmp r1, #2
    beq step_of_pp
    cmp r1, #3
    bne step_of_store
    movs r0, #16
    ldr r12, =0x002094A5
    blx r12
    b step_of_store
step_of_pp:
    cbnz r0, step_of_pp_dir
    ldrb r1, [r4, #7]
    eor r1, r1, #1
    strb r1, [r4, #7]
step_of_pp_dir:
    ldrb r1, [r4, #7]
    cbz r1, step_of_store
step_of_rev:
    rsb r0, r0, #15
step_of_store:
    and r0, r0, #15
    strb r0, [r4, #9]
    pop {r4, pc}

/* BL at 0x0020903E (clock -> step routine 0x0020B7BE, r0 = counter).
 * 1.24: a step played early (microtiming < 0) is not played again; a step
 * with microtiming / swing > 0 waits (seq_tick); otherwise it plays now.
 *
 * State 0x3980: +00..+0F ratchet per step (bits 0-1 hits - 1, 2-3
 * probability 100 75 50 25, 4-5 shape PARI CALA CRESCE), +10..+1F
 * microtiming per step (ticks, signed), +20 swing 0..25, +21 ti page on
 * swing, +22 counter of the step being played, +23 ratchet hit running,
 * +24 last step decision, +25/+26/+31 late step / tick / counter (FF =
 * none), +27 counter played early (FF), +28 hits left, +29 hits, +2A hit
 * index, +2B step, +2C ticks between hits, +2D timer, +2E shape, +30
 * look-ahead done, +32/+33/+34 next step / counter / early tick, +35 a
 * step fired in this tick (the ratchet gap starts on the next one). */
step_map:
    push {r4, r5, r6, lr}
    mov r5, r0
    movw r4, #0x3980
    movs r1, #0
    strb r1, [r4, #0x30]
    ldrb r1, [r4, #0x27]
    cmp r1, r5
    bne step_map_normal
    movs r1, #0xFF
    strb r1, [r4, #0x27]
    pop {r4, r5, r6, pc}
step_map_normal:
    movs r1, #0xFF
    strb r1, [r4, #0x27]
    strb r1, [r4, #0x25]
    movs r1, #0
    strb r1, [r4, #0x28]
    strb r1, [r4, #0x29]
    mov r0, r5
    bl step_of
    mov r6, r0
    mov r1, r5
    bl step_offset
    cmp r0, #0
    ble step_map_now
    strb r6, [r4, #0x25]
    strb r0, [r4, #0x26]
    strb r5, [r4, #0x31]
    pop {r4, r5, r6, pc}
step_map_now:
    mov r0, r6
    mov r1, r5
    movs r2, #72
    bl fire
    pop {r4, r5, r6, pc}

/* r0 = step, r1 = counter -> r0 = ticks of delay (< 0 early): microtiming
 * of the step + swing on the odd counters (2nd, 4th ... sixteenth: up to
 * 36 ticks = 75 %), limited to -36..+66; the first step of a loop never
 * early (the next pattern of a chain is loaded on the bar). */
step_offset:
    movw r12, #0x3990
    ldrsb r2, [r12, r0]
    tst r1, #1
    beq step_offset_lim
    ldrb r3, [r12, #0x10]
    movs r0, #36
    mul r3, r3, r0
    adds r3, #12
    movs r0, #25
    udiv r3, r3, r0
    add r2, r2, r3
step_offset_lim:
    cmp r2, #66
    it gt
    movgt r2, #66
    cmn r2, #36
    it lt
    mvnlt r2, #35
    cmp r1, #0
    bne step_offset_done
    cmp r2, #0
    it lt
    movlt r2, #0
step_offset_done:
    mov r0, r2
    bx lr

/* Play step r0 of counter r1 now; r2 = ticks left in the step (ratchet
 * spacing = r2 / hits). */
fire:
    push {r4, r5, r6, lr}
    movw r4, #0x3980
    mov r5, r0
    strb r1, [r4, #0x22]
    movs r3, #0
    strb r3, [r4, #0x28]
    strb r3, [r4, #0x29]
    strb r3, [r4, #0x2A]
    strb r3, [r4, #0x23]
    movw r12, #0x3F30
    strb r0, [r12, #0xB]
    ldrb r6, [r4, r5]
    and r3, r6, #3
    cbz r3, fire_go
    ubfx r1, r6, #2, #2
    cbz r1, fire_rat
    push {r1, r2, r3, r12}
    movs r0, #4
    ldr r12, =0x002094A5
    blx r12
    pop {r1, r2, r3, r12}
    cmp r0, r1
    blo fire_go
fire_rat:
    adds r3, #1
    strb r3, [r4, #0x29]
    udiv r0, r2, r3
    strb r0, [r4, #0x2C]
    strb r0, [r4, #0x2D]
    subs r3, #1
    strb r3, [r4, #0x28]
    strb r5, [r4, #0x2B]
    ubfx r1, r6, #4, #2
    strb r1, [r4, #0x2E]
    /* the tick that fired does not count for the first gap */
    movs r1, #1
    strb r1, [r4, #0x35]
fire_go:
    mov r0, r5
    bl pm_play
    mov r0, r5
    ldr r12, =0x0020B7BF
    blx r12
    ldrb r0, [r4, #0x24]
    cbnz r0, fire_played
    movs r0, #0
    strb r0, [r4, #0x28]
    strb r0, [r4, #0x29]
    pop {r4, r5, r6, pc}
fire_played:
    bl rat_gates
    pop {r4, r5, r6, pc}

/* With hits: the gates of the new notes scaled to the hit length. */
rat_gates:
    movw r12, #0x3980
    ldrb r3, [r12, #0x29]
    cmp r3, #2
    blo rat_gates_done
    ldrb r3, [r12, #0x2C]
    ldr r12, =0x20003DC4
    movs r2, #6
rat_gates_loop:
    ldrb r0, [r12, #2]
    cmp r0, #1
    bne rat_gates_next
    ldrb r0, [r12, #1]
    mul r0, r0, r3
    movs r1, #72
    udiv r0, r0, r1
    cmp r0, #1
    it lo
    movlo r0, #1
    strb r0, [r12, #1]
rat_gates_next:
    adds r12, #4
    subs r2, #1
    bne rat_gates_loop
rat_gates_done:
    bx lr

/* Next hit: release the notes of the step (gate end), play it again. */
rat_hit:
    push {r4, lr}
    movw r4, #0x3980
    ldr r12, =0x0020BB51
    blx r12
    movs r0, #1
    strb r0, [r4, #0x23]
    ldrb r0, [r4, #0x2A]
    adds r0, #1
    strb r0, [r4, #0x2A]
    ldrb r0, [r4, #0x2B]
    movw r12, #0x3F30
    strb r0, [r12, #0xB]
    ldr r12, =0x0020B7BF
    blx r12
    movs r0, #0
    strb r0, [r4, #0x23]
    bl rat_gates
    ldrb r0, [r4, #0x28]
    subs r0, #1
    strb r0, [r4, #0x28]
    ldrb r0, [r4, #0x2C]
    strb r0, [r4, #0x2D]
    pop {r4, pc}

/* Velocity of a hit (in seq_note, r6): CALA (n - k) / n, CRESCE (k + 1) / n. */
rat_vel:
    movw r12, #0x3980
    ldrb r0, [r12, #0x29]
    cmp r0, #2
    blo rat_vel_done
    ldrb r1, [r12, #0x2E]
    cbz r1, rat_vel_done
    ldrb r2, [r12, #0x2A]
    cmp r1, #1
    ite eq
    subeq r2, r0, r2
    addne r2, r2, #1
    mul r6, r6, r2
    udiv r6, r6, r0
    cmp r6, #1
    it lo
    movlo r6, #1
rat_vel_done:
    bx lr

/* BL at 0x00209096 instead of ADD.W r8, r8, #-1 (end of every clock tick
 * iteration; does the decrement). Late step, ratchet hits, look-ahead and
 * early step. Tick = CLOCK+0xC (0 = the step boundary just processed). */
seq_tick:
    push {r0, r1, r2, r3, r4, r5, r6, lr}
    movw r4, #0x3980
    ldr r12, =0x200031A4
    ldrh r5, [r12]
    ldrb r0, [r4, #0x25]
    cmp r0, #0xFF
    beq seq_tick_rat
    ldrb r1, [r4, #0x26]
    cmp r5, r1
    blo seq_tick_rat
    movs r2, #0xFF
    strb r2, [r4, #0x25]
    ldrb r1, [r4, #0x31]
    rsb r2, r5, #72
    cmp r2, #1
    it lt
    movlt r2, #1
    bl fire
    movs r0, #0
    strb r0, [r4, #0x35]
    b seq_tick_look
seq_tick_rat:
    ldrb r0, [r4, #0x28]
    cbz r0, seq_tick_look
    ldrb r1, [r4, #0x35]
    cbz r1, seq_tick_count
    movs r1, #0
    strb r1, [r4, #0x35]
    b seq_tick_look
seq_tick_count:
    ldrb r1, [r4, #0x2D]
    subs r1, #1
    strb r1, [r4, #0x2D]
    bne seq_tick_look
    bl rat_hit
seq_tick_look:
    cmp r5, #36
    blo seq_tick_done
    ldrb r0, [r4, #0x30]
    cbnz r0, seq_tick_early
    ldrb r0, [r4, #0x25]
    cmp r0, #0xFF
    bne seq_tick_done
    movs r0, #1
    strb r0, [r4, #0x30]
    ldr r12, =0x200031A3
    ldrsb r0, [r12]
    adds r0, #1
    and r0, r0, #15
    cbz r0, seq_tick_nolook
    strb r0, [r4, #0x33]
    bl step_of
    strb r0, [r4, #0x32]
    ldrb r1, [r4, #0x33]
    bl step_offset
    cmp r0, #0
    bge seq_tick_nolook
    adds r0, #72
    strb r0, [r4, #0x34]
    b seq_tick_check
seq_tick_nolook:
    movs r0, #0xFF
    strb r0, [r4, #0x32]
    b seq_tick_done
seq_tick_early:
    ldrb r0, [r4, #0x32]
    cmp r0, #0xFF
    beq seq_tick_done
seq_tick_check:
    ldrb r1, [r4, #0x34]
    cmp r5, r1
    blo seq_tick_done
    ldrb r0, [r4, #0x32]
    movs r1, #0xFF
    strb r1, [r4, #0x32]
    ldrb r1, [r4, #0x33]
    strb r1, [r4, #0x27]
    push {r0, r1}
    ldr r12, =0x0020BB51
    blx r12
    pop {r0, r1}
    movs r2, #72
    bl fire
    movs r0, #0
    strb r0, [r4, #0x35]
seq_tick_done:
    pop {r0, r1, r2, r3, r4, r5, r6, lr}
    sub r8, r8, #1
    bx lr

/* BL at 0x00208E0C (step boundary: release of the notes of the step):
 * not when the next step was already played early. */
bnd_release:
    movw r12, #0x3980
    ldrb r0, [r12, #0x27]
    cmp r0, #0xFF
    it ne
    bxne lr
    ldr r12, =0x0020BB51
    bx r12

/* BL at 0x00208E42 (clock -> step LED 0x0020FC10, r0 = counter). */
led_map:
    push {lr}
    bl step_of
    pop {lr}
    ldr r12, =0x0020FC11
    bx r12
    .align 2
    .ltorg

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
    /* 1.22: sixteenths since the transport start (modulation SYNC) */
    movw r3, #0x3B80
    ldr r1, [r3, #0x3C]
    adds r1, #1
    str r1, [r3, #0x3C]
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
    ldr r2, [r1]
    ldr r3, =0x524F4843
    cmp r2, r3
    beq mod_label
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
/* 1.22: "CHORS nnn" -> "PHASE nnn" / "TREMO nnn" */
mod_label:
    ldrb r2, [r1, #4]
    cmp r2, #83
    bne fx_label_done
    movw r12, #0x3B80
    ldrb r0, [r12]
    subs r3, r0, #1
    cmp r3, #2
    bhs fx_label_done
    /* 1.24: own copy of the names (mod_names is out of ADR range here) */
    adr r2, mod_label_names
    add r0, r2, r0, lsl #3
    subs r0, #8
    movs r2, #5
    b copy_text
    .align 2
mod_label_names:
    .ascii "PHASE\0\0\0TREMO\0\0\0"

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
    /* 1.29: and its STROMBOLI block (effects, filter motion) */
    mov r0, r5
    bl pat_bank_of
    mov r1, r0
    ldr r0, =pat_live
    movs r2, #PAT_N
    bl ext_copy
    bl pat_apply
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


/* ================================================================ */
/* 1.25 MULTI: three parts. A is the live program (knobs, edit, motion);
 * B and C are programs of the internal bank. Each part has a keyboard zone,
 * a velocity zone with an optional fade, an octave, a pan, a level and a
 * limit of voices. A note starts one voice for every part whose zones hold
 * it: zones side by side = split, zones that overlap = layer. With the
 * channel switch on, MIDI IN plays A on the channel of the volca and B, C
 * on the next two (channel 10 is skipped), each over the whole keyboard.
 * Modulation wheel and channel aftertouch raise the LFO depth of the voices.
 * Saved in the pattern (bytes 108..111 of steps 11..16, not used by the Korg
 * firmware): A7, 21 bytes of bit stream (per part the fields with
 * multi_bits bits each, LSB first, then the channel switch), check = xor of
 * the 22 bytes ^ 5A. The record of the first 1.25 build (A6, six bytes per
 * part) is still read. No record = everything off.
 *
 * State MULTI (ITCM 0x3900), 16 bytes per part (A +00, B +10, C +20):
 *   +0 program 0 OFF / 1..64 (not used for A)   +1 low note   +2 high note
 *   +3 octave 0..6 (3 = none)   +4 pan 0..14 (7 = centre)   +5 level 0..100
 *   +6 voices 0 (free) / 1..6   +8 low velocity   +9 high velocity
 *   +10 fade 0..7 (multi_fades)
 *   +30 active        +32 part of each DSP voice (6)
 *   +38 channel switch   +39 forced part + 1 (MIDI)   +3A direct start (MIDI)
 *   +3B parts of the note being started   +3C those parts (3)
 *   +40 their gain (3 x 16 bit: level x fade, 25500 = full)
 *   +48 gain of each DSP voice (6 x 16 bit)
 *   +54 modulation wheel per part (3)   +57 aftertouch per part (3)
 *   +5A LFO pitch depth, +60 amplitude depth, +66 pitch sensitivity of the
 *       program of each DSP voice (6 each)
 *
 * Native code: 0x00209574 (source, note, velocity) gives a note [VM + 8]
 * DSP voices (1, or 2 / 3 with UNISON) out of six records (VREC: +0 time,
 * +4 state 0 free 1 on 5 releasing, +5 note, +0x18 = FF at every
 * allocation) and starts each one with 0x0020E814 (voice, pitch, velocity,
 * pan); 0x002093FE does the same for the arpeggiator; 0x00209870 (source,
 * note) releases the records of a note. 0x0020E6DC builds the program of
 * the voice with 0x0020E518 (destination, program, macro knobs) at every
 * start, sets the left and right gain of the voice (+0x38, +0x3C) from the
 * pan and calls 0x0020DF14, which writes the LFO depths of the program into
 * the voice (+0x10 pitch sensitivity, +0x11 pitch depth, +0x12 amplitude
 * depth), read by the rendering at every sample. */
.equ MULTI, 0x3900
.equ M_ACTIVE, 0x30
.equ M_PART, 0x32
.equ M_CHAN, 0x38
.equ M_FORCE, 0x39
.equ M_DIRECT, 0x3A
.equ M_N, 0x3B
.equ M_CUR, 0x3C
.equ M_CURGAIN, 0x40
.equ M_GAIN, 0x48
.equ M_WHEEL, 0x54
.equ M_TOUCH, 0x57
.equ M_PMD, 0x5A
.equ M_AMD, 0x60
.equ M_PMS, 0x66
.equ VM, 0x200031C8
.equ VREC, 0x2000330C
.equ VOICES, 0x200040BC

/* r0 = part record, r2 = velocity (inside the velocity zone): r0 = fade
 * 0..255. With a fade width W the part comes in over W velocities above its
 * low velocity (when that is above 1) and goes out over W below its high
 * velocity (when that is below 127): x = distance from the nearest such
 * edge, gain = x (2W - x) / W^2 (close to equal power). Clobbers r1, r3. */
multi_fade:
    push {r4, r5, lr}
    ldrb r3, [r0, #10]
    adr r1, multi_fades
    ldrb r4, [r1, r3]
    movs r5, #255
    cmp r4, #0
    beq mf_done
    mov r3, r4
    ldrb r1, [r0, #8]
    cmp r1, #1
    bls mf_high
    subs r1, r2, r1
    cmp r1, r3
    it lo
    movlo r3, r1
mf_high:
    ldrb r1, [r0, #9]
    cmp r1, #127
    bhs mf_curve
    subs r1, r1, r2
    cmp r1, r3
    it lo
    movlo r3, r1
mf_curve:
    cmp r3, r4
    bhs mf_done
    rsb r1, r3, r4, lsl #1
    mul r1, r1, r3
    mul r1, r1, r5
    mul r4, r4, r4
    udiv r5, r1, r4
mf_done:
    mov r0, r5
    pop {r4, r5, pc}

/* r1 = note, r2 = velocity: the parts that play the note, in order, with
 * their gain, into the state; returns r0 = how many. A part plays when it is
 * on (A always, B / C with a program), the note is in its keyboard zone (not
 * checked for the part forced by its MIDI channel, which is then the only
 * one), the velocity is in its velocity zone and its fade is not zero. */
multi_match:
    push {r4, r5, r6, r7, r8, lr}
    movw r4, #MULTI
    mov r8, r4
    movs r5, #0
    movs r6, #0
    ldrb r7, [r4, #M_FORCE]
mm_loop:
    cmp r7, #0
    beq mm_zone
    subs r0, r7, #1
    cmp r0, r5
    bne mm_next
    b mm_on
mm_zone:
    ldrb r3, [r4, #1]
    cmp r1, r3
    blo mm_next
    ldrb r3, [r4, #2]
    cmp r1, r3
    bhi mm_next
mm_on:
    cmp r5, #0
    beq mm_velocity
    ldrb r3, [r4]
    cmp r3, #0
    beq mm_next
mm_velocity:
    ldrb r3, [r4, #8]
    cmp r2, r3
    blo mm_next
    ldrb r3, [r4, #9]
    cmp r2, r3
    bhi mm_next
    mov r0, r4
    push {r1}
    bl multi_fade
    pop {r1}
    cmp r0, #0
    beq mm_next
    ldrb r3, [r4, #5]
    mul r0, r0, r3
    add r3, r8, r6
    strb r5, [r3, #M_CUR]
    add r3, r8, r6, lsl #1
    strh r0, [r3, #M_CURGAIN]
    adds r6, #1
mm_next:
    adds r4, #16
    adds r5, #1
    cmp r5, #3
    blo mm_loop
    strb r6, [r8, #M_N]
    mov r0, r6
    pop {r4, r5, r6, r7, r8, pc}

/* Every part of the note being started that has a limit of voices and
 * already sounds that many releases its oldest one (native release
 * 0x002094E6, record = releasing, as a note-off does), so a part never takes
 * more than its voices: limits that add up to six are reserved voices. */
multi_limit:
    push {r4, r5, r6, r7, r8, r9, r10, lr}
    movw r8, #MULTI
    movs r7, #0
ml_part:
    ldrb r0, [r8, #M_N]
    cmp r7, r0
    bhs ml_done
    add r0, r8, r7
    ldrb r6, [r0, #M_CUR]
    add r3, r8, r6, lsl #4
    ldrb r5, [r3, #6]
    cmp r5, #0
    beq ml_next
ml_again:
    ldr r1, =VREC
    movs r2, #0
    movs r3, #0
    mov r4, #-1
    mov r9, #-1
ml_loop:
    ldrb r0, [r1, #4]
    cmp r0, #1
    bne ml_skip
    add r0, r8, r2
    ldrb r0, [r0, #M_PART]
    cmp r0, r6
    bne ml_skip
    adds r3, #1
    ldr r0, [r1]
    cmp r0, r9
    bhs ml_skip
    mov r9, r0
    mov r4, r2
ml_skip:
    adds r1, #0x34
    adds r2, #1
    cmp r2, #6
    blo ml_loop
    cmp r3, r5
    blo ml_next
    cmp r4, #0
    blt ml_next
    movs r0, #1
    lsls r0, r4
    ldr r12, =0x002094E7
    blx r12
    ldr r1, =VREC
    movs r0, #0x34
    mla r1, r0, r4, r1
    movs r0, #5
    strb r0, [r1, #4]
    b ml_again
ml_next:
    adds r7, #1
    b ml_part
ml_done:
    pop {r4, r5, r6, r7, r8, r9, r10, pc}

/* r0 = voices wanted: while fewer records are free or releasing, the
 * oldest sounding one is marked as releasing, so the native allocation
 * takes it (the voice restarts without a click, as in the Korg firmware). */
multi_steal:
    push {r4, r5, r6, lr}
    mov r4, r0
ms_again:
    ldr r1, =VREC
    movs r2, #0
    movs r3, #0
    movs r5, #0
    mov r6, #-1
ms_loop:
    ldrb r0, [r1, #4]
    cmp r0, #1
    beq ms_on
    adds r3, #1
    b ms_next
ms_on:
    ldr r0, [r1]
    cmp r0, r6
    bhs ms_next
    mov r6, r0
    mov r5, r1
ms_next:
    adds r1, #0x34
    adds r2, #1
    cmp r2, #6
    blo ms_loop
    cmp r3, r4
    bhs ms_done
    cmp r5, #0
    beq ms_done
    movs r0, #5
    strb r0, [r5, #4]
    b ms_again
ms_done:
    pop {r4, r5, r6, pc}

/* Entry of 0x00209574 (r0 source, r1 note, r2 velocity). */
multi_dsp_on:
    movw r12, #MULTI
    ldrb r12, [r12, #M_ACTIVE]
    cmp r12, #0
    beq mdo_body
    push {r0, r1, r2, r4, r5, lr}
    bl multi_match
    movs r4, r0
    beq multi_silent
    bl multi_limit
    ldr r5, =VM
    ldrb r0, [r5, #8]
    cmp r0, #1
    bne mdo_plain
    mov r0, r4
    bl multi_steal
    cmp r4, #1
    beq mdo_plain
    strb r4, [r5, #8]
    ldr r0, [sp]
    ldr r1, [sp, #4]
    ldr r2, [sp, #8]
    bl mdo_body
    movs r1, #1
    strb r1, [r5, #8]
    add sp, #12
    pop {r4, r5, pc}
mdo_plain:
    pop {r0, r1, r2, r4, r5, lr}
mdo_body:
    push.w {r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ldr r12, =0x00209579
    bx r12
/* a note that no part plays is silent */
multi_silent:
    movs r0, #0
    add sp, #12
    pop {r4, r5, pc}

/* Entry of 0x002093FE (r0 source, r1 pitch, r2 velocity; returns the mask
 * of the voices started). */
multi_arp_on:
    movw r12, #MULTI
    ldrb r12, [r12, #M_ACTIVE]
    cmp r12, #0
    beq mao_body
    push {r0, r1, r2, r4, r5, lr}
    adds r1, #0x80
    lsrs r1, r1, #8
    bl multi_match
    movs r4, r0
    beq multi_silent
    ldr r5, =VM
    ldrb r0, [r5, #8]
    cmp r0, #1
    bne mao_plain
    cmp r4, #1
    beq mao_plain
    strb r4, [r5, #8]
    ldr r0, [sp]
    ldr r1, [sp, #4]
    ldr r2, [sp, #8]
    bl mao_body
    movs r1, #1
    strb r1, [r5, #8]
    add sp, #12
    pop {r4, r5, pc}
mao_plain:
    pop {r0, r1, r2, r4, r5, lr}
mao_body:
    push.w {r0, r1, r2, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ldr r12, =0x00209403
    bx r12

/* BL at 0x00209746 (r0 voice, r1 pitch, r2 velocity, r3 pan; r6 = index of
 * the voice within the note, r8 = its record - 0x144) and at 0x00209488
 * (arpeggiator: r7 - 1 = index): the part and the gain of the voice, from
 * the parts of the note (UNISON voices beyond them take the first one). A
 * voice started by a part channel marks its record (+0x18 = D0 + part; the
 * native allocation sets FF again). */
multi_call_a:
    movw r12, #MULTI
    ldrb r12, [r12, #M_ACTIVE]
    cmp r12, #0
    beq mc_native
    push {r0, r1, r2, r3, r4, lr}
    mov r2, r6
    movs r4, #1
    b mc_common
multi_call_b:
    movw r12, #MULTI
    ldrb r12, [r12, #M_ACTIVE]
    cmp r12, #0
    beq mc_native
    push {r0, r1, r2, r3, r4, lr}
    subs r2, r7, #1
    movs r4, #0
mc_common:
    movw r12, #MULTI
    ldrb r3, [r12, #M_N]
    cmp r2, r3
    it hs
    movhs r2, #0
    add r3, r12, r2
    ldrb r1, [r3, #M_CUR]
    add r3, r12, r0
    strb r1, [r3, #M_PART]
    add r3, r12, r2, lsl #1
    ldrh r2, [r3, #M_CURGAIN]
    add r3, r12, r0, lsl #1
    strh r2, [r3, #M_GAIN]
    cmp r4, #0
    beq mc_done
    ldrb r3, [r12, #M_DIRECT]
    cmp r3, #0
    beq mc_done
    add r1, r1, #0xD0
    strb.w r1, [r8, #0x15C]
mc_done:
    pop {r0, r1, r2, r3, r4, lr}
mc_native:
    ldr r12, =0x0020E815
    bx r12

/* BL at 0x0020E6F0 instead of 0x0020E518 (r0 destination, r1 live program,
 * r2 macro knobs). r7 = voice, r5 = pitch, r4 = pan of the caller, changed
 * here for the part: octave into the pitch, pan, and for B / C the program
 * of the bank with the live EG knobs and every operator on. 0x0020E518
 * reads the algorithm (carrier mask) from the live program: the algorithm
 * of the part's program is put there while it runs. */
multi_patch:
    movw r12, #MULTI
    ldrb r3, [r12, #M_ACTIVE]
    cmp r3, #0
    beq mp_native
    push {r0, r1, r2, r6, r9, lr}
    add r3, r12, #M_PART
    ldrb r3, [r3, r7]
    cmp r3, #2
    it hi
    movhi r3, #0
    add r6, r12, r3, lsl #4
    ldrb r3, [r6, #3]
    subs r3, #3
    beq mp_pan
    movw r2, #0xC00
    mul r3, r3, r2
    adds r5, r5, r3
mp_low:
    cmp r5, #0
    bge mp_high
    add r5, r5, r2
    b mp_low
mp_high:
    cmp r5, #0x7F00
    ble mp_pan
    sub r5, r5, r2
    b mp_high
mp_pan:
    ldrb r3, [r6, #4]
    cmp r3, #7
    beq mp_prog
    add r3, r3, r3, lsl #3
    adds r4, r3, #1
mp_prog:
    cmp r6, r12
    beq mp_live
    ldrb r3, [r6]
    cmp r3, #0
    beq mp_live
    subs r3, #1
    ldr r1, =0x2001D090
    ldr r1, [r1]
    add r1, r1, r3, lsl #7
    ldr r2, [sp, #8]
    sub sp, #16
    mov r3, #0x01010101
    str r3, [sp, #4]
    str r3, [sp, #8]
    ldr r3, [r2]
    str r3, [sp]
    ldrb r3, [r2, #4]
    strb r3, [sp, #4]
    ldr r9, =0x20004F5C
    ldrb r3, [r9, #0x6E]
    str r3, [sp, #12]
    ldrb r2, [r1, #0x6E]
    strb r2, [r9, #0x6E]
    mov r2, sp
    ldr r0, [sp, #16]
    ldr r12, =0x0020E519
    blx r12
    ldr r3, [sp, #12]
    strb r3, [r9, #0x6E]
    add sp, #16
    pop {r0, r1, r2, r6, r9, pc}
mp_live:
    pop {r0, r1, r2, r6, r9, lr}
mp_native:
    ldr r12, =0x0020E519
    bx r12

/* r0 = DSP voice: its LFO depths = those of its program (kept at the start
 * of the voice) raised by the modulation wheel (pitch depth) and by the
 * aftertouch (pitch and amplitude depth) of its part. A program with no
 * pitch sensitivity gets that of PMS 3 while a controller is up. With both
 * controllers at zero the values of the program are written back. */
multi_ctrl_voice:
    push {r4, r5, r6, lr}
    movw r12, #MULTI
    add r4, r12, r0
    ldr r5, =VOICES
    mov r1, #624
    mla r5, r1, r0, r5
    ldrb r1, [r4, #M_PART]
    cmp r1, #2
    it hi
    movhi r1, #0
    add r1, r12, r1
    ldrb r2, [r1, #M_WHEEL]
    ldrb r3, [r1, #M_TOUCH]
    cmp r2, r3
    it lo
    movlo r2, r3
    ldrb r0, [r4, #M_PMD]
    add r0, r0, r2, lsl #1
    cmp r0, #255
    it hi
    movhi r0, #255
    strb r0, [r5, #0x11]
    ldrb r0, [r4, #M_PMS]
    cmp r2, #0
    beq mcv_pms
    cmp r0, #33
    it lo
    movlo r0, #33
mcv_pms:
    strb r0, [r5, #0x10]
    ldrb r0, [r4, #M_AMD]
    add r0, r0, r3, lsl #1
    cmp r0, #255
    it hi
    movhi r0, #255
    strb r0, [r5, #0x12]
    pop {r4, r5, r6, pc}

multi_ctrl_all:
    push {r4, lr}
    movs r4, #0
mca_loop:
    mov r0, r4
    bl multi_ctrl_voice
    adds r4, #1
    cmp r4, #6
    blo mca_loop
    pop {r4, pc}

/* BL at 0x0020E79E instead of 0x0020DF14 (four arguments and the voice on
 * the stack): after it, the LFO depths of the program are kept and the
 * controllers applied; with the parts active, the left and right gain of
 * the voice, just set from the pan, times the gain of the voice (level of
 * the part x velocity fade). */
multi_gain:
    push {r2, r3, r4, lr}
    ldr r4, [sp, #16]
    /* 1.27: wave of every operator, before the voice is started */
    push {r0, r1}
    mov r0, r1
    mov r1, r4
    bl wave_voice
    pop {r0, r1}
    ldr r2, [sp]
    ldr r3, [sp, #4]
    push {r4, r5}
    ldr r12, =0x0020DF15
    blx r12
    pop {r4, r5}
    ldr r0, =VOICES
    subs r0, r4, r0
    mov r1, #624
    udiv r0, r0, r1
    movw r12, #MULTI
    add r1, r12, r0
    ldrb r2, [r4, #0x11]
    strb r2, [r1, #M_PMD]
    ldrb r2, [r4, #0x12]
    strb r2, [r1, #M_AMD]
    ldrb r2, [r4, #0x10]
    strb r2, [r1, #M_PMS]
    ldrb r2, [r12, #M_ACTIVE]
    cmp r2, #0
    beq mg_ctrl
    add r1, r12, r0, lsl #1
    ldrh r2, [r1, #M_GAIN]
    movw r3, #25500
    cmp r2, r3
    bhs mg_ctrl
    ldr r1, [r4, #0x38]
    mul r1, r1, r2
    udiv r1, r1, r3
    str r1, [r4, #0x38]
    ldr r1, [r4, #0x3C]
    mul r1, r1, r2
    udiv r1, r1, r3
    str r1, [r4, #0x3C]
mg_ctrl:
    bl multi_ctrl_voice
    /* 1.26: filter of the voice from its pitch and velocity */
    ldrb r0, [r4, #0xD]
    ldr r1, [sp]
    ldr r2, [sp, #4]
    bl filt_start
    pop {r2, r3, r4, pc}

/* Entry of 0x00209870 (r0 source, r1 note): the native note-off releases
 * every record with that note. Records of notes played on a part channel
 * (+0x18 = D1 / D2) are hidden from it (state 1 -> 0x41 and back). */
multi_dsp_off:
    movw r12, #MULTI
    ldrb r12, [r12, #M_ACTIVE]
    cmp r12, #0
    beq mdf_body
    push {r4, r5, r6, lr}
    movs r4, #0x41
    movs r5, #1
    bl mdf_swap
    cmp r6, #0
    beq mdf_plain
    bl mdf_body
    movs r4, #1
    movs r5, #0x41
    bl mdf_swap
    pop {r4, r5, r6, pc}
mdf_plain:
    pop {r4, r5, r6, lr}
mdf_body:
    push.w {r3, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ldr r12, =0x00209875
    bx r12
/* records of the part channels in state r5 -> state r4; r6 = how many.
 * Keeps r0, r1. */
mdf_swap:
    ldr r2, =VREC
    movs r6, #0
    movs r3, #6
mdf_loop:
    ldrb r12, [r2, #4]
    cmp r12, r5
    bne mdf_next
    ldrb r12, [r2, #0x18]
    sub r12, r12, #0xD1
    cmp r12, #1
    bhi mdf_next
    strb r4, [r2, #4]
    adds r6, #1
mdf_next:
    adds r2, #0x34
    subs r3, #1
    bne mdf_loop
    bx lr

/* r0 = part 1 / 2, r1 = note, or -1 for every note: release the sounding
 * voices that the part channel started, as the native note-off does
 * (0x002094E6, record = releasing, sustain mask). */
multi_release:
    push {r4, r5, r6, r7, lr}
    add r4, r0, #0xD0
    mov r5, r1
    ldr r2, =VREC
    movs r6, #0
    movs r3, #0
mr_loop:
    ldrb r0, [r2, #4]
    cmp r0, #1
    bne mr_next
    ldrb r0, [r2, #0x18]
    cmp r0, r4
    bne mr_next
    cmp r5, #0
    blt mr_take
    ldrb r0, [r2, #5]
    cmp r0, r5
    bne mr_next
mr_take:
    movs r0, #5
    strb r0, [r2, #4]
    movs r0, #1
    lsls r0, r3
    orrs r6, r0
mr_next:
    adds r2, #0x34
    adds r3, #1
    cmp r3, #6
    blo mr_loop
    cmp r6, #0
    beq mr_done
    mov r0, r6
    ldr r12, =0x002094E7
    blx r12
    ldr r2, =VM
    ldrb.w r0, [r2, #0x280]
    cmp r0, #0
    beq mr_done
    ldrb.w r0, [r2, #0x281]
    orrs r0, r6
    strb.w r0, [r2, #0x281]
mr_done:
    pop {r4, r5, r6, r7, pc}

/* r0 = MIDI channel: the next one for a part; channel 10 (drum machines)
 * is skipped. */
multi_next_ch:
    adds r0, #1
    and r0, r0, #15
    cmp r0, #9
    it eq
    moveq r0, #10
    bx lr
    .align 2
    .ltorg

/* MIDI channel message dispatch (veneer literal 0x20014F64; r0 source,
 * r1 message), before the Program Change handler in flash (0x0020FC4C) and
 * the native dispatcher 0x00207D98, which only take the channel of the
 * volca. With reception on:
 * - modulation wheel (CC 1) and channel aftertouch on the channel of the
 *   volca, or of a part with the channel switch on: LFO depth of the voices
 *   (all of them, or those of that part);
 * - channel switch on: notes on the channel of the volca play part A over
 *   the whole keyboard; on the channels of B and C (parts with a program):
 *   notes straight to the native voice allocation with that part forced
 *   (no arpeggiator: its switch in the pattern is off for the call),
 *   Program Change = program of the part, CC 120 / 123 = notes off. */
midi_multi:
    cmp r0, #2
    bhi mm_native
    ldr r3, =0x20002F4C
    ldrb.w r3, [r3, #0x1C4]
    cmp r3, #0
    beq mm_native
    push {r4, r5, r6, r7, r8, lr}
    mov r4, r0
    mov r5, r1
    ldrb r6, [r1]
    and r7, r6, #0x0F
    and r6, r6, #0xF0
    movw r8, #MULTI
    ldr r3, =0x200029FC
    ldrb r0, [r3, #9]
    movs r2, #0
    cmp r7, r0
    beq mm_ours
    ldrb r3, [r8, #M_CHAN]
    cmp r3, #0
    beq mm_pass
    bl multi_next_ch
    movs r2, #1
    cmp r7, r0
    beq mm_ours
    bl multi_next_ch
    movs r2, #2
    cmp r7, r0
    bne mm_pass
mm_ours:
    mov r7, r2
    cmp r6, #0xD0
    beq mm_touch
    cmp r6, #0xB0
    bne mm_notes
    ldrb r0, [r5, #1]
    /* 1.26: CC 74 cutoff, CC 71 resonance */
    cmp r0, #74
    beq mm_cutoff
    cmp r0, #71
    beq mm_reso
    cmp r0, #1
    bne mm_notes
    ldrb r0, [r5, #2]
    add r1, r8, #M_WHEEL
    b mm_ctrl
mm_cutoff:
    movs r0, #1
    b mm_filter
mm_reso:
    movs r0, #3
mm_filter:
    ldrb r1, [r5, #2]
    bl filt_set
    pop {r4, r5, r6, r7, r8, pc}
mm_touch:
    ldrb r0, [r5, #1]
    add r1, r8, #M_TOUCH
mm_ctrl:
    ldrb r3, [r8, #M_CHAN]
    cmp r3, #0
    beq mm_ctrl_all
    strb r0, [r1, r7]
    b mm_ctrl_go
mm_ctrl_all:
    strb r0, [r1]
    strb r0, [r1, #1]
    strb r0, [r1, #2]
mm_ctrl_go:
    bl multi_ctrl_all
    pop {r4, r5, r6, r7, r8, pc}
mm_notes:
    ldrb r3, [r8, #M_CHAN]
    cmp r3, #0
    beq mm_pass
    cmp r7, #0
    bne mm_part
    /* channel of the volca: notes play part A */
    cmp r6, #0x90
    it ne
    cmpne r6, #0x80
    bne mm_pass
    movs r0, #1
    strb r0, [r8, #M_FORCE]
    mov r0, r4
    mov r1, r5
    ldr r12, =0x0020FC4D
    blx r12
    movs r0, #0
    strb r0, [r8, #M_FORCE]
    pop {r4, r5, r6, r7, r8, pc}
mm_part:
    add r4, r8, r7, lsl #4
    cmp r6, #0xC0
    bne mm_part_on
    ldrb r0, [r5, #1]
    and r0, r0, #63
    adds r0, #1
    strb r0, [r4]
    bl multi_update
    bl save_multi
    pop {r4, r5, r6, r7, r8, pc}
mm_part_on:
    ldrb r0, [r4]
    cmp r0, #0
    beq mm_done
    cmp r6, #0x90
    bne mm_part_off
    ldrb r2, [r5, #2]
    cmp r2, #0
    beq mm_release
    adds r0, r7, #1
    strb r0, [r8, #M_FORCE]
    movs r0, #1
    strb r0, [r8, #M_DIRECT]
    ldr r4, =0x2001E12C
    ldrb.w r6, [r4, #0x45]
    bic r0, r6, #1
    strb.w r0, [r4, #0x45]
    movs r0, #0x20
    ldrb r1, [r5, #1]
    ldr r12, =0x00209575
    blx r12
    strb.w r6, [r4, #0x45]
    movs r0, #0
    strb r0, [r8, #M_FORCE]
    strb r0, [r8, #M_DIRECT]
    b mm_done
mm_part_off:
    cmp r6, #0x80
    beq mm_release
    cmp r6, #0xB0
    bne mm_done
    ldrb r0, [r5, #1]
    cmp r0, #120
    it ne
    cmpne r0, #123
    bne mm_done
    mov r0, r7
    mov r1, #-1
    bl multi_release
    b mm_done
mm_release:
    mov r0, r7
    ldrb r1, [r5, #1]
    bl multi_release
mm_done:
    pop {r4, r5, r6, r7, r8, pc}
mm_pass:
    mov r0, r4
    mov r1, r5
    pop {r4, r5, r6, r7, r8, lr}
mm_native:
    ldr r12, =0x0020FC4D
    bx r12
    .align 2
    .ltorg

/* active = a program in B or C, the channel switch, or a parameter of A
 * away from its default */
multi_update:
    movw r12, #MULTI
    ldrb r0, [r12, #0x10]
    ldrb r1, [r12, #0x20]
    orrs r0, r1
    ldrb r1, [r12, #M_CHAN]
    orrs r0, r1
    bne mu_on
    adr r2, multi_defaults
    movs r3, #1
mu_loop:
    ldrb r0, [r12, r3]
    ldrb r1, [r2, r3]
    cmp r0, r1
    bne mu_on
    adds r3, #1
    cmp r3, #11
    blo mu_loop
    movs r0, #0
    b mu_store
mu_on:
    movs r0, #1
mu_store:
    strb r0, [r12, #M_ACTIVE]
    bx lr

/* r5 = bit of the stream: r0 = address of its byte in the pattern, r1 = bit
 * in the byte. Clobbers r2. */
multi_bit:
    push {lr}
    lsrs r0, r5, #3
    adds r0, #37
    bl rec_addr
    and r1, r5, #7
    pop {pc}

/* The bit stream of the parameters, r7 = 0 read / 1 write: for every part
 * the fields 0..10 with multi_bits bits each, then the channel switch.
 * Reading returns r0 = 0 if a value is above its maximum. r4 = MULTI. */
multi_stream:
    push {r5, r6, r8, r9, r10, r11, lr}
    movs r5, #0
    movs r6, #0
ms2_field:
    and r0, r6, #15
    adr r1, multi_bits
    ldrb r8, [r1, r0]
    add r9, r4, r6
    cmp r6, #48
    blo ms2_have
    movs r8, #1
    add r9, r4, #M_CHAN
ms2_have:
    cmp r8, #0
    beq ms2_next
    ldrb r10, [r9]
    movs r11, #0
ms2_bit:
    bl multi_bit
    cmp r7, #0
    beq ms2_read
    lsr r2, r10, r11
    ands r2, r2, #1
    beq ms2_step
    lsls r2, r1
    ldrb r3, [r0]
    orrs r3, r2
    strb r3, [r0]
    b ms2_step
ms2_read:
    ldrb r3, [r0]
    lsrs r3, r1
    and r3, r3, #1
    lsl r3, r3, r11
    cmp r11, #0
    it eq
    moveq r10, #0
    orr r10, r10, r3
ms2_step:
    adds r5, #1
    add r11, r11, #1
    cmp r11, r8
    blo ms2_bit
    cmp r7, #0
    bne ms2_next
    cmp r6, #48
    bhs ms2_store
    and r0, r6, #15
    adr r1, multi_max
    ldrb r1, [r1, r0]
    cmp r10, r1
    bhi ms2_bad
ms2_store:
    strb r10, [r9]
ms2_next:
    adds r6, #1
    cmp r6, #49
    blo ms2_field
    movs r0, #1
    pop {r5, r6, r8, r9, r10, r11, pc}
ms2_bad:
    movs r0, #0
    pop {r5, r6, r8, r9, r10, r11, pc}

/* r6 = xor of record bytes 0..21 ^ 5A (r0..r2 clobbered) */
multi_check:
    push {r5, lr}
    movs r5, #0
    movs r6, #0x5A
mck_loop:
    add r0, r5, #36
    bl rec_addr
    ldrb r2, [r0]
    eor r6, r6, r2
    adds r5, #1
    cmp r5, #22
    blo mck_loop
    pop {r5, pc}

save_multi:
    push {r4, r5, r6, r7, lr}
    movw r4, #MULTI
    movs r5, #1
sm_clear:
    add r0, r5, #36
    bl rec_addr
    movs r2, #0
    strb r2, [r0]
    adds r5, #1
    cmp r5, #24
    blo sm_clear
    movs r0, #36
    bl rec_addr
    movs r2, #0xA7
    strb r2, [r0]
    movs r7, #1
    bl multi_stream
    bl multi_check
    movs r0, #58
    bl rec_addr
    strb r6, [r0]
    pop {r4, r5, r6, r7, pc}

/* Pattern load: the parts from the record; none or an invalid one = off. */
load_multi:
    push {r4, r5, r6, r7, lr}
    movw r4, #MULTI
    bl multi_reset
    movs r0, #36
    bl rec_addr
    ldrb r2, [r0]
    cmp r2, #0xA6
    beq lm_old
    cmp r2, #0xA7
    bne lm_done
    bl multi_check
    movs r0, #58
    bl rec_addr
    ldrb r2, [r0]
    cmp r2, r6
    bne lm_done
    movs r7, #0
    bl multi_stream
    cmp r0, #0
    bne lm_done
    bl multi_reset
    b lm_done
/* record of the first 1.25 build: A6, per part program, low, high,
 * octave | pan << 4, level, voices; check = xor of the 19 bytes ^ 5A */
lm_old:
    movs r5, #0
    movs r6, #0x5A
lm_xor:
    add r0, r5, #36
    bl rec_addr
    ldrb r2, [r0]
    eor r6, r6, r2
    adds r5, #1
    cmp r5, #19
    blo lm_xor
    add r0, r5, #36
    bl rec_addr
    ldrb r2, [r0]
    cmp r2, r6
    bne lm_done
    movs r5, #0
lm_copy:
    add r0, r5, #37
    bl rec_addr
    ldrb r2, [r0]
    movs r1, #6
    udiv r7, r5, r1
    mls r3, r7, r1, r5
    add r7, r4, r7, lsl #4
    cmp r3, #3
    blo lm_plain
    beq lm_octpan
    adds r3, #1
lm_plain:
    adr r1, multi_max
    ldrb r1, [r1, r3]
    cmp r2, r1
    bhi lm_bad
    strb r2, [r7, r3]
    b lm_next
lm_octpan:
    and r1, r2, #15
    cmp r1, #6
    bhi lm_bad
    strb r1, [r7, #3]
    lsrs r1, r2, #4
    cmp r1, #14
    bhi lm_bad
    strb r1, [r7, #4]
lm_next:
    adds r5, #1
    cmp r5, #18
    blo lm_copy
    b lm_done
lm_bad:
    bl multi_reset
lm_done:
    bl multi_update
    pop {r4, r5, r6, r7, pc}

/* every parameter to its default, channel switch off (r4 = MULTI) */
multi_reset:
    adr r0, multi_defaults
    movs r1, #0
mrs_loop:
    and r2, r1, #15
    ldrb r2, [r0, r2]
    strb r2, [r4, r1]
    adds r1, #1
    cmp r1, #48
    blo mrs_loop
    movs r2, #0
    strb r2, [r4, #M_CHAN]
    bx lr

/* r0 = selected key, r5 = mode 18..20: r2 = field 0..10 (keys 12..16: 0),
 * r3 = address of the parameter (the channel switch is one for all). */
multi_sel:
    cmp r0, #10
    it hi
    movhi r0, #0
    mov r2, r0
    sub r3, r5, #18
    movw r1, #MULTI
    add r3, r1, r3, lsl #4
    add r3, r3, r2
    cmp r2, #7
    it eq
    addeq r3, r1, #M_CHAN
    bx lr

/* PA Pb PC (18..20): the selected key is the parameter, the slider its
 * value. The program of part A is the live one. */
adc_multi:
    mov r6, r0
    movw r12, #0x3F00
    ldrb r0, [r12, #1]
    bl multi_sel
    cmp r5, #18
    bne adc_multi_set
    cmp r2, #0
    beq adc_render
adc_multi_set:
    adr r1, multi_max
    ldrb r1, [r1, r2]
    mov r0, r6
    mov r6, r3
    bl adc_map
    strb r0, [r6]
    /* channel switch changed: the controllers of the parts start from zero */
    movw r12, #MULTI
    add r1, r12, #M_CHAN
    cmp r6, r1
    bne adc_multi_save
    movs r0, #0
    str r0, [r12, #M_WHEEL]
    strh r0, [r12, #M_WHEEL + 4]
    bl multi_ctrl_all
adc_multi_save:
    bl multi_update
    bl save_multi
    b adc_render

/* "ALo DO  3"  "APr LIVE"  "bPr OFF"  "b05 EPian"  "COc -1"  "bPn L4"
 * "CLE 080"  "AVo --"  "bVo 2"  "bCh OFF"  "bCh 03"  "bdL 040"  "bdH 127"
 * "bdF --"  "bdF 32" */
render_multi:
    ldrb r0, [r7, #1]
    bl multi_sel
    mov r6, r2
    sub r0, r5, #18
    adr r1, multi_letters
    ldrb r0, [r1, r0]
    strb r0, [r4]
    adr r1, multi_names
    add r1, r1, r6, lsl #1
    ldrb r0, [r1]
    strb r0, [r4, #1]
    ldrb r0, [r1, #1]
    strb r0, [r4, #2]
    ldrb r7, [r3]
    adr r1, multi_kinds
    ldrb r0, [r1, r6]
    tbb [pc, r0]
rm_table:
    .byte (rm_prog - rm_table) / 2
    .byte (rm_note - rm_table) / 2
    .byte (rm_oct - rm_table) / 2
    .byte (rm_pan - rm_table) / 2
    .byte (rm_level - rm_table) / 2
    .byte (rm_voices - rm_table) / 2
    .byte (rm_chan - rm_table) / 2
    .byte (rm_fade - rm_table) / 2
rm_voices:
    cmp r7, #0
    beq rm_none
    add r0, r7, #48
    strb r0, [r4, #4]
    b render_out
rm_none:
    movs r0, #45
    strb r0, [r4, #4]
    strb r0, [r4, #5]
    b render_out
rm_fade:
    cmp r7, #0
    beq rm_none
    adr r1, multi_fades
    ldrb r0, [r1, r7]
    adds r1, r4, #4
    bl put2
    b render_out
rm_chan:
    cmp r7, #0
    beq rm_off
    ldr r3, =0x200029FC
    ldrb r0, [r3, #9]
    subs r6, r5, #18
    beq rm_chan_put
rm_chan_next:
    bl multi_next_ch
    subs r6, #1
    bne rm_chan_next
rm_chan_put:
    adds r0, #1
    adds r1, r4, #4
    bl put2
    b render_out
rm_level:
    mov r0, r7
    adds r1, r4, #4
    bl put3
    b render_out
rm_prog:
    cmp r5, #18
    beq rm_live
    cmp r7, #0
    beq rm_off
    mov r0, r7
    adds r1, r4, #1
    bl put2
    subs r0, r7, #1
    ldr r1, =0x2001D090
    ldr r1, [r1]
    add r0, r1, r0, lsl #7
    adds r0, #118
    adds r1, r4, #4
    movs r2, #5
    bl copy_text
    b render_out
rm_live:
    adr r0, multi_live
    adds r1, r4, #4
    movs r2, #4
    bl copy_text
    b render_out
rm_off:
    adr r0, multi_off
    adds r1, r4, #4
    movs r2, #3
    bl copy_text
    b render_out
rm_note:
    movs r1, #12
    udiv r6, r7, r1
    mls r0, r6, r1, r7
    movw r1, #0x1F40
    add r0, r1, r0, lsl #2
    adds r1, r4, #4
    movs r2, #4
    bl copy_text
    movs r0, #45
    cmp r6, #0
    it ne
    addne r0, r6, #47
    strb r0, [r4, #8]
    b render_out
rm_oct:
    subs r0, r7, #3
    bge rm_oct_pos
    mov r1, #45
    strb r1, [r4, #4]
    rsbs r0, r0, #0
rm_oct_pos:
    adds r0, #48
    strb r0, [r4, #5]
    b render_out
rm_pan:
    mov r1, #67
    subs r0, r7, #7
    beq rm_pan_put
    mov r1, #82
    bgt rm_pan_side
    mov r1, #76
    rsbs r0, r0, #0
rm_pan_side:
    adds r0, #48
    strb r0, [r4, #5]
rm_pan_put:
    strb r1, [r4, #4]
    b render_out
    .align 2
/* fields: program, low, high, octave, pan, level, voices, channel switch,
 * low velocity, high velocity, fade */
multi_max:
    .byte 64, 127, 127, 6, 14, 100, 6, 1, 127, 127, 7, 0, 0, 0, 0, 0
multi_defaults:
    .byte 0, 0, 127, 3, 7, 100, 0, 0, 0, 127, 0, 0, 0, 0, 0, 0
/* bits of each field in the record (the channel switch is at the end) */
multi_bits:
    .byte 7, 7, 7, 3, 4, 7, 3, 0, 7, 7, 3, 0, 0, 0, 0, 0
/* readout of each field: 0 program, 1 note, 2 octave, 3 pan, 4 number,
 * 5 voices, 6 channel, 7 fade */
multi_kinds:
    .byte 0, 1, 1, 2, 3, 4, 5, 6, 4, 4, 7, 0
/* fade widths in velocities */
multi_fades:
    .byte 0, 8, 16, 24, 32, 48, 64, 96
multi_letters:
    .ascii "AbC\0"
multi_names:
    .ascii "PrLoHiOcPnLEVoChdLdHdF"
    .byte 0, 0
multi_live:
    .ascii "LIVE"
multi_off:
    .ascii "OFF\0"
    .align 2
    .ltorg

/* ================================================================ */
/* 1.26 FILTER (control part; the audio part is filt_voice in ITCM).
 * State FILT (ITCM 0x3700), global:
 *   +00 type 0 OFF 1 LP 2 BP 3 HP   +01 cutoff   +02 resonance
 *   +03 envelope amount 0..126 (63 = none)   +04 attack   +05 decay
 *   +06 sustain   +07 release   +08 key tracking 0..100 %
 *   +09 velocity on the envelope amount   +0F active bits (1 filter,
 *   2 amplitude modulation)
 *   LFO1 +10, LFO2 +18: wave, rate, depth, destination, sync, division
 *   +20 LFO1 phase  +24 LFO1 value (Q15)  +28 LFO2 phase  +2C LFO2 value
 *   +0E last voice seen  +30 random state  +34 sample counter (samples with
 *   a sounding voice)  +38 its value at the last LFO step  +3C S&H values
 * Per voice at +40 + 48 x voice: +00 ic1 +04 ic2 +08 a1 +0C a2 +10 a3
 *   +14 k (Q29) +18 input gain (Q15) +1C amplitude (Q16) +20 its step
 *   +24 envelope (0..65535)  +29 stage 0 idle 1 attack 2 decay / sustain 3 release
 *   +2A note +2B velocity +2C gate
 * The settings are global and are not saved (as dt / Fb). */
.equ FILT, 0x3700

filt_unused:
    bx lr

/* r0 = DSP voice, r1 = its state, r2 = 1 also step the LFOs (audio
 * interrupt) / 0 (voice start). Every 32 samples of a sounding voice. */
filt_control:
    push {r4, r5, r6, r7, r8, r9, r10, r11, lr}
    mov r4, r0
    mov r5, r1
    cbz r2, fc_env
    bl filt_lfos
fc_env:
    /* 1.29: settings of the part of the voice (its program's block), type
     * per voice for filt_voice */
    mov r0, r4
    bl filt_params
    mov r6, r0
    ldrb r0, [r6]
    strb r0, [r5, #0x2D]
    ldr r7, [r5, #0x24]
    ldrb r0, [r5, #0x29]
    ldrb r1, [r5, #0x2C]
    cbnz r1, fc_stage
    cbz r0, fc_stage
    movs r0, #3
fc_stage:
    cmp r0, #1
    bne fc_not_attack
    ldrb r1, [r6, #4]
    adr r2, filt_att
    ldr r1, [r2, r1, lsl #2]
    add r7, r7, r1
    movw r1, #65535
    cmp r7, r1
    blo fc_env_done
    mov r7, r1
    movs r0, #2
    b fc_env_done
fc_not_attack:
    cmp r0, #2
    bne fc_release
    ldrb r1, [r6, #6]
    lsls r2, r1, #9
    add r2, r2, r1, lsl #2
    ldrb r1, [r6, #5]
    b fc_exp
fc_release:
    cmp r0, #3
    bne fc_env_done
    movs r2, #0
    ldrb r1, [r6, #7]
fc_exp:
    adr r3, filt_dec
    ldrh r1, [r3, r1, lsl #1]
    subs r3, r7, r2
    beq fc_env_done
    mul r1, r3, r1
    asrs r1, r1, #15
    bne fc_exp_sub
    cmp r3, #0
    ite gt
    movgt r1, #1
    movle r1, #-1
fc_exp_sub:
    subs r7, r7, r1
fc_env_done:
    strb r0, [r5, #0x29]
    str r7, [r5, #0x24]
    /* cutoff in 1/8 semitone: 128 + cutoff x 121 / 16 (notes 16..136) */
    ldrb r0, [r6, #1]
    movs r1, #121
    mul r0, r0, r1
    lsrs r0, r0, #4
    add r8, r0, #128
    /* envelope: amount -63..63 = -8..+8 octaves at full envelope, scaled by
     * the velocity (vE) */
    ldrb r0, [r6, #3]
    subs r0, #63
    beq fc_kt
    mul r0, r0, r7
    movs r1, #12
    mul r0, r0, r1
    asrs r0, r0, #16
    ldrb r1, [r6, #9]
    ldrb r2, [r5, #0x2B]
    rsb r2, r2, #127
    mul r1, r1, r2
    movs r2, #127
    udiv r1, r1, r2
    rsb r1, r1, #127
    mul r0, r0, r1
    sdiv r0, r0, r2
    add r8, r8, r0
fc_kt:
    ldrb r0, [r6, #8]
    cbz r0, fc_lfo
    ldrb r1, [r5, #0x2A]
    subs r1, #60
    lsls r1, r1, #3
    mul r1, r1, r0
    movs r0, #100
    sdiv r1, r1, r0
    add r8, r8, r1
fc_lfo:
    /* LFOs: r9 cutoff, r10 resonance, r11 amplitude (Q16), r7 crossfade */
    mov r9, #0
    mov r10, #0
    mov r11, #65536
    mov r7, #-1
    movw r3, #(FILT+0x10)
    movs r2, #2
fc_lfo_loop:
    ldrb r0, [r3, #2]
    cbz r0, fc_lfo_next
    ldr r1, [r3, #0x14]
    ldrb r12, [r3, #3]
    cmp r12, #2
    beq fc_lfo_am
    mul r1, r1, r0
    cmp r12, #0
    it eq
    addeq r9, r9, r1
    cmp r12, #1
    it eq
    addeq r10, r10, r1
    cmp r12, #3
    bne fc_lfo_next
    push {r2}
    movs r2, #127
    sdiv r1, r1, r2
    pop {r2}
    add r7, r1, #32768
    b fc_lfo_next
fc_lfo_am:
    /* tremolo: 1 - depth / 127 x (1 - (value + 1) / 2) */
    rsb r1, r1, #32768
    sub r1, r1, #1
    mul r1, r1, r0
    push {r2}
    movs r2, #127
    udiv r1, r1, r2
    pop {r2}
    rsb r1, r1, #65536
    umull r12, r1, r11, r1
    lsl r1, r1, #16
    orr r11, r1, r12, lsr #16
fc_lfo_next:
    adds r3, #8
    subs r2, #1
    bne fc_lfo_loop
    /* LFO on the cutoff: +-48 semitones at depth 127 */
    add r9, r9, r9, lsl #1
    add r8, r8, r9, asr #15
    /* aftertouch of the part of the voice: up to +32 semitones */
    movw r12, #0x3900
    add r0, r12, r4
    ldrb r0, [r0, #0x32]
    cmp r0, #2
    it hi
    movhi r0, #0
    add r0, r0, r12
    ldrb r0, [r0, #0x57]
    add r8, r8, r0, lsl #1
    usat r8, #11, r8
    movw r0, #1088
    cmp r8, r0
    it hi
    movhi r8, r0
    /* g: table by semitone, linear within the semitone */
    adr r1, filt_g
    lsrs r0, r8, #3
    ldr r2, [r1, r0, lsl #2]
    cmp r0, #136
    bhs fc_g
    add r1, r1, r0, lsl #2
    ldr r3, [r1, #4]
    subs r3, r3, r2
    and r0, r8, #7
    mul r3, r3, r0
    add r2, r2, r3, asr #3
fc_g:
    /* resonance 0..127 (+ LFO): k = 2 - 1.9 x resonance / 127, Q26 */
    ldrb r0, [r6, #2]
    add r0, r0, r10, asr #15
    usat r0, #7, r0
    ldr r1, =1003943
    mul r1, r1, r0
    rsb r3, r1, #0x08000000
    /* input gain against the resonance boost */
    movs r1, #96
    mul r1, r1, r0
    movw r0, #32767
    subs r0, r0, r1
    str r0, [r5, #0x18]
    /* a1 = 1 / (1 + g (g + k)), a2 = g a1, a3 = g a2 (Q30) */
    add r0, r2, r3
    umull r1, r0, r2, r0
    lsrs r0, r0, #4
    add r0, r0, #65536
    mov r1, #-1
    udiv r1, r1, r0
    lsls r1, r1, #14
    str r1, [r5, #8]
    smull r0, r1, r2, r1
    lsls r1, r1, #6
    orr r1, r1, r0, lsr #26
    str r1, [r5, #0xC]
    smull r0, r1, r2, r1
    lsls r1, r1, #6
    orr r1, r1, r0, lsr #26
    str r1, [r5, #0x10]
    lsls r3, r3, #3
    str r3, [r5, #0x14]
    /* amplitude: tremolo x crossfade between parts A and b
     * (x = 0.5 + value x depth / 2: A = 1 - x^2, b = x (2 - x)) */
    cmp r7, #-1
    beq fc_amp
    usat r7, #16, r7
    movw r12, #0x3900
    add r0, r12, r4
    ldrb r0, [r0, #0x32]
    cmp r0, #1
    bhi fc_amp
    beq fc_xf_b
    mul r0, r7, r7
    lsrs r0, r0, #16
    rsb r0, r0, #65536
    b fc_xf_apply
fc_xf_b:
    rsb r0, r7, #131072
    mul r0, r0, r7
    lsrs r0, r0, #16
fc_xf_apply:
    umull r12, r0, r11, r0
    lsls r0, r0, #16
    orr r11, r0, r12, lsr #16
fc_amp:
    ldr r0, [r5, #0x1C]
    sub r0, r11, r0
    asrs r0, r0, #5
    str r0, [r5, #0x20]
    pop {r4, r5, r6, r7, r8, r9, r10, r11, pc}
    .align 2
    .ltorg

/* The two LFOs, from the samples since the last step (LFO2 first: it can
 * move the rate of LFO1). Free: rate table; sync: phase from the sixteenths
 * counted since the transport start and the frames since the last one, free
 * at that rate without clock. */
filt_lfos:
    push {r4, r5, r6, r7, r8, lr}
    movw r4, #FILT
    ldr r0, [r4, #0x34]
    ldr r1, [r4, #0x38]
    str r0, [r4, #0x38]
    subs r5, r0, r1
    cmp r5, #128
    it hi
    movhi r5, #32
    movs r6, #1
fl_loop:
    add r7, r4, r6, lsl #3
    ldrb r0, [r7, #0x14]
    cbnz r0, fl_sync
    ldrb r0, [r7, #0x11]
    cbnz r6, fl_rate
    ldrb r1, [r4, #0x1B]
    cmp r1, #4
    bne fl_rate
    ldrb r1, [r4, #0x1A]
    ldr r2, [r4, #0x2C]
    mul r1, r1, r2
    add r0, r0, r1, asr #15
    usat r0, #7, r0
fl_rate:
    adr r1, filt_lfo_rates
    ldr r1, [r1, r0, lsl #2]
    ldr r0, [r7, #0x20]
    mla r2, r1, r5, r0
    b fl_store
fl_sync:
    movw r12, #0x3F80
    ldr r0, [r12, #8]
    ldr r1, [r12, #0xC]
    ldr r8, [r12, #0x10]
    cmp r8, #0
    it eq
    movweq r8, #6250
    subs r0, r0, r1
    ldrb r1, [r7, #0x15]
    movs r2, #1
    lsls r2, r1
    mul r3, r8, r2
    mov r1, #-1
    udiv r1, r1, r3
    cmp r0, r8, lsl #1
    bhi fl_sync_free
    cmp r0, r8
    it hi
    movhi r0, r8
    movw r3, #0x3B80
    ldr r3, [r3, #0x3C]
    subs r2, #1
    ands r3, r3, r2
    mla r0, r3, r8, r0
    mul r2, r0, r1
    ldr r0, [r7, #0x20]
    b fl_store
fl_sync_free:
    ldr r0, [r7, #0x20]
    mla r2, r1, r5, r0
fl_store:
    str r2, [r7, #0x20]
    cmp r2, r0
    bhs fl_wave
    /* a new cycle: new sample and hold value */
    ldr r0, [r4, #0x30]
    ldr r1, =1664525
    ldr r3, =1013904223
    mla r0, r0, r1, r3
    str r0, [r4, #0x30]
    asrs r0, r0, #16
    add r1, r4, r6, lsl #1
    strh r0, [r1, #0x3C]
fl_wave:
    ldrb r0, [r7, #0x10]
    cmp r0, #5
    bhs fl_sh
    tbb [pc, r0]
fl_wtab:
    .byte (fl_sin - fl_wtab) / 2
    .byte (fl_tri - fl_wtab) / 2
    .byte (fl_up - fl_wtab) / 2
    .byte (fl_down - fl_wtab) / 2
    .byte (fl_sqr - fl_wtab) / 2
    .align 1
fl_sin:
    asrs r0, r2, #16
    eor r1, r0, r0, asr #31
    rsb r1, r1, #32768
    mul r0, r0, r1
    asrs r0, r0, #13
    b fl_put
fl_tri:
    lsrs r0, r2, #16
    lsls r0, r0, #1
    cmp r2, #0
    blt fl_tri_down
    sub r0, r0, #32768
    b fl_put
fl_tri_down:
    rsb r0, r0, #98304
    subs r0, #1
    b fl_put
fl_up:
    lsrs r0, r2, #16
    sub r0, r0, #32768
    b fl_put
fl_down:
    lsrs r0, r2, #16
    rsb r0, r0, #32768
    subs r0, #1
    b fl_put
fl_sqr:
    movw r0, #32767
    cmp r2, #0
    it lt
    rsblt r0, r0, #0
    b fl_put
fl_sh:
    add r1, r4, r6, lsl #1
    ldrsh r0, [r1, #0x3C]
fl_put:
    ssat r0, #16, r0
    str r0, [r7, #0x24]
    subs r6, #1
    bpl fl_loop
    pop {r4, r5, r6, r7, r8, pc}
    .align 2
    .ltorg

/* Voice start (from multi_gain): r0 = DSP voice, r1 = pitch (note x 256),
 * r2 = velocity. New filter, envelope from zero, coefficients at once. */
filt_start:
    push {r4, r5, lr}
    cmp r0, #5
    bhi fs_done
    mov r5, r0
    movw r3, #FILT
    add r4, r0, r0, lsl #1
    add r4, r3, r4, lsl #4
    adds r4, #0x40
    movs r3, #0
    str r3, [r4]
    str r3, [r4, #4]
    str r3, [r4, #0x24]
    str r3, [r4, #0x20]
    mov r3, #65536
    str r3, [r4, #0x1C]
    movs r3, #1
    strb r3, [r4, #0x29]
    strb r3, [r4, #0x2C]
    lsrs r1, r1, #8
    cmp r1, #127
    it hi
    movhi r1, #127
    strb r1, [r4, #0x2A]
    cmp r2, #127
    it hi
    movhi r2, #127
    strb r2, [r4, #0x2B]
    bl filt_flags
    mov r0, r5
    mov r1, r4
    movs r2, #0
    bl filt_control
fs_done:
    pop {r4, r5, pc}

/* BL at 0x0020E7EA instead of 0x00204580 (r0 = the voice): the gate of the
 * filter envelope closes with the Korg envelopes. */
filt_keyoff:
    ldrb r1, [r0, #0xD]
    cmp r1, #5
    bhi fk_native
    add r1, r1, r1, lsl #1
    movw r2, #FILT
    add r2, r2, r1, lsl #4
    movs r1, #0
    strb r1, [r2, #0x6C]
fk_native:
    ldr r12, =0x00204581
    bx r12

/* active bits: 1 = a filter type, 2 = an LFO with depth on the amplitude
 * or on the crossfade */
filt_flags:
    push {r3, lr}
    movw r12, #FILT
    ldrb r0, [r12]
    cmp r0, #0
    it ne
    movne r0, #1
    ldrb r1, [r12, #0x12]
    cbz r1, ff_two
    ldrb r1, [r12, #0x13]
    subs r1, #2
    cmp r1, #1
    it ls
    orrls r0, r0, #2
ff_two:
    ldrb r1, [r12, #0x1A]
    cbz r1, ff_parts
    ldrb r1, [r12, #0x1B]
    subs r1, #2
    cmp r1, #1
    it ls
    orrls r0, r0, #2
ff_parts:
    /* 1.29: parts b and C with a filter in their program */
    tst r0, #1
    bne ff_done
    movw r3, #0x3900
    ldrb r1, [r3, #M_ACTIVE]
    cbz r1, ff_done
    ldrb r1, [r3, #0x10]
    bl ff_part
    ldrb r1, [r3, #0x20]
    bl ff_part
ff_done:
    strb r0, [r12, #0x0F]
    pop {r3, pc}
/* r1 = program 0 (OFF) / 1..64: filter on in its block -> r0 bit 0 */
ff_part:
    subs r1, #1
    it mi
    bxmi lr
    movs r2, #EXT_N
    mul r1, r1, r2
    ldr r2, =ext_bank+2
    ldrb r1, [r2, r1]
    cmp r1, #0
    it ne
    orrne r0, r0, #1
    bx lr

/* r0 = DSP voice -> r0 = its filter settings (layout of FILT +0..+9):
 * FILT for part A (or no parts), the block of the program of part b / C */
filt_params:
    movw r12, #0x3900
    ldrb r1, [r12, #M_ACTIVE]
    cbz r1, fp_a
    add r1, r12, r0
    ldrb r1, [r1, #M_PART]
    subs r1, #1
    cmp r1, #1
    bhi fp_a
    add r1, r12, r1, lsl #4
    ldrb r1, [r1, #0x10]
    subs r1, #1
    bmi fp_a
    movs r2, #EXT_N
    mul r1, r1, r2
    ldr r0, =ext_bank+2
    add r0, r0, r1
    bx lr
fp_a:
    movw r0, #FILT
    bx lr

/* r0 = 1 cutoff / 3 resonance, r1 = 0..127 (knob with FUNC, MIDI CC 74 /
 * 71): moving them with the filter off turns on the low pass. */
filt_set:
    usat r1, #7, r1
    movw r12, #FILT
    cmp r0, #1
    ite eq
    strbeq r1, [r12, #1]
    strbne r1, [r12, #2]
    ldrb r2, [r12]
    cbnz r2, fset_flags
    movs r2, #1
    strb r2, [r12]
fset_flags:
    push {r0, r1, r4, lr}
    bl filt_flags
    bl ext_capture
    pop {r0, r1, r4, lr}
    b pm_record

/* FUNC + TRANSPOSE / VELOCITY: set and show "CUTOF 064" / "RESO  064" */
filt_knob:
    push {r4, r5, lr}
    mov r4, r0
    usat r5, #7, r1
    bl filt_set
    adr r0, filt_cut_text
    cmp r4, #1
    it ne
    addne r0, r0, #6
    adr r1, filt_text
    movs r2, #6
    bl copy_text
    mov r0, r5
    adr r1, filt_text
    adds r1, #6
    bl put3
    adr r0, filt_text
    bl show_text
    pop {r4, r5, pc}
    .align 2
filt_cut_text:
    .ascii "CUTOF RESO  "
filt_text:
    .space 12
    .align 2
    .ltorg

/* r0 = selected key, r5 = mode 21 FL / 22 LF: r0 = first character, r1 =
 * maximum, r2 = item 0..15, r3 = address of the setting. */
filt_sel:
    movw r3, #FILT
    cmp r5, #21
    bne fsl_lfo
    cmp r0, #9
    it hi
    movhi r0, #0
    mov r2, r0
    add r3, r3, r0
    movs r0, #70
    b fsl_max
fsl_lfo:
    movs r1, #0
    cmp r0, #8
    blo fsl_one
    movs r1, #1
    subs r0, #8
fsl_one:
    cmp r0, #4
    it hi
    movhi r0, #0
    add r3, r3, r1, lsl #3
    adds r3, #0x10
    add r2, r0, #10
    cmp r0, #1
    bne fsl_rest
    ldrb r12, [r3, #4]
    cmp r12, #0
    beq fsl_rest
    movs r2, #15
    adds r3, #5
    b fsl_char
fsl_rest:
    add r3, r3, r0
fsl_char:
    add r0, r1, #49
    cmp r2, #13
    bne fsl_max
    cbz r1, fsl_max
    movs r1, #4
    bx lr
fsl_max:
    adr r1, filt_max
    ldrb r1, [r1, r2]
    bx lr

/* FL LF: the selected key is the setting, the slider its value */
adc_filter:
    mov r6, r0
    movw r12, #0x3F00
    ldrb r0, [r12, #1]
    bl filt_sel
    mov r0, r6
    mov r6, r3
    bl adc_map
    strb r0, [r6]
    bl filt_flags
    b adc_render

/* "FTy LP"  "FCu 064"  "FEA  12" / "FEA -12"  "1WA SIN"  "1rA 064"  "1rA S04"
 * "2dS XF"  "1Sy ON" */
render_filter:
    ldrb r0, [r7, #1]
    bl filt_sel
    strb r0, [r4]
    adr r1, filt_names
    add r1, r1, r2, lsl #1
    ldrb r0, [r1]
    strb r0, [r4, #1]
    ldrb r0, [r1, #1]
    strb r0, [r4, #2]
    ldrb r7, [r3]
    adr r1, filt_kinds
    ldrb r0, [r1, r2]
    tbb [pc, r0]
rf_table:
    .byte (rf_num - rf_table) / 2
    .byte (rf_type - rf_table) / 2
    .byte (rf_signed - rf_table) / 2
    .byte (rf_wave - rf_table) / 2
    .byte (rf_dest - rf_table) / 2
    .byte (rf_div - rf_table) / 2
    .byte (rf_onoff - rf_table) / 2
    .align 1
rf_num:
    mov r0, r7
    adds r1, r4, #4
    bl put3
    b render_out
rf_type:
    adr r0, filt_types
    b rf_text
rf_wave:
    adr r0, filt_waves
    b rf_text
rf_dest:
    adr r0, filt_dests
    b rf_text
rf_onoff:
    adr r0, filt_onoff
rf_text:
    add r7, r7, r7, lsl #1
    add r0, r0, r7
    adds r1, r4, #4
    movs r2, #3
    bl copy_text
    b render_out
rf_signed:
    subs r0, r7, #63
    mov r1, #32
    beq rf_sign
    bpl rf_sign
    mov r1, #45
    rsbs r0, r0, #0
rf_sign:
    strb r1, [r4, #4]
    adds r1, r4, #5
    bl put2
    b render_out
rf_div:
    mov r0, #83
    strb r0, [r4, #4]
    movs r0, #1
    lsls r0, r7
    adds r1, r4, #5
    bl put2
    b render_out
    .align 2
/* items: 0 Ty 1 Cu 2 rE 3 EA 4 At 5 dE 6 SU 7 rL 8 tr 9 vE, LFO 10 WA
 * 11 rA 12 dP 13 dS 14 Sy 15 rA (sync division) */
filt_names:
    .ascii "TyCurEEAAtdESUrLtrvEWArAdPdSSyrA"
filt_kinds:
    .byte 1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 3, 0, 0, 4, 6, 5
filt_max:
    .byte 3, 127, 127, 126, 127, 127, 127, 127, 100, 127, 5, 127, 127, 3, 1, 6
filt_types:
    .ascii "OFFLP bP HP "
filt_waves:
    .ascii "SINTRISAuSAdSQRS-H"
filt_dests:
    .ascii "Cu rE AM XF L1 "
filt_onoff:
    .ascii "OFFON "
    .align 2
    .ltorg

/* 1.26 FILTER tables (generated, see docs/NOTE_TECNICHE_1_26.md).
 * filt_g: g = tan(pi fc / fs), Q26, for the notes 0..136 (fc = 440 x
 * 2^((n - 69) / 12) Hz, at most 0.45 fs), fs = 50 kHz.
 * filt_att: attack step per control step (32 samples), Q16, 0.5 ms .. 8 s.
 * filt_dec: decay / release factor per control step, Q15, 60 dB in
 * 2 ms .. 10 s. filt_lfo_rates: phase step per sample, 0.05 .. 30 Hz. */
    .align 2
filt_g:
    .word 0x000086AA, 0x00008EAC, 0x00009728, 0x0000A025, 0x0000A9AA, 0x0000B3C1, 0x0000BE71, 0x0000C9C4
    .word 0x0000D5C4, 0x0000E27A, 0x0000EFF1, 0x0000FE36, 0x00010D54, 0x00011D58, 0x00012E4F, 0x00014049
    .word 0x00015355, 0x00016782, 0x00017CE3, 0x00019389, 0x0001AB88, 0x0001C4F4, 0x0001DFE3, 0x0001FC6C
    .word 0x00021AA8, 0x00023AAF, 0x00025C9F, 0x00028093, 0x0002A6AA, 0x0002CF05, 0x0002F9C6, 0x00032712
    .word 0x00035710, 0x000389E9, 0x0003BFC7, 0x0003F8D9, 0x00043550, 0x00047560, 0x0004B93F, 0x00050127
    .word 0x00054D56, 0x00059E0C, 0x0005F390, 0x00064E29, 0x0006AE25, 0x000713D7, 0x00077F94, 0x0007F1BA
    .word 0x00086AAA, 0x0008EACB, 0x0009728B, 0x000A025E, 0x000A9ABE, 0x000B3C2F, 0x000BE73A, 0x000C9C71
    .word 0x000D5C6F, 0x000E27D9, 0x000EFF5D, 0x000FE3B3, 0x0010D59F, 0x0011D5EF, 0x0012E580, 0x00140539
    .word 0x00153612, 0x0016790F, 0x0017CF46, 0x001939DC, 0x001ABA09, 0x001C5115, 0x001E0060, 0x001FC95C
    .word 0x0021AD93, 0x0023AEA4, 0x0025CE4B, 0x00280E5E, 0x002A70CD, 0x002CF7AA, 0x002FA524, 0x00327B90
    .word 0x00357D65, 0x0038AD43, 0x003C0DF3, 0x003FA26B, 0x00436DD1, 0x0047737E, 0x004BB702, 0x00503C2A
    .word 0x005506FE, 0x005A1BCF, 0x005F7F36, 0x00653619, 0x006B45BA, 0x0071B3B2, 0x00788606, 0x007FC325
    .word 0x008771FB, 0x008F99F8, 0x00984320, 0x00A17618, 0x00AB3C3A, 0x00B59FA8, 0x00C0AB65, 0x00CC6B6F
    .word 0x00D8ECE2, 0x00E63E1A, 0x00F46EE5, 0x010390B2, 0x0113B6D9, 0x0124F6DF, 0x013768DC, 0x014B27E3
    .word 0x01605293, 0x01770BBE, 0x018F7B3C, 0x01A9CEF7, 0x01C63C36, 0x01E50149, 0x020667A9, 0x022AC6C6
    .word 0x025287AC, 0x027E29E9, 0x02AE4A28, 0x02E3AB4B, 0x031F432C, 0x03624CD0, 0x03AE6312, 0x0405A8A2
    .word 0x046B05F6, 0x04E28C8F, 0x05721CC6, 0x062288DA, 0x0701B377, 0x0826D21C, 0x09BBDBBC, 0x0C155477
    .word 0x0FFAAB49
filt_att:
    .word 0x0000FFFF, 0x0000FFFF, 0x0000FFFF, 0x0000FFFF, 0x0000F163, 0x0000DFA1, 0x0000CF2E, 0x0000BFF0
    .word 0x0000B1D1, 0x0000A4BD, 0x0000989E, 0x00008D64, 0x000082FD, 0x0000795B, 0x0000706D, 0x00006828
    .word 0x0000607E, 0x00005965, 0x000052D2, 0x00004CBA, 0x00004715, 0x000041DA, 0x00003D02, 0x00003885
    .word 0x0000345D, 0x00003083, 0x00002CF1, 0x000029A3, 0x00002693, 0x000023BC, 0x0000211B, 0x00001EAC
    .word 0x00001C6A, 0x00001A53, 0x00001863, 0x00001698, 0x000014EF, 0x00001364, 0x000011F7, 0x000010A5
    .word 0x00000F6B, 0x00000E49, 0x00000D3C, 0x00000C43, 0x00000B5C, 0x00000A86, 0x000009C0, 0x00000908
    .word 0x0000085E, 0x000007C1, 0x0000072F, 0x000006A7, 0x0000062A, 0x000005B6, 0x0000054A, 0x000004E7
    .word 0x0000048A, 0x00000435, 0x000003E6, 0x0000039C, 0x00000358, 0x00000319, 0x000002DF, 0x000002A9
    .word 0x00000277, 0x00000248, 0x0000021D, 0x000001F6, 0x000001D1, 0x000001AE, 0x0000018F, 0x00000171
    .word 0x00000156, 0x0000013D, 0x00000126, 0x00000110, 0x000000FC, 0x000000EA, 0x000000D8, 0x000000C9
    .word 0x000000BA, 0x000000AC, 0x0000009F, 0x00000094, 0x00000089, 0x0000007F, 0x00000075, 0x0000006D
    .word 0x00000065, 0x0000005D, 0x00000057, 0x00000050, 0x0000004A, 0x00000045, 0x00000040, 0x0000003B
    .word 0x00000037, 0x00000033, 0x0000002F, 0x0000002B, 0x00000028, 0x00000025, 0x00000023, 0x00000020
    .word 0x0000001E, 0x0000001B, 0x00000019, 0x00000018, 0x00000016, 0x00000014, 0x00000013, 0x00000011
    .word 0x00000010, 0x0000000F, 0x0000000E, 0x0000000D, 0x0000000C, 0x0000000B, 0x0000000A, 0x00000009
    .word 0x00000009, 0x00000008, 0x00000008, 0x00000007, 0x00000006, 0x00000006, 0x00000006, 0x00000005
filt_lfo_rates:
    .word 0x000010C7, 0x000011A5, 0x0000128E, 0x00001384, 0x00001486, 0x00001595, 0x000016B2, 0x000017DF
    .word 0x0000191A, 0x00001A66, 0x00001BC3, 0x00001D33, 0x00001EB5, 0x0000204B, 0x000021F6, 0x000023B7
    .word 0x0000258F, 0x00002780, 0x0000298A, 0x00002BB0, 0x00002DF2, 0x00003051, 0x000032D0, 0x00003570
    .word 0x00003833, 0x00003B1A, 0x00003E28, 0x0000415E, 0x000044BE, 0x0000484B, 0x00004C07, 0x00004FF5
    .word 0x00005416, 0x0000586E, 0x00005D00, 0x000061CE, 0x000066DB, 0x00006C2B, 0x000071C2, 0x000077A2
    .word 0x00007DD0, 0x00008450, 0x00008B26, 0x00009256, 0x000099E6, 0x0000A1D9, 0x0000AA35, 0x0000B300
    .word 0x0000BC3F, 0x0000C5F9, 0x0000D033, 0x0000DAF5, 0x0000E644, 0x0000F229, 0x0000FEAC, 0x00010BD4
    .word 0x000119AA, 0x00012837, 0x00013784, 0x0001479C, 0x00015889, 0x00016A55, 0x00017D0D, 0x000190BC
    .word 0x0001A570, 0x0001BB35, 0x0001D21B, 0x0001EA2F, 0x00020382, 0x00021E23, 0x00023A25, 0x00025799
    .word 0x00027692, 0x00029726, 0x0002B968, 0x0002DD6F, 0x00030352, 0x00032B2B, 0x00035513, 0x00038124
    .word 0x0003AF7D, 0x0003E03A, 0x0004137D, 0x00044965, 0x00048215, 0x0004BDB4, 0x0004FC67, 0x00053E57
    .word 0x000583B0, 0x0005CC9D, 0x0006194F, 0x000669F7, 0x0006BECA, 0x000717FE, 0x000775CE, 0x0007D877
    .word 0x00084039, 0x0008AD57, 0x00092018, 0x000998C6, 0x000A17B1, 0x000A9D2A, 0x000B2988, 0x000BBD26
    .word 0x000C5865, 0x000CFBA9, 0x000DA75C, 0x000E5BEE, 0x000F19D3, 0x000FE188, 0x0010B38E, 0x0011906E
    .word 0x001278B7, 0x00136CFF, 0x00146DE7, 0x00157C13, 0x00169835, 0x0017C305, 0x0018FD44, 0x001A47BF
    .word 0x001BA34C, 0x001D10CE, 0x001E9132, 0x00202571, 0x0021CE92, 0x00238DAA, 0x002563DA, 0x00275254
filt_dec:
    .hword 29175, 28621, 28025, 27391, 26722, 26020, 25291, 24538, 23766, 22978, 22179, 21374
    .hword 20565, 19756, 18952, 18155, 17369, 16595, 15836, 15095, 14372, 13669, 12988, 12329
    .hword 11693, 11080, 10491, 9926, 9384, 8866, 8372, 7900, 7450, 7023, 6617, 6231
    .hword 5865, 5518, 5190, 4879, 4586, 4309, 4047, 3800, 3567, 3348, 3141, 2947
    .hword 2764, 2592, 2430, 2278, 2135, 2000, 1874, 1756, 1645, 1541, 1443, 1351
    .hword 1265, 1184, 1109, 1038, 972, 909, 851, 797, 745, 698, 653, 611
    .hword 571, 535, 500, 468, 438, 410, 383, 358, 335, 314, 293, 274
    .hword 257, 240, 224, 210, 196, 184, 172, 161, 150, 140, 131, 123
    .hword 115, 107, 100, 94, 88, 82, 77, 72, 67, 63, 59, 55
    .hword 51, 48, 45, 42, 39, 37, 34, 32, 30, 28, 26, 25
    .hword 23, 21, 20, 19, 18, 16, 15, 14

/* ---------------------------------------------------------------- */
/* 1.27 FM with waveforms. Every operator reads its wave through its own
 * table pointer (operator record +0x14, the Korg kernels were patched from
 * the voice sine [ip,#0x54] to [r7,#0x14]): 0 = Korg sine, 1..7 = windows
 * of four quarter periods in a chain of twelve quarters (WV_CHAIN, RAM
 * after the reverb/delay buffer). Wave of an operator: bits 7 of bytes 11,
 * 12, 13 of its 17-byte block (ignored by Korg, always 0 in DX7 data). */
.equ WV, 0x3880
.equ WV_CHAIN, 0x20035B00
.equ WV_SINE, 0x20006810
.equ LIVE, 0x20004F5C

/* r0 = program (128 bytes), r1 = voice: pointer of every operator record.
 * Operator record i (voice + 0x90 + 0x50 i) is block i of the program. */
wave_voice:
    push {r4, r5, r6, r7, lr}
    mov r5, r0
    add r7, r1, #0x90
    add r6, r1, #0x270
    /* 1.28: VA program: the record holds the wave number (and S-H) */
    ldrb r0, [r5, #110]
    tst r0, #0x80
    bne wv_va
wv_loop:
    mov r0, r5
    bl wave_of
    cbz r0, wv_sine
    mov r4, r0
    bl wave_build
    adr r1, wave_start
    ldrb r1, [r1, r4]
    ldr r0, =WV_CHAIN
    add r0, r0, r1, lsl #11
    b wv_put
wv_sine:
    ldr r0, =WV_SINE
wv_put:
    str r0, [r7, #0x14]
    adds r5, #17
    adds r7, #0x50
    cmp r7, r6
    blo wv_loop
    pop {r4, r5, r6, r7, pc}
wv_va:
    /* 1.29 simple VA: record 0 = mode (algorithm & 7) and state, records
     * 1..5 = wave + 1 (0 = off at output level 0); the last one (OSC1)
     * always runs: the sub follows its phase */
    ldrb r0, [r5, #110]
    and r0, r0, #7
    str r0, [r7, #0x14]
    movs r0, #0
    str r0, [r7, #0x10]
    adds r5, #17
    adds r7, #0x50
wv_va_loop:
    mov r0, r5
    bl wave_of
    adds r0, #1
    sub r1, r6, #0x50
    cmp r7, r1
    beq wv_va_put
    ldrb r1, [r5, #14]
    cmp r1, #0
    it eq
    moveq r0, #0
wv_va_put:
    str r0, [r7, #0x14]
    adds r5, #17
    adds r7, #0x50
    cmp r7, r6
    blo wv_va_loop
    pop {r4, r5, r6, r7, pc}

/* r0 = 17-byte operator block -> r0 = wave 0..7 */
wave_of:
    ldrb r1, [r0, #11]
    ldrb r2, [r0, #12]
    ldrb r3, [r0, #13]
    lsrs r1, #7
    lsrs r2, #7
    lsrs r3, #7
    orr r0, r1, r2, lsl #1
    orr r0, r0, r3, lsl #2
    bx lr

/* r0 = 17-byte operator block, r1 = wave 0..7 */
wave_put:
    movs r3, #0
wp_loop:
    add r12, r0, #11
    ldrb r2, [r12, r3]
    bic r2, r2, #0x80
    lsrs r1, #1
    it cs
    orrcs r2, r2, #0x80
    strb r2, [r12, r3]
    adds r3, #1
    cmp r3, #3
    blo wp_loop
    bx lr

/* Once per power-on: the twelve quarters, value and slope as the Korg sine
 * table (entry = value, next value - value; 1024 entries per period). */
wave_build:
    movw r12, #WV
    ldrb r0, [r12, #4]
    cbz r0, wb_go
    bx lr
wb_go:
    push {r4, r5, r6, r7, lr}
    ldr r4, =WV_CHAIN
    ldr r5, =WV_SINE
    movs r6, #0
wb_quarter:
    adr r0, wave_chain
    ldrb r7, [r0, r6]
    adr r0, wave_base
    ldrh r3, [r0, r7, lsl #1]
    movs r2, #0
wb_entry:
    cbz r7, wb_zero
    cmp r7, #4
    ite hs
    addhs r1, r3, r2, lsl #1
    addlo r1, r3, r2
    ldr r0, [r5, r1, lsl #3]
    cmp r7, #5
    it eq
    rsbeq r0, r0, #0
    b wb_store
wb_zero:
    movs r0, #0
wb_store:
    str r0, [r4], #8
    adds r2, #1
    cmp r2, #256
    blo wb_entry
    adds r6, #1
    cmp r6, #12
    blo wb_quarter
    /* slopes; after the last entry the period starts again at 0 */
    ldr r4, =WV_CHAIN
    movw r2, #3071
wb_slope:
    ldr r0, [r4]
    ldr r1, [r4, #8]
    subs r1, r1, r0
    str r1, [r4, #4]
    adds r4, #8
    subs r2, #1
    bne wb_slope
    ldr r0, [r4]
    rsbs r0, r0, #0
    str r0, [r4, #4]
    movw r12, #WV
    movs r0, #1
    strb r0, [r12, #4]
    pop {r4, r5, r6, r7, pc}
    .align 2
/* quarter types: 0 zero, 1 rising, 2 falling, 3 falling below 0, 4 hump at
 * twice the frequency, 5 negative hump */
wave_chain:
    .byte 3, 0, 3, 0, 1, 2, 0, 4, 4, 0, 0, 5
/* first sine entry of each type (types 4, 5 step by two) */
wave_base:
    .hword 0, 0, 256, 512, 0, 0
/* first quarter of the window of each wave (wave 0 = Korg sine) */
wave_start:
    .byte 0, 3, 2, 0, 1, 8, 6, 4
    .align 2

/* Korg DX7 voice import (0x0020F018, through the veneer literal at
 * 0x20015174): it writes the bit fields into the bytes of the live
 * program, so the waves of the previous program are cleared first. */
wave_dx7:
    push {r0, r1, r2, r3, r4, lr}
    ldr r4, =LIVE
wd_loop:
    mov r0, r4
    movs r1, #0
    bl wave_put
    adds r4, #17
    ldr r0, =LIVE+102
    cmp r4, r0
    blo wd_loop
    /* 1.28: engine FM */
    ldr r4, =LIVE
    ldrb r0, [r4, #110]
    bic r0, r0, #0x80
    strb r0, [r4, #110]
    ldrb r0, [r4, #111]
    bic r0, r0, #0x80
    strb r0, [r4, #111]
    /* 1.28: the block of the live program back to the defaults */
    ldr r0, =ext_live
    bl ext_default
    bl ext_apply
    pop {r0, r1, r2, r3, r4, lr}
    ldr r12, =0x0020F019
    bx r12

/* 1.28: the wave is a parameter of the operator in the Korg EDIT (after
 * dEtU, index 0x16 of the operator; the same index of ALL is Ptr1).
 * Korg edit state E = 0x20002A08: +2 parameter of the operator, +3 parameter
 * of ALL, +4 operator 0..5 (OP1..OP6) or 6 (ALL). */
.equ EDIT, 0x20002A08
.equ STORED, 0x2000524C

wave_block:
    /* r0 = operator 0..5 (OP1..OP6), r2 = program -> r0 = its block */
    rsb r0, r0, #5
    movs r1, #17
    mla r0, r0, r1, r2
    bx lr

/* operator records of the voices of part A (or all, parts off) from the
 * live program */
wave_follow:
    push {r4, lr}
    movs r4, #0
wf_loop:
    movw r12, #MULTI
    ldrb r0, [r12, #M_ACTIVE]
    cbz r0, wf_set
    add r0, r12, r4
    ldrb r0, [r0, #M_PART]
    cbnz r0, wf_next
wf_set:
    ldr r0, =VOICES
    mov r1, #624
    mla r1, r1, r4, r0
    /* the kernel of the voice says its engine: VA = va_simple */
    ldr r2, [r1]
    ldr r3, =va_simple
    cmp r2, r3
    ite eq
    moveq r2, #0x80
    movne r2, #0
    ldr r0, =LIVE
    ldrb r3, [r0, #110]
    and r3, r3, #0x80
    cmp r2, r3
    bne wf_next
    bl wave_voice
wf_next:
    adds r4, #1
    cmp r4, #6
    blo wf_loop
    pop {r4, pc}

/* Entry of the value getters 0x20012F78 (live program) and 0x2001302C
 * (stored copy): r0 = E. The replaced instructions are ldrb r3,[r0,#4];
 * cmp r3,#6, the native code goes on with those flags. */
edit_get_live:
    ldr r2, =LIVE
    ldr r12, =0x20012F7D
    b eg_body
edit_get_stored:
    ldr r2, =STORED
    ldr r12, =0x20013031
eg_body:
    ldrb r3, [r0, #4]
    cmp r3, #6
    beq eg_all
    ldrb r1, [r0, #2]
    cmp r1, #0x16
    beq eg_wave
    cmp r3, #6
eg_native:
    bx r12
eg_all:
    ldrb r1, [r0, #3]
    cmp r1, #0x27
    bhi eg_ext
    bne eg_native_all
    ldrb r0, [r2, #110]
    lsrs r0, r0, #7
    bx lr
eg_ext:
    /* 1.28 block of the program: live or stored copy of the slot */
    ldr r3, =LIVE
    cmp r2, r3
    beq eg_ext_live
    push {r1, lr}
    bl ext_stored
    mov r2, r0
    pop {r1, lr}
    b ext_get
eg_ext_live:
    ldr r2, =ext_live
    b ext_get
eg_native_all:
    cmp r3, #6
    bx r12
eg_wave:
    mov r0, r3
    push {lr}
    bl wave_block
    bl wave_of
    pop {pc}

/* Entry of the setter 0x20012A2C (r0 = E, r1 = slider 0..127); replaced:
 * push {r3, lr}; mov r3, r0. The wave: 0..127 -> 0..7. */
edit_set:
    ldrb r2, [r0, #4]
    cmp r2, #6
    beq es_all
    ldrb r2, [r0, #2]
    cmp r2, #0x16
    beq es_wave
es_native:
    push {r3, lr}
    mov r3, r0
    ldr r12, =0x20012A31
    bx r12
es_all:
    ldrb r2, [r0, #3]
    cmp r2, #0x27
    bhi es_ext
    bne es_native
    /* engine: 0..63 FM, 64..127 VA; the next notes use it */
    ldr r2, =LIVE
    ldrb r3, [r2, #110]
    bic r3, r3, #0x80
    cmp r1, #64
    it ge
    orrge r3, r3, #0x80
    strb r3, [r2, #110]
    ldr r12, =0x20010DB9
    bx r12
es_ext:
    /* 1.28 block of the program: slider -> 0..max, then the runtime */
    push {r4, r5, r6, lr}
    mov r5, r1
    mov r1, r2
    bl ext_param
    mov r4, r0
    ldrb r1, [r4, #5]
    mov r0, r5
    bl adc_map
    ldrb r1, [r4, #4]
    ldr r2, =ext_live
    strb r0, [r2, r1]
    bl ext_apply
    pop {r4, r5, r6, lr}
    ldr r12, =0x20010DB9
    bx r12
es_wave:
    push {r4, r5, r6, lr}
    ldrb r4, [r0, #4]
    mov r0, r1
    usat r0, #7, r0
    lsrs r5, r0, #4
    /* 1.29 VA: OP1, OP2 5 waves, OP3 3 (sub 1, sub 2, noise), others none */
    ldr r2, =LIVE
    ldrb r2, [r2, #110]
    tst r2, #0x80
    beq esw_put
    adr r2, va_wave_max
    ldrb r2, [r2, r4]
    cmp r5, r2
    it hi
    movhi r5, r2
esw_put:
    mov r0, r4
    ldr r2, =LIVE
    bl wave_block
    mov r1, r5
    bl wave_put
    cbz r5, es_follow
    bl wave_build
es_follow:
    bl wave_follow
    pop {r4, r5, r6, lr}
    ldr r12, =0x20010DB9
    bx r12

/* Entry of the readout 0x200101D4 (r0 = text, r1 = parameter); replaced:
 * push {r3, r4, r5, lr}; mov r4, r0. "3 WAvE dbL" style: "3 WAv dbL". */
edit_text:
    ldr r2, =EDIT
    ldrb r3, [r2, #4]
    cmp r3, #6
    beq et_all
    cmp r1, #0x16
    beq et_wave
et_native:
    push {r3, r4, r5, lr}
    mov r4, r0
    ldr r12, =0x200101D9
    bx r12
et_all:
    cmp r1, #0x27
    bhi et_ext
    bne et_native
    push {r4, r5, lr}
    mov r4, r0
    ldr r12, =0x200100B1
    blx r12
    adr r0, engine_text
    ldr r2, =LIVE
    ldrb r1, [r2, #110]
    tst r1, #0x80
    it ne
    addne r0, r0, #9
    mov r1, r4
    movs r2, #9
    bl copy_text
    pop {r4, r5, pc}
et_ext:
    /* 1.29 "A CUtF 64": name (4), edited mark (Korg 0x15), value 0..99 */
    push {r4, r5, r6, r7, lr}
    mov r4, r0
    mov r5, r1
    ldr r12, =0x200100B1
    blx r12
    movs r0, #65
    strb r0, [r4]
    movs r0, #32
    strb r0, [r4, #1]
    mov r1, r5
    bl ext_param
    mov r6, r0
    adds r1, r4, #2
    movs r2, #4
    bl copy_text
    ldrb r1, [r6, #4]
    ldr r2, =ext_live
    ldrb r7, [r2, r1]
    bl ext_stored
    ldrb r1, [r6, #4]
    ldrb r0, [r0, r1]
    cmp r0, r7
    ite eq
    moveq r0, #32
    movne r0, #0x15
    strb r0, [r4, #6]
    ldrb r2, [r6, #6]
    cmp r2, #6
    beq ete_raw
    cmp r2, #2
    bhs ete_name
    /* 0..max -> 0..99 rounded (max 126 with 63 = 50) */
    ldrb r1, [r6, #5]
    movs r0, #99
    mul r0, r0, r7
    add r0, r0, r1, lsr #1
    udiv r7, r0, r1
ete_raw:
    movs r1, #10
    udiv r0, r7, r1
    mls r1, r0, r1, r7
    adds r0, #48
    adds r1, #48
    strb r0, [r4, #7]
    strb r1, [r4, #8]
    pop {r4, r5, r6, r7, pc}
ete_name:
    adr r0, ext_name_at
    subs r2, #2
    ldrb r0, [r0, r2]
    adr r1, ext_names
    add r0, r0, r1
    add r0, r0, r7, lsl #1
    adds r1, r4, #7
    movs r2, #2
    bl copy_text
    pop {r4, r5, r6, r7, pc}
et_wave:
    push {r4, r5, lr}
    mov r4, r0
    mov r5, r3
    ldr r12, =0x200100B1
    blx r12
    adds r0, r5, #49
    strb r0, [r4]
    adr r0, wave_label
    adds r1, r4, #1
    movs r2, #6
    bl copy_text
    mov r0, r5
    ldr r2, =LIVE
    bl wave_block
    bl wave_of
    adr r1, wave_names
    ldr r2, =LIVE
    ldrb r2, [r2, #110]
    tst r2, #0x80
    beq etw_name
    /* 1.29 VA: names by operator */
    adr r1, va_wave_names
    add r1, r1, r5, lsl #4
etw_name:
    add r0, r1, r0, lsl #1
    adds r1, r4, #7
    movs r2, #2
    bl copy_text
    pop {r4, r5, pc}
    .align 2
wave_label:
    .ascii " WAvE "
engine_text:
    .ascii "A EnGn FMA EnGn VA"
    .align 2
wave_names:
    .ascii "SiHA34PUALdbdAHb"
    .align 2
/* 1.29 VA, operators 1..6: names of the waves (2 characters, 8 each) */
va_wave_names:
    .ascii "SASqPUtrSiSiSiSi"
    .ascii "SASqPUtrSiSiSiSi"
    .ascii "S1S2nononononono"
    .ascii "PWPWPWPWPWPWPWPW"
    .ascii "PiPiPiPiPiPiPiPi"
    .ascii "----------------"
va_wave_max:
    .byte 4, 4, 2, 0, 0, 0
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* 1.28 STROMBOLI block of every program (48 bytes): filter, filter LFOs,
 * delay / reverb / LOFI and modulation effect. Saved by the Korg journal
 * in the free part of the program sector (16 programs per 4 KB sector:
 * Korg uses 0x010..0x8CF, the blocks go to 0x900..0xBFF). Layout:
 *   0 'S'  1 version 1  2..11 filter (FILT+0..9)  12..17 LFO 1 (FILT+0x10)
 *   18..23 LFO 2 (FILT+0x18)  24..28 FX (0x3F80 +0 +2 +4 +5 +6)
 *   29..36 MOD (0x3B80 +0 +2 +3 +4 +5 +6 +7 +9)  37..46 0  47 check
 * check = (sum of bytes 0..46) ^ 0xA5. A block that fails the check
 * (sector written by Korg or an earlier beta) = defaults. */
.equ EXT_N, 48
/* RAM after the blob (initial defaults written by the builder) */
.equ ext_live, 0x2001B3C0
.equ ext_bank, 0x2001B400
.equ JOURNAL, 0x20002D9C
.equ ROOT, 0x2001D08C

.macro EXT_DEFAULT
    .byte 0x53, 1
    .byte 0, 80, 20, 63, 0, 64, 127, 40, 50, 0
    .byte 0, 60, 0, 0, 0, 2
    .byte 1, 40, 0, 2, 0, 4
    .byte 0, 1, 7, 64, 50
    .byte 0, 0, 1, 4, 55, 50, 0, 1
    .byte 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    .byte 0
.endm

/* runtime address of block bytes 2..36 */
ext_map:
    .hword 0x3700, 0x3701, 0x3702, 0x3703, 0x3704, 0x3705, 0x3706, 0x3707, 0x3708, 0x3709
    .hword 0x3710, 0x3711, 0x3712, 0x3713, 0x3714, 0x3715
    .hword 0x3718, 0x3719, 0x371A, 0x371B, 0x371C, 0x371D
    .hword 0x3F80, 0x3F82, 0x3F84, 0x3F85, 0x3F86
    .hword 0x3B80, 0x3B82, 0x3B83, 0x3B84, 0x3B85, 0x3B86, 0x3B87, 0x3B89
    .align 2

/* r0 = block -> r0 = check byte */
ext_check:
    movs r1, #0
    movs r2, #0
ec_loop:
    ldrb r3, [r0, r2]
    add r1, r1, r3
    adds r2, #1
    cmp r2, #47
    blo ec_loop
    and r0, r1, #0xFF
    eor r0, r0, #0xA5
    bx lr

/* r0 = block: valid? -> Z set if valid */
ext_valid:
    push {r4, lr}
    mov r4, r0
    ldrb r1, [r4]
    cmp r1, #0x53
    bne ev_out
    ldrb r1, [r4, #1]
    cmp r1, #1
    bne ev_out
    bl ext_check
    ldrb r1, [r4, #47]
    cmp r0, r1
ev_out:
    pop {r4, pc}

/* r0 = destination block <- defaults */
ext_default:
    adr r1, ext_defaults
    movs r2, #EXT_N
/* r0 = destination, r1 = source, r2 = bytes */
ext_copy:
    subs r2, #1
    ldrb r3, [r1, r2]
    strb r3, [r0, r2]
    bne ext_copy
    bx lr

/* block of the live program -> runtime state */
ext_apply:
    push {r4, r5, lr}
    ldr r4, =ext_live
    adr r5, ext_map
    movs r2, #2
ea_loop:
    sub r3, r2, #2
    ldrh r3, [r5, r3, lsl #1]
    ldrb r1, [r4, r2]
    strb r1, [r3]
    adds r2, #1
    cmp r2, #24
    blo ea_loop
    bl filt_flags
    pop {r4, r5, pc}

/* runtime state -> block of the live program (after an edit outside EDIT:
 * FUNC + EDIT pages, FUNC + TRANSPOSE / VELOCITY, CC 74 / 71) */
ext_capture:
    ldr r0, =ext_live
    adr r1, ext_map
    movs r2, #2
ex_loop:
    sub r3, r2, #2
    ldrh r3, [r1, r3, lsl #1]
    ldrb r3, [r3]
    strb r3, [r0, r2]
    adds r2, #1
    cmp r2, #24
    blo ex_loop
    b pat_capture

/* 0x0020E456 program load, in place of the copy stored -> live (BL at
 * 0x0020E490, r0 live, r1 stored, r2 128, r4 = slot) */
ext_load:
    push {r4, lr}
    ldr r12, =0x00200415
    blx r12
    ldr r0, =ext_live
    ldr r1, =ext_bank
    movs r2, #EXT_N
    mla r1, r4, r2, r1
    bl ext_copy
    bl ext_apply
    pop {r4, pc}

/* 0x0020EF20 program save, before the Korg store (BL at 0x0020EF36,
 * r0 = slot, r1 = live) */
ext_save:
    push {r0, r1, r4, lr}
    mov r4, r0
    ldr r0, =ext_live
    bl ext_check
    ldr r1, =ext_live
    strb r0, [r1, #47]
    ldr r0, =ext_bank
    movs r2, #EXT_N
    mla r0, r4, r2, r0
    bl ext_copy
    pop {r0, r1, r4, lr}
    ldr r12, =0x00207839
    bx r12

/* 0x0020F33C Korg program SysEx received into slot r0 (BL at 0x0020F346
 * in place of the Korg store, r0 = slot, r1 = program): the block of the
 * slot back to the defaults (the dump does not carry it) */
ext_sysex:
    push {r0, r1, r4, lr}
    ldr r1, =ext_bank
    movs r2, #EXT_N
    mla r4, r0, r2, r1
    mov r0, r4
    bl ext_default
    mov r0, r4
    bl ext_check
    strb r0, [r4, #47]
    pop {r0, r1, r4, lr}
    ldr r12, =0x00207839
    bx r12

/* Journal: the program sector of group r = 16 programs is built by
 * 0x20013ACC; its last copy (Korg metadata to +0x810) ends in this tail
 * call (b.w at 0x20013B0A): r0 = sector + 0x810, r1 = metadata of the
 * group, r2 = 0xC0. */
ext_sector:
    push {r0, r1, r4, lr}
    ldr r12, =0x20015421
    blx r12
    pop {r0, r1}
    ldr r2, =ROOT
    ldr r2, [r2, #8]
    subs r1, r1, r2
    movs r2, #192
    udiv r1, r1, r2
    movs r2, #(16*EXT_N)
    ldr r3, =ext_bank
    mla r1, r1, r2, r3
    add r0, r0, #0xF0
    bl ext_copy
    pop {r4, pc}

/* Journal load, state 6 (BL at 0x20013982 in place of the copy of the 16
 * metadata of group [ROOT+0x99]): then the 16 blocks of the group are
 * read from the same sector (+0x900) and checked one by one. */
ext_sector_load:
    push {r4, r5, r6, lr}
    ldr r12, =0x20015421
    blx r12
    ldr r4, =ROOT
    ldrb r5, [r4, #0x99]
    ldrb r0, [r4, #0x91]
    cbnz r0, esl_out
    ldr r1, =JOURNAL
    ldrb r0, [r1, r5, lsl #3]
    cbz r0, esl_out
    add r1, r1, r5, lsl #3
    ldrb r1, [r1, #1]
    adds r1, #0x40
    lsls r1, r1, #12
    add r1, r1, #0x900
    ldr r0, [r4, #0x94]
    add r0, r0, #0x400
    mov r6, r0
    mov r2, #(16*EXT_N)
    ldr r12, =0x20015219
    blx r12
    ldr r4, =ext_bank
    movs r0, #(16*EXT_N)
    mla r4, r5, r0, r4
    movs r5, #16
esl_loop:
    mov r0, r6
    bl ext_valid
    mov r0, r4
    ite eq
    moveq r1, r6
    adrne r1, ext_defaults
    movs r2, #EXT_N
    bl ext_copy
    adds r4, #EXT_N
    adds r6, #EXT_N
    subs r5, #1
    bne esl_loop
esl_out:
    pop {r4, r5, r6, pc}
    .align 2
ext_defaults:
    EXT_DEFAULT
    .align 2
    .ltorg

/* ---------------------------------------------------------------- */
/* 1.28 EDIT, page A (ALL), after EnG (0x27): the block of the program,
 * parameters 0x28..0x4A. Descriptor: name (3), block byte, max, kind
 * (0 number, 1 -63..+63, 2.. names, 9 feedback 100 / LOFI 120). */
.equ EXT_FIRST, 0x28
.equ EXT_LAST, 0x3D
/* 1.29: name (4), block byte, max, kind (0 0..99, 1 0..99 with 50 = 0,
 * 2..5 names of 2 characters, 6 raw number) */
ext_desc:
    .ascii "FLtr"; .byte 2, 3, 2
    .ascii "CUtF"; .byte 3, 127, 0
    .ascii "rESo"; .byte 4, 127, 0
    .ascii "EnvA"; .byte 5, 126, 1
    .ascii "FAtK"; .byte 6, 127, 0
    .ascii "FdEC"; .byte 7, 127, 0
    .ascii "FSUS"; .byte 8, 127, 0
    .ascii "FrEL"; .byte 9, 127, 0
    .ascii "FtrK"; .byte 10, 100, 0
    .ascii "FvEL"; .byte 11, 127, 0
    .ascii "L1Fr"; .byte 12, 5, 3
    .ascii "L1rt"; .byte 13, 127, 0
    .ascii "L1dP"; .byte 14, 127, 0
    .ascii "L1to"; .byte 15, 3, 4
    .ascii "L1Sy"; .byte 16, 1, 5
    .ascii "L1dv"; .byte 17, 6, 6
    .ascii "L2Fr"; .byte 18, 5, 3
    .ascii "L2rt"; .byte 19, 127, 0
    .ascii "L2dP"; .byte 20, 127, 0
    .ascii "L2to"; .byte 21, 4, 4
    .ascii "L2Sy"; .byte 22, 1, 5
    .ascii "L2dv"; .byte 23, 6, 6
ext_names:
    .ascii "OFLPbPHP"              @ 2 filter type
    .ascii "SitrSUSdSqSH"          @ 3 LFO wave
    .ascii "CurEAMXFL1"            @ 4 LFO destination
    .ascii "OFOn"                  @ 5
    .align 2
ext_name_at:
    .byte 0, 8, 20, 30
    .align 2

/* r1 = parameter (0x28..) -> r0 = descriptor */
ext_param:
    sub r1, r1, #EXT_FIRST
    adr r0, ext_desc
    rsb r1, r1, r1, lsl #3
    add r0, r0, r1
    bx lr

/* value of parameter r1 in the block r2 -> r0 */
ext_get:
    push {r2, lr}
    bl ext_param
    pop {r2, lr}
    ldrb r1, [r0, #4]
    ldrb r0, [r2, r1]
    bx lr

/* stored block of the program in EDIT */
ext_stored:
    ldr r0, =EDIT
    ldrb r0, [r0]
    and r0, r0, #63
    movs r1, #EXT_N
    ldr r2, =ext_bank
    mla r0, r0, r1, r2
    bx lr
    .ltorg
