"""1.22: PHASER and TREMOLO as alternatives to the native chorus, tape LOFI.

Executes the patched ARM code (modulation entry of the audio ISR, the whole
ISR, panel pages, pattern load) in the emulator. The phaser and the tremolo
are compared frame by frame with an independent Python model; the chorus
mode is compared with the original 1.12 ISR output.
"""
import math
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
from unicorn.arm_const import UC_ARM_REG_R1
import verify_panel as panel
import verify_118 as v118

MOD = 0x3B80
TAB = 0x3A00
CH = 0x200011D0             # native chorus state (+0x40 level, +0x44 target)
ENTRY = 0x2061              # mod_audio through the jump table (entry 24)
FX = 0x3F80
CH_LINES = (0x20000070,1112*4)


def need(ok,msg):
    if not ok: raise AssertionError(msg)


s32 = v118.s32
def u32(v): return v & 0xFFFFFFFF
def sat(v,bits):
    lo,hi = -(1 << (bits-1)),(1 << (bits-1))-1
    return max(lo,min(hi,v))


def put(a,addr,fmt,*v): a.u.mem_write(addr,struct.pack(fmt,*v))
def get(a,addr,fmt): return struct.unpack(fmt,a.data(addr,struct.calcsize(fmt)))


def call_mod(a,l,r):
    a.call(ENTRY,(u32(l),u32(r)))
    return s32(a.u.reg_read(REGS[0])),s32(a.u.reg_read(UC_ARM_REG_R1))


# ---------------------------------------------------------------- model
def sine(ph):
    v = s32(ph) >> 16
    t = 32768-(v ^ (v >> 31))
    return sat(s32(v*t) >> 13,16)


def period_ms(v): return round(20000*0.005**(v/127))


class ModModel:
    def __init__(self,a):
        st = a.data(MOD,0x44)
        self.type = st[1]
        self.sync,self.st,self.div,self.res,self.shape = st[2],st[3],st[4],st[6],st[7]
        g = lambda o: struct.unpack_from('<i',st,o)[0]
        self.ph = struct.unpack_from('<I',st,0xC)[0]
        self.inc = struct.unpack_from('<I',st,0x10)[0]
        self.sL = [g(0x14+4*i) for i in range(4)]
        self.sR = [g(0x24+4*i) for i in range(4)]
        self.lastL,self.lastR = g(0x34),g(0x38)
        self.n16 = struct.unpack_from('<I',st,0x3C)[0]
        self.fbq = struct.unpack_from('<H',st,0x40)[0]
        self.cur,self.tgt = get(a,CH+0x40,'<ii')
        self.fx = get(a,FX+8,'<III')
        self.tab = list(struct.unpack('<65i',a.data(TAB,260)))

    def common(self):
        d = s32(self.cur-self.tgt)
        r = -((-d) >> 7) if d >= 0 else d >> 7
        self.cur = s32(self.cur-r)
        if not self.sync:
            self.ph = u32(self.ph+self.inc)
            return
        frames,last,f16 = self.fx
        e = u32(frames-last)
        k = 1 << self.div
        step = 0xFFFFFFFF//u32(f16*k)
        if e > 2*f16:
            self.ph = u32(self.ph+step)
            return
        e = min(e,f16)
        self.ph = u32(((self.n16 & (k-1))*f16+e)*step)

    def coef(self,ph):
        u = sine(ph)+32768
        i,fr = u >> 10,u & 1023
        a0,a1 = self.tab[i],self.tab[i+1]
        return s32(a0+(s32(a1-a0) >> 10)*fr)

    def chain(self,x,last,s,a):
        x = sat(s32(x+(((last*self.fbq) >> 16) << 1)),26)
        for i in range(4):
            y = s32(s[i]+((a*s32(x << 1)) >> 32))
            s[i] = s32(((x << 32)-a*s32(y << 1)) >> 32)
            x = y
        return x

    def frame(self,l,r):
        self.common()
        if self.type == 1:
            yl = self.chain(l,self.lastL,self.sL,self.coef(self.ph)); self.lastL = yl
            phr = u32(self.ph+0x40000000) if self.st else self.ph
            yr = self.chain(r,self.lastR,self.sR,self.coef(phr)); self.lastR = yr
            return s32((yl*self.cur) >> 25),s32((yr*self.cur) >> 25)
        depth = (u32((self.cur >> 6)*8738)) >> 16
        g = 16+((self.shape*41) >> 6)
        uL = sat((sine(self.ph)*g) >> 4,16)+32768
        uR = 65535-uL if self.st else uL
        aL,aR = (u32(depth*uL)) >> 8,(u32(depth*uR)) >> 8
        return s32(-((l*aL) >> 24)),s32(-((r*aR) >> 24))


