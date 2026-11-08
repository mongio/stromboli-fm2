"""Native tests of Korg volca FM2 1.12; no firmware patches or device access.

All entry points execute the original bytes. Hooks are named test boundaries,
listed in each report. RAM fixtures and flash-device models are synthetic.
"""
import hashlib
import random
import struct
from arm_checks import OriginalARM, REGS

PATTERN = 0x2001E12C
CLOCK = 0x20003198
SLOTS = 0x20003DC4
ENGINE = 0x200040BC
ROOT = 0x2001D08C
JOURNAL = 0x20002D9C
SCRATCH = 0x2003C000


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Application(OriginalARM):
    def __init__(self, logical):
        super().__init__(logical)
        for dest, lo, hi in [(0, 0x10000, 0x14000),
                             (0x20006000, 0x14000, 0x1E000),
                             (0x20010000, 0x1E000, 0x2A000)]:
            self.u.mem_write(dest, logical[lo:hi])
        # Execute the complete original CPU startup prefix: VTOR, constructors,
        # 40-byte initialized data (including PRNG seeds), constructors again.
        stop = self.hook(0x204264,lambda: self.stop('application_cpu_prefix_complete'))
        self.call(0x204240,(0,))
        need(self.reason == 'application_cpu_prefix_complete','CPU startup prefix failed')
        self.u.hook_del(stop)

    def put32(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value & 0xFFFFFFFF))

    def get32(self, address):
        return struct.unpack('<I', bytes(self.u.mem_read(address, 4)))[0]

    def data(self, address, size):
        return bytes(self.u.mem_read(address, size))


def blank_pattern(a, address=PATTERN):
    a.call(0x20852C, (address,))
    return a.data(address, 1920)


def pattern_fixture(a, seed):
    p = bytearray(blank_pattern(a, SCRATCH))
    p[9] = seed % 64
    p[6:8] = p[12:14] = b'\xff\xff'
    p[15] = 16
    for step in range(16):
        for voice in range(6):
            at = 80 + step * 112
            struct.pack_into('<H', p, at + voice * 2,
                             24 + (seed + step + voice) % 80)
            p[at + 18 + voice] = 50 + (seed + step + voice) % 77
            p[at + 24 + voice] = 0xA0
            for lane in range(13):
                p[at + 43 + lane * 5:at + 48 + lane * 5] = bytes(
                    (seed + step + voice + lane + j) % 128 for j in range(5))
    return bytes(p)


def set_step(a, index, notes, gate=32, velocity=100):
    at = PATTERN + 80 + index * 112
    a.u.mem_write(at, struct.pack('<6H', *(list(notes) + [0] * (6-len(notes)))))
    a.u.mem_write(at + 18, bytes([velocity] * len(notes) + [0] * (6-len(notes))))
    gates = [gate] * len(notes) if isinstance(gate, int) else list(gate)
    a.u.mem_write(at + 24, bytes(gates + [0] * (6-len(gates))))


def sequencer_observer(logical, capacity=6):
    a = Application(logical)
    blank_pattern(a)
    a.u.mem_write(PATTERN + 6, b'\xff\xff')
    a.u.mem_write(0x20003C6C + 0xDC, bytes([capacity]))
    a.events = []
    def on():
        args = [a.u.reg_read(r) for r in REGS[:3]]
        a.events.append(['on', args])
        a.return_(args[2])
    def off():
        a.events.append(['off', [a.u.reg_read(r) for r in REGS[:2]]])
        a.return_(0)
    a.hook(0x20AC54, on)
    a.hook(0x20AC70, off)
    return a


def prepare_clock(a, active_mask=0xFFFF):
    a.put32(0x20003F8C, 1)
    a.u.mem_write(0x20003E34, b'\xff')
    for offset, value in [(0xB, 255), (0xE, 1), (0x1C, 1),
                          (0x1A, 255), (0x26, 255)]:
        a.u.mem_write(CLOCK + offset, bytes([value]))
    a.u.mem_write(PATTERN + 12, struct.pack('<H', active_mask))
    a.u.mem_write(PATTERN + 15, bytes([active_mask.bit_count()]))


def verify_pattern_format(logical):
    a = Application(logical)
    p = blank_pattern(a)
    need(p[:4] == b'PTST' and p[4:6] == b'\xe8\x4e' and p[-4:] == b'PTED',
         'Native pattern initializer disagrees with recovered format')
    cases = []
    original = pattern_fixture(a, 17)
    a.u.mem_write(SCRATCH, original)
    for name, offset in [('valid', None), ('start_magic', 0),
                         ('format_tag', 4), ('end_magic', 1919)]:
        q = bytearray(original)
        if offset is not None:
            q[offset] ^= 1
        a.u.mem_write(SCRATCH, bytes(q))
        a.u.mem_write(SCRATCH + 0x1000, b'\xA5' * 1920)
        r = a.call(0x20014964, (SCRATCH + 0x1000, SCRATCH))
        need(r == (1 if offset is None else 0), 'Pattern validator: ' + name)
        if offset is None:
            need(a.data(SCRATCH + 0x1000, 1920) == original, 'Valid pattern altered')
        else:
            need(a.data(SCRATCH + 0x1000, 1920) == b'\xA5' * 1920,
                 'Malformed pattern copied')
        cases.append({'case': name, 'accepted': bool(r)})
    legacy = bytearray(0x660)
    legacy[:4] = b'PTST'; legacy[4:6] = b'\xb8\x33'; legacy[-4:] = b'PTED'
    legacy[6:8] = legacy[12:14] = b'\xff\xff'; legacy[15] = 16
    for step in range(16):
        at = 64+step*96
        struct.pack_into('<3H',legacy,at,48+step,55+step,60+step)
        legacy[at+9:at+12] = b'\x01\x01\x01'
        legacy[at+12:at+15] = b'\x20\x20\x20'
    a.u.mem_write(SCRATCH,bytes(legacy))
    need(a.call(0x20014964,(SCRATCH+0x1000,SCRATCH)) == 1,'Legacy pattern conversion failed')
    converted = a.data(SCRATCH+0x1000,1920)
    need(converted[:4] == b'PTST' and converted[4:6] == b'\xe8\x4e' and
         converted[-4:] == b'PTED','Converted pattern markers wrong')
    for step in range(16):
        at = 80+step*112
        need(struct.unpack_from('<6H',converted,at) ==
             (48+step,55+step,60+step,0,0,0),'Legacy notes not expanded to six')
        need(converted[at+18:at+24] == bytes([64,64,64,0,0,0]),'Legacy velocity conversion wrong')
    return {'native_entries': ['0x0020852C', '0x20014964'],
            'pattern_bytes': 1920, 'header_bytes': 80, 'step_bytes': 112,
            'steps': 16, 'notes_per_step': 6, 'motion_lanes': 13,
            'motion_points_per_lane_per_step': 5, 'cases': cases,
            'legacy_1632_to_1920_byte_conversion':True,
            'modeled_functions': {}}


