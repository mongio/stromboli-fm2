"""Validate files for FM2 beta hardware testing, including exact rollback.

No physical instrument is accessed. Native ARM handles FSK, parsing, version
checks, flash-sector decisions and copying, boot and application initialization.
Analog input, GPIO key recognition and physical flash/SPI devices are modeled.
"""
import json,struct,time
from pathlib import Path
from build_release import generate,decode_wave,ROOT,BASE,INSTALL,RESTORE,sha,need
from original_image import canonical_events
from arm_checks import OriginalARM,REGS,verify_installer,verify_boot,verify_application_initialization,runtime_storage
import reverse_checks as native
import verify_patch as core
import verify_panel as panel
from probability_format import set_profile,get_profile

def stage(installed,decoded,full_FSK=False,stream=None):
    # Actual installed firmware, including its real version bytes, is the
    # source of the emulated flash. No synthetic installed-version overwrite.
    a=OriginalARM(installed)
    if full_FSK:a.duration_input(decoded['bits'])
    else:
        a.receiver_stubs();a.hook(0x202834,lambda:a.return_(0))
    a.byte_stream=stream if stream is not None else b''.join(e.packet for e in decoded['events'])
    a.byte_pos=0
    a.hook(0x203734,lambda:a.return_(0x20005000))
    a.staging_stop_hook=a.hook(0x2024C8,lambda:a.stop('staging_complete'))
    a.call(0x202AB4,(0,1),limit=250000000 if full_FSK else 20000000)
    need(bytes(a.u.mem_read(0x20420C,2))==installed[0x420C:0x420E],'Installed version was changed by fixture')
    return a

def recovery_route(installed,corrupt_application=False):
    flash=bytearray(installed)
    if corrupt_application:flash[0x4000:0x10000]=bytes(0xC000)
    a=OriginalARM(bytes(flash));storage=runtime_storage(installed)
    for address,value in {0x20047C:0,0x200738:0,0x20070C:0,0x203654:0,
                          0x200B28:0,0x2037E0:0x13,0x200B44:0,0x200E00:1,
                          0x200778:0,0x200B7C:1}.items():
        a.hook(address,lambda v=value:a.return_(v))
    def read():
        dest,src,size=[a.u.reg_read(r) for r in REGS[:3]]
        need(src+size<=len(storage),'Read outside modeled SPI')
        a.u.mem_write(dest,bytes(storage[src:src+size]));a.return_(1)
    a.hook(0x200EC8,read)
    args=[]
    def receiver():
        args.extend(a.u.reg_read(r) for r in REGS[:2]);a.stop('native_update_receiver_reached')
    a.hook(0x202AB4,receiver)
    a.hook(0x204240,lambda:a.stop('unexpected_application_entry'))
    a.call(0x2000E4,(),limit=3000000)
    need(a.reason=='native_update_receiver_reached' and args==[0,1],'Reset recovery did not reach version-checked updater')
    return {'result':a.reason,'original_receiver_arguments':args,
            'decoded_key_mode_fixture':'0x13; FUNC+PLAY per official update instructions',
            'application_flash_zeroed_for_fault_test':corrupt_application,
            'application_not_executed':True,'physical_GPIO_not_tested':True}

# Images of the earlier betas (built from their own sources) are optional: they
# contain Korg firmware and are not part of the repository. When present in
# reference/, the upgrade paths from those betas are tested too.
def _beta(minor):
    p=BASE/f'reference/installed_beta_1_{minor}_logical.bin'
    return p.read_bytes() if p.exists() else None
BETAS={m:_beta(m) for m in range(13,22)}
BETA_113,BETA_114,BETA_115,BETA_116,BETA_117,BETA_118,BETA_119,BETA_120,BETA_121=(BETAS[m] for m in range(13,22))
SKIPPED=[f'1.{m}' for m,v in BETAS.items() if v is None]

