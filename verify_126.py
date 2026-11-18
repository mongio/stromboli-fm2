"""1.26: a 12 dB state variable filter on every voice (LP / BP / HP), its
envelope, two LFOs (cutoff, resonance, amplitude, crossfade between parts A
and b, rate of LFO1), FUNC + TRANSPOSE / VELOCITY, MIDI CC 74 / 71, pages
FL and LF.

Runs the patched code in the emulator against a model of the filter, sample
by sample, and against the Korg 1.12 voices.
"""
import math
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
import numpy as np
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R8,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R12
import reverse_checks as native
from reverse_checks import audio_machine,render_synth,render_isr,ENGINE
import build_patch
import verify_panel as panel
import verify_122 as v
import verify_125 as m

F = 0x3700
FS = 50000.0


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def s32(x):
    x &= 0xFFFFFFFF
    return x-(1 << 32) if x & 0x80000000 else x


def ssat(x,bits):
    hi = (1 << (bits-1))-1
    return max(-hi-1,min(hi,x))


def sym(name): return build_patch.SRAM_SYMBOLS[name]
def isym(name): return build_patch.ITCM_SYMBOLS[name]


def setf(a,typ=None,cut=None,res=None,amt=None,att=None,dec=None,sus=None,rel=None,kt=None,ve=None,lfo1=None,lfo2=None):
    """Write the global settings and the active bits as the pages do."""
    for off,val in ((0,typ),(1,cut),(2,res),(3,amt),(4,att),(5,dec),(6,sus),(7,rel),(8,kt),(9,ve)):
        if val is not None: a.u.mem_write(F+off,bytes([val]))
    for base,l in ((0x10,lfo1),(0x18,lfo2)):
        if l:
            for i,k in enumerate(('wave','rate','depth','dest','sync','div')):
                if k in l: a.u.mem_write(F+base+i,bytes([l[k]]))
    a.call(sym('filt_flags'))


def vstate(a,i):
    raw = a.data(F+0x40+48*i,48)
    ic1,ic2,a1,a2,a3,k,gain,amp,step,env = struct.unpack('<10i',raw[:40])
    return dict(ic1=ic1,ic2=ic2,a1=a1,a2=a2,a3=a3,k=k,gain=gain,amp=amp,step=step,env=env,stage=raw[0x29],
                note=raw[0x2A],vel=raw[0x2B],gate=raw[0x2C])


def model(r8,st,typ,flags):
    """The audio part of the filter, as filt_voice (ITCM)."""
    out = r8
    ic1,ic2 = st['ic1'],st['ic2']
    if flags & 1:
        g = st['gain'] & 0xFFFF
        g = g-65536 if g & 0x8000 else g
        v0 = (r8*g) >> 16
        v3 = s32(v0-ic2)
        v1 = s32((st['a1']*ic1+st['a2']*v3) >> 30)
        v2 = s32(ic2+s32((st['a2']*ic1+st['a3']*v3) >> 30))
        ic1 = ssat(s32((v1 << 1)-ic1),31)
        ic2 = ssat(s32((v2 << 1)-ic2),31)
        if typ == 1: y = v2
        elif typ == 2: y = v1
        else: y = s32(s32(v0-s32((st['k']*v1) >> 29))-v2)
        out = s32(ssat(y,28) << 1)
    amp = st['amp']
    if flags & 2:
        amp = s32(amp+st['step'])
        out = s32((out*amp) >> 16)
    return out,ic1,ic2,amp


def start(a,notes,vel=100):
    for i,n in enumerate(notes):
        a.call(0x20E814,(i,n << 8,vel,0x40))


