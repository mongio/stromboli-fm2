"""Build the experimental 1.19 payload from the exact original Korg 1.12.

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
from original_image import read_original,sum16,LAYOUT,LOGICAL_SHA

VERSION_MINOR = 19          # transport header of the install WAV
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
             'REVRB ON ','REVRB OFF','DELAY ON ','DELAY OFF','LOFI ON  ','LOFI OFF ']
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
            'RANDOM   ','COPY ALL ','COND OFF ','RESET ALL','BETA 1.19',
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
    return bytes(state)


FLASH_BLOB = 0x20FC40          # 1.19 chain blob (flash, logical 0xFC40)
FLASH_LIMIT = 0x20FFF0
CHAIN_DATA = 0x1C00            # 1.19 chain list, capture list, state (ITCM)
CHAIN_NAMES = 0x1980
CHAIN_TEXT = ['KORG  ','LIBERA','OFF   ','ON    ','REC   ']


def symbols(obj,base):
    import subprocess
    out = subprocess.run(['llvm-nm',str(obj)],check=True,capture_output=True,text=True).stdout
    table = {}
    for line in out.split('\n'):
        parts = line.split()
        if len(parts) == 3 and parts[1] in 'tT':
            table[parts[2]] = int(parts[0],16)+base
    return table


def assemble_flash(itcm_symbols):
    import subprocess,tempfile
    with tempfile.TemporaryDirectory() as tmp:
        inc = Path(tmp)/'itcm_symbols.inc'
        inc.write_text(''.join(f'.equ {n}, {v|1:#x}\n' for n,v in sorted(itcm_symbols.items())
                               if n in ('chain_msg',)))
        obj = Path(tmp)/'f.o'; binary = Path(tmp)/'f.bin'
        subprocess.run(['llvm-mc','-triple=thumbv7em-none-eabi','-mcpu=cortex-m7','-I',tmp,
                        '-filetype=obj',str(BASE/'src/fm2_119_flash.S'),'-o',str(obj)],check=True)
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
                        '-filetype=obj',str(BASE/'src/fm2_119.S'),'-o',str(obj)],check=True)
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


def build():
    original = read_original(BASE/'reference/volca_fm2_updater_0112.zip')
    logical = original['logical']
    if sha(logical) != LOGICAL_SHA:
        raise ValueError('Original image mismatch')
    code = assemble()
    if CODE_ADDRESS+len(code) > ARP_BUFFER:
        raise ValueError('Code overlaps the arpeggio buffer')
    # Jump table must be eight 4-byte B.W instructions.
    md = capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS)
    md.skipdata = True
    table = list(md.disasm(code[:96],CODE_ADDRESS))
    if len(table) != 24 or any(i.size != 4 or i.mnemonic not in ('b.w','b') for i in table):
        raise ValueError('Entry table is not twenty-four B.W instructions')
    additions = [(CODE_ADDRESS,code),(NAMES_ADDRESS,arp_names()),(TEXT_ADDRESS,text_tables()),
                 (STATE_ADDRESS,initial_state()),
                 (TEXT2_ADDRESS,text2_tables()),
                 (TEXT3_ADDRESS,text3_tables()),(FX_STATE,fx_state()),
                 (LOFI_TABLE,lofi_table()),
                 (CHAIN_DATA,bytes(0x110)),
                 (CHAIN_NAMES,''.join(CHAIN_TEXT).encode())]
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
        # 1.18 delay: audio ISR effect literal and FUNC+4 veneer literal
        (ITCM_TO_LOGICAL+AUDIO_LITERAL,struct.pack('<I',0x1461),struct.pack('<I',0x2059)),
        (TOGGLE_LITERAL,struct.pack('<I',0x20C8B7),struct.pack('<I',0x205D))]
    # 1.19 chain blob in flash
    flash,flash_symbols = assemble_flash(ITCM_SYMBOLS)
    if FLASH_BLOB+len(flash) > FLASH_LIMIT:
        raise ValueError('Flash blob too large')
    fl = FLASH_BLOB-0x200000
    if logical[fl-0x18:FLASH_LIMIT-0x200000] != b'\xff'*(FLASH_LIMIT-0x200000-fl+0x18):
        raise ValueError('Flash blob area is not original FF padding')
    ft = list(md.disasm(flash[:24],FLASH_BLOB))
    if len(ft) != 6 or any(i.size != 4 for i in ft):
        raise ValueError('Flash entry table is not six B.W instructions')
    F = lambda n: FLASH_BLOB+4*n
    hooks += [
        (0x22FC4,struct.pack('<I',0x20C611),struct.pack('<I',F(0)|1)),     # chain selection veneer
        (0x9006,bytes.fromhex('03f0d3fa'),thumb_bl(0x209006,F(1))),        # chain advance
        (0x900C,bytes.fromhex('fff778fc'),thumb_bl(0x20900C,F(2))),        # chain pattern load
        (0x8E30,bytes.fromhex('94f90b30'),thumb_bl(0x208E30,F(3))),        # step wrap (capture)
        (0xFA6C,struct.pack('<I',0x20010B11),struct.pack('<I',F(4)|1)),    # transport change veneer
        (0x22FBC,struct.pack('<I',0x208C5D),struct.pack('<I',ITCM_SYMBOLS['chain_disp']|1)),  # pattern readout veneer
        (0xC666,bytes.fromhex('01f083fa'),thumb_bl(0x20C666,F(5)))]        # REC check in the selection
    patched = bytearray(logical)
    patched[fl:fl+len(flash)] = flash
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
    (out/'fm2_119_code_ARM.bin').write_bytes(code)
    (out/'candidate_logical_1_19_BETA.bin').write_bytes(patched)
    listing = '\n'.join(f'{i.address:08X}  {i.bytes.hex(" "):12}  {i.mnemonic:8} {i.op_str}'
                        for i in md.disasm(code,CODE_ADDRESS))
    (out/'fm2_119_code.asm').write_text(listing+'\n')
    report = {'status':'BUILT_OFFLINE_EXPERIMENTAL_NOT_HARDWARE_VALIDATED',
              'source_firmware':'original 1.12',
              'application_version':f'1.{VERSION_MINOR} beta experimental, not a Korg release',
              'stored_version_byte':f'1.{STORED_MINOR} (REC shows 1.11; the official Korg 1.12 updater is accepted)',
              'original_logical_sha256':sha(logical),'patched_logical_sha256':sha(patched),
              'code_bytes':len(code),'code_range':[hex(CODE_ADDRESS),hex(CODE_ADDRESS+len(code))],
              'text_tables':hex(TEXT_ADDRESS),'state':hex(STATE_ADDRESS),
              'changed_byte_count':len(changed),
              'hooks':[{'offset':hex(at),'before':b.hex(),'after':a.hex()} for at,b,a in hooks],
              'checksum_changes':checksum_changes,'bootloader_sector_byte_identical':True,
              'format':'PRB2 in pattern reserved bytes 1888..1915; PRB1 (1.13) read and converted on edit','hold':'virtual damper bit 0x04 in voice manager 0x20003C6C+0xE2/0xE3',
              'scales':'global, not saved; note maps 0x1800..0x191F; tables 0x1E00',
              'delay':'alternative to the reverb on its buffer 0x20029B00 (48 KiB); state 0x3F80; ISR literal 0x023C; FUNC+4 veneer 0x2001516C',
              'chain':'flash blob 0x0020FC40; ITCM state 0x1D00, lists 0x1C00/0x1C80; hooks 0x20014FC4, 0x00209006, 0x0020900C, 0x00208E30, 0x0020FA6C, 0x20014FBC, 0x0020C666',
              'all_unchanged_image_bytes_compared':True}
    (out/'patch_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    header = bytearray(original['header']); header[22:24] = bytes([1,VERSION_MINOR])
    return logical,bytes(patched),code,report,bytes(header)


if __name__ == '__main__':
    print(json.dumps(build()[3],indent=2))
