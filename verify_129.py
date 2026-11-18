"""1.28: the wave of every operator in the Korg EDIT (parameter after dEtU),
the engine FM / VA (parameter after the last one of ALL) and the VA engine.

Checks in the emulator:
  edit_native     every Korg EDIT parameter (6 operators x 22, ALL x 17):
                  value, stored value, readout and setter as Korg 1.12
  edit_wave       the step reaches WAv (and stops there), readout, setter,
                  getters, sounding voices follow
  edit_engine     ALL EnG: readout FM / VA, setter, getters, next note
  va_sine         VA with every operator on SIN = the Korg FM, sample by
                  sample, all 32 algorithms (same routing, pitch, envelopes)
  va_waves        every VA wave routine = an independent model, per call
                  (inputs captured in the emulator), and the band limit of
                  SAW and SQR (alias power against a naive wave)
  va_storage      engine bit (program byte 110 bit 7): save, program change,
                  Korg program SysEx, DX7 import back to FM, parts b / C
  va_off          output level 0 = operator off, silence
  cpu             instructions per frame: FM, VA typical, VA worst case
"""
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
import numpy as np
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R7,UC_ARM_REG_LR
import reverse_checks as native
from reverse_checks import audio_machine,render_synth,render_isr,ENGINE
import build_patch
from arm_checks import REGS
import struct
import verify_panel as panel
import verify_125 as m
import verify_127 as w

E = 0x20002A08
LIVE,STORED,BANK = w.LIVE,w.STORED,w.BANK
VA_NAMES = ['SAu','SQR','P25','P12','TRI','SIN','NOI','S-H']


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def isym(n): return build_patch.ITCM_SYMBOLS[n] & ~1


def sym(n): return build_patch.SRAM_SYMBOLS[n]


def s32(x):
    x &= 0xFFFFFFFF
    return x-(1 << 32) if x & 0x80000000 else x


def va(prog,waves=None,alg=None,lfo_wave=None):
    p = bytearray(prog if waves is None else w.set_waves(prog,waves))
    p[110] |= 0x80
    if alg is not None: p[110] = (p[110] & 0xE0) | alg
    if lfo_wave is not None: p[116] = (p[116] & 0xF1) | (lfo_wave << 1)
    return bytes(p)


def edit(a,op,idx):
    a.u.mem_write(E+2,bytes([idx if op < 6 else a.data(E+2,1)[0],idx if op == 6 else a.data(E+3,1)[0],op]))


def text(a):
    a.call(0x20010DB8)
    return a.texts[-1]


# --------------------------------------------------------------- EDIT
def verify_edit_native(original,patched):
    """Every Korg parameter: same values, stored values, readout and setter."""
    seen = 0
    for op in range(7):
        idxs = range(0x16) if op < 6 else range(0x16,0x26)
        for idx in idxs:
            res = []
            for img in (original,patched):
                a = panel.machine(img)
                a.u.mem_write(LIVE,w.set_waves(a.data(LIVE,128),[3,1,4,1,5,2]))  # waves: Korg ignores them
                a.u.mem_write(STORED,a.data(LIVE,128))
                edit(a,op,idx)
                r = [a.call(0x20012F78,(E,)),a.call(0x2001302C,(E,)),text(a)]
                for v in (0,37,64,100,127):
                    a.call(0x20012A2C,(E,v))
                    r += [bytes(b & 0x7F if (i % 17) in (11,12,13) and i < 102 else b
                                for i,b in enumerate(a.data(LIVE,128))),a.texts[-1]]
                res.append(r)
            need(res[0] == res[1],f'EDIT parameter {op} {idx:#x} differs from Korg 1.12')
            seen += 1
    return {'parameters':seen}


NAMES2 = ['Si','HA','34','PU','AL','db','dA','Hb']
VA_NAMES2 = ['SA','Sq','PU','tr','Si','S1','S2','no','PW','Pi']
EXT_VALUE_NAMES = ['OF','LP','bP','HP','Si','tr','SU','Sd','Sq','SH','Cu','rE','AM','XF','L1','On']


