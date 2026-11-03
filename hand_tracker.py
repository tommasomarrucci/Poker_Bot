"""Read-only temporal hand tracking from consecutive table snapshots.

The tracker is deliberately conservative: it records observations and inferred
events, but does not claim a complete hand history or legal-action oracle.
"""

from copy import deepcopy


STREET_ORDER = {'no_board': 0, 'flop': 1, 'turn': 2, 'river': 3}


def _seat_map(snapshot):
    return {seat.get('seat'): seat for seat in snapshot.get('seats', [])}


def _cards(snapshot):
    return tuple(snapshot.get('hero', {}).get('cards') or ())


def _board(snapshot):
    return tuple(snapshot.get('board') or ())


def _bet_value(snapshot, seat):
    issues = snapshot.get('issues') or []
    raw = (seat.get('bet_raw') or '').strip()
    if seat.get('bet_cents') is not None:
        return seat['bet_cents']
    if raw or f"bet_unreadable_seat_{seat.get('seat')}" in issues:
        return None
    return 0


def _stack_value(seat):
    return seat.get('stack_cents')


def _seat_bets(snapshot):
    return {seat_id: _bet_value(snapshot, seat)
            for seat_id, seat in _seat_map(snapshot).items()}


def _known_max(values):
    known = [value for value in values if value is not None]
    return max(known, default=0)


def _fingerprint(snapshot):
    seats = []
    for seat_id, seat in sorted(_seat_map(snapshot).items()):
        seats.append((seat_id, _bet_value(snapshot, seat), seat.get('stack_cents'),
                      bool(seat.get('cards_visible')), bool(seat.get('empty')),
                      seat.get('action')))
    return (snapshot.get('street'), _board(snapshot), _cards(snapshot),
            snapshot.get('pot_cents'), snapshot.get('to_act_seat'),
            bool(snapshot.get('hero_controls_visible')), tuple(seats))


def _event(t, hand_id, street, seat, action, **fields):
    return {'t': t, 'hand_id': hand_id, 'street': street, 'seat': seat,
            'action': action, **fields}


