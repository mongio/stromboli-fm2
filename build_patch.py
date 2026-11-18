"""Build the experimental 1.29 payload from the exact original Korg 1.12.

1.20 = 1.19 with the chain simplified: page CR only (ON = free chain +
recording on it, OFF = Korg chain); CH and CC (live capture) removed.

1.19 = 1.18 + chain options: CH LIBERA (free order, repeats), CC (live chain
capture), CR (recording while a chain plays, automatic WRITE). The chain code
is a second blob in flash (FF padding at 0x0020FC40).

1.18 = 1.17 + delay (DELAY 16 bit / LOFI 8 bit, mono or ping-pong, SYNC or
LIBERO) as an alternative to the reverb, on the reverb buffer; pages FX, dt, Fb.

1.17 = 1.16 (probability, conditions, quick commands, pattern probability,
HOLD, new arpeggio modes, arpeggio on MIDI OUT) + global musical scale,
humanize and random octave per pattern. One ITCM blob at 0x2000, text tables at
0x3E00, state at 0x3F00. Every patched byte is checked against its expected
original value; the bootloader sector is never changed.
"""
from pathlib import Path
import json
import struct
import sys
import hashlib
import capstone
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB,KS_MODE_V8

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
from original_image import read_original,reference_source,sum16,LAYOUT,LOGICAL_SHA

VERSION_MINOR = 28          # transport header of the install WAV
STORED_MINOR = 11           # application version byte: below 1.12 so the official Korg updater is accepted
CODE_ADDRESS = 0x2000
HOOK_ADDRESS = 0x20B7CA
HOOK_OFFSET = HOOK_ADDRESS-0x200000
ORIGINAL_HOOK = bytes.fromhex('e3884ff00008')
TEXT_ADDRESS = 0x3E00
STATE_ADDRESS = 0x3F00
ARP_BUFFER = 0x3C00          # runtime step table (ITCM RAM, not written by the image)
NAMES_ADDRESS = 0x3D80
TEXT2_ADDRESS = 0x1E00       # 1.17 messages, scale and tonic names, scale masks
NOTE_MAPS = (0x1800,0x1920)  # runtime note maps (ITCM RAM, original FF = empty)
MESSAGES2 = ['SCALA ON ','SCALA OFF','SEQ SI   ','SEQ NO   ',
             'SYNC     ','LIBERO   ','MONO     ','PING PONG',
             'REVRB ON ','REVRB OFF','DELAY ON ','DELAY OFF','LOFI ON  ','LOFI OFF ',
             'REC AUTO ','REC FISSO','STEREO   ','PAN      ','PARI     ','CALA     ','CRESCE   ']
TEXT3_ADDRESS = 0x1940       # 1.18 effect names and delay divisions
FX_NAMES = ['REVRB','DELAY','LOFI ']
DIV_NAMES = ['1-32 ','1-24 ','1-16 ','1-12 ','3-32 ','1-8  ','1-6  ','3-16 ','1-4  ']
FX_STATE = 0x3F80            # 1.18 delay state (128 bytes)
AUDIO_LITERAL = 0x023C       # ITCM literal of the audio ISR effect call
TOGGLE_LITERAL = 0x2316C     # logical offset of the SRAM veneer literal 0x2001516C (FUNC+4)
SCALE_NAMES = ['CROM','MAG ','MIN ','ARM ','DOR ','FRI ','LID ','MIS ',
               'PMA ','PMI ','BLU ','TON ','HIR ','INS ','ARA ']
SCALE_STEPS = [range(12),(0,2,4,5,7,9,11),(0,2,3,5,7,8,10),(0,2,3,5,7,8,11),
               (0,2,3,5,7,9,10),(0,1,3,5,7,8,10),(0,2,4,6,7,9,11),(0,2,4,5,7,9,10),
               (0,2,4,7,9),(0,3,5,7,10),(0,3,5,6,7,10),(0,2,4,6,8,10),
               (0,2,3,7,8),(0,1,5,7,10),(0,1,4,5,7,8,11)]
TONIC_NAMES = ['DO  ','REb ','RE  ','MIb ','MI  ','FA  ','SOLb','SOL ','LAb ','LA  ','SIb ','SI  ']
ARP_NAMES = ['tYP UPdn1','tYP UPdn2','tYP UPdn3','tYP  Conv','tYP  dIvr','tYP  PEdL','tYP  Chrd']
ITCM_TO_LOGICAL = 0x10000

COND_TEXT = ['OFF ','1-2 ','2-2 ','1-3 ','2-3 ','3-3 ',
             '1-4 ','2-4 ','3-4 ','4-4 ','1ST ','N1ST']
MESSAGES = ['ALL 100  ','ALL 75   ','ALL 50   ','ALL 25   ',
            'RANDOM   ','COPY ALL ','COND OFF ','RESET ALL','BETA 1.29',
            'HOLD ON  ','HOLD OFF ','T RIPARTE','T SPEGNE ']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text_tables():
    blob = bytearray(b'\0'*0x100)
    for i,t in enumerate(COND_TEXT):
        assert len(t) == 4
        blob[4*i:4*i+4] = t.encode()
    for i,t in enumerate(MESSAGES):
        assert len(t) == 9
        blob[0x40+12*i:0x40+12*i+9] = t.encode()
    return bytes(blob)