def trace(a,count):
    """Render, recording for every voice call: input, the filter state used
    (after a control step), output, gains."""
    rec = []
    cur = {}
    fv = isym('fv_run')
    def h_in(uc,addr,size,ud):
        ip = uc.reg_read(UC_ARM_REG_R12)
        i = a.data(ip+0xD,1)[0]
        cur['i'] = i
        cur['in'] = s32(uc.reg_read(UC_ARM_REG_R8))
        cur['st'] = vstate(a,i)
        cur['typ'] = a.data(F,1)[0]
        cur['flags'] = a.data(F+0xF,1)[0]
    def h_entry(uc,addr,size,ud):
        cur['in0'] = s32(uc.reg_read(UC_ARM_REG_R8))
        cur['ip'] = uc.reg_read(UC_ARM_REG_R12)
        cur.pop('st',None)
    def h_out(uc,addr,size,ud):
        if 'st' not in cur:
            i = a.data(cur['ip']+0xD,1)[0]
            cur.update(i=i,st=vstate(a,i),typ=a.data(F,1)[0],flags=a.data(F+0xF,1)[0],**{'in':cur['in0']})
        rec.append(dict(cur,out=s32(uc.reg_read(UC_ARM_REG_R8)),gl=uc.reg_read(UC_ARM_REG_R2),gr=uc.reg_read(UC_ARM_REG_R3),
                        after=vstate(a,cur['i'])))
    hs = [a.u.hook_add(UC_HOOK_CODE,h_entry,None,0x1266,0x1266),
          a.u.hook_add(UC_HOOK_CODE,h_in,None,fv,fv),
          a.u.hook_add(UC_HOOK_CODE,h_out,None,0x126A,0x126A)]
    raw = render_synth(a,count)
    for h in hs: a.u.hook_del(h)
    return rec,raw


def machine(img):
    a = audio_machine(img)
    a.call(0x208198,(0,1))
    return a


# ----------------------------------------------------------------- off
def verify_off_identical(original,patched):
    """Filter OFF and no LFO on the amplitude (the state at power-on): voices
    and samples identical to the Korg 1.12, also through the audio
    interrupt; LFO depths alone change nothing."""
    res = {}
    for name,kw in (('power_on',{}),('lfo_on_cutoff_only',dict(lfo1=dict(depth=100,dest=0),lfo2=dict(depth=90,dest=1)))):
        o,p = machine(original),machine(patched)
        setf(p,**kw)
        need(p.data(F+0xF,1) == b'\0','Active bits with the filter off: '+str(p.data(F+0xF,1)))
        for mm in (o,p): start(mm,[48,55,60,64,67,72])
        need(render_synth(o,3000) == render_synth(p,3000),name+': sound differs from 1.12')
        need(m.vdata(o,ENGINE,6*624) == m.vdata(p,ENGINE,6*624),name+': voice state differs')
        o2,p2 = machine(original),machine(patched)
        for mm in (o2,p2): start(mm,[60,64])
        need(render_isr(o2,400) == render_isr(p2,400),name+': audio interrupt differs from 1.12')
        res[name] = True
    return res


# ---------------------------------------------------- sample by sample
def verify_model(original,patched):
    """LP, BP, HP with envelope, resonance and LFOs: every output sample of
    every voice equals the model; the voice input is the Korg voice (the
    loop is not disturbed: same input samples and voice state as with the
    filter off); the mix is the sum of the filtered voices."""
    res = {}
    for typ in (1,2,3):
        o = machine(patched); p = machine(patched)
        setf(p,typ=typ,cut=40+typ*10,res=90,amt=63+40,att=10,dec=50,sus=60,rel=30,kt=60,ve=64,
             lfo1=dict(wave=0,rate=100,depth=60,dest=0),lfo2=dict(wave=2,rate=110,depth=80,dest=2))
        for mm in (o,p): start(mm,[36,55,62,79],vel=110)
        ro,_ = trace(o,1500)
        rp,raw = trace(p,1500)
        need([r['in'] for r in ro] == [r['in'] for r in rp],'Voice input changed by the filter')
        need(m.vdata(o,ENGINE,6*624) == m.vdata(p,ENGINE,6*624),'Voice state changed by the filter')
        bad = 0; peak = 0
        for r in rp:
            out,ic1,ic2,amp = model(r['in'],r['st'],r['typ'],r['flags'])
            if (out,ic1,ic2,amp) != (r['out'],r['after']['ic1'],r['after']['ic2'],r['after']['amp']): bad += 1
            peak = max(peak,abs(r['out']))
        need(bad == 0,f'Type {typ}: {bad} samples differ from the model')
        need(peak < 1 << 29,'Output above the limit')
        # mix of the four voices = sum of the Korg gain products
        frames = len(raw)//8
        mix = struct.unpack('<%di' % (frames*2),raw)
        calc = [0]*(frames*2); n = 0
        per = len(rp)//frames
        for f in range(frames):
            for r in rp[f*per:(f+1)*per]:
                calc[2*f] = s32(calc[2*f]+s32((r['out']*s32(r['gl'])) >> 16))
                calc[2*f+1] = s32(calc[2*f+1]+s32((r['out']*s32(r['gr'])) >> 16))
        need(per == 4 and list(mix) == calc,'Mix is not the sum of the filtered voices')
        res[('LP','BP','HP')[typ-1]] = {'samples':len(rp),'peak':peak}
    return res


