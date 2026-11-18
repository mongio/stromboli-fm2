"""1.27: FM with waveforms. Every operator chooses one of eight waves (bits 7
of bytes 11, 12, 13 of its block in the program, ignored by Korg and always
0 in DX7 data): wave 1 is the Korg sine, waves 2..8 are windows of four
quarter periods in a chain of twelve quarters built in RAM at the first use.

Checks in the emulator:
  off_identical  programs without waves: voices and samples identical to the
                 Korg 1.12, all 32 algorithms, poly, through the interrupt
  tables         the chain, entry by entry, against a model built from the
                 Korg sine table
  oracle         a program with every operator on wave w sounds exactly as the
                 Korg 1.12 with its sine table replaced by the window of w
  operators      operator record i reads the wave of block i; mixed waves
  storage        save in the bank, program change, Korg program SysEx: the
                 waves stay; DX7 voice import clears them
  (1.28: the wave is chosen in the Korg EDIT, see verify_128.py)
  cpu            same instructions per frame as 1.26 (the patched load is
                 the same instruction), table built once
"""
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
from unicorn import UC_HOOK_CODE
import reverse_checks as native
from reverse_checks import audio_machine,render_synth,render_isr,ENGINE
from arm_checks import REGS
import build_patch
import verify_panel as panel
import verify_122 as v

WV = 0x3880
CHAIN = 0x20035B00
SINE = 0x20006810
LIVE = 0x20004F5C
STORED = 0x2000524C
BANK = 0x20027800
CHAIN_TYPES = [3,0,3,0,1,2,0,4,4,0,0,5]
START = [None,3,2,0,1,8,6,4]
NAMES = ['SIN','HAL','3-4','PUL','ALt','dbL','dbA','HAb']


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def sym(name): return build_patch.SRAM_SYMBOLS[name]


def korg_sine(a):
    return struct.unpack('<2048i',a.data(SINE,0x2000))[0::2]


def chain_model(sine):
    vals = []
    for t in CHAIN_TYPES:
        for j in range(256):
            vals.append([0,sine[j],sine[256+j],sine[512+j],sine[2*j],-sine[2*j]][t])
    out = []
    for p,x in enumerate(vals):
        nxt = vals[p+1] if p+1 < len(vals) else 0
        out += [x,(nxt-x) & 0xFFFFFFFF]
    return [x & 0xFFFFFFFF for x in out]


def window(model,w):
    """1024 entries (value, slope) of wave w as the chain holds them."""
    s = START[w]*256*2
    return struct.pack('<2048I',*model[s:s+2048])


def set_waves(prog,waves):
    """waves[i] = wave 0..7 of block i (block 0 = OP6)."""
    p = bytearray(prog)
    for b,w in enumerate(waves):
        for k in range(3):
            p[b*17+11+k] = (p[b*17+11+k] & 0x7F) | (((w >> k) & 1) << 7)
    return bytes(p)


def waves_of(prog):
    return [sum(((prog[b*17+11+k] >> 7) & 1) << k for k in range(3)) for b in range(6)]


def machine(img,prog=None):
    a = audio_machine(img)
    a.call(0x208198,(0,1))          # POLY
    if prog is not None: a.u.mem_write(LIVE,prog)
    return a


def with_algorithm(prog,alg,lfo_wave=0):
    p = bytearray(prog)
    p[110] = (p[110] & 0xE0) | alg
    p[116] = (p[116] & 0xF1) | (lfo_wave << 1)
    return bytes(p)


def pointers(a,voice):
    return [a.get32(ENGINE+voice*624+0x90+i*0x50+0x14) for i in range(6)]


# ----------------------------------------------------------------- off
def verify_off_identical(original,patched):
    """No waves: the voices are the Korg ones (operator pointers on the Korg
    sine), sample by sample, every algorithm, also through the interrupt."""
    shas = []
    base = machine(original).data(LIVE,128)
    for alg in range(32):
        outs = []
        for img in (original,patched):
            a = machine(img,with_algorithm(base,alg,4))
            a.call(0x20E864,(0,60,100)); a.call(0x20E864,(1,67,80))
            outs.append(render_synth(a,1500))
            if img is patched:
                need(pointers(a,0) == [SINE]*6 and pointers(a,1) == [SINE]*6,'Sine pointers')
                need(a.data(WV+4,1) == b'\0','Chain built without waves')
        need(outs[0] == outs[1],f'Algorithm {alg+1} differs from Korg 1.12')
        shas.append(native.digest(outs[1])[:8])
    outs = []
    for img in (original,patched):
        a = machine(img)
        a.call(0x20EA84,(100,)); a.call(0x20453C,(1,)); a.call(0x20EA70,(100,)); a.call(0x2045F4,(1,))
        a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
        for i,n in enumerate((48,55,60,64,67,72)): a.call(0x20E814,(i,n << 8,110,0x40))
        outs.append(render_isr(a,4000,service_every=64))
    need(outs[0] == outs[1],'Interrupt output differs from Korg 1.12')
    return {'algorithms':32,'first_digests':shas[:4],'interrupt_six_voices':True}


