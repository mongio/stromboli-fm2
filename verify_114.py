"""1.14 feature tests: execute the real patched ARM bytes in the emulator.

Covers step conditions (with the native clock and the native transport start),
pattern probability scale, PRB2 validation/fail-open, PRB1 compatibility and
conversion, page modes, quick commands, persistence and native +/- regression.
"""
import random
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
import reverse_checks as native
from arm_checks import REGS
import verify_panel as panel
from probability_format import get_prb2,set_prb2,set_profile,get_profile,OFFSET

COND = {1:(1,2),2:(2,2),3:(1,3),4:(2,3),5:(3,3),6:(1,4),7:(2,4),8:(3,4),9:(4,4)}
COND_TEXT = ['OFF ','1-2 ','2-2 ','1-3 ','2-3 ','3-3 ','1-4 ','2-4 ','3-4 ','4-4 ','1ST ','N1ST']


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def expected_play(cond,loop):
    if cond == 0: return True
    if cond == 10: return loop == 0
    if cond == 11: return loop > 0
    a,b = COND[cond]
    return loop % b == a-1


def clocked(img,mask=0xFFFF):
    a = native.sequencer_observer(img)
    native.prepare_clock(a,mask)
    a.u.mem_write(native.PATTERN+6,b'\xff\xff')
    for i in range(16):
        native.set_step(a,i,[40+i],0xA0)
    return a


def passes(a,count,steps_per_pass=16):
    """Run the native clock; returns, per pass, the set of steps that played."""
    out = []
    for _ in range(count):
        a.events = []
        for _ in range(steps_per_pass):
            a.call(0x208CF8,(1,0))
        out.append(sorted({e[1][0]-40 for e in a.events if e[0] == 'on'}))
    return out


def verify_conditions(original,patched):
    # Steps 0..11 carry conditions 0..11; steps 12..15 have none.
    a = clocked(patched)
    conds = list(range(12))+[0]*4
    a.u.mem_write(native.PATTERN,set_prb2(a.data(native.PATTERN,1920),[100]*16,conds))
    draws = []
    a.hook(0x2094A4,lambda: draws.append(1))
    played = passes(a,25)
    for loop,steps in enumerate(played):
        want = [s for s in range(16) if expected_play(conds[s],loop)]
        need(steps == want,f'Condition mismatch on pass {loop}: {steps} != {want}')
    need(not draws,'Conditions at 100% consumed randomness')
    need(a.data(0x3F12,2) == struct.pack('<H',24),'Loop counter wrong after 25 passes')
    # Active step mask 0x0005: a pass is two steps long.
    b = clocked(patched,0x0005)
    b.u.mem_write(native.PATTERN,set_prb2(b.data(native.PATTERN,1920),[100]*16,
                                          [1,0,7]+[0]*13))
    played = passes(b,12,2)
    for loop,steps in enumerate(played):
        want = [0] if expected_play(1,loop) else []
        if expected_play(7,loop): want.append(2)
        need(steps == want,f'Active-step pass counting failed on pass {loop}')
    return {'conditions_checked':11,'passes':25,'active_step_mask_0005':True,
            'no_randomness_for_conditions':True}


def verify_transport_reset(original,patched):
    a = clocked(patched)
    a.u.mem_write(native.PATTERN,set_prb2(a.data(native.PATTERN,1920),[100]*16,[10,11]+[0]*14))
    # Native PLAY through the patched button veneer: start resets loop state.
    m = panel.machine(patched)
    m.u.mem_write(native.PATTERN+6,b'\xff\xff')
    for i in range(16): native.set_step(m,i,[40+i],0xA0)
    m.u.mem_write(native.PATTERN,set_prb2(m.data(native.PATTERN,1920),[100]*16,[10,11]+[0]*14))
    m.u.mem_write(0x3F10,b'\x07\x01\x05\x00')      # stale state from an earlier run
    m.call(0x20FAA0,(3,1))
    need(m.get32(0x20003F8C) == 1,'PLAY did not start')
    need(m.data(0x3F10,4) == b'\xff\x00\x00\x00','Transport start did not reset loop state')
    # Continue (r2 = 0) keeps the counter; start (r2 = 1) resets it.
    m.u.mem_write(0x3F10,b'\x03\x01\x02\x00')
    m.call(0x2090C0,(1,0,0))
    need(m.data(0x3F10,4) == b'\x03\x01\x02\x00','Continue reset the loop state')
    m.call(0x2090C0,(1,0,1))
    need(m.data(0x3F10,4) == b'\xff\x00\x00\x00','Start did not reset the loop state')
    # FIRST plays only on the first pass after start, NOT FIRST afterwards.
    played = passes(a,3)
    need([0 in p for p in played] == [True,False,False],'FIRST condition wrong')
    need([1 in p for p in played] == [False,True,True],'NOT FIRST condition wrong')
    a.call(0x2090C0,(1,0,1)); native.prepare_clock(a)
    played = passes(a,2)
    need([0 in p for p in played] == [True,False],'FIRST after restart wrong')
    return {'native_PLAY_resets':True,'continue_keeps_counter':True,'first_not_first_after_restart':True}


