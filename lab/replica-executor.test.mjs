import test from 'node:test';
import assert from 'node:assert/strict';
import {runLocalRaise} from './replica-executor.mjs';

function fixture(change = () => {}) {
  const state = {source:'local_screenshot_fixture',version:1,done:false,
    amount:'0.84',raiseTo:84,enabled:true};
  let clicks = 0;
  return {state, get clicks() {return clicks;},
    read:() => ({...state}),
    fill(value) {state.amount=value; state.raiseTo=120; change(state);},
    clickRaise() {clicks++; state.version++; state.done=true;
      state.event={action:'raise',raise_to_cents:120,real_order_sent:false};},
  };
}
test('read, fill, reread, one click and confirmation', () => {
  const ui=fixture(); const trace=[];
  runLocalRaise(ui,'1,20',x=>trace.push(x));
  assert.equal(ui.clicks,1); assert.equal(trace.length,4);
  assert.throws(()=>runLocalRaise(ui,'1,20')); assert.equal(ui.clicks,1);
});
test('stale state, mismatched label/input and disabled control prevent click', () => {
  for (const change of [s=>s.version++,s=>s.raiseTo=130,s=>s.amount='1.30',s=>s.enabled=false]) {
    const ui=fixture(change); assert.throws(()=>runLocalRaise(ui,'1,20'));
    assert.equal(ui.clicks,0);
  }
});
test('unconfirmed result is not retried', () => {
  const ui=fixture(); let attempts=0; ui.clickRaise=()=>attempts++;
  assert.throws(()=>runLocalRaise(ui,'1,20'), /Esito non confermato/);
  assert.equal(attempts,1);
});
test('reject non-local adapter before filling or clicking', () => {
  const ui=fixture(); ui.state.source='other';
  assert.throws(()=>runLocalRaise(ui,'1,20')); assert.equal(ui.clicks,0);
  assert.equal(ui.state.amount,'0.84');
});
