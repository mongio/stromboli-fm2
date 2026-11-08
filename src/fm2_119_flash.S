/* volca FM2 experimental firmware 1.19 - chain blob in flash at 0x0020FC40
 * (original FF padding at the end of the application section).
 *
 * Free chain (CH LIBERA), live chain capture (CC) and recording while a
 * chain plays (CR). State in ITCM 0x1D00, chain list 0x1C00 (64 x {pattern,
 * repeats}), capture list 0x1C80 (same format).
 *
 * State 0x1D00:
 *   +00 CH 0 KORG 1 LIBERA      +01 CC 0 off 1 armed 2 capturing
 *   +02 CR 0/1                  +03 chain length (entries)
 *   +04 our chain plays         +05 entry playing  +06 repeat done
 *   +07 MEMORY pressed (new free chain)            +08 capture length
 *   +09 pattern of the loop being captured         +0A last transport state
 *   +0B skip the next load (repeat of the same pattern)
 *   +0C a captured loop is in progress
 *   +0D show the chain readout instead of the native one
 *
 * Native: chain 0x20003E34 (+02 mask, +04 list[16], +14 count, +15 chain
 * flag, +18 position), CLOCK 0x20003198 (+06 current pattern, +0B step),
 * transport state 0x20003F8C (bit 0 play, bit 1 REC), pattern 0x2001E12C,
 * pattern banks [0x2001D08C] (16 x 1920 bytes).
 *
 * ITCM symbols (chain_msg) come from itcm_symbols.inc, written by the
 * builder. Everything else is PC-relative or an absolute literal. */
.syntax unified
.thumb
.include "itcm_symbols.inc"

.equ ST, 0x1D00
.equ LIST, 0x1C00
.equ CAP, 0x1C80
.equ CHAIN, 0x20003E34
.equ CLOCK, 0x20003198
.equ SEQSTATE, 0x20003F8C
.equ PATTERN, 0x2001E12C
.equ ROOT, 0x2001D08C
.equ N_BUILD, 0x0020C611
.equ N_ADVANCE, 0x0020C5B1
.equ N_LOAD, 0x00208901
.equ N_SWITCHSTEP, 0x0020C5D7
.equ N_PENDING, 0x00209389
.equ N_ISREC, 0x0020DB71
.equ N_WRITE, 0x0020815D
.equ N_TRANSPORT, 0x20010B11

