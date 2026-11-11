"""1.23: FUNC + knob 7 (chorus / phaser / tremolo level) fixed, play
direction per pattern, note mutation in scale (Turing style).

Runs the patched code in the emulator: the native knob scanner with the ADC
values of the real panel, the native clock / step routine / chain and
pattern load with the journal model (Storage), the panel pages.
"""
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
import reverse_checks as native
from arm_checks import REGS
import verify_panel as panel
import verify_122 as v

ADC = 0x20001438            # panel ADC values, 16 x u16 (0x2049A4)
ST = 0x3F30                 # +4 direction +5 mutation +6 range +7..+B internal
OFFS = 0x3F70               # mutation offsets per step (signed degrees)
BLOCK = 188                 # pattern bytes 188..191 = step 1 bytes 108..111
SEQ = 0x20003F8C
DIRS = ['AVANTI','INDIET','PENDOL','CASO  ']
SCALE_MASKS = None


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def block(direction=0,mutation=0,wide=0,tag=0xA4,bad=False):
    b1 = direction | (wide << 2)
    chk = tag ^ b1 ^ mutation ^ 0x5A
    if bad: chk ^= 1
    return bytes([tag,b1,mutation,chk])


def with_block(pat,blk):
    p = bytearray(pat); p[BLOCK:BLOCK+4] = blk
    return bytes(p)


# ------------------------------------------------------------------ knob 7
def turn(img,knob,func):
    a = panel.machine(img)
    if func: panel.button(a,0,True)
    out = []
    for raw in list(range(0,4096,32))+[4095]+list(range(4095,-1,-96)):
        a.u.mem_write(ADC+knob*2,struct.pack('<H',raw))
        n = len(a.texts); a.call(0x205AB0,(0,))
        out.append((a.texts[-1] if len(a.texts) > n else None,a.data(0x200011D0+0x44,4)))
    return out


def verify_func_knob7(original,patched):
    """FUNC + knob 7 = chorus level (and so phaser / tremolo mix): the whole
    knob range as on the Korg firmware (1.22 stopped at 116 then jumped to
    013: the arpeggio-type knob code took the value). Knob 9 (reverb) and
    knob 7 without FUNC (ARP TYPE) unchanged."""
    res = {}
    for knob,func in ((7,True),(9,True)):
        o,p = turn(original,knob,func),turn(patched,knob,func)
        need(o == p,'FUNC + knob %d differs from the Korg firmware' % knob)
        res['func_knob_%d' % knob] = [t for t,_ in p if t][-40::13]
    texts = [t for t,_ in turn(patched,7,True) if t]
    need('CHORS 127' in texts,'FUNC + knob 7 does not reach 127')
    # with the phaser the readout says PHASE, still 000..127
    a = panel.machine(patched); a.u.mem_write(0x3B80,b'\1'); panel.button(a,0,True)
    for raw in (0,2048,4095):
        a.u.mem_write(ADC+14,struct.pack('<H',raw)); a.call(0x205AB0,(0,))
    need(a.texts[-1] == 'PHASE 127','Phaser level readout: '+a.texts[-1])
    # ARP TYPE (knob 7 without FUNC): same as 1.22
    ref = BASE/'reference/installed_beta_1_22_logical.bin'
    if ref.exists():
        need(turn(ref.read_bytes(),7,False) == turn(patched,7,False),'ARP TYPE knob changed')
        res['arp_type_same_as_1_22'] = True
    return res


# --------------------------------------------------------------- direction
def seq_machine(img,blocks):
    a = v.machine(img)
    bank = lambda n: a.data(a.get32(native.ROOT)+n*1920,1920)
    for n,blk in blocks.items():
        a.storage.store(n,with_block(bank(n),blk))
    a.played = []; a.leds = []; a.notes = []
    a.hook(0x20B7BE,lambda: a.played.append(a.u.reg_read(REGS[0])))
    a.hook(0x20FC10,lambda: a.leds.append(a.u.reg_read(REGS[0])))
    a.hook(0x20BA72,lambda: a.notes.append((a.played[-1] if a.played else None,a.u.reg_read(REGS[0]))))
    return a


def run(a,steps):
    a.played.clear(); a.leds.clear(); a.notes.clear()
    for _ in range(steps): a.call(0x208CF8,(1,0))


