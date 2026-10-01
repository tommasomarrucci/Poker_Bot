"""Window identity and failure tests; never capture the user's desktop in unit tests."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from mac_capture import LockedWindowCapture, capture_window, check_locked_window, poker_windows


def window(number=10, title='PokerStars', pid=123):
    return {'id': number, 'pid': pid, 'title': title, 'owner': 'Brave Browser',
            'bounds': {'X': 0, 'Y': 0, 'Width': 1710, 'Height': 1107}, 'onscreen': True}


class CaptureTest(unittest.TestCase):
    def test_selection_excludes_other_browser_windows(self):
        rows = [window(1, 'Mail'), window(2), window(3, 'New tab')]
        self.assertEqual([w['id'] for w in poker_windows(rows)], [2])
        self.assertEqual([w['id'] for w in poker_windows(rows, 3)], [3])
        with self.assertRaises(RuntimeError):
            poker_windows([window(1, 'Mail')])

    def test_lock_allows_movement_but_rejects_resize_tab_change_and_id_reuse(self):
        locked = window()
        moved = copy.deepcopy(locked)
        moved['bounds']['X'] = 250
        self.assertEqual(check_locked_window(locked, [moved]), moved)
        for changed in [window(title='Mail'), window(pid=999), window(number=99)]:
            with self.subTest(changed=changed):
                with self.assertRaises(RuntimeError):
                    check_locked_window(locked, [changed])
        moved['bounds']['Width'] = 1300
        self.assertEqual(check_locked_window(locked, [moved], allow_resize=True), moved)
        with self.assertRaisesRegex(RuntimeError, 'resized'):
            check_locked_window(locked, [moved])

    def test_closed_window_never_switches_to_another_table(self):
        image = Image.new('RGB', (1710, 1107))
        with patch('mac_capture.list_windows', side_effect=[[window()], [window(20)]]), \
                patch('mac_capture.capture_window', return_value=image) as capture:
            source = LockedWindowCapture('unused.png', lambda im: None)
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                source.read()
            self.assertEqual(capture.call_count, 1)

    def test_multiple_valid_tables_require_explicit_selection(self):
        with patch('mac_capture.list_windows', return_value=[window(10), window(20)]), \
                patch('mac_capture.capture_window', return_value=Image.new('RGB', (10, 10))):
            with self.assertRaisesRegex(RuntimeError, 'Multiple'):
                LockedWindowCapture('unused.png', lambda im: None)

    def test_failed_capture_removes_stale_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'capture.png'
            Image.new('RGB', (10, 10)).save(path)
            with patch('mac_capture.subprocess.run', side_effect=subprocess.TimeoutExpired('screencapture', 15)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    capture_window(10, path)
            self.assertFalse(path.exists())

    def test_existing_log_is_preserved(self):
        fixture = Path(__file__).parent/'fixtures'/'218.png'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'session.jsonl'
            path.write_text('previous session\n')
            result = subprocess.run([sys.executable, 'stars_reader.py', '--image', str(fixture),
                                     '--log', str(path)], cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Log already exists', result.stderr)
            self.assertEqual(path.read_text(), 'previous session\n')


if __name__ == '__main__':
    unittest.main()
