import unittest
from dry_run import command, control_regions, preview


class DryRunTest(unittest.TestCase):
    def test_check_preview_only(self):
        result = preview(command('check'), {'hero_controls_visible': True, 'to_act_seat': 1})
        self.assertEqual(result['action'], 'check')
        self.assertFalse(result['sent'])
        self.assertFalse(result['execution_enabled'])
        self.assertIsNone(result['requested_raise_to_cents'])
        with self.assertRaises(ValueError):
            command('check', '1')

    def test_decimal_input(self):
        for text in ('1.50', '1,50', '01.50'):
            self.assertEqual(command('raise', text)['requested_raise_to_cents'], 150)
        self.assertEqual(command('raise', '0.01')['requested_raise_to_cents'], 1)

    def test_invalid_amounts(self):
        for text in (None, '0', '-1', 'NaN', 'Infinity', '1.001', '1,000.00', '1e2', ''):
            with self.subTest(text=text), self.assertRaises(ValueError):
                command('raise', text)
        with self.assertRaises(ValueError):
            command('fold', '1')
        with self.assertRaises(ValueError):
            command('bet')

    def test_visible_turn_is_not_permission_to_execute(self):
        state = {'t': 123, 'hero_controls_visible': True, 'to_act_seat': 1, 'issues': []}
        result = preview(command('raise', '1,50'), state)
        self.assertFalse(result['sent'])
        self.assertFalse(result['execution_enabled'])
        self.assertEqual(result['status'], 'not_verified')
        self.assertEqual(result['amount_text_example'], '1,50')
        self.assertIsNone(result['target_coordinates'])
        self.assertEqual([r['role'] for r in result['target_regions']],
                         ['amount_input', 'right_action_button'])
        self.assertTrue(all(not r['clickable'] for r in result['target_regions']))

    def test_unreadable_or_missing_turn(self):
        result = preview(command('call'), {'status': 'unreadable'})
        self.assertIn('unreadable_snapshot', result['reasons'])
        self.assertIn('hero_turn_not_confirmed', result['reasons'])
        self.assertIsNone(result['amount_text_example'])
        self.assertEqual(result['target_regions'], [])

    def test_control_regions_are_visual_only(self):
        regions = control_regions({'hero_controls_visible': True, 'to_act_seat': 1})
        self.assertEqual([r['role'] for r in regions],
                         ['fold_button', 'middle_action_button', 'right_action_button', 'amount_input'])
        self.assertTrue(all(r['coordinate_space'] == 'canonical_table_image_1710x1107' for r in regions))
        self.assertTrue(all(r['screen_coordinates'] is False for r in regions))
        self.assertTrue(all(r['clickable'] is False for r in regions))
