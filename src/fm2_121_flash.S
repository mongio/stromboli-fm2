/* volca FM2 experimental firmware 1.20 - chain blob in flash at 0x0020FC40
 * (original FF padding at the end of the application section).
 *
 * CR ON: free chain (MEMORY + keys in any order, repeats) and recording
 * while the chain plays (automatic WRITE of each recorded pattern).
 * CR OFF: native Korg chain. State in ITCM 0x1D00, chain list 0x1C00
 * (64 x {pattern, repeats}).
 *
 * State 0x1D00:
 *   +00 free chain selection (= CR)                 +02 CR 0/1
 *   +03 chain length (entries)  +04 our chain plays +05 entry playing
 *   +06 repeat done             +07 MEMORY pressed (new free chain)
 *   +0A last transport state    +0B skip the next load (repeat)
 *   +0E pattern played before + 1 (copy source)    +0F REC FISSO (ITCM)
 *   +0D show the chain readout instead of the native one
 *
 * Native: chain 0x20003E34 (+02 mask, +04 list[16], +14 count, +15 chain
 * flag, +18 position), CLOCK 0x20003198 (+06 current pattern, +0B step),
 * transport state 0x20003F8C (bit 0 play, bit 1 REC), pattern 0x2001E12C,
 * pattern banks [0x2001D08C] (16 x 1920 bytes).
 *
 * Everything is PC-relative or an absolute literal. */
.syntax unified
.thumb
.include "itcm_symbols.inc"

.equ ST, 0x1D00
.equ LIST, 0x1C00
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
    b.w midi_in           @ +0C veneer literal 0x20014F64 (was 0x00207D99)
    b.w trans_hook        @ +10 veneer literal 0x0020FA6C (was 0x20010B11)
    b.w cr_check          @ +14 BL at 0x0020C666 (was 0x0020DB70)
    b.w motion_end        @ +18 BL at 0x00209062 (was 0x00208598)
    b.w load_fx           @ +1C pattern loads (BL to 0x00208900, 5 places)

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
    ldrb r5, [r0]
    ldr r1, =PATTERN
    ldrh r1, [r1, #0xC]
    ldr r0, =CHAIN
    ldr r12, =N_SWITCHSTEP
    blx r12
    /* 1.20: while playing, adding to the chain does not restart the pattern */
    ldr r0, =SEQSTATE
    ldr r0, [r0]
    tst r0, #1
    beq cf_done
    ldr r0, =CLOCK
    strb r5, [r0, #0xB]
cf_done:
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
    /* 1.20: remember the pattern played before (copy source), + 1 */
    itt ne
    addne r1, r5, #1
    strbne r1, [r4, #0xE]
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
    b load_fx

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

/* Every transport change (PLAY, STOP, REC) ends in the veneer 0x0020FA68.
 * CR: when recording ends on a chain (REC off, by hand or after a motion
 * loop, or STOP) the current pattern is saved if it was changed. */
trans_hook:
    push {r0, r4, r5, r6, r7, lr}
    movw r4, #ST
    ldr r0, =SEQSTATE
    ldr r5, [r0]
    ldrb r6, [r4, #0xA]
    strb r5, [r4, #0xA]
    tst r6, #2
    beq th_done
    tst r5, #2
    beq th_save
    tst r5, #1
    bne th_done
th_save:
    ldrb r0, [r4, #2]
    cbz r0, th_done
    ldrb r0, [r4, #4]
    ldr r1, =CHAIN
    ldrb r1, [r1, #0x15]
    orrs r0, r1
    beq th_done
    ldr r0, =CLOCK
    ldrb r0, [r0, #6]
    bl save_if_modified
th_done:
    pop {r0, r4, r5, r6, r7, lr}
    ldr r12, =N_TRANSPORT
    bx r12

/* 1.20: every pattern load (0x00208900) also sets the effect type (FX
 * REVRB / DELAY / LOFI, 0x3F80) from the pattern (PRB3 bits of steps 13-14;
 * no block = REVRB, as in the Korg firmware). */
load_fx:
    push {r4, lr}
    ldr r12, =N_LOAD
    blx r12
    mov r4, r0
    ldr r0, =PATTERN+1888
    movs r1, #12
    ldr r12, =block_bits
    blx r12
    and r0, r0, #3
    cmp r0, #3
    it eq
    moveq r0, #0
    movw r1, #0x3F80
    strb r0, [r1]
    mov r0, r4
    pop {r4, pc}

/* BL at 0x00209062 (was 0x00208598, REC off at the end of a motion loop):
 * with REC FISSO (state 0x1D0F) recording continues. */
motion_end:
    movw r12, #ST
    ldrb r12, [r12, #0xF]
    cmp r12, #0
    beq me_native
    bx lr
me_native:
    ldr r12, =0x00208599
    bx r12

/* MIDI channel message dispatch (veneer literal 0x20014F64, was 0x00207D99;
 * r0 source, r1 message). Program Change on the volca channel, with
 * ShortMessage reception on: program (PC mod 64) + 1, as with the encoder. */
midi_in:
    ldrb r2, [r1]
    and r3, r2, #0xF0
    cmp r3, #0xC0
    bne midi_native
    cmp r0, #2
    bhi midi_done
    ldr r3, =0x20002F4C
    ldrb r3, [r3, #0x1C4]
    cbz r3, midi_done
    push {r4, lr}
    ldrb r4, [r1, #1]
    and r2, r2, #0xF
    push {r2}
    ldr r12, =0x00205C9D
    blx r12
    pop {r2}
    cmp r0, r2
    bne midi_pc_done
    and r1, r4, #63
    movs r2, #1
    ldr r0, =0x20002A08
    ldr r12, =0x200133A5
    blx r12
midi_pc_done:
    pop {r4, pc}
midi_done:
    bx lr
midi_native:
    ldr r12, =0x00207D99
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
