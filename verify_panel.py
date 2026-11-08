"""Run patched panel ARM with native button dispatch, glyphs and LED buffers.

Only hardware input is supplied as decoded scan/ADC fixtures. Display conversion,
profile writing and sequencer probability execute their actual instructions.
"""
import struct
import sys
from pathlib import Path

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'baseline'))
import reverse_checks as native
from arm_checks import REGS
from probability_format import set_profile,get_profile

def need(ok,msg):
    if not ok: raise AssertionError(msg)

def machine(img):
    a=native.Application(img)
    native.blank_pattern(a)
    a.u.mem_write(0x200029E4,struct.pack('<i',-1))
    a.u.mem_write(0x200029F0,struct.pack('<i',-1))
    a.u.mem_write(0x2000143E,struct.pack('<H',2048))
    a.texts=[]
    # Observe the input to the real ASCII -> segment converter, do not replace it.
    a.hook(0x2058A8,lambda:a.texts.append(a.string(a.u.reg_read(REGS[1]))))
    return a

def button(a,index,down):
    # Execute the original debouncer and its patched dispatch veneer.
    a.u.mem_write(0x200028EE,bytes([1<<index if down else 0]))
    for _ in range(3):scan(a)

def scan(a):
    # Completed panel serial response echoes the request sequence byte.
    a.u.mem_write(0x200028EC,a.data(0x200028DC,1))
    a.u.mem_write(0x200028ED,b'\0')
    a.call(0x20558C,(0,))

def enter(a):
    button(a,0,True)
    need(a.data(0x200029DA,1)==b'\x12','FUNC mapping/entry failed')
    # Hold FUNC while EDIT reaches the three-scan debounce threshold.
    a.u.mem_write(0x200028EE,b'\x11')
    for _ in range(3):scan(a)
    need(a.data(0x3F00,1)==b'\1','FUNC+EDIT did not enter probability')
    a.u.mem_write(0x200028EE,b'\0')
    for _ in range(3):scan(a)
    need(a.data(0x3F00,1)==b'\1','Release of entry combination closed page')

def raw_for_step(step):
    pos=0
    for i in range(step):pos+=1+((0x5BB7>>i)&1)
    return 1<<pos

def select(a,step):
    a.call(0x20FC18,(0,))
    a.call(0x20FC18,(raw_for_step(step),))
    need(a.data(0x3F01,1)==bytes([step]),'Wrong step selected')

def glyphs(a,text):
    # Native ASCII conversion independently produces the expected glyph bytes.
    a.u.mem_write(0x2003F000,text.encode()+b'\0')
    a.call(0x2058A8,(0x2003F020,0x2003F000,len(text)))
    return a.data(0x2003F020,len(text))

def check_display(a,text):
    need(a.texts[-1]==text,'ASCII readout mismatch: '+repr(a.texts[-1]))
    rows=struct.unpack('<8H',a.data(0x20002778,16))
    actual=bytes(sum(((rows[7-bit]>>char)&1)<<bit for bit in range(8)) for char in range(9))
    need(actual==glyphs(a,text),'Native segment buffer differs from expected glyphs')

def verify_page(original,patched):
    a=machine(patched); before=a.data(native.PATTERN,1920)
    enter(a);check_display(a,'01 P100  ')
    need(a.data(native.PATTERN,1920)==before,'Entering page modified pattern')
    for step in range(16):
        select(a,step);check_display(a,f'{step+1:02} P100  ')
        need(a.data(native.PATTERN,1920)==before,'Selecting step modified pattern')
        # Verify exactly one native blink mask; logical keys use original mapping.
        mapping=[15,14,11,10,7,6,3,2,13,12,9,8,5,4,1,0]
        need(a.get32(0x200028A8)&65535==1<<mapping[step],'Blink selection mask mismatch')
    button(a,0,True)
    need(a.data(0x3F00,1)==b'\0' and a.data(0x200029DA,1)==b'\0','FUNC failed to exit')
    need(a.get32(0x200028A8)&65535==0,'Blink remained after exit')
    need(a.data(native.PATTERN,1920)==before,'Exit modified pattern')
    return {'all_16_steps':True,'entry_release_exit':True,'pattern_unchanged_until_edit':True,
            'real_debouncer_and_native_glyph_buffer':True,'selected_LED_blink_mask':True}