# ------------------------------------------------------------ response
def verify_response(original,patched):
    """The coefficients are those of the Simper SVF for the cutoff and the
    resonance (g = tan(pi fc / fs), k = 2 - 1.9 res / 127), and the measured
    response of LP, BP, HP (cross spectrum of input and output of a voice)
    follows the analog prototype."""
    res = {}
    for cut in (0,30,64,100,127):
        for rr in (0,64,127):
            a = machine(patched)
            setf(a,typ=1,cut=cut,res=rr,amt=63,kt=0)
            start(a,[60])
            st = vstate(a,0)
            a1,a2,a3 = st['a1']/2**30,st['a2']/2**30,st['a3']/2**30
            g = a2/a1; k = (1/a1-1)/g-g
            n = (128+cut*121//16)/8
            fc = min(440*2**((n-69)/12),0.45*FS)
            gw = math.tan(math.pi*fc/FS); kw = 2-1.9*rr/127
            need(abs(g/gw-1) < 0.012,f'g at cutoff {cut}: {g} vs {gw}')
            need(abs(k-kw) < 0.01+0.002*kw/g if g < 0.05 else abs(k-kw) < 0.01,f'k at {cut},{rr}: {k} vs {kw}')
            need(abs(a3/(g*a2)-1) < 1e-3,'a3 is not g a2')
            need(abs(st['k']/2**29-kw) < 0.002,'k of the high pass')
            res[f'cut{cut}_res{rr}'] = [round(fc,1),round(g,5),round(k,3)]
    # measured response: noise-like FM voice through each type
    meas = {}
    for typ in (1,2,3):
        a = machine(patched)
        a.u.mem_write(0x20004F5C,a.data(0x20027800+5*128,128))
        setf(a,typ=typ,cut=70,res=64,amt=63,kt=0)
        start(a,[40],vel=127)
        rec,_ = trace(a,8192)
        x = np.array([r['in'] for r in rec],float); y = np.array([r['out'] for r in rec],float)
        st = rec[-1]['st']; gain = (st['gain'] & 0xFFFF)/32768
        g = st['a2']/st['a1']; k = (2**30/st['a1']-1)/g-g
        seg = 1024; win = np.hanning(seg); sxx = 0; sxy = 0
        for i in range(0,len(x)-seg,seg//2):
            X = np.fft.rfft(x[i:i+seg]*win); Y = np.fft.rfft(y[i:i+seg]*win)
            sxx = sxx+abs(X)**2; sxy = sxy+np.conj(X)*Y
        f = np.fft.rfftfreq(seg,1/FS)
        h = abs(sxy)/np.maximum(sxx,1e-9)
        w = np.tan(np.pi*f/FS)/g
        den = abs(-w**2+1j*k*w+1)
        ana = {1:1/den,2:k*w/den/k,3:w**2/den}[typ]
        ana = ana*gain
        ok = sxx > sxx.max()*1e-4
        ok &= (f > 100) & (f < 15000)
        err = 20*np.log10(np.maximum(h[ok],1e-9)/np.maximum(ana[ok],1e-9))
        need(np.median(abs(err)) < 1.0 and np.percentile(abs(err),90) < 3.0,
             f'Type {typ}: response off by {np.median(abs(err)):.2f} dB (90%: {np.percentile(abs(err),90):.2f})')
        meas[('LP','BP','HP')[typ-1]] = {'bins':int(ok.sum()),'median_dB':round(float(np.median(abs(err))),3)}
    res['measured'] = meas
    return res


# ------------------------------------------------------------ envelope
def verify_envelope(original,patched):
    """Attack to full in its time, decay to the sustain, release to zero
    after the key-off of the voice; the envelope opens the cutoff by the
    amount, scaled by the velocity; key tracking."""
    res = {}
    a = machine(patched)
    setf(a,typ=1,cut=30,res=0,amt=63+63,att=60,dec=40,sus=64,rel=40,kt=0,ve=0)
    start(a,[60])
    envs = []
    for _ in range(240):
        render_synth(a,32); envs.append(vstate(a,0)['env'])
    t_att = 0.0005*2**(60*14/127)
    top = next(i for i,e in enumerate(envs) if e >= 65535)
    need(abs((top+1)*32/FS/t_att-1) < 0.15,f'Attack time {(top+1)*32/FS} vs {t_att}')
    sus = 64*516
    need(abs(envs[-1]-sus) < 400 and vstate(a,0)['stage'] == 2,f'Sustain {envs[-1]} vs {sus}')
    a.call(0x20E7C8,(0,))
    need(vstate(a,0)['gate'] == 0,'Key-off did not close the gate')
    rel = []
    for _ in range(400):
        render_synth(a,32); rel.append(vstate(a,0)['env'])
        if rel[-1] == 0: break
    t_rel = 0.002*2**(40*12.3/127)
    need(rel[-1] == 0 and vstate(a,0)['stage'] == 3,'Release did not reach zero')
    i60 = next(i for i,e in enumerate(rel) if e < sus/1000)
    need(abs((i60+1)*32/FS/t_rel-1) < 0.2,f'Release time to -60 dB {(i60+1)*32/FS} vs {t_rel}')
    res['attack_s'] = round((top+1)*32/FS,4); res['release_60dB_s'] = round((i60+1)*32/FS,4)
    # amount and velocity: g with the envelope at full / zero
    def g_at(amt,ve,vel,note=60,kt=0):
        b = machine(patched)
        setf(b,typ=1,cut=30,res=0,amt=amt,att=0,dec=127,sus=127,rel=0,kt=kt,ve=ve)
        start(b,[note],vel=vel); render_synth(b,64*6)
        st = vstate(b,0); return st['a2']/st['a1']
    base = g_at(63,0,100)
    up = g_at(63+40,0,100); down = g_at(63-40,0,100)
    semis = lambda g1,g0: 12*math.log2(math.atan(g1)/math.atan(g0))
    need(abs(semis(up,base)-59.9) < 1.0,f'Envelope +40: {semis(up,base)} semitones')
    need(abs(semis(down,base)+44.4) < 1.5,f'Envelope -40 (down to the lowest cutoff): {semis(down,base)} semitones')
    half = g_at(63+40,127,64)
    need(abs(semis(half,base)/semis(up,base)-64/127) < 0.05,'Velocity scaling of the envelope amount')
    kt = g_at(63,0,100,note=72,kt=100)
    need(abs(semis(kt,base)-12) < 0.3,f'Key tracking 100 % over an octave: {semis(kt,base)}')
    res['env_plus40_semitones'] = round(semis(up,base),2); res['key_tracking_octave'] = round(semis(kt,base),2)
    return res


# ---------------------------------------------------------------- LFOs
def verify_lfos(original,patched):
    """Waves, free rate, sync to the tempo, LFO2 on the rate of LFO1,
    tremolo and crossfade between parts A and b."""
    res = {}
    def run(lfo1,lfo2=None,frames=50000//2,notes=(60,)):
        a = machine(patched)
        setf(a,typ=1,cut=64,lfo1=lfo1,lfo2=lfo2 or dict(depth=0))
        start(a,list(notes))
        vals = []
        for _ in range(frames//32):
            render_synth(a,32)
            vals.append(struct.unpack('<ii',a.data(F+0x24,8)))
        return a,vals
    rates = {}
    for rate in (40,90,127):
        _,vals = run(dict(wave=2,rate=rate,depth=10,dest=0,sync=0),frames=50000)
        saw = [x for x,_ in vals]
        wraps = [i for i in range(1,len(saw)) if saw[i] < saw[i-1]-30000]
        f = 0.05*600**(rate/127)
        if len(wraps) >= 2:
            per = (wraps[-1]-wraps[0])/(len(wraps)-1)*32/FS
            need(abs(per*f-1) < 0.03,f'Rate {rate}: period {per} vs {1/f}')
            rates[rate] = round(1/per,3)
    res['rates_hz'] = rates
    # waves at one rate: shapes
    shapes = {}
    for wave,name in enumerate(('SIN','TRI','SAu','SAd','SQR','S-H')):
        _,vals = run(dict(wave=wave,rate=110,depth=10,dest=0),frames=20000)
        x = np.array([a for a,_ in vals],float)
        need(name == 'S-H' or (x.max() > 25000 and x.min() < -25000),f'{name}: range {x.min()} {x.max()}')
        if name == 'SQR': need(set(np.unique(x)) <= {32767,-32767},'SQR values')
        if name == 'S-H': need(len(np.unique(x)) > 3,'S&H does not change')
        shapes[name] = [int(x.min()),int(x.max())]
    res['waves'] = shapes
    # sync: phase from the sixteenths and the measured tempo
    a = machine(patched)
    setf(a,typ=1,cut=64,lfo1=dict(wave=2,depth=10,dest=0,sync=1,div=2))
    start(a,[60])
    a.u.mem_write(0x3F80+0x10,struct.pack('<I',6000))
    got = []
    for s16 in range(0,12):
        a.u.mem_write(0x3B80+0x3C,struct.pack('<I',s16))
        a.u.mem_write(0x3F80+0xC,struct.pack('<I',1000))
        a.u.mem_write(0x3F80+8,struct.pack('<I',1000+3000))
        render_synth(a,32)
        got.append(struct.unpack('<I',a.data(F+0x20,4))[0])
    want = [round(((s16 % 4)*6000+3000)*(0xFFFFFFFF//(6000*4))) & 0xFFFFFFFF for s16 in range(12)]
    need(all(abs(g-w) < 1 << 12 for g,w in zip(got,want)),'Synced phase: '+str([hex(g) for g in got[:5]]))
    res['sync_4_sixteenths'] = True
    # LFO2 on the rate of LFO1
    a,vals = run(dict(wave=2,rate=60,depth=10,dest=0),dict(wave=4,rate=70,depth=127,dest=4),frames=50000)
    saw = [x for x,_ in vals]; sq = [y for _,y in vals]
    steps = [(saw[i]-saw[i-1]) % 65536 for i in range(1,len(saw))]
    hi = np.median([s for s,q in zip(steps,sq[1:]) if q > 0]); lo = np.median([s for s,q in zip(steps,sq[1:]) if q < 0])
    need(hi/lo > 50,f'LFO2 on the rate of LFO1: {hi} / {lo}')
    res['lfo2_rate_ratio'] = round(float(hi/lo),1)
    # tremolo: amplitude follows 1 - depth (1 - (v + 1) / 2)
    a = machine(patched)
    setf(a,typ=0,lfo1=dict(wave=4,rate=90,depth=127,dest=2))
    need(a.data(F+0xF,1) == b'\2','Tremolo alone is not the amplitude bit')
    start(a,[60]); amps = []
    for _ in range(400):
        render_synth(a,32); amps.append((vstate(a,0)['amp'],struct.unpack('<i',a.data(F+0x24,4))[0]))
    lo = min(x for x,_ in amps[20:]); hi = max(x for x,_ in amps[20:])
    need(hi > 64000 and lo < 1200,f'Tremolo range {lo} {hi}')
    res['tremolo_range'] = [lo,hi]
    # crossfade between A and b (layer): sum of power about constant
    a = machine(patched)
    m.parts(a,B=dict(prog=6))
    setf(a,typ=0,lfo1=dict(wave=1,rate=40,depth=127,dest=3))
    a.call(0x209574,(0x40,60,100))
    pts = []
    for _ in range(600):
        render_synth(a,32)
        x = struct.unpack('<i',a.data(F+0x24,4))[0]
        ga,gb = vstate(a,0)['amp']+32*vstate(a,0)['step'],vstate(a,1)['amp']+32*vstate(a,1)['step']
        pts.append((x,ga,gb))
    need({m.part_of(a,0),m.part_of(a,1)} == {0,1},'Layer parts')
    pa = 0 if m.part_of(a,0) == 0 else 1
    for x,ga,gb in pts[10:]:
        gA,gB = (ga,gb) if pa == 0 else (gb,ga)
        xx = min(65535,max(0,32768+x*127//127))
        need(abs(gA/65536-(1-(xx/65536)**2)) < 0.02 and abs(gB/65536-(xx/65536)*(2-xx/65536)) < 0.02,
             f'Crossfade gains at {x}: {gA} {gB}')
        pw = (gA/65536)**2+(gB/65536)**2
        need(0.99 <= pw <= 1.14,f'Crossfade power {pw}')
    res['crossfade'] = True
    return res


# --------------------------------------------- knobs, MIDI, pages, CPU
def verify_controls(original,patched):
    """FUNC + TRANSPOSE = cutoff, FUNC + VELOCITY = resonance (transpose and
    velocity unchanged, the filter turns on as LP); without FUNC the knobs
    are those of Korg; MIDI CC 74 / 71 on the channel of the volca."""
    res = {}
    a = panel.machine(patched)
    func = [1]
    a.hook(0x20FA60,lambda: a.return_(func[0]))
    tr = lambda: a.get32(0x20002A08+4*1+0xC)
    vl = lambda: a.get32(0x20002A08+4*3+0xC)
    t0,v0 = tr(),vl()
    a.call(0x2059D0,(1,100,0,0))
    need(a.data(F,3) == bytes([1,100,20]) and a.data(F+0xF,1) == b'\1','FUNC + TRANSPOSE: '+a.data(F,3).hex())
    panel.check_display(a,'CUTOF 100')
    a.call(0x2059D0,(3,33,0,0))
    need(a.data(F+2,1) == b'\x21','FUNC + VELOCITY'); panel.check_display(a,'RESO  033')
    need(tr() == t0 and vl() == v0,'Transpose or velocity changed with FUNC')
    func[0] = 0
    a.call(0x2059D0,(1,90,0,0)); a.call(0x2059D0,(3,70,0,0))
    need(a.data(F,3) == bytes([1,100,33]),'Knobs without FUNC changed the filter')
    o = panel.machine(original); o.hook(0x20FA60,lambda: o.return_(0))
    o.call(0x2059D0,(1,90,0,0)); o.call(0x2059D0,(3,70,0,0))
    need((tr(),vl()) == (o.get32(0x20002A08+4+0xC),o.get32(0x20002A08+12+0xC)),'Knobs without FUNC differ from Korg')
    func[0] = 1
    for k in (7,9):
        b = panel.machine(patched); c = panel.machine(original)
        for x in (b,c): x.hook(0x20FA60,lambda x=x: x.return_(1)); x.call(0x2059D0,(k,50,0,0))
        need(b.texts[-1:] == c.texts[-1:],f'FUNC + knob {k} is no longer Korg')
    res['func_knobs'] = True
    # MIDI CC 74 / 71
    mm = m.midi_machine(patched)
    m.send(mm,0xB0,74,12); m.send(mm,0xB0,71,99)
    need(mm.data(F,3) == bytes([1,12,99]),'CC 74 / 71: '+mm.data(F,3).hex())
    m.send(mm,0xB5,74,90)
    need(mm.data(F+1,1) == bytes([12]),'CC 74 on another channel')
    mm2 = m.midi_machine(patched,B=dict(prog=6),chan=1); m.send(mm2,0xB1,74,77)
    need(mm2.data(F+1,1) == bytes([77]),'CC 74 on the channel of part b')
    res['midi_cc'] = True
    return res


def verify_pages(original,patched):
    """1.29: the pages FL and LF left FUNC + EDIT (filter and LFOs are in the
    EDIT of the program): after PC comes P again, before P comes PC."""
    a = panel.machine(patched)
    v.page_to(a,20)
    need(a.texts[-1].startswith('C'),'Page 20 is not PC: '+a.texts[-1])
    panel.button(a,6,True); panel.button(a,6,False)
    need(a.texts[-1][3:4] == 'P','PC is not followed by P: '+a.texts[-1])
    panel.button(a,7,True); panel.button(a,7,False)
    need(a.texts[-1].startswith('C'),'P is not preceded by PC: '+a.texts[-1])
    for t in ['CUTOF','RESO']:
        g = panel.glyphs(a,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    return {'pages':'... CR PA Pb PC P'}


def verify_cpu(original,patched):
    """Instructions of the whole audio interrupt per 50 kHz frame, six voices,
    chorus and reverb on (as in the earlier versions): Korg 1.12, filter
    off, LP with envelope, LP + two LFOs (cutoff and amplitude); the most in
    one frame includes a control step (one voice per frame)."""
    import verify_118 as v118
    res = {}
    def run(img,kw):
        a = audio_machine(img)
        a.count = [0,False]
        def cb(*x):
            if a.count[1]: a.count[0] += 1
        a.u.hook_add(UC_HOOK_CODE,cb)
        a.call(0x20EA84,(127,)); a.call(0x20453C,(1,))
        a.call(0x20EA70,(100,)); a.call(0x2045F4,(1,))
        a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
        if kw: setf(a,**kw)
        for i in range(6): a.call(0x20E814,(i,(48+7*i) << 8,127,0x40))
        render_isr(a,600)
        c = v118.count_isr(a,320)
        return {'max':max(c),'mean':round(sum(c)/len(c),1)}
    full = dict(typ=1,cut=60,res=90,amt=100,att=20,dec=60,sus=80,rel=40,kt=50,ve=60,
                lfo1=dict(wave=0,rate=100,depth=60,dest=0),lfo2=dict(wave=1,rate=60,depth=80,dest=2))
    res['korg_1_12'] = run(original,None)
    b124 = BASE/'reference/installed_beta_1_24_logical.bin'
    # the 1.24 image is optional (Korg firmware, not in the repository):
    # without it the reference is the 1.12 count + 36 (the 1.24 effects
    # wrappers, measured with it)
    res['stromboli_1_24'] = run(b124.read_bytes(),None) if b124.exists() else {'max':res['korg_1_12']['max']+36,'estimated':True}
    res['filter_off'] = run(patched,None)
    res['lp_envelope'] = run(patched,dict(typ=1,cut=60,res=90,amt=100))
    res['lp_two_lfos_amplitude'] = run(patched,full)
    ref = res['korg_1_12']
    need(ref['mean'] > 2000,'The six voices are not sounding in the count')
    need(res['filter_off']['max'] <= res['stromboli_1_24']['max']+48,'Filter off costs more than 1.24 + 48 (8 per voice): '+str(res['filter_off']))
    worst = res['lp_two_lfos_amplitude']
    res['extra_mean'] = round(worst['mean']-ref['mean'],1)
    res['extra_max'] = worst['max']-ref['max']
    res['extra_mean_pct'] = round(100*(worst['mean']-ref['mean'])/ref['mean'],1)
    need(worst['max'] < 3600,'Peak above 3600 instructions per frame (4311 cycles at 216 MHz)')
    return res


TASKS = [('v126/off_identical',verify_off_identical),
         ('v126/model',verify_model),
         ('v126/response',verify_response),
         ('v126/envelope',verify_envelope),
         ('v126/lfos',verify_lfos),
         ('v126/controls',verify_controls),
         ('v126/pages',verify_pages),
         ('v126/cpu',verify_cpu)]


if __name__ == '__main__':
    import json,time
    original,patched,code,manifest,header = build_patch.build()
    only = sys.argv[1:]
    for name,fn in TASKS:
        if only and not any(o in name for o in only): continue
        t = time.monotonic()
        try:
            r = fn(original,patched)
            print(name+': PASS (%.1fs) ' % (time.monotonic()-t)+json.dumps(r,default=str)[:400],flush=True)
        except Exception as e:
            import traceback
            print(name+': FAIL '+type(e).__name__+': '+str(e)[:600],flush=True)
            if '-v' in sys.argv: traceback.print_exc()
