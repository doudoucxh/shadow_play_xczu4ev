from pathlib import Path
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).parents[1]/'hdmi_ui/runtime'))
from board_audio import BoardAudio, TRACK, TRACK_SHA, DURATION


class AudioTests(unittest.TestCase):
    def test_selected_asset_matches_v20_audio_metadata(self):
        root = Path(__file__).parents[1]
        self.assertEqual(hashlib.sha256((root/TRACK['playback']['asset']).read_bytes()).hexdigest(), TRACK_SHA)
        source = TRACK['source']
        self.assertLess(abs(DURATION-source['sample_frames']/source['sample_rate_hz']), 1/48000)
        self.assertEqual(source['sha256'], '8b95f441e7f696213d1f175cb52caa2e07ea05bca4e0e8697e48647b96621ff8')

    def test_new_track_is_not_expired_at_old_track_deadline(self):
        audio = BoardAudio('.')
        owned = Mock()
        owned.poll.return_value = None
        audio.process = owned
        audio.started, audio.last_request = 0, 78
        with patch('board_audio.time.monotonic', return_value=78): audio.expire()
        owned.terminate.assert_not_called()

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