def check_update_guards(original,beta,install,restore):
    if BETA_113 is not None:
        need(sha(BETA_113)=='2b20120a2d6b76d074f0bd7aeba2d2fae1483be49fb5dfeb00345f2bd5c27ab1','1.13 reference image changed')
    def with_header(decoded,minor,payload):
        h=bytearray(decoded['header']);h[23]=minor
        return {'events':canonical_events(bytes(h),payload)[0]}
    cases=[]
    need(beta[0x420D]==11,'Beta must store application version 1.11')
    for name,installed,incoming,expected,target in [
        ('original_1_12_to_beta_1_22',original,install,'staging_complete',beta),
        ('beta_1_13_to_beta_1_22',BETA_113,install,'staging_complete',beta),
        ('beta_1_14_to_beta_1_22',BETA_114,install,'staging_complete',beta),
        ('beta_1_15_to_beta_1_22',BETA_115,install,'staging_complete',beta),
        ('beta_1_16_to_beta_1_22',BETA_116,install,'staging_complete',beta),
        ('beta_1_17_to_beta_1_22',BETA_117,install,'staging_complete',beta),
        ('beta_1_18_to_beta_1_22',BETA_118,install,'staging_complete',beta),
        ('beta_1_19_to_beta_1_22',BETA_119,install,'staging_complete',beta),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_19',BETA_119,with_header(restore,12,original),'staging_complete',original),
        ('beta_1_20_to_beta_1_22',BETA_120,install,'staging_complete',beta),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_20',BETA_120,with_header(restore,12,original),'staging_complete',original),
        ('beta_1_21_to_beta_1_22',BETA_121,install,'staging_complete',beta),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_21',BETA_121,with_header(restore,12,original),'staging_complete',original),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_18',BETA_118,with_header(restore,12,original),'staging_complete',original),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_17',BETA_117,with_header(restore,12,original),'staging_complete',original),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_16',BETA_116,with_header(restore,12,original),'staging_complete',original),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_15',BETA_115,with_header(restore,12,original),'staging_complete',original),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_14',BETA_114,with_header(restore,12,original),'staging_complete',original),
        ('beta_1_22_reinstall_accepted',beta,install,'staging_complete',beta),
        ('OFFICIAL_KORG_1_12_UPDATER_over_beta_1_22',beta,with_header(restore,12,original),'staging_complete',original),
        ('official_korg_1_12_over_beta_1_13_still_rejected',BETA_113,with_header(restore,12,original),'error:ERR_VER',None),
        ('restore_header_1_15_from_beta_1_22',beta,restore,'staging_complete',original),
        ('restore_header_1_15_from_beta_1_13',BETA_113,restore,'staging_complete',original),
        ('original_1_12_same_version_rejected',original,with_header(restore,12,original),'error:ERR_VER',None)]:
        if installed is None: continue
        a=stage(installed,incoming);need(a.reason==expected,name+': '+str(a.reason))
        if target is not None:
            need(bytes(a.u.mem_read(0x20010000,0x30000))==target,'Staged payload mismatch: '+name)
        cases.append({'case':name,'result':a.reason,'installed_version_fixture':False})
    bad=bytearray(b''.join(e.packet for e in install['events']))
    # The first logical block follows the 35-byte system packet.
    bad[35+1+20]^=1
    a=stage(original,install,stream=bytes(bad))
    need(a.reason is not None and a.reason.startswith('error:') and a.reason!='staging_complete','Corrupt CRC accepted')
    cases.append({'case':'corrupt_payload_frame_rejected_before_install','result':a.reason})
    return {'cases':cases,'receiver_and_version_guard_unmodified':True}

def panel_after_native_install(a):
    a.data=lambda addr,size:bytes(a.u.mem_read(addr,size))
    a.put32=lambda addr,value:a.u.mem_write(addr,struct.pack('<I',value&0xFFFFFFFF))
    a.get32=lambda addr:struct.unpack('<I',a.data(addr,4))[0]
    a.texts=[];a.hook(0x2058A8,lambda:a.texts.append(a.string(a.u.reg_read(REGS[1]))))
    native.blank_pattern(a)
    a.put32(0x200029E4,0xFFFFFFFF);a.put32(0x200029F0,0xFFFFFFFF)
    a.u.mem_write(0x2000143E,struct.pack('<H',2048))
    panel.enter(a);panel.select(a,4)
    a.call(0x2059D0,(3,64,0,0));panel.check_display(a,'05 P050  ')
    native.set_step(a,4,[60,64,67],160)
    a.u.mem_write(native.PATTERN+6,b'\xff\xff');a.u.mem_write(0x20003C6C+0xDC,b'\6')
    ons=[]
    def on():ons.append(a.u.reg_read(REGS[0]));a.return_(a.u.reg_read(REGS[2]))
    a.hook(0x20AC54,on);a.hook(0x20AC70,lambda:a.return_(0))
    for adc,expected in [(0,0),(127,3)]:
        a.call(0x2059D0,(3,adc,0,0));ons.clear();a.u.mem_write(native.SLOTS,bytes(0x34))
        a.call(0x20B7BE,(4,));need(len(ons)==expected,'Installed panel to sequencer failed')
    return {'native_debounce_step5_display_50':True,'panel_to_sequencer_zero_100':True,
            'same_CPU_instance_as_receiver_installer_boot':True}