def scale_mask(steps):
    return sum(1 << i for i in steps)


def text2_tables():
    blob = bytearray(b'\0'*0x190)
    for i,t in enumerate(MESSAGES2):
        assert len(t) == 9
        blob[12*i:12*i+9] = t.encode()
    for i,t in enumerate(SCALE_NAMES):
        assert len(t) == 4
        blob[0x100+4*i:0x100+4*i+4] = t.encode()
    for i,t in enumerate(TONIC_NAMES):
        assert len(t) == 4
        blob[0x140+4*i:0x140+4*i+4] = t.encode()
    for i,steps in enumerate(SCALE_STEPS):
        struct.pack_into('<H',blob,0x170+2*i,scale_mask(steps))
    return bytes(blob)


def text3_tables():
    blob = b''.join(t.encode() for t in FX_NAMES+DIV_NAMES)
    assert all(len(t) == 5 for t in FX_NAMES+DIV_NAMES)
    return blob


LOFI_TABLE = 0x1A00          # 1.18 LOFI byte -> 16-bit sample decode table (256 x int16)


def lofi_decode(c):
    mant,seg = c & 15,(c >> 4) & 7
    v = ((2*mant+33) << (seg+2)) if seg else mant << 4
    return -v if c & 0x80 else v


def lofi_table():
    return struct.pack('<256h',*(lofi_decode(c) for c in range(256)))


def fx_state():
    st = bytearray(0x80)
    st[2] = 1            # SYNC
    st[4] = 7            # 1/8 dotted
    st[5] = 64           # LIBERO slider
    st[6] = 50           # feedback 50
    struct.pack_into('<I',st,0x10,6250)   # frames per 16th at 120 BPM, 50 kHz
    struct.pack_into('<I',st,0x58,0x9E3779B9)   # 1.24 LOFI hiss noise seed (never 0)
    return bytes(st)


def arp_names():
    blob = bytearray()
    for t in ARP_NAMES:
        assert len(t) == 9
        blob += t.encode()+b'\0'
    return bytes(blob)


def initial_state():
    state = bytearray(0x80)
    state[0x10] = 0xFF      # no step applied yet: next step is a fresh start
    state[0x28:0x2E] = b'\xff'*6   # no arpeggio note sent on MIDI OUT
    state[0x31] = 1                 # scale MAG preselected (scale itself off)
    state[0x37] = 1                 # 1.23 ping-pong: first loop forward
    state[0x38] = 0xFF              # 1.23 no step cached by the direction map
    state[0x3B] = 0xFF              # 1.23 no step being played (mutation idle)
    return bytes(state)


FLASH_BLOB = 0x20FC40          # 1.19 chain blob (flash, logical 0xFC40)
FLASH_LIMIT = 0x20FFF0
CHAIN_DATA = 0x1C00            # 1.19 chain list, capture list, state (ITCM)
CHAIN_NAMES = 0x1980
CHAIN_TEXT = ['OFF   ','ON    ']
SEQX_STATE = 0x3980            # 1.24 ratchet / microtiming state (128 bytes)
MULTI_STATE = 0x3900           # 1.25 parts (128 bytes)
FILT_STATE = 0x3700            # 1.26 filter and LFOs (0x160 bytes)
WAVE_STATE = 0x3880            # 1.27 waveforms: program of the voice, chain built (16 bytes)
# 1.27: operator sine lookups of the Korg kernels, ldr.w r2,[ip,#0x54] -> ldr.w r2,[r7,#0x14]
WAVE_SITES = (0x30A,0x3FC,0x4DC,0x5BA,0x69C,0x78A,0x87A,0x96A,0xA4C,0xB2A,0xC1A)
DX7_LITERAL = 0x23174          # SRAM veneer literal of the Korg DX7 voice import 0x0020F018
MOD_TABLE = 0x3A00             # 1.22 phaser allpass coefficients (65 x Q31)
MOD_STATE = 0x3B80             # 1.22 modulation state (128 bytes)
CHORUS_LITERAL = 0x0238        # ITCM literal of the audio ISR chorus call
MOD_PHASER_HZ = (100.0,2400.0)
MOD_DEFAULT = {'free':55,'res':50,'shape':0,'div':4,'stereo':1,'stages':1}


def mod_period_ms(v):
    return round(20000*0.005**(v/127))


def phaser_table():
    import math
    lo,hi = MOD_PHASER_HZ
    out = bytearray()
    for i in range(65):
        fc = lo*(hi/lo)**(i/64)
        t = math.tan(math.pi*fc/50000)
        out += struct.pack('<i',round((t-1)/(t+1)*2**31))
    return bytes(out)


