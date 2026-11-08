"""PRB1 pattern extension: no change to original 1920-byte framing."""
import struct

SIZE = 1920
OFFSET = 1888
MAGIC = b'PRB1'
GUARD = 0xCEBDADAF


def fnv1a(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def valid_pattern(data):
    return (len(data) == SIZE and data[:6] == b'PTST\xe8N'
            and data[-4:] == b'PTED')


PRB2_TAG = 0xA2
PRB3_TAG = 0xA3


def prb2_digest(block26):
    value = fnv1a(block26)
    value ^= value >> 16
    return value & 0xFFFF


def get_prb2(pattern):
    """(probabilities, conditions, scale, valid) of a PRB2 (1.14/1.15) or PRB3 (1.16) block."""
    if not valid_pattern(pattern):
        raise ValueError('Expected an original-format 1920-byte FM2 pattern')
    b = pattern[OFFSET:OFFSET+28]
    probs = [x & 0x7F for x in b[1:17]]
    conds = [(b[17+i//2] >> (4*(i & 1))) & 15 for i in range(16)]
    scale = b[25]
    ok = (b[0] in (PRB2_TAG,PRB3_TAG) and all(x <= 100 for x in probs) and all(c <= 11 for c in conds)
          and scale <= 100 and prb2_digest(b[:26]) == struct.unpack_from('<H',b,26)[0])
    if not ok:
        return [100]*16,[0]*16,100,False
    return probs,conds,scale,True


def get_prb3_fields(pattern):
    """(ext arpeggio mode, humanize, octave) from bit 7 of steps 1-4, 5-8, 9-12; 0 without PRB3."""
    probs,_,_,ok = get_prb2(pattern)
    b = pattern[OFFSET:OFFSET+28]
    if not ok or b[0] != PRB3_TAG:
        return 0,0,0
    f = [sum(((b[1+4*k+i] >> 7) & 1) << i for i in range(4)) for k in range(3)]
    return tuple(f)


def set_prb2(pattern,probs,conds=None,scale=100,tag=PRB2_TAG,fields=(0,0,0)):
    if not valid_pattern(pattern):
        raise ValueError('Expected an original-format 1920-byte FM2 pattern')
    conds = [0]*16 if conds is None else list(conds)
    probs = list(probs)
    if (len(probs) != 16 or len(conds) != 16 or any(not 0 <= x <= 100 for x in probs)
            or any(not 0 <= c <= 11 for c in conds) or not 0 <= scale <= 100):
        raise ValueError('16 probabilities 0..100, 16 conditions 0..11, scale 0..100')
    raw = list(probs)
    if tag == PRB3_TAG:
        for k,v in enumerate(fields):
            for i in range(4):
                raw[4*k+i] |= ((v >> i) & 1) << 7
    b = bytearray(bytes([tag]) + bytes(raw) +
                  bytes(conds[2*i] | (conds[2*i+1] << 4) for i in range(8)) + bytes([scale]))
    b += struct.pack('<H',prb2_digest(bytes(b)))
    result = bytearray(pattern)
    result[OFFSET:OFFSET+28] = b
    return bytes(result)


def set_prb3(pattern,probs,conds=None,scale=100,ext=0,humanize=0,octave=0):
    return set_prb2(pattern,probs,conds,scale,PRB3_TAG,(ext,humanize,octave))


def get_profile(pattern):
    """Probabilities as seen by the 1.14 firmware: PRB2 first, then PRB1."""
    probs,_,_,ok = get_prb2(pattern)
    if ok:
        return probs,True
    return get_prb1(pattern)


def get_prb1(pattern):
    if not valid_pattern(pattern):
        raise ValueError('Expected an original-format 1920-byte FM2 pattern')
    block = pattern[OFFSET:OFFSET+28]
    if block[:4] != MAGIC or struct.unpack_from('<I',block,20)[0] != GUARD:
        return [100]*16,False
    values = list(block[4:20])
    if any(x > 100 for x in values) or fnv1a(block[4:20]) != struct.unpack_from('<I',block,24)[0]:
        return [100]*16,False
    return values,True


def set_profile(pattern,percentages):
    if not valid_pattern(pattern):
        raise ValueError('Expected an original-format 1920-byte FM2 pattern')
    values = list(percentages)
    if len(values) != 16 or any(type(x) is not int or not 0 <= x <= 100 for x in values):
        raise ValueError('Exactly 16 integer percentages in range 0..100 are required')
    result = bytearray(pattern)
    result[OFFSET:OFFSET+28] = (MAGIC + bytes(values) +
        struct.pack('<II',GUARD,fnv1a(bytes(values))))
    return bytes(result)


def clear_profile(pattern):
    if not valid_pattern(pattern):
        raise ValueError('Expected an original-format 1920-byte FM2 pattern')
    result = bytearray(pattern)
    result[OFFSET:OFFSET+28] = bytes(28)
    return bytes(result)


def pack7(data):
    out = bytearray()
    for start in range(0,len(data),7):
        group = data[start:start+7]
        out.append(sum((value >> 7) << index for index,value in enumerate(group)))
        out.extend(value & 127 for value in group)
    return bytes(out)


def unpack7(data):
    if any(value > 127 for value in data):
        raise ValueError('Non-data byte in packed SysEx body')
    out = bytearray()
    for start in range(0,len(data),8):
        group = data[start:start+8]
        if len(group) < 2:
            raise ValueError('Incomplete SysEx group')
        if group[0] >> (len(group)-1):
            raise ValueError('Unused MSB bits must be zero')
        out.extend(value | (((group[0] >> index) & 1) << 7)
                   for index,value in enumerate(group[1:]))
    return bytes(out)


def read_sequence_file(data):
    """Return pattern plus exact framing; raw pattern, current or stored SysEx."""
    if len(data) == SIZE and valid_pattern(data):
        return data,b'',b''
    if len(data) not in (2203,2204) or data[:2] != b'\xf0\x42' or data[-1:] != b'\xf7':
        raise ValueError('Expected one complete FM2 sequence SysEx or raw pattern')
    if not 0x30 <= data[2] <= 0x3F or data[3:6] != b'\x00\x01\x2f':
        raise ValueError('Wrong SysEx device header')
    opcode = data[6]
    head = 7 if opcode == 0x40 else 8 if opcode == 0x4C else 0
    if not head or len(data) != head+2195+1:
        raise ValueError('Wrong sequence SysEx opcode or length')
    if head == 8 and data[7] > 15:
        raise ValueError('Stored pattern number out of range')
    pattern = unpack7(data[head:-1])
    if not valid_pattern(pattern):
        raise ValueError('Decoded sequence markers/format mismatch')
    return pattern,data[:head],b'\xf7'


def write_sequence_file(pattern,prefix,suffix):
    if not valid_pattern(pattern):
        raise ValueError('Wrong pattern')
    return prefix+pack7(pattern)+suffix if prefix else pattern
