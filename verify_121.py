"""1.20: chain options simplified to CR (ON = free chain + recording on it),
FUNC functions during a chain, pattern copy, REC FISSO, Program Change in.

Runs the patched code with the native journal/bank model (Storage), the
native chain selection (through its SRAM veneer, as the panel does), the
native clock and the native transport functions.
"""
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
import reverse_checks as native
from reverse_checks import Storage,PATTERN,CLOCK,pattern_fixture,prepare_clock
from arm_checks import REGS
import verify_panel as panel

ST = 0x1D00
LIST = 0x1C00
CHAIN = 0x20003E34
SEQ = 0x20003F8C
SELECT = 0x20014FC0          # veneer called by the panel for MEMORY + keys
PLAY_ON = 0x20DAE2           # native transport: start (0->1, 2->3)
PLAY_OFF = 0x20DB00          # native transport: stop (1->0, 3->2)
REC_ON = 0x20DB20            # native transport: REC on (0->2, 1->3)


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def machine(img):
    s = Storage(img); a = s.a
    a.pats = [pattern_fixture(a,i) for i in range(16)]
    for i,p in enumerate(a.pats): s.store(i,p)
    a.storage = s
    a.writes = []
    a.hook(0x20815C,lambda: a.writes.append(a.u.reg_read(REGS[0])))
    prepare_clock(a)
    a.call(0x209D60)                 # native reset of motion recording (0x20003638 = 0xFF)
    a.put32(SEQ,0)
    a.texts = []
    a.hook(0x2058A8,lambda: a.texts.append(a.string(a.u.reg_read(REGS[1]))))
    return a


def setopt(a,ch=None,cc=None,cr=None):
    # 1.20: CR sets both the free chain selection (+0) and recording (+2)
    if cr is not None and ch is None: ch = cr
    if ch is not None and cr is None: cr = ch
    for off,v in ((0,ch),(2,cr)):
        if v is not None: a.u.mem_write(ST+off,bytes([v]))


def memory_press(a):
    a.u.mem_write(ST+7,b'\1')


def keys(a,*seq):
    """Key events while MEMORY is held: each item = set of held keys."""
    old = 0
    for held in seq:
        new = sum(1 << k for k in held)
        a.call(SELECT,(CHAIN,new,old))
        old = new
    a.call(SELECT,(CHAIN,0,old))


def current(a): return a.data(PATTERN+9,1)[0]


def play(a,loops):
    """Steps of the native clock; returns the pattern of each loop."""
    out = []
    for _ in range(loops):
        seen = []
        for _ in range(16):
            a.call(0x208CF8,(1,0))
            seen.append(current(a))
        need(len(set(seen)) == 1,'Pattern changed inside a loop: '+str(seen))
        out.append(seen[0])
    return out


def start(a,rec=False):
    if rec: a.call(REC_ON,(SEQ,))
    a.call(PLAY_ON,(SEQ,))


def stop(a): a.call(PLAY_OFF,(SEQ,))


def verify_korg_unchanged(original,patched):
    """CH KORG (power-on): selection and playback identical to the original 1.12."""
    old = original
    cases = [((2,),(2,5)),((0,),(0,15)),((7,),),((3,),(3,4)),((9,),(9,12),(9,12,4))]
    res = []
    for seq in cases:
        got = []
        for img in (old,patched):
            a = machine(img); a.put32(SEQ,1)
            keys(a,*seq)
            got.append((a.data(CHAIN,0x1C),play(a,10)))
        need(got[0] == got[1],f'KORG chain differs from the original for {seq}: {got}')
        res.append(got[1][1])
    # REC: native firmware keeps one pattern; 1.19 with CR off too
    for img in (old,patched):
        a = machine(img); a.put32(SEQ,3)
        keys(a,(2,),(2,6))
        need(a.data(CHAIN+4,2) == bytes([2,255]),'REC did not keep one pattern')
    return {'sequences':res,'rec_single_pattern':True}


