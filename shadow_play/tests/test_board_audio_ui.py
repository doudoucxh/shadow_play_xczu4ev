from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).parents[1]/'hdmi_ui/runtime'))
from board_audio import BoardAudio


class AudioTests(unittest.TestCase):
    def test_missing_media_never_launches(self):
        with tempfile.TemporaryDirectory() as folder, patch('board_audio.subprocess.Popen') as launch:
            audio = BoardAudio(folder)
            with self.assertRaises(RuntimeError): audio.start()
            launch.assert_not_called()

    def test_wrong_media_hash_never_launches(self):
        with tempfile.TemporaryDirectory() as folder, patch('board_audio.subprocess.Popen') as launch:
            for name in ('usb_audio_play', 'wusong.mp3'): (Path(folder)/name).write_bytes(b'wrong')
            audio = BoardAudio(folder)
            with patch.object(audio, 'output', return_value=(1, 0)):
                with self.assertRaises(RuntimeError): audio.start()
            launch.assert_not_called()

    def test_viewer_loss_terminates_only_owned_player(self):
        audio = BoardAudio('.')
        owned = Mock()
        owned.poll.return_value = None
        audio.process = owned
        with patch('board_audio.time.monotonic', return_value=15): audio.expire()
        owned.terminate.assert_called_once()
        self.assertIsNone(audio.process)


if __name__ == '__main__': unittest.main()
