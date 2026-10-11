"""Pure register-model tests; never open /dev/mem or a serial connection."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from servo_pwm_device import PwmDevice, STATUS_READ_ATTEMPTS, PERSISTENT_MOTION_INHIBIT
from test_servo_commissioning import FakeRegisters


class EdgeRegisters(FakeRegisters):
    def __init__(self, trigger_address=0x10):
        super().__init__(apply=False)
        self.trigger_address=trigger_address
        self.edge_pending=False

    def write(self, address, value):
        super().write(address,value)
        if address==0x18:self.edge_pending=True

    def read(self, address):
        if self.edge_pending and address==self.trigger_address:
            for i in range(10):self.values[0x80+4*i]=self.values[0x40+4*i]
            self.values[8]=self.values[0x14]
            self.values[0x20]=(self.values.get(0x20,0)+1)&0xffffffff
            self.values[0x24]=0
            self.edge_pending=False
        return super().read(address)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        # Isolate these tests from any local incident marker.
        self.stat=patch('servo_pwm_device.os.stat',side_effect=FileNotFoundError()).start()
        self.addCleanup(patch.stopall)

    def test_frame_edge_before_sequence_or_mid_pulses_never_recommits(self):
        for trigger in [0x10,0x80+4*5]:
            with self.subTest(trigger=trigger):
                reg=EdgeRegisters(trigger);d=PwmDevice(reg)
                pulses=[1500]*10;pulses[6]=1537
                state=d.commit(pulses,64,allow_arm=True)
                self.assertEqual(state['enabled_mask'],64)
                self.assertEqual(state['pulse_us'],pulses)
                self.assertEqual(sum(a==0x18 for a,v in reg.writes),1)
                self.assertEqual(sum(a==0x10 for a,v in reg.writes),1)

    def test_control_transition_without_sequence_increment_is_retried(self):
        for change in [{8:0,0x10:0,0x0c:2,0x24:0},
                       {8:0,0x10:0,0x24:0}, {0x10:1}]:
            with self.subTest(change=change):
                reg=FakeRegisters();reg.values.update({8:64,0x10:1,0x20:9})
                if change=={0x10:1}:reg.values.update({8:0,0x10:0})
                original=reg.read;fired=[False]
                def read(address):
                    if address==0x80 and not fired[0]:
                        reg.values.update(change);fired[0]=True
                    return original(address)
                reg.read=read;state=PwmDevice(reg).status()
                self.assertEqual(state['sequence'],9)
                self.assertEqual(state['enabled_mask'],reg.values[8])
                self.assertEqual(state['armed'],bool(reg.values[0x10]))
                self.assertEqual(state['faults'],reg.values.get(0x0c,0))
                self.assertEqual(reg.writes,[])

    def test_persistent_snapshot_changes_fail_after_bound_without_writes(self):
        reg=FakeRegisters();original=reg.read;sequence_reads=[0]
        def read(address):
            if address==0x20:
                sequence_reads[0]+=1
                return sequence_reads[0]
            return original(address)
        reg.read=read
        with self.assertRaisesRegex(RuntimeError,'bounded read-only snapshot'):
            PwmDevice(reg).status()
        self.assertEqual(sequence_reads[0],2*STATUS_READ_ATTEMPTS)
        self.assertEqual(reg.writes,[])

    def test_persistent_control_changes_without_sequence_fail_after_bound(self):
        reg=FakeRegisters();original=reg.read;transitions=[0]
        def read(address):
            if address==0x80:
                transitions[0]+=1;reg.values[0x10]=1-reg.values.get(0x10,0)
            return original(address)
        reg.read=read
        with self.assertRaisesRegex(RuntimeError,'bounded read-only snapshot'):
            PwmDevice(reg).status()
        self.assertEqual(transitions[0],STATUS_READ_ATTEMPTS)
        self.assertEqual(reg.writes,[])

    def test_stable_real_mismatch_still_fails_with_expected_and_observed(self):
        class WrongMask(FakeRegisters):
            def write(self,address,value):
                super().write(address,value)
                if address==0x18:self.values[8]=2
        reg=WrongMask()
        with self.assertRaisesRegex(RuntimeError,'adopted-state readback mismatch; expected=.*observed='):
            PwmDevice(reg).commit([1500]*10,64,allow_arm=True)
        self.assertEqual(sum(a==0x18 for a,v in reg.writes),1)
        self.assertEqual(sum(a==0x10 for a,v in reg.writes),1)

    def test_inhibit_prevents_all_commit_writes_but_status_and_off_work(self):
        self.stat.side_effect=None;self.stat.return_value=object()
        reg=FakeRegisters();d=PwmDevice(reg)
        with self.assertRaisesRegex(RuntimeError,'motion inhibited'):
            d.commit([1500]*10,64,allow_arm=True)
        self.assertEqual(reg.writes,[])
        d.status();self.assertEqual(reg.writes,[])
        self.assertFalse(d.off()['armed'])
        self.assertEqual(reg.writes,[(0x0c,0)])

    def test_inhibit_created_during_snapshot_blocks_first_write(self):
        self.stat.side_effect=[FileNotFoundError(),FileNotFoundError(),object()]
        reg=FakeRegisters()
        with self.assertRaisesRegex(RuntimeError,'motion inhibited'):
            PwmDevice(reg).commit([1500]*10,64,allow_arm=True)
        self.assertEqual(reg.writes,[])

    def test_persistent_marker_blocks_when_run_marker_is_absent(self):
        def marker(path):
            if path==PERSISTENT_MOTION_INHIBIT:return object()
            raise FileNotFoundError()
        self.stat.side_effect=marker
        reg=FakeRegisters();d=PwmDevice(reg)
        with self.assertRaisesRegex(RuntimeError,'motion inhibited.*.motion-inhibit'):
            d.commit([1500]*10,64,allow_arm=True)
        self.assertEqual(reg.writes,[])
        self.assertEqual(d.off()['enabled_mask'],0)

    def test_custom_marker_paths_are_injectable_without_disabling_check(self):
        def marker(path):
            if path=='test-marker':return object()
            raise FileNotFoundError()
        self.stat.side_effect=marker
        reg=FakeRegisters();d=PwmDevice(reg,motion_inhibit_paths=['test-marker'])
        with self.assertRaisesRegex(RuntimeError,'motion inhibited by test-marker'):
            d.commit([1500]*10,64,allow_arm=True)
        self.assertEqual(reg.writes,[])
        with self.assertRaises(ValueError):PwmDevice(reg,motion_inhibit_paths=[])

    def test_unreadable_inhibit_state_fails_closed_without_write(self):
        self.stat.side_effect=PermissionError('marker status unavailable')
        reg=FakeRegisters()
        with self.assertRaises(PermissionError):PwmDevice(reg).commit([1500]*10,64,allow_arm=True)
        self.assertEqual(reg.writes,[])


if __name__=='__main__':unittest.main()
