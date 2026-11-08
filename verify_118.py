"""1.18: delay as an alternative to the reverb.

Executes the patched ARM code (audio ISR, effect wrapper, panel, clock tick)
in the emulator. The delay output is compared frame by frame with an
independent Python model of the same algorithm; the reverb mode is compared
with the 1.17 image byte for byte.
"""
import random
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
import reverse_checks as native
from reverse_checks import audio_machine,render_isr,PATTERN
from arm_checks import REGS
from unicorn import UC_HOOK_CODE
import verify_panel as panel

FX = 0x3F80
BUF = 0x20029B00
BUF_BYTES = 49152
IO = 0x20000038            # the ISR's effect io pair (state 0x20000010 + 0x28)
ENTRY = 0x2059             # fx_audio through the jump table
DIV_K = [3,4,6,8,9,12,16,18,24]
FX_NAMES = ['REVRB','DELAY','LOFI ']
DIV_NAMES = ['1-32 ','1-24 ','1-16 ','1-12 ','3-32 ','1-8  ','1-6  ','3-16 ','1-4  ']


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def s32(v):
    v &= 0xFFFFFFFF
    return v-(1 << 32) if v & 0x80000000 else v


def u32(a,addr): return struct.unpack('<I',a.data(addr,4))[0]
def i32(a,addr): return struct.unpack('<i',a.data(addr,4))[0]


def setfx(a,type_=None,sync=None,pp=None,div=None,free=None,fb=None,period=None):
    for off,v in ((0,type_),(2,sync),(3,pp),(4,div),(5,free),(6,fb)):
        if v is not None: a.u.mem_write(FX+off,bytes([v]))
    if period is not None: a.u.mem_write(FX+0x10,struct.pack('<I',period))


def frame(a,x,y=0):
    a.u.mem_write(IO,struct.pack('<ii',x,y))
    a.call(ENTRY,(IO,))
    return struct.unpack('<ii',a.data(IO,8))


def settle(a,limit=2000):
    """Run silent frames until the transition (fade + clear) has finished."""
    n = 0
    while a.data(FX+0x19,1) != b'\0' or n == 0:
        frame(a,0); n += 1
        need(n < limit,'Transition did not finish')
    return n


# ---------------------------------------------------------------- model
def slots(key):
    return (49152 if key & 3 == 2 else 24576) >> ((key >> 2) & 1)


def samples(m,key):
    mx = slots(key)-4
    if m['sync']:
        v = (m['period']*DIV_K[m['div'] if m['div'] < 9 else 0]) // 12
        while v > mx: v >>= 1
        return max(v,16)
    s = m['free']
    return 250+(s*s*(mx-250))//16129


def limit(v):
    if v > 24576: v = 24576+((v-24576) >> 2)
    if v < -24576: v = ((v+24576) >> 2)-24576
    return max(-32768,min(32767,v))


def enc8(v):
    sign = 0
    if v < 0: sign,v = 0x80,-v
    m = min(v >> 4,2047)
    if m < 16: return sign | m
    p = m.bit_length()-1
    return sign | ((p-3) << 4) | ((m >> (p-4)) & 15)


def dec8(c):
    mant,seg = c & 15,(c >> 4) & 7
    v = ((2*mant+33) << (seg+2)) if seg else mant << 4
    return -v if c & 0x80 else v