def verify_free_chain(original,patched):
    a = machine(patched); setopt(a,ch=1); a.put32(SEQ,1)
    memory_press(a)
    # 3, 3 again, 5, 2 (keys released between presses), and 7+8 together
    keys(a,(2,),(),(2,),(),(4,),(),(1,),(),(6,7))
    need(a.data(ST+3,1) == b'\x05','Free chain length wrong')
    need(a.data(LIST,10) == bytes([2,2,4,1,1,1,6,1,7,1]),'Free chain list wrong: '+a.data(LIST,10).hex())
    need(a.data(ST+4,1) == b'\1' and a.data(CHAIN+0x15,1) == b'\1','Chain mode not on')
    seq = play(a,13)
    need(seq == [2,2,4,1,6,7,2,2,4,1,6,7,2],'Free chain playback wrong: '+str(seq))
    # repeat of the same pattern does not reload it (live edits stay)
    b = machine(patched); setopt(b,ch=1); b.put32(SEQ,1)
    memory_press(b); keys(b,(5,),(),(5,),(),(9,))
    b.u.mem_write(PATTERN+20,b'\x77')
    play(b,1)                         # first loop of 5
    need(play(b,1) == [5] and b.data(PATTERN+20,1) == b'\x77','Repeat reloaded the pattern')
    play(b,1)                         # -> pattern 9 (loaded)
    need(current(b) == 9 and b.data(PATTERN+20,1) == b.pats[9][20:21],'Next pattern not loaded')
    play(b,1)                         # -> pattern 5 reloaded from its bank
    need(current(b) == 5 and b.data(PATTERN+20,1) == b.pats[5][20:21],'Pattern not reloaded on return')
    # a new MEMORY press starts a new chain; one key = single pattern (Korg)
    memory_press(a); keys(a,(11,))
    need(a.data(ST+3,1) == b'\1' and a.data(ST+4,1) == b'\0' and current(a) == 11,'Single key not a single pattern')
    need(play(a,3) == [11,11,11],'Single pattern did not loop')
    # same key pressed three times: one entry, three loops, then wraps
    # (1.21: building while playing keeps the step, so this part starts fresh)
    a = machine(patched); setopt(a,ch=1); a.put32(SEQ,1)
    memory_press(a); keys(a,(3,),(),(3,),(),(3,),(),(8,))
    need(a.data(LIST,4) == bytes([3,3,8,1]),'Repeat count wrong')
    got = play(a,8); need(got == [3,3,3,8,3,3,3,8],'Repeat playback wrong '+str(got)+' step '+str(a.data(CLOCK+0xB,1)[0]))
    # more than 16 entries (native list holds 16)
    a = machine(patched); setopt(a,ch=1); a.put32(SEQ,1)
    memory_press(a)
    seq = []
    for i in range(40):
        seq += [(i % 16,),()]
    keys(a,*seq)
    need(a.data(ST+3,1)[0] == 40 and a.data(CHAIN+0x14,1) == b'\x10','Long chain wrong')
    need(play(a,41) == [i % 16 for i in range(40)]+[0],'Long chain playback wrong')
    # 64 entries maximum
    memory_press(a)
    seq = []
    for i in range(80): seq += [((i*7) % 16,),()]
    keys(a,*seq)
    need(a.data(ST+3,1)[0] == 64,'Chain not limited to 64')
    # STOP, then the native start from the beginning: first entry again
    # (the KORG chain does the same)
    memory_press(a); keys(a,(2,),(),(2,),(),(7,),(),(4,))
    stop(a); a.call(0x2090C0,(1,0,1))   # 1.21: building while playing keeps the step
    need(play(a,3) == [2,2,7],'Free chain before restart')
    stop(a); a.call(0x2090C0,(1,0,1))
    need(play(a,5) == [2,2,7,4,2],'Free chain did not restart from the first entry')
    k = machine(patched); keys(k,(2,),(2,5)); k.put32(SEQ,1); play(k,2)
    stop(k); k.call(0x2090C0,(1,0,1))
    need(play(k,3) == [2,3,4],'KORG chain restart (reference) changed')
    # back to CH KORG: a native selection ends the free chain
    setopt(a,ch=0); keys(a,(4,),(4,6))
    need(a.data(ST+4,1) == b'\0' and play(a,4) == [4,5,6,4],'KORG selection after free chain wrong')
    return {'free_order_and_repeats':True,'repeat_keeps_edits':True,'max_entries':64,'native_list_16':True}


