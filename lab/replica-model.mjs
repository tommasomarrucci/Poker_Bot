// One local decision fixture from the supplied screenshot, not a poker engine.
export function parseAmount(text) {
  if (!/^\d{1,7}(?:[.,]\d{1,2})?$/.test(text)) throw new Error('Usa un importo come 0,84 o 1.20.');
  const [whole, fraction = ''] = text.replace(',', '.').split('.');
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
}
export const formatAmount = cents => (cents / 100).toFixed(2);
export class DecisionFixture {
  constructor(clock = () => performance.now()) {
    this.clock = clock; this.version = 0; this.reset();
  }
  reset() {
    this.version++; this.stack = 390; this.pot = 111;
    this.currentContribution = 10; this.toCall = 37;
    this.minRaiseTo = 84; this.maxRaiseTo = 400;
    this.done = false; this.event = null; this.started = this.clock();
  }
  act(action, amount, version) {
    if (version !== this.version || this.done) throw new Error('Comando scaduto o già eseguito: ripristina la scena.');
    if (!['fold', 'call', 'raise'].includes(action)) throw new Error('Azione non valida.');
    let paid = 0; let raiseTo = null;
    if (action === 'call') paid = this.toCall;
    if (action === 'raise') {
      raiseTo = parseAmount(amount);
      if (raiseTo < this.minRaiseTo || raiseTo > this.maxRaiseTo)
        throw new Error('In questa scena il totale deve essere tra 0,84 e 4,00.');
      paid = raiseTo - this.currentContribution;
    }
    this.stack -= paid; this.pot += paid;
    this.currentContribution += paid;
    this.done = true; this.version++;
    this.event = {source:'local_screenshot_fixture', action, raise_to_cents:raiseTo,
      paid_cents:paid, stack_cents:this.stack, pot_cents:this.pot,
      decision_ms:Math.round(this.clock()-this.started), real_order_sent:false};
    return this.event;
  }
}
