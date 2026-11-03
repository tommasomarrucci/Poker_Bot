import unittest

from hand_tracker import HandTracker


def snapshot(t=0, street='no_board', board=None, bets=None, stacks=None, to_act=None,
             hero_controls=False, hero_cards=None, visible=None, pot=0, issues=None):
    bets = bets or {}
    stacks = stacks or {}
    visible = visible or {}
    return {
        't': t,
        'street': street,
        'board': board or [],
        'hero': {'seat': 1, 'cards': hero_cards or ['Qc', '6h']},
        'pot_cents': pot,
        'to_act_seat': to_act,
        'hero_controls_visible': hero_controls,
        'issues': issues or [],
        'seats': [
            {'seat': seat, 'bet_cents': bets.get(seat), 'bet_raw': '' if seat not in bets else str(bets[seat]),
             'stack_cents': stacks.get(seat, 1000), 'cards_visible': visible.get(seat, True),
             'empty': False, 'action': None}
            for seat in range(1, 7)
        ],
    }


class HandTrackerTest(unittest.TestCase):
    def test_detects_initial_blinds_from_first_preflop_contributions(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, bets={}, pot=0))
        result = tracker.update(snapshot(t=2, bets={2: 5, 3: 10}, pot=15))
        actions = [(e['seat'], e['action']) for e in result['new_events']]
        self.assertIn((2, 'small_blind'), actions)
        self.assertIn((3, 'big_blind'), actions)

    def test_detects_blinds_already_present_in_first_readable_snapshot(self):
        tracker = HandTracker()
        result = tracker.update(snapshot(t=1, bets={1: 2, 2: 5}, pot=7))
        actions = [(e['seat'], e['action']) for e in result['new_events']]
        self.assertEqual(actions, [(None, 'hand_start'), (1, 'small_blind'), (2, 'big_blind')])

    def test_fast_raise_and_call_between_two_frames_are_not_lost(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, bets={2: 5, 3: 10}, pot=15, to_act=4))
        result = tracker.update(snapshot(t=1.2, bets={2: 5, 3: 10, 4: 30, 5: 30},
                                         pot=75, to_act=6))
        actions = [(e['seat'], e['action'], e.get('to_cents')) for e in result['new_events']]
        self.assertIn((4, 'raise', 30), actions)
        self.assertIn((5, 'call', 30), actions)
        self.assertEqual(result['current']['preflop_aggressor'], 4)

    def test_street_change_and_continuation_bet_are_tracked(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, bets={1: 30, 3: 30}, pot=75, to_act=3))
        result = tracker.update(snapshot(t=2, street='flop', board=['Qd', '8s', '2c'],
                                         bets={}, pot=75, to_act=3))
        self.assertEqual(result['new_events'][0]['action'], 'street_change')
        result = tracker.update(snapshot(t=2.2, street='flop', board=['Qd', '8s', '2c'],
                                         bets={3: 40}, pot=115, to_act=1,
                                         hero_controls=True))
        actions = [e['action'] for e in result['new_events']]
        self.assertIn('bet', actions)
        self.assertIn('hero_decision_point', actions)
        self.assertEqual(result['current']['hero_to_call_cents'], 40)

    def test_turn_moves_without_paid_call_can_be_fold_or_check(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, bets={2: 10, 3: 10}, to_act=2,
                                visible={2: True, 3: True}))
        result = tracker.update(snapshot(t=2, bets={2: 10, 3: 10}, to_act=3,
                                         visible={2: True, 3: True}))
        self.assertIn('check_or_pass', [e['action'] for e in result['new_events']])
        tracker.update(snapshot(t=3, bets={2: 10, 3: 20}, to_act=2,
                                visible={2: True, 3: True}))
        result = tracker.update(snapshot(t=4, bets={2: 10, 3: 20}, to_act=3,
                                         visible={2: False, 3: True}))
        self.assertIn('fold', [e['action'] for e in result['new_events']])

    def test_duplicate_check_or_pass_is_suppressed_until_street_changes(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, street='flop', board=['Qd', '8s', '2c'],
                                bets={}, to_act=2))
        result = tracker.update(snapshot(t=2, street='flop', board=['Qd', '8s', '2c'],
                                         bets={}, to_act=1))
        self.assertIn('check_or_pass', [e['action'] for e in result['new_events']])
        tracker.update(snapshot(t=3, street='flop', board=['Qd', '8s', '2c'],
                                bets={}, to_act=2))
        result = tracker.update(snapshot(t=4, street='flop', board=['Qd', '8s', '2c'],
                                         bets={}, to_act=1))
        self.assertNotIn('check_or_pass', [e['action'] for e in result['new_events']])
        result = tracker.update(snapshot(t=5, street='turn', board=['Qd', '8s', '2c', '4h'],
                                         bets={}, to_act=1))
        self.assertIn('street_change', [e['action'] for e in result['new_events']])

    def test_unknown_transition_uses_last_known_street(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, street='flop', board=['Qd', '8s', '2c'], bets={}))
        tracker.update(snapshot(t=2, street='unknown', board=['Qd', '8s', '2c', '?h'], bets={}))
        result = tracker.update(snapshot(t=3, street='turn', board=['Qd', '8s', '2c', '4h'], bets={}))
        event = next(e for e in result['new_events'] if e['action'] == 'street_change')
        self.assertEqual(event['from_street'], 'flop')

    def test_unreadable_snapshot_does_not_advance_history(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, bets={2: 5, 3: 10}))
        result = tracker.update({'t': 2, 'status': 'unreadable'})
        self.assertEqual(result['status'], 'unreadable')
        self.assertEqual(result['new_events'], [])

    def test_new_hand_does_not_diff_against_previous_hand(self):
        tracker = HandTracker()
        tracker.update(snapshot(t=1, street='river', board=['Qd', '8s', '2c', '4h', 'Ts'],
                                bets={1: 100, 3: 100}, hero_cards=['Qc', '6h']))
        result = tracker.update(snapshot(t=2, street='no_board', board=[], bets={2: 5, 3: 10},
                                         hero_cards=['As', 'Ad']))
        self.assertEqual([e['action'] for e in result['new_events']],
                         ['hand_start', 'small_blind', 'big_blind'])


if __name__ == '__main__':
    unittest.main()
