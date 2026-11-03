# PokerStars coordinate reference

Questo documento raccoglie le coordinate viste sul tavolo PokerStars nella configurazione corrente del browser.

Le coordinate principali sono in formato browser client, cioe quelle mostrate dal riquadro verde con `x` e `y`. Sono le coordinate da usare come riferimento visivo sul tavolo aperto nel browser. Se la finestra cambia dimensione, se cambi zoom, se apri o chiudi DevTools, o se cambia il layout del tavolo, le coordinate vanno ricontrollate.

## Sistema di coordinate

Coordinate browser client: valori mostrati dal riquadro verde, per esempio `x: 360, y: 1023`.

Coordinate PNG Retina: valori dello screenshot salvato, circa il doppio delle coordinate browser. Per passare da PNG a client, dividi per 2.

Esempio:

```text
Centro PNG    720, 2045
Centro client 360, 1023
```

## Bottoni principali a tre pulsanti

Questi sono i tre bottoni rossi principali quando sono visibili Fold, Vedi o Check, e Rilancia o Puntata.

| Controllo | Centro client | Rettangolo client approssimativo | Note |
|---|---:|---:|---|
| Fold | `141, 1023` | `x 37-245, y 958-1087` | Primo bottone rosso |
| Vedi o Check | `360, 1023` | `x 256-464, y 958-1087` | Secondo bottone rosso |
| Rilancia o Puntata | `579, 1023` | `x 474-683, y 958-1087` | Terzo bottone rosso |

Quando cambia il testo, la posizione resta la stessa:

```text
Fold = primo pulsante
Check o Vedi = secondo pulsante
Puntata o Rilancia = terzo pulsante
```

## Layout a due pulsanti

Quando compaiono solo due bottoni rossi, Fold resta a sinistra e Vedi si sposta piu a destra.

| Controllo | Centro client | Rettangolo client approssimativo | Note |
|---|---:|---:|---|
| Fold | `141, 1023` | `x 37-245, y 958-1087` | Primo bottone rosso |
| Vedi | `516, 1023` | `x 412-621, y 958-1087` | Bottone rosso a destra nel layout a due bottoni |

## Campo importo e controlli puntata

Questi controlli appaiono quando e disponibile una puntata o un rilancio con importo modificabile.

| Controllo | Centro client | Rettangolo client approssimativo | Note |
|---|---:|---:|---|
| Campo importo | `783, 1042` | `x 709-857, y 1005-1078` | Campo con valore tipo `0.29`, `0.70` |
| Meno | `911, 1042` | `x 878-944, y 1005-1078` | Bottone `-` |
| Slider knob | `978, 1042` | `x 944-1012, y 1005-1078` | Manopola slider |
| Piu | `1627, 1042` | `x 1593-1660, y 1005-1078` | Bottone `+` |

## Scorciatoie puntata

Le scorciatoie sopra lo slider cambiano testo a seconda della situazione. In alcuni screenshot il secondo pulsante era `1/2`; nel tavolo live e apparso come `3BB`.

| Controllo | Centro client | Rettangolo client approssimativo | Note |
|---|---:|---:|---|
| Min | `1030, 963` | `x 952-1109, y 930-995` | Scorciatoia minima |
| 1/2 o 3BB | `1194, 963` | `x 1115-1272, y 930-995` | Il testo puo cambiare |
| Pot | `1357, 963` | `x 1279-1434, y 930-995` | Punta pot |
| Max | `1519, 963` | `x 1441-1597, y 930-995` | Puntata massima |

## Checkbox pre turno

Questi controlli compaiono in basso a sinistra quando non e il tuo turno o quando puoi preimpostare un azione.

| Controllo | Centro client | Rettangolo client approssimativo | Note |
|---|---:|---:|---|
| Checkbox Fold | `65, 1023` | `x 45-85, y 1000-1045` | Casella pre turno Fold |
| Checkbox Check o Vedi | `194, 1023` | `x 174-214, y 1000-1045` | Casella pre turno Check o Vedi |

## Log mani e chat

Il log mani compare nella parte bassa destra. Puo coprire una parte del tavolo e alcuni punti vuoti.

| Area | Coordinate client approssimative | Note |
|---|---:|---|
| Riquadro log mani | `x 950-1660, y 820-1080` | Area grande del log in basso a destra |
| Icona log mani | `1630, 900` | Icona per aprire o chiudere il log |

## Punti vuoti di riferimento

Questi punti sono aree del tavolo che, nella configurazione osservata, sembrano lontane da bottoni, carte, player box e log. Usali solo come riferimenti visivi: il layout puo cambiare durante la mano.

| Punto | Centro client | Note |
|---|---:|---|
| Punto vuoto 1 | `760, 520` | Area centrale alta del tavolo |
| Punto vuoto 2 | `1050, 520` | Area centrale alta destra |
| Punto vuoto 3 | `1320, 570` | Area destra del tavolo |
| Punto vuoto 4 | `520, 650` | Area sinistra interna del tavolo |
| Punto vuoto 5 | `1450, 720` | Area destra interna del tavolo |

## Aree da evitare

Queste zone contengono controlli o elementi attivi.

| Area | Coordinate client approssimative | Motivo |
|---|---:|---|
| Bottoni principali | `x 0-700, y 950-1090` | Fold, Vedi, Check, Puntata, Rilancia |
| Importo e slider | `x 760-1660, y 950-1090` | Campo importo, meno, piu, slider |
| Log mani | `x 900-1660, y 820-1080` | Riquadro log mani |
| Checkbox pre turno | `x 20-220, y 950-1090` | Fold, Check, Vedi pre turno |

## Immagini annotate

Nella copia locale di questa cartella sono conservate tre immagini annotate, escluse da Git perché contengono schermate del tavolo:

```text
poker_button_rectangles_raise_layout.png
poker_button_rectangles_three_button_layout.png
poker_button_rectangles_two_button_layout.png
```

Quelle immagini usano i pixel dello screenshot PNG, quindi i valori sono circa il doppio delle coordinate browser client.

## Nota pratica

Queste coordinate sono riferimenti per la configurazione osservata il 2 ottobre 2026 con Brave aperto sul tavolo PokerStars. Prima di usarle in una sessione diversa, verifica almeno un punto noto con il riquadro verde, per esempio il centro del bottone Vedi o Check.