def mod_state():
    d = MOD_DEFAULT
    st = bytearray(128)
    st[2] = 0; st[3] = d['stereo']; st[4] = d['div']; st[5] = d['free']
    st[6] = d['res']; st[7] = d['shape']; st[9] = d['stages']
    struct.pack_into('<I',st,0x10,85899346//mod_period_ms(d['free']))
    fb = d['res']*301
    struct.pack_into('<HH',st,0x40,fb,32767-fb//2)
    return bytes(st)


def multi_state():
    st = bytearray(128)
    # program, low, high, octave, pan, level, voices, -, low velocity, high velocity, fade
    st[0:48] = bytes([0,0,127,3,7,100,0,0,0,127,0,0,0,0,0,0])*3
    st[0x48:0x54] = struct.pack('<6H',*[25500]*6)   # gain of each DSP voice: full
    return bytes(st)


def filt_state():
    st = bytearray(0x160)
    # type, cutoff, resonance, envelope amount, A, D, S, R, key tracking, velocity
    st[0:10] = bytes([0,80,20,63,0,64,127,40,50,0])
    st[0x10:0x16] = bytes([0,60,0,0,0,2])      # LFO1: SIN, rate, depth 0, Cu, free, 4/16
    st[0x18:0x1E] = bytes([1,40,0,2,0,4])      # LFO2: TRI, rate, depth 0, AM, free, 16/16
    st[0x30:0x34] = struct.pack('<I',0x13579BDF)
    for v in range(6):
        o = 0x40+48*v
        st[o+0x1C:o+0x20] = struct.pack('<I',65536)
    return bytes(st)


def seqx_state():
    st = bytearray(128)
    for o in (0x25,0x27,0x32):
        st[o] = 0xFF            # no late / early step pending
    return bytes(st)


SRAM_BLOB = 0x200164B0         # 1.22: non-audio code (ff13 section FF padding)
SRAM_LIMIT = 0x2001B040         # 1.29: then the blocks of the patterns, 1.28: of the programs
PAT_LIVE = 0x2001B040           # 1.29 block of the pattern in use (52 bytes)
PAT_BANK = 0x2001B074           # 1.29 blocks of the 16 patterns (16 x 52 = 0x2001B3B4)
PAT_DEFAULT = bytes([0x50,1, 0,1,7,64,50, 0,0,1,4,55,50,0,1, 0x80]+[0]*35+[0xE0])
EXT_LIVE = 0x2001B3C0           # 1.28 block of the live program (48 bytes)
EXT_BANK = 0x2001B400           # 1.28 blocks of the 64 programs (64 x 48 = 0x2001C000)
EXT_DEFAULT = bytes([0x53,1, 0,80,20,63,0,64,127,40,50,0, 0,60,0,0,0,2, 1,40,0,2,0,4,
                     0,1,7,64,50, 0,0,1,4,55,50,0,1]+[0]*11)
SRAM_TO_LOGICAL = 0x1E000-0x20010000


def symbols(obj,base):
    import subprocess
    out = subprocess.run(['llvm-nm',str(obj)],check=True,capture_output=True,text=True).stdout
    table = {}
    for line in out.split('\n'):
        parts = line.split()
        if len(parts) == 3 and parts[1] in 'tT':
            table[parts[2]] = int(parts[0],16)+base
    return table


def assemble_sram(itcm_symbols):
    import subprocess,tempfile
    with tempfile.TemporaryDirectory() as tmp:
        inc = Path(tmp)/'itcm_symbols.inc'
        inc.write_text(''.join(f'.equ {n}, {v|1:#x}\n' for n,v in sorted(itcm_symbols.items())
                               if not n.startswith(('tr_','table'))))
        obj = Path(tmp)/'s.o'; binary = Path(tmp)/'s.bin'
        subprocess.run(['llvm-mc','-triple=thumbv7em-none-eabi','-mcpu=cortex-m7','-I',tmp,
                        '-filetype=obj',str(BASE/'src/fm2_129_sram.S'),'-o',str(obj)],check=True)
        relocs = subprocess.run(['llvm-readobj','-r',str(obj)],check=True,
                                capture_output=True,text=True).stdout
        if 'R_ARM' in relocs:
            raise ValueError('Unexpected relocations in the SRAM blob')
        subprocess.run(['llvm-objcopy','-O','binary','--only-section=.text',
                        str(obj),str(binary)],check=True)
        return binary.read_bytes(),symbols(obj,SRAM_BLOB)


def assemble_flash(itcm_symbols):
    import subprocess,tempfile
    with tempfile.TemporaryDirectory() as tmp:
        inc = Path(tmp)/'itcm_symbols.inc'
        inc.write_text(''.join(f'.equ {n}, {v|1:#x}\n' for n,v in sorted(itcm_symbols.items())
                               if n in ('chain_q','block_bits','load_types','pat_dirty')))
        obj = Path(tmp)/'f.o'; binary = Path(tmp)/'f.bin'
        subprocess.run(['llvm-mc','-triple=thumbv7em-none-eabi','-mcpu=cortex-m7','-I',tmp,
                        '-filetype=obj',str(BASE/'src/fm2_129_flash.S'),'-o',str(obj)],check=True)
        relocs = subprocess.run(['llvm-readobj','-r',str(obj)],check=True,
                                capture_output=True,text=True).stdout
        if 'R_ARM' in relocs:
            raise ValueError('Unexpected relocations in the flash blob')
        subprocess.run(['llvm-objcopy','-O','binary','--only-section=.text',
                        str(obj),str(binary)],check=True)
        return binary.read_bytes(),symbols(obj,FLASH_BLOB)


def assemble():
    # LLVM integrated assembler (llvm-mc). Position independent: the blob uses
    # only PC-relative branches/literals and absolute addresses from literals.
    import subprocess,tempfile
    global ITCM_SYMBOLS
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp)/'a.o'; binary = Path(tmp)/'a.bin'
        subprocess.run(['llvm-mc','-triple=thumbv7em-none-eabi','-mcpu=cortex-m7',
                        '-filetype=obj',str(BASE/'src/fm2_129.S'),'-o',str(obj)],check=True)
        relocs = subprocess.run(['llvm-readobj','-r',str(obj)],check=True,
                                capture_output=True,text=True).stdout
        if 'R_ARM' in relocs:
            raise ValueError('Unexpected relocations: blob must be self-contained')
        subprocess.run(['llvm-objcopy','-O','binary','--only-section=.text',
                        str(obj),str(binary)],check=True)
        ITCM_SYMBOLS = symbols(obj,0x2000)
        return binary.read_bytes()


def hook_branch(source,target,length):
    ks = Ks(KS_ARCH_ARM,KS_MODE_THUMB)
    body = bytes(ks.asm(f'b.w #{target:#x}'+('; nop' if length == 6 else ''),addr=source)[0])
    if len(body) != length:
        raise ValueError('Hook branch has unexpected length')
    return body


def thumb_bl(source,target):
    # Encode BL independently of the assembler (T1 encoding, +-16 MiB).
    off = target-(source+4)
    if not -(1 << 24) <= off < (1 << 24):
        raise ValueError('BL out of range')
    imm = off & 0x1FFFFFF
    s_ = (imm >> 24) & 1; i1 = (imm >> 23) & 1; i2 = (imm >> 22) & 1
    imm10 = (imm >> 12) & 0x3FF; imm11 = (imm >> 1) & 0x7FF
    j1 = (~(i1 ^ s_)) & 1; j2 = (~(i2 ^ s_)) & 1
    hw1 = 0xF000 | (s_ << 10) | imm10
    hw2 = 0xD000 | (j1 << 13) | (j2 << 11) | imm11
    body = struct.pack('<HH',hw1,hw2)
    md = capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS)
    ins = list(md.disasm(body,source))
    if len(ins) != 1 or ins[0].mnemonic != 'bl' or int(ins[0].op_str.lstrip('#'),16) != target:
        raise ValueError('BL encoding check failed')
    return body