def verify_sequence(logical):
    a = sequencer_observer(logical)
    snapshots = []
    for index, notes, gate, expected in [
        (0, [60], 32, ['on']), (1, [60], 32, []),
        (2, [62], 32, ['off', 'on']), (3, [62], 0xA0, ['off', 'on']),
        (4, [62], 0, ['off']),
        (5, [60,64,67,72,76,79], 127, ['on'] * 6),
        (6, [], 32, ['off'] * 6)]:
        set_step(a, index, notes, gate)
        a.events = []
        a.call(0x20B7BE, (index,))
        need([e[0] for e in a.events] == expected, 'Sequence transition failed')
        snapshots.append({'step': index, 'events': a.events,
                          'logical_slots': list(a.data(SLOTS, 24))})
    mono = sequencer_observer(logical, capacity=1)
    set_step(mono, 0, [60,64,67])
    mono.call(0x20B7BE, (0,))
    need(len(mono.events) == 1 and mono.events[0][1][0] == 60,
         'Capacity-one sequencer failed')
    muted = sequencer_observer(logical)
    set_step(muted, 0, [60])
    muted.u.mem_write(PATTERN + 6, b'\xfe\xff')
    muted.call(0x20B7BE, (0,))
    need(muted.events == [], 'Muted step emitted a note')
    gate_tests = []
    for duration in [1,2,32,72,126,127]:
        b = sequencer_observer(logical)
        set_step(b, 0, [60], duration)
        b.call(0x20B7BE, (0,))
        b.events = []
        for t in range(duration):
            b.call(0x20BB28)
            if t < duration-1:
                need(not b.events, 'Gate released early')
        # The isolated counter also decrements TIE=127. In a running sequence,
        # the next step refreshes/retains that slot before 127 ticks elapse;
        # status 2 exempts it from boundary release, tested in verify_clock.
        need(len(b.events) == 1, 'Gate expiry failed')
        gate_tests.append({'duration': duration, 'off_events': len(b.events),
                           'isolated_counter_calls': duration})
    return {'native_entries': ['0x0020B7BE','0x0020B774','0x0020BB28','0x0020BB50'],
            'direct_apply_snapshots': snapshots, 'gate_tests': gate_tests,
            'capacity_one': mono.events, 'muted_step_silent': True,
            'modeled_functions': {'0x0020AC54': 'observe backend note-on; return logical slot',
                                  '0x0020AC70': 'observe backend note-off'},
            'direct_apply_is_not_a_clock_boundary': True}


def verify_clock(logical):
    a = sequencer_observer(logical)
    prepare_clock(a)
    for i in range(16):
        set_step(a, i, [60+i], 0xA0)
    seen = []
    a.hook(0x20903E, lambda: seen.append(a.u.reg_read(REGS[0])))
    for _ in range(36):
        a.call(0x208CF8, (1,0))
    need(seen == list(range(16))*2 + list(range(4)), '16-step wrap failed')
    b = sequencer_observer(logical)
    prepare_clock(b, 5)
    set_step(b, 0, [60]); set_step(b, 2, [62])
    sparse = []
    b.hook(0x20903E, lambda: sparse.append(b.u.reg_read(REGS[0])))
    for _ in range(8):
        b.call(0x208CF8, (1,0))
    need(sparse == [0,2]*4, 'Active step mask failed')
    c = sequencer_observer(logical)
    prepare_clock(c)
    subticks = []
    c.hook(0x20903E, lambda: subticks.append(c.u.reg_read(REGS[0])))
    for _ in range(71):
        c.call(0x208CF8, (0,0))
    need(not subticks, 'Step advanced before 72 subticks')
    c.call(0x208CF8, (0,0))
    need(subticks == [0], '72-subtick boundary failed')
    c.put32(0x20003F8C, 0)
    for _ in range(100):
        c.call(0x208CF8, (1,0))
    need(subticks == [0], 'Stopped clock advanced')
    ties = []
    for first, following, expected in [(32,32,['off','on']),
                                        (127,32,[]), (127,160,['off','on'])]:
        t = sequencer_observer(logical)
        prepare_clock(t)
        set_step(t, 0, [60], first); set_step(t, 1, [60], following)
        t.call(0x208CF8, (1,0)); t.events = []
        t.call(0x208CF8, (1,0))
        need([x[0] for x in t.events] == expected, 'Clock-boundary tie failed')
        ties.append({'first_gate': first, 'next_gate': following, 'events': t.events})
    seek = Application(logical)
    rng = random.Random(112)
    masks = [0,0xFFFF,0xAAAA,0x5555] + [1<<i for i in range(16)]
    masks += [rng.randrange(65536) for _ in range(128)]
    count = 0
    for mask in masks:
        for initial in range(16):
            for direction in [0,1]:
                expected = initial
                if mask:
                    while not (mask & (1 << expected)):
                        expected = (expected + (1 if direction else -1)) % 16
                seek.u.mem_write(SCRATCH, bytes([initial]))
                seek.call(0x20832C, (SCRATCH,mask,direction))
                need(seek.data(SCRATCH,1)[0] == expected, 'Native step seek failed')
                count += 1
    return {'native_entry': '0x00208CF8', 'forced_boundary_steps': seen,
            'active_mask_0005': sparse, 'subticks_per_step_at_division_one': 72,
            'stopped_clock_does_not_advance': True, 'boundary_tie_cases': ties,
            'active_step_seek_cases': count,
            'modeled_functions': {'0x0020AC54': 'backend note-on observer',
                                  '0x0020AC70': 'backend note-off observer'},
            'step_clock_not_replaced': True, 'timer_frequency_not_measured': True}