def install_transition(installed,decoded,expected,check_panel=False):
    a=stage(installed,decoded,full_FSK=True)
    need(a.reason=='staging_complete','Actual WAV FSK was rejected: '+str(a.reason))
    need(bytes(a.u.mem_read(0x20010000,0x30000))==expected,'FSK staging mismatch')
    installed_result=verify_installer(expected,staged_arm=a)
    # The shared baseline helper labels every prepared run as its historical
    # 1.10 fixture. This release uses the actual observed installed image.
    installed_result['installed_fixture']=False
    installed_result['installed_start_version']=f'{installed[0x420C]}.{installed[0x420D]:02}'
    sectors=installed_result['erased_16_KiB_sectors']
    need(0 not in sectors,'Bootloader sector would be erased')
    physical=bytes(a.u.mem_read(0x08000000,0x10000));external=bytes(a.verified_external_storage)
    actual=physical+external[:0xE000]+external[0x10000:0x1C000]+external[0x20000:0x26000]
    need(actual==expected,'Actual installed image differs from target')
    need(all(int(x['storage_offset'],16)+x['bytes']<=0x26000 for x in installed_result['external_storage_writes']),
         'Installer wrote outside firmware regions into user-data area')
    boot=verify_boot(expected,prepared_arm=a)
    cpu=verify_application_initialization(expected,prepared_arm=a)
    result={'actual_installed_start_sha256':sha(installed),'installed_payload_sha256':sha(actual),
            'installed_version_fixture':False,'WAV_file_SHA256':sha(decoded['data']),
            'native_FSK_halfcycles_consumed':a.half_index,'native_installer':installed_result,
            'native_reset_and_load':boot,'native_application_CPU_prefix':cpu,
            'bootloader_sector_erased':False,'writes_do_not_reach_user_data_area':True,
            'single_CPU_for_each_install_and_boot':True,
            'physical_analog_GPIO_SPI_flash_controller_not_tested':True}
    if check_panel:result['panel_after_native_install']=panel_after_native_install(a)
    return actual,result

def audio_with_page(original,beta):
    a=native.audio_machine(beta);b=native.audio_machine(beta)
    for m in (a,b):
        native.blank_pattern(m);m.call(0x208198,(0,1));native.prepare_clock(m)
        m.u.mem_write(native.PATTERN+6,b'\xff\xff')
        for step in range(16):native.set_step(m,step,[36+step,43+step,48+step,52+step,55+step,60+step],160)
        m.call(0x20EA70,(90,));m.call(0x2045F4,(1,));m.call(0x20EA84,(80,));m.call(0x20453C,(1,))
        m.put32(0x20000028,0x7FFFFFFF);m.put32(0x2000002C,0x7FFFFFFF)
    a.put32(0x200029E4,0xFFFFFFFF);a.put32(0x200029F0,0xFFFFFFFF)
    a.texts=[];a.hook(0x2058A8,lambda:a.texts.append(a.string(a.u.reg_read(REGS[1]))))
    panel.enter(a)
    for step in range(16):
        panel.select(a,step);a.call(0x2059D0,(3,[0,32,64,96,127][step%5],0,0))
    profile,valid=get_profile(a.data(native.PATTERN,1920));need(valid,'Panel profile invalid')
    b.u.mem_write(native.PATTERN,set_profile(b.data(native.PATTERN,1920),profile))
    panel.select(a,4);panel.check_display(a,'05 P100  ')
    output=bytearray()
    for visit in range(32):
        for m in (a,b):m.call(0x208CF8,(1,0))
        first=native.render_isr(a,512,service_every=64);second=native.render_isr(b,512,service_every=64)
        need(first==second,'Opening probability page changed six-voice FM/effects output')
        output.extend(first)
        for m in (a,b):
            for i in range(6):m.u.mem_write(0x20003C6C+i*16+11,b'\0')
    need(a.data(0x3F00,2)==b'\1\4','Playback changed probability page/selection')
    panel.check_display(a,'05 P100  ')
    return {'six_note_chords':True,'chorus_and_reverb_native_DSP':True,
            'stereo_frames_compared':len(output)//8,'PCM32_sha256':sha(output),
            'page_open_and_closed_outputs_sample_identical':True,'realtime_interrupt_deadlines_not_tested':True}

