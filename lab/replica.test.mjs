import test from 'node:test';
import assert from 'node:assert/strict';
import {DecisionFixture, parseAmount} from './replica-model.mjs';
test('decimal input is converted to exact integer cents', () => {
  for (const value of ['1.20', '1,2', '01.20']) assert.equal(parseAmount(value), 120);
  for (const value of ['NaN', '-1', '1.234', '1e2', '']) assert.throws(() => parseAmount(value));
});
test('raise-to subtracts only the increment and conserves chips', () => {
  const model = new DecisionFixture(() => 100);
  const event = model.act('raise', '1,20', model.version);
  assert.equal(event.paid_cents, 110);
  assert.equal(model.stack, 280); assert.equal(model.pot, 221);
  assert.equal(model.stack + model.pot, 501);
  assert.equal(event.real_order_sent, false);
});
test('call and fold accounting', () => {
  const model = new DecisionFixture();
  assert.equal(model.act('call', null, model.version).paid_cents, 37);
  model.reset(); assert.equal(model.act('fold', null, model.version).paid_cents, 0);
});
test('bounds, stale commands and duplicate clicks rejected', () => {
  const model = new DecisionFixture(); const old = model.version;
  for (const amount of ['0.83','4.01']) assert.throws(() => model.act('raise', amount, model.version));
  model.act('raise','4.00',model.version); assert.equal(model.stack,0);
  assert.throws(() => model.act('fold',null,model.version));
  model.reset(); assert.throws(() => model.act('fold',null,old));
});