def verify_chain(logical):
    a = Application(logical)
    blank_pattern(a)
    a.u.mem_write(PATTERN+12,b'\xff\xff')
    a.put32(0x20003F8C,1)
    a.hook(0x208CB8,lambda: a.return_(1))
    count = 0
    for first in range(16):
        for last in range(first,16):
            mask = (1<<first) | (1<<last)
            a.call(0x20C610,(0x20003E34,mask,0))
            expected = list(range(first,last+1))
            slots = list(a.data(0x20003E38,16))
            need(slots == expected+[255]*(16-len(expected)), 'Chain interval construction failed')
            need(a.data(0x20003E48,1)[0] == len(expected), 'Chain count failed')
            got = [a.call(0x20C5B0,(0x20003E34,)) for _ in range(len(expected)*2)]
            need(got == [expected[(i+1)%len(expected)] for i in range(len(expected)*2)],
                 'Chain advance/wrap failed')
            count += 1
    return {'native_entries':['0x0020C610','0x0020C5B0','0x0020C5D6'],
            'all_contiguous_intervals':count, 'patterns_available':16,
            'endpoints_select_inclusive_interval':True,
            'modeled_functions':{'0x00208CB8':'pattern-load boundary returns success'},
            'pattern_byte_storage_checked_separately':True}


def verify_motion(logical):
    a = Application(logical)
    blank_pattern(a)
    a.u.mem_write(PATTERN + 68, b'\x01')
    a.u.mem_write(CLOCK + 11, b'\x00')
    values = []
    def sink():
        ptr = a.u.reg_read(REGS[2])
        value = struct.unpack('<h', a.data(ptr,2))[0]
        values.append([a.u.reg_read(REGS[1]),value])
        a.return_(1)
    a.hook(0x20FBB0, sink)
    tested = []
    for lane in [0,1,3,4,5,6,7,8,11,12]:
        a.u.mem_write(PATTERN + 16, bytes(26))
        a.u.mem_write(PATTERN + 16 + lane*2, b'\x01')
        a.u.mem_write(0x20003464, bytes(13*36))
        base = 0x20003464 + lane*36
        a.u.mem_write(base + 12, struct.pack('<5i',10,28,46,64,82))
        a.put32(base + 32, -999)
        values.clear()
        for phase in range(72):
            a.u.mem_write(CLOCK + 27, bytes([phase]))
            a.call(0x209EF8)
        need([v for _,v in values] == list(range(10,82)), 'Motion interpolation failed')
        tested.append({'lane': lane, 'parameter_id': values[0][0],
                       'phases': 72, 'first': 10, 'last': 81})
    return {'native_entry': '0x00209EF8', 'interpolation_cases': tested,
            'quarter_step_subticks': 18,
            'discrete_lanes_excluded_from_linear_interpolation': [2,9,10],
            'modeled_functions': {'0x0020FBB0': 'observe parameter sink; accept computed value'},
            'fixture_points_are_decoded_runtime_values': True}


def pack7(data):
    out = bytearray()
    for start in range(0,len(data),7):
        chunk = data[start:start+7]
        out.append(sum((x>>7)<<i for i,x in enumerate(chunk)))
        out.extend(x & 127 for x in chunk)
    return bytes(out)


def unpack7(data):
    out = bytearray()
    for start in range(0,len(data),8):
        group = data[start:start+8]
        for i,value in enumerate(group[1:]):
            out.append(value | (((group[0]>>i)&1)<<7))
    return bytes(out)


