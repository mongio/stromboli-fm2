"""1.24: ratchet, microtiming and swing per pattern, LOFI with hiss and
self-oscillation, page order (modulation before the effect).

Runs the patched code in the emulator with real clock ticks (72 per
sixteenth, as the internal clock calls 0x00208CF8), the native step routine,
voices (note-on 0x0020AC54, note-off 0x0020B774), journal and panel.
"""
import collections
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
from arm_checks import REGS
import verify_panel as panel
import verify_122 as v
import verify_123 as v123
import verify_118 as v118
from reverse_checks import audio_machine,render_isr

SQ = 0x3980                 # ratchet x16, microtiming x16, swing
REC0 = 300                  # pattern byte of the record (step 2, byte 108)


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def rat(n,prob=100,shape=0):
    return (n-1) | ({100:0,75:1,50:2,25:3}[prob] << 2) | (shape << 4)


def run(img,setup=None,steps=16,pat=3,sel=True):
    a = v123.seq_machine(img,{})
    if sel: v.keys(a,(pat,))
    if setup: setup(a)
    v.start(a)
    on,off,T = [],[],[0]
    a.hook(0x20AC54,lambda: on.append((T[0],a.u.reg_read(REGS[0]),a.u.reg_read(REGS[1]))))
    a.hook(0x20B774,lambda: off.append((T[0],a.u.reg_read(REGS[0]))))
    for i in range(72*steps):
        T[0] = i; a.call(0x208CF8,(0,0))
    v.stop(a)
    a.on,a.off = on,off
    return a


def times(a): return sorted(set(t for t,_,_ in a.on))


def put(a,addr,data): a.u.mem_write(addr,bytes(data))


# ------------------------------------------------------------- regression
def verify_ticks_unchanged(original,patched):
    """All off: note-on / note-off of every tick identical to the Korg 1.12
    (two loops, 6-note chords, real clock ticks), also with REC."""
    res = {}
    for name,setup in (('play',None),('rec',lambda a: a.call(v.REC_ON,(v.SEQ,)))):
        o,p = run(original,setup,32),run(patched,setup,32)
        need(o.on == p.on and o.off == p.off,'Tick timeline differs from 1.12 ('+name+')')
        res[name] = {'note_on':len(p.on),'note_off':len(p.off)}
    return res


