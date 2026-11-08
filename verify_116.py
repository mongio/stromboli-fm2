"""1.16 tests: new arpeggio modes, executed on the real patched ARM bytes.

Covers the 17-position TYPE knob (panel and MIDI CC), names on the display,
generated step tables for every mode and every number of held notes (1-6),
Korg compatibility of saved patterns, restoration of Korg's Rise1 table,
PRB2 -> PRB3 conversion keeping probabilities.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
from reverse_checks import audio_machine,blank_pattern,set_step,PATTERN
from arm_checks import REGS
import verify_panel as panel
from probability_format import set_prb3,set_prb2,get_prb2,get_prb3_fields

KORG_NAMES = ['tYP   Off','tYP Rise1','tYP Rise2','tYP Rise3','tYP Fall1','tYP Fall2','tYP Fall3',
              'tYP Rand1','tYP Rand2','tYP Rand3']
NEW_NAMES = ['tYP UPdn1','tYP UPdn2','tYP UPdn3','tYP  Conv','tYP  dIvr','tYP  PEdL','tYP  Chrd']


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def expected_cycle(ext,n):
    """Expected cycle of (slot, octave) for a new mode."""
    if ext <= 3:
        up = [(k,o) for o in range(ext) for k in range(n)]
        return up + up[-2:0:-1]
    if ext in (4,5):
        order = []
        lo,hi = 0,n-1
        while lo <= hi:
            order.append(lo)
            if lo != hi: order.append(hi)
            lo += 1; hi -= 1
        if ext == 5: order.reverse()
        return [(k,0) for k in order]
    if ext == 6:
        if n == 1: return [(0,0)]
        out = []
        for k in range(1,n): out += [(0,0),(k,0)]
        return out
    return None


def arp_run(img,chord,ext,ticks,korg_type=1,prb=True):
    a = audio_machine(img); blank_pattern(a)
    a.u.mem_write(PATTERN+69,b'\x01'); a.u.mem_write(PATTERN+70,bytes([korg_type,2]))
    a.call(0x208198,(0,1)); a.u.mem_write(PATTERN+6,b'\xff\xff')
    if prb:
        a.u.mem_write(PATTERN,set_prb3(a.data(PATTERN,1920),[100]*16,ext=ext))
    set_step(a,0,chord,127)
    a.tick = 0; a.arp = []
    a.hook(0x20E814,lambda: a.arp.append((a.tick,a.u.reg_read(REGS[1])//256)))
    a.call(0x20B7BE,(0,))
    for t in range(1,ticks+1):
        a.tick = t; a.call(0x20C40C,(0x20003E10,))
    return a


def verify_generated_modes(original,patched):
    base = [60,64,67,71,74,77]
    checked = 0
    for ext in range(1,7):
        for n in range(1,7):
            chord = base[:n]
            cyc = [chord[k]+12*o for k,o in expected_cycle(ext,n)]
            a = arp_run(patched,chord,ext,18*(3*len(cyc)+4))
            notes = [v for _,v in a.arp][2:]          # skip the start of the arpeggio
            need(len(notes) >= 2*len(cyc),'Too few arpeggio notes')
            # Must follow the cycle from some phase.
            ok = any(all(notes[i] == cyc[(p+i) % len(cyc)] for i in range(len(notes)))
                     for p in range(len(cyc)))
            need(ok,f'Mode {ext} with {n} notes: {notes[:12]} != cycle {cyc}')
            checked += 1
    # Chord: all held notes on the same tick, every DIV step.
    for n in range(1,7):
        a = arp_run(patched,base[:n],7,18*8)
        by_tick = {}
        for t,v in a.arp: by_tick.setdefault(t,[]).append(v)
        later = [sorted(v) for t,v in sorted(by_tick.items()) if t >= 18]
        need(len(later) >= 6 and all(v == base[:n] for v in later),f'Chord mode with {n} notes')
        need(sorted(by_tick) [1:] == list(range(18,18*len(by_tick),18)),'Chord timing not on DIV steps')
        checked += 1
    return {'mode_note_count_cases':checked}


def verify_knob_and_names(original,patched):
    a = panel.machine(patched)
    seen = set()
    for v in range(128):
        a.call(0x2059D0,(7,v,0,0))
        idx = (v*17) >> 7
        p = a.data(PATTERN,1920)
        ext = get_prb3_fields(p)[0]
        if idx < 10:
            need(p[70] == idx and ext == 0,f'Knob {v}: Korg type {p[70]} ext {ext}')
            need(a.texts[-1] == KORG_NAMES[idx],f'Knob {v}: name {a.texts[-1]!r}')
        else:
            need(p[70] == 1 and ext == idx-9,f'Knob {v}: new mode stored wrong ({p[70]},{ext})')
            need(a.texts[-1] == NEW_NAMES[idx-10],f'Knob {v}: name {a.texts[-1]!r}')
            g = panel.glyphs(a,NEW_NAMES[idx-10])
            need(all(x != 0 for i,x in enumerate(g) if NEW_NAMES[idx-10][i] != ' '),'Name has a blank glyph')
        seen.add(idx)
    need(seen == set(range(17)),'Not all 17 types reachable')
    # MIDI CC path (r2 = 1) uses the same mapping.
    b = panel.machine(patched)
    b.call(0x2059D0,(7,127,1,0))
    p = b.data(PATTERN,1920)
    need(p[70] == 1 and get_prb3_fields(p)[0] == 7,'MIDI CC did not select Chrd')
    b.call(0x2059D0,(7,0,1,0))
    p = b.data(PATTERN,1920)
    need(p[70] == 0 and get_prb3_fields(p)[0] == 0,'MIDI CC did not select Off')
    return {'knob_positions':128,'types':17,'names_checked':True,'midi_cc':True}


def verify_korg_compatibility(original,patched):
    # A pattern saved with a new mode plays Rise1 on the original firmware.
    a = arp_run(original,[60,64,67],4,18*12)
    notes = [v for _,v in a.arp]
    need(notes[:9] == [60,64,67]*3,'Original firmware does not play Rise1 for a new-mode pattern')
    # Selecting Korg Rise1 again restores Korg's table pointer.
    b = arp_run(patched,[60,64,67],4,18*4)
    need(b.data(0x2000B424,4) == (0x3C00).to_bytes(4,'little'),'Generated table not in use')
    b.u.mem_write(PATTERN,set_prb3(b.data(PATTERN,1920),[100]*16,ext=0))
    b.call(0x20C40C,(0x20003E10,))
    need(b.data(0x2000B424,4) == (0x2000B57C).to_bytes(4,'little'),'Korg Rise1 table not restored')
    c = arp_run(patched,[60,64,67],0,18*10,prb=False)
    need([v for _,v in c.arp][:9] == [60,64,67]*3,'Korg Rise1 changed without a new mode')
    return {'new_mode_pattern_on_korg_plays_Rise1':True,'korg_table_restored':True}


def verify_prb3_conversion(original,patched):
    a = panel.machine(patched)
    a.u.mem_write(PATTERN,set_prb2(a.data(PATTERN,1920),[10*i % 101 for i in range(16)],[3]+[0]*15,70))
    a.call(0x2059D0,(7,127,0,0))                       # Chrd
    p = a.data(PATTERN,1920)
    probs,conds,scale,ok = get_prb2(p)
    need(ok and p[0x760] == 0xA3,'Block not converted to PRB3')
    need(probs == [10*i % 101 for i in range(16)] and conds[0] == 3 and scale == 70,'Values lost in conversion')
    need(get_prb3_fields(p)[0] == 7,'Mode not stored')
    # Probability edits keep the mode bits.
    panel.enter(a); panel.select(a,1); a.call(0x2059D0,(3,64,0,0))
    p = a.data(PATTERN,1920)
    need(get_prb2(p)[0][1] == 50 and get_prb3_fields(p)[0] == 7,'Probability edit lost the mode')
    return {'PRB2_to_PRB3':True,'bits_preserved_by_edits':True}


def midi_run(img,chord,ext,korg=1,ticks=18*7):
    a = audio_machine(img); blank_pattern(a)
    a.u.mem_write(PATTERN+69,b'\x01'); a.u.mem_write(PATTERN+70,bytes([korg,2]))
    a.call(0x208198,(0,1)); a.u.mem_write(PATTERN+6,b'\xff\xff')
    a.u.mem_write(PATTERN,set_prb3(a.data(PATTERN,1920),[100]*16,ext=ext))
    set_step(a,0,chord,100)
    a.out = []
    a.hook(0x207bd4,lambda: (a.out.append(('on',a.tick,a.u.reg_read(REGS[0]),a.u.reg_read(REGS[1]))),a.return_(0)))
    a.hook(0x207c74,lambda: (a.out.append(('off',a.tick,a.u.reg_read(REGS[0]))),a.return_(0)))
    a.tick = 0
    a.call(0x20B7BE,(0,)); a.call(0x207F2C,(0,))
    for t in range(1,ticks+1):
        a.tick = t; a.call(0x20C40C,(0x20003E10,)); a.call(0x207F2C,(0,))
    return a


def verify_arp_midi_out(original,patched):
    def check(out,cycle,chord_mode=False):
        ons = [(t,n) for k,t,n,*_ in out if k == 'on']
        offs = [(t,n) for k,t,n,*_ in out if k == 'off']
        steps = sorted({t for t,_ in ons})
        need(steps == list(range(0,18*len(steps),18)),'MIDI note-on not on arpeggio steps')
        held = set()
        for k,t,n,*rest in out:
            if k == 'on':
                need(n not in held,'Note-on sent twice without note-off')
                held.add(n)
            else:
                need(n in held,'Note-off for a note not sent'); held.discard(n)
        return ons,offs
    # UPdn1 with 3 notes: one note per step, note-off when the next step starts.
    a = midi_run(patched,[60,64,67],1)
    ons,offs = check(a.out,None)
    need([n for _,n in ons] == [60,64,67,64,60,64,67,64],'UPdn1 MIDI notes wrong')
    need(all(any(o == (t,p_) for o in offs) for (t,_),(_,p_) in zip(ons[1:],ons[:-1])),'Previous note not released at next step')
    # Chrd: all notes per step.
    a = midi_run(patched,[60,64,67],7)
    ons,_ = check(a.out,None)
    by = {}
    for t,n in ons: by.setdefault(t,[]).append(n)
    need(all(sorted(v) == [60,64,67] for t,v in by.items() if t >= 18),'Chord not sent on MIDI')
    # Korg types too (Fall1), and nothing else is echoed while the arpeggio runs.
    a = midi_run(patched,[60,64,67],0,korg=4)
    ons,_ = check(a.out,None)
    need([n for _,n in ons][:6] == [67,64,60,67,64,60],'Korg Fall1 not sent on MIDI')
    # Arpeggio stops: notes released from the main loop service.
    a.u.mem_write(0x200031D4+4,b'\0'); a.u.mem_write(0x200031D4+0x34+4,b'\0'); a.u.mem_write(0x200031D4+0x68+4,b'\0')
    a.call(0x207F2C,(0,))
    held = set()
    for k,t,n,*rest in a.out:
        if k == 'on': held.add(n)
        else: held.discard(n)
    need(not held,'Notes left on after the arpeggio stopped')
    # Original firmware: no arpeggio notes on MIDI OUT (only the chord echo).
    b = midi_run(original,[60,64,67],1)
    need(sorted(n for k,t,n,*_ in b.out if k == 'on') == [60,64,67],'Original firmware MIDI behaviour changed?')
    return {'arpeggio_notes_on_midi':True,'chord_steps':True,'korg_types':True,'released_on_stop':True}


def verify_keyboard_echo(original,patched):
    for img in (original,patched):
        a = panel.machine(img)
        a.out = []
        a.hook(0x207bd4,lambda a=a: (a.out.append(a.u.reg_read(REGS[0])),a.return_(0)))
        a.call(0x20FC18,(panel.raw_for_step(0),)); a.call(0x20FC18,(0,))
        need(len(a.out) == 1,'Keyboard note not echoed on MIDI with the arpeggiator off')
    a = panel.machine(patched)
    a.call(0x2059D0,(7,40,0,0))
    a.out = []
    a.hook(0x207bd4,lambda: (a.out.append(a.u.reg_read(REGS[0])),a.return_(0)))
    a.call(0x20FC18,(panel.raw_for_step(0),)); a.call(0x20FC18,(0,))
    need(a.out == [],'Keyboard echoed on MIDI while the arpeggiator is on')
    return {'echo_with_arp_off':True,'no_echo_with_arp_on':True}


TASKS = [('v116/generated_modes',verify_generated_modes),
         ('v116/knob_and_names',verify_knob_and_names),
         ('v116/korg_compatibility',verify_korg_compatibility),
         ('v116/prb3_conversion',verify_prb3_conversion),
         ('v116/arp_midi_out',verify_arp_midi_out),
         ('v116/keyboard_echo',verify_keyboard_echo)]

if __name__ == '__main__':
    from build_patch import build
    o,p,*_ = build()
    failed = 0
    for name,fn in TASKS:
        try:
            print(name,'PASS',fn(o,p),flush=True)
        except Exception as e:
            failed += 1
            print(name,'FAIL',type(e).__name__,e,flush=True)
    raise SystemExit(1 if failed else 0)
