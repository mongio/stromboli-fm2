"""Execute real patched ARM bytes and compare against native original behavior."""
from pathlib import Path
import json
import struct
import time
import sys
import hashlib
import random
import subprocess
import tempfile
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
    UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP)

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
from build_patch import build,CODE_ADDRESS,HOOK_OFFSET
from probability_format import *
import reverse_checks as native
from arm_checks import REGS,verify_boot,stage_receiver,verify_installer,verify_application_initialization
from original_image import canonical_events,rebuild_original,sum16,LAYOUT


def need(condition,message):
    if not condition:
        raise AssertionError(message)


def core_snapshot(a):
    # Excludes code images and unused stack bytes, includes application/audio state.
    return (a.data(0x20000000,0x5800),a.data(0x2000590C,16),
            a.data(native.PATTERN,1920),a.data(0x2001D08C,32))


def configure(a,profile):
    a.u.mem_write(native.PATTERN,set_profile(a.data(native.PATTERN,1920),profile))


def verify_thresholds(original,patched):
    a = native.sequencer_observer(patched)
    native.set_step(a,0,[48,55,60,64,67,72],0xA0)
    a.draw = 0; a.draw_calls = 0
    def supplied_draw():
        need(a.u.reg_read(REGS[0]) == 100,'Wrong native PRNG modulus')
        a.draw_calls += 1; a.return_(a.draw)
    a.hook(0x2094A4,supplied_draw)
    cases = 0
    for pct in range(101):
        configure(a,[pct]*16)
        before = a.draw_calls
        for draw in range(100):
            a.draw = draw
            a.u.mem_write(native.SLOTS,bytes(0x34))
            a.events = []
            a.call(0x20B7BE,(0,))
            ons = [event for event in a.events if event[0] == 'on']
            need(len(ons) == (6 if draw < pct else 0),'Percentage threshold/chord atomicity mismatch')
            cases += 1
        need(a.draw_calls-before == (0 if pct in (0,100) else 100),
             '0/100 percent unexpectedly consumed randomness')
    return {'cases':cases,'percentages':101,'draws_per_percentage':100,
            'six_note_chord_is_one_decision':True,
            'modeled_functions':{'0x002094A4':'controlled draw 0..99 only for threshold matrix',
                                '0x0020AC54':'backend note-on observer',
                                '0x0020AC70':'backend note-off observer'}}


def verify_native_random(original,patched):
    a = native.sequencer_observer(patched)
    native.set_step(a,0,[60,64,67],0xA0)
    configure(a,[50]*16)
    state = list(struct.unpack('<4I',a.data(0x2000590C,16)))
    hits = 0; decisions = bytearray()
    for _ in range(10000):
        x,y,z,w = state
        t = (x ^ (x<<11)) & 0xFFFFFFFF
        next_w = (w ^ (w>>19) ^ t ^ (t>>8)) & 0xFFFFFFFF
        state = [y,z,w,next_w]
        expected = next_w%100 < 50
        a.u.mem_write(native.SLOTS,bytes(0x34)); a.events = []
        a.call(0x20B7BE,(0,))
        ons = [event for event in a.events if event[0]=='on']
        need(len(ons) == (3 if expected else 0),'Native RNG decision differs from independent formula')
        hits += bool(ons); decisions.append(bool(ons))
    need(list(struct.unpack('<4I',a.data(0x2000590C,16))) == state,'Native RNG state diverged')
    return {'passes':10000,'played':hits,'skipped':10000-hits,
            'observed_percent':hits/100,'decision_sha256':hashlib.sha256(decisions).hexdigest(),
            'original_PRNG_executed':True,'independent_model_matches_every_decision':True,
            'modeled_functions':{'0x0020AC54':'backend note-on observer',
                                '0x0020AC70':'backend note-off observer'}}