def verify_slider(original,patched):
    a=machine(patched);enter(a)
    for step in range(16):native.set_step(a,step,[60,64,67],160)
    # Isolate backend observations, retaining the actual sequencer and RNG code.
    ons=[]
    a.u.mem_write(0x20003C6C+0xDC,b'\6')
    def on():ons.append(a.u.reg_read(REGS[0]));a.return_(a.u.reg_read(REGS[2]))
    a.hook(0x20AC54,on);a.hook(0x20AC70,lambda:a.return_(0))
    seen=set()
    for value in range(128):
        select(a,value%16)
        previous=a.data(native.PATTERN,1920)
        velocity_state=a.data(0x20002A20,4)
        a.call(0x2059D0,(3,value,0,0))
        p=a.data(native.PATTERN,1920); profile,valid=get_profile(p)
        need(valid,'ARM profile writer produced invalid metadata')
        pct=(value*100+63)//127
        need(profile[value%16]==pct,'Slider scale or digest wrong')
        need(p[:1888]==previous[:1888] and p[1916:]==previous[1916:], 'Notes/motion/header damaged')
        need(a.data(0x20002A20,4)==velocity_state,'Slider changed native velocity state')
        check_display(a,f'{value%16+1:02} P{pct:03}  ');seen.add(pct)
    need(seen==set(range(101)),'Not every integer percent is reachable')
    for value,expected in [(0,0),(127,3)]:
        select(a,5);a.call(0x2059D0,(3,value,0,0));ons.clear()
        a.u.mem_write(native.PATTERN+6,b'\xff\xff');a.u.mem_write(native.SLOTS,bytes(0x34))
        a.call(0x20B7BE,(5,));need(len(ons)==expected,'Panel value did not reach real probability hook')
    return {'all_128_slider_positions':True,'all_101_percentages_reachable':True,
            'unrelated_pattern_bytes_preserved':True,'native_velocity_not_changed':True,
            'panel_to_real_sequencer_zero_and_100':True}

def verify_regressions(original,patched):
    # Outside the page compare the newly wrapped native display, LED and knob
    # functions against original bytes, including preserved registers via call.
    for fn,args in [(0x20591C,(0x20002968,0x2003F000,0,0)),
                    (0x20548C,(3,8,1)),(0x2059D0,(3,64,0,0))]:
        a=machine(original);b=machine(patched)
        for m in [a,b]:
            m.u.mem_write(0x2003F000,b'HELLO123 \0')
            # The native text API has a fifth stack argument; this address is
            # untouched by OriginalARM.call's reset of SP/LR.
            m.u.mem_write(0x20006000,bytes(4));m.call(fn,args)
        need(a.data(0x20000000,0x5800)==b.data(0x20000000,0x5800),'Inactive wrapper regression')
    a=machine(patched);enter(a)
    select(a,4); a.call(0x2059D0,(3,64,0,0));check_display(a,'05 P050  ')
    # An unrelated display request must leave the modal readout visible.
    a.u.mem_write(0x2003F000,b'OTHER\0');a.u.mem_write(0x20006000,bytes(4))
    a.call(0x20591C,(0x20002968,0x2003F000,0,0));check_display(a,'05 P050  ')
    # A running clock retains step order/timing while the editor is open.
    native.prepare_clock(a)
    for step in range(16):native.set_step(a,step,[])
    for _ in range(32):a.call(0x208CF8,(1,0))
    need(a.data(0x3F01,1)==b'\4','Playback moved the selected editor step')
    check_display(a,'05 P050  ')
    return {'inactive_display_LED_velocity_match_original':True,
            'unrelated_text_cannot_overwrite_page':True,'32_clock_steps_while_editing':True}

