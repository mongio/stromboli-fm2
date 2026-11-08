"""Decode the exact original 1.12 audio update. In-memory original bytes only."""
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import struct
import wave
import zipfile
import numpy as np

WAV_SHA = '8e80e7bc2e2c24f8fef9962492b381a95e394204bfc3ba02e05114a9e403fc9d'
LOGICAL_SHA = 'daf7052f0483a3bd82958f142d81038aeaec011d6f018de31261b8f5baed5e40'
LAYOUT = ((0xff00,0,0x10000,0x4200),(0xff11,0x10000,0x4000,0),
          (0xff12,0x14000,0xa000,0),(0xff13,0x1e000,0xc000,0),
          (0xff14,0x2a000,0x6000,0))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def crc16(data):
    crc = 0xffff
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc


def sum16(data):
    need(len(data) % 2 == 0, 'Odd length for LE16 checksum')
    return int(np.frombuffer(data,dtype='<u2').sum(dtype=np.uint64)) & 65535


@dataclass
class Event:
    idle: int
    packet: bytes
    output: bytes


def parse_symbols(bits):
    pos = 0
    events = []
    header = None
    logical = bytearray()
    def take(n):
        nonlocal pos
        need(pos+8*n <= len(bits), 'Truncated packet')
        v=np.packbits(bits[pos:pos+8*n],bitorder='little').tobytes()
        pos+=8*n
        return v
    while pos < len(bits):
        begin=pos
        while pos < len(bits) and bits[pos] == 1:
            pos+=1
        idle=pos-begin
        if pos==len(bits):
            trailing=idle
            break
        need(bits[pos]==0, 'Missing start bit')
        pos+=1
        marker=take(1)
        if marker==b'\xa9':
            n=32 if header is None else 512
            data=take(n)
            check=take(2)
            need(crc16(data)==struct.unpack('<H',check)[0], 'Frame CRC mismatch')
            if header is None:
                need(data[:16]==b'KORG SYSTEM FILE','Invalid system header')
                header=data
                output=b''
            else:
                output=data
            packet=marker+data+check
        elif marker==b'\x4e':
            need(header is not None,'Fill before header')
            pair=take(2)
            need(pair[0]^pair[1]==255,'Fill complement mismatch')
            packet=marker+pair
            output=bytes([pair[0]])*512
        else:
            raise ValueError('Unknown marker '+marker.hex())
        events.append(Event(idle,packet,output))
        logical.extend(output)
    else:
        trailing=0
    need(header is not None,'Missing header')
    return header,bytes(logical),events,trailing


def read_original(source):
    source=Path(source)
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as z:
            names=[n for n in z.namelist() if Path(n).name=='volca_fm2_sys_112.wav']
            need(len(names)==1,'Expected original 1.12 WAV')
            wav=z.read(names[0])
    else:
        wav=source.read_bytes()
    need(sha(wav)==WAV_SHA,'Original WAV SHA256 mismatch')
    with wave.open(io.BytesIO(wav)) as f:
        need((f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,44100),'Wrong WAV format')
        pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
    need(np.all(pcm!=0),'Unexpected zero sample')
    signs=pcm>0
    edges=np.flatnonzero(signs[1:]!=signs[:-1])+1
    runs=np.diff(np.r_[0,edges,len(pcm)])
    need(len(runs)%2==0 and np.all(runs[::2]==runs[1::2]),'Asymmetric cycles')
    need(np.all((runs==5)|(runs==10)),'Invalid cycle duration')
    bits=(runs[::2]==5).astype(np.uint8)
    header,logical,events,trailing=parse_symbols(bits)
    need(sha(logical)==LOGICAL_SHA,'Logical image SHA256 mismatch')
    need(len(logical)==struct.unpack_from('<I',header,24)[0]==0x30000,'Logical size mismatch')
    for tag,start,size,ho in LAYOUT:
        section=logical[start:start+size]
        need(section[ho:ho+6]==b'KORG\xe8N','Section magic mismatch')
        need(struct.unpack_from('<H',section,ho+6)[0]==tag,'Section tag mismatch')
        need(struct.unpack_from('<I',section,ho+8)[0]==size,'Section size mismatch')
        need(sum16(section)==0,'Internal checksum mismatch')
    return {'wav':wav,'bits':bits,'header':header,'logical':logical,
            'events':events,'trailing':trailing,'pcm_samples':len(pcm)}


def canonical_events(header,logical):
    """Regenerate original packets from logical bytes, not captured wire packets."""
    events=[Event(10000,b'\xa9'+header+struct.pack('<H',crc16(header)),b'')]
    for at in range(0,len(logical),512):
        block=logical[at:at+512]
        if block[0] in (0xff,0x30) and block==bytes([block[0]])*512:
            packet=bytes([0x4e,block[0],block[0]^255])
        else:
            packet=b'\xa9'+block+struct.pack('<H',crc16(block))
        events.append(Event(4000 if at==0 else 700,packet,block))
    return events,4700


def rebuild_original(events,trailing):
    # Synthesize from regenerated packets and fixed protocol grammar.
    chunks=[]
    for event in events:
        chunks.extend((np.ones(event.idle,dtype=np.uint8),np.zeros(1,dtype=np.uint8),
                       np.unpackbits(np.frombuffer(event.packet,dtype=np.uint8),bitorder='little')))
    chunks.append(np.ones(trailing,dtype=np.uint8))
    bits=np.concatenate(chunks)
    lengths=np.repeat(np.where(bits==1,5,10),2)
    starts=np.r_[0,np.cumsum(lengths[:-1])]
    ends=starts+lengths-1
    signs=np.where(np.arange(len(lengths))%2==0,1,-1).astype(np.int16)
    pcm=np.repeat(signs*32767,lengths).astype('<i2')
    pcm[starts]=signs*28672
    pcm[ends]=signs*10752
    out=io.BytesIO()
    with wave.open(out,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(44100)
        f.writeframes(pcm.tobytes())
    return bits,out.getvalue()