class HandTracker:
    """Diff readable snapshots into a bounded, best-effort event timeline."""

    def __init__(self, stable_frames=2, max_events=1000):
        self.stable_frames = stable_frames
        self.max_events = max_events
        self.hand_no = 0
        self.hand_id = None
        self.previous = None
        self.previous_fingerprint = None
        self.same_fingerprint_count = 0
        self.street = None
        self.street_bets = {}
        self.preflop_aggressor = None
        self.last_aggressor = None
        self.hero_decision_open = False
        self.pass_events = set()
        self.events = []

    def update(self, snapshot):
        t = snapshot.get('t')
        if snapshot.get('status') == 'unreadable':
            return {'status': 'unreadable', 'hand_id': self.hand_id,
                    'stable_frames': 0, 'new_events': [],
                    'current': self.current_state(snapshot)}
        if snapshot.get('issues'):
            status = 'uncertain_snapshot'
        else:
            status = 'tracking'

        fingerprint = _fingerprint(snapshot)
        if fingerprint == self.previous_fingerprint:
            self.same_fingerprint_count += 1
        else:
            self.same_fingerprint_count = 1
        self.previous_fingerprint = fingerprint
        settled = self.same_fingerprint_count >= self.stable_frames

        new_events = []
        started = False
        if self._starts_new_hand(snapshot):
            new_events.append(self._start_hand(snapshot, settled))
            new_events.extend(self._initial_snapshot_events(snapshot, settled))
            started = True
        elif self.hand_id is None:
            new_events.append(self._start_hand(snapshot, settled))
            new_events.extend(self._initial_snapshot_events(snapshot, settled))
            started = True

        if self.previous is not None and not started:
            new_events.extend(self._diff_snapshot(self.previous, snapshot, settled))
        new_events.extend(self._hero_decision_events(snapshot, settled))

        self.previous = deepcopy(snapshot)
        self._remember(new_events)
        return {'status': status if settled else 'waiting_for_stability',
                'hand_id': self.hand_id, 'stable_frames': self.same_fingerprint_count,
                'settled': settled, 'new_events': new_events,
                'current': self.current_state(snapshot)}

    def current_state(self, snapshot=None):
        snapshot = snapshot or self.previous or {}
        bets = _seat_bets(snapshot)
        max_bet = _known_max(bets.values())
        hero_bet = bets.get(1)
        to_call = None if hero_bet is None else max(0, max_bet - hero_bet)
        return {'street': snapshot.get('street'), 'board': list(_board(snapshot)),
                'hero_cards': list(_cards(snapshot)), 'pot_cents': snapshot.get('pot_cents'),
                'street_bets': bets, 'current_bet_cents': max_bet,
                'hero_to_call_cents': to_call,
                'to_act_seat': snapshot.get('to_act_seat'),
                'hero_controls_visible': bool(snapshot.get('hero_controls_visible')),
                'last_aggressor': self.last_aggressor,
                'preflop_aggressor': self.preflop_aggressor,
                'scope': 'best_effort_visual_timeline'}

    def _starts_new_hand(self, snapshot):
        if self.previous is None:
            return True
        old_cards, new_cards = _cards(self.previous), _cards(snapshot)
        if old_cards and new_cards and old_cards != new_cards:
            return True
        old_board, new_board = _board(self.previous), _board(snapshot)
        if old_board and not new_board and snapshot.get('street') == 'no_board':
            old_pot = self.previous.get('pot_cents')
            new_pot = snapshot.get('pot_cents')
            if new_pot is None or old_pot is None or new_pot <= old_pot:
                return True
        return False

    def _start_hand(self, snapshot, settled):
        self.hand_no += 1
        self.hand_id = f"observed-{self.hand_no}"
        self.street = snapshot.get('street')
        self.street_bets = _seat_bets(snapshot)
        self.preflop_aggressor = None
        self.last_aggressor = None
        self.hero_decision_open = False
        self.pass_events = set()
        return _event(snapshot.get('t'), self.hand_id, self.street, None, 'hand_start',
                      confidence='medium' if settled else 'low',
                      evidence=['new_or_first_readable_snapshot'],
                      board=list(_board(snapshot)), hero_cards=list(_cards(snapshot)))

    def _initial_snapshot_events(self, snapshot, settled):
        if snapshot.get('street') != 'no_board':
            return []
        positives = [(seat_id, value) for seat_id, value in _seat_bets(snapshot).items()
                     if value is not None and value > 0]
        if len(positives) != 2:
            return []
        return self._contribution_events(
            snapshot, [(seat_id, 0, value) for seat_id, value in positives],
            0, max(value for _, value in positives), settled)

    def _diff_snapshot(self, old, new, settled):
        events = []
        old_street, new_street = old.get('street'), new.get('street')
        if STREET_ORDER.get(new_street, -1) > STREET_ORDER.get(old_street, -1):
            from_street = self.street if self.street in STREET_ORDER else old_street
            self.street = new_street
            self.street_bets = {seat_id: 0 for seat_id in _seat_bets(new)}
            self.last_aggressor = None
            self.pass_events = set()
            events.append(_event(new.get('t'), self.hand_id, new_street, None, 'street_change',
                                 confidence='high' if settled else 'medium',
                                 evidence=['board_size_increased'],
                                 from_street=from_street, board=list(_board(new))))
        elif new_street in STREET_ORDER and new_street != 'unknown':
            self.street = new_street

        old_bets = _seat_bets(old)
        new_bets = _seat_bets(new)
        old_max = _known_max(old_bets.values())
        new_max = _known_max(new_bets.values())
        increases = []
        for seat_id in sorted(new_bets):
            old_bet = old_bets.get(seat_id, 0)
            new_bet = new_bets[seat_id]
            if old_bet is None or new_bet is None or new_bet <= old_bet:
                continue
            increases.append((seat_id, old_bet, new_bet))

        events.extend(self._contribution_events(new, increases, old_max, new_max, settled))
        events.extend(self._turn_pass_events(old, new, increases, old_max, settled))
        return events

    def _contribution_events(self, snapshot, increases, old_max, new_max, settled):
        events = []
        first_preflop = (snapshot.get('street') == 'no_board'
                         and not any(e['action'] not in ('hand_start', 'hero_decision_point')
                                     for e in self.events if e['hand_id'] == self.hand_id))
        blind_candidates = self._blind_candidates(increases) if first_preflop and old_max == 0 else {}
        seats = _seat_map(snapshot)
        running_max = old_max
        for seat_id, old_bet, new_bet in increases:
            action = blind_candidates.get(seat_id)
            evidence = ['bet_increased']
            confidence = 'high' if settled else 'medium'
            if action:
                evidence.append('first_preflop_contribution')
                confidence = 'medium' if settled else 'low'
            elif old_max == 0:
                action = 'bet'
            elif new_bet > running_max:
                action = 'raise'
                running_max = new_bet
            elif new_bet == running_max:
                action = 'call'
            else:
                action = 'short_call_or_all_in'
                confidence = 'medium' if settled else 'low'
            stack = _stack_value(seats.get(seat_id, {}))
            if stack == 0 and action not in ('small_blind', 'big_blind'):
                action = 'all_in_' + action
                evidence.append('stack_zero')
            if action in ('bet', 'raise', 'all_in_bet', 'all_in_raise'):
                self.last_aggressor = seat_id
                if snapshot.get('street') == 'no_board':
                    self.preflop_aggressor = seat_id
                self.pass_events = {key for key in self.pass_events
                                    if key[1] != snapshot.get('street')}
            self.street_bets[seat_id] = new_bet
            events.append(_event(snapshot.get('t'), self.hand_id, snapshot.get('street'),
                                 seat_id, action, confidence=confidence, evidence=evidence,
                                 from_cents=old_bet, to_cents=new_bet,
                                 table_current_bet_cents=new_max))
        return events

    def _blind_candidates(self, increases):
        positives = sorted((new_bet, seat_id) for seat_id, _, new_bet in increases if new_bet > 0)
        if len(positives) < 2:
            return {}
        small, big = positives[0], positives[1]
        if small[0] < big[0] <= small[0] * 3:
            return {small[1]: 'small_blind', big[1]: 'big_blind'}
        return {}

    def _turn_pass_events(self, old, new, increases, old_max, settled):
        old_actor = old.get('to_act_seat')
        if old_actor is None or old_actor == new.get('to_act_seat'):
            return []
        if any(seat_id == old_actor for seat_id, _, _ in increases):
            return []
        old_seats, new_seats = _seat_map(old), _seat_map(new)
        old_bet = _bet_value(old, old_seats.get(old_actor, {}))
        action = None
        evidence = ['turn_moved_without_bet_increase']
        if old_seats.get(old_actor, {}).get('cards_visible') and not new_seats.get(old_actor, {}).get('cards_visible'):
            action = 'fold'
            evidence.append('cards_no_longer_visible')
        elif old_bet is not None and old_bet >= old_max:
            action = 'check_or_pass'
        if not action:
            return []
        key = (self.hand_id, old.get('street'), tuple(_board(old)), old_actor, action)
        if key in self.pass_events:
            return []
        self.pass_events.add(key)
        return [_event(new.get('t'), self.hand_id, old.get('street'), old_actor, action,
                       confidence='medium' if settled else 'low', evidence=evidence)]

    def _hero_decision_events(self, snapshot, settled):
        visible = bool(snapshot.get('hero_controls_visible') and snapshot.get('to_act_seat') == 1)
        if not visible:
            self.hero_decision_open = False
            return []
        current = self.current_state(snapshot)
        if self.hero_decision_open:
            return []
        self.hero_decision_open = True
        return [_event(snapshot.get('t'), self.hand_id, snapshot.get('street'), 1,
                       'hero_decision_point',
                       confidence='high' if settled else 'medium',
                       evidence=['hero_controls_visible'],
                       to_call_cents=current['hero_to_call_cents'],
                       current_bet_cents=current['current_bet_cents'],
                       pot_cents=snapshot.get('pot_cents'))]

    def _remember(self, events):
        self.events.extend(events)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
