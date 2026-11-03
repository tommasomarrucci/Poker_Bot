import sqlite3
import tempfile
import unittest
from pathlib import Path

from poker_store import PokerStore


class PokerStoreTest(unittest.TestCase):
    def test_records_snapshot_events_results_and_seats(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.sqlite'
            store = PokerStore(path, source='test', log_path='session.jsonl')
            snapshot = {
                't': 1.25,
                'street': 'flop',
                'board': ['Qd', '8s', '2c'],
                'hero': {'cards': ['Qc', '6h']},
                'pot_cents': 75,
                'contribution_cents': 30,
                'to_act_seat': 1,
                'hero_controls_visible': True,
                'issues': [],
                'seats': [
                    {'seat': 1, 'name': 'Hero', 'label_raw': 'Hero', 'status_raw': '€2.70',
                     'action': None, 'stack_cents': 270, 'bet_cents': None, 'bet_raw': '',
                     'cards_visible': True, 'empty': False, 'highlighted': True},
                    {'seat': 2, 'name': 'Villain', 'label_raw': 'Villain', 'status_raw': '€4.50',
                     'action': None, 'stack_cents': 450, 'bet_cents': 40, 'bet_raw': '€0.40',
                     'cards_visible': True, 'empty': False, 'highlighted': False},
                ],
                'new_hand_results': [{'confirmed_t': 2, 'hand_id': '123', 'winner': 'Hero',
                                      'payout_cents': 100, 'ocr_confidence': 88}],
                'hand_tracker': {
                    'hand_id': 'observed-1',
                    'new_events': [{'t': 1.25, 'hand_id': 'observed-1', 'street': 'flop',
                                    'seat': 2, 'action': 'bet', 'confidence': 'medium',
                                    'from_cents': 0, 'to_cents': 40}],
                    'current': {'hero_to_call_cents': 40},
                },
            }
            store.record_snapshot(0, snapshot)
            store.close()

            db = sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM snapshot_seats').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT action, player_name FROM events').fetchone(),
                             ('bet', 'Villain'))
            self.assertEqual(db.execute('SELECT winner, payout_cents FROM hand_results').fetchone(),
                             ('Hero', 100))
            db.close()


if __name__ == '__main__':
    unittest.main()
