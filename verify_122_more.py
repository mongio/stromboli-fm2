"""1.20 tests: REC with CR, save when REC goes off, REC FISSO, FUNC during a
chain, pattern copy (FUNC + MEMORY), Program Change in."""
import struct
import verify_122 as v
import sys
import verify_panel as panel
import reverse_checks as native
from unicorn import UC_HOOK_BLOCK

need = v.need
FLASH_TABLE = 0x20FC40


def press(a,i,steps=20):
    panel.button(a,i,True); panel.button(a,i,False)
    for _ in range(steps): a.call(0x208CF8,(1,0))


def transport(a,seq):
    out = []
    for lab,btn in seq:
        press(a,btn); out.append(a.get32(v.SEQ))
    return out


SEQ_TEST = [('PLAY',3),('REC',2),('REC',2),('REC',2),('STOP',3),('REC',2),('PLAY',3),('REC',2),('REC',2)]


def verify_rec_toggle(original,patched):
    """CR ON: REC goes on and off while a chain plays, also after STOP.
    CR OFF: as the Korg firmware (REC blocked during a chain)."""
    res = {}
    for name,img in (('orig',original),('cr_off',patched)):
        a = v.ui(img); v.keys(a,(2,),(2,4))
        res[name] = transport(a,SEQ_TEST)
    need(res['orig'] == res['cr_off'],'CR OFF differs from Korg: '+str(res))
    a = v.ui(patched); v.setopt(a,cr=1); v.memory_press(a); v.keys(a,(2,),(),(4,),(),(1,))
    res['cr_on'] = transport(a,SEQ_TEST)
    need(res['cr_on'] == [1,3,1,3,0,2,3,1,3],'CR ON: REC not free during the chain: '+str(res['cr_on']))
    return res


def verify_rec_off_save(original,patched):
    """CR ON: REC off by hand in the middle of a pattern saves it."""
    a = v.machine(patched); v.setopt(a,cr=1); a.put32(v.SEQ,2)
    v.memory_press(a); v.keys(a,(2,),(),(5,)); v.start(a)
    for _ in range(5): a.call(0x208CF8,(1,0))
    slot = a.data(v.CLOCK+6,1)[0]
    a.u.mem_write(v.PATTERN+80,b'\x30')
    a.call(0x208598)                       # native REC toggle (off)
    need(a.get32(v.SEQ) == 1,'REC not off')
    need(a.writes == [slot],'REC off did not save: '+str(a.writes))
    # REC off with nothing changed: no save
    a.writes.clear(); a.call(0x208598); a.call(0x208598)
    need(a.writes == [],'Unchanged pattern saved')
    # CR OFF: no save
    b = v.machine(patched); b.put32(v.SEQ,3); v.keys(b,(2,))
    b.u.mem_write(v.PATTERN+80,b'\x30'); b.call(0x208598)
    need(b.writes == [],'CR OFF saved')
    return {'saved_slot':slot,'unchanged_not_saved':True,'cr_off_not_saved':True}


def verify_rec_fisso(original,patched):
    """End of a motion loop (BL at 0x209062): REC AUTO leaves REC like Korg,
    REC FISSO keeps it."""
    entry = FLASH_TABLE+0x18
    res = {}
    for opt in (0,1):
        a = v.machine(patched); a.put32(v.SEQ,3)
        a.u.mem_write(v.ST+0xF,bytes([opt]))
        a.call(entry)
        res[opt] = a.get32(v.SEQ)
    o = v.machine(original); o.put32(v.SEQ,3); o.call(0x208598)
    need(res[0] == o.get32(v.SEQ) == 1,'REC AUTO differs from Korg')
    need(res[1] == 3,'REC FISSO left REC')
    return {'REC_AUTO':res[0],'REC_FISSO':res[1]}


def blocks_of(a,mask_down):
    a.u.mem_write(0x200028EE,b'\x01')
    for _ in range(3): panel.scan(a)
    seen = set()
    h = a.u.hook_add(UC_HOOK_BLOCK,lambda uc,ad,sz,ud: seen.add(ad))
    a.u.mem_write(0x200028EE,bytes([mask_down]))
    for _ in range(3): panel.scan(a)
    a.u.hook_del(h)
    a.u.mem_write(0x200028EE,b'\0')
    for _ in range(3): panel.scan(a)
    return seen