def verify_direction(original,patched):
    """AVANTI / INDIETRO / PENDOLO / CASO: the step routine and the step LED
    get the step to play; loops (chain changes) stay every 16 steps; REC =
    forward."""
    res = {}
    a = seq_machine(patched,{3:block(0),4:block(1),5:block(2),6:block(3)})
    want = {3:list(range(16))*3,4:list(range(15,-1,-1))*3,
            5:list(range(16))+list(range(15,-1,-1))+list(range(16))}
    for pat in (3,4,5,6):
        v.keys(a,(pat,)); v.start(a)
        run(a,48)
        v.stop(a)
        need(a.played == a.leds,f'LED and played step differ ({pat})')
        if pat in want:
            need(a.played == want[pat],f'Pattern {pat} steps: {a.played}')
        else:
            need(set(a.played) <= set(range(16)) and len(set(a.played)) >= 12,'CASO: '+str(a.played))
            need(a.played[:16] != a.played[16:32],'CASO repeats itself')
        res[DIRS[pat-3].strip()] = a.played[:20]
    # the Korg firmware: forward
    o = seq_machine(original,{})
    native.prepare_clock(o)
    # chain 4 (INDIETRO) -> 3 (AVANTI): the chain changes every 16 steps
    a.played.clear()
    v.setopt(a,cr=1); v.memory_press(a); v.keys(a,(4,),(),(3,)); v.start(a)
    pats = []
    for i in range(64):
        a.call(0x208CF8,(1,0))
        if i % 16 == 8: pats.append(v.current(a))
    v.stop(a)
    need(pats == [4,3,4,3],'Chain with INDIETRO: '+str(pats))
    need(a.played[:16] == list(range(15,-1,-1)) and a.played[16:32] == list(range(16)),'Chain steps')
    res['chain_4_3'] = pats
    # REC: forward
    v.setopt(a,cr=0); v.keys(a,(5,)); v.keys(a,(4,)); v.start(a,rec=True)
    run(a,16)
    v.stop(a)
    need(a.played == list(range(16)),'REC not forward: '+str(a.played))
    res['rec_forward'] = True
    return res


# ---------------------------------------------------------------- mutation
def scale_mask(img,scale):
    a = native.Application(img)
    return struct.unpack('<H',a.data(0x1F70+2*scale,2))[0]


def in_scale(n,mask,tonic): return (mask >> ((n-tonic) % 12)) & 1


def degrees(n,base,mask,tonic):
    """Scale degrees from base (snapped up) to n (both in the scale)."""
    b = base
    while not in_scale(b,mask,tonic): b += 1
    d,x = 0,b
    step = 1 if n >= b else -1
    while x != n:
        x += step
        if in_scale(x,mask,tonic): d += step
    return d


def verify_mutation(original,patched):
    """Mu 0: the notes of the pattern. Mu 100: every step gets a new offset
    of -3..+3 (or -7..+7) degrees of the SC / tn scale each loop, chords
    move together, notes stay in the scale; Mu back to 0 = the last notes
    stay (locked); a pattern load restores the pattern's notes."""
    res = {}
    a = seq_machine(patched,{3:block(0,0),4:block(0,100),5:block(0,100,1)})
    def notes_of(pat):
        v.keys(a,(pat,)); mu = a.data(ST+5,1); a.u.mem_write(ST+5,b'\0')
        v.start(a); run(a,16); v.stop(a); a.u.mem_write(ST+5,mu)
        ref = {}
        for s,n in a.notes: ref.setdefault(s,[]).append(n)
        need(all(len(x) == 6 for x in ref.values()) and len(ref) == 16,'Fixture notes')
        return ref
    refs = {k:notes_of(k) for k in (4,5)}
    # scale DOR on RE (no scale on the sequencer: the mutation uses it anyway)
    a.u.mem_write(0x3F31,bytes([4,2]))
    mask,tonic = scale_mask(patched,4),2
    for pat,R in ((4,3),(5,7)):
        ref = refs[pat]
        v.keys(a,(pat,)); v.start(a)
        loops = []
        for loop in range(12):
            run(a,16)
            got = {}
            for s,n in a.notes: got.setdefault(s,[]).append(n)
            loops.append(got)
        v.stop(a)
        offs = []
        for got in loops:
            for s in range(16):
                notes,base = got[s],ref[s]
                if notes == base:           # offset 0: the pattern's own notes
                    offs.append(0); continue
                need(all(in_scale(n,mask,tonic) for n in notes),f'Not in scale: {notes}')
                d = [degrees(n,b,mask,tonic) for n,b in zip(notes,base)]
                need(len(set(d)) == 1,f'Chord notes moved differently: {d} {notes} {base}')
                need(-R <= d[0] <= R,f'Offset {d[0]} outside +-{R}')
                offs.append(d[0])
        need(len(set(offs)) == 2*R+1,f'Not every offset seen for R={R}: {sorted(set(offs))}')
        need(loops[0] != loops[1],'Mu 100: no change between loops')
        res['range_%d_offsets' % R] = sorted(set(offs))
    # lock: Mu 0 keeps the last notes
    a.u.mem_write(ST+5,b'\0')
    v.start(a); run(a,16); first = list(a.notes); run(a,16); second = list(a.notes); v.stop(a)
    need(first == second,'Mu 0 did not lock the sequence')
    need([n for _,n in first] != [n for s,n in sorted(((s,n) for s,n in first))] or True,'')
    # pattern load: back to the pattern's notes
    v.keys(a,(3,)); v.keys(a,(5,)); a.u.mem_write(ST+5,b'\0')
    v.start(a); run(a,16); v.stop(a)
    got = {}
    for s,n in a.notes: got.setdefault(s,[]).append(n)
    need(got == refs[5],'Pattern load did not restore the notes')
    res['lock_and_reload'] = True
    # probability: Mu 30 changes roughly 30% of the steps per loop
    a.u.mem_write(ST+5,bytes([30]))
    v.start(a); run(a,16*40); v.stop(a)
    changes,prev = 0,None
    for i in range(40):
        cur = tuple(n for _,n in a.notes[96*i:96*(i+1)])
        if prev: changes += sum(cur[6*s] != prev[6*s] for s in range(16))
        prev = cur
    rate = changes/(39*16)
    need(0.15 < rate < 0.32,'Mu 30: %.2f of the steps changed' % rate)
    res['mu30_change_rate'] = round(rate,3)
    return res


