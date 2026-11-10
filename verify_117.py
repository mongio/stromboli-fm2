"""1.17 tests: global scale, humanize and random octave, on the real patched ARM.

Scale: nearest scale note, ties go to the upper note. Covers the keyboard
(note-on / note-off functions 0x20AA60 / 0x20AAB8 with the native MIDI echo),
MIDI DIN and USB note wrappers, the sequencer slot store (live option), the
panel (FUNC+SAVE, modes HU / OC / SC / tn, key 16 in SC) and PRB3 fields.
Every note-off must release exactly the note its note-on played, also when
the scale changes while notes are held.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
from reverse_checks import audio_machine,blank_pattern,set_step,PATTERN
from arm_checks import REGS
import verify_panel as panel
from probability_format import set_prb3,set_prb2,get_prb2,get_prb3_fields,OFFSET
from build_patch import SCALE_STEPS,SCALE_NAMES,TONIC_NAMES

V = 0x20003C6C
STATE = 0x3F30


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def model(note,scale,tonic):
    steps = set(SCALE_STEPS[scale])
    pc = (note-tonic) % 12
    if pc in steps: return note
    for d in range(1,12):
        if (pc+d) % 12 in steps and note+d <= 127: return note+d
        if (pc-d) % 12 in steps and note-d >= 0: return note-d
    return note


def set_scale(a,on,scale=1,tonic=0,seq=None):
    a.u.mem_write(STATE,bytes([on,scale,tonic]))
    if seq is not None: a.u.mem_write(STATE+3,bytes([seq]))


def watch(a):
    a.ev = []
    a.hook(0x20A78C,lambda: a.ev.append(('von',a.u.reg_read(REGS[0]),a.u.reg_read(REGS[1]),a.u.reg_read(REGS[2]))))
    a.hook(0x20A530,lambda: a.ev.append(('voff',a.u.reg_read(REGS[0]),a.u.reg_read(REGS[1]))))
    a.hook(0x207bd4,lambda: (a.ev.append(('mon',a.u.reg_read(REGS[0]))),a.return_(0)))
    a.hook(0x207c74,lambda: (a.ev.append(('moff',a.u.reg_read(REGS[0]))),a.return_(0)))


def kmachine(img):
    a = panel.machine(img)
    a.u.mem_write(V+0xDC,bytes([6]))
    watch(a)
    return a


def octave(a):
    return a.data(0x20005358+4,1)[0]


def sounding(a):
    d = a.data(V,0x60)
    return sorted(d[16*i+8] for i in range(6) if d[16*i])


def verify_scale_keyboard(original,patched):
    a = kmachine(patched)
    o = octave(a)
    checked = 0
    for scale in range(15):
        for tonic in range(12):
            set_scale(a,1,scale,tonic)
            for key in range(27):
                raw = key+12*o+5
                want = model(raw,scale,tonic)
                a.ev = []
                a.call(0x20AA60,(key,100))
                a.call(0x20AAB8,(key,))
                ev = a.ev
                need(('von',0x40,want,100) in ev,f'Keyboard note-on {raw} -> {want} wrong ({SCALE_NAMES[scale]} {tonic}): {ev}')
                need(('mon',want) in ev and ('moff',want) in ev,'MIDI echo does not carry the corrected note')
                need(('voff',0x40,want) in ev,'Keyboard note-off released another note')
                checked += 1
            need(sounding(a) == [],'Voices left sounding')
    # Scale off: notes exactly as before (and as the original firmware).
    set_scale(a,0,3,5)
    b = kmachine(original)
    for key in range(27):
        for m in (a,b):
            m.ev = []; m.call(0x20AA60,(key,90)); m.call(0x20AAB8,(key,))
        need(a.ev == b.ev,'Scale off: keyboard differs from the original firmware')
    # Ties go up: C# in C major (between C and D) -> D; F# in C pentatonic major -> G (E..G).
    need(model(61,1,0) == 62 and model(66,8,0) == 67 and model(65,8,0) == 64,'Model sanity')
    return {'keyboard_notes_checked':checked,'scale_off_identical_to_original':True}


def verify_release_after_change(original,patched):
    a = kmachine(patched)
    o = octave(a)
    set_scale(a,1,8,0)                     # pentatonic major, C
    a.ev = []
    a.call(0x20AA60,(1,100))               # C# -> D
    on = [e for e in a.ev if e[0] == 'von'][0][2]
    set_scale(a,1,9,4)                     # change scale and tonic while held
    a.call(0x20AAB8,(1,))
    need(('voff',0x40,on) in a.ev and ('moff',on) in a.ev,'Release after a scale change used another note')
    need(sounding(a) == [],'Note left sounding after a scale change')
    # Scale switched on while a key is held: the original note is released.
    set_scale(a,0)
    a.ev = []; a.call(0x20AA60,(6,100)); set_scale(a,1,1,0); a.call(0x20AAB8,(6,))
    need(('voff',0x40,6+12*o+5) in a.ev and sounding(a) == [],'Release after switching the scale on failed')
    # Switched off while held.
    set_scale(a,1,1,0)
    a.ev = []; a.call(0x20AA60,(6,100)); played = a.ev[0][2] if a.ev[0][0] == 'von' else None
    played = [e for e in a.ev if e[0] == 'von'][0][2]
    set_scale(a,0); a.call(0x20AAB8,(6,))
    need(('voff',0x40,played) in a.ev and sounding(a) == [],'Release after switching the scale off failed')
    return {'scale_change_while_held':True,'switch_on_while_held':True,'switch_off_while_held':True}


def verify_midi_in(original,patched):
    a = kmachine(patched)
    for on_fn,off_fn,src in [(0x20AB2C,0x20AB64,0x20),(0x20ABC0,0x20ABF8,0x30)]:
        set_scale(a,1,4,2)                  # D dorian
        for n in range(128):
            want = model(n,4,2)
            a.ev = []
            a.call(on_fn,(n,100)); a.call(off_fn,(n,))
            need(('von',src,want,100) in a.ev,f'MIDI in {n} -> {want} wrong: {a.ev}')
            need(('voff',src,want) in a.ev,'MIDI note-off released another note')
        need(sounding(a) == [],'MIDI voices left sounding')
        # Change while held.
        a.ev = []; a.call(on_fn,(61,100)); played = [e for e in a.ev if e[0] == 'von'][0][2]
        set_scale(a,1,11,1); a.call(off_fn,(61,))
        need(('voff',src,played) in a.ev and sounding(a) == [],'MIDI release after scale change failed')
        # Scale off: unchanged.
        set_scale(a,0)
        a.ev = []; a.call(on_fn,(61,100)); a.call(off_fn,(61,))
        need(('von',src,61,100) in a.ev and ('voff',src,61) in a.ev,'Scale off changed MIDI notes')
    return {'DIN_and_USB_notes':256,'change_while_held':True}


def seq_machine(img,chord,vel=100,fields=(0,0,0)):
    a = audio_machine(img); blank_pattern(a)
    a.u.mem_write(V+0xDC,bytes([6]))
    a.call(0x208198,(0,1)); a.u.mem_write(PATTERN+6,b'\xff\xff')
    if any(fields):
        a.u.mem_write(PATTERN,set_prb3(a.data(PATTERN,1920),[100]*16,ext=fields[0],humanize=fields[1],octave=fields[2]))
    set_step(a,0,chord,velocity=vel)
    watch(a)
    return a


def seq_play(a):
    a.ev = []
    a.call(0x20B7BE,(0,))
    ons = [(e[2],e[3]) for e in a.ev if e[0] == 'von' and e[1] == 0x10]
    slots = [a.data(0x20003DC4+4*i,4) for i in range(6)]
    for i in range(6): a.call(0x20B774,(i,))
    offs = [e[2] for e in a.ev if e[0] == 'voff' and e[1] == 0x10]
    return ons,offs,slots


def verify_sequencer_live(original,patched):
    chord = [61,63,66,68,70]
    # Option off: notes as recorded, identical to the original firmware.
    a = seq_machine(patched,chord); set_scale(a,1,1,0,seq=0)
    ons,offs,_ = seq_play(a)
    b = seq_machine(original,chord)
    ons_o,offs_o,_ = seq_play(b)
    need(sorted(n for n,_ in ons) == chord and ons == ons_o and offs == offs_o,'Live option off changed the sequence')
    need(sounding(a) == [],'Sequencer voices left sounding')
    # Option on: corrected notes, note-off of the same notes.
    for scale,tonic in [(1,0),(8,0),(2,9),(14,4)]:
        a = seq_machine(patched,chord); set_scale(a,1,scale,tonic,seq=1)
        ons,offs,slots = seq_play(a)
        want = sorted(model(n,scale,tonic) for n in chord)
        need(sorted(n for n,_ in ons) == want,f'Live scale wrong: {ons} vs {want}')
        # Two chord notes may land on the same scale note: the native voice
        # manager then reuses one voice (as for a duplicate note in a step).
        need(set(offs) == set(want),'Sequencer note-off does not match')
        need(sorted(s[0] for s in slots if s[2]) == want,'Slot table does not keep the played note')
        need(sounding(a) == [],'Sequencer voices left sounding')
    # Option on, scale off: unchanged.
    a = seq_machine(patched,chord); set_scale(a,0,1,0,seq=1)
    ons,_,_ = seq_play(a)
    need(sorted(n for n,_ in ons) == chord,'Scale off but live option changed notes')
    # Pattern data never modified by the live option.
    a = seq_machine(patched,chord); set_scale(a,1,1,0,seq=1)
    before = a.data(PATTERN,1920); seq_play(a)
    need(a.data(PATTERN,1920) == before,'Live option modified the pattern')
    return {'option_off_identical_to_original':True,'scales_checked':4,'note_offs_match':True}


def verify_humanize_octave(original,patched):
    chord = [60,64,67]
    # Level 0: exact.
    a = seq_machine(patched,chord,vel=80,fields=(0,0,0))
    ons,_,_ = seq_play(a)
    need(sorted(ons) == [(60,80),(64,80),(67,80)],'Level 0 changed notes or velocity')
    # Humanize 15: velocity within 80 +- 45, varying; notes unchanged.
    vels = set()
    a = seq_machine(patched,chord,vel=80,fields=(0,15,0))
    for _ in range(40):
        ons,offs,_ = seq_play(a)
        need(sorted(n for n,_ in ons) == chord and sorted(offs) == chord,'Humanize changed the notes')
        vels.update(v for _,v in ons)
    need(min(vels) >= 35 and max(vels) <= 125 and len(vels) > 10,f'Humanize velocity range wrong: {sorted(vels)}')
    # Extreme velocities stay in 1..127.
    a = seq_machine(patched,chord,vel=126,fields=(0,15,0))
    for _ in range(20):
        ons,_,_ = seq_play(a)
        need(all(1 <= v <= 127 for _,v in ons),'Velocity out of range')
    # Humanize 5: +- 15.
    a = seq_machine(patched,chord,vel=80,fields=(0,5,0))
    vs = set()
    for _ in range(40):
        ons,_,_ = seq_play(a); vs.update(v for _,v in ons)
    need(min(vs) >= 65 and max(vs) <= 95,'Humanize 5 range wrong')
    # Octave 15: always an octave up or down, both directions, offs match.
    a = seq_machine(patched,chord,fields=(0,0,15))
    shifts = set()
    for _ in range(30):
        ons,offs,_ = seq_play(a)
        need(sorted(n for n,_ in ons) == sorted(offs),'Octave jump note-off mismatch')
        for (n,_),c in zip(sorted(ons,key=lambda x: x[0] % 12),sorted(chord,key=lambda x: x % 12)):
            shifts.add(n-c)
        need(sounding(a) == [],'Octave jump left a voice sounding')
    need(shifts == {12,-12},f'Octave 15 shifts wrong: {shifts}')
    # Octave 7: some notes jump, some do not.
    a = seq_machine(patched,chord,fields=(0,0,7))
    same = jump = 0
    for _ in range(40):
        ons,_,_ = seq_play(a)
        for n,_ in ons:
            if n in chord: same += 1
            else: jump += 1
    need(same > 10 and jump > 10,'Octave 7 not a mix')
    # Range: top notes jump down instead of above 127.
    a = seq_machine(patched,[120,124],fields=(0,0,15))
    for _ in range(20):
        ons,_,_ = seq_play(a)
        need(all(0 <= n <= 127 for n,_ in ons),'Octave jump out of range')
    # Combined with the live scale: still in scale.
    a = seq_machine(patched,[61,66],fields=(0,0,15)); set_scale(a,1,1,0,seq=1)
    for _ in range(10):
        ons,_,_ = seq_play(a)
        need(all(model(n,1,0) == n for n,_ in ons),'Octave + scale left the scale')
    # Arpeggio mode bits are independent.
    p = set_prb3(bytes(seq_machine(patched,chord).data(PATTERN,1920)),[100]*16,ext=5,humanize=3,octave=9)
    need(get_prb3_fields(p) == (5,3,9),'Field packing')
    return {'humanize_levels':[0,5,15],'octave_levels':[0,7,15],'ranges_ok':True}


def verify_recording_note(original,patched):
    # The native recorder (0x20B480, record slots at 0x20003D54) is fed by the
    # voice note-on path with the note given to the voice: the corrected one.
    a = kmachine(patched)
    rec = []
    a.hook(0x20B480,lambda: rec.append((a.u.reg_read(REGS[0]),a.u.reg_read(REGS[1]))))
    o = octave(a)
    set_scale(a,1,8,0)
    for key in range(27):
        rec.clear()
        a.call(0x20AA60,(key,100)); a.call(0x20AAB8,(key,))
        want = model(key+12*o+5,8,0)
        need(rec and rec[0] == (want,100),f'Recorder got {rec}, expected {want}')
        need(all(n == want for n,_ in rec),'Recorder note-off with another note')
    for on_fn,off_fn in [(0x20AB2C,0x20AB64),(0x20ABC0,0x20ABF8)]:
        rec.clear(); a.call(on_fn,(61,90)); a.call(off_fn,(61,))
        need(rec and all(n == 62 for n,_ in rec),'Recorder got the uncorrected MIDI note')
    return {'recorder_receives_corrected_note':True}


def page(img):
    a = panel.machine(img)
    panel.enter(a)
    return a


def press(a,b):
    panel.button(a,b,True); panel.button(a,b,False)


def key(a,step):
    panel.select(a,step) if False else None
    a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(step),)); a.call(0x20FC18,(0,))


def verify_panel_modes(original,patched):
    a = page(patched)
    for _ in range(3): press(a,6)
    panel.check_display(a,'HU 00    ')
    before = a.data(PATTERN,1920)
    seen = set()
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*15+63)//127; seen.add(want)
        p = a.data(PATTERN,1920)
        need(get_prb3_fields(p) == (0,want,0),'HU slider write wrong')
        need(p[:OFFSET] == before[:OFFSET] and p[OFFSET+28:] == before[OFFSET+28:],'HU slider damaged pattern')
        need(get_prb2(p)[0] == [100]*16,'HU slider touched probabilities')
        panel.check_display(a,f'HU {want:02}    ')
    need(seen == set(range(16)),'Not every humanize level reachable')
    press(a,6)
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*15+63)//127
        need(get_prb3_fields(a.data(PATTERN,1920)) == (0,15,want),'OC slider write wrong')
        panel.check_display(a,f'OC {want:02}    ')
    # Probability edits keep the fields; fields keep the probabilities.
    # (1.20: OC -> SC -> tn -> FX -> dt -> Fb -> CR -> P)
    for _ in range(7): press(a,6)
    panel.select(a,6); a.call(0x2059D0,(3,64,0,0))
    p = a.data(PATTERN,1920)
    need(get_prb2(p)[0][6] == 50 and get_prb3_fields(p) == (0,15,15),'Probability edit lost HU/OC')
    for _ in range(3): press(a,6)
    a.call(0x2059D0,(3,0,0,0))
    p = a.data(PATTERN,1920)
    need(get_prb2(p)[0][6] == 50 and get_prb3_fields(p) == (0,0,15),'HU edit lost probability')
    # SC: scale names, slider over the 15 scales.
    press(a,6); press(a,6)
    seen = set()
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*14+63)//127; seen.add(want)
        need(a.data(STATE+1,1)[0] == want,'SC slider wrong')
        panel.check_display(a,'SC '+SCALE_NAMES[want]+'--')
    need(seen == set(range(15)),'Not every scale reachable')
    pat = a.data(PATTERN,1920)
    key(a,15)
    need(a.data(STATE+3,1) == b'\1','Key 16 did not switch the live option on')
    panel.check_display(a,'SEQ SI   ')
    key(a,15); panel.check_display(a,'SEQ NO   ')
    need(a.data(STATE+3,1) == b'\0','Key 16 did not switch the live option off')
    for k in range(15):
        key(a,k)
        need(a.data(STATE+3,1) == b'\0','Other keys changed the option')
    need(a.data(PATTERN,1920) == pat,'SC keys modified the pattern')
    # tn: tonic.
    press(a,6)
    seen = set()
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*11+63)//127; seen.add(want)
        need(a.data(STATE+2,1)[0] == want,'tn slider wrong')
        panel.check_display(a,'tn '+TONIC_NAMES[want]+'  ')
    need(seen == set(range(12)),'Not every tonic reachable')
    # Glyphs: every new text has visible characters.
    for t in SCALE_NAMES+TONIC_NAMES+['SCALA ON','SCALA OFF','SEQ SI','SEQ NO','HU','OC','tn']:
        g = panel.glyphs(a,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    # Leaving the page keeps the global settings.
    panel.button(a,0,True); panel.button(a,0,False)
    need(a.data(0x3F00,1) == b'\0','Page did not close')
    need(a.data(STATE+1,2) == bytes([14,11]),'Settings lost on leaving the page')
    return {'HU_OC_levels':16,'scales':15,'tonics':12,'seq_key':True}


def func_save(a):
    panel.button(a,0,True)
    a.u.mem_write(0x200028EE,bytes([1 | (1 << 5)]))
    for _ in range(3): panel.scan(a)
    a.u.mem_write(0x200028EE,bytes([1]))
    for _ in range(3): panel.scan(a)
    panel.button(a,0,False)


def verify_func_save(original,patched):
    a = panel.machine(patched)
    need(a.data(STATE,4) == bytes([0,1,0,0]),'Initial scale state wrong (off, MAG, DO, live off)')
    pat = a.data(PATTERN,1920)
    func_save(a)
    need(a.data(STATE,1) == b'\1' and 'SCALA ON ' in a.texts,'FUNC+SAVE did not switch the scale on')
    func_save(a)
    need(a.data(STATE,1) == b'\0' and 'SCALA OFF' in a.texts,'FUNC+SAVE did not switch the scale off')
    need(a.data(PATTERN,1920) == pat,'FUNC+SAVE changed the pattern')
    need(a.data(0x200029DA,1) == b'\0','FUNC+SAVE left the panel in FUNC mode')
    # Compare the rest of the RAM with the original firmware doing the same.
    b = panel.machine(original)
    func_save(b); func_save(b)
    ra,rb = a.data(0x20000000,0x5800),b.data(0x20000000,0x5800)
    diff = [hex(0x20000000+i) for i,(x,y) in enumerate(zip(ra,rb)) if x != y]
    # Allowed: display/text buffers (our message) and LED/blink buffers.
    allowed = lambda ad: 0x20002700 <= ad < 0x20002A00
    bad = [d for d in diff if not allowed(int(d,16))]
    need(not bad,'FUNC+SAVE changed state the original does not: '+','.join(bad[:10]))
    # SAVE alone still reaches the native handler (no FUNC).
    c = panel.machine(patched)
    panel.button(c,5,True); panel.button(c,5,False)
    need(c.data(STATE,1) == b'\0','SAVE alone switched the scale')
    return {'toggle':True,'pattern_untouched':True,'ram_vs_original_outside_display':len(bad) == 0}


TASKS = [('v117/scale_keyboard',verify_scale_keyboard),
         ('v117/release_after_change',verify_release_after_change),
         ('v117/midi_in',verify_midi_in),
         ('v117/sequencer_live',verify_sequencer_live),
         ('v117/humanize_octave',verify_humanize_octave),
         ('v117/recording_note',verify_recording_note),
         ('v117/panel_modes',verify_panel_modes),
         ('v117/func_save',verify_func_save)]

if __name__ == '__main__':
    from build_patch import build
    o,p,*_ = build()
    only = sys.argv[1:]
    failed = 0
    for name,fn in TASKS:
        if only and not any(x in name for x in only): continue
        try:
            print(name,'PASS',fn(o,p),flush=True)
        except Exception as e:
            failed += 1
            import traceback; traceback.print_exc()
            print(name,'FAIL',type(e).__name__,e,flush=True)
    raise SystemExit(1 if failed else 0)