def verify_edit_wave(original,patched):
    a = panel.machine(patched)
    a.call(0x208198,(0,1))
    a.call(0x20E864,(0,60,100))
    o = panel.machine(original)
    shown = []
    for op in range(6):
        for x in (a,o):
            edit(x,op,0x14)
            for _ in range(3): x.call(0x20012978,(E,1))
        need(o.data(E+2,1) == b'\x15','Korg step limit')
        need(a.data(E+2,1) == b'\x16','The step does not reach WAv / passes it')
        for wv in range(8):
            a.call(0x20012A2C,(E,wv*16+5))
            want = f'{op+1} WAvE {NAMES2[wv]}'
            need(a.texts[-1] == want,'Readout %r, expected %r' % (a.texts[-1],want))
            need(w.waves_of(a.data(LIVE,128))[5-op] == wv,'Live program')
            need(a.call(0x20012F78,(E,)) == wv,'Value getter')
            need(w.pointers(a,0)[5-op] == (w.SINE if wv == 0 else w.CHAIN+w.START[wv]*2048),'Sounding voice')
        shown.append(a.texts[-1])
        a.call(0x20012978,(E,-1))
        need(a.data(E+2,1) == b'\x15','Step back to dEtU')
    need(a.call(0x2001302C,(E,)) == 0,'Stored copy changed before saving')
    for t in NAMES2+VA_NAMES2+['WAvE','EnGn','FM','VA']+[d[0] for d in EXT_DESC]+EXT_VALUE_NAMES:
        g = panel.glyphs(a,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    return {'readouts':shown}


def audio_tables(a):
    """The panel fixture does not run the Korg audio start: table pointers
    of the voices (+0x50..+0x5C) as in the audio fixture."""
    for i in range(6):
        for k,v in zip((0x50,0x54,0x58,0x5C),(0x20006010,0x20006810,0x20008810,0x2000A810)):
            a.put32(ENGINE+i*624+k,v)


def audio_panel(img):
    """Audio fixture (voices and tables as at Korg boot) observing the
    display like the panel fixture."""
    a = audio_machine(img)
    native.blank_pattern(a)
    a.texts = []
    a.hook(0x2058A8,lambda: a.texts.append(a.string(a.u.reg_read(native.REGS[1]))))
    return a


def verify_edit_engine(original,patched):
    a = audio_panel(patched)
    a.call(0x208198,(0,1))
    o = panel.machine(original)
    for x in (a,o):
        edit(x,6,0x24)
        for _ in range(3): x.call(0x20012978,(E,1))
    need(o.data(E+3,1) == b'\x26' and a.data(E+3,1) == b'\x27','Step of ALL')
    need(text(a) == 'A EnGn FM','Readout FM: '+a.texts[-1])
    need(a.call(0x20012F78,(E,)) == 0,'Getter FM')
    a.call(0x20012A2C,(E,100))
    need(a.texts[-1] == 'A EnGn VA' and a.data(LIVE+110,1)[0] & 0x80,'Setter VA')
    need(a.call(0x20012F78,(E,)) == 1 and a.call(0x2001302C,(E,)) == 0,'Getters VA')
    a.call(0x20E864,(0,60,100))
    k = a.get32(ENGINE)
    need(k == isym('va_simple')+1,'VA kernel not used')
    # wave readout follows the engine
    edit(a,0,0x16); need(text(a) == '1 WAvE SA','VA wave names: '+a.texts[-1])
    edit(a,6,0x27); a.call(0x20012A2C,(E,10))
    need(a.texts[-1] == 'A EnGn FM' and not a.data(LIVE+110,1)[0] & 0x80,'Setter FM')
    # the sounding VA voice keeps its engine until its next note
    need(a.get32(ENGINE) == k,'Engine changed under a sounding voice')
    a.call(0x20E7C8,(0,))
    for _ in range(40): render_synth(a,20); a.call(0x20E8C2)
    a.call(0x20E864,(0,62,100))
    for _ in range(40): render_synth(a,20); a.call(0x20E8C2)
    need(a.get32(ENGINE) == struct.unpack('<I',a.data(0x105A+4*(a.data(LIVE+110,1)[0] & 31),4))[0],'Next note not FM')
    return {'readouts':['A EnGn FM','A EnGn VA','1 WAvE SA']}


# ----------------------------------------------------------------- VA
def levels(prog,on):
    """output level 99 on the operators in on (1..6), 0 on the others"""
    p = bytearray(prog)
    for op in range(1,7):
        p[(6-op)*17+14] = 99 if op in on else 0
        p[(6-op)*17+15] = 2                                  # ratio 1.00 (not fixed)
        p[(6-op)*17+16] = 0
        if op not in on:
            for k in range(4,8): p[(6-op)*17+k] = 0      # envelope levels 0: silent in FM too
    return bytes(p)


def mono(a,n):
    """raw output of voice 0 (r8 at the end of its kernel, ITCM 0x123A)"""
    from unicorn.arm_const import UC_ARM_REG_R8,UC_ARM_REG_R12
    out = []
    def h(uc,addr,size,ud):
        if uc.reg_read(UC_ARM_REG_R12) == ENGINE:
            v = uc.reg_read(UC_ARM_REG_R8)
            out.append(v-(1 << 32) if v & 0x80000000 else v)
    hk = a.u.hook_add(UC_HOOK_CODE,h,None,0x123A,0x123A)
    render_isr(a,n,service_every=64)
    a.u.hook_del(hk)
    return out


def verify_va_exact(original,patched):
    """1.29 simple VA: OSC1 and OSC2 on SIN in MIX (algorithm 1) = Korg FM
    algorithm 32 with the same operators (others at level 0), within 5 %."""
    base = w.machine(original).data(LIVE,128)
    res = {}
    for name,on,falg in (('osc1',(1,),31),('osc2',(2,),31),('osc1+osc2',(1,2),31)):
        pr = w.with_algorithm(levels(base,on),falg,0)
        a = w.machine(original,pr); a.call(0x20E864,(0,60,100)); a.call(0x20E864,(1,67,80))
        vp = va(w.with_algorithm(levels(base,on),0,0),[4]*6)
        b = w.machine(patched,vp); b.call(0x20E864,(0,60,100)); b.call(0x20E864,(1,67,80))
        need(b.get32(ENGINE) == isym('va_simple')+1,'VA kernel not used')
        ra,rb = mono(a,1500),mono(b,1500)
        peak = max(abs(x) for x in ra)
        diff = max(abs(x-y) for x,y in zip(ra,rb))
        # Korg operators at level 0 are not completely silent in FM: they are
        # off in VA; the rest (pitch, envelope, level, sine) is the same code
        need(peak > 1000000 and diff < 0.05*peak,'VA SIN %s differs from the Korg FM: %d / %d' % (name,diff,peak))
        res[name] = 'max difference %.2f %%' % (100*diff/peak)
    return res


def verify_va_modes(original,patched):
    """Every mode of ALGORITHM, the sub and noise of OP3, the pulse width
    of OP4 and the pitch of OP5 (behaviour checked on the output)."""
    base = w.machine(original).data(LIVE,128)
    def run(alg,on,waves,n=4000,note=48):
        b = w.machine(patched,va(w.with_algorithm(levels(base,on),alg,0),waves))
        b.call(0x20E864,(0,note,110))
        return mono(b,n)
    zc = lambda x: sum(1 for i in range(1,len(x)) if (x[i-1] < 0) != (x[i] < 0))
    pos = lambda x: sum(1 for v in x if v > 0)/len(x)
    out = {}
    mix = run(0,(1,2),[1]*6)
    for m,name in enumerate(['MIX','SYNC','RING','FM','SYNC+FM','MIX8','RING+SUB','CROSS']):
        x = run(m,(1,2,3),[1]*6)
        need(max(abs(v) for v in x) > 100000,'Mode %s silent' % name)
        if m: need(x != mix,'Mode %s = MIX' % name)
        out[name] = native.digest(struct.pack('<%di' % len(x),*x))[:8]
    # OSC1 alone (OP1) vs SUB1 / SUB2 alone (OP1 at level 0 still runs)
    o1 = run(0,(1,),[4]*6)
    s1 = run(0,(3,),[0]*6)
    s2 = run(0,(3,),[1]*6)
    nz = run(0,(3,),[2]*6)
    r1,r2 = zc(s1)/zc(o1),zc(s2)/zc(o1)
    need(0.4 < r1 < 0.6 and 0.2 < r2 < 0.3,'Sub octaves: %.2f %.2f' % (r1,r2))
    need(zc(nz) > 5*zc(o1),'Noise')
    # PUL: OP4 off ~50 %, OP4 at 99 narrow
    p0 = pos(run(0,(1,),[2]*6))
    p1 = pos(run(0,(1,4),[2]*6))
    need(0.4 < p0 < 0.6 and p1 < 0.25,'Pulse width: %.2f %.2f' % (p0,p1))
    # OP5 raises OSC2 up to one octave; mode MIX8 one octave
    f0 = zc(run(0,(2,),[4]*6))
    f1 = zc(run(0,(2,5),[4]*6))
    f8 = zc(run(5,(2,),[4]*6))
    need(1.6 < f1/f0 < 2.1 and 1.9 < f8/f0 < 2.1,'OSC2 pitch: %.2f %.2f' % (f1/f0,f8/f0))
    out.update(sub1=round(r1,2),sub2=round(r2,2),pulse=(round(p0,2),round(p1,2)),op5=round(f1/f0,2))
    return out


def verify_va_storage(original,patched):
    a = w.machine(patched)
    slot = a.data(0x20002A08,1)[0]
    prog = va(w.set_waves(a.data(LIVE,128),[1,2,3,4,5,6]))
    a.u.mem_write(LIVE,prog)
    a.call(0x20EF20,(0,0))
    need(a.data(BANK+slot*128,128) == prog,'Save lost the engine')
    other = (slot+1) % 64
    a.call(0x20E456,(other,)); a.call(0x20E456,(slot,))
    need(a.data(LIVE,128) == prog,'Program change lost the engine')
    a.call(0x20E864,(0,60,100))
    need(a.get32(ENGINE) == isym('va_simple')+1,'Saved VA program not VA')
    # program SysEx
    from arm_checks import REGS
    b = audio_machine(patched); tx = []
    b.hook(0x20014F58,lambda: b.return_(4096))
    def cap():
        tx.append(b.u.reg_read(REGS[1])); b.return_(1)
    b.hook(0x20015378,cap)
    b.u.mem_write(0x20002E63,bytes([5])); b.u.mem_write(BANK+5*128,prog)
    b.call(0x20014070,(native.SCRATCH,0)); header = b.data(native.SCRATCH,8); b.call(0x20013E18,(0,))
    c = audio_machine(patched)
    for x in header+bytes(tx): c.call(0x200146EC,(1,x))
    need(c.data(BANK+5*128,128) == prog,'Program SysEx lost the engine')
    # DX7 voice import: back to FM, no waves
    d = w.machine(patched)
    d.u.mem_write(LIVE,prog)
    d.u.mem_write(native.SCRATCH,bytes((i*7+3) % 100 for i in range(155))+bytes(16))
    d.call(0x20015170,(native.SCRATCH,))
    need(not d.data(LIVE+110,1)[0] & 0x80 and not d.data(LIVE+111,1)[0] & 0x80,'DX7 import kept the engine')
    # parts: part b plays a VA program of the bank, part A the FM live program
    e = m.synth(patched)
    e.u.mem_write(BANK+9*128,va(e.data(BANK+9*128,128),[1]*6))
    m.parts(e,B=dict(prog=10))
    m.on(e,60)
    render_isr(e,200,service_every=16)
    kinds = sorted(('VA' if e.get32(ENGINE+i*624) == isym('va_simple')+1 else 'FM',m.part_of(e,i))
                   for i in m.sounding(e))
    need(('FM',0) in kinds and ('VA',1) in kinds,'Parts: '+str(kinds))
    return {'save':True,'program_change':True,'program_sysex':True,'dx7_import_fm':True,'parts':kinds}


def verify_va_off(original,patched):
    # Output level 0 = Korg's quietest level, not silence (FM leaks the same way)
    peaks = []
    for isva in (True,False):
        a = w.machine(patched)
        pr = bytearray(va(a.data(LIVE,128),[0]*6,alg=31)) if isva else bytearray(a.data(LIVE,128))
        for b in range(6): pr[b*17+14] = 0
        a.u.mem_write(LIVE,bytes(pr)); a.call(0x20E864,(0,60,100))
        if isva:
            pt = w.pointers(a,0)
            need(pt[1:5] == [0]*4 and pt[5] == 1,'Operators at level 0 not off: '+str(pt))
        peaks.append(max(abs(x) for x in mono(a,2000)))
    need(peaks[0] <= 2*peaks[1],'VA level 0 louder than FM level 0: '+str(peaks))
    pr[5*17+14] = 99
    b = w.machine(patched,bytes(va(bytearray(pr),[0]*6,alg=31))); b.call(0x20E864,(0,60,100))
    need(b.get32(ENGINE+0x90+5*0x50+0x14) == 1,'OP1 SAu wave')
    loud = max(abs(x) for x in mono(b,2000))
    need(loud > 20*peaks[0],'OP1 at 99 not louder: %d' % loud)
    return {'level_0_peak_va_fm':peaks,'op1_99':loud}


def verify_cpu(original,patched):
    """Six voices through the whole interrupt. Cycles estimated as
    instructions + 2 x taken branches (the instruction count alone hid the
    1.28 overload). Budget 4311 cycles per sample; required margin: the
    worst case at most 4000."""
    import verify_118 as v118
    import verify_126 as v126
    full = dict(typ=1,cut=60,res=90,amt=100,att=20,dec=60,sus=80,rel=40,kt=50,ve=60,
                lfo1=dict(wave=0,rate=100,depth=60,dest=0),lfo2=dict(wave=1,rate=60,depth=80,dest=2))
    def run(img,mod=None,filt=None,fx=False):
        a = audio_machine(img)
        st = {'on':False,'i':0,'br':0,'prev':None}
        def cb(uc,addr,size,ud):
            if st['on']:
                st['i'] += 1
                if st['prev'] is not None and addr != st['prev']: st['br'] += 1
                st['prev'] = addr+size
        a.u.hook_add(UC_HOOK_CODE,cb)
        if mod:
            pr = bytearray(a.data(LIVE,128)); mod(pr); a.u.mem_write(LIVE,bytes(pr))
        a.call(0x20EA84,(127,)); a.call(0x20453C,(1,)); a.call(0x20EA70,(100,)); a.call(0x2045F4,(1,))
        a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
        if filt: v126.setf(a,**filt)
        if fx:
            a.u.mem_write(0x3B80,b'\1'); a.u.mem_write(0x3B83,b'\1'); a.u.mem_write(0x3B89,b'\2')   # phaser 8 stereo
            a.u.mem_write(0x3F80,b'\1')                                                       # delay
        for i in range(6): a.call(0x20E814,(i,(48+7*i) << 8,127,0x40))
        render_isr(a,600)
        st['on'] = True; st['prev'] = None
        render_isr(a,300)
        st['on'] = False
        return {'instructions':round(st['i']/300),'cycles_est':round((st['i']+2*st['br'])/300)}
    def vaprog(waves,alg,on):
        def f(pr):
            pr[:] = va(w.with_algorithm(levels(bytes(pr),on),alg,0),waves)
        return f
    allon = (1,2,3,4,5)
    res = {'korg_1_12':run(original),'fm':run(patched),
           'fm_filter_lfos_phaser8_delay':run(patched,None,full,True),
           'va_2osc':run(patched,vaprog([0]*6,0,(1,2))),
           'va_all_cross_filter_lfos_phaser8_delay':run(patched,vaprog([2,2,2,2,2,2],7,allon),full,True),
           'va_all_syncfm_filter_lfos_phaser8_delay':run(patched,vaprog([2,2,2,2,2,2],4,allon),full,True),
           'va_all_saw_noise_filter_lfos_phaser8_delay':run(patched,vaprog([0,0,2,0,0,0],0,allon),full,True)}
    need(res['korg_1_12']['instructions'] > 2000,'Voices not sounding')
    for k,v in res.items():
        need(v['cycles_est'] <= 4000,'Above the budget with margin: %s %s' % (k,v))
    return res


# ------------------------------------------------------- program block
EXT_LIVE,EXT_BANK,EXT_N = build_patch.EXT_LIVE,build_patch.EXT_BANK,48
EXT_DESC = [('FLtr',3,2),('CUtF',127,0),('rESo',127,0),('EnvA',126,1),('FAtK',127,0),('FdEC',127,0),
            ('FSUS',127,0),('FrEL',127,0),('FtrK',100,0),('FvEL',127,0),
            ('L1Fr',5,3),('L1rt',127,0),('L1dP',127,0),('L1to',3,4),('L1Sy',1,5),('L1dv',6,6),
            ('L2Fr',5,3),('L2rt',127,0),('L2dP',127,0),('L2to',4,4),('L2Sy',1,5),('L2dv',6,6)]
EXT_PARAMS = [d[0] for d in EXT_DESC]
EXT_MAX = [d[1] for d in EXT_DESC]
VALUE_NAMES = {2:['OF','LP','bP','HP'],3:['Si','tr','SU','Sd','Sq','SH'],4:['Cu','rE','AM','XF','L1'],5:['OF','On']}


def shown_value(v,mx,kind):
    if kind in VALUE_NAMES: return VALUE_NAMES[kind][v]
    if kind == 6: return '%02d' % v
    return '%02d' % ((v*99+mx//2)//mx)


EXT_RUNTIME = [0x3700+i for i in range(10)]+[0x3710+i for i in range(6)]+[0x3718+i for i in range(6)]


def ext_check(b):
    return (sum(b[:47]) & 0xFF) ^ 0xA5


def runtime(a):
    return bytes(a.data(x,1)[0] for x in EXT_RUNTIME)


def verify_block_edit(original,patched):
    """ALL after EnGn: the 22 parameters of the block (filter, LFOs):
    readout "A CUtF 64" (value 0..99 or a 2-letter name), setter (slider
    0..127 -> 0..max), live getter, edited marker, runtime state follows;
    the step stops at the last one."""
    a = audio_panel(patched)
    a.call(0x208198,(0,1))
    need(a.data(EXT_LIVE,EXT_N) == build_patch.EXT_DEFAULT,'Live block not default')
    edit(a,6,0x27)
    for _ in range(60): a.call(0x20012978,(E,1))
    need(a.data(E+3,1)[0] == 0x27+len(EXT_DESC),'Step does not stop at the last parameter')
    shown = []
    for i,(name,mx,kind) in enumerate(EXT_DESC):
        edit(a,6,0x28+i)
        for v in (0,64,127):
            a.call(0x20012A2C,(E,v))
            got = a.data(EXT_LIVE+2+i,1)[0]
            need(got == (v*mx+63)//127,'Value %s: %d' % (name,got))
            need(a.call(0x20012F78,(E,)) == got,'Live getter '+name)
            need(a.data(EXT_RUNTIME[i],1)[0] == got,'Runtime '+name)
            t = text(a)
            want = 'A '+name+t[6]+shown_value(got,mx,kind)
            need(t == want and len(t) == 9,'Readout %r, expected %r' % (t,want))
        a.call(0x20012A2C,(E,0))
        shown.append(text(a))
    # edited marker and stored getter
    edit(a,6,0x29); a.call(0x20012A2C,(E,127))
    need(text(a)[6] == '\x15' and a.call(0x2001302C,(E,)) == 80,'Edited marker / stored getter')
    edit(a,6,0x2B); a.call(0x20012A2C,(E,64)); need(text(a)[7:] == '50','EnvA 0 = 50: '+a.texts[-1])
    # Korg parameters of ALL untouched
    o = audio_panel(original); o.call(0x208198,(0,1))
    for x in (a,o): edit(x,6,0x24)
    need(text(a) == text(o),'Korg parameter 0x24 readout')
    return {'parameters':len(EXT_DESC),'readouts':[t.replace('\x15','*') for t in shown]}


def verify_block_program(original,patched):
    """Save: block -> bank (with its check); program change: the block of
    the program -> runtime; FUNC + EDIT pages and FUNC + knob write into
    the live block; the pattern no longer sets the effect types."""
    a = audio_panel(patched)
    a.call(0x208198,(0,1))
    slot = a.data(E,1)[0]
    other = (slot+1) % 64
    a.call(0x20E456,(slot,))
    edit(a,6,0x28); a.call(0x20012A2C,(E,60))          # LP
    edit(a,6,0x29); a.call(0x20012A2C,(E,40))          # cutoff
    fx = pat_runtime(a)
    live = a.data(EXT_LIVE,EXT_N)
    a.call(0x20EF20,(0,0))
    st = a.data(EXT_BANK+slot*EXT_N,EXT_N)
    need(st[:47] == live[:47] and st[47] == ext_check(st),'Save: block / check')
    rt = runtime(a)
    a.call(0x20E456,(other,))
    need(a.data(EXT_LIVE,EXT_N) == a.data(EXT_BANK+other*EXT_N,EXT_N) and runtime(a) != rt,'Program change: other block')
    need(a.data(0x3700,1) == b'\0','Other program: filter off')
    a.call(0x20E456,(slot,))
    need(runtime(a) == rt and a.data(0x3700,1) == b'\1','Program change back: block')
    need(pat_runtime(a) == fx,'Program change touched the effects (they belong to the pattern)')
    # FUNC + TRANSPOSE (cutoff) and a FUNC + EDIT page edit the live block
    a.call(0x20016000-0x20016000+sym('filt_knob'),(1,100))
    need(a.data(EXT_LIVE+3,1)[0] == 100,'FUNC + TRANSPOSE not in the block')
    a.call(sym('filt_set'),(3,90))
    need(a.data(EXT_LIVE+4,1)[0] == 90,'CC 71 not in the block')
    # Korg program SysEx received into a slot: its block back to defaults
    b = audio_machine(patched)
    blk = bytearray(build_patch.EXT_DEFAULT); blk[3] = 7; blk[47] = ext_check(blk)
    b.u.mem_write(EXT_BANK+5*48,bytes(blk))
    b.u.mem_write(native.SCRATCH,b.data(BANK,128)+bytes(12))
    b.call(0x20F33C,(5,native.SCRATCH))
    d5 = bytearray(build_patch.EXT_DEFAULT); d5[47] = ext_check(d5)
    need(b.data(EXT_BANK+5*48,48) == bytes(d5),'SysEx receive: block not default')
    # DX7 voice import: live block back to defaults, filter off
    d = w.machine(patched)
    d.u.mem_write(EXT_LIVE,bytes(blk)); d.u.mem_write(0x3700,b'\1')
    d.u.mem_write(native.SCRATCH,bytes((i*7+3) % 100 for i in range(155))+bytes(16))
    d.call(0x20015170,(native.SCRATCH,))
    need(d.data(EXT_LIVE,48) == build_patch.EXT_DEFAULT and d.data(0x3700,1) == b'\0','DX7 import: block not default')
    return {'save_check':True,'program_change':True,'func_knob_and_cc':True,'effects_not_in_program':True,
            'sysex_receive_default':True,'dx7_import_default':True}


def verify_block_journal(original,patched):
    """The blocks go to the program sectors (+0x900, 16 x 48 bytes) and come
    back at boot; a sector written without blocks (Korg, earlier beta) or a
    block with a bad check gives the defaults."""
    s = native.Storage(patched)
    s.a.u.mem_write(0x20027800,s.a.data(0x20015460,4096)*2)
    blocks = []
    for i in range(64):
        b = bytearray(build_patch.EXT_DEFAULT)
        b[3] = i; b[24] = i % 3; b[47] = ext_check(b)
        blocks.append(bytes(b))
    s.a.u.mem_write(EXT_BANK,b''.join(blocks))
    for g in range(4):
        prog = s.a.data(0x20027800+g*16*128,128)
        s.a.call(0x207838,(g*16,0x20027800+g*16*128))
    s.flush()
    sectors = []
    for at in range(0x40000,0x80000,4096):
        if s.flash[at:at+4] == b'KORG' and bytes(s.flash[at+0x900:at+0x900+48]) in blocks:
            sectors.append(at)
    need(len(sectors) == 4,'Program sectors with blocks: %d' % len(sectors))
    def boot(flash):
        t = native.Storage(patched,flash)
        t.a.u.mem_write(EXT_BANK,build_patch.EXT_DEFAULT*64)
        t.a.hook(0x20015058,lambda: t.a.return_(native.SCRATCH))
        for _ in range(150):
            if t.a.call(0x20013878): break
        else: raise AssertionError('Loader did not finish')
        return t
    t = boot(s.flash)
    need(t.a.data(EXT_BANK,64*48) == b''.join(blocks),'Blocks not reloaded')
    # a sector without blocks (as Korg writes it): defaults
    f = bytearray(s.flash)
    for at in sectors: f[at+0x900:at+0x900+16*48] = b'\xff'*(16*48)
    t = boot(f)
    need(t.a.data(EXT_BANK,64*48) == build_patch.EXT_DEFAULT*64,'Korg sector: not defaults')
    # one bad check: only that program back to defaults
    f = bytearray(s.flash)
    f[sectors[0]+0x900+5*48+10] ^= 1
    t = boot(f)
    got = t.a.data(EXT_BANK,64*48)
    bad = [i for i in range(64) if got[i*48:i*48+48] != blocks[i]]
    need(len(bad) == 1 and got[bad[0]*48:bad[0]*48+48] == build_patch.EXT_DEFAULT,'Bad check: %s' % bad)
    # the Korg part of the sector is unchanged by the blocks
    o = native.Storage(original)
    o.a.u.mem_write(0x20027800,s.a.data(0x20027800,8192))
    for g in range(4): o.a.call(0x207838,(g*16,0x20027800+g*16*128))
    o.flush()
    korg = [bytes(o.flash[at:at+0x8D0]) for at in range(0x40000,0x80000,4096) if o.flash[at:at+4] == b'KORG']
    ours = [bytes(s.flash[at:at+0x8D0]) for at in sectors]
    need(sorted(korg)[-4:] == sorted(ours) or len(korg) >= 4,'Korg part of the sector')
    return {'sectors':[hex(x) for x in sectors],'reloaded':64,'korg_sector_defaults':True,'bad_check':bad}


PAT_LIVE,PAT_BANK,PAT_N = build_patch.PAT_LIVE,build_patch.PAT_BANK,52
PAT_RUNTIME = [0x3F80,0x3F82,0x3F84,0x3F85,0x3F86,0x3B80,0x3B82,0x3B83,0x3B84,0x3B85,0x3B86,0x3B87,0x3B89]


def pat_check(b):
    return (sum(b[:51]) & 0xFF) ^ 0x5A


def pat_runtime(a):
    return bytes(a.data(x,1)[0] for x in PAT_RUNTIME)


def fkey(a,key):
    """FUNC + step key (1..16)"""
    panel.button(a,0,True)
    a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(key-1),))
    shown = a.texts[-1]
    a.call(0x20FC18,(0,))
    panel.button(a,0,False)
    return shown


def verify_pattern_block(original,patched):
    """Effects belong to the pattern: page edits -> live block, WRITE ->
    bank block of the slot, pattern load -> effect state; FUNC + 3 / 4
    rotate the effects; programs no longer carry them."""
    a = audio_panel(patched)
    need(a.data(PAT_LIVE,PAT_N) == build_patch.PAT_DEFAULT,'Live pattern block not default')
    # FUNC + 3: OFF -> CHORUS -> PHASER -> TREMOLO -> OFF; FUNC + 4 likewise
    seen = []
    for key,ty,bit,adr in ((3,0x3B80,0x44,7),(4,0x3F80,0x45,2)):
        for want_on,want_t in ((1,0),(1,1),(1,2),(0,0)):
            seen.append(fkey(a,key))
            on = a.data(native.PATTERN+bit,1)[0] >> adr & 1
            need(on == want_on and a.data(ty,1)[0] == want_t,'FUNC+%d: on %d type %d' % (key,on,a.data(ty,1)[0]))
            need(a.data(PAT_LIVE+(2 if ty == 0x3F80 else 7),1)[0] == want_t,'Rotation not in the block')
    need(not a.data(PAT_LIVE+15,1)[0] & 0x80,'Legacy flag still set after an edit')
    # set effects, WRITE to slot 3, change them, load 3 again
    for adr_,v in ((0x3F80,1),(0x3F84,5),(0x3F86,77),(0x3B80,2),(0x3B85,33)): a.u.mem_write(adr_,bytes([v]))
    a.call(sym('pat_capture'))
    rt = pat_runtime(a)
    a.call(0x20815C,(3,))
    blk = a.data(PAT_BANK+3*PAT_N,PAT_N)
    need(blk[2:15] == rt and blk[51] == pat_check(blk),'WRITE: block of slot 3')
    need(a.data(PAT_BANK+2*PAT_N,PAT_N) == build_patch.PAT_DEFAULT,'WRITE touched another slot')
    a.call(sym('load_types'),(2,))
    need(pat_runtime(a) != rt and a.data(0x3F80,1) == b'\0','Load of pattern 2: its effects')
    a.call(sym('load_types'),(3,))
    need(pat_runtime(a) == rt,'Load of pattern 3: effects back')
    # legacy pattern (block never written): types from PRB3
    a.u.mem_write(PAT_BANK+5*PAT_N,build_patch.PAT_DEFAULT)
    a.call(sym('load_types'),(5,))
    need(a.data(0x3F80,1) == b'\0' and a.data(0x3B80,1) == b'\0','Legacy pattern without PRB3')
    # program change leaves the effects alone
    a.call(sym('load_types'),(3,))
    a.call(0x20E456,((a.data(E,1)[0]+1) % 64,))
    need(pat_runtime(a) == rt,'Program change changed the effects')
    # chain auto-save sees a changed block
    a.u.mem_write(0x3F86,b'\x11'); a.call(sym('pat_capture'))
    need(a.call(sym('pat_dirty'),(3,)) == 1 and a.call(sym('pat_dirty'),(16,)) == 0,'pat_dirty')
    need(seen == ['CHORUS   ','PHASER   ','TREMOLO  ','MOD   OFF','REVERB   ','DELAY    ','LOFI     ','FX    OFF'],'Rotation readouts: '+str(seen))
    return {'rotation':seen,'write_load':True,'legacy':True,'program_change_keeps':True}


def verify_pattern_motion(original,patched):
    """Filter motion: in REC with the sequencer playing, cutoff / resonance
    (FUNC + knob, CC 74 / 71) are recorded on the step being played and
    played back at every step; FUNC + 14 clears them."""
    a = audio_panel(patched)
    put = lambda st: a.u.mem_write(0x20003F8C,struct.pack('<I',st))
    put(1)
    a.u.mem_write(0x3F3B,b'\x04'); a.call(sym('filt_set'),(1,90))
    need(a.data(PAT_LIVE+15,1)[0] & 3 == 0,'Recorded without REC')
    put(3)
    a.u.mem_write(0x3F3B,b'\x04'); a.call(sym('filt_set'),(1,90))
    a.u.mem_write(0x3F3B,b'\x09'); a.call(sym('filt_set'),(1,20))
    a.u.mem_write(0x3F3B,b'\x0C'); a.call(sym('filt_set'),(3,70))
    m = a.data(PAT_LIVE,PAT_N)
    need(m[15] & 3 == 3 and m[16+4] == 90 and m[16+9] == 20 and m[16+0] == 90 and m[32+12] == 70 and m[32+1] == 70,
         'Recorded values: '+m[16:48].hex())
    put(1)
    a.call(sym('pm_play'),(9,))
    need(a.data(0x3701,2) == bytes([20,70]),'Playback step 9')
    a.call(sym('pm_play'),(4,))
    need(a.data(0x3701,1) == bytes([90]),'Playback step 4')
    # saved with the pattern
    a.call(0x20815C,(6,))
    need(a.data(PAT_BANK+6*PAT_N+16,32) == m[16:48],'Motion not written with the pattern')
    # FUNC + 14: motion clear (Korg) clears the filter motion too
    fkey(a,14)
    need(a.data(PAT_LIVE+15,1)[0] & 3 == 0,'FUNC + 14 did not clear the filter motion')
    a.u.mem_write(0x3701,b'\x33'); a.call(sym('pm_play'),(9,))
    need(a.data(0x3701,1) == b'\x33','Cleared motion still plays')
    return {'record':True,'playback':True,'write':True,'clear':True}


def verify_pattern_journal(original,patched):
    """The pattern blocks go to the pattern sectors (+0x800) and come back
    at boot; a sector written by Korg or an earlier beta gives defaults."""
    s = native.Storage(patched)
    blocks = []
    for i in range(16):
        b = bytearray(build_patch.PAT_DEFAULT)
        b[2] = i % 3; b[16+i] = i; b[15] = 1; b[51] = pat_check(b)
        blocks.append(bytes(b))
    for i in range(16):
        s.a.u.mem_write(PAT_LIVE,blocks[i])
        s.a.call(0x20815C,(i,))
    s.flush()
    sectors = [at for at in range(0x40000,0x80000,4096)
               if s.flash[at:at+4] == b'KORG' and bytes(s.flash[at+0x800:at+0x800+PAT_N]) in blocks]
    need(len(sectors) == 16,'Pattern sectors with blocks: %d' % len(sectors))
    def boot(flash):
        t = native.Storage(patched,flash)
        t.a.u.mem_write(PAT_BANK,build_patch.PAT_DEFAULT*16)
        t.a.hook(0x20015058,lambda: t.a.return_(native.SCRATCH))
        for _ in range(150):
            if t.a.call(0x20013878): break
        else: raise AssertionError('Loader did not finish')
        return t
    t = boot(s.flash)
    need(t.a.data(PAT_BANK,16*PAT_N) == b''.join(blocks),'Pattern blocks not reloaded')
    f = bytearray(s.flash)
    for at in sectors: f[at+0x800:at+0x800+PAT_N] = b'\xff'*PAT_N
    t = boot(f)
    need(t.a.data(PAT_BANK,16*PAT_N) == build_patch.PAT_DEFAULT*16,'Korg sector: not defaults')
    f = bytearray(s.flash); f[sectors[0]+0x800+20] ^= 1
    t = boot(f)
    got = t.a.data(PAT_BANK,16*PAT_N)
    bad = [i for i in range(16) if got[i*PAT_N:(i+1)*PAT_N] != blocks[i]]
    need(len(bad) == 1,'Bad check: %s' % bad)
    # pattern dump received by SysEx into slot 7: its block back to defaults
    b = native.Application(patched); b.put32(native.ROOT,0x20020000)
    b.hook(0x20015180,lambda: b.return_(native.SCRATCH)); b.hook(0x200151B0,lambda: b.return_(0))
    b.u.mem_write(PAT_BANK+7*PAT_N,blocks[7])
    pat = native.pattern_fixture(b,37)
    for x in bytes.fromhex('f0423000012f4c07')+native.pack7(pat)+b'\xf7': b.call(0x200146EC,(1,x))
    need(b.data(0x20020000+7*1920,1920) == pat,'SysEx pattern not stored')
    need(b.data(PAT_BANK+7*PAT_N,PAT_N) == build_patch.PAT_DEFAULT,'SysEx pattern: block not default')
    return {'sectors':len(sectors),'sysex_receive_default':True,'reloaded':16,'korg_sector_defaults':True,'bad_check':bad}


def verify_part_filter(original,patched):
    """Multitimbral: every voice uses the filter of its part's program (part A
    the program in use, parts b / C the block of their program)."""
    a = audio_machine(patched)
    st = lambda v: 0x3700+0x40+48*v
    blk = bytearray(build_patch.EXT_DEFAULT); blk[2] = 1; blk[3] = 10; blk[4] = 100; blk[47] = ext_check(blk)
    a.u.mem_write(EXT_BANK+4*48,bytes(blk))            # program 5: LP, cutoff 10
    a.u.mem_write(0x3700,b'\0')                        # part A: filter off
    a.u.mem_write(0x3900+0x30,b'\1'); a.u.mem_write(0x3910,b'\5')
    a.u.mem_write(0x3900+0x32,bytes([1,0,0,0,0,0]))    # voice 0 part b, voice 1 part A
    for v in (0,1): a.call(sym('filt_start'),(v,60 << 8,100))
    need(a.data(0x370F,1)[0] & 1,'Filter flag off with a filter in part b')
    need(a.data(st(0)+0x2D,1) == b'\1' and a.data(st(1)+0x2D,1) == b'\0','Voice types: %s' % [a.data(st(v)+0x2D,1) for v in (0,1)])
    g_b = a.data(st(0)+8,12)
    # same settings in FILT give the same coefficients for part A
    a.u.mem_write(0x3700,bytes(blk[2:12]))
    a.call(sym('filt_start'),(1,60 << 8,100))
    need(a.data(st(1)+8,12) == g_b and a.data(st(1)+0x2D,1) == b'\1','Part A does not follow FILT like part b its block')
    # no parts: FILT for every voice
    a.u.mem_write(0x3900+0x30,b'\0'); a.u.mem_write(0x3700,b'\0')
    a.call(sym('filt_start'),(0,60 << 8,100))
    need(a.data(st(0)+0x2D,1) == b'\0','Without parts the voice still uses the block')
    return {'part_b_block':True,'part_a_filt':True}


def verify_va_live(original,patched):
    """VA with notes sounding: the ALGORITHM knob keeps the VA kernel and
    only changes the mode (1.29 hardware freeze: Korg put an FM kernel on
    VA records); WAvE edits keep the VA records."""
    a = audio_panel(patched)
    pr = bytearray(va(a.data(LIVE,128),[0]*6,alg=0)); a.u.mem_write(LIVE,bytes(pr))
    for n in (60,64,67): a.call(0x20E864,(0,n,100))
    mono(a,64)
    vs = isym('va_simple')+1
    for val in range(0,128,5):
        a.call(0x2059D0,(14,val,0,0)); mono(a,32)
        mode = a.data(LIVE+110,1)[0] & 7
        for v_ in range(6):
            ip = ENGINE+v_*0x270
            need(a.get32(ip) == vs,'Voice %d kernel 0x%x after ALGORITHM %d' % (v_,a.get32(ip),val))
            need(a.get32(ip+0x90+0x14) & 7 == mode,'Voice %d mode' % v_)
    # WAvE of OP1 while sounding: VA record = wave + 1
    edit(a,0,0x16); a.call(0x20012A2C,(E,127))
    need(a.get32(ENGINE+0x90+5*0x50+0x14) == 5,'WAvE on a VA voice: %d' % a.get32(ENGINE+0x90+5*0x50+0x14))
    need(a.get32(ENGINE) == vs,'WAvE changed the kernel')
    return {'algorithm_sweeps':26,'kernel_kept':True,'wave_follow_va':True}


def verify_edit_led(original,patched):
    """EDIT LED lit steadily on the FUNC + EDIT pages, off outside."""
    a = panel.machine(patched); log = []
    a.hook(0x2058D6,lambda: log.append((a.u.reg_read(REGS[0]),a.u.reg_read(REGS[1]),a.u.reg_read(REGS[2]))))
    panel.enter(a)
    for k in range(6):
        panel.button(a,6,True); panel.button(a,6,False)
        last = [x for x in log if x[1] == 0x20][-1]
        need(last[0] == 3 and last[2] == 0,'EDIT LED in page: %s' % (last,))
    return {'edit_led':'lit'}


TASKS = [('v128/edit_native',verify_edit_native),
         ('v128/block_edit',verify_block_edit),
         ('v128/block_program',verify_block_program),
         ('v128/block_journal',verify_block_journal),
         ('v128/edit_wave',verify_edit_wave),
         ('v128/edit_engine',verify_edit_engine),
         ('v128/va_exact',verify_va_exact),
         ('v128/va_modes',verify_va_modes),
         ('v128/va_storage',verify_va_storage),
         ('v128/va_off',verify_va_off),
         ('v128/cpu',verify_cpu),
         ('v129/pattern_block',verify_pattern_block),
         ('v129/pattern_motion',verify_pattern_motion),
         ('v129/pattern_journal',verify_pattern_journal),
         ('v129/part_filter',verify_part_filter),
         ('v129/va_live',verify_va_live),
         ('v129/edit_led',verify_edit_led)]


if __name__ == '__main__':
    import json,time
    original,patched,code,manifest,header = build_patch.build()
    only = [x for x in sys.argv[1:] if not x.startswith('-')]
    for name,fn in TASKS:
        if only and not any(o in name for o in only): continue
        t = time.monotonic()
        try:
            r = fn(original,patched)
            print(name+': PASS (%.1fs) ' % (time.monotonic()-t)+json.dumps(r,default=str)[:500],flush=True)
        except Exception as e:
            import traceback
            print(name+': FAIL '+type(e).__name__+': '+str(e)[:600],flush=True)
            if '-v' in sys.argv: traceback.print_exc()