def verify_sysex(logical):
    a = Application(logical)
    p = pattern_fixture(a, 37)
    a.u.mem_write(PATTERN, p)
    transmitted = []
    a.hook(0x20014F58, lambda: a.return_(4096))
    def tx():
        transmitted.append(a.u.reg_read(REGS[1]))
        a.return_(1)
    a.hook(0x20015378, tx)
    a.call(0x20013F48, (SCRATCH,0))
    header = a.data(SCRATCH,7)
    a.call(0x20013E18, (0,))
    need(header == bytes.fromhex('f0 42 30 00 01 2f 40'), 'SysEx header mismatch')
    need(bytes(transmitted) == pack7(p)+b'\xf7', 'Native 8-to-7 encoder mismatch')
    need(unpack7(bytes(transmitted[:-1])) == p, 'Independent decoder mismatch')
    # Incoming dump uses the original MIDI byte parser, including F0/F7.
    b = Application(logical)
    b.put32(ROOT, 0x20020000)
    b.hook(0x20015180, lambda: b.return_(SCRATCH))
    b.hook(0x200151B0, lambda: b.return_(0))
    packet = bytes.fromhex('f0 42 30 00 01 2f 4c 07') + pack7(p) + b'\xf7'
    for value in packet:
        b.call(0x200146EC, (1,value))
    need(b.data(0x20020000 + 7*1920, 1920) == p,
         'Native SysEx parser/decoder/store differs from source')
    need(b.data(JOURNAL + 0x22 + 7*8,1) == b'\x01', 'SysEx did not mark slot dirty')
    rejection = []
    for label,message in [('wrong_manufacturer',bytes([0xF0,0x41])+packet[2:]),
                          ('wrong_start_magic',packet[:8]+pack7(b'X'+p[1:])+b'\xf7'),
                          ('premature_eox',packet[:80]+b'\xf7')]:
        c = Application(logical)
        c.put32(ROOT,0x20020000)
        c.u.mem_write(0x20020000+7*1920,b'\xA5'*1920)
        c.hook(0x20015180,lambda: c.return_(SCRATCH))
        c.hook(0x200151B0,lambda: c.return_(0))
        for value in message:
            c.call(0x200146EC,(1,value))
        need(c.data(0x20020000+7*1920,1920) == b'\xA5'*1920,
             'Malformed SysEx altered stored pattern: '+label)
        rejection.append(label)
    return {'native_entries': ['0x20013F48','0x20013E18','0x200146EC','0x20014460',
                              '0x200143E0','0x20014A9E'],
            'current_sequence_dump_header': header.hex(' '),
            'raw_bytes': 1920, 'packed_data_bytes': len(transmitted)-1,
            'stored_dump_packet_bytes': len(packet), 'receive_slot_zero_based': 7,
            'transmit_receive_byte_identical': True,
            'malformed_receive_rejected':rejection,
            'modeled_functions': {'0x20014F58': 'MIDI TX capacity available',
                '0x20015378': 'capture transmitted MIDI byte',
                '0x20015180': 'scratch allocator returns 0x2003C000',
                '0x200151B0': 'scratch release'},
            'uart_electrical_io_not_emulated': True}


def verify_program_sysex(logical):
    a = audio_machine(logical)
    b = audio_machine(logical)
    meta = bytes([64]*4+[4]+[1]*6+[0])
    a.u.mem_write(0x20029800,meta*64)
    transmitted = []
    a.hook(0x20014F58,lambda: a.return_(4096))
    def tx():
        transmitted.append(a.u.reg_read(REGS[1])); a.return_(1)
    a.hook(0x20015378,tx)
    cases = []
    for slot in range(64):
        a.u.mem_write(0x20002E63,bytes([slot]))
        program = bytearray(a.data(0x20027800+slot*128,128))
        program[118:128] = ('SYSEX%05d'%slot).encode('ascii')
        a.u.mem_write(0x20027800+slot*128,bytes(program))
        transmitted.clear()
        a.call(0x20014070,(SCRATCH,0))
        header = a.data(SCRATCH,8)
        a.call(0x20013E18,(0,))
        expected = bytes(program)+meta
        need(header == bytes.fromhex('f0423000012f4e')+bytes([slot]),'Stored program header mismatch')
        need(bytes(transmitted) == pack7(expected)+b'\xf7','Program data encoder mismatch')
        for value in header+bytes(transmitted):
            b.call(0x200146EC,(1,value))
        need(b.data(0x20027800+slot*128,128) == bytes(program),'Program SysEx store mismatch')
        need(b.data(0x20029800+slot*12,12) == meta,'Program metadata SysEx store mismatch')
        cases.append(slot)
    return {'native_entries':['0x20014070','0x20013E18','0x200146EC','0x20014354',
                              '0x0020F33C','0x00207838','0x00207870'],
            'all_program_slots':cases,'raw_program_bytes':128,'metadata_bytes':12,
            'packed_bytes':160,'stored_packet_bytes':169,
            'modeled_functions':{'0x20014F58':'TX capacity available',
                                  '0x20015378':'capture transmitted MIDI byte'},
            'uart_electrical_io_not_emulated':True}


