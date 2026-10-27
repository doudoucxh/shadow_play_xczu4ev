"""Bounded brake stream with an emulated UART, no physical I/O."""
import unittest

from shadow_play.bus_servo.brake_probe import FRAME, stream_brake


class Clock:
    def __init__(self): self.t = 0
    def now(self): return self.t
    def sleep(self, seconds): self.t += seconds


class Registers:
    def __init__(self, clock, reply=None, after_frame=1):
        self.clock, self.reply, self.after_frame = clock, reply, after_frame
        self.frames, self.times, self.writes = [], [], []
        self.staging, self.rx = {}, bytearray()
        self.busy_until = 0
        self.fault = self.lease = self.other = 0
        self.rx_at = None
    def read(self, offset):
        if self.rx_at is not None and self.clock.t >= self.rx_at:
            self.rx.extend(self.reply); self.rx_at = None
        if offset == 8: return self.fault
        if offset == 16: return self.lease
        if offset == 0x100: return self.other
        if offset == 0x400:
            return int(self.clock.t < self.busy_until) | len(self.rx) << 8
        if offset == 0x404: return self.rx.pop(0)
        return 0
    def write(self, offset, value):
        self.writes.append((offset, value))
        if offset == 0x408: self.staging[value >> 8] = value & 255
        elif offset == 0x40c:
            self.frames.append(bytes(self.staging[i] for i in range(value)))
            self.times.append(self.clock.t)
            self.busy_until = self.clock.t + .001
            if self.reply is not None and len(self.frames) == self.after_frame:
                self.rx_at = self.clock.t + .003
        else: raise AssertionError('Non-TX register write')


class BrakeTests(unittest.TestCase):
    def run_probe(self, regs, seconds=.2, **kwargs):
        return stream_brake(regs, seconds, clock=regs.clock.now,
                            sleep=regs.clock.sleep, **kwargs)

    def test_power_off_window_sends_only_id10_brake_and_expires(self):
        r=Registers(Clock()); result=self.run_probe(r)
        self.assertEqual(result['status'], 'window_expired')
        self.assertGreater(len(r.frames), 1)
        self.assertLessEqual(len(r.frames), 10)
        self.assertTrue(all(frame == FRAME for frame in r.frames))
        self.assertTrue(all(offset in (0x408,0x40c) for offset,_ in r.writes))
        self.assertTrue(all(b-a >= .02-1e-9 for a,b in zip(r.times,r.times[1:])))
        self.assertFalse(result['physical_stop_verified'])

    def test_power_on_ack_stops_further_frames(self):
        r=Registers(Clock(),b'#010POK!',after_frame=3)
        result=self.run_probe(r)
        self.assertEqual(result['status'],'acknowledged_id10')
        self.assertEqual(len(r.frames),3)
        self.assertEqual(result['rx_hex'],b'#010POK!'.hex())
        self.assertFalse(result['startup_motion_prevented'])

    def test_unaddressed_ack_is_not_claimed_as_id_verification(self):
        r=Registers(Clock(),b'#OK!')
        self.assertEqual(self.run_probe(r)['status'],'acknowledged_without_id')
        self.assertEqual(len(r.frames),1)

    def test_echo_wrong_id_error_and_partial_reply_end_without_resending(self):
        for reply in (FRAME,b'#009POK!',b'#010PERR:4!',b'#010P'):
            with self.subTest(reply=reply):
                r=Registers(Clock(),reply)
                self.assertEqual(self.run_probe(r)['status'],'unrecognized_reply')
                self.assertEqual(len(r.frames),1)

    def test_initial_stale_rx_other_bus_fault_or_lease_never_transmits(self):
        for condition in ('rx','other','fault','lease','busy'):
            r=Registers(Clock())
            if condition=='rx':r.rx.extend(b'#010POK!')
            elif condition=='busy':r.busy_until=1
            else:setattr(r,condition,1)
            self.run_probe(r)
            self.assertEqual(r.writes,[],condition)

    def test_cancellation_during_window_does_not_release_or_reenable(self):
        r=Registers(Clock())
        result=self.run_probe(r,canceled=lambda:r.clock.t>=.035)
        self.assertEqual(result['status'],'canceled')
        self.assertEqual(len(r.frames),2)
        self.assertTrue(all(frame==FRAME for frame in r.frames))

    def test_clock_stall_cannot_extend_window_or_catch_up(self):
        r=Registers(Clock())
        def emit(event):
            if event['event']=='transmitting':r.clock.t+=1
        result=self.run_probe(r,emit=emit)
        self.assertEqual(result['status'],'window_expired')
        self.assertEqual(len(r.frames),1)

    def test_invalid_duration_never_touches_registers(self):
        for value in (0,-1,31,float('inf'),float('nan'),True):
            r=Registers(Clock())
            with self.assertRaises(ValueError):self.run_probe(r,seconds=value)
            self.assertEqual(r.writes,[])


if __name__=='__main__':unittest.main()
