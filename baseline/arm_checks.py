"""Execute unmodified original ARM routines with explicitly modeled I/O.

This is CPU-level verification, not an emulator of the physical instrument.
No device access and no output firmware/WAV. All fixtures stay in RAM.
"""
import struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE,UC_HOOK_MEM_WRITE,UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC

REGS=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
STOP=0x002ff000


class OriginalARM:
    def __init__(self,logical):
        self.logical=logical
        self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        for addr,size in [(0,0x4000),(0x200000,0x10000),(STOP,0x1000),
                          (0x20000000,0x40000),(0x40000000,0x30000),(0xe000e000,0x2000)]:
            self.u.mem_map(addr,size)
        self.u.mem_write(0x200000,logical[:0x10000])
        self.u.reg_write(UC_ARM_REG_SP,0x20006000)
        self.hooks=[]
        self.reason=None

    def hook(self,addr,fn):
        def callback(uc,pc,size,user):
            fn()
        h=self.u.hook_add(UC_HOOK_CODE,callback,begin=addr,end=addr)
        self.hooks.append(h)
        return h

    def return_(self,value=None):
        if value is not None:
            self.u.reg_write(UC_ARM_REG_R0,value)
        self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))

    def string(self,addr,maxlen=100):
        return bytes(self.u.mem_read(addr,maxlen)).split(b'\0',1)[0].decode('ascii',errors='replace')

    def call(self,addr,args=(),limit=2000000):
        self.reason=None
        self.u.reg_write(UC_ARM_REG_SP,0x20006000)
        self.u.reg_write(UC_ARM_REG_LR,STOP|1)
        for reg,value in zip(REGS,args):
            self.u.reg_write(reg,value)
        self.u.emu_start(addr|1,STOP,count=limit)
        pc=self.u.reg_read(UC_ARM_REG_PC)
        if pc!=STOP and self.reason is None:
            raise RuntimeError(f'Instruction budget exceeded at {pc:08X}')
        return self.u.reg_read(UC_ARM_REG_R0)

    def stop(self,reason):
        self.reason=reason
        self.u.emu_stop()

    def receiver_stubs(self):
        self.byte_stream=b''
        self.byte_pos=0
        self.u.mem_write(0x200026e8,struct.pack('<I',1))
        self.hook(0x202458,lambda:self.return_(0)) # Background UI task.
        self.hook(0x2027b8,lambda:self.return_(0x7fffffff)) # Preamble duration already established.
        def byte():
            if self.byte_pos>=len(self.byte_stream):
                self.stop('input_exhausted')
                return
            value=self.byte_stream[self.byte_pos]
            self.byte_pos+=1
            self.return_(value)
        self.hook(0x2029d0,byte) # Demodulated bytes, not the frame parser.
        self.hook(0x20281c,lambda:self.stop('error:'+self.string(self.u.reg_read(UC_ARM_REG_R0))))

    def receive(self,packet,size):
        self.byte_stream=packet
        self.byte_pos=0
        self.u.mem_write(0x20001000,b'\x5a'*(size+16))
        self.call(0x2029ea,(0x20001000,size),limit=100000)
        return bytes(self.u.mem_read(0x20001000,size)),self.reason,self.byte_pos

    def duration_input(self,bits,timing_scale=1.0):
        """Supply measured-WAV half-cycle durations at the capture-ring boundary.

        Native preamble synchronization, bit classification, byte assembly,
        frame CRC and fill decoding all execute, without replacements.
        Timer tick rate is the software's nominal 108 ticks per microsecond.
        Analog threshold crossings and capture interrupts are not simulated.
        """
        self.half_index=0
        self.source_sample_count=0
        self.capture_ticks=0
        self.hook(0x202458,lambda:self.return_(0))
        self.hook(0x20281c,lambda:self.stop('error:'+self.string(self.u.reg_read(UC_ARM_REG_R0))))
        def capture():
            if self.half_index>=len(bits)*2:
                self.stop('capture_input_exhausted')
                return
            self.source_sample_count+=5 if bits[self.half_index//2] else 10
            ticks=round(self.source_sample_count*(108000000/44100)*timing_scale)
            delta=ticks-self.capture_ticks
            self.capture_ticks=ticks
            flag=0x80000000 if self.half_index%2 else 0
            self.half_index+=1
            self.u.mem_write(0x40000c24,struct.pack('<I',ticks&0xffffffff))
            self.return_(delta|flag)
        self.hook(0x2027b8,capture)


def verify_receivers(logical,events):
    arm=OriginalARM(logical)
    arm.receiver_stubs()
    counts={'header':0,'data':0,'fill_ff':0,'fill_30':0}
    for index,event in enumerate(events):
        n=32 if index==0 else 512
        expected=event.packet[1:33] if index==0 else event.output
        actual,reason,consumed=arm.receive(event.packet,n)
        if reason or actual!=expected or consumed!=len(event.packet):
            raise RuntimeError(f'Original ARM receiver failed event {index}: {reason}, {consumed}')
        key='header' if index==0 else ('data' if event.packet[0]==0xa9 else 'fill_'+format(event.packet[1],'02x'))
        counts[key]+=1
    negative=[]
    for index,event in enumerate(events):
        if event.packet[0]!=0xa9:
            continue
        for label,offset in [('first_data',1),('last_data',len(event.packet)-3),
                             ('crc_low',len(event.packet)-2),('crc_high',len(event.packet)-1)]:
            bad=bytearray(event.packet);bad[offset]^=1
            _,reason,_=arm.receive(bytes(bad),32 if index==0 else 512)
            if reason is None or not reason.startswith('error:'):
                raise RuntimeError('Original ARM receiver accepted bad CRC')
            negative.append({'event':index,'fault':label,'result':reason})
    for value in (0xff,0x30):
        _,reason,_=arm.receive(bytes([0x4e,value,value^254]),512)
        if reason is None or not reason.startswith('error:'):
            raise RuntimeError('Original ARM receiver accepted wrong complement')
        negative.append({'fault':f'fill_{value:02x}_wrong_complement','result':reason})
    return {'executed_original_entry':'0x002029EA','all_original_events':counts,
            'positive_events':len(events),'negative_tests':negative,
            'modeled_functions':{'0x00202458':'background UI task returns',
                '0x002027B8':'preamble duration ready',
                '0x002029D0':'demodulated byte input from original WAV',
                '0x0020281C':'stop at original fatal-error handler'},
            'frame_crc_and_fill_parser_unmodified':True,
            'physical_fsk_input_not_emulated':True}


def stage_receiver(logical,events,current_minor,stream=None,capture_bits=None):
    arm=OriginalARM(logical)
    if capture_bits is None:
        arm.receiver_stubs()
    else:
        arm.duration_input(capture_bits)
    # Only the installed version field is a fixture, not a genuine old firmware.
    arm.u.mem_write(0x20420d,bytes([current_minor]))
    arm.byte_stream=stream if stream is not None else b''.join(e.packet for e in events)
    arm.byte_pos=0
    if capture_bits is None:
        arm.hook(0x202834,lambda:arm.return_(0)) # Physical input synchronization.
    arm.hook(0x203734,lambda:arm.return_(0x20005000)) # Display bitmap.
    arm.staging_stop_hook=arm.hook(0x2024c8,lambda:arm.stop('staging_complete'))
    arm.call(0x202ab4,(0,1),limit=250000000 if capture_bits is not None else 20000000)
    return arm


def verify_staging(logical,events):
    same=stage_receiver(logical,events,12)
    if same.reason!='error:ERR_VER':
        raise RuntimeError('Same-version check unexpected: '+str(same.reason))
    older=stage_receiver(logical,events,10)
    if older.reason!='staging_complete':
        raise RuntimeError('Original staging failed: '+str(older.reason))
    got=bytes(older.u.mem_read(0x20010000,0x30000))
    if got!=logical or older.byte_pos!=sum(len(e.packet) for e in events):
        raise RuntimeError('Staged image differs from original logical image')
    malformed=[]
    from original_image import crc16
    for name,offset in [('system_magic',0),('device_tag',16),('type',20)]:
        p=bytearray(events[0].packet)
        p[1+offset]^=4
        p[-2:]=struct.pack('<H',crc16(p[1:-2]))
        arm=stage_receiver(logical,events,10,bytes(p))
        if arm.reason is None or not arm.reason.startswith('error:'):
            raise RuntimeError('Invalid system header accepted: '+name)
        malformed.append({'fault':name,'result':arm.reason})
    return {'executed_original_entry':'0x00202AB4','version_check_enabled':True,
            'same_version_1_12':same.reason,
            'installed_1_10_fixture_incoming_exact_original_1_12':older.reason,
            'incoming_events_consumed':len(events),'staging_address':'0x20010000',
            'staged_bytes_compared':len(got),'exact_match':True,
            'malformed_header_valid_transport_crc_tests':malformed,
            'additional_modeled_functions':{'0x00202834':'physical synchronization succeeds',
                '0x00203734':'display rendering returns bitmap pointer',
                '0x002024C8':'stop before storage writes'},
            'installed_version_is_a_test_fixture':True}


def runtime_storage(logical):
    data=bytearray(b'\xff'*0x40000)
    data[0:0xe000]=logical[0x10000:0x1e000]
    data[0x10000:0x1c000]=logical[0x1e000:0x2a000]
    data[0x20000:0x26000]=logical[0x2a000:0x30000]
    return data


def verify_boot(logical,prepared_arm=None):
    def boot(fault=None,mode=0,prepared=None):
        arm=prepared if prepared is not None else OriginalARM(logical)
        storage=bytearray(arm.verified_external_storage) if prepared is not None else runtime_storage(logical)
        if fault=='ff14_data':
            storage[0x20000+0x120]^=1
        elif fault=='ff11_magic':
            storage[0]^=1
        elif fault=='ff12_magic':
            storage[0x4000]^=1
        elif fault=='ff13_magic':
            storage[0x10000]^=1
        elif fault=='ff11_body':
            storage[0x120]^=1
        arm.u.mem_write(0x20000000,b'\xa5'*0x40000)
        # Clocks, ADC, timers, GPIO, SPI initiation/polling and keys.
        peripheral_returns={0x20047c:0,0x200738:0,0x20070c:0,0x203654:0,
            0x200b28:0,0x2037e0:mode,0x200b44:0,0x200e00:1,0x200778:0,0x200b7c:1}
        for addr,value in peripheral_returns.items():
            arm.hook(addr,lambda v=value:arm.return_(v))
        reads=[]
        def read_storage():
            dest,source,size=(arm.u.reg_read(reg) for reg in REGS[:3])
            if source+size>len(storage):
                raise RuntimeError('SPI fixture read outside memory')
            arm.u.mem_write(dest,bytes(storage[source:source+size]))
            reads.append({'storage_offset':hex(source),'runtime_address':hex(dest),'bytes':size})
            arm.return_(1)
        arm.hook(0x200ec8,read_storage)
        observations={}
        def at_main():
            observations['reset_cleared_256_KiB']=bytes(arm.u.mem_read(0x20000000,0x40000))==bytes(0x40000)
        arm.hook(0x200598,at_main)
        arm.app_entry_stop_hook=arm.hook(0x204240,lambda:arm.stop('original_application_entry_reached'))
        def recovery():
            observations['recovery_arguments']=[arm.u.reg_read(reg) for reg in REGS[:2]]
            arm.stop('original_recovery_path_reached')
        arm.hook(0x202cfc,recovery)
        arm.call(0x2000e4,(),limit=3000000)
        observations['result']=arm.reason
        observations['storage_reads']=reads
        if fault is None:
            observations['runtime_sections_exact']={
                'FF11':bytes(arm.u.mem_read(0,0x4000))==logical[0x10000:0x14000],
                'FF12':bytes(arm.u.mem_read(0x20006000,0xa000))==logical[0x14000:0x1e000],
                'FF13':bytes(arm.u.mem_read(0x20010000,0xc000))==logical[0x1e000:0x2a000]}
            observations['FF14_exact_if_mode_requires_it']=bytes(arm.u.mem_read(0x20020000,0x6000))==(logical[0x2a000:0x30000] if mode==0xff else bytes(0x6000))
        return observations
    good=boot(prepared=prepared_arm)
    if good['result']!='original_application_entry_reached' or not good['reset_cleared_256_KiB'] or not all(good['runtime_sections_exact'].values()) or not good['FF14_exact_if_mode_requires_it']:
        raise RuntimeError('Original boot verification failed: '+str(good))
    if prepared_arm is not None:
        return good
    extended=boot(mode=0xff)
    if extended['result']!='original_application_entry_reached' or not extended['FF14_exact_if_mode_requires_it']:
        raise RuntimeError('Additional native FF14 loading path failed')
    negative=[]
    for fault in ('ff14_data','ff11_magic','ff12_magic','ff13_magic'):
        result=boot(fault,mode=0xff if fault=='ff14_data' else 0)
        if result['result']!='original_recovery_path_reached':
            raise RuntimeError('Native boot did not request recovery for '+fault)
        negative.append({'fault':fault,**result})
    header_only=boot('ff11_body')
    if header_only['result']!='original_application_entry_reached':
        raise RuntimeError('Native normal-boot header-only behavior differs from disassembly')
    return {'executed_from_original_reset_vector':'0x002000E5',
            'positive_normal_boot':good,'positive_native_mode_FF_fixture':extended,
            'negative_boot_fixtures':negative,
            'normal_boot_does_not_detect_FF11_body_fault':header_only,
            'modeled_peripherals':['clock/ADC/timer/GPIO initialization','key-mode return: normal 0 or additional FF test fixture',
                'SPI storage initialization and completion','SPI reads from original section bytes',
                'no physical interrupts or analog audio'],
            'native_reset_clear_header_checks_conditional_FF14_checksum_and_dispatch_executed':True,
            'complete_application_execution':False,'physical_device_boot':False}


def verify_application_initialization(logical,prepared_arm=None):
    arm=prepared_arm if prepared_arm is not None else OriginalARM(logical)
    if prepared_arm is None:
        for dest,lo,hi in [(0,0x10000,0x14000),(0x20006000,0x14000,0x1e000),
                           (0x20010000,0x1e000,0x2a000)]:
            arm.u.mem_write(dest,logical[lo:hi])
    else:
        arm.u.hook_del(arm.app_entry_stop_hook)
    pointers=struct.unpack_from('<10I',logical,0x1e000+0x6460)
    seen=[]
    for p in pointers:
        arm.hook(p&~1,lambda p=p:seen.append(hex(p))) # Observe; execute original instruction.
    arm.hook(0x204264,lambda:arm.stop('CPU_initialization_prefix_complete'))
    if prepared_arm is None:
        arm.call(0x204240,(0,),limit=1000000)
    else:
        arm.reason=None
        arm.u.emu_start(0x204241,STOP,count=1000000)
    vtor=struct.unpack('<I',arm.u.mem_read(0xe000ed08,4))[0]
    data=bytes(arm.u.mem_read(0x200058fc,0x28))
    expected=logical[0x1e000+0x6488:0x1e000+0x6488+0x28]
    if arm.reason!='CPU_initialization_prefix_complete' or vtor!=0x204000 or data!=expected or seen!=list(map(hex,pointers))*2:
        raise RuntimeError('Unmodified application CPU initialization failed')
    return {'entry':'0x00204240','stop_before_peripheral_initialization':'0x00204264',
            'VTOR_written_by_original_code':hex(vtor),'data_destination':'0x200058FC',
            'data_source':'0x20016488','data_bytes_compared':40,'data_exact':True,
            'constructor_addresses_executed':seen,'constructors_stubbed':False,
            'application_audio_and_UI_loop_executed':False}


def verify_installer(logical,staged_arm=None):
    from original_image import sha
    def install(force_four,prepared=None):
        arm=prepared if prepared is not None else OriginalARM(logical)
        u=arm.u
        u.mem_map(0x08000000,0x10000)
        installed=bytearray(u.mem_read(0x200000,0x10000))
        # Only installed-flash fixtures change. Incoming/staged original stays exact.
        if force_four:
            for off in (0x3fff,0x7fff,0xbfff,0xffff):
                installed[off]^=1
        u.mem_write(0x200000,bytes(installed))
        u.mem_write(0x08000000,bytes(installed))
        if prepared is None:
            u.mem_write(0x20010000,logical)
            u.mem_write(0x200026cc,struct.pack('<I',0x20010000)) # Receiver's completed staging pointer.
        storage=bytearray(b'\xff'*0x40000)
        writes=[]
        def store():
            dest,src,size=(u.reg_read(reg) for reg in REGS[:3])
            data=bytes(u.mem_read(src,size))
            if dest+size>len(storage):
                raise RuntimeError('External write outside fixture')
            storage[dest:dest+size]=data
            writes.append({'storage_offset':hex(dest),'staging_address':hex(src),'bytes':size,'sha256':sha(data)})
            arm.return_(1)
        arm.hook(0x2023e4,store) # SPI erase/program transport modeled, caller original.
        arm.hook(0x203734,lambda:arm.return_(0x20005000))
        arm.hook(0x202458,lambda:arm.return_(0))
        erased=[]
        programmed=[]
        def read_register(uc,access,addr,size,value,user):
            if addr==0x40023c10:
                cr=struct.unpack('<I',u.mem_read(addr,4))[0]
                u.mem_write(addr,struct.pack('<I',cr&~(1<<16))) # STRT self-clears.
            elif addr==0x40023c0c:
                u.mem_write(addr,bytes(4)) # Controller completes with no error in this model.
        def write_register(uc,access,addr,size,value,user):
            if addr==0x40023c10 and value&(1<<16) and value&2:
                sector=(value>>3)&15
                if sector>=4:
                    raise RuntimeError('Unexpected flash sector')
                erased.append(sector)
                u.mem_write(0x08000000+sector*0x4000,b'\xff'*0x4000)
                u.mem_write(0x200000+sector*0x4000,b'\xff'*0x4000)
        def write_flash(uc,access,addr,size,value,user):
            if size!=4:
                raise RuntimeError('Unexpected physical flash write size')
            off=addr-0x08000000
            old=int.from_bytes(u.mem_read(addr,size),'little')
            if old&value!=value:
                raise RuntimeError('Flash programming attempted a 0-to-1 transition')
            programmed.append(off)
            u.mem_write(0x200000+off,value.to_bytes(size,'little')) # Physical alias relation.
        u.hook_add(UC_HOOK_MEM_READ,read_register,begin=0x40023c0c,end=0x40023c10)
        u.hook_add(UC_HOOK_MEM_WRITE,write_register,begin=0x40023c10,end=0x40023c10)
        u.hook_add(UC_HOOK_MEM_WRITE,write_flash,begin=0x08000000,end=0x0800ffff)
        # Native installer copies its own flash-writing code into SRAM before use.
        relocated_base=0x20020000
        arm.hook(relocated_base+(0x2ce-0x10c),lambda:arm.stop('native_flash_loop_complete'))
        if prepared is None:
            arm.call(0x2024c8,(0,),limit=4000000)
        else:
            arm.u.hook_del(arm.staging_stop_hook)
            arm.reason=None
            arm.u.emu_start(0x2024c9,STOP,count=4000000) # Continue original updater state/stack.
        if arm.reason!='native_flash_loop_complete':
            raise RuntimeError('Native flash installer did not complete: '+str(arm.reason))
        actual=bytes(u.mem_read(0x08000000,0x10000))
        alias=bytes(u.mem_read(0x200000,0x10000))
        if actual!=logical[:0x10000] or alias!=actual:
            raise RuntimeError('Modeled installed flash differs from original')
        expected_storage=runtime_storage(logical)
        for lo,hi in [(0,0xe000),(0x10000,0x1c000),(0x20000,0x26000)]:
            if storage[lo:hi]!=expected_storage[lo:hi]:
                raise RuntimeError('Native external-storage routing mismatch')
        expected_sectors=[i for i in range(4) if installed[i*0x4000:(i+1)*0x4000]!=logical[i*0x4000:(i+1)*0x4000]]
        if erased!=expected_sectors or len(programmed)!=len(expected_sectors)*4096:
            raise RuntimeError('Native flash erase/write plan mismatch: '+str(erased))
        arm.verified_external_storage=storage
        return {'installed_fixture':'installed version-field fixture 1.10' if prepared is not None else ('one differing byte in each sector' if force_four else 'already identical'),
            'external_storage_writes':writes,'external_storage_sections_exact':True,
            'executed_original_installer':'0x002024C8','native_relocated_flasher':'0x20020158',
            'erased_16_KiB_sectors':erased,'native_word_program_operations':len(programmed),
            'physical_and_alias_flash_exact':True,'installed_main_sha256':sha(actual)}
    if staged_arm is not None:
        return install(False,staged_arm)
    return {'identical_image_skip_write_path':install(False),
            'four_sector_erase_program_path':install(True),
            'native_sector_compare_erase_program_loops_executed':True,
            'modeled_IO':['SPI driver writes','display','flash controller always completes without error',
                          'physical flash / code alias coherence'],
            'power_loss_busy_time_wear_protection_not_emulated':True,
            'physical_device_programmed':False}


def verify_integrated(logical,events,capture_bits=None):
    arm=stage_receiver(logical,events,10,capture_bits=capture_bits)
    if arm.reason!='staging_complete' or bytes(arm.u.mem_read(0x20010000,len(logical)))!=logical:
        raise RuntimeError('Integrated run staging mismatch')
    stages={'receive_and_stage':{'logical_bytes_exact':len(logical)}}
    if capture_bits is None:
        stages['receive_and_stage']['consumed_packet_bytes']=arm.byte_pos
    else:
        stages['receive_and_stage'].update({'native_FSK_bit_byte_and_sync_routines_executed':True,
            'captured_half_cycles_consumed':arm.half_index,'original_waveform_samples_consumed':arm.source_sample_count,
            'modeled_timer_ticks_per_second':108000000,'physical_ADC_and_capture_interrupts':False})
    stages['install']=verify_installer(logical,staged_arm=arm)
    stages['reset_and_load']=verify_boot(logical,prepared_arm=arm)
    stages['application_CPU_initialization']=verify_application_initialization(logical,prepared_arm=arm)
    return {'single_ARM_instance':True,'original_receiver_installer_boot_application_prefix':stages,
            'incoming_firmware_original_1_12_unmodified':True,
            'installed_version_field_fixture_1_10_not_genuine_1_10_binary':True,
            'all_storage_and_controller_IO_modeled':True,
            'physical_instrument_or_full_audio_engine_test':False}
