"""Create reproducible install/restore WAVs for the FM2 hardware test.

The restore transport header is 1.15, but its installed payload is EXACTLY
original 1.12. Neither image changes the original bootloader sector.
"""
from pathlib import Path
import hashlib,io,json,struct,wave
import numpy as np
from build_patch import build,BASE
from original_image import canonical_events,rebuild_original,parse_symbols,LAYOUT,sum16,read_original

ROOT=BASE/'dist'
ROOT.mkdir(exist_ok=True)
INSTALL='01_INSTALLA_FM2_1_19_BETA.wav'
RESTORE='02_RIPRISTINA_ORIGINALE_1_12.wav'
RESTORE_TRANSPORT_MINOR=15

def need(ok,msg):
    if not ok:raise AssertionError(msg)

def sha(b):return hashlib.sha256(b).hexdigest()

def decode_wave(path):
    data=Path(path).read_bytes()
    with wave.open(io.BytesIO(data),'rb') as f:
        fmt=(f.getnchannels(),f.getsampwidth(),f.getframerate())
        need(fmt==(1,2,44100),'Unexpected WAV format')
        samples=f.getnframes();pcm=np.frombuffer(f.readframes(samples),dtype='<i2')
    need(np.all(pcm!=0),'Zero sample in update waveform')
    positive=pcm>0;edges=np.flatnonzero(positive[1:]!=positive[:-1])+1
    runs=np.diff(np.r_[0,edges,len(pcm)])
    need(len(runs)%2==0 and np.all(runs[::2]==runs[1::2]),'Asymmetric cycles')
    need(np.all((runs==5)|(runs==10)),'Invalid FSK half-cycle')
    bits=(runs[::2]==5).astype(np.uint8)
    header,payload,events,trailing=parse_symbols(bits)
    need(len(payload)==0x30000==struct.unpack_from('<I',header,24)[0],'Wrong logical size')
    for tag,start,size,ho in LAYOUT:
        sec=payload[start:start+size]
        need(sec[ho:ho+6]==b'KORG\xe8N','Wrong section magic')
        need(struct.unpack_from('<HI',sec,ho+6)==(tag,size),'Wrong tag/size')
        need(sum16(sec)==0,'Section checksum error')
    return {'data':data,'bits':bits,'header':header,'payload':payload,'events':events,
            'trailing':trailing,'samples':samples,'duration_seconds':samples/44100}

def generate():
    original,beta,code,manifest,beta_header=build()
    reference=read_original(BASE/'reference/volca_fm2_updater_0112.zip')
    restore_header=bytearray(reference['header']);restore_header[22:24]=bytes([1,RESTORE_TRANSPORT_MINOR])
    need(original[:0x4000]==beta[:0x4000],'Bootloader modified')
    artifacts=[]
    for filename,header,payload in [(INSTALL,beta_header,beta),(RESTORE,bytes(restore_header),original)]:
        events,trailing=canonical_events(header,payload)
        _,wav_data=rebuild_original(events,trailing)
        path=ROOT/filename;path.write_bytes(wav_data)
        decoded=decode_wave(path)
        need(decoded['payload']==payload and decoded['header']==header,'WAV roundtrip mismatch')
        artifacts.append({'file':filename,'sha256':sha(wav_data),'bytes':len(wav_data),
                          'duration_seconds':decoded['duration_seconds'],
                          'transport_version':f'{header[22]}.{header[23]:02}',
                          'installed_version':f'{payload[0x420C]}.{payload[0x420D]:02}',
                          'logical_sha256':sha(payload),
                          'all_frames_CRC_and_section_checksums_valid':True})
    result={'release':'FM2 1.19 BETA (probability, step conditions, quick commands, pattern scale, HOLD, arpeggio modes, arpeggio MIDI out, musical scales, humanize, random octave, delay alternative to the reverb, free chain, chain capture, recording on a chain), independent experimental modification',
            'source':'Korg original 1.12','physical_hardware_validated':False,
            'bootloader_first_16384_bytes_unchanged':True,
            'install_and_restore_files':artifacts,
            'restore_installed_payload_byte_identical_to_original':True,
            'restore_header_is_recoded_not_an_unmodified_official_WAV':True}
    (BASE/'build/release_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'SHA256SUMS.txt').write_text(''.join(x['sha256']+'  '+x['file']+'\n' for x in artifacts))
    import shutil
    for src,dst in (('docs/GUIDA_1_19.txt','LEGGIMI.txt'),('docs/PROVE_1_19.txt','PROVE.txt'),
                    ('docs/en/GUIDE.md','GUIDE_EN.md'),('docs/en/TESTS_1_19.txt','TESTS_EN.txt'),
                    ('release/VERIFICA_FILE.command','VERIFICA_FILE.command'),
                    ('release/VERIFICA_FILE.bat','VERIFICA_FILE.bat'),
                    ('release/verifica_file.ps1','verifica_file.ps1')):
        shutil.copyfile(BASE/src,ROOT/dst)
    return original,beta,result

if __name__=='__main__':print(json.dumps(generate()[2],indent=2))