# ---------------------------------------------------------------- ratchet
def verify_ratchet(original,patched):
    """2, 3, 4 hits at 36 / 24 / 18 ticks, gates shorter than the gap, the
    shapes PARI / CALA / CRESCE on the velocity, probability 25..100, no
    hits when the step does not play (probability 0)."""
    res = {}
    for n,shape in ((2,0),(3,1),(4,2)):
        a = run(patched,lambda a,n=n,shape=shape: put(a,SQ+4,[rat(n,100,shape)]),16)
        step4 = [e for e in a.on if 4*72+71 <= e[0] < 5*72+71]
        hits = sorted(set(t for t,_,_ in step4))
        gap = 72//n
        need(hits == [4*72+71+k*gap for k in range(n)],f'{n} hits at {hits}')
        vel = [sorted(vv for t,_,vv in step4 if t == h) for h in hits]
        base = vel[0] if shape != 2 else None
        ref = run(patched,None,16)
        v0 = sorted(vv for t,_,vv in ref.on if t == 4*72+71)
        want = {0:[v0]*n,1:[[max(1,x*(n-k)//n) for x in v0] for k in range(n)],
                2:[[max(1,x*(k+1)//n) for x in v0] for k in range(n)]}[shape]
        need(vel == [sorted(w) for w in want],f'Velocities {vel} vs {want}')
        # every hit's notes are released before the next hit
        offs = sorted(t for t,_ in a.off if 4*72+71 <= t < 5*72+71)
        need(len(offs) >= 6*(n-1),f'Notes not released between hits: {offs}')
        res[f'{n}_hits'] = hits
    # probability
    for prob in (25,50,75):
        a = run(patched,lambda a,prob=prob: put(a,SQ,[rat(2,prob)]*16),16*20)
        per = collections.Counter(t//72 for t,_,_ in a.on)
        ratio = sum(per[k] == 12 for k in per)/len(per)
        need(abs(ratio-prob/100) < 0.1,f'Probability {prob}: {ratio:.2f}')
        res[f'prob_{prob}'] = round(ratio,2)
    # a step that does not play has no hits (pattern probability 0 on step 5)
    def setup(a):
        put(a,SQ+4,[rat(4)])
        import probability_format as pf
        pat = bytearray(a.data(v.PATTERN,1920))
        probs = [100]*16; probs[4] = 0
        pat = pf.set_prb3(bytes(pat),probs)
        a.u.mem_write(v.PATTERN,pat)
    a = run(patched,setup,16)
    need(not [e for e in a.on if 4*72+71 <= e[0] < 5*72+71],'Hits on a step that does not play')
    res['no_hits_when_muted'] = True
    return res


# ------------------------------------------------------------- microtiming
def verify_microtiming(original,patched):
    """Late / early steps by ticks, swing on the 2nd, 4th ... sixteenth
    (75 % = 36 ticks), the first step of a loop never early, chains still
    change on the bar, ratchet after a late or early step."""
    res = {}
    def setup(a):
        put(a,SQ+0x10+2,struct.pack('b',20))
        put(a,SQ+0x10+6,struct.pack('b',-30))
        put(a,SQ+0x10+0,struct.pack('b',-10))      # step 1: not early
        put(a,SQ+0x10+9,struct.pack('b',36))
    a = run(patched,setup,16)
    want = [k*72+71 for k in range(16)]
    want[2] += 20; want[6] -= 30; want[9] += 36
    need(times(a) == sorted(t for t in want if t < 72*16),f'Steps at {times(a)}')
    res['late_early'] = {'step3':want[2],'step7':want[6],'step10':want[9]}
    for sw,ticks in ((0,0),(8,12),(25,36)):
        a = run(patched,lambda a,sw=sw: put(a,SQ+0x20,[sw]),16)
        want = [t for t in (k*72+71+(ticks if k % 2 else 0) for k in range(16)) if t < 72*16]
        need(times(a) == want,f'Swing {sw}: {times(a)}')
        res[f'swing_{50+sw}'] = ticks
    # ratchet on a late and on an early step
    def setup2(a):
        put(a,SQ+5,[rat(2)]); put(a,SQ+0x10+5,struct.pack('b',24))     # (72-24)/2 = 24
        put(a,SQ+8,[rat(4)]); put(a,SQ+0x10+8,struct.pack('b',-12))    # 72/4 = 18
    a = run(patched,setup2,16)
    t = times(a)
    need({5*72+71+24,5*72+71+48}.issubset(t),'Ratchet after a late step: '+str(t))
    need({8*72+59,8*72+77,8*72+95,8*72+113}.issubset(t),'Ratchet after an early step: '+str(t))
    res['ratchet_late_early'] = True
    # chain with early steps: patterns still change on the bar
    a = v123.seq_machine(patched,{})
    v.setopt(a,cr=1); v.memory_press(a); v.keys(a,(3,),(),(4,))
    put(a,SQ+0x10,struct.pack('16b',*([-20]*16)))
    v.start(a)
    pats = []
    for i in range(72*64):
        a.call(0x208CF8,(0,0))
        if i % (72*16) == 72*8: pats.append(v.current(a))
    v.stop(a)
    need(pats == [3,4,3,4],'Chain with early steps: '+str(pats))
    res['chain'] = pats
    return res


# ---------------------------------------------------------- storage, pages
def verify_storage_pages(original,patched):
    """rA / ti pages: readouts, shapes on the selected step key, swing on
    the ti step key, record in the pattern (WRITE, load, invalid = off),
    page order: modulation before the effect."""
    res = {}
    b = panel.machine(patched)
    order = []
    panel.enter(b)
    for _ in range(18):
        order.append(b.texts[-1][:2]); panel.button(b,6,True); panel.button(b,6,False)
    need(order == ['01','01','GL','HU','OC','SC','tn','CH','rt','rS','FX','dt','Fb','dr','Mu','01','01','CR'],
         'Page order: '+str(order))
    res['order'] = 'P C GL HU OC SC tn MOD rt rS FX dt Fb dr Mu rA ti CR'
    for _ in range(15): panel.button(b,6,True); panel.button(b,6,False)
    panel.check_display(b,'01 r1    ')
    panel.select(b,4); panel.check_display(b,'05 r1    ')
    seen = []
    for val in range(128):
        b.call(0x2059D0,(3,val,0,0))
        seen.append(b.texts[-1])
    need(seen[0] == '05 r1    ' and seen[127] == '05 r4   P' and '05 r2 25P' in seen and '05 r3 50P' in seen,
         'rA readouts: '+str(sorted(set(seen))))
    need(len(set(seen)) == 13,'13 rA positions expected')
    need(b.data(SQ+4,1)[0] == rat(4),'rA value')
    for want,msg in ((1,'CALA     '),(2,'CRESCE   '),(0,'PARI     ')):
        v.key16(b) if False else None
        panel.select(b,4); panel.check_display(b,msg)
        need(b.data(SQ+4,1)[0] >> 4 == want,'Shape not stored')
    panel.select(b,4); b.call(0x2059D0,(3,127,0,0)); panel.check_display(b,'05 r4   C')
    panel.button(b,6,True); panel.button(b,6,False)
    panel.check_display(b,'05 ti 00 ')
    b.call(0x2059D0,(3,0,0,0)); panel.check_display(b,'05 ti-36 ')
    b.call(0x2059D0,(3,127,0,0)); panel.check_display(b,'05 ti 36 ')
    panel.select(b,4); panel.check_display(b,'SWING 50 ')
    b.call(0x2059D0,(3,127,0,0)); panel.check_display(b,'SWING 75 ')
    panel.select(b,2); panel.check_display(b,'03 ti 00 ')
    rec = b.data(v.PATTERN+REC0,4)
    need(rec[0] == 0xA5 and rec[1] == 25,'Record tag / swing: '+rec.hex())
    for t in ['r1','r4','ti','SWING','PARI','CALA','CRESCE','P','C','S','-']:
        g = panel.glyphs(b,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    # load / WRITE / invalid
    a = v123.seq_machine(patched,{})
    v.keys(a,(2,))
    a.u.mem_write(SQ,bytes([rat(3,50,2)]+[0]*15)+struct.pack('16b',*([5]+[0]*15))+bytes([10]))
    b2 = panel.machine(patched)
    import verify_123
    # write the record as the pages do
    a.call(0x20FC18,(0,))
    from build_patch import SRAM_SYMBOLS
    a.call(SRAM_SYMBOLS['save_seq2']|1,())
    a.call(0x20815C,(2,))
    v.keys(a,(3,)); need(a.data(SQ,0x21) == bytes(0x21),'Pattern 3 should be off')
    v.keys(a,(2,)); need(a.data(SQ,1)[0] == rat(3,50,2) and a.data(SQ+0x10,1) == b'\5' and a.data(SQ+0x20,1) == b'\x0a',
                         'WRITE + load lost the record')
    a.u.mem_write(v.PATTERN+REC0+2,b"\x77")         # corrupt (ratchet of step 1)
    a.call(0x20815C,(2,)); v.keys(a,(3,)); v.keys(a,(2,))
    need(a.data(SQ,0x21) == bytes(0x21),'Invalid record not ignored')
    res['record'] = 'saved / loaded / invalid ignored'
    return res


# ------------------------------------------------------------------- LOFI
def verify_lofi(original,patched):
    """LOFI: hiss in the loop (silence in, noise out, more with feedback),
    feedback up to 120 = self-oscillation that keeps going and stays
    bounded; DELAY keeps 100 as its maximum."""
    res = {}
    def tail(typ,fb,burst=True,frames=200000):
        a = audio_machine(patched)
        v118.setfx(a,typ,0,0,0,40,fb,None)
        sig = [(1 << 27) if (burst and i < 2000 and (i//50) % 2) else 0 for i in range(frames)]
        out = []
        for i,x in enumerate(sig):
            l,r = v118.frame(a,x)
            out.append(abs(l)+abs(r))
        return out
    q = tail(2,60,False,60000)
    need(max(q[20000:]) > 0,'No hiss with LOFI and feedback 60')
    res['hiss_peak_fb60'] = max(q[20000:])
    o = tail(2,120,True)
    blocks = [max(o[i:i+20000]) for i in range(0,len(o),20000)]
    need(blocks[-1] > blocks[1]//4 and blocks[-1] > 0,'Fb 120: no self-oscillation '+str(blocks))
    need(max(o) <= (32767 << 13),'Fb 120: not bounded')
    res['fb120_blocks'] = blocks
    d = tail(1,120,True,120000)
    db = [max(d[i:i+20000]) for i in range(0,len(d),20000)]
    need(db[-1] < db[1],'DELAY with Fb byte 120 should still decay (max 100): '+str(db))
    # Fb page: 120 with LOFI, 100 with DELAY
    b = panel.machine(patched)
    v.page_to(b,10); b.call(0x2059D0,(3,127,0,0))           # FX LOFI
    panel.button(b,6,True); panel.button(b,6,False); panel.button(b,6,True); panel.button(b,6,False)
    b.call(0x2059D0,(3,127,0,0)); panel.check_display(b,'Fb 120 MO')
    panel.button(b,7,True); panel.button(b,7,False); panel.button(b,7,True); panel.button(b,7,False)
    b.call(0x2059D0,(3,64,0,0))                               # DELAY
    panel.button(b,6,True); panel.button(b,6,False); panel.button(b,6,True); panel.button(b,6,False)
    b.call(0x2059D0,(3,127,0,0)); panel.check_display(b,'Fb 100 MO')
    res['fb_max'] = {'LOFI':120,'DELAY':100}
    return res


TASKS = [('v124/ticks_unchanged',verify_ticks_unchanged),
         ('v124/ratchet',verify_ratchet),
         ('v124/microtiming',verify_microtiming),
         ('v124/storage_pages',verify_storage_pages),
         ('v124/lofi',verify_lofi)]


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