def verify_scale_and_probability(original,patched):
    a = native.sequencer_observer(patched)
    native.set_step(a,0,[48,55,60],0xA0)
    a.draw = 0; a.calls = 0
    def draw():
        need(a.u.reg_read(REGS[0]) == 100,'Wrong PRNG modulus')
        a.calls += 1; a.return_(a.draw)
    a.hook(0x2094A4,draw)
    cases = 0
    for p in [0,1,25,50,99,100]:
        for g in [0,1,30,50,99,100]:
            eff = (p*g+50)//100
            a.u.mem_write(native.PATTERN,set_prb2(a.data(native.PATTERN,1920),[p]*16,None,g))
            before = a.calls
            for d in range(100):
                a.draw = d; a.events = []
                a.u.mem_write(native.SLOTS,bytes(0x34))
                a.call(0x20B7BE,(0,))
                ons = [e for e in a.events if e[0] == 'on']
                need(len(ons) == (3 if d < eff else 0),f'p={p} g={g} draw={d}')
                cases += 1
            need(a.calls-before == (0 if eff in (0,100) else 100),'Randomness at 0/100 effective')
    # A failing condition never consumes randomness.
    a.u.mem_write(native.PATTERN,set_prb2(a.data(native.PATTERN,1920),[50]*16,[2]*16,100))
    a.u.mem_write(0x3F10,b'\xff\x00\x00\x00')
    before = a.calls; a.events = []
    a.call(0x20B7BE,(0,))
    need(a.calls == before and not [e for e in a.events if e[0] == 'on'],'Failed condition consumed PRNG')
    return {'cases':cases,'effective_probability':'(p*scale+50)//100'}