def verify_persistence_and_controls(original,patched):
    a=machine(patched)
    # Short EDIT remains the original FM sound editor.
    button(a,4,True)
    need(a.data(0x3F00,1)==b'\0' and a.data(0x200029DA,1)==b'\x16','Normal EDIT changed')
    a=machine(patched);enter(a)
    # A real native ADC polling pass must reach the panel writer, without the
    # test calling the parameter handler directly.
    a.call(0x205AB0,(1,))
    select(a,7)
    a.u.mem_write(0x2000143E,struct.pack('<H',127<<5))
    a.call(0x205AB0,(0,));check_display(a,'08 P100  ')
    a.u.mem_write(0x2000143E,bytes(2))
    a.call(0x205AB0,(0,));check_display(a,'08 P000  ')
    need(get_profile(a.data(native.PATTERN,1920))[0][7]==0,'Native ADC polling did not write probability')
    # PLAY starts and stops while the editor retains its selected step/value.
    a.call(0x20FAA0,(3,1));need(a.get32(0x20003F8C)==1,'PLAY did not start')
    a.call(0x20FAA0,(3,1));need(a.get32(0x20003F8C)==0,'PLAY did not stop')
    check_display(a,'08 P000  ')
    p=a.data(native.PATTERN,1920)
    button(a,0,True)
    s=native.Storage(patched)
    s.store(3,p);s.flush()
    reboot=native.Storage(patched,s.flash)
    accepted,loaded=reboot.load(3)
    need(accepted==1 and loaded==p,'Panel-created profile did not survive journal/reboot')
    # Corrupted metadata is shown as the same 100% fallback used by playback;
    # selecting a step is read-only, editing rebuilds a complete valid profile.
    b=machine(patched);bad=bytearray(p);bad[1912]^=1
    b.u.mem_write(native.PATTERN,bytes(bad));enter(b);check_display(b,'01 P100  ')
    need(b.data(native.PATTERN,1920)==bad,'Entry repaired metadata without an edit')
    b.call(0x2059D0,(3,64,0,0));profile,valid=get_profile(b.data(native.PATTERN,1920))
    need(valid and profile==[50]+[100]*15,'First edit did not rebuild invalid metadata')
    return {'native_ADC_poll_to_profile':True,'PLAY_start_stop_in_page':True,
            'normal_EDIT_retained':True,'panel_profile_NOR_reboot_exact':True,
            'corrupt_profile_display_and_first_edit':True}

def verify_midi_and_raw_flags(original,patched):
    a=machine(patched);enter(a)
    # A marker combined with actual key bits is not the no-data sentinel.
    for step in range(16):
        a.call(0x20FC18,(0,))
        a.call(0x20FC18,(0x80000000|raw_for_step(step),))
        need(a.data(0x3F01,1)==bytes([step]),'Flagged raw key frame was dropped')
    a.call(0x20FC18,(0x80000000,))
    need(a.data(0x3F01,1)==b'\x0f','No-data sentinel changed selection')
    a.call(0x2059D0,(3,64,0,0))
    before=a.data(native.PATTERN,1920)
    a.call(0x2080A4,(1,));a.call(0x200148E4,(1,))
    for v in [0xB0,41,22]:a.call(0x200146EC,(1,v))
    need(a.data(native.PATTERN,1920)==before,'MIDI CC velocity edited probability')
    need(a.get32(0x20002A20)==22,'MIDI CC velocity lost its original meaning')
    check_display(a,'16 P050  ')
    return {'flagged_raw_frames_all_16_steps':True,'no_data_marker_ignored':True,
            'actual_MIDI_parser_CC41_preserved':True,'MIDI_does_not_edit_probability':True}

TASKS=[('panel/page',verify_page),('panel/slider',verify_slider),('panel/regression',verify_regressions),
       ('panel/persistence_and_controls',verify_persistence_and_controls),
       ('panel/MIDI_and_raw_flags',verify_midi_and_raw_flags)]

if __name__=='__main__':
    from build_patch import build
    o,p,*_=build()
    for name,fn in TASKS:print(name,fn(o,p),flush=True)
