import {parseAmount} from './replica-model.mjs';

// Only the local fixture supplies this adapter. No browser/app/remote transport.
export function runLocalRaise(ui, amount, report = () => {}) {
  const wanted = parseAmount(amount);
  const before = ui.read();
  if (before.source !== 'local_screenshot_fixture' || before.done)
    throw new Error('Scena locale non disponibile.');
  report('1. Scena locale e versione lette.');
  ui.fill(amount);
  const fresh = ui.read();
  if (fresh.version !== before.version || fresh.done)
    throw new Error('Stato cambiato durante l’inserimento: nessun click.');
  if (parseAmount(fresh.amount) !== wanted || fresh.raiseTo !== wanted || !fresh.enabled)
    throw new Error('Campo e controllo Rilancia non coincidono o sono disabilitati.');
  report('2. Importo riletto e confrontato con il controllo Rilancia.');
  // Adapter rechecks this version immediately before activating the local DOM.
  ui.clickRaise(before.version);
  report('3. Un solo click eseguito nella replica.');
  const after = ui.read();
  if (after.version !== before.version + 1 || !after.done ||
      after.event?.action !== 'raise' || after.event?.raise_to_cents !== wanted ||
      after.event?.real_order_sent !== false)
    throw new Error('Esito non confermato: non ripetere automaticamente il click.');
  report('4. Esito simulato confermato; nessun nuovo tentativo.');
  return after.event;
}