# --------------------------------------------------------------- tables
def verify_tables(original,patched):
    a = machine(patched)
    need(a.data(WV+4,1) == b'\0','Chain marked built at power-on')
    a.call(sym('wave_build'))
    need(a.data(WV+4,1) == b'\1','Chain not marked built')
    model = chain_model(korg_sine(a))
    got = list(struct.unpack('<6144I',a.data(CHAIN,6144*4)))
    bad = [i for i,(x,y) in enumerate(zip(got,model)) if x != y]
    need(not bad,'Chain differs from the model at entry %s' % bad[:3])
    need(CHAIN+6144*4 <= 0x2003C000,'Chain reaches the SysEx scratch')
    peak = max(abs(x) for x in struct.unpack('<6144i',a.data(CHAIN,6144*4))[0::2])
    need(peak == 1 << 24,'Peak %d' % peak)
    # a second call does not rebuild (one pass per power-on)
    a.u.mem_write(CHAIN,b'\x11\x22\x33\x44')
    a.call(sym('wave_build'))
    need(a.data(CHAIN,4) == b'\x11\x22\x33\x44','Chain rebuilt')
    shapes = {}
    for w in range(1,8):
        vals = struct.unpack('<2048i',window(model,w))[0::2]
        shapes[NAMES[w]] = [round(vals[i]/(1 << 24),2) for i in range(0,1024,128)]
    return {'entries':3072,'bytes':24576,'range':'0x20035B00..0x2003BB00','shapes_every_eighth':shapes}


# --------------------------------------------------------------- oracle
def verify_oracle(original,patched):
    """All six operators on wave w == Korg 1.12 with the window of w in place
    of its sine table (LFO not on the sine: it reads the same table)."""
    a = machine(patched)
    model = chain_model(korg_sine(a))
    base = a.data(LIVE,128)
    res = {}
    for w in range(1,8):
        for alg in (0,4,6,15,31):
            p = with_algorithm(base,alg,0)
            outs = []
            o = machine(original,p)
            o.u.mem_write(SINE,window(model,w))
            o.call(0x20E864,(0,57,110)); o.call(0x20E864,(1,64,70))
            outs.append(render_synth(o,1500))
            b = machine(patched,set_waves(p,[w]*6))
            b.call(0x20E864,(0,57,110)); b.call(0x20E864,(1,64,70))
            outs.append(render_synth(b,1500))
            need(pointers(b,0) == [CHAIN+START[w]*2048]*6,'Pointers of wave %d' % (w+1))
            need(outs[0] == outs[1],f'Wave {w+1} algorithm {alg+1} differs from the oracle')
            need(any(outs[1][i:i+4] != b'\0'*4 for i in range(0,len(outs[1]),4)),'Silence')
        ref = machine(original,with_algorithm(base,31,0))
        ref.call(0x20E864,(0,57,110)); ref.call(0x20E864,(1,64,70))
        need(render_synth(ref,1500) != outs[1],'Wave %d sounds as the sine' % (w+1))
        res[NAMES[w]] = native.digest(outs[1])[:8]
    return {'waves_vs_oracle':res,'algorithms':[1,5,7,16,32]}


# ------------------------------------------------------------ operators
def verify_operators(original,patched):
    """Record i <- block i; mixed waves; a new note on the same voice takes
    the new waves; a voice stolen by another program (part b) takes its own."""
    a = machine(patched)
    base = a.data(LIVE,128)
    ws = [1,0,5,7,3,2]
    a.u.mem_write(LIVE,set_waves(base,ws))
    a.call(0x20E864,(0,60,100))
    exp = [SINE if w == 0 else CHAIN+START[w]*2048 for w in ws]
    need(pointers(a,0) == exp,'Operator pointers %s' % [hex(x) for x in pointers(a,0)])
    # block i is the operator processed in position i: only operator 6 on
    # the wave changes the output when operator 6 is silent
    p = bytearray(set_waves(base,[0]*6))
    p[14] = 0                                   # OP6 output level 0
    outs = []
    for w6 in (0,3):
        b = machine(patched,set_waves(bytes(p),[w6,0,0,0,0,0]))
        b.call(0x20E864,(0,60,100))
        outs.append(render_synth(b,800))
    o = machine(original,bytes(p)); o.call(0x20E864,(0,60,100))
    need(outs[0] == render_synth(o,800),'Sine program differs')
    a.u.mem_write(LIVE,set_waves(base,[0]*6))
    # the voice still sounds: Korg queues the note, fades the voice out and
    # starts it from the service routine (0x0020E8C2)
    a.call(0x20E864,(0,62,100))
    need(pointers(a,0) == exp,'Queued note changed the sounding voice')
    render_isr(a,600,service_every=16)
    need(pointers(a,0) == [SINE]*6,'New note kept the old waves')
    return {'block_to_record':'block i (OP6 first) = record i','mixed':[NAMES[w] for w in ws]}


