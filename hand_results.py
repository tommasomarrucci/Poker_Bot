"""Conservative result observations from the visible Italian dealer chat.

These messages can concern an older hand. Never associate them with the currently
displayed cards, infer a net loss, or assume one payout describes all side pots.
"""
import re
from collections import OrderedDict
from decimal import Decimal


RESULT = re.compile(
    r'Mano\s+n[°ºo.]?\s*(?P<hand_id>\d{10,15})\s+'
    r'(?P<winner>\S+)\s+vince\s*[€£E]\s*'
    r'(?P<amount>\d+(?:[.,]\d{1,2})?)(?![\d.,])', re.I)


def parse_results(words):
    """Extract only messages with an explicit hand ID, winner, and payout."""
    text = ''
    spans = []
    for word, confidence in words:
        start = len(text)
        text += word + ' '
        spans.append((start, len(text) - 1, confidence))
    results = []
    for match in RESULT.finditer(text):
        start, end = match.start('hand_id'), match.end('amount')
        confidence = min((c for a, b, c in spans if a < end and b > start), default=0)
        if confidence < 60:
            continue
        results.append({'hand_id': match['hand_id'], 'winner': match['winner'],
                        'payout_cents': int(Decimal(match['amount'].replace(',', '.')) * 100),
                        'ocr_confidence': round(confidence, 2),
                        'source': 'visible_dealer_chat', 'raw': match[0]})
    return text.strip(), results


class ResultObserver:
    """Require two successive readable observations; deduplicate repeated chat."""
    def __init__(self):
        self.pending = {}
        self.seen = OrderedDict()
        self.frames = 0

    def update(self, candidates, t):
        self.frames += 1
        pending = {}
        events = []
        for result in candidates:
            key = (result['hand_id'], result['winner'], result['payout_cents'])
            if key in pending:
                continue
            previous = self.pending.get(key)
            count, first_seen, at_start = previous if previous else (0, t, self.frames == 1)
            pending[key] = (count + 1, first_seen, at_start)
            if count >= 1 and key not in self.seen:
                events.append({**result, 'first_seen_t': first_seen, 'confirmed_t': t,
                               'visible_at_start': at_start,
                               'relation_to_current_cards': 'not_assumed',
                               'net_profit_cents': None})
                self.seen[key] = True
                if len(self.seen) > 512:
                    self.seen.popitem(last=False)
        self.pending = pending
        return events

    def unreadable(self):
        self.frames += 1
        self.pending.clear()