def verify_free_chain_rec(original,patched):
    # CR OFF: REC keeps one pattern (Korg)
    a = machine(patched); a.put32(SEQ,3)
    keys(a,(2,),(2,5))
    need(a.data(CHAIN+4,2) == bytes([2,255]) and a.data(ST+4,1) == b'\0','CR OFF in REC accepted a chain')
    # CR ON: the free chain is accepted in REC
    b = machine(patched); setopt(b,cr=1); b.put32(SEQ,3)
    memory_press(b); keys(b,(2,),(),(5,))
    need(b.data(ST+3,1) == b'\2' and b.data(ST+4,1) == b'\1','REC with CR refused the chain')
    return {'cr_off_rec_single':True,'cr_on_rec_chain':True}


def verify_cr_save(original,patched):
    res = {}
    # CR OFF (as the native firmware): REC keeps one pattern, nothing saved
    a = machine(patched); a.put32(SEQ,2)
    keys(a,(2,),(2,3)); start(a)
    a.u.mem_write(PATTERN+80,b'\x30')
    need(play(a,3) == [2,2,2] and a.writes == [],'CR OFF: chain or save in REC')
    need(a.data(PATTERN+80,1) == b'\x30','CR OFF: recorded data lost')
    stop(a); need(a.writes == [],'STOP saved without CR')
    res['CR_OFF'] = 'single pattern, no automatic save'
    # CR ON: the chain plays while recording; each recorded pattern is saved
    a = machine(patched); setopt(a,cr=1); a.put32(SEQ,2)
    keys(a,(2,),(2,3)); start(a)
    a.u.mem_write(PATTERN+80,b'\x30')   # "recorded" data in pattern 3 (slot 2)
    bank = lambda n: a.data(a.get32(native.ROOT)+n*1920,1920)
    need(play(a,2) == [2,3],'CR ON: chain not playing in REC')
    need(a.writes == [2] and bank(2)[80] == 0x30,'CR did not save the recorded pattern: '+str(a.writes))
    need(play(a,1) == [2] and a.writes == [2],'Unmodified pattern saved')
    need(a.data(PATTERN+80,1) == b'\x30','Recorded pattern lost on return')
    a.u.mem_write(PATTERN+81,b'\x31')   # edit, then STOP while recording
    stop(a)
    need(a.writes == [2,2] and bank(2)[81] == 0x31,'STOP did not save')
    a.storage.flush()
    got,q = Storage(patched,a.storage.flash).load(2)
    need(got == 1 and q[80] == 0x30 and q[81] == 0x31,'Saved pattern not in flash after the journal')
    others = [Storage(patched,a.storage.flash).load(n)[1] == a.pats[n] for n in range(16) if n != 2]
    need(all(others),'Other patterns changed')
    res['CR_ON'] = a.writes
    # CR on but not recording: no saving
    b = machine(patched); setopt(b,cr=1); keys(b,(2,),(2,3)); start(b)
    b.u.mem_write(PATTERN+80,b'\x30'); play(b,2); stop(b)
    need(b.writes == [],'Saved while not recording')
    res['not_recording'] = []
    return res


def ui(img):
    a = machine(img)
    native.blank_pattern(a)
    a.u.mem_write(0x200029E4,struct.pack('<i',-1))
    a.u.mem_write(0x200029F0,struct.pack('<i',-1))
    a.u.mem_write(0x2000143E,struct.pack('<H',2048))
    a.texts = []
    a.hook(0x2058A8,lambda: a.texts.append(a.string(a.u.reg_read(REGS[1]))))
    return a


def verify_panel_memory(original,patched):
    """Real panel path: MEMORY held + keyboard keys, readout, new session."""
    a = ui(patched); setopt(a,ch=1); a.put32(SEQ,1)
    def mem_keys(steps):
        panel.button(a,1,True)
        for s in steps:
            a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(s),))
            for _ in range(3): panel.scan(a)
            a.call(0x20FC18,(0,))
            for _ in range(3): panel.scan(a)
        panel.button(a,1,False)
    mem_keys([4,4,9])
    need(a.data(LIST,4) == bytes([4,2,9,1]),'Panel free chain wrong: '+a.data(LIST,6).hex())
    need('CH02  P10' in a.texts,'Readout missing: '+str(a.texts[-6:]))
    mem_keys([1])
    need(a.data(ST+3,1) == b'\1' and current(a) == 1,'New MEMORY press did not start a new chain')
    # KORG mode readout is the native one
    b = ui(patched); b.put32(SEQ,1)
    o = ui(original); o.put32(SEQ,1)
    for m in (b,o):
        panel.button(m,1,True)
        m.call(0x20FC18,(0,)); m.call(0x20FC18,(panel.raw_for_step(6),))
        for _ in range(3): panel.scan(m)
        m.call(0x20FC18,(0,)); panel.button(m,1,False)
    need(b.texts[-4:] == o.texts[-4:] and b.data(CHAIN,0x1C) == o.data(CHAIN,0x1C),'KORG panel path differs')
    return {'panel_free_chain':True,'readout':'CH02  P10','korg_panel_identical':True}