def verify_prb2_fail_open(original,patched):
    a = native.sequencer_observer(patched)
    native.set_step(a,0,[60],0xA0)
    a.hook(0x2094A4,lambda: a.return_(99))
    good = set_prb2(a.data(native.PATTERN,1920),[0]*16,[0]*16,100)
    a.u.mem_write(native.PATTERN,good); a.events = []
    a.call(0x20B7BE,(0,)); need(not a.events,'Valid PRB2 0% played')
    flipped = 0
    for bit in range(28*8):
        bad = bytearray(good); bad[OFFSET+bit//8] ^= 1 << (bit % 8)
        a.u.mem_write(native.PATTERN,bytes(bad)); a.events = []
        a.u.mem_write(native.SLOTS,bytes(0x34))
        a.call(0x20B7BE,(0,))
        need([e[0] for e in a.events] == ['on'],f'Corrupted bit {bit} did not fall back to 100%')
        flipped += 1
    # PRB1 (1.13) is still honoured when no PRB2 is present.
    a.u.mem_write(native.PATTERN,set_profile(good,[0]*16)); a.events = []
    a.u.mem_write(native.SLOTS,bytes(0x34))
    a.call(0x20B7BE,(0,)); need(not [e for e in a.events if e[0] == 'on'],'PRB1 0% not honoured')
    a.u.mem_write(native.PATTERN,set_profile(good,[100]*16)); a.events = []
    a.call(0x20B7BE,(0,)); need([e[0] for e in a.events] == ['on'],'PRB1 100% not honoured')
    return {'single_bit_corruptions':flipped,'PRB1_still_played':True}


def page_machine(patched,pattern=None):
    m = panel.machine(patched)
    if pattern is not None:
        m.u.mem_write(native.PATTERN,pattern)
    panel.enter(m)
    return m


def press(m,index):
    panel.button(m,index,True); panel.button(m,index,False)


def key(m,step):
    m.call(0x20FC18,(0,))
    m.call(0x20FC18,(panel.raw_for_step(step),))
    m.call(0x20FC18,(0,))


def verify_modes_and_sliders(original,patched):
    m = page_machine(patched)
    panel.check_display(m,'01 P100  ')
    press(m,6); panel.check_display(m,'01 C OFF ')
    press(m,6); panel.check_display(m,'GL P100  ')
    # 1.17: HU, OC, SC, tn follow GL
    press(m,6); panel.check_display(m,'HU 00    ')
    press(m,6); panel.check_display(m,'OC 00    ')
    press(m,6); panel.check_display(m,'SC MAG --')
    press(m,6); panel.check_display(m,'tn DO    ')
    # 1.18: FX, dt, Fb follow tn
    press(m,6); panel.check_display(m,'FX REVRB ')
    press(m,6); panel.check_display(m,'dt 3-16  ')
    press(m,6); panel.check_display(m,'Fb 050 MO')
    # 1.22: MOD, rt, rS follow Fb; then CR (1.20)
    press(m,6); panel.check_display(m,'CHORUS   ')
    press(m,6); panel.check_display(m,'rt --    ')
    press(m,6); panel.check_display(m,'rS --    ')
    press(m,6); panel.check_display(m,'dr AVANTI')
    press(m,6); panel.check_display(m,'Mu 000  3')
    press(m,6); panel.check_display(m,'CR OFF   ')
    press(m,6); panel.check_display(m,'01 P100  ')
    press(m,7); panel.check_display(m,'CR OFF   ')
    for _ in range(13): press(m,7)
    panel.check_display(m,'GL P100  ')
    press(m,7); panel.check_display(m,'01 C OFF ')
    need(m.data(0x3F00,1) == b'\1','Mode buttons closed the page')
    # Condition slider over all 128 positions on step 9.
    panel.select(m,8)
    seen = set()
    for v in range(128):
        before = m.data(native.PATTERN,1920)
        m.call(0x2059D0,(3,v,0,0))
        c = (v*11+63)//127; seen.add(c)
        probs,conds,scale,ok = get_prb2(m.data(native.PATTERN,1920))
        need(ok and conds[8] == c and conds[:8]+conds[9:] == [0]*15,'Condition slider write wrong')
        need(probs == [100]*16 and scale == 100,'Condition slider touched other values')
        after = m.data(native.PATTERN,1920)
        need(after[:OFFSET] == before[:OFFSET] and after[OFFSET+28:] == before[OFFSET+28:],
             'Condition slider damaged pattern data')
        panel.check_display(m,'09 C '+COND_TEXT[c]+'')
    need(seen == set(range(12)),'Not every condition reachable')
    # Scale slider.
    press(m,6)
    for v in range(128):
        m.call(0x2059D0,(3,v,0,0))
        g = (v*100+63)//127
        probs,conds,scale,ok = get_prb2(m.data(native.PATTERN,1920))
        need(ok and scale == g,'Scale slider write wrong')
        panel.check_display(m,f'GL P{g:03}  ')
    # Probability mode still works (and keeps condition / scale).
    # (1.23: GL -> HU -> OC -> SC -> tn -> FX -> dt -> Fb -> MOD -> rt -> rS -> dr -> Mu -> CR -> P)
    for _ in range(14): press(m,6)
    panel.select(m,2); m.call(0x2059D0,(3,64,0,0))
    panel.check_display(m,'03 P050  ')
    probs,conds,scale,ok = get_prb2(m.data(native.PATTERN,1920))
    need(ok and probs[2] == 50 and conds[8] == 11 and scale == 100,'P mode edit lost other values')
    # Leave and re-enter: mode returns to P.
    panel.button(m,0,True); panel.button(m,0,False)
    need(m.data(0x3F00,1) == b'\0','FUNC did not close page')
    panel.enter(m); panel.check_display(m,'01 P100  ')
    need(m.data(0x3F02,1) == b'\0','Mode not reset on entry')
    return {'mode_cycle_plus_minus':True,'condition_positions':128,'scale_positions':128}


def verify_prb1_conversion(original,patched):
    blank = panel.machine(patched).data(native.PATTERN,1920)
    old = set_profile(blank,[10*i % 101 for i in range(16)])
    m = page_machine(patched,old)
    panel.select(m,3); panel.check_display(m,'04 P030  ')
    need(m.data(native.PATTERN,1920) == old,'Viewing a 1.13 pattern modified it')
    press(m,6); m.call(0x2059D0,(3,127,0,0))          # condition N1ST on step 4
    probs,conds,scale,ok = get_prb2(m.data(native.PATTERN,1920))
    need(ok and probs == [10*i % 101 for i in range(16)],'PRB1 probabilities lost in conversion')
    need(conds == [0,0,0,11]+[0]*12 and scale == 100,'Conversion defaults wrong')
    return {'PRB1_probabilities_kept':True,'converted_on_first_edit_only':True}


def verify_commands(original,patched):
    m = page_machine(patched)
    # Prepare step 5: 30% with condition 1-2, then copy it to all steps.
    panel.select(m,4); m.call(0x2059D0,(3,38,0,0))
    press(m,6); m.call(0x2059D0,(3,12,0,0))
    probs,conds,_,ok = get_prb2(m.data(native.PATTERN,1920))
    need(ok and probs[4] == 30 and conds[4] == 1,'Fixture for copy failed')
    press(m,6)                                          # mode G
    panel.check_display(m,'GL P100  ')
    key(m,5); panel.check_display(m,'COPY ALL ')
    probs,conds,scale,ok = get_prb2(m.data(native.PATTERN,1920))
    need(ok and probs == [30]*16 and conds == [1]*16,'Copy command failed')
    need(m.data(0x3F01,1) == b'\4','Command key changed the selected step')
    for k,(text,value) in enumerate([('ALL 100  ',100),('ALL 75   ',75),('ALL 50   ',50),('ALL 25   ',25)]):
        key(m,k); panel.check_display(m,text)
        probs,conds,_,ok = get_prb2(m.data(native.PATTERN,1920))
        need(ok and probs == [value]*16 and conds == [1]*16,'Fill command failed: '+text)
    key(m,6); panel.check_display(m,'COND OFF ')
    probs,conds,_,ok = get_prb2(m.data(native.PATTERN,1920))
    need(ok and conds == [0]*16 and probs == [25]*16,'Condition clear failed')
    key(m,4); panel.check_display(m,'RANDOM   ')
    probs,conds,_,ok = get_prb2(m.data(native.PATTERN,1920))
    need(ok and set(probs) <= {25,50,75,100} and len(set(probs)) > 1,'Random command failed')
    m.call(0x2059D0,(3,64,0,0)); panel.check_display(m,'GL P050  ')
    key(m,7); panel.check_display(m,'RESET ALL')
    probs,conds,scale,ok = get_prb2(m.data(native.PATTERN,1920))
    need(ok and probs == [100]*16 and conds == [0]*16 and scale == 100,'Reset failed')
    before = m.data(native.PATTERN,1920)
    for k in range(8,15):
        key(m,k)
        need(m.data(native.PATTERN,1920) == before,'Keys 9-15 changed the pattern')
    panel.check_display(m,'RESET ALL')
    key(m,15); panel.check_display(m,'BETA 1.23')
    need(m.data(native.PATTERN,1920) == before,'Key 16 changed the pattern')
    # Mode change clears the message.
    press(m,7); press(m,7); panel.check_display(m,'05 P100  ')
    return {'commands':8,'keys_9_15_inert':True,'key_16_shows_version':True,'selection_kept':True}


def verify_persistence(original,patched):
    m = page_machine(patched)
    panel.select(m,1); m.call(0x2059D0,(3,64,0,0))
    press(m,6); m.call(0x2059D0,(3,60,0,0))
    press(m,6); m.call(0x2059D0,(3,100,0,0))
    p = m.data(native.PATTERN,1920)
    probs,conds,scale,ok = get_prb2(p)
    need(ok and probs[1] == 50 and conds[1] == 5 and scale == 79,'Fixture failed')
    panel.button(m,0,True)
    s = native.Storage(patched); s.store(9,p); s.flush()
    reboot = native.Storage(patched,s.flash); accepted,loaded = reboot.load(9)
    need(accepted == 1 and loaded == p,'PRB2 did not survive NOR journal and reboot')
    return {'NOR_journal_reboot_exact':True}


def verify_native_buttons_outside_page(original,patched):
    for index in (6,7,1,2,5):
        a = panel.machine(original); b = panel.machine(patched)
        for x in (a,b):
            panel.button(x,index,True); panel.button(x,index,False)
        need(a.data(0x20000000,0x5800) == b.data(0x20000000,0x5800),
             f'Button {index} outside the page differs from original')
    return {'buttons_compared':[6,7,1,2,5]}


def verify_page_while_playing(original,patched):
    a = clocked(patched)
    a.u.mem_write(native.PATTERN,set_prb2(a.data(native.PATTERN,1920),[100]*16,[1]+[0]*15))
    a.u.mem_write(0x200029E4,struct.pack('<i',-1)); a.u.mem_write(0x200029F0,struct.pack('<i',-1))
    a.u.mem_write(0x2000143E,struct.pack('<H',2048))
    a.texts = []; a.hook(0x2058A8,lambda: a.texts.append(a.string(a.u.reg_read(REGS[1]))))
    panel.enter(a); press(a,6); press(a,6)
    played = passes(a,4)
    need([0 in p for p in played] == [True,False,True,False],'Conditions wrong with page open')
    panel.check_display(a,'GL P100  ')
    return {'clock_with_page_in_mode_G':True}


TASKS = [('v114/conditions',verify_conditions),
         ('v114/transport_reset',verify_transport_reset),
         ('v114/scale_and_probability',verify_scale_and_probability),
         ('v114/prb2_fail_open',verify_prb2_fail_open),
         ('v114/modes_and_sliders',verify_modes_and_sliders),
         ('v114/prb1_conversion',verify_prb1_conversion),
         ('v114/commands',verify_commands),
         ('v114/persistence',verify_persistence),
         ('v114/native_buttons_outside_page',verify_native_buttons_outside_page),
         ('v114/page_while_playing',verify_page_while_playing)]

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
