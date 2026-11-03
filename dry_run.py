"""Read-only command previews. No mouse, keyboard, or execution backend."""
import re
from decimal import Decimal

CANONICAL_COORDINATE_SPACE = 'canonical_table_image_1710x1107'

# Calibrated read-only regions in the canonical table image. These are not
# desktop coordinates and this module intentionally has no mouse/keyboard API.
CONTROL_REGIONS = {
    'fold_button': {
        'role': 'fold_button',
        'box': [35, 945, 250, 1095],
        'expected_labels': ['Fold'],
    },
    'middle_action_button': {
        'role': 'middle_action_button',
        'box': [260, 945, 475, 1095],
        'expected_labels': ['Check', 'Vedi'],
    },
    'right_action_button': {
        'role': 'right_action_button',
        'box': [485, 945, 700, 1095],
        'expected_labels': ['Puntata', 'Rilancia'],
    },
    'amount_input': {
        'role': 'amount_input',
        'box': [720, 1000, 870, 1095],
        'expected_labels': [],
    },
}

ACTION_REGIONS = {
    'fold': ['fold_button'],
    'check': ['middle_action_button'],
    'call': ['middle_action_button'],
    'raise': ['amount_input', 'right_action_button'],
}


def command(action, amount=None):
    if action not in ('fold', 'check', 'call', 'raise'):
        raise ValueError('Action must be fold, check, call or raise')
    if action != 'raise' and amount is not None:
        raise ValueError('An amount is supported only for raise')
    cents = None
    if action == 'raise':
        if amount is None or not re.fullmatch(r'[0-9]{1,9}(?:[.,][0-9]{1,2})?', amount):
            raise ValueError('Raise requires a positive decimal amount, e.g. 1,50 (no thousands separators)')
        cents = int(Decimal(amount.replace(',', '.')) * 100)
        if cents <= 0:
            raise ValueError('Amount must be positive')
    return {'action': action, 'requested_raise_to_cents': cents}


def control_regions(state):
    if not state.get('hero_controls_visible') or state.get('to_act_seat') != 1:
        return []
    return [
        {
            **region,
            'coordinate_space': CANONICAL_COORDINATE_SPACE,
            'screen_coordinates': False,
            'clickable': False,
        }
        for region in CONTROL_REGIONS.values()
    ]


def regions_for_action(request, state):
    visible = {r['role']: r for r in control_regions(state)}
    return [visible[role] for role in ACTION_REGIONS[request['action']] if role in visible]


def preview(request, state):
    reasons = []
    if state.get('status') == 'unreadable':
        reasons.append('unreadable_snapshot')
    if not state.get('hero_controls_visible') or state.get('to_act_seat') != 1:
        reasons.append('hero_turn_not_confirmed')
    if state.get('issues'):
        reasons.append('reader_reports_uncertainty')
    # Existing reader detects a generic control area, not individual buttons,
    # allowed actions, call price, raise limits or the input field contents.
    reasons.append('individual_controls_and_legal_amounts_not_verified')
    cents = request['requested_raise_to_cents']
    return {
        **request, 'mode': 'dry_run', 'execution_enabled': False,
        'status': 'not_verified', 'reasons': reasons,
        'snapshot_t': state.get('t'),
        'amount_text_example': None if cents is None else f'{cents // 100},{cents % 100:02d}',
        'amount_semantics': 'requested_total_raise_to_not_increment' if cents is not None else None,
        'target_coordinates': None,
        'target_regions': regions_for_action(request, state),
        'coordinate_note': 'Regions are for visual verification only, not OS mouse coordinates.',
        'sent': False,
    }