def func_key(a,step):
    a.u.mem_write(0x200028EE,b'\x01')
    for _ in range(3): panel.scan(a)
    seen = set()
    h = a.u.hook_add(UC_HOOK_BLOCK,lambda uc,ad,sz,ud: seen.add(ad))
    a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(step),))
    for _ in range(3): panel.scan(a)
    a.u.hook_del(h)
    a.call(0x20FC18,(0,))
    a.u.mem_write(0x200028EE,b'\0')
    for _ in range(3): panel.scan(a)
    return seen


def verify_func_in_chain(original,patched):
    TABLE = 0x200111DC                     # first block of the FUNC + key table
    res = {}
    # Korg and CR OFF: blocked during a chain
    for name,img in (('orig',original),('cr_off',patched)):
        a = v.ui(img); v.keys(a,(2,),(2,4)); a.put32(v.SEQ,1)
        res[name] = TABLE in func_key(a,0)
    need(not res['orig'] and not res['cr_off'],'Korg FUNC + key not blocked in a chain?')
    # CR ON, free chain: FUNC + key and FUNC + PLAY (ACTIVE STEP) work
    a = v.ui(patched); v.setopt(a,cr=1); v.memory_press(a); v.keys(a,(2,),(),(4,)); a.put32(v.SEQ,1)
    need(a.data(v.CHAIN+0x15,1) == b'\1','Chain not active')
    res['cr_on_key'] = TABLE in func_key(a,0)
    need(res['cr_on_key'],'CR ON: FUNC + key still blocked')
    a.texts.clear(); blocks_of(a,0x01|0x08)
    res['cr_on_active_step'] = 'ActiveStp' in a.texts
    need(res['cr_on_active_step'],'CR ON: FUNC + PLAY still blocked: '+str(a.texts[-4:]))
    # the same functions without a chain behave as in Korg
    o = v.ui(original); v.keys(o,(2,)); o.put32(v.SEQ,1)
    b = v.ui(patched); v.setopt(b,cr=1); v.keys(b,(2,)); b.put32(v.SEQ,1)
    need(TABLE in func_key(o,0) and TABLE in func_key(b,0),'FUNC + key without a chain broken')
    return res


def func_memory(a):
    a.u.mem_write(0x200028EE,b'\x01')
    for _ in range(3): panel.scan(a)
    a.u.mem_write(0x200028EE,b'\x03')
    for _ in range(3): panel.scan(a)
    a.u.mem_write(0x200028EE,b'\0')
    for _ in range(3): panel.scan(a)


def verify_copy(original,patched):
    res = {}
    a = v.ui(patched); v.setopt(a,cr=1)
    blank = native.blank_pattern(a,native.SCRATCH)
    a.storage.store(3,blank)
    bank = lambda n: a.data(a.get32(native.ROOT)+n*1920,1920)
    v.memory_press(a); v.keys(a,(2,),(),(3,))
    v.start(a,rec=True)
    v.play(a,1)
    for _ in range(5): a.call(0x208CF8,(1,0))
    need(a.data(v.CLOCK+6,1) == b'\3','Not on the empty pattern: '+str(a.data(v.CLOCK+6,1)[0]))
    step = a.data(v.CLOCK+0xB,1)
    src = bank(2)
    a.writes.clear(); a.texts.clear()
    func_memory(a)
    need(a.data(v.PATTERN,1920) == src,'Pattern not copied')
    need(a.writes == [3] and bank(3) == src,'Copy not saved: '+str(a.writes))
    need(a.data(v.CLOCK+0xB,1) == step,'Copy moved the step')
    need('CPY 03-04' in a.texts,'No CPY message: '+str(a.texts[-4:]))
    res['copied'] = '3 -> 4'
    # the chain keeps playing: 3 (pattern 2 copy) then 2
    need(v.play(a,1) == [v.current(a)],'Loop broken after the copy')
    # not empty: native WRITE, no copy
    b = v.ui(patched); v.setopt(b,cr=1)
    v.memory_press(b); v.keys(b,(2,),(),(3,)); v.start(b,rec=True); v.play(b,1)
    for _ in range(5): b.call(0x208CF8,(1,0))
    before = b.data(v.PATTERN,1920); b.writes.clear(); b.texts.clear()
    func_memory(b)
    need(b.data(v.PATTERN,1920) == before and 'CPY 03-04' not in b.texts,'Copied a non-empty pattern')
    res['non_empty_write'] = b.writes
    # not recording: no copy
    c = v.ui(patched); v.setopt(c,cr=1)
    c.storage.store(3,blank)
    v.memory_press(c); v.keys(c,(2,),(),(3,)); v.start(c); v.play(c,1)
    for _ in range(5): c.call(0x208CF8,(1,0))
    before = c.data(v.PATTERN,1920); c.texts.clear()
    func_memory(c)
    need(c.data(v.PATTERN,1920) == before,'Copied without REC')
    res['no_rec_no_copy'] = True
    return res


