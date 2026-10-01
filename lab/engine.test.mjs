import test from 'node:test';
import assert from 'node:assert/strict';
import { Lab, decide, executeClick, scenario } from './engine.mjs';

test('all six seats, repeated turns, streets, cards and timing are logged', () => {
  let now = 0;
  const lab = new Lab(() => now);
  lab.start();
  for (const [, , action] of scenario) {
    now += 250;
    const state = lab.snapshot();
    executeClick(decide(state), state, [{dataset:{action}, disabled:false,
      click: () => lab.act(action, state.version)}]);
  }
  assert.equal(lab.events.length, 10);
  assert.equal(new Set(lab.events.map(e => e.seat)).size, 6);
  assert.ok(lab.events.every(e => e.decision_ms === 250 && e.scenario_match));
  assert.deepEqual(lab.events[0].hero_cards, ['Qc', '6h']);
  assert.equal(lab.events[7].street, 'flop');
  assert.equal(decide(lab.snapshot()), null);
});
test('stale and duplicate decisions cannot advance the state', () => {
  const lab = new Lab(() => 0); lab.start();
  const old = lab.snapshot(); lab.act('call', old.version);
  assert.throws(() => lab.act('call', old.version), /Stale/);
  assert.throws(() => executeClick(decide(old), lab.snapshot(), []), /Stale/);
  assert.equal(lab.events.length, 1);
});
test('missing or disabled buttons fail closed', () => {
  const lab = new Lab(); lab.start(); const state = lab.snapshot();
  assert.throws(() => executeClick(decide(state), state, []), /unavailable/);
  assert.throws(() => executeClick(decide(state), state,
    [{dataset:{action:'call'}, disabled:true}]), /unavailable/);
  assert.equal(lab.events.length, 0);
});
test('invalid actions, finished scenarios and new hands', () => {
  const lab = new Lab(() => 0); lab.start();
  assert.throws(() => lab.act('bogus', lab.version), /Invalid/);
  for (const [, , action] of scenario) lab.act(action, lab.version);
  assert.throws(() => lab.act('call', lab.version), /Invalid/);
  lab.start(); assert.equal(lab.snapshot().hand_id, 'lab-2');
  assert.equal(lab.snapshot().seat, 1);
});
test('retained event history stays bounded', () => {
  const lab = new Lab(() => 0);
  for (let n = 0; n < 120; n++) {
    lab.start(); for (const [, , action] of scenario) lab.act(action, lab.version);
  }
  assert.equal(lab.events.length, 1000);
});
