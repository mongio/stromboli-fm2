"""1.15 HOLD tests: execute the real patched ARM bytes in the emulator.

HOLD is a virtual damper pedal (bit 0x04 of the native damper bytes). The
tests drive the real keyboard veneer, the real button debouncer, the native
MIDI note wrappers, the native sequencer note wrappers and the native voice
tick that releases damped voices.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
import verify_panel as panel

V = 0x20003C6C


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def voices(a):
    d = a.data(V,0x60)
    return [(d[16*i],d[16*i+1],d[16*i+2],d[16*i+8]) for i in range(6)]


def sounding(a):
    """Notes of active voices, with their key-held flag."""
    return sorted((v[3],v[2]) for v in voices(a) if v[0])


def machine(img):
    a = panel.machine(img)
    a.u.mem_write(V+0xDC,bytes([6]))
    return a


def func_button(a,index):
    panel.button(a,0,True)
    a.u.mem_write(0x200028EE,bytes([1 | (1 << index)]))
    for _ in range(3): panel.scan(a)
    a.u.mem_write(0x200028EE,bytes([1]))
    for _ in range(3): panel.scan(a)
    panel.button(a,0,False)


def keys(a,*steps):
    raw = 0
    for s in steps: raw |= panel.raw_for_step(s)
    a.call(0x20FC18,(raw,))


def verify_hold_toggle(original,patched):
    a = machine(patched)
    before = a.data(V+0xE2,2)
    func_button(a,6)
    need(a.data(0x3F14,1) == b'\1','FUNC+OCTAVE+ did not switch HOLD on')
    need(a.data(V+0xE2,2) == bytes([before[0] | 4,before[1] | 4]),'Damper bits not set')
    need('HOLD ON  ' in a.texts,'HOLD ON not shown')
    func_button(a,6)
    need(a.data(0x3F14,1) == b'\0','Second FUNC+OCTAVE+ did not switch HOLD off')
    need(a.data(V+0xE3,1)[0] & 4 == 0,'Damper target bit not cleared')
    need('HOLD OFF ' in a.texts,'HOLD OFF not shown')
    a.call(0x20AF08,())
    need(a.data(V+0xE2,2) == before,'Native tick did not restore damper bytes')
    func_button(a,7)
    need(a.data(0x3F15,1) == b'\1' and 'T SPEGNE ' in a.texts,'FUNC+OCTAVE- did not select SPEGNE')
    func_button(a,7)
    need(a.data(0x3F15,1) == b'\0' and 'T RIPARTE' in a.texts,'FUNC+OCTAVE- did not select RIPARTE')
    return {'hold_toggle':True,'tasto_toggle':True,'damper_restored':True}


def verify_hold_keyboard(original,patched):
    a = machine(patched)
    keys(a,0); keys(a)
    need(sounding(a) == [],'Without HOLD a released key must stop')
    func_button(a,6)
    keys(a,0,2,4)
    held = sounding(a)
    need(len(held) == 3 and all(f == 1 for _,f in held),'Chord not playing')
    keys(a)
    kept = sounding(a)
    need([n for n,_ in kept] == [n for n,_ in held] and all(f == 0 for _,f in kept),
         'HOLD did not keep the released chord')
    for _ in range(5): a.call(0x20AF08,())
    need(len(sounding(a)) == 3,'Voice tick released notes while HOLD is on')
    # A CC64 pedal (native bit 0x01) keeps the notes after HOLD is switched off.
    a.u.mem_write(V+0xE2,bytes([a.data(V+0xE2,1)[0] | 1,a.data(V+0xE3,1)[0] | 1]))
    func_button(a,6)
    a.call(0x20AF08,())
    need(len(sounding(a)) == 3,'HOLD off released notes held by the CC64 pedal')
    a.u.mem_write(V+0xE3,bytes([a.data(V+0xE3,1)[0] & ~1 & 0xFF]))
    a.call(0x20AF08,())
    need(sounding(a) == [],'Notes not released when HOLD and pedal are both off')
    return {'drone_kept':3,'released_on_HOLD_off':True,'CC64_pedal_respected':True}


def verify_riparte(original,patched):
    a = machine(patched)
    func_button(a,6)
    keys(a,0); keys(a)
    note = sounding(a)[0][0]
    # RIPARTE without arpeggiator: pressing the held note again restarts it.
    keys(a,0)
    s = sounding(a)
    need(s == [(note,1)],'RIPARTE did not restart the held note')
    keys(a)
    keys(a,2); keys(a)
    need(len(sounding(a)) == 2,'A new note must add to the drone without arpeggiator')
    # With the arpeggiator on, a chord started with no key held replaces it.
    a.call(0x2059D0,(7,20,0,0))
    need(a.data(0x20003E11,1) != b'\0','Arpeggiator not switched on')
    keys(a,7)
    s = sounding(a)
    need(len(s) == 1 and s[0][1] == 1,'New chord did not replace the held one with ARP on')
    keys(a,7,9)
    need(len(sounding(a)) == 2,'Notes added while a key is held must not clear the chord')
    keys(a)
    need(len(sounding(a)) == 2,'Arp chord not kept by HOLD')
    return {'restart_held_note':True,'drone_adds':True,'arp_new_chord_replaces':True}


def verify_spegne(original,patched):
    a = machine(patched)
    func_button(a,6); func_button(a,7)
    keys(a,0); keys(a)
    n0 = sounding(a)[0][0]
    keys(a,4); keys(a)
    s = sounding(a)
    need(len(s) == 2 and all(f == 0 for _,f in s),'Two held notes expected')
    n4 = [n for n,_ in s if n != n0][0]
    keys(a,0)
    need(sounding(a) == [(n4,0)],'SPEGNE did not release exactly the pressed held note')
    keys(a)
    need(sounding(a) == [(n4,0)],'Releasing the key after SPEGNE changed something')
    keys(a,2); keys(a)
    need(len(sounding(a)) == 2,'SPEGNE must add a note that was not held')
    return {'second_press_releases':True,'new_note_adds':True}


def verify_midi_and_sequencer(original,patched):
    a = machine(patched)
    func_button(a,6)
    for wrapper_on,wrapper_off in [(0x20AB2C,0x20AB64),(0x20ABC0,0x20ABF8)]:
        a.call(wrapper_on,(60,100)); a.call(wrapper_off,(60,))
        need((60,0) in sounding(a),'MIDI note not kept by HOLD')
    func_button(a,7)                                 # SPEGNE
    a.call(0x20AB2C,(60,100))
    need(60 not in [n for n,_ in sounding(a)],'SPEGNE did not release the MIDI note')
    a.call(0x20AB64,(60,))
    need(60 not in [n for n,_ in sounding(a)],'MIDI note off after SPEGNE restarted something')
    func_button(a,7)
    # Sequencer notes (source 0x10) are not affected by HOLD.
    b = machine(patched)
    func_button(b,6)
    b.call(0x20AC54,(50,100,0)); b.call(0x20AC70,(50,0))
    need(50 not in [n for n,f in sounding(b)],'Sequencer note was kept by HOLD')
    return {'MIDI_DIN_and_USB_kept':True,'sequencer_unaffected':True}


TASKS = [('v115/hold_toggle',verify_hold_toggle),
         ('v115/hold_keyboard',verify_hold_keyboard),
         ('v115/riparte',verify_riparte),
         ('v115/spegne',verify_spegne),
         ('v115/midi_and_sequencer',verify_midi_and_sequencer)]

if __name__ == '__main__':
    from build_patch import build
    o,p,*_ = build()
    failed = 0
    for name,fn in TASKS:
        try:
            print(name,'PASS',fn(o,p),flush=True)
        except Exception as e:
            failed += 1
            import traceback; traceback.print_exc()
            print(name,'FAIL',type(e).__name__,e,flush=True)
    raise SystemExit(1 if failed else 0)
