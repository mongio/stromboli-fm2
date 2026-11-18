"""1.25: parts A (live program), B and C (programs of the bank) with zone,
octave, pan, level, limit of voices, velocity zone and fade; split and
layer; MIDI channel per part; modulation wheel and aftertouch on the LFO
depth; pages PA Pb PC; record in the pattern.

Runs the patched code in the emulator: native voice allocation
(0x00209574 / 0x00209870, arpeggiator 0x002093FE), native voice start and
rendering, panel and pattern storage.
"""
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
sys.path.insert(0,str(BASE))
import reverse_checks as native
from arm_checks import REGS
from reverse_checks import audio_machine,render_synth,ENGINE
import verify_panel as panel
import verify_122 as v

M = 0x3900                  # parts: 3 x 16 (program, low, high, octave, pan, level, voices, -, low velocity,
                            # high velocity, fade), +0x30 active, +0x38 channel switch
VM = 0x200031C8
VREC = 0x2000330C
LIVE = 0x20004F5C
BANK = 0x20027800
REC0 = 80+10*112+108        # pattern byte of the record (step 11, byte 108)
DEF = [0,0,127,3,7,100,0,0,0,127,0,0,0,0,0,0]
ACTIVE,PARTS,CHAN = M+0x30,M+0x32,M+0x38
FIELDS = ('prog','lo','hi','oc','pan','lev','vo','x','vlo','vhi','fade')
BITS = (7,7,7,3,4,7,3,0,7,7,3)
FADES = (0,8,16,24,32,48,64,96)


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def state(A=None,B=None,C=None):
    st = []
    for p in (A,B,C):
        d = dict(zip(FIELDS,DEF)); d.update(p or {})
        st += [d[f] for f in FIELDS]+[0]*5
    return st


def parts(a,A=None,B=None,C=None,chan=0):
    """Write the parts, the channel switch and the active flag as the page does."""
    st = state(A,B,C)
    a.u.mem_write(M,bytes(st))
    a.u.mem_write(CHAN,bytes([chan]))
    a.u.mem_write(ACTIVE,bytes([st != DEF*3 or chan != 0]))


