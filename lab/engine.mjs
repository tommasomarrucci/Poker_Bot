// Deterministic UI-automation fixture, NOT a complete poker rules engine.
export const scenario = [
  ['preflop', 1, 'call'], ['preflop', 2, 'fold'],
  ['preflop', 3, 'raise'], ['preflop', 4, 'fold'],
  ['preflop', 5, 'call'], ['preflop', 6, 'fold'],
  ['preflop', 1, 'call'], ['flop', 5, 'check'],
  ['flop', 1, 'check'], ['flop', 3, 'check'],
];

export class Lab {
  constructor(clock = () => performance.now()) {
    this.clock = clock;
    this.events = [];
    this.hand = 0;
    this.version = 0;
    this.index = scenario.length;
  }
  start() {
    this.hand++;
    this.index = 0;
    this.version++;
    this.started = this.clock();
    // Bound retained history; export before starting further hands if needed.
    if (this.events.length >= 1000) this.events = this.events.slice(-990);
    return this.snapshot();
  }
  snapshot() {
    const step = scenario[this.index];
    return {
      source: 'local_simulation', hand_id: `lab-${this.hand}`,
      version: this.version, hero_cards: ['Qc', '6h'],
      board: step?.[0] === 'flop' || this.index === scenario.length && this.hand > 0
        ? ['Qd', '8s', '2c'] : [],
      street: step?.[0] ?? 'complete', seat: step?.[1] ?? null,
      legal_actions: step ? ['fold', 'check', 'call', 'raise'] : [],
      expected_action: step?.[2] ?? null,
    };
  }
  act(action, version) {
    const state = this.snapshot();
    if (version !== this.version) throw new Error('Stale decision rejected');
    if (!state.legal_actions.includes(action)) throw new Error('Invalid action');
    const now = this.clock();
    const event = {
      ...state, action, player: `Player ${state.seat}`,
      decision_ms: Math.round(now - this.started),
      timing_source: 'local_monotonic_clock',
      timing_note: 'UI turn duration, including automation delay; not human thinking time',
      scenario_match: action === state.expected_action,
    };
    delete event.legal_actions;
    delete event.expected_action;
    this.events.push(event);
    this.index++;
    this.version++;
    this.started = now;
    return event;
  }
}

export function decide(snapshot) {
  // Scripted policy to exercise buttons; no strategic recommendation.
  return snapshot.seat === null ? null : {
    action: snapshot.expected_action, version: snapshot.version,
  };
}

export function executeClick(decision, snapshot, buttons) {
  if (!decision || decision.version !== snapshot.version) throw new Error('Stale decision rejected');
  const button = buttons.find(b => b.dataset.action === decision.action);
  if (!snapshot.legal_actions.includes(decision.action) || !button || button.disabled)
    throw new Error('Action button unavailable');
  button.click();
}