def check_adr(blob,base,syms):
    """ADR silently wraps when the label is more than 4095 bytes away
    (llvm-mc 18): every PC-relative address must be a symbol."""
    md = capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS)
    md.skipdata = True
    targets = set(syms.values())
    for i in md.disasm(blob,base):
        ops = i.op_str.replace(' ','').split(',')
        pc = (i.address+4) & ~3
        # backward ADR (the case that wraps); data decoded as code is skipped
        # by accepting only targets that are labels
        if i.mnemonic in ('adr','adr.w') and int(ops[-1].lstrip('#'),0) < 0:
            t = pc+int(ops[-1].lstrip('#'),0)
        elif i.mnemonic == 'subw' and len(ops) == 3 and ops[1] == 'pc':
            t = pc-int(ops[2].lstrip('#'),0)
        else:
            continue
        if t not in targets:
            raise ValueError('ADR out of range at %x (%s %s)' % (i.address,i.mnemonic,i.op_str))


def md_sram_table(blob):
    md = capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS)
    md.skipdata = True
    return md.disasm(blob[:172],SRAM_BLOB)


def build():
    original = read_original(reference_source(BASE/'reference'))
    logical = original['logical']
    if sha(logical) != LOGICAL_SHA:
        raise ValueError('Original image mismatch')
    code = assemble()
    if CODE_ADDRESS+len(code) > FILT_STATE:
        raise ValueError('ITCM code overlaps the sequencer state')
    global SRAM_SYMBOLS
    sram,SRAM_SYMBOLS = assemble_sram(ITCM_SYMBOLS)
    if SRAM_BLOB+len(sram) > SRAM_LIMIT:
        raise ValueError('SRAM blob too large')
    sl = SRAM_BLOB+SRAM_TO_LOGICAL
    if logical[sl:SRAM_LIMIT+SRAM_TO_LOGICAL] != b'\xff'*(SRAM_LIMIT-SRAM_BLOB):
        raise ValueError('SRAM blob area is not original FF padding')
    check_adr(sram,SRAM_BLOB,SRAM_SYMBOLS)
    stab = list(md_sram_table(sram))
    if len(stab) != 43 or any(i.size != 4 or i.mnemonic not in ('b.w','b') for i in stab):
        raise ValueError('SRAM entry table is not forty-three B.W instructions')
    # Jump table must be eight 4-byte B.W instructions.
    md = capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS)
    md.skipdata = True
    table = list(md.disasm(code[:172],CODE_ADDRESS))
    if len(table) != 43 or any(i.size != 4 or i.mnemonic not in ('b.w','b') for i in table):
        raise ValueError('Entry table is not forty-three B.W instructions')
    additions = [(CODE_ADDRESS,code),(NAMES_ADDRESS,arp_names()),(TEXT_ADDRESS,text_tables()),
                 (STATE_ADDRESS,initial_state()),
                 (TEXT2_ADDRESS,text2_tables()),
                 (TEXT3_ADDRESS,text3_tables()),(FX_STATE,fx_state()),
                 (LOFI_TABLE,lofi_table()),
                 (CHAIN_DATA,bytes(0x110)),
                 (CHAIN_NAMES,''.join(CHAIN_TEXT).encode()),
                 (MOD_TABLE,phaser_table()),(MOD_STATE,mod_state()),
                 (SEQX_STATE,seqx_state()),(MULTI_STATE,multi_state()),(FILT_STATE,filt_state()),
                 (WAVE_STATE,bytes(16))]
    lo,hi = ITCM_TO_LOGICAL+NOTE_MAPS[0],ITCM_TO_LOGICAL+NOTE_MAPS[1]
    if logical[lo:hi] != b'\xff'*(hi-lo):
        raise ValueError('Note map area is not original FF padding')
    lo = ITCM_TO_LOGICAL+ARP_BUFFER
    if logical[lo:lo+0x100] != b'\xff'*0x100:
        raise ValueError('Arpeggio buffer area is not original FF padding')
    hooks = [
        # sequencer step decision
        (HOOK_OFFSET,ORIGINAL_HOOK,hook_branch(HOOK_ADDRESS,0x2000,6)),
        # transport start (loop counter reset)
        (0x90C0,bytes.fromhex('f8b51646'),hook_branch(0x2090C0,0x2004,4)),
        # keyboard, button and encoder veneer literals
        (0xFC1C,bytes.fromhex('0d180120'),struct.pack('<I',0x2009)),
        (0xFAA4,bytes.fromhex('21130120'),struct.pack('<I',0x200D)),
        (0xFB24,bytes.fromhex('21150120'),struct.pack('<I',0x2019)),
        # ADC parameter, text request and LED prologues
        (0x59D0,bytes.fromhex('70b586b00446'),hook_branch(0x2059D0,0x2010,6)),
        (0x591C,bytes.fromhex('7fb51d460023'),hook_branch(0x20591C,0x2014,6)),
        (0x548C,bytes.fromhex('272910b4'),hook_branch(0x20548C,0x201C,4)),
        # voice note-on (HOLD: TASTO RIPARTE/SPEGNE)
        (0xA78C,bytes.fromhex('2de9f04f'),hook_branch(0x20A78C,0x2020,4)),
        # arpeggiator tick (new modes: generated step table)
        (0xC40C,bytes.fromhex('2de9f041'),hook_branch(0x20C40C,0x2024,4)),
        (0xBDFC,bytes.fromhex('f8b50446'),hook_branch(0x20BDFC,0x2028,4)),
        # arpeggio notes on MIDI OUT
        (0x97E4,bytes.fromhex('f8b51746'),hook_branch(0x2097E4,0x202C,4)),
        (0xC1F4,bytes.fromhex('2de9f04f'),hook_branch(0x20C1F4,0x2030,4)),
        (0x7F2C,bytes.fromhex('2de9f04f'),hook_branch(0x207F2C,0x2034,4)),
        (0xAA8E,bytes.fromhex('fdf7a1f8'),thumb_bl(0x20AA8E,0x2038)),
        (0xA732,bytes.fromhex('fdf74ffa'),thumb_bl(0x20A732,0x2038)),
        # scales: keyboard note-on/off, MIDI DIN/USB note-on/off, sequencer slot
        (0xAA8A,bytes.fromhex('0534e0b2'),thumb_bl(0x20AA8A,0x203C)),
        (0xAACA,bytes.fromhex('0534e6b2'),thumb_bl(0x20AACA,0x2040)),
        (0xAB2C,bytes.fromhex('38b50446'),hook_branch(0x20AB2C,0x2044,4)),
        (0xAB64,bytes.fromhex('38b50146'),hook_branch(0x20AB64,0x2048,4)),
        (0xABC0,bytes.fromhex('38b50446'),hook_branch(0x20ABC0,0x204C,4)),
        (0xABF8,bytes.fromhex('38b50146'),hook_branch(0x20ABF8,0x2050,4)),
        (0xBA6E,bytes.fromhex('07f82400'),thumb_bl(0x20BA6E,0x2054)),
        # 1.23 pattern direction: clock -> step routine and step LED
        (0x903E,thumb_bl(0x20903E,0x20B7BE),thumb_bl(0x20903E,0x2064)),
        (0x8E42,thumb_bl(0x208E42,0x20FC10),thumb_bl(0x208E42,0x2068)),
        # 1.24 microtiming / ratchet: end of every clock tick, step boundary release
        (0x9096,bytes.fromhex('08f1ff38'),thumb_bl(0x209096,0x206C)),
        (0x8E0C,thumb_bl(0x208E0C,0x20BB50),thumb_bl(0x208E0C,0x2070)),
        # 1.25 parts: voices per note, part of each voice, program / octave / pan / level of the voice
        (0x9574,bytes.fromhex('2de9f04f'),hook_branch(0x209574,0x2074,4)),
        (0x93FE,bytes.fromhex('2de9f74f'),hook_branch(0x2093FE,0x2078,4)),
        (0x9746,thumb_bl(0x209746,0x20E814),thumb_bl(0x209746,0x207C)),
        (0x9488,thumb_bl(0x209488,0x20E814),thumb_bl(0x209488,0x2080)),
        (0xE6F0,thumb_bl(0x20E6F0,0x20E518),thumb_bl(0x20E6F0,0x2084)),
        (0xE79E,thumb_bl(0x20E79E,0x20DF14),thumb_bl(0x20E79E,0x2088)),
        (0x9870,bytes.fromhex('2de9f84f'),hook_branch(0x209870,0x208C,4)),
        # 1.26 filter: per voice in the Korg voice loop (ITCM), key-off of the voice
        (ITCM_TO_LOGICAL+0x1266,bytes.fromhex('dce90e23'),thumb_bl(0x1266,0x2090)),
        (0xE7EA,thumb_bl(0x20E7EA,0x204580),thumb_bl(0x20E7EA,0x2094)),
        # 1.27 waveforms: every operator reads its own table pointer
        *[(ITCM_TO_LOGICAL+site,bytes.fromhex('dcf85420'),bytes.fromhex('d7f81420')) for site in WAVE_SITES],
        # 1.18 delay: audio ISR effect literal and FUNC+4 veneer literal
        (ITCM_TO_LOGICAL+AUDIO_LITERAL,struct.pack('<I',0x1461),struct.pack('<I',0x2059)),
        (TOGGLE_LITERAL,struct.pack('<I',0x20C8B7),struct.pack('<I',0x205D)),
        # 1.22 modulation effect: audio ISR chorus literal
        (ITCM_TO_LOGICAL+CHORUS_LITERAL,struct.pack('<I',0x12AD),struct.pack('<I',0x2061))]
    # 1.19 chain blob in flash
    flash,flash_symbols = assemble_flash(SRAM_SYMBOLS)
    if FLASH_BLOB+len(flash) > FLASH_LIMIT:
        raise ValueError('Flash blob too large')
    fl = FLASH_BLOB-0x200000
    if logical[fl-0x18:FLASH_LIMIT-0x200000] != b'\xff'*(FLASH_LIMIT-0x200000-fl+0x18):
        raise ValueError('Flash blob area is not original FF padding')
    ft = list(md.disasm(flash[:32],FLASH_BLOB))
    if len(ft) != 8 or any(i.size != 4 for i in ft):
        raise ValueError('Flash entry table is not eight B.W instructions')
    F = lambda n: FLASH_BLOB+4*n
    hooks += [
        (0x22FC4,struct.pack('<I',0x20C611),struct.pack('<I',F(0)|1)),     # chain selection veneer
        (0x9006,bytes.fromhex('03f0d3fa'),thumb_bl(0x209006,F(1))),        # chain advance
        (0x900C,bytes.fromhex('fff778fc'),thumb_bl(0x20900C,F(2))),        # chain pattern load
        (0xFA6C,struct.pack('<I',0x20010B11),struct.pack('<I',F(4)|1)),    # transport change veneer
        (0x22FBC,struct.pack('<I',0x208C5D),struct.pack('<I',SRAM_SYMBOLS['chain_disp']|1)),  # pattern readout veneer
        (0xC666,bytes.fromhex('01f083fa'),thumb_bl(0x20C666,F(5))),        # REC check in the selection
        # 1.20: chain check of the panel, REC at the end of a motion loop, MIDI Program Change
        (0x230E4,struct.pack('<I',0x20C5D3),struct.pack('<I',SRAM_SYMBOLS['chain_q']|1)),
        (0x9062,bytes.fromhex('fff799fa'),thumb_bl(0x209062,F(6))),
        (0x22F64,struct.pack('<I',0x207D99),struct.pack('<I',SRAM_SYMBOLS['midi_multi']|1)),
        # 1.27: DX7 voice import clears the waves first
        (DX7_LITERAL,struct.pack('<I',0x20F019),struct.pack('<I',SRAM_SYMBOLS['wave_dx7']|1)),
        # 1.28: wave = parameter 0x16 of the operator in the Korg EDIT: step limit
        # 0x15 -> 0x16, value getters (live, stored), setter, readout
        (0x20012996+SRAM_TO_LOGICAL,bytes.fromhex('1529'),bytes.fromhex('1629')),
        (0x2001299A+SRAM_TO_LOGICAL,bytes.fromhex('1521'),bytes.fromhex('1621')),
        (0x20012F78+SRAM_TO_LOGICAL,bytes.fromhex('0379062b'),hook_branch(0x20012F78,SRAM_SYMBOLS['edit_get_live'],4)),
        (0x2001302C+SRAM_TO_LOGICAL,bytes.fromhex('0379062b'),hook_branch(0x2001302C,SRAM_SYMBOLS['edit_get_stored'],4)),
        (0x20012A2C+SRAM_TO_LOGICAL,bytes.fromhex('08b50346'),hook_branch(0x20012A2C,SRAM_SYMBOLS['edit_set'],4)),
        (0x200101D4+SRAM_TO_LOGICAL,bytes.fromhex('38b50446'),hook_branch(0x200101D4,SRAM_SYMBOLS['edit_text'],4)),
        # 1.28: engine = parameter 0x27 of ALL (step limit 0x26 -> 0x27), kernel of the voice
        (0x20012982+SRAM_TO_LOGICAL,bytes.fromhex('2629'),bytes.fromhex('3d29')),
        (0x20012986+SRAM_TO_LOGICAL,bytes.fromhex('2621'),bytes.fromhex('3d21')),
        (0xDFA8,thumb_bl(0x20DFA8,0x204578),thumb_bl(0x20DFA8,0x209C)),
        # 1.28: STROMBOLI block of the program (filter, effects): load, save,
        # journal sector build and load
        (0xE490,thumb_bl(0x20E490,0x200414),thumb_bl(0x20E490,0x20A0)),
        (0xEF36,thumb_bl(0x20EF36,0x207838),thumb_bl(0x20EF36,0x20A4)),
        (0xF346,thumb_bl(0x20F346,0x207838),thumb_bl(0x20F346,0x20A8)),
        (0x20013B0A+SRAM_TO_LOGICAL,hook_branch(0x20013B0A,0x20015420,4),hook_branch(0x20013B0A,SRAM_SYMBOLS['ext_sector'],4)),
        (0x20013982+SRAM_TO_LOGICAL,thumb_bl(0x20013982,0x20015420),thumb_bl(0x20013982,SRAM_SYMBOLS['ext_sector_load'])),
        # 1.29: STROMBOLI block of the pattern (effects, filter motion): WRITE,
        # journal sector build and load; FUNC + 3 / 4 rotation; motion clear
        (0xFA94,struct.pack('<I',0x200134ED),struct.pack('<I',SRAM_SYMBOLS['pat_write']|1)),
        (0x20013ABC+SRAM_TO_LOGICAL,hook_branch(0x20013ABC,0x20015420,4),hook_branch(0x20013ABC,SRAM_SYMBOLS['pat_sector'],4)),
        (0x200138D8+SRAM_TO_LOGICAL,thumb_bl(0x200138D8,0x20014A88),thumb_bl(0x200138D8,SRAM_SYMBOLS['pat_sector_load'])),
        (0x232F4,struct.pack('<I',0x20C88B),struct.pack('<I',SRAM_SYMBOLS['rot_mod']|1)),
        (0x2316C,struct.pack('<I',0x20C8B7),struct.pack('<I',SRAM_SYMBOLS['rot_fx']|1)),
        (0x23254,struct.pack('<I',0x20A225),struct.pack('<I',SRAM_SYMBOLS['pm_clear']|1)),
        (0x20014AC8+SRAM_TO_LOGICAL,thumb_bl(0x20014AC8,0x200134EC),thumb_bl(0x20014AC8,SRAM_SYMBOLS['pat_sysex'])),
        (0x20014B10+SRAM_TO_LOGICAL,thumb_bl(0x20014B10,0x20015190),thumb_bl(0x20014B10,SRAM_SYMBOLS['alg_kernel'])),
        (0x20014F74+SRAM_TO_LOGICAL,struct.pack('<I',0x2058D7),struct.pack('<I',SRAM_SYMBOLS['led_filter']|1))]+[
        # 1.20: effect type from the pattern at every pattern load
        (site-0x200000,thumb_bl(site,0x208900),thumb_bl(site,F(7)))
        for site in (0x208C7C,0x208CCE,0x209144,0x2092AE)]
    patched = bytearray(logical)
    patched[fl:fl+len(flash)] = flash
    patched[sl:sl+len(sram)] = sram
    # 1.28: blocks of the live program and of the 64 programs, defaults
    el = EXT_LIVE+SRAM_TO_LOGICAL
    eb = EXT_BANK+SRAM_TO_LOGICAL
    if logical[el:0x2001C000+SRAM_TO_LOGICAL] != b'\xff'*(0x2001C000-EXT_LIVE) or EXT_BANK+64*48 != 0x2001C000:
        raise ValueError('Program block area is not original FF padding')
    patched[el:el+48] = EXT_DEFAULT
    # 1.29: blocks of the pattern in use and of the 16 patterns, defaults
    pl = PAT_LIVE+SRAM_TO_LOGICAL
    if logical[pl:el] != b'\xff'*(EXT_LIVE-PAT_LIVE) or PAT_BANK+16*52 > EXT_LIVE:
        raise ValueError('Pattern block area is not original FF padding')
    if (sum(PAT_DEFAULT[:51]) & 0xFF) ^ 0x5A != PAT_DEFAULT[51]:
        raise ValueError('Pattern default check')
    patched[pl:pl+52] = PAT_DEFAULT
    patched[pl+52:pl+52+16*52] = PAT_DEFAULT*16
    patched[eb:eb+64*48] = EXT_DEFAULT*64
    for at,body in additions:
        lo = ITCM_TO_LOGICAL+at
        if logical[lo:lo+len(body)] != b'\xff'*len(body):
            raise ValueError(f'ITCM slot {at:#x} is not original FF padding')
        patched[lo:lo+len(body)] = body
    spans = sorted((a,a+len(b)) for a,b in additions)
    for (a0,a1),(b0,b1) in zip(spans,spans[1:]):
        if a1 > b0:
            raise ValueError('ITCM additions overlap')
    for at,before,after in hooks:
        if logical[at:at+len(before)] != before or len(before) != len(after):
            raise ValueError('Hook preimage mismatch at '+hex(at))
        patched[at:at+len(after)] = after
    patched[0x420D] = STORED_MINOR
    checksum_changes = []
    for tag,start,size,header_offset in LAYOUT:
        section = bytes(patched[start:start+size])
        if section != logical[start:start+size]:
            at = start+header_offset+14
            old = struct.unpack_from('<H',patched,at)[0]
            new = (old-sum16(section)) & 65535
            struct.pack_into('<H',patched,at,new)
            checksum_changes.append({'tag':hex(tag),'offset':hex(at),'before':old,'after':new})
        if sum16(patched[start:start+size]):
            raise ValueError('Section checksum failed after building')
    if patched[:0x4000] != logical[:0x4000]:
        raise ValueError('Bootloader sector changed')
    allowed = {0x420D}
    allowed.update(range(fl,fl+len(flash)))
    allowed.update(range(sl,sl+len(sram)))
    allowed.update(range(PAT_LIVE+SRAM_TO_LOGICAL,0x2001C000+SRAM_TO_LOGICAL))
    for at,body in additions:
        allowed.update(range(ITCM_TO_LOGICAL+at,ITCM_TO_LOGICAL+at+len(body)))
    for at,before,after in hooks:
        allowed.update(range(at,at+len(after)))
    for item in checksum_changes:
        at = int(item['offset'],16); allowed.update([at,at+1])
    changed = [i for i,(o,n) in enumerate(zip(logical,patched)) if o != n]
    if not set(changed) <= allowed:
        raise ValueError('Unexpected image changes')
    out = BASE/'build'; out.mkdir(exist_ok=True)
    (out/'fm2_129_code_ARM.bin').write_bytes(code)
    (out/'candidate_logical_1_29_BETA.bin').write_bytes(patched)
    listing = '\n'.join(f'{i.address:08X}  {i.bytes.hex(" "):12}  {i.mnemonic:8} {i.op_str}'
                        for i in md.disasm(code,CODE_ADDRESS))
    (out/'fm2_129_code.asm').write_text(listing+'\n')
    report = {'status':'BUILT_OFFLINE_EXPERIMENTAL_NOT_HARDWARE_VALIDATED',
              'source_firmware':'original 1.12',
              'application_version':f'1.{VERSION_MINOR} beta experimental, not a Korg release',
              'stored_version_byte':f'1.{STORED_MINOR} (REC shows 1.11; the official Korg 1.12 updater is accepted)',
              'original_logical_sha256':sha(logical),'patched_logical_sha256':sha(patched),
              'code_bytes':len(code),'code_range':[hex(CODE_ADDRESS),hex(CODE_ADDRESS+len(code))],
              'sram_code_bytes':len(sram),'sram_range':[hex(SRAM_BLOB),hex(SRAM_BLOB+len(sram))],
              'text_tables':hex(TEXT_ADDRESS),'state':hex(STATE_ADDRESS),
              'changed_byte_count':len(changed),
              'hooks':[{'offset':hex(at),'before':b.hex(),'after':a.hex()} for at,b,a in hooks],
              'checksum_changes':checksum_changes,'bootloader_sector_byte_identical':True,
              'format':'PRB2 in pattern reserved bytes 1888..1915; PRB1 (1.13) read and converted on edit','hold':'virtual damper bit 0x04 in voice manager 0x20003C6C+0xE2/0xE3',
              'scales':'global, not saved; note maps 0x1800..0x191F; tables 0x1E00',
              'delay':'alternative to the reverb on its buffer 0x20029B00 (48 KiB); state 0x3F80; ISR literal 0x023C; FUNC+4 veneer 0x2001516C',
              'chain':'flash blob 0x0020FC40; ITCM state 0x1D00, lists 0x1C00/0x1C80; hooks 0x20014FC4, 0x00209006, 0x0020900C, 0x0020FA6C, 0x20014FBC, 0x0020C666',
              'all_unchanged_image_bytes_compared':True}
    (out/'patch_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    header = bytearray(original['header']); header[22:24] = bytes([1,VERSION_MINOR])
    return logical,bytes(patched),code,report,bytes(header)


if __name__ == '__main__':
    print(json.dumps(build()[3],indent=2))