def midi_machine(img):
    a = native.audio_machine(img)
    a.call(0x20AD54,(6,0)); a.call(0x2080A4,(1,)); a.call(0x200148E4,(1,))
    return a


def send(a,pk):
    for x in pk: a.call(0x200146EC,(1,x))


def verify_program_change(original,patched):
    res = {}
    o = midi_machine(original); p0 = o.data(0x20002A08,1)[0]
    send(o,[0xC0,5])
    need(o.data(0x20002A08,1)[0] == p0,'Korg 1.12 reacted to Program Change?')
    a = midi_machine(patched)
    got = []
    for pc in (5,63,64,70,127,0):
        send(a,[0xC0,pc]); got.append(a.data(0x20002A08,1)[0])
    need(got == [5,63,0,6,63,0],'Program Change mapping wrong: '+str(got))
    res['pc_5_63_64_70_127_0'] = got
    send(a,[0xC3,9])
    need(a.data(0x20002A08,1)[0] == 0,'Other channel accepted')
    send(a,[0x90,60,100])
    need(any(a.data(0x20003C6C+i*16,1)[0] for i in range(6)),'Notes broken after the hook')
    send(a,[0xE0,0,64]); send(a,[0xB0,123,0])
    res['other_channel_ignored'] = True
    return res


def with_fx(pat,fx):
    import probability_format as pf
    b = bytearray(pf.set_prb3(pat,[100]*16))
    for i in range(2):
        b[pf.OFFSET+13+i] |= ((fx >> i) & 1) << 7
    struct.pack_into('<H',b,pf.OFFSET+26,pf.prb2_digest(bytes(b[pf.OFFSET:pf.OFFSET+26])))
    return bytes(b)


def verify_fx_per_pattern(original,patched):
    """1.21: the effect type (REVRB / DELAY / LOFI) is saved in the pattern and
    set at every pattern load (selection and chain)."""
    a = v.machine(patched)
    bank = lambda n: a.data(a.get32(native.ROOT)+n*1920,1920)
    a.storage.store(3,with_fx(bank(3),1)); a.storage.store(4,with_fx(bank(4),2))
    sel = []
    for k in (3,4,2,3):
        v.keys(a,(k,)); sel.append(a.data(0x3F80,1)[0])
    need(sel == [1,2,0,1],'Selection: '+str(sel))
    a.u.mem_write(0x3F80,b'\0')
    v.setopt(a,cr=1); v.memory_press(a); v.keys(a,(3,),(),(2,),(),(4,)); v.start(a)
    seq = []
    for i in range(64):
        a.call(0x208CF8,(1,0))
        if i % 16 == 2: seq.append((a.data(v.CLOCK+6,1)[0],a.data(0x3F80,1)[0]))
    need(seq == [(3,1),(2,0),(4,2),(3,1)],'Chain: '+str(seq))
    # the FX page writes the type into the current pattern
    b = panel.machine(patched)
    v.page_to(b,10)                      # 1.24: FX is page 10
    b.call(0x2059D0,(3,64,0,0)); panel.check_display(b,'FX DELAY ')
    import probability_format as pf
    got = sum(((b.data(v.PATTERN+pf.OFFSET+13+i,1)[0] >> 7) & 1) << i for i in range(2))
    need(got == 1,'FX page did not write the pattern: '+str(got))
    return {'selection':sel,'chain':seq,'page_writes_pattern':True}


def verify_add_keeps_step(original,patched):
    """1.21: adding a pattern to the chain while playing does not restart it."""
    a = v.machine(patched); v.setopt(a,cr=1)
    v.keys(a,(1,)); v.start(a)
    for _ in range(6): a.call(0x208CF8,(1,0))
    st = lambda: (a.data(v.CLOCK+6,1)[0],a.data(v.CLOCK+0xB,1)[0])
    before = st()
    v.memory_press(a); v.keys(a,(1,)); v.keys(a,(),(3,))
    after = st()
    need(after == before,'Restarted: '+str((before,after)))
    for _ in range(16-before[1]-1): a.call(0x208CF8,(1,0))
    nxt = []
    for _ in range(2): a.call(0x208CF8,(1,0)); nxt.append(a.data(v.CLOCK+6,1)[0])
    need(nxt[-1] == 3,'Chain did not move on to 3: '+str(nxt))
    return {'before':before,'after_adding':after}