def page_to(a,n):
    panel.enter(a)
    for _ in range(n): panel.button(a,6,True); panel.button(a,6,False)


def key16(a):
    a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(15),))
    a.call(0x20FC18,(0,))


def verify_pages(original,patched):
    a = panel.machine(patched)
    page_to(a,10)
    panel.check_display(a,'CR OFF   ')
    a.call(0x2059D0,(3,127,0,0)); panel.check_display(a,'CR ON    ')
    need(a.data(ST,3) == bytes([1,0,1]),'CR ON did not set free chain + recording')
    key16(a); panel.check_display(a,'REC FISSO')
    need(a.data(ST+0xF,1) == b'\1','REC FISSO not stored')
    a.call(0x2059D0,(3,120,0,0)); panel.check_display(a,'CR ON   F')
    key16(a); panel.check_display(a,'REC AUTO ')
    need(a.data(ST+0xF,1) == b'\0','REC AUTO not stored')
    a.call(0x2059D0,(3,0,0,0)); panel.check_display(a,'CR OFF   ')
    need(a.data(ST,3) == bytes(3),'CR OFF did not clear the options')
    a.call(0x2059D0,(3,127,0,0))
    panel.button(a,6,True); panel.button(a,6,False)
    panel.check_display(a,'01 P100  ')
    panel.button(a,7,True); panel.button(a,7,False)
    panel.check_display(a,'CR ON    ')
    for t in ['CR ON','CR OFF','CR ON   F','REC FISSO','REC AUTO','CH02  P10','CPY 03-04']:
        g = panel.glyphs(a,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    panel.button(a,0,True); panel.button(a,0,False)
    need(a.data(ST,3) == bytes([1,0,1]),'Options lost on leaving the page')
    return {'pages':['CR'],'rec_fisso_key16':True,'wrap':True,'glyphs':True}


def verify_cr_off_chain(original,patched):
    """CR ON -> OFF ends the free chain; the pattern playing continues."""
    a = ui(patched); setopt(a,cr=1); a.put32(SEQ,1)
    memory_press(a); keys(a,(2,),(),(5,))
    need(a.data(ST+4,1) == b'\1','Free chain not on')
    page_to(a,10)
    a.call(0x2059D0,(3,0,0,0))
    need(a.data(ST+4,1) == b'\0' and a.data(CHAIN+0x15,1) == b'\0','CR OFF did not end the free chain')
    panel.button(a,0,True); panel.button(a,0,False)
    p0 = current(a)
    need(play(a,3) == [p0]*3,'Pattern changed after CR OFF')
    return {'free_chain_ended':True,'pattern_kept':p0}


def verify_power_on(original,patched):
    a = machine(patched)
    need(a.data(ST,0x10) == bytes(0x10),'Chain state not zero at power-on')
    need(a.data(0x1980,12) == b'OFF   ON    ','Chain names missing')
    return {'CR':'OFF','REC':'AUTO'}

TASKS = [('v120/power_on',verify_power_on),
         ('v120/korg_unchanged',verify_korg_unchanged),
         ('v120/free_chain',verify_free_chain),
         ('v120/free_chain_rec',verify_free_chain_rec),
         ('v120/cr_save',verify_cr_save),
         ('v120/panel_memory',verify_panel_memory),
         ('v120/pages',verify_pages),
         ('v120/cr_off_chain',verify_cr_off_chain)]

def all_tasks():
    import verify_121_more as more
    return TASKS+[('v120/'+n,getattr(more,'verify_'+n)) for n in
                  ('rec_toggle','rec_off_save','rec_fisso','func_in_chain','copy','program_change',
                   'fx_per_pattern','add_keeps_step')]


if __name__ == '__main__':
    TASKS = all_tasks()
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
