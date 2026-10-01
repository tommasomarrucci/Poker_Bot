"""Read-only command previews. No mouse, keyboard, or execution backend."""
import re
from decimal import Decimal


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
        'target_coordinates': None, 'sent': False,
    }