def verify_profiles_and_fail_open(original,patched):
    a = native.sequencer_observer(patched)
    native.set_step(a,0,[60,64,67],0xA0)
    current = a.data(native.PATTERN,1920)
    p = set_profile(current,[0]*16)
    pristine_rng = a.data(0x2000590C,16)
    a.u.mem_write(native.PATTERN,p)
    a.events = []; a.call(0x20B7BE,(0,))
    need(not a.events,'Valid 0 percent profile did not skip')
    cases = 0
    for offset in range(28):
        for bit in range(8):
            bad = bytearray(p); bad[OFFSET+offset] ^= 1<<bit
            a.u.mem_write(native.PATTERN,bytes(bad))
            a.u.mem_write(native.SLOTS,bytes(0x34)); a.events = []
            a.call(0x20B7BE,(0,))
            need(len([x for x in a.events if x[0]=='on']) == 3,'Damaged extension did not fall back to native playback')
            need(a.data(0x2000590C,16) == pristine_rng,'Damaged extension advanced PRNG')
            cases += 1
    for fill in [0,255]:
        legacy = bytearray(current); legacy[OFFSET:OFFSET+28] = bytes([fill])*28
        a.u.mem_write(native.PATTERN,bytes(legacy)); a.u.mem_write(native.SLOTS,bytes(0x34)); a.events=[]
        a.call(0x20B7BE,(0,))
        need(len([x for x in a.events if x[0]=='on']) == 3,'Legacy pattern changed')
    invalid = bytearray(p)
    invalid[OFFSET+4] = 101
    struct.pack_into('<I',invalid,OFFSET+24,fnv1a(invalid[OFFSET+4:OFFSET+20]))
    a.u.mem_write(native.PATTERN,bytes(invalid)); a.u.mem_write(native.SLOTS,bytes(0x34)); a.events=[]
    a.call(0x20B7BE,(0,))
    need(len([x for x in a.events if x[0]=='on']) == 3,'Out-of-range percentage was accepted')
    return {'corrupted_extension_bits_tested':cases,'legacy_zero_and_FF_reserved_bytes_play_normally':True,
            'invalid_percent_falls_back_to_original':True,'fallback_advances_PRNG':False}


def verify_no_random_on_native_rests(original,patched):
    a = native.sequencer_observer(patched)
    configure(a,[50]*16)
    native.set_step(a,0,[60],0xA0)
    before = a.data(0x2000590C,16)
    a.u.mem_write(native.PATTERN+6,b'\xfe\xff')
    a.call(0x20B7BE,(0,))
    need(a.data(0x2000590C,16)==before,'Muted step consumed randomness')
    a.u.mem_write(native.PATTERN+6,b'\xff\xff')
    native.set_step(a,0,[])
    a.call(0x20B7BE,(0,))
    need(a.data(0x2000590C,16)==before,'Rest consumed randomness')
    return {'native_mute_and_rest_do_not_consume_PRNG':True}


