import { Lab, decide, executeClick } from './engine.mjs';
const lab = new Lab();
const $ = id => document.getElementById(id);
let timer = null;
function stop() { clearInterval(timer); timer = null; }
function render() {
  const state = lab.snapshot();
  $('seats').replaceChildren(...Array.from({length:6}, (_, i) => {
    const seat = document.createElement('div');
    seat.className = `seat ${state.seat === i+1 ? 'active' : ''}`;
    seat.textContent = `${i+1 === 1 ? 'Tu' : `Player ${i+1}`} · posto ${i+1}`;
    return seat;
  }));
  $('cards').textContent = `${state.hand_id} · ${state.street} | Tu: Q♣ 6♥ | Board: ${state.board.join(' ') || '—'}`;
  $('actions').replaceChildren(...state.legal_actions.map(action => {
    const button = document.createElement('button');
    button.textContent = action;
    button.dataset.action = action;
    button.addEventListener('click', () => {
      try {
        lab.act(action, state.version);
        render();
        if (lab.snapshot().seat === null) { stop(); $('status').textContent = 'Scenario concluso.'; }
      } catch (error) { stop(); $('status').textContent = error.message; }
    });
    return button;
  }));
  $('step').disabled = $('auto').disabled = state.seat === null;
  $('events').replaceChildren(...lab.events.slice(-100).reverse().map(event => {
    const row = document.createElement('tr');
    for (const value of [event.hand_id, event.street, event.player, event.action, `${event.decision_ms} ms`]) {
      const td = document.createElement('td'); td.textContent = value; row.append(td);
    }
    return row;
  }));
}
function step() {
  try {
    const before = lab.snapshot();
    const decision = decide(before);
    if (!decision) { stop(); return; }
    executeClick(decision, lab.snapshot(), [...$('actions').querySelectorAll('button')]);
    if (lab.snapshot().version !== before.version + 1) throw new Error('Click non confermato: automazione fermata');
    $('status').textContent = lab.snapshot().seat === null ? 'Scenario concluso: tutti i click confermati.' : `Click ${decision.action} confermato.`;
  } catch (error) { stop(); $('status').textContent = error.message; }
}
$('new').onclick = () => { stop(); lab.start(); render(); $('status').textContent = 'Mano pronta.'; };
$('step').onclick = step;
$('auto').onclick = () => { stop(); timer = setInterval(step, 1000 / Number($('fps').value)); };
$('stop').onclick = () => { stop(); $('status').textContent = 'Automazione fermata.'; };
$('fps').onchange = stop;
document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
$('export').onclick = () => {
  const blob = new Blob([lab.events.map(e => JSON.stringify(e)).join('\n') + '\n'], {type:'application/x-ndjson'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = `local-lab-${Date.now()}.jsonl`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
lab.start(); render();