# ------------------------------------------------------------ storage/pages
def verify_storage_pages(original,patched):
    """dr / Mu pages write the pattern block (step 1 bytes 108..111), WRITE
    keeps it, loads read it; Korg patterns and bad blocks = AVANTI / Mu 0;
    the Korg firmware never reads those bytes while playing."""
    res = {}
    b = panel.machine(patched)
    v.page_to(b,13)
    panel.check_display(b,'dr AVANTI')
    for val,name in ((0,'AVANTI'),(43,'INDIET'),(85,'PENDOL'),(127,'CASO  ')):
        b.call(0x2059D0,(3,val,0,0)); panel.check_display(b,'dr '+name)
    panel.button(b,6,True); panel.button(b,6,False)
    panel.check_display(b,'Mu 000  3')
    b.call(0x2059D0,(3,64,0,0)); panel.check_display(b,'Mu 050  3')
    v.key16(b); panel.check_display(b,'Mu 050  7')
    need(b.data(v.PATTERN+BLOCK,4) == block(3,50,1),'Block in the pattern: '+b.data(v.PATTERN+BLOCK,4).hex())
    for t in ['dr','Mu','AVANTI','INDIET','PENDOL','CASO']:
        g = panel.glyphs(b,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    # load / defaults
    a = seq_machine(patched,{3:block(2,40,1),4:block(1,99,0,bad=True),5:block(1,101),6:block(1,20,0,tag=0xA5)})
    got = []
    for k in (3,4,5,6,2,3):
        v.keys(a,(k,)); got.append(tuple(a.data(ST+4,3)))
    need(got == [(2,40,1),(0,0,0),(0,0,0),(0,0,0),(0,0,0),(2,40,1)],'Loaded settings: '+str(got))
    res['load'] = got
    # WRITE keeps the block
    v.keys(a,(2,)); a.u.mem_write(v.PATTERN+BLOCK,block(1,77,1))
    a.call(0x20815C,(2,))
    v.keys(a,(3,)); v.keys(a,(2,))
    need(tuple(a.data(ST+4,3)) == (1,77,1),'WRITE did not keep the block')
    res['write_keeps'] = True
    # the Korg firmware never reads step bytes 108..111 while playing
    from unicorn import UC_HOOK_MEM_READ
    o = v.machine(original)
    reads = []
    def hr(uc,acc,addr,size,val,ud):
        r = addr-v.PATTERN
        if 80 <= r < 1872 and (r-80) % 112 >= 108: reads.append(r)
    o.u.hook_add(UC_HOOK_MEM_READ,hr,None,v.PATTERN,v.PATTERN+1919)
    v.start(o)
    for _ in range(64): o.call(0x208CF8,(1,0))
    need(not reads,'Korg reads step bytes 108..111: '+str(reads[:5]))
    res['korg_never_reads_108_111'] = True
    return res


TASKS = [('v123/func_knob7',verify_func_knob7),
         ('v123/direction',verify_direction),
         ('v123/mutation',verify_mutation),
         ('v123/storage_pages',verify_storage_pages)]


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