def main():
    original,beta,manifest=generate()
    # Core suites include the additional active-page MIDI/raw-frame regression.
    core.main(include_transport=False)
    base_report=json.loads((BASE/'reports/patch_verification.json').read_text())
    need(base_report['patched_logical_sha256']==sha(beta),'Core suite used another image')
    report={'release':'FM2 1.22 BETA','physical_hardware_tested':False,
            'beta_logical_sha256':sha(beta),'original_logical_sha256':sha(original),
            'groups':base_report['groups'].copy(),'status':'IN_PROGRESS',
            'files':manifest['install_and_restore_files']}
    out=BASE/'reports/release_verification.json'
    install=decode_wave(ROOT/INSTALL);restore=decode_wave(ROOT/RESTORE)
    def task(name,fn):
        start=time.monotonic()
        try:result=fn();result['status']='PASS'
        except Exception as e:
            report['status']='FAIL';result={'status':'FAIL','error':type(e).__name__+': '+str(e)}
            report['groups'][name]=result;out.write_text(json.dumps(report,indent=2)+'\n');raise
        result['seconds']=round(time.monotonic()-start,3)
        report['groups'][name]=result;out.write_text(json.dumps(report,indent=2)+'\n')
        print(name+': PASS ('+str(result['seconds'])+'s)',flush=True)
        return result
    task('release/version_and_CRC_guards',lambda:check_update_guards(original,beta,install,restore))
    task('release/original_reset_recovery',lambda:{'normal_beta':recovery_route(beta),
         'application_corrupted':recovery_route(beta,True)})
    task('release/six_voice_audio_with_page',lambda:audio_with_page(original,beta))
    forward={}
    def go():
        actual,result=install_transition(original,install,beta,True)
        forward['actual']=actual;return result
    task('release/actual_1_12_to_beta_1_22_WAV_FSK_install_boot_panel',go)
    for minor,image in BETAS.items():
        if image is None: continue
        def up(image=image,minor=minor):
            actual,result=install_transition(image,install,beta,True)
            need(actual==beta,f'1.{minor} -> 1.22 install mismatch');return result
        task(f'release/actual_beta_1_{minor}_to_beta_1_22_WAV_FSK_install_boot_panel',up)
    def back():
        actual,result=install_transition(forward['actual'],restore,original)
        need(actual==original,'Restoration was not byte-identical to original 1.12')
        result['all_196608_installed_bytes_equal_original_1_12']=True
        return result
    task('release/beta_1_22_to_exact_original_1_12_WAV_FSK_install_boot',back)
    def official():
        import zipfile,tempfile
        with zipfile.ZipFile(BASE/'reference/volca_fm2_updater_0112.zip') as z:
            name=[n for n in z.namelist() if n.lower().endswith('.wav')][0]
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'korg.wav';path.write_bytes(z.read(name))
                korg=decode_wave(path)
        actual,result=install_transition(forward['actual'],korg,original)
        need(actual==original,'Official Korg WAV did not restore exact 1.12 over beta 1.22')
        result['official_Korg_WAV_file']=name
        return result
    task('release/OFFICIAL_KORG_1_12_WAV_over_beta_1_22_FSK_install_boot',official)
    report.update(status='PASS_SOFTWARE_READY_FOR_EXPERIMENTAL_HARDWARE_TEST',
                  total_groups=len(report['groups']),passed_groups=sum(x['status']=='PASS' for x in report['groups'].values()),
                  hardware_validation_pending=True,
                  earlier_beta_images_not_available=SKIPPED)
    need(report['total_groups']==report['passed_groups'],'Not all groups passed')
    out.write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'ESITO_VERIFICHE.txt').write_text(report['status']+'\n'+
        str(report['passed_groups'])+'/'+str(report['total_groups'])+' gruppi PASS / groups PASS\n'+
        'Verifica software nell\'emulatore; la prova sullo strumento si fa con PROVE.txt.\n'+
        'Software check in the emulator; the test on the instrument uses TESTS_EN.txt.\n'+
        '\n'.join(v['status']+' '+k for k,v in report['groups'].items())+'\n')
    print(report['status']+' '+str(report['passed_groups'])+'/'+str(report['total_groups']),flush=True)

if __name__=='__main__':main()
