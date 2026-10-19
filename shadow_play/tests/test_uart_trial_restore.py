from pathlib import Path
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from restore_standard_uart_image import STANDARD_SHA,TRIAL_SHA,check_identities
from zdt_uartlite_telemetry import SWAPPED_PORTS,TelemetryError
import restore_standard_uart_image as restore


class Tests(unittest.TestCase):
    def test_restore_only_this_trial_and_its_preserved_image(self):
        current=dict(sha256=TRIAL_SHA,boot_id='boot',uart_pin_swap_trial=True,
                     rail_uart=dict(ports=SWAPPED_PORTS,pin_map='swapped',tx_drive_ma=4))
        preserved=dict(sha256=STANDARD_SHA,boot_id='boot')
        check_identities(current,preserved,'boot')
        for field,value in [('sha256',STANDARD_SHA),('boot_id','other'),('uart_pin_swap_trial',False)]:
            with self.assertRaises(ValueError):check_identities(dict(current,**{field:value}),preserved,'boot')
        for field,value in [('sha256',TRIAL_SHA),('boot_id','other')]:
            with self.assertRaises(ValueError):check_identities(current,dict(preserved,**{field:value}),'boot')
        altered=dict(current,rail_uart=dict(current['rail_uart'],ports={}))
        with self.assertRaises(TelemetryError):check_identities(altered,preserved,'boot')

    def test_display_recreates_garbage_collected_transient_unit(self):
        names=('shadow_play/integrations/follow/usb_hdmi.py',
               'shadow_play/hdmi_ui/runtime/hdmi_sink.py',
               'shadow_play/hdmi_ui/runtime/browser_display.py')
        files={str(Path('/run/shadow-pwm-loaded.json')):json.dumps(dict(sha256=STANDARD_SHA,boot_id='boot')),
               str(Path('/proc/sys/kernel/random/boot_id')):'boot',
               str(restore.STANDARD/'MANIFEST.json'):json.dumps(dict(files={name:'hash' for name in names}))}
        with patch.object(Path,'read_text',autospec=True,side_effect=lambda p,*a,**k:files[str(p)]), \
             patch.object(restore,'digest',return_value='hash'), \
             patch.object(restore.time,'sleep'), \
             patch.object(restore.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(restore.start_standard_display('boot'))
            command=run.call_args_list[0].args[0]
            self.assertEqual(command[0],'systemd-run')
            self.assertIn('--unit=shadow-uart-restored-hdmi',command)
            self.assertNotIn('start',command)
            files[str(Path('/run/shadow-pwm-loaded.json'))]=json.dumps(dict(sha256=TRIAL_SHA,boot_id='boot'))
            run.reset_mock()
            with self.assertRaises(ValueError):restore.start_standard_display('boot')
            run.assert_not_called()


if __name__=='__main__':unittest.main()