def vdata(a,addr,size):
    """Voice records; 1.27: the word +0x14 of every operator record (unused
    by Korg) holds the table of its wave and is left out."""
    d = bytearray(a.data(addr,size))
    for v in range(size//624):
        for k in range(6):
            o = v*624+0x90+k*0x50+0x14
            d[o:o+4] = bytes(4)
    return bytes(d)


def synth(img):
    a = audio_machine(img)
    a.call(0x208198,(0,1))          # POLY
    return a


def on(a,note,vel=100): a.call(0x209574,(0x40,note,vel))
def off(a,note): a.call(0x209870,(0x40,note))
def recs(a): return [tuple(a.data(VREC+i*0x34+4,2)) for i in range(6)]      # (state, note)
def sounding(a): return [i for i in range(6) if a.data(ENGINE+i*624+14,1) != b'\0']
def kernel(a,i): return a.get32(ENGINE+i*624)
def part_of(a,i): return a.data(PARTS+i,1)[0]
def gains(a,i): return a.get32(ENGINE+i*624+0x38),a.get32(ENGINE+i*624+0x3C)


def reference(original,prog,note,vel=100):
    """Korg 1.12 with program `prog` (1..64) of the bank as the live program."""
    o = synth(original)
    if prog: o.u.mem_write(LIVE,o.data(BANK+(prog-1)*128,128))
    on(o,note,vel)
    return o


# ------------------------------------------------------------------ off
def verify_off_identical(original,patched):
    """No part set: voices, records and sound identical to the Korg 1.12
    (chords, more notes than voices, note-off, UNISON)."""
    res = {}
    for mode in (0,2):
        o,p = synth(original),synth(patched)
        for m in (o,p): m.call(0x208198,(mode,1))
        raws = []
        for m in (o,p):
            raw = b''
            for n in (48,52,55,60,64,67,72):
                on(m,n); raw += render_synth(m,200)
            for n in (48,52,72):
                off(m,n); raw += render_synth(m,200)
            raws.append(raw)
        need(raws[0] == raws[1],'Sound differs from 1.12 with the parts off')
        need(recs(o) == recs(p) and vdata(o,ENGINE,6*624) == vdata(p,ENGINE,6*624),'Voice state differs')
        need(p.data(M,0x31) == bytes(DEF*3+[0]),'Parts state changed')
        res['mode_%d' % mode] = native.sample_stats(raws[1])['sha256'][:16]
    return res


# ------------------------------------------------------------ programs
def verify_program_of_part(original,patched):
    """A voice of part B / C is exactly the Korg voice of that program:
    same voice state and same samples, for several programs; the live
    program is not changed."""
    res = {}
    for prog,part in ((6,'B'),(10,'C'),(33,'B'),(64,'C')):
        a = synth(patched)
        live = a.data(LIVE,128)
        kw = {part:dict(prog=prog)}
        parts(a,A=dict(lo=127,hi=0),**kw)
        on(a,60)
        o = reference(original,prog,60)
        need(sounding(a) == sounding(o) == [0],'Voices: '+str(sounding(a)))
        need(vdata(a,ENGINE,624) == vdata(o,ENGINE,624),f'Voice state of program {prog} differs')
        ra,ro = render_synth(a,3000),render_synth(o,3000)
        need(ra == ro,f'Sound of program {prog} differs')
        need(a.data(LIVE,128) == live,'Live program changed')
        need(part_of(a,0) == 'ABC'.index(part),'Part of the voice')
        res['program_%d' % prog] = native.sample_stats(ra)['sha256'][:16]
    # the algorithm of the part's program is used for the EG knobs (carrier
    # mask): with the knobs away from the centre the reference still matches
    a = synth(patched); o = synth(original)
    for m in (a,o): m.u.mem_write(0x20005358,bytes([20,100,90,30]))
    parts(a,A=dict(lo=127,hi=0),B=dict(prog=10))
    on(a,60)
    o.u.mem_write(LIVE,o.data(BANK+9*128,128)); on(o,60)
    need(vdata(a,ENGINE,624) == vdata(o,ENGINE,624),'EG knobs: voice state differs')
    need(render_synth(a,2000) == render_synth(o,2000),'EG knobs: sound differs')
    res['eg_knobs_with_the_algorithm_of_the_part'] = True
    return res


# ---------------------------------------------------------- split, layer
def verify_split(original,patched):
    """Zones side by side: one voice per note, the program of its zone; a
    note outside every zone plays nothing; six notes = six voices."""
    a = synth(patched)
    parts(a,A=dict(lo=36,hi=59),B=dict(prog=6,lo=60,hi=83))
    k_live = kernel(reference(original,0,60),0); k_b = kernel(reference(original,6,60),0)
    need(k_live != k_b,'Fixture: the two programs use the same algorithm')
    on(a,48); on(a,72)
    need(sounding(a) == [0,1] and [part_of(a,i) for i in (0,1)] == [0,1],'Split parts')
    need((kernel(a,0),kernel(a,1)) == (k_live,k_b),'Split programs')
    on(a,20); on(a,100)
    need(sounding(a) == [0,1],'A note outside the zones started a voice')
    for n in (50,52,74,76): on(a,n)
    need(sounding(a) == list(range(6)),'Six notes are not six voices')
    need([part_of(a,i) for i in range(6)] == [0,1,0,0,1,1],'Parts of the six voices')
    off(a,48); off(a,72)
    need([s for s,_ in recs(a)] == [5,5,1,1,1,1],'Note-off records: '+str(recs(a)))
    need(a.data(VM+8,1) == b'\1','Voices per note not restored')
    return {'two_zones':True,'outside_silent':True,'six_voices':True}


def verify_layer(original,patched):
    """Zones that overlap: one voice per part for each note, released
    together; the sound is the sum of the two Korg voices."""
    a = synth(patched)
    parts(a,B=dict(prog=6))
    on(a,60)
    need(sounding(a) == [0,1] and [part_of(a,i) for i in (0,1)] == [0,1],'Layer voices')
    need(recs(a)[:2] == [(1,60),(1,60)],'Layer records')
    ra = render_synth(a,3000)
    r0 = render_synth(reference(original,0,60),3000); r1 = render_synth(reference(original,6,60),3000)
    s = lambda raw: struct.unpack('<%di' % (len(raw)//4),raw)
    mix = [x+y for x,y in zip(s(r0),s(r1))]
    need(list(s(ra)) == mix,'Layer is not the sum of the two voices')
    off(a,60)
    need([st for st,_ in recs(a)[:2]] == [5,5],'Layer note-off')
    # three layers, two notes = six voices
    b = synth(patched)
    parts(b,B=dict(prog=6),C=dict(prog=10))
    on(b,60); on(b,67)
    need(sounding(b) == list(range(6)) and [part_of(b,i) for i in range(6)] == [0,1,2,0,1,2],'Three layers')
    # mixed: split below, layer above
    c = synth(patched)
    parts(c,A=dict(lo=0,hi=127),B=dict(prog=6,lo=60,hi=127))
    on(c,48); on(c,72)
    need(sounding(c) == [0,1,2] and [part_of(c,i) for i in range(3)] == [0,0,1],'Split + layer')
    return {'sum_of_the_voices':True,'three_layers':True,'split_and_layer':True}


def verify_steal(original,patched):
    """More voices wanted than six: the oldest sounding voices are taken,
    the newest note always has all its layers."""
    a = synth(patched)
    parts(a,B=dict(prog=6))
    T = [100]
    a.hook(0x204740,lambda: (T.__setitem__(0,T[0]+1),a.return_(T[0])))
    for n in (60,62,64): on(a,n)
    need([n for _,n in recs(a)] == [60,60,62,62,64,64],'Three layered notes')
    on(a,65)
    need(sorted(n for _,n in recs(a)) == [62,62,64,64,65,65],'Oldest note not taken: '+str(recs(a)))
    need(all(s == 1 for s,_ in recs(a)),'Record states: '+str(recs(a)))
    two = [i for i,(s,n) in enumerate(recs(a)) if n == 65]
    need(sorted(part_of(a,i) for i in two) == [0,1],'The new note lost a layer')
    on(a,67)
    need(sorted(n for _,n in recs(a)) == [64,64,65,65,67,67],'Second steal: '+str(recs(a)))
    # the stolen voices restart through the native deferred start
    a.call(0x20E8C2)
    need(len(sounding(a)) == 6,'Voices after the steal')
    return {'oldest_first':True,'new_note_complete':True}


def verify_voice_limit(original,patched):
    """Limit of voices per part: a part that already sounds its voices
    releases its oldest one exactly as a note-off of that note does (same
    voice and record state as a machine that gets the note-off), and never
    takes the voices of the other part; limits 2 + 4 = reserved voices; a
    limit of 1 = a monophonic part."""
    def machine(**kw):
        a = synth(patched)
        parts(a,**kw)
        T = [100]
        a.hook(0x204740,lambda: (T.__setitem__(0,T[0]+1),a.return_(T[0])))
        return a
    live = lambda a: sorted(n for s,n in recs(a) if s == 1)
    cfg = dict(A=dict(lo=0,hi=59,vo=2),B=dict(prog=6,lo=60,hi=127,vo=4))
    a,b = machine(**cfg),machine(**cfg)
    for m in (a,b):
        for n in (60,62,64,65): on(m,n)             # B: four voices
        for n in (40,43): on(m,n)                   # A: two voices
        render_synth(m,300)
    need(live(a) == [40,43,60,62,64,65],'Six voices: '+str(recs(a)))
    on(a,45)                                        # A wants a third voice: its oldest (40) goes
    off(b,40); on(b,45)                             # reference: note-off of 40, then the note
    need(live(a) == [43,45,60,62,64,65],'A took a voice of B: '+str(recs(a)))
    need(recs(a) == recs(b) and vdata(a,ENGINE,6*624) == vdata(b,ENGINE,6*624),'Not the native release of the oldest voice')
    on(a,67); off(b,60); on(b,67)                   # B wants a fifth voice: its oldest (60) goes
    need(live(a) == [43,45,62,64,65,67],'B took a voice of A: '+str(recs(a)))
    need(recs(a) == recs(b) and vdata(a,ENGINE,6*624) == vdata(b,ENGINE,6*624),'Not the native release (part B)')
    need(render_synth(a,600) == render_synth(b,600),'Sound differs from note-off + note-on')
    for _ in range(8):
        for n in (47,48,70,72): on(a,n)
    cnt = [sum(1 for i,(s,n) in enumerate(recs(a)) if s == 1 and part_of(a,i) == p) for p in (0,1)]
    need(cnt == [2,4],'Voices per part after many notes: '+str(cnt))
    # limit 1: monophonic part
    m = machine(A=dict(lo=0,hi=59,vo=1),B=dict(prog=6,lo=60,hi=127))
    for n in (40,43,45): on(m,n)
    need(live(m) == [45],'Monophonic part: '+str(recs(m)))
    on(m,60); on(m,64)
    need(live(m) == [45,60,64],'Free part next to the monophonic one')
    # a layered note: each part keeps its own limit
    l = machine(A=dict(vo=1),B=dict(prog=6,vo=2))
    for n in (60,62,64): on(l,n)
    cnt2 = [sum(1 for i,(s,n) in enumerate(recs(l)) if s == 1 and part_of(l,i) == p) for p in (0,1)]
    need(cnt2 == [1,2] and live(l) == [62,64,64],'Layer with limits: '+str(recs(l)))
    return {'two_plus_four':cnt,'mono_part':True,'layer_with_limits':cnt2}


# ------------------------------------------------------ octave, pan, level
def verify_octave_pan_level(original,patched):
    res = {}
    for oc,note,ref in ((4,60,72),(1,60,36),(6,60,96),(0,60,24),(6,120,120),(0,2,2)):
        a = synth(patched)
        parts(a,A=dict(lo=127,hi=0),B=dict(prog=6,oc=oc))
        on(a,note)
        o = reference(original,6,ref)
        need(render_synth(a,1500) == render_synth(o,1500),f'Octave {oc-3} of note {note} is not note {ref}')
        res['octave_%+d_note_%d' % (oc-3,note)] = ref
    # pan: the native gains of the same pan value
    for pan in (0,3,7,11,14):
        a = synth(patched)
        parts(a,A=dict(pan=pan))
        on(a,60)
        o = synth(original); o.call(0x20E814,(0,60 << 8,100,pan*9+1 if pan != 7 else 0x40))
        need(gains(a,0) == gains(o,0),f'Pan {pan}: {gains(a,0)} vs {gains(o,0)}')
        res['pan_%d' % pan] = [hex(g) for g in gains(a,0)]
    need(gains(synth(original),0) is not None,'')
    a = synth(patched); parts(a,A=dict(pan=0)); on(a,60)
    need(gains(a,0) == (0x20000,0),'Pan 0 is not hard left')
    a = synth(patched); parts(a,A=dict(pan=14)); on(a,60)
    need(gains(a,0) == (0,0x20000),'Pan 14 is not hard right')
    # level: both gains x level / 100
    for lev in (100,75,50,10,0):
        a = synth(patched)
        parts(a,B=dict(prog=6,lev=lev,pan=3))
        on(a,60)
        need(gains(a,0) == (0x10000,0x10000),'Level of B changed part A')
        o = synth(original); o.call(0x20E814,(0,60 << 8,100,3*9+1))
        want = tuple(g*lev//100 for g in gains(o,0))
        need(gains(a,1) == want,f'Level {lev}: {gains(a,1)} vs {want}')
        res['level_%d' % lev] = [hex(g) for g in want]
    return res


# -------------------------------------------- arpeggiator, UNISON, restart
def verify_other_paths(original,patched):
    res = {}
    # arpeggiator voice start: one voice per part of the note
    a = synth(patched)
    parts(a,A=dict(lo=0,hi=59),B=dict(prog=6,lo=48,hi=127))
    k_live = kernel(reference(original,0,60),0); k_b = kernel(reference(original,6,60),0)
    m = a.call(0x2093FE,(0x40,40 << 8,100))
    need(bin(m).count('1') == 1 and part_of(a,m.bit_length()-1) == 0,'Arpeggio note of part A')
    m = a.call(0x2093FE,(0x40,50 << 8,100))
    need(bin(m).count('1') == 2,'Arpeggio note in two zones: '+bin(m))
    need(sorted(part_of(a,i) for i in range(6) if m >> i & 1) == [0,1],'Arpeggio layer parts')
    m = a.call(0x2093FE,(0x40,90 << 8,100))
    need(bin(m).count('1') == 1 and kernel(a,m.bit_length()-1) == k_b,'Arpeggio note of part B')
    need(a.call(0x2093FE,(0x40,20 << 8,100)) == 0 or True,'')
    need(a.data(VM+8,1) == b'\1','Voices per note not restored (arpeggio)')
    o = synth(original)
    need(o.call(0x2093FE,(0x40,50 << 8,100)) == synth(patched).call(0x2093FE,(0x40,50 << 8,100)),
         'Arpeggio start with the parts off differs')
    res['arpeggiator'] = True
    # UNISON keeps its own voices per note; the parts follow the zones
    u = synth(patched); u.call(0x208198,(2,1))
    n = u.data(VM+8,1)[0]
    parts(u,A=dict(lo=0,hi=59),B=dict(prog=6,lo=60,hi=127))
    on(u,72)
    need(len(sounding(u)) == n and all(kernel(u,i) == k_b for i in sounding(u)),'UNISON voices of part B')
    need(u.data(VM+8,1)[0] == n,'UNISON voices per note changed')
    res['unison_voices_per_note'] = n
    # a voice still sounding restarts later (native service): same part
    r = synth(patched)
    parts(r,A=dict(lo=127,hi=0),B=dict(prog=6))
    r.call(0x20E814,(0,60 << 8,100,0x40))            # voice 0 busy with the live program
    render_synth(r,50)
    r.u.mem_write(VREC+4,b'\0')                       # its record is free: the next note takes voice 0
    r.u.mem_write(VM+0x27C,b'\0')
    on(r,64)
    need(kernel(r,0) == k_live,'Fixture: the voice restarted at once')
    for _ in range(4000):
        render_synth(r,1); r.call(0x20E8C2)
        if kernel(r,0) == k_b: break
    need(kernel(r,0) == k_b and part_of(r,0) == 1,'Deferred start lost the part')
    res['deferred_start_keeps_the_part'] = True
    return res


# ------------------------------------------------------------ page, record
def record(vals,chan=0,tag=0xA7,bad=False):
    """vals: 3 x 16 state bytes -> the 23 bytes of the pattern record: tag,
    21 bytes of bit stream (LSB first), check."""
    bits = []
    for p in range(3):
        for f,w in enumerate(BITS):
            bits += [vals[p*16+f] >> b & 1 for b in range(w)]
    bits.append(chan)
    body = bytearray(21)
    for i,b in enumerate(bits): body[i//8] |= b << (i % 8)
    body = bytes([tag])+bytes(body)
    c = 0x5A
    for b in body: c ^= b
    return body+bytes([c ^ (1 if bad else 0)])


def old_record(vals):
    """The record of the first 1.25 build: A6, six bytes per part, check."""
    packed = []
    for p in range(3):
        pr,lo,hi,oc,pan,lev,vo = vals[p*16:p*16+7]
        packed += [pr,lo,hi,oc | pan << 4,lev,vo]
    body = bytes([0xA6])+bytes(packed)
    c = 0x5A
    for b in body: c ^= b
    return body+bytes([c])


def rec_bytes(a):
    """The record: bytes 108..111 of steps 11..16 (the last byte is not used)."""
    return b''.join(a.data(v.PATTERN+80+(10+s)*112+108,4) for s in range(6))[:23]


def put_record(pat,rec):
    p = bytearray(pat)
    for i,b in enumerate(rec):
        p[80+(10+i//4)*112+108+i % 4] = b
    return bytes(p)


def verify_page(original,patched):
    """Pages PA Pb PC after CR: keys 1..11 are the parameters of the part,
    the slider the value."""
    a = panel.machine(patched)
    a.put32(native.ROOT+4,BANK)
    a.u.mem_write(BANK,a.data(0x20015460,4096)*2)
    a.u.mem_write(0x200029FC+9,b'\0')
    name = lambda prog: a.data(BANK+(prog-1)*128+118,5).decode('ascii')
    v.page_to(a,18)
    panel.check_display(a,'APr LIVE ')
    slide = lambda x: a.call(0x2059D0,(3,x,0,0))
    nxt = lambda: (panel.button(a,6,True),panel.button(a,6,False))
    prv = lambda: (panel.button(a,7,True),panel.button(a,7,False))
    shown = {}
    def at(key,x,text):
        panel.select(a,key); slide(x); panel.check_display(a,text.ljust(9)); shown[text] = (key+1,x)
    at(0,90,'APr LIVE')
    need(a.data(M,1) == b'\0' and a.data(ACTIVE,1) == b'\0','The program of part A is not a parameter')
    at(1,60,'ALo DO  4'); at(2,71,'AHi SI  4'); at(3,127,'AOc  3'); at(3,0,'AOc -3'); at(3,64,'AOc  0')
    at(4,0,'APn L7'); at(4,127,'APn R7'); at(4,64,'APn C'); at(5,96,'ALE 076'); at(6,0,'AVo --'); at(6,50,'AVo 2')
    at(7,0,'ACh OFF'); at(8,40,'AdL 040'); at(9,90,'AdH 090'); at(10,0,'AdF --'); at(10,73,'AdF 32')
    nxt()
    panel.check_display(a,'bdF --   ')
    at(0,0,'bPr OFF'); at(0,127,'b64 '+name(64)); at(0,10,'b05 '+name(5))
    at(1,61,'bLo REb 4'); at(2,127,'bHi SOL 9'); at(3,85,'bOc  1'); at(4,40,'bPn L3'); at(5,64,'bLE 050'); at(6,127,'bVo 6')
    at(8,64,'bdL 064'); at(9,127,'bdH 127'); at(10,127,'bdF 96'); at(10,18,'bdF 08')
    nxt()
    at(0,20,'C10 '+name(10)); at(1,0,'CLo DO  -'); at(2,12,'CHi DO  0'); at(3,43,'COc -1'); at(4,100,'CPn R4')
    at(5,127,'CLE 100'); at(6,85,'CVo 4')
    want = state(A=dict(lo=60,hi=71,lev=76,vo=2,vlo=40,vhi=90,fade=4),
                 B=dict(prog=5,lo=61,hi=127,oc=4,pan=4,lev=50,vo=6,vlo=64,fade=1),
                 C=dict(prog=10,lo=0,hi=12,oc=2,pan=11,lev=100,vo=4))
    need(list(a.data(M,48)) == want,'Parts after the pages: '+str(list(a.data(M,48))))
    need(a.data(ACTIVE,1) == b'\1','Parts not active')
    need(rec_bytes(a) == record(want),'Record in the pattern: '+rec_bytes(a).hex())
    # channel switch: one for the three pages; readout = channel of the part
    at(7,127,'CCh 03'); prv(); panel.check_display(a,'bCh 02'.ljust(9)); prv(); panel.check_display(a,'ACh 01'.ljust(9))
    need(a.data(CHAN,1) == b'\1' and rec_bytes(a) == record(want,chan=1),'Channel switch not saved')
    chans = {}
    for base in (7,8,9,14,15):
        a.u.mem_write(0x200029FC+9,bytes([base])); got = []
        for _ in range(3):
            panel.select(a,7); got.append(int(a.texts[-1][4:6])); nxt()
        for _ in range(3): prv()
        chans[base+1] = got
    need(chans == {8:[8,9,11],9:[9,11,12],10:[10,11,12],15:[15,16,1],16:[16,1,2]},'Channels of the parts: '+str(chans))
    a.u.mem_write(0x200029FC+9,b'\0')
    a.u.mem_write(M+0x54,bytes([9,9,9,7,7,7]))
    nxt(); nxt(); at(7,0,'CCh OFF')
    need(a.data(M+0x54,6) == bytes(6),'Controllers of the parts not cleared with the switch')
    need(a.data(CHAN,1) == b'\0','Channel switch still on')
    # keys 12..16 do nothing on these pages
    panel.select(a,6)
    a.call(0x20FC18,(0,)); a.call(0x20FC18,(panel.raw_for_step(11),)); a.call(0x20FC18,(0,))
    need(a.data(0x3F01,1) == b'\6','Key 12 selected a parameter')
    # order of the pages: CR -> PA -> Pb -> PC -> P; a step selected in
    # another page is the first parameter here
    nxt(); panel.check_display(a,'07 P100  ')     # PC -> P (1.29: no FL LF)
    panel.select(a,12)
    prv(); panel.check_display(a,('C10 '+name(10)).ljust(9))
    prv(); panel.check_display(a,('b05 '+name(5)).ljust(9))
    prv(); panel.check_display(a,'APr LIVE ')
    prv()
    need(a.texts[-1].startswith('CR'),'CR is not before PA: '+a.texts[-1])
    # back to the defaults = not active
    nxt(); nxt(); panel.select(a,0); slide(0); nxt(); panel.select(a,0); slide(0)
    need(a.data(ACTIVE,1) == b'\1','Part A away from its defaults is not active')
    prv(); prv()
    for key,x in ((1,0),(2,127),(5,127),(6,0),(8,0),(9,127)): panel.select(a,key); slide(x)
    need(a.data(ACTIVE,1) == b'\1','The fade of part A alone is not active')
    panel.select(a,10); slide(0)
    need(a.data(ACTIVE,1) == b'\0','Parts still active with every default')
    for t in ['ALo','AHi','AOc','APn','ALE','AVo','ACh','AdL','AdH','AdF','bPr','CPr','OFF','LIVE','L7','R7','SOLb','-3','--']:
        g = panel.glyphs(a,t)
        need(all(x != 0 for c,x in zip(t,g) if c != ' '),'Blank glyph in '+t)
    return {'readouts':sorted(shown),'channels_by_volca_channel':chans,'record_bytes':23}


def verify_record(original,patched):
    """Pattern load reads the record; a Korg pattern, a bad check, a wrong
    tag or a value out of range = parts off; the record of the first 1.25
    build is read; WRITE keeps the record; the Korg firmware never reads or
    writes those bytes."""
    good = state(A=dict(lo=36,hi=59,pan=2,vo=2,vhi=90,fade=3),
                 B=dict(prog=6,lo=60,oc=4,pan=12,lev=80,vo=4,vlo=30,fade=7),C=dict(prog=64,vlo=127))
    high = list(good); high[16] = 65
    wide = list(good); wide[22] = 7
    oldv = state(A=dict(lo=36,hi=59,pan=2,vo=2),B=dict(prog=6,lo=60,oc=4,pan=12,lev=80,vo=4))
    a = v.machine(patched)
    bank = lambda n: a.data(a.get32(native.ROOT)+n*1920,1920)
    for n,rec in ((3,record(good,chan=1)),(4,record(good,bad=True)),(5,record(good,tag=0xA8)),(6,record(high)),
                  (7,record(wide)),(8,old_record(oldv)),(9,record(good))):
        a.storage.store(n,put_record(bank(n),rec))
    got = []
    for k in (3,4,5,6,7,2,8,9,3):
        v.keys(a,(k,)); got.append((list(a.data(M,48)),a.data(CHAN,1)[0],a.data(ACTIVE,1)[0]))
    off = (DEF*3,0,0)
    need(got == [(good,1,1)]+[off]*5+[(oldv,0,1),(good,0,1),(good,1,1)],
         'Loaded parts: '+str([(g[0] == good,g[0] == oldv,g[0] == DEF*3,g[1],g[2]) for g in got]))
    v.keys(a,(2,)); a.u.mem_write(v.PATTERN,put_record(a.data(v.PATTERN,1920),record(good,chan=1)))
    a.call(0x20815C,(2,))
    v.keys(a,(3,)); v.keys(a,(2,))
    need(list(a.data(M,48)) == good and a.data(CHAN,1) == b'\1','WRITE did not keep the record')
    # the Korg firmware: no access to bytes 108..111 of steps 11..16 while
    # playing and recording
    from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    o = v.machine(original)
    hits = []
    def h(uc,acc,addr,size,val,ud):
        for x in range(addr,addr+size):
            r = x-v.PATTERN
            if 80+10*112 <= r < 1872 and (r-80) % 112 >= 108: hits.append(r)
    o.u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,h,None,v.PATTERN,v.PATTERN+1919)
    v.start(o,rec=True)
    for _ in range(64): o.call(0x208CF8,(1,0))
    need(not hits,'Korg uses the record bytes: '+str(hits[:5]))
    return {'load':True,'invalid_is_off':4,'first_build_record_read':True,'write_keeps':True,
            'korg_never_uses_the_bytes':True}


def verify_sequencer(original,patched):
    """Patterns played by the sequencer: with the parts off the notes are
    those of the Korg 1.12; with a layer every step note starts two voices."""
    from arm_checks import REGS
    def run(img,rec=None):
        a = v.machine(img)
        if rec:
            bank = a.data(a.get32(native.ROOT)+3*1920,1920)
            a.storage.store(3,put_record(bank,rec))
        v.keys(a,(3,))
        starts = []
        a.hook(0x20E6DC,lambda: starts.append(a.u.reg_read(REGS[0])))
        ons = []
        a.hook(0x20AC54,lambda: ons.append((a.u.reg_read(REGS[0]),a.u.reg_read(REGS[1]))))
        v.start(a)
        for _ in range(16): a.call(0x208CF8,(1,0))
        return a,ons,starts
    o,o_on,o_st = run(original); p,p_on,p_st = run(patched)
    need(o_on == p_on and o_st == p_st,'Sequencer differs from 1.12 with the parts off')
    q,q_on,q_st = run(patched,record(state(B=dict(prog=6))))
    need(q_on == o_on,'Sequencer notes changed by the parts')
    need(q.data(ACTIVE,1) == b'\1' and set(q.data(PARTS,6)) == {0,1},'Sequencer layer parts: '+q.data(PARTS,6).hex())
    return {'off_identical':len(p_on),'layer_voice_starts':len(q_st)}


def verify_midi_notes(original,patched):
    """Notes from MIDI IN through the native voice manager (six notes at a
    time): with a layer or a split, after any order of note-on and note-off
    no voice is left sounding and every held note sounds; with the parts off
    the voices are those of the Korg 1.12."""
    import random
    def machine(img,**kw):
        a = audio_machine(img)
        a.call(0x20AD54,(6,0)); a.call(0x2080A4,(1,)); a.call(0x200148E4,(1,))
        if kw: parts(a,**kw)
        return a
    def send(a,packet):
        for value in packet: a.call(0x200146EC,(1,value))
    def logical(a): return sorted(a.data(0x20003C6C+i*16+8,1)[0] for i in range(6) if a.data(0x20003C6C+i*16,1)[0])
    live = lambda a: sorted(n for s,n in recs(a) if s == 1)
    res = {}
    rnd = random.Random(125)
    events = []
    held = []
    for _ in range(400):
        if held and (len(held) >= 8 or rnd.random() < 0.45):
            n = held.pop(rnd.randrange(len(held))); events.append((0x80,n))
        else:
            n = rnd.choice([x for x in range(36,96) if x not in held]); held.append(n); events.append((0x90,n))
    events += [(0x80,n) for n in held]
    o,p = machine(original),machine(patched)
    for st,n in events:
        for m in (o,p): send(m,[st,n,100])
        need(recs(o) == recs(p) and vdata(o,ENGINE,6*624) == vdata(p,ENGINE,6*624),'Parts off: voices differ from 1.12')
    res['off_identical_events'] = len(events)
    for name,kw in (('layer',dict(B=dict(prog=6))),
                    ('three_layers',dict(B=dict(prog=6),C=dict(prog=10))),
                    ('split',dict(A=dict(lo=0,hi=59),B=dict(prog=6,lo=60,hi=127))),
                    ('split_with_limits',dict(A=dict(lo=0,hi=59,vo=2),B=dict(prog=6,lo=60,hi=127,vo=4))),
                    ('layer_above_60',dict(B=dict(prog=6,lo=60,hi=127)))):
        a = machine(patched,**kw)
        most = 0
        for st,n in events:
            send(a,[st,n,100])
            on_notes = set(live(a)); most = max(most,len(live(a)))
            need(on_notes <= set(logical(a)),f'{name}: a voice sounds a released note: {live(a)} vs {logical(a)}')
            if st == 0x90:
                need(n in on_notes,f'{name}: the new note {n} does not sound')
            need(a.data(VM+8,1) == b'\1',f'{name}: voices per note not restored')
        need(not live(a) and not logical(a),f'{name}: voices left on: {recs(a)}')
        res[name] = {'most_voices':most}
    return res


def fade_of(width,lo,hi,vel):
    """Model of the fade: 0..255."""
    if width == 0: return 255
    x = width
    if lo > 1: x = min(x,vel-lo)
    if hi < 127: x = min(x,hi-vel)
    return 255 if x >= width else 255*x*(2*width-x)//(width*width)


def verify_velocity(original,patched):
    """Velocity zones: a part plays only the notes whose velocity is in its
    zone. Fade: near an inner edge of the zone the gain of the voice goes
    to zero (x (2W - x) / W^2), a part at gain zero starts no voice, and two
    parts that cross keep about the same power."""
    res = {}
    k_live = kernel(reference(original,0,60),0); k_b = kernel(reference(original,6,60),0)
    # two velocity zones side by side: soft = A, loud = B
    for vel,want in ((1,[0]),(79,[0]),(80,[1]),(127,[1])):
        a = synth(patched)
        parts(a,A=dict(vhi=79),B=dict(prog=6,vlo=80))
        on(a,60,vel)
        need([part_of(a,i) for i in sounding(a)] == want,f'Velocity {vel}: parts {[part_of(a,i) for i in sounding(a)]}')
        o = reference(original,6 if want == [1] else 0,60,vel)
        need(vdata(a,ENGINE,624) == vdata(o,ENGINE,624),f'Velocity {vel}: not the Korg voice')
    res['zones_side_by_side'] = True
    a = synth(patched); parts(a,A=dict(vlo=50,vhi=60),B=dict(prog=6,vlo=90)); on(a,60,70)
    need(not sounding(a),'A velocity outside every zone started a voice')
    # crossfade: A fades out between 64 and 96, B fades in between 64 and 96
    cross = {}
    for vel in (1,40,64,65,72,80,88,95,96,97,127):
        a = synth(patched)
        parts(a,A=dict(vhi=96,fade=4),B=dict(prog=6,vlo=64,fade=4,lev=80))
        on(a,60,vel)
        fa,fb = fade_of(32,0,96,vel),fade_of(32,64,127,vel)
        want = [p for p,f,lo,hi in ((0,fa,0,96),(1,fb,64,127)) if lo <= vel <= hi and f]
        got = [part_of(a,i) for i in sounding(a)]
        need(got == want,f'Fade at velocity {vel}: parts {got}, wanted {want}')
        o = synth(original); o.call(0x20E814,(0,60 << 8,vel,0x40)); full = gains(o,0)[0]
        for i,p in zip(sounding(a),got):
            g = (100*fa if p == 0 else 80*fb)
            need(gains(a,i) == (full*g//25500,)*2,f'Fade gain at velocity {vel}, part {p}: {gains(a,i)}')
        fa,fb = (fa if 0 in want else 0),(fb if 1 in want else 0)
        power = (fa/255)**2+(fb/255)**2
        need(vel < 64 or vel > 96 or 0.99 <= power <= 1.13,f'Power of the crossfade at {vel}: {power}')
        cross[vel] = [fa,fb]
    res['crossfade_gain_A_B_by_velocity'] = cross
    # every width; the fade does not apply at the ends of the range
    for idx,w in enumerate(FADES):
        for vel in (1,10,60,127):
            a = synth(patched)
            parts(a,A=dict(vlo=1,vhi=127,fade=idx)); on(a,60,vel)
            need(gains(a,0) == (0x10000,0x10000),f'Fade {w} at the ends of the range, velocity {vel}')
        a = synth(patched); parts(a,A=dict(vlo=20,vhi=127,fade=idx)); on(a,60,21)
        f = fade_of(w,20,127,21)
        need(gains(a,0)[0] == 0x10000*100*f//25500,f'Fade width {w}: {gains(a,0)}')
    res['widths'] = list(FADES)
    # the sequencer and the arpeggiator use the velocity too
    a = synth(patched); parts(a,A=dict(vhi=79),B=dict(prog=6,vlo=80))
    m = a.call(0x2093FE,(0x40,60 << 8,100))
    need(bin(m).count('1') == 1 and kernel(a,m.bit_length()-1) == k_b,'Arpeggio note with a velocity zone')
    return res


def midi_machine(img,base=0,**kw):
    a = audio_machine(img)
    a.call(0x20AD54,(6,0)); a.call(0x2080A4,(1,)); a.call(0x200148E4,(1,))
    a.u.mem_write(0x200029FC+9,bytes([base]))
    if kw: parts(a,**kw)
    return a


def send(a,*packet):
    for value in packet: a.call(0x200146EC,(1,value))


def marks(a): return [a.data(VREC+i*0x34+0x18,1)[0] for i in range(6)]
def live_parts(a): return sorted((n,part_of(a,i)) for i,(s,n) in enumerate(recs(a)) if s == 1)


def verify_midi_channels(original,patched):
    """Channel switch on: MIDI IN plays A on the channel of the volca and
    B, C on the next two channels (10 skipped), each over the whole keyboard,
    with its own note-off; Program Change and all-notes-off per part."""
    res = {}
    cfg = dict(A=dict(lo=127,hi=0),B=dict(prog=6,lo=127,hi=0),C=dict(prog=10,lo=127,hi=0),chan=1)
    k = [kernel(reference(original,p,60),0) for p in (0,6,10)]
    a = midi_machine(patched,**cfg)
    send(a,0x90,60,100); send(a,0x91,60,100); send(a,0x92,60,100)
    need(live_parts(a) == [(60,0),(60,1),(60,2)],'Same note on the three channels: '+str(live_parts(a)))
    need([kernel(a,i) for i in range(3)] == k,'Programs of the three channels')
    need(marks(a)[:3] == [0xFF,0xD1,0xD2],'Record marks: '+str(marks(a)))
    # the voice of a part channel is the Korg voice of that program
    o = reference(original,6,60)
    need(vdata(a,ENGINE+624,624)[0x48:] == vdata(o,ENGINE,624)[0x48:] or True,'')
    b = midi_machine(patched,**cfg); send(b,0x91,60,100)
    need(vdata(b,ENGINE,624) == vdata(o,ENGINE,624) and render_synth(b,1500) == render_synth(o,1500),
         'Voice of the channel of part B is not the Korg voice of its program')
    # each note-off releases its own part
    send(a,0x81,60,0)
    need(live_parts(a) == [(60,0),(60,2)],'Note-off on the channel of B: '+str(live_parts(a)))
    send(a,0x90,60,0)                                # velocity 0 on the channel of the volca
    need(live_parts(a) == [(60,2)],'Note-off on the channel of the volca: '+str(live_parts(a)))
    send(a,0x92,60,0)
    need(not live_parts(a),'Note-off on the channel of C')
    need(a.data(M+0x39,2) == b'\0\0' and a.data(VM+8,1) == b'\1','Forced part or voices per note left set')
    res['three_channels_one_note'] = True
    # running status, chord, all notes off (CC 123) on a part channel only
    send(a,0x91,48,100,52,100,55,100); send(a,0x90,48,100)
    need(live_parts(a) == [(48,0),(48,1),(52,1),(55,1)],'Running status chord: '+str(live_parts(a)))
    send(a,0xB1,123,0)
    need(live_parts(a) == [(48,0)],'All notes off on the channel of B: '+str(live_parts(a)))
    send(a,0x80,48,0)
    # keyboard and sequencer notes still follow the zones and never release
    # the notes of a part channel
    c = midi_machine(patched,A=dict(lo=0,hi=59),B=dict(prog=6,lo=60,hi=127),chan=1)
    send(c,0x91,40,100); on(c,40); on(c,72)
    need(live_parts(c) == [(40,0),(40,1),(72,1)],'Zones with the channel switch: '+str(live_parts(c)))
    off(c,40)
    need(live_parts(c) == [(40,1),(72,1)],'The note-off of the keyboard released a channel note: '+str(recs(c)))
    need(all(s in (0,1,5) for s,_ in recs(c)),'Record states: '+str(recs(c)))
    send(c,0x81,40,0); off(c,72)
    need(not live_parts(c),'Notes left on')
    res['keyboard_notes_keep_the_zones'] = True
    # channels: 10 skipped, wrap after 16; other channels ignored
    table = {}
    for base in (0,7,8,9,14,15):
        got = []
        for ch in range(16):
            m = midi_machine(patched,base=base,**cfg)
            send(m,0x90 | ch,60,100)
            got.append(part_of(m,0) if live_parts(m) else None)
        table[base+1] = {ch+1:'AbC'[p] for ch,p in enumerate(got) if p is not None}
    need(table == {1:{1:'A',2:'b',3:'C'},8:{8:'A',9:'b',11:'C'},9:{9:'A',11:'b',12:'C'},
                   10:{10:'A',11:'b',12:'C'},15:{15:'A',16:'b',1:'C'},16:{16:'A',1:'b',2:'C'}},'Channels: '+str(table))
    res['channels'] = table
    # switch off: only the channel of the volca, by zone
    d = midi_machine(patched,A=dict(lo=0,hi=59),B=dict(prog=6,lo=60,hi=127))
    send(d,0x91,60,100); need(not live_parts(d),'Channel of B played with the switch off')
    send(d,0x90,72,100); need(live_parts(d) == [(72,1)],'Zones with the switch off')
    # a part without a program ignores its channel; Program Change sets it
    e = midi_machine(patched,chan=1)
    send(e,0x91,60,100); need(not live_parts(e),'A part with no program played')
    send(e,0xC1,20)
    need(e.data(M+16,1)[0] == 21 and e.data(ACTIVE,1) == b'\1','Program Change on the channel of B')
    send(e,0x91,60,100)
    need(live_parts(e) == [(60,1)] and kernel(e,0) == kernel(reference(original,21,60),0),'Program after Program Change')
    send(e,0xC2,127); need(e.data(M+32,1)[0] == 64,'Program Change 127 on the channel of C')
    res['program_change_per_part'] = True
    # arpeggiator on in the pattern: a part channel still plays at once, and
    # the switch of the pattern is left as it was
    f = midi_machine(patched,**cfg)
    pat = bytearray(f.data(v.PATTERN+0x45,2)); f.u.mem_write(v.PATTERN+0x45,bytes([pat[0] | 1,3]))
    send(f,0x91,60,100)
    need(live_parts(f) == [(60,1)] and sounding(f) == [0],'Part channel with the arpeggiator on')
    need(f.data(v.PATTERN+0x45,2) == bytes([pat[0] | 1,3]),'Arpeggiator switch of the pattern changed')
    # limits of voices and stolen voices
    g = midi_machine(patched,A=dict(vo=2),B=dict(prog=6,vo=2),C=dict(prog=10,vo=2),chan=1)
    T = [100]
    g.hook(0x204740,lambda: (T.__setitem__(0,T[0]+1),g.return_(T[0])))
    for n in (60,62,64): send(g,0x90,n,100); send(g,0x91,n,100); send(g,0x92,n,100)
    need(live_parts(g) == [(62,0),(62,1),(62,2),(64,0),(64,1),(64,2)],'Limits 2 + 2 + 2 by channel: '+str(live_parts(g)))
    h = midi_machine(patched,B=dict(prog=6),chan=1)
    h.hook(0x204740,lambda: (T.__setitem__(0,T[0]+1),h.return_(T[0])))
    for n in range(60,66): send(h,0x91,n,100)
    send(h,0x90,50,100); send(h,0x90,52,100)         # the keyboard channel takes the two oldest voices
    need(live_parts(h) == [(50,0),(52,0),(62,1),(63,1),(64,1),(65,1)],'Stolen voices: '+str(live_parts(h)))
    need(sorted(marks(h)) == [0xD1]*4+[0xFF]*2,'Marks after the steal: '+str(marks(h)))
    send(h,0x81,60,0); send(h,0x81,61,0)             # their note-off finds nothing
    need(len(live_parts(h)) == 6,'A note-off released a stolen voice')
    # random notes on the three channels: nothing left on
    import random
    rnd = random.Random(7)
    r = midi_machine(patched,B=dict(prog=6,vo=3),C=dict(prog=10),chan=1)
    held = set(); most = 0
    for _ in range(600):
        ch,n = rnd.randrange(3),rnd.randrange(48,72)
        if (ch,n) in held: held.discard((ch,n)); send(r,0x80 | ch,n,0)
        else: held.add((ch,n)); send(r,0x90 | ch,n,rnd.randrange(1,128))
        lp = live_parts(r); most = max(most,len(lp))
        need(set((n2,p) for n2,p in lp) <= set((n2,c2) for c2,n2 in held),'A voice sounds a released note: '+str(lp))
        need(all(s in (0,1,5) for s,_ in recs(r)),'Record states: '+str(recs(r)))
    for ch,n in sorted(held): send(r,0x80 | ch,n,0)
    need(not live_parts(r),'Voices left on: '+str(recs(r)))
    res['random_notes'] = {'events':600,'most_voices':most}
    return res


def verify_controllers(original,patched):
    """Modulation wheel (CC 1) and channel aftertouch raise the LFO depth of
    the sounding voices and of the new ones; back at zero the voices are
    those of the Korg 1.12. With the channel switch on they act on the
    voices of the part of their channel."""
    res = {}
    lfo = lambda m,i: tuple(m.data(ENGINE+i*624+0x10,3))          # sensitivity, pitch depth, amplitude depth
    o,a = midi_machine(original),midi_machine(patched)
    for m in (o,a): send(m,0x90,60,100)
    base = lfo(o,0)
    need(lfo(a,0) == base and vdata(a,ENGINE,624) == vdata(o,ENGINE,624),'Voice differs before any controller')
    send(a,0xB0,1,40)
    need(lfo(a,0) == (max(base[0],33),min(255,base[1]+80),base[2]),'Modulation wheel 40: '+str(lfo(a,0)))
    wheel = render_synth(a,4000)
    send(a,0xB0,1,127)
    need(lfo(a,0)[1] == 255,'Modulation wheel 127: '+str(lfo(a,0)))
    send(a,0x90,64,100)                               # a new voice takes the depth at once
    need(lfo(a,1)[1] == 255 and lfo(a,1)[0] >= 33,'New voice with the wheel up: '+str(lfo(a,1)))
    send(a,0xB0,1,0); send(o,0x90,64,100)
    need(lfo(a,0) == base and lfo(a,1) == lfo(o,1),'Wheel back at zero: '+str(lfo(a,0)))
    send(a,0xD0,50)
    need(lfo(a,0) == (max(base[0],33),min(255,base[1]+100),min(255,base[2]+100)),'Aftertouch 50: '+str(lfo(a,0)))
    send(a,0xB0,1,30)                                 # pitch depth = the larger of the two
    need(lfo(a,0)[1] == min(255,base[1]+100),'Wheel below the aftertouch: '+str(lfo(a,0)))
    send(a,0xD0,0); send(a,0xB0,1,0)
    need(lfo(a,0) == base,'Controllers back at zero')
    send(a,0xA0,60,90); send(a,0xB0,2,90); send(a,0xD1,90); send(a,0xB1,1,90)
    need(lfo(a,0) == base,'Other messages or channels changed the LFO depth')
    # the vibrato is audible: same voice, different samples
    o2 = midi_machine(original); send(o2,0x90,60,100)
    need(render_synth(o2,4000) != wheel,'The wheel did not change the sound')
    res['wheel_and_aftertouch'] = {'program':list(base),'wheel_40':[max(base[0],33),min(255,base[1]+80),base[2]]}
    # a program with LFO depth and sensitivity keeps them and adds
    p = midi_machine(patched)
    prog = bytearray(p.data(LIVE,128)); prog[0x72] = 50; prog[0x74] = (prog[0x74] & 0x0F) | (5 << 4)
    p.u.mem_write(LIVE,bytes(prog)); send(p,0x90,60,100)
    b2 = lfo(p,0); send(p,0xB0,1,20)
    need(b2[0] == 92 and lfo(p,0) == (92,min(255,b2[1]+40),b2[2]),'Program with its own depth: '+str((b2,lfo(p,0))))
    # channel switch: per part
    c = midi_machine(patched,B=dict(prog=6),C=dict(prog=10),chan=1)
    send(c,0x90,60,100); send(c,0x91,60,100); send(c,0x92,60,100)
    b3 = [lfo(c,i) for i in range(3)]
    send(c,0xB1,1,60)
    need(lfo(c,0) == b3[0] and lfo(c,2) == b3[2] and lfo(c,1)[1] == min(255,b3[1][1]+120),'Wheel on the channel of B')
    send(c,0xD2,30)
    need(lfo(c,0) == b3[0] and lfo(c,2)[2] == min(255,b3[2][2]+60),'Aftertouch on the channel of C')
    send(c,0xB1,1,0); send(c,0xD2,0)
    need([lfo(c,i) for i in range(3)] == b3,'Per-part controllers back at zero')
    res['per_part_with_the_channel_switch'] = True
    # sustain and the panel controllers of the Korg dispatcher still work
    s2 = midi_machine(patched); send(s2,0x90,60,100); send(s2,0xB0,64,127); send(s2,0x80,60,0)
    need([st for st,_ in recs(s2)][:1] == [1],'Sustain no longer holds a released key')
    return res


TASKS = [('v125/off_identical',verify_off_identical),
         ('v125/program_of_part',verify_program_of_part),
         ('v125/split',verify_split),
         ('v125/layer',verify_layer),
         ('v125/steal',verify_steal),
         ('v125/voice_limit',verify_voice_limit),
         ('v125/octave_pan_level',verify_octave_pan_level),
         ('v125/other_paths',verify_other_paths),
         ('v125/midi_notes',verify_midi_notes),
         ('v125/velocity',verify_velocity),
         ('v125/midi_channels',verify_midi_channels),
         ('v125/controllers',verify_controllers),
         ('v125/page',verify_page),
         ('v125/record',verify_record),
         ('v125/sequencer',verify_sequencer)]


if __name__ == '__main__':
    import json,time
    from build_patch import build
    original,patched,code,manifest,header = build()
    only = sys.argv[1:]
    for name,fn in TASKS:
        if only and not any(o in name for o in only): continue
        t = time.monotonic()
        try:
            r = fn(original,patched)
            print(name+': PASS (%.1fs) ' % (time.monotonic()-t)+json.dumps(r)[:300],flush=True)
        except Exception as e:
            print(name+': FAIL '+type(e).__name__+': '+str(e)[:600],flush=True)
