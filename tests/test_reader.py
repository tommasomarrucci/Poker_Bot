"""Golden-frame regression tests; these frames were not used to build templates."""
import sys
import io
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch

from PIL import ImageDraw
from stars_reader import Image, TableReader, canonical, png_frames


@unittest.skipUnless((Path(__file__).parent/'fixtures'/'218.png').exists(),
                     'Private screenshot fixtures are not distributed; see README')
class ReaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = TableReader()

    def test_recording_frames(self):
        cases = {
            '143': (['6d','4c','Ah','5c','8c'], [], 143, [250,313,515,None,801,450]),
            '218': (['Qc','Kd','7d','8s','7s'], ['5s','2s'], 14, [190,313,455,None,799,690]),
            '258': (['8c','2s','5d'], ['8d','9c'], 54, [149,301,455,None,787,712]),
        }
        for frame, (board, hero, pot, stacks) in cases.items():
            with self.subTest(frame=frame):
                im = Image.open(Path(__file__).parent/'fixtures'/f'{frame}.png')
                state, _, _ = self.reader.read(im)
                self.assertEqual(state['board'], board)
                self.assertEqual(state['hero']['cards'], hero)
                self.assertEqual(state['pot_cents'], pot)
                self.assertEqual([s['stack_cents'] for s in state['seats']], stacks)

    def test_moved_and_resized_table(self):
        im = Image.open(Path(__file__).parent/'fixtures'/'218.png')
        im = im.resize((1368, 886))
        screen = Image.new('RGB', (1800, 1200), (25,25,25))
        screen.paste(im, (150,110))
        state,_,_ = self.reader.read(screen)
        self.assertEqual(state['board'], ['Qc','Kd','7d','8s','7s'])
        self.assertEqual(state['hero']['cards'], ['5s','2s'])
        self.assertEqual(state['pot_cents'], 14)

    def test_no_table(self):
        with self.assertRaises(ValueError):
            self.reader.read(Image.new('RGB', (1710,1107), 'black'))

    def test_obscured_board_is_not_an_empty_board(self):
        im = canonical(Image.open(Path(__file__).parent/'fixtures'/'218.png'))
        ImageDraw.Draw(im).rectangle((570, 530, 1140, 690), fill='black')
        with self.assertRaisesRegex(ValueError, 'Community-card region obscured'):
            self.reader.read(im)

    def test_locked_layout_is_reused_and_rejects_resize(self):
        reader = TableReader(lock_layout=True)
        im = Image.open(Path(__file__).parent/'fixtures'/'218.png')
        first, _, _ = reader.read(im)
        with patch('stars_reader.locate_table', side_effect=AssertionError('Must not locate again')):
            second, _, _ = reader.read(im)
            self.assertEqual(first, second)
            with self.assertRaisesRegex(ValueError, 'size changed'):
                reader.read(im.resize((1368, 886)))

    def test_locked_layout_rejects_missing_table_without_relocking(self):
        reader = TableReader(lock_layout=True)
        im = Image.open(Path(__file__).parent/'fixtures'/'218.png')
        reader.read(im)
        geometry = reader.geometry
        with self.assertRaisesRegex(ValueError, 'layout missing'):
            reader.read(Image.new('RGB', im.size, 'black'))
        self.assertIs(reader.geometry, geometry)
        state, _, _ = reader.read(im)
        self.assertEqual(state['board'], ['Qc', 'Kd', '7d', '8s', '7s'])

    def test_video_pipe_preserves_pixels_and_frame_boundaries(self):
        images = [Image.new('RGB', (17, 13), 'red'), Image.new('RGB', (17, 13), 'blue')]
        stream = io.BytesIO()
        for im in images:
            im.save(stream, format='PNG')
        decoded = list(png_frames(io.BytesIO(stream.getvalue())))
        self.assertEqual([im.tobytes() for im in decoded], [im.tobytes() for im in images])
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            list(png_frames(io.BytesIO(stream.getvalue()[:-5])))

    def test_live_amounts_recover_uncertain_ocr(self):
        im = Image.open(Path(__file__).parent/'fixtures'/'live_amounts.png')
        state, _, _ = self.reader.read(im)
        self.assertEqual(state['board'], [])
        self.assertEqual(state['pot_cents'], 59)
        self.assertEqual(state['contribution_cents'], 0)
        self.assertEqual([s['stack_cents'] for s in state['seats']], [300, None, 724, 487, 473, 693])
        self.assertEqual([s['bet_cents'] for s in state['seats']], [None, None, None, 15, None, 44])
        self.assertEqual(state['dealer_seat'], 3)
        self.assertEqual(state['to_act_seat'], 4)

    def test_return_to_play_button_is_not_hero_turn(self):
        im = Image.open(Path(__file__).parent/'fixtures'/'live_sitout.png')
        state, _, _ = self.reader.read(im)
        self.assertEqual(state['board'], ['6s', '6c', 'Tc'])
        self.assertEqual(state['hero']['cards'], [])
        self.assertFalse(state['hero_controls_visible'])
        self.assertNotEqual(state['to_act_seat'], 1)
        self.assertEqual(state['pot_cents'], 11)
        self.assertEqual(state['chat_result_candidates'][0]['hand_id'], '262250807004')
        self.assertEqual(state['chat_result_candidates'][0]['winner'], 'KGEM11')
        self.assertEqual(state['chat_result_candidates'][0]['payout_cents'], 601)

    def test_queen_descender_does_not_contaminate_heart(self):
        im = Image.open(Path(__file__).parent/'fixtures'/'live_queen_heart.png')
        state, _, _ = self.reader.read(im)
        self.assertEqual(state['hero']['cards'], ['8h', 'Qh'])
        self.assertNotIn('unknown_card', state['issues'])
        self.assertEqual(state['chat_result_candidates'][0]['winner'], 'cibi690')
        self.assertEqual(state['chat_result_candidates'][0]['payout_cents'], 7)

    def test_live_rank_calibration_examples(self):
        # Development/calibration examples, not independent accuracy evidence.
        for filename, board, hero in [
                ('live_red_three.png', ['3s', '6s', '3h'], ['7h', '4c']),
                ('live_four_diamond.png', ['8s', 'As', 'Th', '5c'], ['Td', '4d'])]:
            with self.subTest(filename=filename):
                state, _, _ = self.reader.read(Image.open(Path(__file__).parent/'fixtures'/filename))
                self.assertEqual(state['board'], board)
                self.assertEqual(state['hero']['cards'], hero)

    def test_adaptive_layout_recalibrates_on_resize(self):
        reader = TableReader(lock_layout=True, allow_resize=True)
        im = Image.open(Path(__file__).parent/'fixtures'/'218.png')
        reader.read(im)
        state, _, _ = reader.read(im.resize((1368, 886)))
        self.assertEqual(reader.geometry.source_size, (1368, 886))
        self.assertEqual(state['board'], ['Qc', 'Kd', '7d', '8s', '7s'])
        self.assertEqual(state['hero']['cards'], ['5s', '2s'])
        self.assertEqual(state['pot_cents'], 14)

    def test_resized_rank_antialiasing(self):
        im = Image.open(Path(__file__).parent/'fixtures'/'resized_nine.png')
        state, _, _ = self.reader.read(im)
        self.assertEqual(state['board'], ['Ks', '2h', '9h', 'Jh', '9d'])

    def test_user_verified_queen_six(self):
        im = Image.open(Path(__file__).parent/'fixtures'/'live_queen_six.png')
        state, _, _ = self.reader.read(im)
        self.assertEqual(state['hero']['cards'], ['Qc', '6h'])


if __name__ == '__main__':
    unittest.main()