class Model:
    def __init__(self,a):
        st = a.data(FX,0x44)
        self.key = st[1]
        self.m = {'sync':st[2],'pp':st[3],'div':st[4],'free':st[5],'fb':st[6],
                  'period':struct.unpack_from('<I',st,0x10)[0]}
        self.phase = st[7]
        g = lambda o: struct.unpack_from('<i',st,o)[0]
        self.lp,self.acc,self.w,self.D = g(0x1C),g(0x20),g(0x24),g(0x28)
        self.dL,self.dR,self.pL,self.pR,self.cL,self.cR = (g(o) for o in (0x2C,0x30,0x34,0x38,0x3C,0x40))
        self.n = slots(self.key)
        raw = a.data(BUF,BUF_BYTES)
        if self.key & 3 == 2: self.buf = list(raw)
        else: self.buf = list(struct.unpack('<%dh' % (BUF_BYTES//2),raw))

    def idx(self,i,c): return i*2+c if self.key & 4 else i

    def read(self,i,c):
        v = self.buf[self.idx(i,c)]
        return dec8(v) if self.key & 3 == 2 else v

    def write(self,i,c,v):
        self.buf[self.idx(i,c)] = enc8(v) if self.key & 3 == 2 else v

    def tap(self,i0,frac,c):
        s0 = self.read(i0,c)
        i1 = i0-1 if i0 > 0 else self.n-1
        return s0+(((self.read(i1,c)-s0)*frac) >> 12)

    def frame(self,x):
        d = s32(x-self.lp)
        self.lp = s32(self.lp+(d >> 1)+(d >> 3))
        self.phase ^= 1
        if self.phase:
            self.acc = self.lp
            t = samples(self.m,self.key) << 12
            self.D += max(-2048,min(2047,(t-self.D) >> 9))
            return ((self.pL >> 1)+(self.cL >> 1),(self.pR >> 1)+(self.cR >> 1))
        s16 = ((self.acc >> 1)+(self.lp >> 1)) >> 13
        di,frac = self.D >> 12,self.D & 0xFFF
        i0 = self.w-di
        if i0 < 0: i0 += self.n
        self.pL,self.pR = self.cL,self.cR
        fbq = self.m['fb']*321
        yL = self.tap(i0,frac,0)
        if self.key & 4:
            yR = self.tap(i0,frac,1)
            self.dL += ((yL-self.dL)*3) >> 2
            self.dR += ((yR-self.dR)*3) >> 2
            self.write(self.w,0,limit(s16+((self.dR*fbq) >> 15)))
            self.write(self.w,1,limit((self.dL*fbq) >> 15))
        else:
            yR = yL
            self.dL += ((yL-self.dL)*3) >> 2
            self.write(self.w,0,limit(s16+((self.dL*fbq) >> 15)))
        self.w = (self.w+1) % self.n
        self.cL,self.cR = s32(yL << 12),s32(yR << 12)
        return (self.cL,self.cR)


def test_signal(n,seed):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        if i < n//3:      # loud noise burst, beyond full scale (limiter, LOFI)
            out.append(rnd.randint(-(1 << 29),1 << 29))
        elif i < n//2:    # sine sweep
            out.append(int((1 << 27)*__import__('math').sin(i*i*1e-6)))
        else:             # silence: echoes and feedback only
            out.append(0)
    return out


# ---------------------------------------------------------------- tests
def verify_dsp_model(original,patched):
    """ARM delay == model, every frame, all layouts, feedback, SYNC/LIBERO,
    time changes during playback (glide)."""
    cases = []
    configs = [(1,0,0,0,40,None),(1,0,1,0,100,None),(1,1,0,3,70,None),
               (2,0,0,0,50,None),(2,1,1,8,95,None),(2,0,1,0,100,None),
               (1,1,1,5,30,None),(2,1,0,7,60,9000)]
    for n,(typ,sync,pp,div,fb,period) in enumerate(configs):
        a = audio_machine(patched)
        setfx(a,typ,sync,pp,div,(n*37) % 128,fb,period)
        settle(a)
        key = typ | (pp << 2)
        need(a.data(FX+1,1)[0] == key,'Layout key not activated')
        need(a.data(BUF,BUF_BYTES) == bytes(BUF_BYTES),'Buffer not cleared before the delay')
        m = Model(a)
        t1 = samples(m.m,key)
        new = dict(m.m)
        if sync: new['div'] = (div+4) % 9
        else: new['free'] = 127-m.m['free']
        t2 = samples(new,key)
        change = 2*t1+3000
        sig = test_signal(change,n)+[0]*(4*abs(t2-t1)+2*t2+4000)
        worst = 0
        for i,x in enumerate(sig):
            if i == change:     # change the time while echoes are running
                setfx(a,div=new['div'],free=new['free']); m.m = new
            got = frame(a,x); want = m.frame(x)
            need(got == want,f'Frame {i} config {n}: ARM {got} model {want}')
            worst = max(worst,abs(got[0]),abs(got[1]))
        raw = a.data(BUF,BUF_BYTES)
        mb = bytes(m.buf) if key & 3 == 2 else struct.pack('<%dh' % (BUF_BYTES//2),*m.buf)
        need(raw == mb,'Delay buffer differs from the model')
        need(worst > 0,f'Delay silent (config {n})')
        cases.append({'type':FX_NAMES[typ].strip(),'sync':sync,'pingpong':pp,'fb':fb,'frames':len(sig),
                      'slots':[t1,t2],'peak':worst})
    return {'configs':cases,'bit_exact':True}


def first_echo(a,amp=1 << 27,n=None):
    n = n or 2*slots(a.data(FX+1,1)[0])+64
    outs = [frame(a,amp if i == 0 else 0) for i in range(n)]
    for i,(l,r) in enumerate(outs):
        if l or r: return i,outs
    return None,outs


def verify_times(original,patched):
    """Echo time = setting: LIBERO limits, SYNC divisions, halving, layouts."""
    res = []
    for typ,pp in ((1,0),(1,1),(2,0),(2,1)):
        key = typ | (pp << 2)
        for free in (0,64,127):
            a = audio_machine(patched)
            setfx(a,typ,0,pp,None,free,0)
            settle(a)
            want = samples({'sync':0,'free':free},key)
            i,outs = first_echo(a)
            need(i is not None and abs(i-2*want) <= 2,f'Echo at {i}, expected about {2*want} ({key},{free})')
            if pp:  # ping-pong: right echo only, then left at twice... with fb=0 only L
                need(all(r == 0 for l,r in outs),'Ping-pong with feedback 0 leaked to R')
            res.append({'key':key,'free':free,'slots':want,'ms':round(want/25,1),'echo_frame':i})
    # ping-pong with feedback: L at T, R at 2T
    a = audio_machine(patched)
    setfx(a,1,0,1,None,20,80); settle(a)
    T = samples({'sync':0,'free':20},5)
    outs = [frame(a,(1 << 27) if i == 0 else 0) for i in range(4*T+80)]
    fl = next(i for i,(l,r) in enumerate(outs) if l)
    fr = next(i for i,(l,r) in enumerate(outs) if r)
    need(abs(fl-2*T) <= 2 and abs(fr-4*T) <= 3,f'Ping-pong order wrong: L {fl} R {fr} T {T}')
    # SYNC: 120 BPM (6250 frames per 16th), every division, halving when too long
    sync = []
    for div in range(9):
        a = audio_machine(patched)
        setfx(a,1,1,0,div,None,0,6250); settle(a)
        v = (6250*DIV_K[div])//12
        while v > 24572: v >>= 1
        i,_ = first_echo(a)
        need(abs(i-2*v) <= 2,f'SYNC division {div}: echo {i}, expected {2*v}')
        sync.append({'div':DIV_NAMES[div].strip(),'ms':round(v/25,1)})
    a = audio_machine(patched)
    setfx(a,1,1,1,8,None,0,6250); settle(a)   # 1/4 = 500 ms > 491 ms ping-pong: halved
    i,_ = first_echo(a)
    need(abs(i-2*6250) <= 2,'Halving of a too long SYNC time failed')
    return {'free':res,'sync_120bpm':sync,'pingpong_L_then_R':True,'halving':True}


def verify_reverb_unchanged(original,patched):
    """Reverb selected (power-on default): ISR output identical to 1.17."""
    old = original                   # 1.13-1.17 never changed the audio path
    shas = []
    for chorus,reverb,level in ((0,1,127),(1,1,96),(1,0,96),(0,1,40)):
        outs = []
        for img in (old,patched):
            a = audio_machine(img)
            a.call(0x20E864,(0,60,100)); a.call(0x20E864,(1,67,90))
            a.call(0x20EA70,(100,)); a.call(0x2045F4,(chorus,))
            a.call(0x20EA84,(level,)); a.call(0x20453C,(reverb,))
            a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
            raw = render_isr(a,6000,service_every=64)
            a.call(0x20E7C8,(0,)); a.call(0x20E7C8,(1,))
            raw += render_isr(a,6000,service_every=64)
            outs.append(raw)
        need(outs[0] == outs[1],'Reverb mode output differs from the original 1.12')
        shas.append(native.digest(outs[1])[:16])
    return {'cases':4,'identical_to_original_1_12':True,'sha':shas}


def isr_machine(img,type_,level=127,on=1,**kw):
    a = audio_machine(img)
    setfx(a,type_,**kw)
    a.call(0x20EA70,(0,)); a.call(0x2045F4,(0,))
    a.call(0x20EA84,(level,)); a.call(0x20453C,(on,))
    a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
    return a


def verify_isr_integration(original,patched):
    """Real audio ISR: delay echoes come out through the native REVRB level;
    with the effect off (FUNC+4) the output equals the 1.17 dry output."""
    # Effect off: identical to 1.17 with reverb off.
    old = original
    outs = []
    for img,t in ((old,0),(patched,1),(patched,2)):
        a = isr_machine(img,t,on=0,sync=0,free=40,fb=60)
        a.call(0x20E864,(0,60,100))
        raw = render_isr(a,3000,service_every=64)
        a.call(0x20E7C8,(0,))
        raw += render_isr(a,12000,service_every=64)
        outs.append(raw)
    need(outs[0] == outs[1] == outs[2],'Effect off: output differs from the original dry output')
    # Effect on: wet = output with REVRB level 127 - output with level 0.
    T = samples({'sync':0,'free':40},1)
    def note_run(level):
        m = isr_machine(patched,1,level=level,sync=0,free=40,fb=60)
        render_isr(m,1200)                   # transition (fade + clear), level settles
        need(m.data(FX+1,1) == b'\1','Delay not active in the ISR')
        m.call(0x20E864,(0,72,127))
        raw = render_isr(m,600,service_every=64)
        m.call(0x20E7C8,(0,))
        raw += render_isr(m,6*T,service_every=64)
        return m,struct.unpack('<%di' % (len(raw)//4),raw)
    a,full = note_run(127)
    _,dry = note_run(0)
    wet = [x-y for x,y in zip(full,dry)]
    L,R = wet[0::2],wet[1::2]
    first = next(i for i,v in enumerate(L) if v)
    # (the FM attack makes the first non-zero input a few frames after note-on)
    need(2*T <= first <= 2*T+20,f'First wet sample at {first}, expected {2*T}')
    need(L == R,'Mono delay not identical on both sides')
    def energy(lo,hi): return sum(abs(v) for v in L[lo:hi])/(hi-lo)
    e1,e2,e3 = energy(2*T,2*T+600),energy(4*T,4*T+600),energy(6*T-600,6*T)
    need(e1 > e2 > 0 and e3 > 0,'Echoes do not decay with feedback 60')
    # the wet level matches the dry note level (REVRB 127 = 0.89 x)
    d1 = sum(abs(v) for v in dry[0:1200:2])/600
    need(0.2 < e1/d1 < 1.5,f'Wet level {e1/d1:.2f} of the dry note')
    # buffer guards untouched
    a.u.mem_write(0x20029AF0,b'\x5A'*16); a.u.mem_write(0x20035B00,b'\xA5'*16)
    for t,pp in ((2,1),(1,1),(2,0),(0,0)):
        setfx(a,t,pp=pp); render_isr(a,1500)
        need(a.data(0x20029AF0,16) == b'\x5A'*16 and a.data(0x20035B00,16) == b'\xA5'*16,
             'Buffer guard altered')
    return {'off_identical_to_original':True,'first_echo_frame':first,'echo_energy':[round(e1),round(e2),round(e3)],
            'wet_to_dry':round(e1/d1,2),
            'level_zero_silent':True,'guards':True,'delay_slots':T}


def verify_transitions(original,patched):
    """Type/layout changes: fade out, clear the whole buffer, then start;
    the reverb comes back from silence."""
    a = isr_machine(patched,0)
    a.call(0x20E864,(0,60,127)); render_isr(a,4000,service_every=64)
    need(any(a.data(BUF,BUF_BYTES)),'Reverb buffer unused')
    results = []
    for t,pp in ((1,0),(1,1),(2,1),(2,0),(0,0),(0,1),(1,1)):
        before = a.data(FX+1,1)[0]
        setfx(a,t,pp=pp)
        key = t | (pp << 2) if t else 0
        outs = []; n = 0
        while True:
            a.call(0x10)
            outs.append(struct.unpack('<ii',a.data(0x20000038,8)))
            n += 1
            if a.data(FX+0x19,1) == b'\0' and n > 1: break
            need(n < 1000,'Transition stuck')
        if key == before:
            need(n == 2,'Unneeded transition'); results.append({'key':key,'frames':0}); continue
        need(a.data(FX+1,1)[0] == key,'Wrong layout after transition')
        need(256 <= n <= 520,f'Transition length {n}')
        # the clear phase outputs silence
        need(all(o == (0,0) for o in outs[257:-1]),'Clear phase not silent')
        results.append({'key':key,'frames':n})
        render_isr(a,3000,service_every=64)
    # right after a switch to the reverb the buffer was fully cleared
    a2 = isr_machine(patched,1)
    a2.call(0x20E864,(0,60,127)); render_isr(a2,5000,service_every=64)
    need(any(a2.data(BUF,BUF_BYTES)),'Delay buffer unused')
    setfx(a2,0)
    a2.call(0x10)
    while a2.data(FX+0x19,1) != b'\0': a2.call(0x10)
    # the frame that finishes the clear starts the reverb on an empty buffer
    need(a2.data(FX+1,1) == b'\0','Reverb not restored')
    need(a2.data(BUF,BUF_BYTES) == bytes(BUF_BYTES),'Buffer not cleared when returning to the reverb')
    render_isr(a2,2000,service_every=64)
    need(any(a2.data(BUF,BUF_BYTES)),'Reverb not running after the return')
    # pages changes that do not change the layout never interrupt the sound
    setfx(a2,1,pp=0); render_isr(a2,600)
    for kw in ({'sync':0},{'free':10},{'fb':90},{'sync':1},{'div':2}):
        setfx(a2,**kw); render_isr(a2,8)
        need(a2.data(FX+0x19,1) == b'\0','Parameter change caused a transition')
    return {'transitions':results}


def verify_tempo(original,patched):
    """Frames per 16th measured from the clock ticks (72 per 16th) through
    the patched arpeggiator tick entry, with the audio frames of the ISR."""
    a = audio_machine(patched)
    def run(period,steps):
        acc = 0.0
        for s in range(steps):
            for t in range(72):
                acc += period/72
                k = int(acc); acc -= k
                for _ in range(k): a.call(ENTRY,(IO,))
                a.call(0x20C40C,(0x20003E10,))
    out = []
    for bpm in (60,90,120,133,174,240):
        period = 50000*60/bpm/4
        run(period,3)
        got = u32(a,FX+0x10)
        need(abs(got-period) <= 2,f'{bpm} BPM: measured {got}, expected {period:.1f}')
        out.append({'bpm':bpm,'frames_per_16th':got})
    # pause longer than 0.5 s: the next 16th is measured from the restart
    for _ in range(30000): a.call(ENTRY,(IO,))
    run(50000*60/100/4,2)
    need(abs(u32(a,FX+0x10)-7500) <= 2,'Restart after a pause mis-measured')
    # ticks without audio frames (no ISR): absurd periods are ignored
    for _ in range(72): a.call(0x20C40C,(0x20003E10,))
    before = u32(a,FX+0x10)
    for _ in range(300): a.call(0x20C40C,(0x20003E10,))
    need(u32(a,FX+0x10) == before,'Ticks without frames changed the tempo')
    return {'measured':out,'restart':True}


def counted_machine(img,type_,**kw):
    # The counting hook is installed before any code runs, so every
    # translated block is instrumented; it only counts while enabled.
    a = audio_machine(img)
    a.count = [0,False]
    def cb(*x):
        if a.count[1]: a.count[0] += 1
    a.u.hook_add(UC_HOOK_CODE,cb)
    setfx(a,type_,**kw)
    a.call(0x20EA84,(127,)); a.call(0x20453C,(1,))
    a.call(0x20EA70,(100,)); a.call(0x2045F4,(1,))
    a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
    for v in range(6): a.call(0x20E864,(v,48+7*v,127))
    return a


def count_isr(a,frames):
    counts = []
    for _ in range(frames):
        a.count[:] = [0,True]; a.call(0x10); counts.append(a.count[0])
    a.count[1] = False
    return counts


def verify_cpu(original,patched):
    """Instructions per audio frame (whole ISR, 6 voices, chorus on): every
    delay layout must not cost more, at its peak, than the 1.17 reverb."""
    res = {}
    for name,t,pp in (('REVRB',0,0),('DELAY',1,0),('DELAY_PP',1,1),('LOFI',2,0),('LOFI_PP',2,1)):
        a = counted_machine(patched,t,pp=pp,sync=1,div=8,fb=100)
        render_isr(a,1100)
        c = count_isr(a,400)
        res[name] = {'max':max(c),'mean':round(sum(c)/len(c),1)}
    # transition frames (fade over the reverb, then clear)
    a = counted_machine(patched,0)
    render_isr(a,200)
    setfx(a,2,pp=1)
    c = count_isr(a,520)
    res['TRANSITION'] = {'max':max(c),'mean':round(sum(c)/len(c),1)}
    # the same ISR on the 1.17 image (reverb called directly)
    a = counted_machine(original,0); render_isr(a,1100)
    c = count_isr(a,400)
    res['REVRB_1_12'] = {'max':max(c),'mean':round(sum(c)/len(c),1)}
    rev = res['REVRB_1_12']['max']
    for k in ('DELAY','DELAY_PP','LOFI','LOFI_PP'):
        need(res[k]['max'] <= rev,f'{k} peak costs more than the 1.17 reverb: {res[k]["max"]} > {rev}')
    need(res['REVRB']['max'] <= rev+40,'Reverb wrapper overhead too high')
    need(res['TRANSITION']['max'] <= rev+100,'Transition overhead too high')
    res['note'] = 'instructions per audio frame, whole ISR, 6 voices + chorus; transition = 512 frames (about 10 ms) only'
    return res


def page_machine(img):
    a = panel.machine(img)
    panel.enter(a)
    for _ in range(7): panel.button(a,6,True); panel.button(a,6,False)
    return a


def key(a,step):
    a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(step),)); a.call(0x20FC18,(0,))


def verify_panel_pages(original,patched):
    a = page_machine(patched)
    panel.check_display(a,'FX REVRB ')
    seen = set()
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*2+63)//127; seen.add(want)
        need(a.data(FX,1)[0] == want,'FX slider wrong')
        panel.check_display(a,'FX '+FX_NAMES[want]+' ')
    need(seen == {0,1,2},'Not every effect reachable')
    a.call(0x2059D0,(3,64,0,0))                 # DELAY
    # dt, SYNC: divisions
    panel.button(a,6,True); panel.button(a,6,False)
    panel.check_display(a,'dt 3-16  ')
    seen = set()
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*8+63)//127; seen.add(want)
        need(a.data(FX+4,1)[0] == want,'dt SYNC slider wrong')
        panel.check_display(a,'dt '+DIV_NAMES[want]+' ')
    need(seen == set(range(9)),'Not every division reachable')
    key(a,15); panel.check_display(a,'LIBERO   ')
    need(a.data(FX+2,1) == b'\0','Key 16 did not select LIBERO')
    for v in (0,1,64,100,127):
        a.call(0x2059D0,(3,v,0,0))
        ms = samples({'sync':0,'free':v},1)//25
        panel.check_display(a,'dt '+f'{ms:4d}'+'ms')
    need(a.data(FX+5,1) == b'\x7f','LIBERO slider not stored')
    key(a,15); panel.check_display(a,'SYNC     ')
    need(a.data(FX+2,1) == b'\1' and a.data(FX+5,1) == b'\x7f','SYNC/LIBERO toggle lost values')
    # Fb
    panel.button(a,6,True); panel.button(a,6,False)
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*100+63)//127
        need(a.data(FX+6,1)[0] == want,'Fb slider wrong')
        panel.check_display(a,f'Fb {want:03} MO')
    key(a,15); panel.check_display(a,'PING PONG')
    need(a.data(FX+3,1) == b'\1','Key 16 did not select ping-pong')
    a.call(0x2059D0,(3,0,0,0)); panel.check_display(a,'Fb 000 PP')
    key(a,15); panel.check_display(a,'MONO     ')
    for k in range(15):
        key(a,k); need(a.data(FX+3,1) == b'\0','Other keys changed the Fb option')
    # LIBERO in ping-pong and LOFI: the maximum follows the layout
    key(a,15)
    panel.button(a,7,True); panel.button(a,7,False); panel.button(a,7,True); panel.button(a,7,False)
    a.call(0x2059D0,(3,127,0,0))                # FX -> LOFI
    panel.button(a,6,True); panel.button(a,6,False); key(a,15)  # dt LIBERO? (was SYNC) -> LIBERO
    a.call(0x2059D0,(3,127,0,0))
    panel.check_display(a,f'dt {samples({"sync":0,"free":127},6)//25:4d}ms')
    # wrap-around: dt -> Fb -> CH -> CC -> CR (1.19) -> P
    for _ in range(5): panel.button(a,6,True); panel.button(a,6,False)
    panel.check_display(a,'01 P100  ')
    # glyphs
    texts = FX_NAMES+DIV_NAMES+['FX','dt','Fb','ms','MO','PP','SYNC','LIBERO','MONO','PING PONG',
                                'DELAY ON','DELAY OFF','LOFI ON','LOFI OFF','REVRB ON','REVRB OFF']
    for t in texts:
        g = panel.glyphs(a,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    panel.button(a,0,True); panel.button(a,0,False)
    need(a.data(0x3F00,1) == b'\0','Page did not close')
    need(a.data(FX,7) == bytes([2,0,0,1,8,127,0]),'Settings lost on leaving the page: '+a.data(FX,7).hex())
    return {'FX':3,'divisions':9,'free_ms_examples':True,'fb_levels':101,'keys':True,'glyphs':len(texts)}


def func4(a):
    panel.button(a,0,True)
    a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(3),)); a.call(0x20FC18,(0,))
    for _ in range(3): panel.scan(a)
    panel.button(a,0,False)


def verify_func4_and_label(original,patched):
    a = panel.machine(patched)
    res = []
    for t,name in ((0,'REVRB'),(1,'DELAY'),(2,'LOFI ')):
        setfx(a,t)
        func4(a); on = a.data(0x20000011,1)[0]
        need(on == 1 and (name.strip()+' ON').ljust(9) in a.texts,f'FUNC+4 ON message for {name}')
        func4(a); on = a.data(0x20000011,1)[0]
        need(on == 0 and (name.strip()+' OFF').ljust(9) in a.texts,f'FUNC+4 OFF message for {name}')
        res.append(name.strip())
    # pattern bit and native flag behave as in the original
    b = panel.machine(original)
    func4(b)
    c = panel.machine(patched); setfx(c,1); func4(c)
    need(c.data(PATTERN+0x45,1) == b.data(PATTERN+0x45,1) and
         c.data(0x20000011,1) == b.data(0x20000011,1),'FUNC+4 state differs from the original')
    # REVRB level readout
    for t,label in ((0,'REVRB '),(1,'DELAY '),(2,'LOFI  ')):
        setfx(a,t)
        a.call(0x2059D0,(5,100,0,0))
        need(a.texts[-1] == label+'100','Level readout '+repr(a.texts[-1]))
    o = panel.machine(original); o.call(0x2059D0,(5,100,0,0))
    need(o.texts[-1] == 'REVRB 100','Original readout changed?')
    return {'messages':res,'pattern_bit_as_original':True,'level_label':True}


def verify_power_on(original,patched):
    a = audio_machine(patched)
    st = a.data(FX,0x44)
    need(st[:8] == bytes([0,0,1,0,7,64,50,0]),'Power-on state wrong: '+st[:8].hex())
    need(struct.unpack_from('<I',st,0x10)[0] == 6250,'Default tempo not 120 BPM')
    need(a.data(0x023C,4) == struct.pack('<I',0x2059),'ISR literal not patched')
    return {'type':'REVRB','sync':'1-8.','free':64,'fb':50,'tempo_default_bpm':120}


TASKS = [('v118/power_on',verify_power_on),
         ('v118/reverb_unchanged',verify_reverb_unchanged),
         ('v118/dsp_model',verify_dsp_model),
         ('v118/times',verify_times),
         ('v118/isr_integration',verify_isr_integration),
         ('v118/transitions',verify_transitions),
         ('v118/tempo',verify_tempo),
         ('v118/cpu',verify_cpu),
         ('v118/panel_pages',verify_panel_pages),
         ('v118/func4_and_label',verify_func4_and_label)]

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