def verify_100_percent_differential(original,patched):
    rng = random.Random(1120311)
    a = native.sequencer_observer(original)
    b = native.sequencer_observer(patched)
    for machine in [a,b]:
        configure(machine,[100]*16)
    regs = [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
            UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
    sentinel = [0xA5000000+i*0x10101 for i in range(8)]
    observed = 0
    def hook_seen():
        nonlocal observed
        observed += 1
    b.hook(CODE_ADDRESS,hook_seen)
    for case in range(256):
        step = case%16
        notes = rng.sample(range(24,108),rng.randrange(7))
        gates = [rng.choice([0,1,32,72,126,127,160,255]) for _ in notes]
        velocity = rng.randrange(1,128)
        enabled = rng.randrange(65536)
        for machine in [a,b]:
            native.set_step(machine,step,notes,gates,velocity)
            machine.u.mem_write(native.PATTERN+6,struct.pack('<H',enabled))
            for reg,value in zip(regs,sentinel):machine.u.reg_write(reg,value)
            machine.events = []; machine.call(0x20B7BE,(step,))
            need([machine.u.reg_read(reg) for reg in regs] == sentinel,'Callee-saved register corrupted')
            need(machine.u.reg_read(UC_ARM_REG_SP) == 0x20006000,'Stack not restored')
        need(a.events == b.events,'100 percent event regression')
        need(core_snapshot(a) == core_snapshot(b),'100 percent application-state regression')
    need(observed == 256,'Real patch trampoline was not executed')
    return {'differential_step_cases':256,'events_and_application_state_equal':True,
            'callee_saved_registers_and_stack_verified':True,'actual_trampoline_entries':observed}


def verify_ties_and_clock(original,patched):
    a = native.sequencer_observer(patched)
    native.prepare_clock(a)
    profile = [100]*16; profile[1]=0
    for i in range(16):native.set_step(a,i,[60,64,67],127)
    configure(a,profile)
    a.call(0x208CF8,(1,0)); a.events=[]
    a.call(0x208CF8,(1,0))
    need([x[0] for x in a.events] == ['off']*3,'Skipped step did not release a previous TIE chord')
    need(a.data(native.SLOTS,24) == bytes(24),'Skipped TIE left logical notes active')
    a.events=[]; a.call(0x208CF8,(1,0))
    need([x[0] for x in a.events] == ['on']*3,'Playback failed to resume after skipped TIE')
    b = native.sequencer_observer(patched)
    native.prepare_clock(b,0x55)
    for i in range(16):native.set_step(b,i,[60+i],160)
    configure(b,[0]*16)
    seen=[]; b.hook(0x20903E,lambda:seen.append(b.u.reg_read(REGS[0])))
    for _ in range(12):b.call(0x208CF8,(1,0))
    need(seen == [0,2,4,6]*3,'Probability altered active-step timing/order')
    need(not [x for x in b.events if x[0]=='on'],'0 percent clock generated notes')
    return {'skipped_TIE_releases_previous_chord':True,'next_step_resumes':True,
            'all_zero_probability_active_step_order':seen,'native_clock_still_advances':True}


def verify_metadata_survives_storage_and_sysex(original,patched):
    s = native.Storage(patched)
    patterns = [set_profile(native.pattern_fixture(s.a,i),[(i*7+j*11)%101 for j in range(16)])
                for i in range(16)]
    for i,p in enumerate(patterns):s.store(i,p)
    s.flush(); reboot = native.Storage(patched,s.flash)
    for i,p in enumerate(patterns):
        accepted,loaded = reboot.load(i)
        need(accepted == 1 and loaded == p and get_profile(loaded)[1],'Profile did not survive native journal')
    a = native.Application(patched); a.put32(native.ROOT,0x20020000)
    a.hook(0x20015180,lambda:a.return_(native.SCRATCH)); a.hook(0x200151B0,lambda:a.return_(0))
    for slot,p in enumerate(patterns):
        packet=bytes.fromhex('f0423000012f4c')+bytes([slot])+pack7(p)+b'\xf7'
        for value in packet:a.call(0x200146EC,(1,value))
        need(a.data(0x20020000+slot*1920,1920)==p,'Profile did not survive native SysEx receive')
    return {'all_pattern_slots':16,'native_NOR_reboot_byte_identical':True,
            'native_SysEx_receive_byte_identical':True,'pattern_size_unchanged':1920,
            'new_SRAM_global_bytes':0,'new_writable_ITCM_state_bytes':16}


def verify_editor_roundtrip(original,patched):
    a = native.Application(original); p=native.pattern_fixture(a,4)
    frames=[p,bytes.fromhex('f0423000012f40')+pack7(p)+b'\xf7',
            bytes.fromhex('f0423000012f4c05')+pack7(p)+b'\xf7']
    with tempfile.TemporaryDirectory(prefix='fm2_probability_') as temp:
        folder=Path(temp)
        for index,frame in enumerate(frames):
            inp=folder/f'input{index}.bin'; out=folder/f'output{index}.bin'; inp.write_bytes(frame)
            result=subprocess.run([sys.executable,str(BASE/'edit_probability.py'),str(inp),str(out),
                                   '--set','2=50','--set','6=0'],capture_output=True,text=True)
            need(result.returncode==0,'Editor failed: '+result.stderr)
            p2,head,tail=read_sequence_file(out.read_bytes())
            need(get_profile(p2)==([100,50,100,100,100,0]+[100]*10,True),'Editor profile incorrect')
            need(p2[:OFFSET]==p[:OFFSET] and p2[OFFSET+28:]==p[OFFSET+28:],'Editor modified notes/header/footer')
            need(inp.read_bytes()==frame,'Editor overwrote input')
    return {'CLI_roundtrips':['raw pattern','current sequence SysEx','stored sequence SysEx'],
            'only_reserved_extension_bytes_changed':True,'input_files_preserved':True}


def verify_live_midi_ownership(original,patched):
    a = native.audio_machine(patched); native.blank_pattern(a); a.call(0x208198,(0,1))
    a.call(0x2080A4,(1,)); a.call(0x200148E4,(1,))
    for value in [0x90,84,100]:a.call(0x200146EC,(1,value))
    a.u.mem_write(native.PATTERN+6,b'\xff\xff')
    native.set_step(a,0,[60],127);native.set_step(a,1,[64],160)
    profile=[100]*16;profile[1]=0;configure(a,profile)
    a.call(0x20B7BE,(0,));a.call(0x20B7BE,(1,))
    records=[list(a.data(0x20003C6C+i*16,12)) for i in range(6)]
    live=[r for r in records if r[0] and r[1]==0x30 and r[8]==84]
    internal=[r for r in records if r[0] and r[1]==0x10]
    need(len(live)==1 and not internal,'Probability released unrelated live MIDI note')
    return {'external_MIDI_note_retained':84,'previous_sequencer_note_released':60,
            'skipped_new_note_not_started':64,'modeled_functions':{}}


def verify_audio_differential_mixed(original,patched):
    a=native.audio_machine(original); b=native.audio_machine(patched)
    profile=[100,50,0,25,100,75,0,50,100,0,90,10,50,100,0,100]
    for machine in [a,b]:
        native.blank_pattern(machine);machine.call(0x208198,(0,1));native.prepare_clock(machine)
        machine.u.mem_write(native.PATTERN+6,b'\xff\xff')
        for step in range(16):native.set_step(machine,step,[36+step,43+step,48+step,52+step,55+step,60+step],160)
        configure(machine,profile)
        machine.call(0x20EA70,(90,));machine.call(0x2045F4,(1,))
        machine.call(0x20EA84,(80,));machine.call(0x20453C,(1,))
        machine.put32(0x20000028,0x7FFFFFFF);machine.put32(0x2000002C,0x7FFFFFFF)
    raw=bytearray(); cases=[]
    for tick in range(64):
        step=tick%16; pct=profile[step]
        expected = pct==100 or (pct!=0 and a.call(0x2094A4,(100,))<pct)
        # Native original muted-step behavior is the independent semantic oracle.
        mask=0xFFFF if expected else 0xFFFF^(1<<step)
        a.u.mem_write(native.PATTERN+6,struct.pack('<H',mask))
        a.call(0x208CF8,(1,0));b.call(0x208CF8,(1,0))
        a.u.mem_write(native.PATTERN+6,b'\xff\xff')
        need(core_snapshot(a)==core_snapshot(b),'Mixed probability state differs from native mute oracle')
        first=native.render_isr(a,512,service_every=64)
        second=native.render_isr(b,512,service_every=64)
        need(first==second,'Mixed probability output differs from original DSP/effect path')
        raw.extend(second);cases.append({'step':step,'percent':pct,'played':expected})
        for machine in [a,b]:
            for i in range(6):machine.u.mem_write(0x20003C6C+i*16+11,b'\0')
    return {'step_visits':64,'stereo_frames_compared':len(raw)//8,
            'PCM32_sha256':hashlib.sha256(raw).hexdigest(),
            'FM_chorus_reverb_sample_identical_to_native_muted_step_oracle':True,
            'decisions':cases,'physical_tempo_or_DAC_not_emulated':True}


def verify_native_image_transport(original,patched,header):
    events,trailing=canonical_events(header,patched)
    bits,wav_in_memory=rebuild_original(events,trailing)
    a=stage_receiver(patched,events,10,capture_bits=bits)
    need(a.reason=='staging_complete','Patched image staging rejected')
    staged_exact=bytes(a.u.mem_read(0x20010000,0x30000))==patched
    need(staged_exact,'Staged candidate differs from generated image')
    # Installed program is the ORIGINAL image, with only the modeled installed
    # version field set to 1.10 to exercise the official version-gated path.
    installed=bytearray(original[:0x10000]);installed[0x420D]=10
    a.u.mem_write(0x200000,bytes(installed))
    result=verify_installer(patched,staged_arm=a)
    boot=verify_boot(patched,prepared_arm=a)
    cpu=verify_application_initialization(patched,prepared_arm=a)
    blob=(BASE/'build/fm2_123_code_ARM.bin').read_bytes()
    need(bytes(a.u.mem_read(CODE_ADDRESS,len(blob)))==blob,
         'Native boot did not load the exact 1.23 code')
    need(bytes(a.u.mem_read(0x3E00,0x100))==patched[0x13E00:0x13F00],'Native boot did not load text tables')
    need(bytes(a.u.mem_read(0x3F00,0x80))==patched[0x13F00:0x13F80],'State not initialized by native boot')
    need(bytes(a.u.mem_read(0x3F80,0x80))==patched[0x13F80:0x14000],'Delay state not initialized by native boot')
    need(bytes(a.u.mem_read(0x1A00,0x200))==patched[0x11A00:0x11C00],'LOFI table not loaded by native boot')
    need(bytes(a.u.mem_read(0x023C,4))==struct.pack('<I',0x2059),'Audio ISR effect literal not loaded')
    need(bytes(a.u.mem_read(0x1C00,0x110))==bytes(0x110),'Chain state not zero after native boot')
    need(bytes(a.u.mem_read(0x20FC40,0x3B0))==patched[0xFC40:0xFFF0],'Flash chain blob not mapped')
    # Execute the hook after install/reset in that same CPU instance.
    a.call(0x20852C,(native.PATTERN,))
    a.u.mem_write(native.PATTERN+6,b'\xff\xff')
    a.u.mem_write(0x20003C6C+0xDC,b'\x06')
    native.set_step(a,0,[60,64,67],160)
    events=[];entries=[]
    a.hook(CODE_ADDRESS,lambda:entries.append(1))
    def on():
        events.append([a.u.reg_read(r) for r in REGS[:3]])
        a.return_(a.u.reg_read(REGS[2]))
    a.hook(0x20AC54,on)
    data=bytes(a.u.mem_read(native.PATTERN,1920))
    a.u.mem_write(native.PATTERN,set_profile(data,[0]*16));a.call(0x20B7BE,(0,))
    need(not events and len(entries)==1,'Installed patch 0 percent failed')
    a.u.mem_write(native.PATTERN,set_profile(data,[100]*16));a.call(0x20B7BE,(0,))
    need(len(events)==3 and len(entries)==2,'Installed patch 100 percent failed')
    return {'waveform_generated_only_in_RAM':True,'installable_WAV_file_created':False,
            'generated_PCM_WAV_bytes':len(wav_in_memory),'capture_halfcycles':a.half_index,
            'logical_payload_byte_identical_after_staging':staged_exact,
            'installer':result,'reset_and_load':boot,'application_CPU_prefix':cpu,
            'installed_code_0_and_100_percent_verified':True,'same_CPU_instance':True,
            'post_boot_observation_boundaries':{'0x0020AC54':'backend note-on observer'},
            'installed_old_version_field_is_a_fixture_not_a_real_1_10_firmware':True}


def main(include_transport=True):
    from verify_panel import TASKS as panel_tasks
    original,patched,code,manifest,header=build()
    report={'firmware':'volca FM2 original 1.12 + experimental 1.23 beta (probability, conditions, commands, scale, HOLD, arpeggio modes and MIDI out, musical scales, humanize, random octave, delay alternative to the reverb, free chain with recording (CR), FUNC during a chain, pattern copy, REC FISSO, Program Change in, effect type saved in the pattern, phaser and tremolo, tape LOFI, play direction, note mutation)',
            'date':'2026-11-08','patched_logical_sha256':manifest['patched_logical_sha256'],
            'physical_hardware_tested':False,'groups':{}}
    tasks=[('threshold_matrix',lambda:verify_thresholds(original,patched)),
           ('native_random',lambda:verify_native_random(original,patched)),
           ('profile_validation',lambda:verify_profiles_and_fail_open(original,patched)),
           ('native_mute_and_rest',lambda:verify_no_random_on_native_rests(original,patched)),
           ('100_percent_differential_ABI',lambda:verify_100_percent_differential(original,patched)),
           ('ties_and_clock',lambda:verify_ties_and_clock(original,patched)),
           ('profile_storage_and_sysex',lambda:verify_metadata_survives_storage_and_sysex(original,patched)),
           ('editor',lambda:verify_editor_roundtrip(original,patched)),
           ('live_MIDI_ownership',lambda:verify_live_midi_ownership(original,patched)),
           ('mixed_probability_audio',lambda:verify_audio_differential_mixed(original,patched))]
    regression=[('pattern_format',native.verify_pattern_format),('sequence',native.verify_sequence),
                ('clock',native.verify_clock),('chain',native.verify_chain),('motion',native.verify_motion),
                ('sysex',native.verify_sysex),('program_sysex',native.verify_program_sysex),
                ('storage',native.verify_storage),('fm',native.verify_fm),
                ('voice_modes',native.verify_voice_modes),('prng',native.verify_prng),
                ('arpeggiator',native.verify_arpeggiator),('effects',native.verify_effects),
                ('midi',native.verify_midi),('application_path',native.verify_application_path)]
    tasks.extend(('regression/'+name,lambda fn=fn:fn(patched)) for name,fn in regression)
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in panel_tasks)
    from verify_114 import TASKS as v114_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v114_tasks)
    from verify_115 import TASKS as v115_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v115_tasks)
    from verify_116 import TASKS as v116_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v116_tasks)
    from verify_117 import TASKS as v117_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v117_tasks)
    from verify_118 import TASKS as v118_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v118_tasks)
    from verify_122 import all_tasks as v122_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v122_tasks())
    from verify_122_mod import TASKS as v122_mod_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v122_mod_tasks)
    from verify_123 import TASKS as v123_tasks
    tasks.extend((name,lambda fn=fn:fn(original,patched)) for name,fn in v123_tasks)
    tasks.append(('native_boot',lambda:verify_boot(patched)))
    tasks.append(('same_version_still_rejected',lambda: {
        'reason':stage_receiver(patched,canonical_events(header,patched)[0],23).reason}))
    if include_transport:
        tasks.append(('native_FSK_staging_installer',lambda:verify_native_image_transport(original,patched,header)))
    failed=[]
    out=BASE/'reports';out.mkdir(exist_ok=True)
    for name,fn in tasks:
        start=time.monotonic()
        try:
            result=fn()
            if name=='same_version_still_rejected':need(result['reason']=='error:ERR_VER','Version guard changed')
            result['status']='PASS'
        except Exception as e:
            result={'status':'FAIL','error':type(e).__name__+': '+str(e)};failed.append(name)
        result['seconds']=round(time.monotonic()-start,3);report['groups'][name]=result
        print(name+': '+result['status']+' ('+str(result['seconds'])+'s)',flush=True)
        if name in failed:print(result['error'],flush=True)
        report['status']='FAIL' if failed else 'IN_PROGRESS'
        (out/'patch_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    report['status']='FAIL' if failed else 'PASS_OFFLINE_PATCH_EXPERIMENTAL_HARDWARE_UNTESTED'
    report['total_groups']=len(tasks);report['passed_groups']=len(tasks)-len(failed)
    (out/'patch_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'ESITO.txt').write_text(report['status']+'\n'+str(report['passed_groups'])+'/'+str(len(tasks))+' gruppi PASS\n'+
        '\n'.join(v['status']+' '+k for k,v in report['groups'].items())+'\n',encoding='utf-8')
    print(report['status'],flush=True)
    if failed:raise SystemExit(1)


if __name__=='__main__':
    main(include_transport='--quick' not in sys.argv)