def mod_machine(img,type_,sync=0,st=1,div=4,free=55,res=30,shape=0,level=0x1E00000):
    a = audio_machine(img)
    put(a,MOD,'<BBBBBBBB',type_,type_,sync,st,div,free,res,shape)
    put(a,MOD+0x10,'<I',85899346//period_ms(free))
    put(a,MOD+0x40,'<H',res*180)
    put(a,CH+0x40,'<ii',level,level)
    return a


def signal(n,seed):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        if i < n//3:
            out.append((rnd.randint(-(1 << 23),1 << 23),rnd.randint(-(1 << 23),1 << 23)))
        elif i < 2*n//3:
            s = int((1 << 22)*math.sin(i*0.03))
            out.append((s,-s))
        else:
            out.append((1 << 23,-(1 << 23)) if (i//300) & 1 else (-(1 << 23),1 << 23))
    return out


# ---------------------------------------------------------------- tests
def verify_static(original,patched):
    """Builder data: phaser coefficient table, initial state, ISR literal."""
    a = audio_machine(patched)
    tab = struct.unpack('<65i',a.data(TAB,260))
    for i,v in enumerate(tab):
        fc = 120*(1600/120)**(i/64); t = math.tan(math.pi*fc/50000)
        need(abs(v-(t-1)/(t+1)*2**31) <= 1,'Phaser coefficient %d wrong' % i)
    need(all(tab[i] < tab[i+1] for i in range(64)),'Coefficients not monotonic')
    st = a.data(MOD,0x44)
    need(st[:8] == bytes([0,0,0,1,4,55,30,0]),'Initial modulation state wrong: '+st[:8].hex())
    need(struct.unpack_from('<I',st,0x10)[0] == 85899346//2016,'LIBERO increment wrong')
    need(struct.unpack_from('<H',st,0x40)[0] == 30*180,'Resonance wrong')
    need(get(a,0x238,'<I')[0] == 0x2061,'ISR chorus literal not redirected')
    need(get(original_machine(original),0x238,'<I')[0] == 0x12AD,'Original literal unexpected')
    return {'table_hz':[120,1600],'entries':65,'state':st[:8].hex(),'literal':'0x12AD -> 0x2061'}


def original_machine(img): return audio_machine(img)


def verify_model(original,patched):
    """ARM phaser/tremolo == model, every frame: STEREO/MONO, PAN, LIBERO and
    SYNC, resonance, shape, level glides (native smoothing)."""
    configs = [dict(type_=1),dict(type_=1,st=0,res=100,free=127),dict(type_=1,res=0,free=0),
               dict(type_=1,sync=1,div=0),dict(type_=2),dict(type_=2,st=0,shape=100,free=110),
               dict(type_=2,sync=1,div=2,shape=50),dict(type_=1,sync=1,div=6,res=70)]
    res = []
    for n,c in enumerate(configs):
        a = mod_machine(patched,**c)
        if c.get('sync'):
            put(a,FX+8,'<III',100000,100000-37,6250)
            put(a,MOD+0x3C,'<I',13)
        m = ModModel(a)
        sig = signal(3000,n)
        peak = 0
        for i,(l,r) in enumerate(sig):
            if i == 1000:       # level change: glide
                put(a,CH+0x44,'<i',0x0800000); m.tgt = 0x0800000
            if c.get('sync') and i % 400 == 0:   # clock: frames and sixteenths advance
                f = (100000+i,100000+i-(i*7) % 6000,6250)
                put(a,FX+8,'<III',*f); m.fx = f
                put(a,MOD+0x3C,'<I',13+i//400); m.n16 = 13+i//400
            got = call_mod(a,l,r); want = m.frame(l,r)
            need(got == want,f'Config {n} frame {i}: ARM {got} model {want}')
            peak = max(peak,abs(got[0]),abs(got[1]))
        need(peak > 0,'Silent')
        need(get(a,MOD+0xC,'<I')[0] == m.ph,'LFO phase differs')
        res.append({'type':['','PHASER','TREMOLO'][c['type_']],'peak':peak,
                    **{k:v for k,v in c.items() if k != 'type_'}})
    return {'configs':res,'bit_exact':True}


def verify_sound(original,patched):
    """What it does: the phaser moves notches (sum with dry), stereo phase
    offset; the tremolo modulates the gain from 1 to 1 - level, PAN in
    opposition, period = setting."""
    out = {}
    # phaser: dry + wet on a sine at 600 Hz swings in level as the notch passes
    a = mod_machine(patched,1,free=127,res=60)    # 100 ms period
    env = []
    for i in range(10000):
        x = int((1 << 22)*math.sin(2*math.pi*600*i/50000))
        l,r = call_mod(a,x,x)
        env.append((abs(x+l),abs(x+r)))
    blk = [max(e[0] for e in env[j:j+250]) for j in range(5000,10000,250)]
    out['phaser_600Hz_level_range'] = [min(blk)/(1 << 22),max(blk)/(1 << 22)]
    need(min(blk) < 0.5*max(blk),'Phaser notch too shallow: '+str(out['phaser_600Hz_level_range']))
    blr = [max(e[1] for e in env[j:j+250]) for j in range(5000,10000,250)]
    need(blk != blr,'STEREO: L and R identical')
    # tremolo: constant input -> gain follows the LFO, 1 .. 0
    a = mod_machine(patched,2,free=127,st=1)
    g = []
    for i in range(10000):
        l,r = call_mod(a,1 << 22,1 << 22)
        g.append(((1 << 22)+l,(1 << 22)+r))
    gl = [x[0]/(1 << 22) for x in g]; gr = [x[1]/(1 << 22) for x in g]
    need(max(gl) > 0.99 and min(gl) < 0.02,'Tremolo depth at full level wrong: %f %f' % (min(gl),max(gl)))
    need(all(abs(x+y-1) < 0.01 for x,y in zip(gl,gr)),'PAN: L + R not constant')
    ups = [i for i in range(1,10000) if gl[i-1] < 0.5 <= gl[i]]
    per = (ups[-1]-ups[0])/(len(ups)-1) if len(ups) > 1 else 0
    need(abs(per-5000) < 60,'Tremolo period %.0f frames, expected 5000 (100 ms)' % per)
    out['tremolo_gain'] = [round(min(gl),3),round(max(gl),3)]
    out['tremolo_period_frames'] = per
    # SYNC 1-1 at 120 BPM: one cycle per 16 sixteenths
    a = mod_machine(patched,2,sync=1,div=4,st=0)
    phs = []
    for n16 in range(17):
        put(a,MOD+0x3C,'<I',n16); put(a,FX+8,'<III',1000+n16*6250,1000+n16*6250,6250)
        call_mod(a,0,0); phs.append(get(a,MOD+0xC,'<I')[0])
    need(phs[0] == 0 and phs[16] == 0 and abs(phs[8]-0x80000000) < 1 << 16,'SYNC phase wrong')
    # half a sixteenth later: in between
    put(a,FX+8,'<III',1000+3125,1000,6250); put(a,MOD+0x3C,'<I',0); call_mod(a,0,0)
    need(abs(get(a,MOD+0xC,'<I')[0]-0x08000000) < 1 << 12,'SYNC interpolation wrong')
    out['sync_phase_per_16th'] = hex(phs[1])
    return out


def verify_chorus_unchanged(original,patched):
    """CHORUS (default): the whole ISR output equals the original 1.12."""
    outs = []
    for img in (original,patched):
        a = audio_machine(img)
        a.call(0x20E864,(0,60,100)); a.call(0x20E864,(1,64,90))
        a.call(0x20EA70,(110,)); a.call(0x2045F4,(1,))
        a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
        outs.append(render_isr(a,5000,service_every=64))
    need(outs[0] == outs[1],'Chorus output differs from 1.12')
    return {'identical_to_1_12':True,'sha':native.digest(outs[1])[:16]}


def isr(img,level=110):
    a = audio_machine(img)
    a.call(0x20E864,(0,60,100)); a.call(0x20E864,(1,67,90))
    a.call(0x20EA70,(level,)); a.call(0x2045F4,(1,))
    a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
    return a


def verify_transitions(original,patched):
    """Type changes: fade out, (clear the chorus lines), switch, fade in;
    no click; back to the chorus = output identical to a fresh chorus."""
    a = isr(patched)
    render_isr(a,3000)
    need(any(a.data(*CH_LINES)),'Chorus lines not in use')
    res = {}
    for t in (1,2,1,0):
        put(a,MOD,'<B',t)
        n = 0; switched = None
        while True:
            a.call(0x10); n += 1
            if switched is None and a.data(MOD+1,1)[0] == t:
                switched = n
                # at the switch: the old effect is silent, the new one starts clean
                if t == 0: need(a.data(*CH_LINES) == bytes(CH_LINES[1]),'Chorus lines not cleared')
                else: need(a.data(MOD+0x14,0x28) == bytes(0x28),'Phaser states not reset')
            if switched and a.data(MOD+8,1) == b'\0': break
            need(n < 2000,'Transition to %d did not finish' % t)
        res['to_%d' % t] = [switched,n]
        render_isr(a,600)
        if t == 0: need(any(a.data(*CH_LINES)),'Chorus not running after the return')
    need(res['to_1'] == [257,513] and res['to_0'] == [256+139,256+139+256],
         'Unexpected transition lengths: '+str(res))
    # the wet signal fades: no step in the output at the change
    out = {}
    for img,t in ((patched,None),(patched,1)):
        b = isr(img); render_isr(b,2000)
        if t: put(b,MOD,'<B',t)
        raw = render_isr(b,700)
        v = struct.unpack('<%di' % (len(raw)//4),raw)
        out[t] = max(abs(v[i+2]-v[i]) for i in range(0,len(v)-2,2))
    need(out[1] <= 1.5*out[None]+(1 << 20),'Click at the change: %d vs %d' % (out[1],out[None]))
    return {'frames_switch_end':res,'max_step':{'steady':out[None],'change':out[1]}}


def verify_cpu(original,patched):
    """Instructions per audio frame, whole ISR (6 voices, chorus slot on):
    PHASER/TREMOLO with the reverb and with the heaviest delay (LOFI
    ping-pong) against the chorus with the reverb on the original 1.12."""
    res = {}
    def run(img,mod,fxt=0,pp=0):
        a = v118.counted_machine(img,fxt,pp=pp,sync=1,div=8,fb=100)
        if mod:
            put(a,MOD,'<BBBBBBBB',mod,mod,0,1,4,55,30,50)
            put(a,MOD+0x10,'<I',85899346//2016); put(a,MOD+0x40,'<H',5400)
        render_isr(a,1100)
        c = v118.count_isr(a,400)
        return {'max':max(c),'mean':round(sum(c)/len(c),1)}
    res['CHORUS_REVRB_1_12'] = run(original,0)
    for name,mod,fxt,pp in (('CHORUS_REVRB',0,0,0),('PHASER_REVRB',1,0,0),('TREMOLO_REVRB',2,0,0),
                            ('PHASER_LOFI_PP',1,2,1),('TREMOLO_LOFI_PP',2,2,1),('PHASER_DELAY_PP',1,1,1)):
        res[name] = run(patched,mod,fxt,pp)
    ref = res['CHORUS_REVRB_1_12']['max']
    need(res['CHORUS_REVRB']['max'] <= ref+40,'Chorus wrapper overhead too high')
    worst = max(v['max'] for k,v in res.items() if k != 'CHORUS_REVRB_1_12')
    res['worst_over_1_12'] = worst-ref
    res['worst_over_1_12_pct'] = round(100*(worst-ref)/ref,1)
    need(worst <= res['CHORUS_REVRB']['max']+40,'Modulation peak too expensive: +%d' % (worst-ref))
    res['note'] = 'instructions per 50 kHz frame, whole ISR'
    return res


def verify_pages(original,patched):
    """MOD / rt / rS-Fo pages, keys 16, label on FUNC + chorus key."""
    a = panel.machine(patched)
    panel.enter(a)
    for _ in range(10): panel.button(a,6,True); panel.button(a,6,False)
    panel.check_display(a,'CHORUS   ')
    names = ['CHORUS   ','PHASER   ','TREMOLO  ']
    seen = set()
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*2+63)//127; seen.add(want)
        need(a.data(MOD,1)[0] == want,'Type slider wrong')
        panel.check_display(a,names[want])
    need(seen == {0,1,2},'Not every type reachable')
    def key16():
        a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(15),)); a.call(0x20FC18,(0,))
    a.call(0x2059D0,(3,64,0,0))                 # PHASER
    key16(); panel.check_display(a,'MONO     '); need(a.data(MOD+3,1) == b'\0','MONO not set')
    key16(); panel.check_display(a,'STEREO   ')
    a.call(0x2059D0,(3,127,0,0))                # TREMOLO
    key16(); panel.check_display(a,'MONO     ')
    key16(); panel.check_display(a,'PAN      ')
    # rt
    panel.button(a,6,True); panel.button(a,6,False)
    need(a.texts[-1].startswith('rt '),'rt page missing: '+a.texts[-1])
    a.call(0x2059D0,(3,0,0,0)); panel.check_display(a,'rt 20000ms'[:9]) if False else None
    for v,ms in ((0,20000),(55,2016),(127,100)):
        a.call(0x2059D0,(3,v,0,0))
        txt = 'rt' + ('%5dms' % ms).rjust(7)
        panel.check_display(a,txt)
        need(get(a,MOD+0x10,'<I')[0] == 85899346//ms,'LIBERO increment wrong')
    key16(); panel.check_display(a,'SYNC     ')
    rts = ['1-16','1-8 ','1-4 ','1-2 ','1-1 ','2-1 ','4-1 ']
    for v in range(128):
        a.call(0x2059D0,(3,v,0,0))
        want = (v*6+63)//127
        need(a.data(MOD+4,1)[0] == want,'Division slider wrong')
        panel.check_display(a,'rt '+rts[want]+'  ')
    key16(); panel.check_display(a,'LIBERO   ')
    # Fo (tremolo) / rS (phaser)
    panel.button(a,6,True); panel.button(a,6,False)
    a.call(0x2059D0,(3,127,0,0)); panel.check_display(a,'Fo 100   ')
    need(a.data(MOD+7,1) == b'\x64','Shape not stored')
    panel.button(a,7,True); panel.button(a,7,False); panel.button(a,7,True); panel.button(a,7,False)
    a.call(0x2059D0,(3,64,0,0))
    for _ in range(2): panel.button(a,6,True); panel.button(a,6,False)
    a.call(0x2059D0,(3,127,0,0)); panel.check_display(a,'rS 100   ')
    need(get(a,MOD+0x40,'<H')[0] == 18000,'Resonance Q15 wrong')
    for t in ['CHORUS','PHASER','TREMOLO','STEREO','PAN','MONO','rt','rS','Fo','ms','PHASE','TREMO',
              '1-16','1-8','1-4','1-2','1-1','2-1','4-1']:
        g = panel.glyphs(a,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    return {'types':3,'rt_sync':7,'rt_free_ms':[20000,2016,100],'keys16':True,'glyphs':True}


def with_types(pat,fx,mod):
    import probability_format as pf
    b = bytearray(pf.set_prb3(pat,[100]*16))
    for i in range(4):
        b[pf.OFFSET+13+i] |= (((fx | (mod << 2)) >> i) & 1) << 7
    struct.pack_into('<H',b,pf.OFFSET+26,pf.prb2_digest(bytes(b[pf.OFFSET:pf.OFFSET+26])))
    return bytes(b)


def verify_pattern_types(original,patched):
    """FX type (steps 13-14) and modulation type (15-16) live together in the
    pattern; every load sets both; patterns without them -> REVRB + CHORUS;
    the pages write their own two bits only."""
    import verify_122 as v
    import probability_format as pf
    a = v.machine(patched)
    bank = lambda n: a.data(a.get32(native.ROOT)+n*1920,1920)
    a.storage.store(3,with_types(bank(3),1,1)); a.storage.store(4,with_types(bank(4),2,2))
    a.storage.store(5,with_types(bank(5),0,2)); a.storage.store(6,with_types(bank(6),2,0))
    sel = []
    for k in (3,4,2,5,6,3):
        v.keys(a,(k,)); sel.append((a.data(FX,1)[0],a.data(MOD,1)[0]))
    need(sel == [(1,1),(2,2),(0,0),(0,2),(2,0),(1,1)],'Selection: '+str(sel))
    # chain
    a.u.mem_write(MOD,b'\0'); a.u.mem_write(FX,b'\0')
    v.setopt(a,cr=1); v.memory_press(a); v.keys(a,(3,),(),(2,),(),(4,)); v.start(a)
    seq = []
    for i in range(64):
        a.call(0x208CF8,(1,0))
        if i % 16 == 2: seq.append((a.data(v.CLOCK+6,1)[0],a.data(FX,1)[0],a.data(MOD,1)[0]))
    need(seq == [(3,1,1),(2,0,0),(4,2,2),(3,1,1)],'Chain: '+str(seq))
    # pages: MOD writes bits 2-3, FX bits 0-1
    b = panel.machine(patched)
    bits = lambda: sum(((b.data(v.PATTERN+pf.OFFSET+13+i,1)[0] >> 7) & 1) << i for i in range(4))
    v.page_to(b,10)
    b.call(0x2059D0,(3,127,0,0)); panel.check_display(b,'TREMOLO  ')
    need(bits() == 8,'MOD page bits: '+str(bits()))
    for _ in range(3): panel.button(b,7,True); panel.button(b,7,False)
    panel.check_display(b,'FX REVRB ')
    b.call(0x2059D0,(3,64,0,0)); panel.check_display(b,'FX DELAY ')
    need(bits() == 9,'FX page bits: '+str(bits()))
    for _ in range(3): panel.button(b,6,True); panel.button(b,6,False)
    b.call(0x2059D0,(3,64,0,0)); panel.check_display(b,'PHASER   ')
    need(bits() == 5 and b.data(FX,1) == b'\1','MOD page changed the FX bits: '+str(bits()))
    return {'selection':sel,'chain':seq,'page_bits':'FX 0-1, MOD 2-3'}


def verify_on_off_and_label(original,patched):
    """FUNC + 3 (chorus on/off) and the chorus level knob drive the phaser and
    the tremolo; the level readout names the active effect."""
    res = {}
    for t,label in ((0,'CHORS 100'),(1,'PHASE 100'),(2,'TREMO 100')):
        a = panel.machine(patched); put(a,MOD,'<B',t)
        a.call(0x2059D0,(0,100,0,0))
        need(a.texts[-1] == label,'Level readout '+repr(a.texts[-1]))
        res[t] = label
    o = panel.machine(original); o.call(0x2059D0,(0,100,0,0))
    need(o.texts[-1] == 'CHORS 100','Original readout changed?')
    for t in (1,2):
        a = mod_machine(patched,t,level=0)
        put(a,CH+0x44,'<i',0x1E00000)
        outs = [call_mod(a,1 << 22,1 << 22) for _ in range(3000)]
        need(any(x != (0,0) for x in outs[-500:]),'On: silent')
        put(a,CH+0x44,'<i',0)            # FUNC + 3 off: target 0
        outs = [call_mod(a,1 << 22,1 << 22) for _ in range(6000)]
        need(outs[-1] == (0,0),'Off: still sounding %s' % (outs[-1],))
        need(max(abs(outs[i+1][0]-outs[i][0]) for i in range(1000,5999)) < 1 << 18 or t == 1,'Off: not smooth')
    return {'labels':res,'func3_fades':True}


TASKS = [('v122/static',verify_static),
         ('v122/mod_model',verify_model),
         ('v122/mod_sound',verify_sound),
         ('v122/chorus_unchanged',verify_chorus_unchanged),
         ('v122/mod_transitions',verify_transitions),
         ('v122/mod_cpu',verify_cpu),
         ('v122/mod_pages',verify_pages),
         ('v122/pattern_types',verify_pattern_types),
         ('v122/on_off_label',verify_on_off_and_label)]


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
            import traceback; traceback.print_exc()
            print(name,'FAIL',e,flush=True); failed += 1
    sys.exit(1 if failed else 0)