table:
    b.w chain_build       @ +00 veneer literal 0x20014FC4 (was 0x0020C611)
    b.w chain_next        @ +04 BL at 0x00209006 (was 0x0020C5B0)
    b.w chain_load        @ +08 BL at 0x0020900C (was 0x00208900)
    b.w cap_wrap          @ +0C BL at 0x00208E30 (was ldrsb.w r3, [r4, #0xb])
    b.w trans_hook        @ +10 veneer literal 0x0020FA6C (was 0x20010B11)
    b.w cr_check          @ +14 BL at 0x0020C666 (was 0x0020DB70)

/* MEMORY + keys (r0 chain, r1 keys held, r2 keys held before). */
chain_build:
    push {r4, r5, r6, r7, lr}
    movw r4, #ST
    ldrb r3, [r4]
    cbnz r3, cb_free
    /* CH KORG: native chain; a native selection ends our chain */
    strb r3, [r4, #4]
    ldr r12, =N_BUILD
    blx r12
    pop {r4, r5, r6, r7, pc}
cb_free:
    bic r5, r1, r2
    uxth r5, r5
    cbz r5, cb_done
    ldrb r7, [r4, #3]
    ldrb r3, [r4, #7]
    cbz r3, cb_rec
    movs r3, #0
    strb r3, [r4, #7]
    movs r7, #0
    strb r7, [r4, #3]
cb_rec:
    /* REC without CR: one pattern only, as in the native firmware */
    cbz r7, cb_keys
    ldr r0, =SEQSTATE
    ldr r12, =N_ISREC
    blx r12
    cbz r0, cb_keys
    ldrb r0, [r4, #2]
    cbz r0, cb_done
cb_keys:
    movs r6, #0
cb_bit:
    lsr r0, r5, r6
    tst r0, #1
    beq cb_next
    mov r0, r6
    ldr r1, =LIST
    adds r2, r4, #3
    bl append
cb_next:
    adds r6, #1
    cmp r6, #16
    blo cb_bit
    cbnz r7, cb_force
    /* first pattern of the chain: native single selection (loads it) */
    ldr r1, =LIST
    ldrb r1, [r1]
    movs r0, #1
    lsl r1, r0, r1
    ldr r0, =CHAIN
    movs r2, #0
    ldr r12, =N_BUILD
    blx r12
    movs r0, #0
    strb r0, [r4, #5]
    strb r0, [r4, #6]
cb_force:
    bl chain_force
    movs r0, #1
    strb r0, [r4, #0xD]
cb_done:
    pop {r4, r5, r6, r7, pc}

/* r0 = pattern, r1 = list, r2 -> length byte: append, merging repeats. */
append:
    push {r4, lr}
    ldrb r3, [r2]
    cbz r3, append_new
    add r4, r1, r3, lsl #1
    ldrb r12, [r4, #-2]
    cmp r12, r0
    bne append_new
    ldrb r12, [r4, #-1]
    cmp r12, #99
    it lo
    addlo r12, #1
    strb r12, [r4, #-1]
    pop {r4, pc}
append_new:
    cmp r3, #64
    bhs append_done
    add r4, r1, r3, lsl #1
    strb r0, [r4]
    movs r12, #1
    strb r12, [r4, #1]
    adds r3, #1
    strb r3, [r2]
append_done:
    pop {r4, pc}

/* Our chain plays when it has more than one loop: native chain flag on,
 * native list = first 16 entries (LEDs), switch step recomputed. */
chain_force:
    push {r4, r5, r6, lr}
    movw r4, #ST
    ldrb r5, [r4, #3]
    ldr r6, =LIST
    cmp r5, #1
    bhi cf_on
    blo cf_off
    ldrb r0, [r6, #1]
    cmp r0, #1
    bhi cf_on
cf_off:
    movs r0, #0
    strb r0, [r4, #4]
    pop {r4, r5, r6, pc}
cf_on:
    movs r0, #1
    strb r0, [r4, #4]
    ldr r3, =CHAIN
    movs r0, #0
    movs r2, #0
cf_fill:
    movs r1, #0xFF
    cmp r0, r5
    bhs cf_put
    ldrb r1, [r6, r0, lsl #1]
    movs r12, #1
    lsl r12, r12, r1
    orr r2, r2, r12
cf_put:
    add r12, r3, r0
    strb r1, [r12, #4]
    adds r0, #1
    cmp r0, #16
    blo cf_fill
    strh r2, [r3, #2]
    cmp r5, #16
    it hi
    movhi r5, #16
    cmp r5, #2
    bhs cf_count
    ldrb r1, [r3, #4]
    strb r1, [r3, #5]
    movs r5, #2
cf_count:
    strb r5, [r3, #0x14]
    movs r0, #1
    strb r0, [r3, #0x15]
    movs r0, #0
    str r0, [r3, #0x18]
    ldr r12, =N_PENDING
    blx r12
    mov r2, r0
    ldr r1, =PATTERN
    ldrh r1, [r1, #0xC]
    ldr r0, =CHAIN
    ldr r12, =N_SWITCHSTEP
    blx r12
    pop {r4, r5, r6, pc}

/* End of a pattern in chain mode (r0 = chain): next pattern. */
chain_next:
    push {r4, r5, r6, lr}
    mov r6, r0
    movw r4, #ST
    ldr r5, =CLOCK
    ldrb r5, [r5, #6]
    /* CR: save the pattern just recorded */
    ldrb r0, [r4, #2]
    cbz r0, cn_play
    ldr r0, =SEQSTATE
    ldr r12, =N_ISREC
    blx r12
    cbz r0, cn_play
    mov r0, r5
    bl save_if_modified
cn_play:
    ldrb r0, [r4, #4]
    cbnz r0, cn_ours
    mov r0, r6
    ldr r12, =N_ADVANCE
    pop {r4, r5, r6, lr}
    bx r12
cn_ours:
    ldr r3, =LIST
    ldrb r1, [r4, #5]
    ldrb r2, [r4, #6]
    adds r2, #1
    add r12, r3, r1, lsl #1
    ldrb r0, [r12, #1]
    cmp r2, r0
    blo cn_same
    movs r2, #0
    adds r1, #1
    ldrb r0, [r4, #3]
    cmp r1, r0
    it hs
    movhs r1, #0
    strb r1, [r4, #5]
cn_same:
    strb r2, [r4, #6]
    ldrb r0, [r3, r1, lsl #1]
    cmp r0, r5
    ite eq
    moveq r1, #1
    movne r1, #0
    strb r1, [r4, #0xB]
    pop {r4, r5, r6, pc}

/* Load of the next chain pattern: skipped for a repeat of the same one
 * (the pattern keeps playing as a single pattern would). */
chain_load:
    movw r12, #ST
    ldrb r2, [r12, #0xB]
    cbz r2, cl_native
    movs r2, #0
    strb r2, [r12, #0xB]
    bx lr
cl_native:
    ldr r12, =N_LOAD
    bx r12

/* r0 = slot: native WRITE (0x0020815C) if the pattern differs from its bank. */
save_if_modified:
    push {r4, r5, r6, lr}
    cmp r0, #16
    bhs sm_done
    mov r6, r0
    ldr r1, =ROOT
    ldr r1, [r1]
    movw r2, #1920
    mla r1, r0, r2, r1
    ldr r0, =PATTERN
    movs r3, #0
sm_loop:
    ldr r4, [r0, r3]
    ldr r5, [r1, r3]
    cmp r4, r5
    bne sm_write
    adds r3, #4
    cmp r3, r2
    blo sm_loop
    pop {r4, r5, r6, pc}
sm_write:
    mov r0, r6
    ldr r12, =N_WRITE
    blx r12
sm_done:
    pop {r4, r5, r6, pc}

/* Replaces "ldrsb.w r3, [r4, #0xb]" (r4 = CLOCK) after the step increment.
 * A new loop starts at step 0 (start from the beginning, or a chain pattern
 * just loaded) or at the wrap (step > 15). A capture logs the loop that
 * has just ended and samples the pattern of the new one. */
cap_wrap:
    ldrsb.w r3, [r4, #0xB]
    cmp r3, #15
    bgt cw_loop
    cbz r3, cw_loop
    bx lr
cw_loop:
    push {r0, r1, r2, r3, r4, lr}
    movw r4, #ST
    ldrb r0, [r4, #1]
    cmp r0, #2
    bne cw_done
    ldrb r0, [r4, #0xC]
    cbz r0, cw_sample
    ldrb r0, [r4, #9]
    ldr r1, =CAP
    adds r2, r4, #8
    bl append
cw_sample:
    movs r0, #1
    strb r0, [r4, #0xC]
    ldr r0, =CLOCK
    ldrb r0, [r0, #6]
    strb r0, [r4, #9]
cw_done:
    pop {r0, r1, r2, r3, r4, pc}

/* Every transport change (PLAY, STOP, REC) ends in the veneer 0x0020FA68. */
trans_hook:
    push {r0, r4, r5, r6, r7, lr}
    movw r4, #ST
    ldr r0, =SEQSTATE
    ldr r5, [r0]
    ldrb r6, [r4, #0xA]
    strb r5, [r4, #0xA]
    eor r0, r5, r6
    tst r0, #1
    beq th_done
    tst r5, #1
    beq th_stop
    /* PLAY: an armed capture starts */
    ldrb r0, [r4, #1]
    cmp r0, #1
    bne th_done
    movs r0, #2
    strb r0, [r4, #1]
    movs r0, #0
    strb r0, [r4, #8]
    strb r0, [r4, #0xC]
    b th_done
th_stop:
    /* CR: STOP after recording on a chain saves the current pattern */
    tst r6, #2
    beq th_capture
    ldrb r0, [r4, #2]
    cbz r0, th_capture
    ldrb r0, [r4, #4]
    ldr r1, =CHAIN
    ldrb r1, [r1, #0x15]
    orrs r0, r1
    beq th_capture
    ldr r0, =CLOCK
    ldrb r0, [r0, #6]
    bl save_if_modified
th_capture:
    ldrb r0, [r4, #1]
    cmp r0, #2
    bne th_done
    /* a loop stopped on its last step is complete: log it */
    ldrb r0, [r4, #0xC]
    cbz r0, th_count
    ldr r0, =CLOCK
    ldrb r0, [r0, #0xB]
    cmp r0, #15
    bne th_count
    ldrb r0, [r4, #9]
    ldr r1, =CAP
    adds r2, r4, #8
    bl append
th_count:
    ldrb r5, [r4, #8]
    cbnz r5, th_take
    movs r0, #1
    strb r0, [r4, #1]
    b th_done
th_take:
    /* capture -> chain, CC off, first pattern loaded, chain on */
    ldr r1, =CAP
    ldr r2, =LIST
    movs r3, #0
th_copy:
    ldrh r0, [r1, r3]
    strh r0, [r2, r3]
    adds r3, #2
    cmp r3, r5, lsl #1
    blo th_copy
    strb r5, [r4, #3]
    movs r0, #0
    strb r0, [r4, #1]
    strb r0, [r4, #5]
    strb r0, [r4, #6]
    ldrb r1, [r2]
    movs r0, #1
    lsl r1, r0, r1
    ldr r0, =CHAIN
    movs r2, #0
    ldr r12, =N_BUILD
    blx r12
    bl chain_force
    /* "CATENA nn" */
    ldr r12, =chain_msg
    blx r12
th_done:
    pop {r0, r4, r5, r6, r7, lr}
    ldr r12, =N_TRANSPORT
    bx r12

/* Recording check inside the native chain selection: with CR on, a chain
 * can be selected while recording. */
cr_check:
    movw r12, #ST
    ldrb r12, [r12, #2]
    cmp r12, #0
    itt ne
    movne r0, #0
    bxne lr
    ldr r12, =N_ISREC
    bx r12
    .align 2
    .ltorg
