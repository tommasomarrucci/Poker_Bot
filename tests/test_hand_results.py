import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hand_results import parse_results, ResultObserver


def message(winner='KGEM11', payout='6.01', hand='262250807004'):
    text = f'Dealer: Mano n° {hand} {winner} vince €{payout} dal piatto'
    return [(word, 90) for word in text.split()]


class ResultTest(unittest.TestCase):
    def test_explicit_payout_and_hand_id(self):
        _, results = parse_results(message())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['hand_id'], '262250807004')
        self.assertEqual(results[0]['winner'], 'KGEM11')
        self.assertEqual(results[0]['payout_cents'], 601)

    def test_unrelated_text_and_low_confidence_do_not_produce_results(self):
        self.assertEqual(parse_results([('Dealer: tocca a te, KGEM11', 95)])[1], [])
        words = [(w, 10 if w == 'KGEM11' else c) for w, c in message()]
        self.assertEqual(parse_results(words)[1], [])

    def test_two_observations_and_deduplication(self):
        candidates = parse_results(message())[1]
        observer = ResultObserver()
        self.assertEqual(observer.update(candidates, 1), [])
        events = observer.update(candidates, 2)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['visible_at_start'])
        self.assertEqual(events[0]['relation_to_current_cards'], 'not_assumed')
        self.assertIsNone(events[0]['net_profit_cents'])
        self.assertEqual(observer.update(candidates, 3), [])
        observer.update([], 4)
        observer.update(candidates, 5)
        self.assertEqual(observer.update(candidates, 6), [])

    def test_error_breaks_confirmation(self):
        candidates = parse_results(message())[1]
        observer = ResultObserver()
        observer.update(candidates, 1)
        observer.unreadable()
        self.assertEqual(observer.update(candidates, 2), [])
        self.assertEqual(len(observer.update(candidates, 3)), 1)

    def test_multiple_payouts_are_not_collapsed_to_a_single_winner(self):
        candidates = parse_results(message() + message(winner='AnotherPlayer', payout='2,50'))[1]
        observer = ResultObserver()
        observer.update(candidates, 1)
        events = observer.update(candidates, 2)
        self.assertEqual([e['payout_cents'] for e in events], [601, 250])

    def test_duplicate_text_in_one_image_is_not_confirmation(self):
        candidates = parse_results(message())[1]
        observer = ResultObserver()
        self.assertEqual(observer.update(candidates * 2, 1), [])


if __name__ == '__main__':
    unittest.main()
