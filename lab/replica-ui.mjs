import {DecisionFixture, parseAmount, formatAmount} from './replica-model.mjs';
import {runLocalRaise} from './replica-executor.mjs';
const $ = id => document.getElementById(id);
const model = new DecisionFixture();
const controls = ['fold','call','raise','amount','slider','min','pot','max','test'];
function updateAmount() {
  try {
    const cents = parseAmount($('amount').value);
    $('raise').textContent = `Rilancia a\n€${formatAmount(cents)}`;
    $('raise').disabled = model.done || cents < model.minRaiseTo || cents > model.maxRaiseTo;
    if (cents >= model.minRaiseTo && cents <= model.maxRaiseTo) $('slider').value = cents;
    $('status').textContent = $('raise').disabled ? 'Importo fuori limite: usa da 0,84 a 4,00.' : 'Importo letto. Nessuna azione ancora inviata, neanche alla simulazione.';
  } catch (error) {
    $('raise').disabled = true; $('raise').textContent = 'Importo\nnon valido'; $('status').textContent = error.message;
  }
}
function setAmount(cents) { $('amount').value = formatAmount(cents); updateAmount(); }
function render() {
  $('stack').textContent = `€${formatAmount(model.stack)}`;
  $('potLabel').textContent = `Pot: €${formatAmount(model.pot)}`;
  controls.forEach(id => $(id).disabled = model.done);
  if (model.done) {
    $('status').textContent = `Azione locale confermata: ${model.event.action}. Nessun ordine reale. Ripristina per riprovare.`;
    $('log').textContent = JSON.stringify(model.event, null, 2);
  }
}
for (const action of ['fold','call','raise']) $(action).onclick = () => {
  try { model.act(action, $('amount').value, model.version); render(); }
  catch (error) { $('status').textContent = error.message; }
};
$('amount').oninput = updateAmount;
$('slider').oninput = () => setAmount(Number($('slider').value));
$('min').onclick = () => setAmount(model.minRaiseTo);
// Pot-sized raise: current wager + pot after calling, for this fixture only.
$('pot').onclick = () => setAmount(Math.min(model.maxRaiseTo, 47 + model.pot + model.toCall));
$('max').onclick = () => setAmount(model.maxRaiseTo);
$('reset').onclick = () => {
  model.reset(); render(); setAmount(84); $('log').textContent = '';
  $('trace').textContent = '';
  $('status').textContent = 'Scena ripristinata: una decisione locale disponibile.';
};
$('test').onclick = () => {
  const trace = [];
  // These IDs belong only to our local document, not to PokerStars.
  const ui = {
    read() {
      const label = $('raise').textContent.match(/^Rilancia a\s*€(\d+[.,]\d{2})$/);
      return {source:'local_screenshot_fixture', version:model.version,
        done:model.done, amount:$('amount').value,
        raiseTo:label ? parseAmount(label[1]) : null,
        enabled:!$('raise').disabled && !$('amount').disabled,
        event:model.event};
    },
    fill(value) {
      $('amount').value = value;
      $('amount').dispatchEvent(new Event('input', {bubbles:true}));
    },
    clickRaise(version) {
      if (version !== model.version || model.done || $('raise').disabled)
        throw new Error('Stato cambiato prima del click.');
      $('raise').click();
    },
  };
  try {
    runLocalRaise(ui, '1,20', message => trace.push(message));
  } catch (error) {
    $('status').textContent = error.message;
    trace.push(`STOP: ${error.message}`);
  } finally {
    $('trace').textContent = trace.join('\n');
  }
};