class Storage:
    """Original journal logic; modeled synchronous SPI reads/sector/page writes."""
    def __init__(self, logical, flash=None):
        self.a = a = Application(logical)
        self.flash = bytearray(b'\xff' * 0x80000) if flash is None else bytearray(flash)
        self.ops = []
        self.page_snapshots = []
        self.capture_snapshots = False
        for address in [0x20015180,0x20015058]:
            a.hook(address, lambda: a.return_(SCRATCH))
        a.hook(0x200151B0, lambda: a.return_(0))
        a.hook(0x20015238, lambda: a.return_(1))
        def read():
            dst,src,n = [a.u.reg_read(r) for r in REGS[:3]]
            need(0 <= src and src+n <= len(self.flash), 'SPI read out of model bounds')
            a.u.mem_write(dst,bytes(self.flash[src:src+n])); a.return_(1)
        a.hook(0x20015218,read)
        a.hook(0x200153C0,read)
        def erase():
            at = a.u.reg_read(REGS[0])
            need(at % 4096 == 0 and 0x40000 <= at < 0x80000, 'SPI erase out of journal')
            self.flash[at:at+4096] = b'\xff' * 4096
            self.ops.append(['erase',at])
            a.return_(1)
        def page():
            src,at = [a.u.reg_read(r) for r in REGS[:2]]
            need(at % 256 == 0 and 0x40000 <= at < 0x80000, 'SPI page out of journal')
            data = a.data(src,256)
            need(all((x & y) == y for x,y in zip(self.flash[at:at+256],data)),
                 'Native page write requires forbidden NOR 0-to-1 transition')
            self.flash[at:at+256] = data
            self.ops.append(['page',at])
            if self.capture_snapshots:
                self.page_snapshots.append(bytes(self.flash))
            a.return_(1)
        a.hook(0x200150F0,erase)
        a.hook(0x20015100,page)
        a.call(0x200135C0)

    def store(self,slot,p):
        self.a.u.mem_write(SCRATCH + 0x2000,p)
        self.a.call(0x200134EC,(SCRATCH + 0x2000,slot))

    def flush(self):
        self.a.call(0x20013CD0)
        for count in range(3000):
            if self.a.call(0x20013D58):
                return count+1
        raise AssertionError('Journal worker did not terminate')

    def load(self,slot):
        self.a.put32(ROOT + 0x94,SCRATCH + 0x1000)
        r = self.a.call(0x20013760,(slot,))
        return r,self.a.data(SCRATCH + 0x1000,1920)


def verify_storage(logical):
    s = Storage(logical)
    need([s.a.get32(ROOT+i) for i in [0,4,8,28]] ==
         [0x20020000,0x20027800,0x20029800,0x20029B00], 'Runtime bank allocation mismatch')
    patterns = [pattern_fixture(s.a,i) for i in range(16)]
    for i,p in enumerate(patterns):
        s.store(i,p)
    work = s.flush()
    first = list(s.ops)
    t = Storage(logical,s.flash)
    for i,p in enumerate(patterns):
        r,q = t.load(i)
        need(r == 1 and q == p, 'Pattern reload failed: ' + str(i))
    # Load RAM banks after reboot by executing the native loading state machine.
    t.a.hook(0x20015058,lambda: t.a.return_(SCRATCH))
    for _ in range(150):
        if t.a.call(0x20013878):
            break
    else:
        raise AssertionError('Native bank loader failed to finish')
    for i,p in enumerate(patterns):
        need(t.a.data(0x20020000+i*1920,1920) == p, 'RAM bank loader mismatch')
    old_flash = bytes(t.flash)
    replacement = pattern_fixture(t.a,63)
    t.store(7,replacement)
    t.capture_snapshots = True
    t.flush()
    need(len(t.page_snapshots) == 16, 'Single-pattern journal uses unexpected page count')
    # Reboot after each completed page. No claim about a torn physical page.
    cut_cases = []
    for n,snapshot in enumerate([old_flash] + t.page_snapshots):
        reboot = Storage(logical,snapshot)
        r,q = reboot.load(7)
        expected = replacement if n == 16 else patterns[7]
        need(r == 1 and q == expected, 'Page-boundary recovery failed at ' + str(n))
        cut_cases.append({'completed_new_pages': n, 'selected': 'new' if n == 16 else 'old'})
    final = Storage(logical,t.flash)
    r,q = final.load(7)
    need(r == 1 and q == replacement, 'Committed replacement not recoverable')
    committed_before_old_erase = t.page_snapshots[-1]
    new_sector = next(at for op,at in t.ops if op == 'page') & ~4095
    damaged_headers = []
    for label,offset in [('sector_start_magic',0),('sector_end_magic',4095)]:
        corrupted = bytearray(committed_before_old_erase)
        corrupted[new_sector+offset] ^= 1
        reboot = Storage(logical,corrupted)
        r,q = reboot.load(7)
        need(r == 1 and q == patterns[7], 'Journal accepted damaged sector marker')
        damaged_headers.append(label)
    corrupted = bytearray(committed_before_old_erase)
    corrupted[new_sector+16+80] ^= 1
    reboot = Storage(logical,corrupted)
    r,q = reboot.load(7)
    need(r == 1 and q != replacement and q != patterns[7],
         'Unexpected payload integrity behavior')
    # Original journal markers do not implement a payload CRC.
    t.capture_snapshots = False
    programs = []
    metadata = []
    for i in range(64):
        program = bytearray(t.a.data(0x20015460+(i%32)*128,128))
        program[118:128] = ('TEST_%05d'%i).encode('ascii')
        meta = bytes([64,64,64,64,4]+[1]*6+[i])
        programs.append(bytes(program)); metadata.append(meta)
        t.a.u.mem_write(SCRATCH+0x2000,bytes(program))
        t.a.u.mem_write(SCRATCH+0x2100,meta)
        t.a.call(0x207838,(i,SCRATCH+0x2000))
        t.a.call(0x207870,(i,SCRATCH+0x2100))
    t.flush()
    program_reboot = Storage(logical,t.flash)
    for _ in range(150):
        if program_reboot.a.call(0x20013878):
            break
    else:
        raise AssertionError('Program bank loader did not terminate')
    need(program_reboot.a.data(0x20027800,8192) == b''.join(programs),
         '64 programs did not survive journal reload')
    need(program_reboot.a.data(0x20029800,768) == b''.join(metadata),
         '64 program metadata records did not survive journal reload')
    # Native index bounds: slot 16 performs no 1920-byte bank copy.
    before = s.a.data(0x20020000,0x7800)
    s.store(16,replacement)
    need(s.a.data(0x20020000,0x7800) == before, 'Invalid slot altered bank')
    return {'native_entries': ['0x200135C0','0x200134EC','0x20013760',
                              '0x20013878','0x20013CD0','0x20013D58'],
            'patterns_saved_and_reloaded': 16, 'initial_worker_calls': work,
            'programs_and_metadata_saved_and_reloaded':64,
            'initial_sector_erases': sum(x[0]=='erase' for x in first),
            'initial_256_byte_page_writes': sum(x[0]=='page' for x in first),
            'journal_arena': ['0x00040000','0x00080000'], 'sector_bytes':4096,
            'page_boundary_recovery': cut_cases, 'out_of_range_slot_rejected': True,
            'damaged_sector_markers_fall_back_to_previous':damaged_headers,
            'payload_bit_corruption_not_rejected_by_journal':True,
            'modeled_functions': {'0x20015180':'scratch allocation',
                '0x200151B0':'scratch release', '0x20015058':'scratch pointer',
                '0x20015238':'SPI ready', '0x20015218':'synchronous SPI read',
                '0x200153C0':'SPI read scheduling boundary',
                '0x200150F0':'4096-byte NOR sector erase',
                '0x20015100':'256-byte NOR program page'},
            'physical_torn_page_or_flash_wear_not_tested': True}