# -------------------------------------------------------------- storage
def verify_storage(original,patched):
    a = machine(patched)
    slot = a.data(0x20002A08,1)[0]
    prog = set_waves(a.data(LIVE,128),[7,6,5,4,3,2])
    a.u.mem_write(LIVE,prog)
    # Korg save: live -> bank slot and the stored copy
    a.call(0x20EF20,(0,0))
    need(a.data(BANK+slot*128,128) == prog,'Save lost the waves')
    need(a.data(STORED,128) == prog,'Stored copy lost the waves')
    # program change to another slot and back
    other = (slot+1) % 64
    a.call(0x20E456,(other,))
    need(waves_of(a.data(LIVE,128)) == waves_of(a.data(BANK+other*128,128)),'Program change')
    a.call(0x20E456,(slot,))
    need(waves_of(a.data(LIVE,128)) == [7,6,5,4,3,2],'Program change back lost the waves')
    a.call(0x20E864,(0,60,100))
    need(pointers(a,0) == [CHAIN+START[w]*2048 for w in [7,6,5,4,3,2]],'Pointers after program change')
    # Korg program SysEx dump and receive (8 bits through the 7-bit packing)
    b = audio_machine(patched)
    tx = []
    b.hook(0x20014F58,lambda: b.return_(4096))
    def cap():
        tx.append(b.u.reg_read(REGS[1])); b.return_(1)
    b.hook(0x20015378,cap)
    b.u.mem_write(0x20002E63,bytes([5]))
    b.u.mem_write(BANK+5*128,prog)
    b.call(0x20014070,(native.SCRATCH,0))
    header = b.data(native.SCRATCH,8)
    b.call(0x20013E18,(0,))
    c = audio_machine(patched)
    for x in header+bytes(tx): c.call(0x200146EC,(1,x))
    need(c.data(BANK+5*128,128) == prog,'Program SysEx lost the waves')
    # DX7 voice import (through the patched veneer): waves of the previous
    # program cleared, everything else as the Korg import
    res = {}
    for img in (original,patched):
        d = machine(img)
        d.u.mem_write(LIVE,prog)
        voice = bytes((i*7+3) % 100 for i in range(155)) + bytes(16)
        d.u.mem_write(native.SCRATCH,voice)
        d.call(0x20015170,(native.SCRATCH,))
        res[img is patched] = d.data(LIVE,128)
    need(waves_of(res[True]) == [0]*6,'DX7 import kept the waves')
    need(res[True] == set_waves(res[False],[0]*6),'DX7 import differs from the Korg one')
    need(waves_of(res[False]) == [7,6,5,4,3,2],'Fixture: Korg import keeps bit 7')
    return {'save_bank_and_stored_copy':True,'program_change':True,'program_sysex_roundtrip':True,
            'dx7_voice_import_clears':True}


# ------------------------------------------------------------------ cpu
def verify_cpu(original,patched):
    """The patched load is the same instruction: the Korg voice loop and
    kernels (ITCM 0x0250..0x12A3) execute the same instructions with or
    without waves; whole frame as in 1.26; the chain is built once."""
    import verify_118 as v118
    def run(img,ws):
        # hooks before the first instruction (Unicorn does not add them to
        # code already translated)
        a = audio_machine(img)
        a.count = [0,False]
        loop = [0]
        def cb(uc,addr,size,ud):
            if a.count[1]:
                a.count[0] += 1
                if 0x250 <= addr < 0x12A4: loop[0] += 1
        a.u.hook_add(UC_HOOK_CODE,cb)
        if ws: a.u.mem_write(LIVE,set_waves(a.data(LIVE,128),ws))
        a.call(0x20EA84,(127,)); a.call(0x20453C,(1,))
        a.call(0x20EA70,(100,)); a.call(0x2045F4,(1,))
        a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
        for i in range(6): a.call(0x20E814,(i,(48+7*i) << 8,127,0x40))
        render_isr(a,600)
        c = v118.count_isr(a,320)
        return {'voice_loop_per_frame':round(loop[0]/320,1),'frame_max':max(c),'frame_mean':round(sum(c)/len(c),1)}
    res = {'korg_1_12':run(original,None),'sine':run(patched,None),'waves':run(patched,[1,2,3,4,5,6])}
    need(res['korg_1_12']['frame_mean'] > 2000,'The six voices are not sounding in the count')
    need(res['sine']['voice_loop_per_frame'] == res['waves']['voice_loop_per_frame'] == res['korg_1_12']['voice_loop_per_frame'],
         'Waves change the cost of the voices: '+str(res))
    a = machine(patched)
    n = [0]
    a.u.hook_add(UC_HOOK_CODE,lambda *x: n.__setitem__(0,n[0]+1))
    a.call(sym('wave_build'))
    res['chain_build_instructions'] = n[0]
    n[0] = 0
    a.call(sym('wave_voice'),(LIVE,ENGINE))
    res['voice_start_instructions'] = n[0]
    need(res['chain_build_instructions'] < 60000,'Chain build too long')
    return res


TASKS = [('v127/off_identical',verify_off_identical),
         ('v127/tables',verify_tables),
         ('v127/oracle',verify_oracle),
         ('v127/operators',verify_operators),
         ('v127/storage',verify_storage),
         ('v127/cpu',verify_cpu)]


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
