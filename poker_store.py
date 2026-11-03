"""SQLite recorder for read-only PokerStars observations."""

import json
import sqlite3
import time
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at REAL NOT NULL,
  source TEXT,
  log_path TEXT,
  version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS snapshots (
  run_id INTEGER NOT NULL,
  frame_index INTEGER NOT NULL,
  t REAL,
  status TEXT,
  hand_id TEXT,
  street TEXT,
  pot_cents INTEGER,
  contribution_cents INTEGER,
  to_act_seat INTEGER,
  hero_controls_visible INTEGER,
  issues_json TEXT NOT NULL,
  board_json TEXT NOT NULL,
  hero_cards_json TEXT NOT NULL,
  capture_json TEXT,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, frame_index)
);
CREATE TABLE IF NOT EXISTS snapshot_seats (
  run_id INTEGER NOT NULL,
  frame_index INTEGER NOT NULL,
  seat INTEGER NOT NULL,
  player_name TEXT,
  label_raw TEXT,
  status_raw TEXT,
  action TEXT,
  stack_cents INTEGER,
  bet_cents INTEGER,
  bet_raw TEXT,
  cards_visible INTEGER,
  empty INTEGER,
  highlighted INTEGER,
  PRIMARY KEY (run_id, frame_index, seat)
);
CREATE TABLE IF NOT EXISTS events (
  run_id INTEGER NOT NULL,
  event_index INTEGER NOT NULL,
  t REAL,
  hand_id TEXT,
  street TEXT,
  seat INTEGER,
  action TEXT NOT NULL,
  confidence TEXT,
  player_name TEXT,
  amount_from_cents INTEGER,
  amount_to_cents INTEGER,
  pot_cents INTEGER,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, event_index)
);
CREATE TABLE IF NOT EXISTS hand_results (
  run_id INTEGER NOT NULL,
  result_index INTEGER NOT NULL,
  t REAL,
  hand_id TEXT,
  winner TEXT,
  payout_cents INTEGER,
  ocr_confidence REAL,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, result_index)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_hand ON snapshots(run_id, hand_id, frame_index);
CREATE INDEX IF NOT EXISTS idx_events_hand ON events(run_id, hand_id, event_index);
CREATE INDEX IF NOT EXISTS idx_events_action ON events(run_id, action);
CREATE INDEX IF NOT EXISTS idx_seats_player ON snapshot_seats(run_id, player_name);
"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _seat_player(snapshot, seat_id):
    for seat in snapshot.get('seats') or []:
        if seat.get('seat') == seat_id:
            return seat.get('name') or seat.get('label_raw')
    return None


class PokerStore:
    def __init__(self, path, source=None, log_path=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)
        self.db.execute('INSERT INTO runs(started_at, source, log_path) VALUES (?, ?, ?)',
                        (time.time(), source, str(log_path) if log_path else None))
        self.run_id = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.event_index = 0
        self.result_index = 0
        self.db.commit()

    def record_snapshot(self, frame_index, snapshot):
        tracker = snapshot.get('hand_tracker') or {}
        current = tracker.get('current') or {}
        capture = snapshot.get('capture')
        self.db.execute(
            """INSERT INTO snapshots VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.run_id, frame_index, snapshot.get('t'), snapshot.get('status'),
             tracker.get('hand_id'), snapshot.get('street'), snapshot.get('pot_cents'),
             snapshot.get('contribution_cents'), snapshot.get('to_act_seat'),
             int(bool(snapshot.get('hero_controls_visible'))),
             _json(snapshot.get('issues') or []), _json(snapshot.get('board') or []),
             _json((snapshot.get('hero') or {}).get('cards') or []),
             _json(capture) if capture is not None else None, _json(snapshot)))
        for seat in snapshot.get('seats') or []:
            self.db.execute(
                """INSERT INTO snapshot_seats VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.run_id, frame_index, seat.get('seat'), seat.get('name'),
                 seat.get('label_raw'), seat.get('status_raw'), seat.get('action'),
                 seat.get('stack_cents'), seat.get('bet_cents'), seat.get('bet_raw'),
                 int(bool(seat.get('cards_visible'))), int(bool(seat.get('empty'))),
                 int(bool(seat.get('highlighted')))))
        for event in tracker.get('new_events') or []:
            self.record_event(event, snapshot)
        for result in snapshot.get('new_hand_results') or []:
            self.record_hand_result(result)
        return current

    def record_event(self, event, snapshot=None):
        self.event_index += 1
        seat = event.get('seat')
        player = event.get('player_name') or (_seat_player(snapshot or {}, seat) if seat else None)
        self.db.execute(
            """INSERT INTO events VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.run_id, self.event_index, event.get('t'), event.get('hand_id'),
             event.get('street'), seat, event.get('action'), event.get('confidence'),
             player, event.get('from_cents'), event.get('to_cents'),
             event.get('pot_cents'), _json(event)))

    def record_hand_result(self, result):
        self.result_index += 1
        self.db.execute(
            """INSERT INTO hand_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.run_id, self.result_index, result.get('confirmed_t'),
             result.get('hand_id'), result.get('winner'), result.get('payout_cents'),
             result.get('ocr_confidence'), _json(result)))

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()