def audio_machine(logical):
    a = Application(logical)
    # Real normal-boot layout, with factory defaults used as synthetic stored bank.
    a.put32(ROOT + 4,0x20027800)
    a.put32(ROOT + 8,0x20029800)
    a.u.mem_write(0x20027800,a.data(0x20015460,4096)*2)
    a.u.mem_write(0x20005358,bytes([64]*4+[4]+[1]*6))
    a.call(0x20E970,(2,))
    a.call(0x209A98,(0,))
    a.call(0x204BD8,(2,))
    a.call(0x204C20,(0x20029B00,))
    # ADC input fixture for the volume knob, consumed by original background code.
    a.u.mem_write(0x20001452,struct.pack('<H',4095))
    return a


def render_synth(a,count):
    out = bytearray()
    for _ in range(count):
        a.call(0x10DA,(SCRATCH,))
        out.extend(a.data(SCRATCH,8))
    return bytes(out)


def sample_stats(raw):
    samples = struct.unpack('<'+'i'*(len(raw)//4),raw)
    return {'sha256':digest(raw), 'stereo_frames':len(raw)//8,
            'minimum':min(samples), 'maximum':max(samples),
            'nonzero_samples':sum(x != 0 for x in samples)}


def verify_fm(logical):
    a = audio_machine(logical)
    table = struct.unpack('<32I',a.data(0x105A,128))
    need(len(set(table)) == 32, '32 algorithm entry points are not distinct')
    algorithms = []
    for algorithm,kernel in enumerate(table):
        b = audio_machine(logical)
        old = b.data(0x20004F5C+110,1)[0]
        b.u.mem_write(0x20004F5C+110,bytes([(old & 0xE0) | algorithm]))
        b.call(0x20E864,(0,60,100))
        need(b.get32(ENGINE) == kernel, 'Native algorithm selection mismatch')
        raw = render_synth(b,2048)
        stats = sample_stats(raw)
        need(stats['nonzero_samples'] > 0, 'Algorithm emitted only silence')
        algorithms.append({'algorithm_one_based':algorithm+1,
                           'kernel':f'0x{kernel & ~1:08X}', **stats})
    chord = audio_machine(logical)
    for voice,note in enumerate([48,55,60,64,67,72]):
        chord.call(0x20E864,(voice,note,100))
    need(all(chord.data(ENGINE+voice*624+14,1) != b'\0' for voice in range(6)),
         'Six DSP voices did not activate')
    poly = render_synth(chord,8192)
    need(sample_stats(poly)['nonzero_samples'] > 0, 'Six-voice output silent')
    release_before = chord.data(ENGINE,624)
    chord.call(0x20E7C8,(0,))
    need(chord.data(ENGINE,624) != release_before, 'Release did not change voice state')
    return {'native_entries':['0x0020E970','0x0020E864','0x0020E6DC',
                              '0x000010DA','0x0020E7C8'],
            'algorithm_dispatch_table':'0x0000105A', 'algorithms':algorithms,
            'six_voice_render':sample_stats(poly), 'voice_bytes':624,
            'operators_per_voice':6, 'operator_bytes':80,
            'modeled_functions': {},
            'fixtures':'factory preset Volcanic; neutral macro controls; synthetic note events',
            'no_physical_sound_comparison':True}


def verify_voice_modes(logical):
    results = []
    for mode,capacity,variants,active in [(0,6,1,6),(1,1,1,1),(2,3,2,6),(3,1,3,3)]:
        a = audio_machine(logical)
        blank_pattern(a)
        a.call(0x208198,(mode,1))
        a.u.mem_write(PATTERN+6,b'\xff\xff')
        set_step(a,0,[48,52,55,60,64,67],0xA0)
        a.call(0x20B7BE,(0,))
        got_capacity = a.data(0x20003C6C+0xDC,1)[0]
        got_variants = a.data(0x200031C8+8,1)[0]
        got_active = sum(a.data(ENGINE+i*624+14,1)[0] != 0 for i in range(6))
        need((got_capacity,got_variants,got_active) == (capacity,variants,active),
             'Voice mode allocation mismatch')
        raw = render_synth(a,1024)
        need(sample_stats(raw)['nonzero_samples'] > 0,'Voice mode silent')
        results.append({'mode_bits':mode,'logical_capacity':capacity,
                        'dsp_voices_per_logical_note':variants,
                        'active_dsp_voices_for_six_note_input':active,
                        'render':sample_stats(raw)})
    return {'native_entries':['0x00208198','0x00209A98','0x00209574'],
            'modes':results,'modeled_functions':{},
            'bits_interpretation':'bit 0 MONO; bit 1 UNISON'}


def verify_prng(logical):
    a = Application(logical)
    state = list(struct.unpack('<4I',a.data(0x2000590C,16)))
    initial = list(state)
    need(all(state),'Original initialized PRNG seed missing')
    outputs = bytearray()
    for i in range(10000):
        modulus = [0,1,6,16,127,256,65535][i%7]
        x,y,z,w = state
        t = (x ^ (x<<11)) & 0xFFFFFFFF
        w = (w ^ (w>>19) ^ t ^ (t>>8)) & 0xFFFFFFFF
        state = [y,z,state[3],w]
        expected = w % modulus if modulus else w
        got = a.call(0x2094A4,(modulus,))
        need(got == expected,'Original xorshift128 output mismatch')
        outputs.extend(struct.pack('<I',got))
    need(list(struct.unpack('<4I',a.data(0x2000590C,16))) == state,
         'PRNG state transition mismatch')
    return {'native_entry':'0x002094A4','algorithm':'xorshift128 with optional unsigned remainder',
            'initial_state':initial,'cases':10000,'output_sha256':digest(outputs),
            'modeled_functions':{},'hardware_randomness_not_assumed':True}


def verify_arpeggiator(logical):
    def make(kind,division):
        a = audio_machine(logical)
        blank_pattern(a)
        a.u.mem_write(PATTERN+69,b'\x01')
        a.u.mem_write(PATTERN+70,bytes([kind,division]))
        a.call(0x208198,(0,1))
        a.u.mem_write(PATTERN+6,b'\xff\xff')
        set_step(a,0,[60,64,67],127)
        a.tick = 0
        a.arpeggio = []
        a.hook(0x20E814,lambda: a.arpeggio.append(
            [a.tick,a.u.reg_read(REGS[1])//256]))
        a.call(0x20B7BE,(0,))
        return a
    order_cycles = {1:[60,64,67],2:[60,64,67,72,76,79],
                    3:[60,64,67,72,76,79,84,88,91],
                    4:[67,64,60],5:[67,64,60,55,52,48],
                    6:[67,64,60,55,52,48,43,40,36]}
    kinds = []
    for kind in range(1,10):
        a = make(kind,2)
        for tick in range(1,601):
            a.tick = tick
            a.call(0x20C40C,(0x20003E10,))
        notes = [v for _,v in a.arpeggio]
        need(len(notes) == 34,'Arpeggio tick count mismatch')
        if kind <= 6:
            cycle = order_cycles[kind]
            need(notes == [cycle[i%len(cycle)] for i in range(len(notes))],
                 'Arpeggio order/octave mismatch')
        else:
            need(len(set(notes)) > 1 and all(0 <= n <= 127 for n in notes),
                 'Seeded random arpeggio is invalid or constant')
        kinds.append({'type':kind,'note_events':a.arpeggio})
    divisions = []
    for index,interval in enumerate([6,9,18,24,36,48,72,108,144,216,288]):
        a = make(1,index)
        for tick in range(1,interval*3+1):
            a.tick = tick
            a.call(0x20C40C,(0x20003E10,))
        need([t for t,_ in a.arpeggio] == [0,interval,interval*2,interval*3],
             'Arpeggio division mismatch')
        divisions.append({'division_index':index,'subticks_between_notes':interval})
    return {'native_entries':['0x0020C40C','0x0020C1F4','0x0020BF78','0x002094A4'],
            'types':kinds,'divisions':divisions,
            'modeled_functions':{},'observation_hook':'0x0020E814 (original instruction executes)',
            'random_types_use_original_startup_seed':True}


def render_isr(a,count,service_every=None):
    raw = bytearray()
    for index in range(count):
        a.call(0x10)
        raw.extend(a.data(0x20000020,8))
        if service_every and (index+1) % service_every == 0:
            a.call(0x20E8C2)
    return bytes(raw)


def verify_midi(logical):
    a = audio_machine(logical)
    a.call(0x20AD54,(6,0))
    a.call(0x2080A4,(1,))
    a.call(0x200148E4,(1,))
    def send(packet):
        for value in packet:
            a.call(0x200146EC,(1,value))
    def voices():
        result = []
        for i in range(6):
            record = a.data(0x20003C6C+i*16,12)
            if record[0]:
                result.append([i,record[8],record[2]])
        return result
    states = []
    send([0x91,70,100])
    need(not voices(), 'Wrong MIDI channel accepted')
    send([0x90,60,100])
    need([v[1] for v in voices()] == [60], 'MIDI note-on failed')
    states.append({'case':'note_on','voices':voices()})
    send([64,100])
    need([v[1] for v in voices()] == [60,64], 'Running status failed')
    states.append({'case':'running_status','voices':voices()})
    send([0x90,67,0xFE,100])
    need([v[1] for v in voices()] == [60,64,67], 'Interleaved active sensing failed')
    send([0x90,67,0])
    need([v[1] for v in voices()] == [60,64], 'Velocity zero did not release note')
    send([0xB0,64,127]); send([0x80,64,0])
    need([v[1:] for v in voices()] == [[60,1],[64,0]], 'Sustain did not hold released key')
    states.append({'case':'sustain_holds_released_key','voices':voices()})
    send([0xB0,64,0]); a.call(0x20AF08)
    need([v[1] for v in voices()] == [60], 'Sustain service did not release held note')
    send([0xB0,123,0])
    need(not voices(), 'All notes off failed')
    states.append({'case':'all_notes_off','voices':voices()})
    # Seven different pitches exercise original allocation/stealing, six capacity.
    for note in [48,50,52,53,55,57,59]:
        send([0x90,note,100])
        # Voice-steal policy protects very recent voices for a short interval.
        for i in range(6):
            a.u.mem_write(0x20003C6C+i*16+11,b'\0')
    v = voices()
    need(len(v) == 6 and 59 in [x[1] for x in v], 'Six-voice allocation/steal failed')
    states.append({'case':'seventh_pitch_steals_with_synthetic_age_expired','voices':v})
    return {'native_entries':['0x2080A4','0x200146EC','0x00207D98',
                              '0x0020A78C','0x0020AF08'],
            'states':states,'configured_channel_zero_based':0,
            'wrong_channel_ignored':True,'interleaved_active_sensing':True,
            'macro_cc_by_parameter_id':list(a.data(0x2000B377,16)),
            'modeled_functions':{},
            'fixtures':'MIDI RX enabled; hardware-free input bytes; expired steal protection for last case',
            'uart_wire_timing_not_emulated':True}


def verify_application_path(logical):
    a = audio_machine(logical)
    blank_pattern(a)
    a.call(0x208198,(0,1))
    prepare_clock(a)
    a.u.mem_write(PATTERN+6,b'\xff\xff')
    for step in range(16):
        set_step(a,step,[36+step,43+step,48+step,52+step,55+step,60+step],0xA0)
    a.call(0x20EA70,(90,)); a.call(0x2045F4,(1,))
    a.call(0x20EA84,(80,)); a.call(0x20453C,(1,))
    a.put32(0x20000028,0x7FFFFFFF); a.put32(0x2000002C,0x7FFFFFFF)
    cases = []
    output = bytearray()
    for step in range(18):
        a.call(0x208CF8,(1,0))
        need(a.data(CLOCK+11,1)[0] == step%16,'Integrated clock step mismatch')
        slots = [list(a.data(SLOTS+i*4,4)) for i in range(6)]
        need([r[0] for r in slots] == [36+step%16,43+step%16,48+step%16,
                                     52+step%16,55+step%16,60+step%16],
             'Integrated step notes mismatch')
        need(all(r[3] < 6 for r in slots),'Integrated sequence lost a backend voice')
        raw = render_isr(a,512,service_every=64)
        need(sample_stats(raw)['nonzero_samples'] > 0,'Integrated sequencer audio silent')
        output.extend(raw)
        cases.append({'step':step%16,'notes':[r[0] for r in slots],
                      'backend_voices':[r[3] for r in slots]})
        # Original per-millisecond allocator service normally ages this field.
        # The fixture advances it explicitly because this test has no timer ISR.
        for i in range(6):
            a.u.mem_write(0x20003C6C+i*16+11,b'\0')
    return {'native_path':['0x00208CF8','0x0020B7BE','0x0020AC54','0x0020A78C',
                          '0x00209574','0x0020E814','0x0020E6DC','0x0020E8C2',
                          '0x00000010','0x000010DA','0x000012AC','0x00001460'],
            'step_cases':cases,'render':sample_stats(bytes(output)),
            'modeled_functions':{},
            'fixtures':'poly mode initialized; forced step boundaries; 512 frames/step; native voice service every 64 frames; max volume ADC; voice age explicitly elapsed',
            'physical_tempo_and_latency_not_measured':True}


def verify_effects(logical):
    modes = []
    for chorus,reverb in [(0,0),(1,0),(0,1),(1,1)]:
        a = audio_machine(logical)
        a.call(0x20E864,(0,60,100))
        a.call(0x20EA70,(100,)); a.call(0x2045F4,(chorus,))
        a.call(0x20EA84,(96,)); a.call(0x20453C,(reverb,))
        a.put32(0x20000028,0x7FFFFFFF)
        a.put32(0x2000002C,0x7FFFFFFF)
        a.u.mem_write(0x20029AF0,b'\x5A'*16)
        a.u.mem_write(0x20035B00,b'\xA5'*16)
        raw = render_isr(a,30000)
        need(a.data(0x20029AF0,16) == b'\x5A'*16 and
             a.data(0x20035B00,16) == b'\xA5'*16,
             'Reverb buffer canary altered')
        stats = sample_stats(raw)
        need(stats['nonzero_samples'] > 0, 'Audio ISR emitted silence')
        modes.append({'chorus':bool(chorus),'reverb':bool(reverb),**stats,
                      'last_reverb_head':list(a.data(0x20001A54+0xD0,3))})
    need(len({m['sha256'] for m in modes}) == 4, 'Effects switches did not change output')
    return {'native_entries':['0x00000010','0x000010DA','0x000012AC','0x00001460',
                              '0x002045B4','0x00204C20','0x0020EA70','0x0020EA84'],
            'audio_modes':modes, 'chorus_ring_bytes':[2024,2424],
            'chorus_buffers':['0x20000070','0x20000858'],
            'reverb_buffer':['0x20029B00','0x20035B00'],
            'reverb_bytes':49152, 'reverb_guard_bytes_unchanged':True,
            'modeled_functions':{},
            'memory_mapped_hardware_registers':'ordinary RAM; no peripheral timing',
            'dac_analog_and_realtime_deadline_not_tested':True}
