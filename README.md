# PokerStars window reader

## Repository contents and private local data

This repository includes the reader, native capture sources, local UI laboratory,
card-glyph templates and test code. Session logs, diagnostic captures, full-table
regression screenshots (`tests/fixtures/`), the replica background
(`lab/table-reference.png`) and live observation reports are intentionally not
published. They remain on the development machine.

On a fresh clone, screenshot-based `ReaderTest` tests are skipped until the private
fixtures are supplied locally; other tests remain available. The screenshot
replica needs your own local `lab/table-reference.png` (1976 × 1279) to reproduce
its background. Its overlay controls still exist without that file. The separate
`lab/index.html` demonstration does not require the screenshot.

A local, read-only macOS reader calibrated to the Italian PokerStars browser theme in your recording. It takes screenshots and emits JSON. It never clicks, places bets, recommends actions, or sends screenshots to a service.

## Local automation lab (separate from the reader)

Open `http://127.0.0.1:8765/replica.html` for the screenshot-based local button
fixture. The supplied reference image is kept locally and git-ignored because it
contains visible player details; it is not fetched from PokerStars. Three DOM
buttons and a numeric input overlay the reference. This is one decision only,
not a full poker game. Reset after each action. The test button demonstrates
setting `input.value`, dispatching an `input` event, verifying it, invoking the
local raise button's `.click()`, and checking the simulated outcome. No code
controls other apps. Test the model with `node --test lab/replica.test.mjs`.

The local test executor lives in `lab/replica-executor.mjs`, with its DOM adapter
in `replica-ui.mjs`. It rereads both the numeric field and the raise label,
checks the scene version before clicking, then verifies the resulting local
event. Missing confirmation stops the sequence without retry. The page shows
the verification trace. This uses our own DOM IDs/model version, not a native
accessibility driver or discovered PokerStars selectors. Run its fault tests
with `node --test lab/replica-executor.test.mjs`.

The `lab/` directory is an isolated, deterministic six-seat UI fixture. It has no
PokerStars connection and is not a complete poker rules engine or strategy.
It tests observe → scripted decision → DOM button click → state confirmation.

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory lab
# Open http://127.0.0.1:8765
node --test lab/engine.test.mjs
```

Use “Calcola e clicca una volta” for one action, or “Avvia automatico” for the
complete scripted sequence. “Stop” cancels automation; hiding the browser tab
also stops it. The FPS selector controls local decision polling, not screen OCR.
New hands stop automation before resetting the state. Stale decisions and missing
buttons are rejected. Button clicks are DOM `.click()` calls inside this local
page, not operating-system mouse input or clicks on another app.

Logs include hand ID, hero cards, street, board, seat, action and monotonic-clock
turn duration. This duration includes scheduling and automation delay: it does
not measure human thinking time. Export JSONL before closing the page; nothing
is saved automatically. At most 1,000 events are retained in memory (the last
100 shown), with no screenshot storage. The existing reader remains read-only.

## Reader installation

Install Homebrew first if it is not already installed, then run these commands from this folder:

```bash
brew install python@3.12 tesseract ffmpeg
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

FFmpeg is needed only for video input. Tesseract is required for all modes.

## Read one locked PokerStars window

In macOS System Settings → Privacy & Security, allow screen recording for the app running Python (usually Terminal), then restart that app if requested.

Select the PokerStars table tab in your browser, using the same green theme and preferred bottom seat. Default live capture uses ScreenCaptureKit (macOS 14+); Xcode Command Line Tools are required to compile the bundled Swift helper on first run (`xcode-select --install` if missing). Run:

```bash
python stars_reader.py --fps 5 --quiet
```

The reader finds windows whose title or app name contains `PokerStars`, validates the table, and locks to exactly one window ID and owner process. A continuous ScreenCaptureKit stream captures that window directly, without clicking or activating it. Other windows are not included. The latest frame replaces the previous frame; there is no accumulating frame queue in Python. Frames are transferred as uncompressed pixels at a maximum width of 1710, avoiding repeated PNG compression. The stream requests the configured fps; OCR can process fewer frames.

Stop with Ctrl+C. Use a new log filename for each session: existing logs are never overwritten. If the window closes or changes title/tab, the reader emits an unreadable record and does not switch to another window. Moving the window is supported. Resizing keeps the window ID, restarts the stream at the new dimensions, and recalibrates the table; transient frames or unsupported/small layouts can be rejected. Background capture succeeded locally, including frames marked offscreen by macOS. Minimized/suspended windows and all combinations of macOS Spaces are not guaranteed; missing fresh stream updates produce an error rather than silently replaying stale images.

If selection is ambiguous, inspect window IDs and choose one explicitly:

```bash
python stars_reader.py --list-windows
python stars_reader.py --window-id 12345 --quiet
```

Window IDs are local to the currently open windows; do not reuse an old ID after closing the browser. An explicitly selected window must still contain a readable table.

The program prints one JSON snapshot per processed capture. The default target is 5 fps (one capture every 0.2 seconds); allowed values are greater than zero and at most 30. Actual recognition speed depends on OCR and capture time. Use `--quiet` to suppress snapshot printing while retaining logs. Screen Recording permission is still required. `capture` metadata includes the window ID, dimensions, layout revision, visibility, backend, and source freshness timestamps. Temporary capture/OCR errors produce unreadable records; the reader retries the same window.

Live runs without `--log` automatically create timestamped logs in `sessions/`. With `--log example.jsonl`, snapshots go to that file and confirmed chat payout observations go to `example.hands.jsonl`. These are **not complete poker hand histories**: the results file contains explicit hand IDs, winners and payouts from the visible dealer chat, not inferred actions, net profit, or a guaranteed association with the current cards. An empty results file means no payout message met the recognition/confirmation requirements.

The older window backend is available with `--capture-backend legacy`; it is less reliable in the background. Whole-display capture remains available with `--screen --display 2`; it does not lock the window or layout and requires the table to remain visible.

## Test before live use

### Read-only command preview on PokerStars

```bash
python stars_reader.py --limit 3 --dry-run-action raise --dry-run-amount 1,50
```

This annotates observations with a `command_preview`; it never moves the mouse,
types an amount, or sends an order. Amounts use exact integer cents and mean the
requested total raise-to, not an increment. Commas or dots are accepted as decimal
separators (no thousands separators). `fold`, `check` and `call` accept no amount.
The current reader does not identify individual action buttons, call price,
raise limits, or field contents, so previews explicitly remain `not_verified`,
with no target coordinates. A visible hero control area is not enough to certify
a legal action. No screenshots are saved unless explicitly requested.

```bash
python -m unittest discover -s tests -v
python stars_reader.py --image tests/fixtures/218.png --debug-dir diagnostics/debug
python stars_reader.py --video '/path/to/recording.mov' --fps 1 --log replay.jsonl
python stars_reader.py --limit 30 --log live-check.jsonl --raw-dir diagnostics/live-check/raw --debug-dir diagnostics/live-check/debug
```

`--debug-dir debug` saves normalized screenshots with detected cards outlined. Avoid leaving it enabled indefinitely: it saves every processed frame.

`--raw-dir` saves input PNGs, including captured frames that recognition rejects, for comparison with the JSON. `--raw-every 10` saves only every tenth processed frame to reduce disk use. A startup probe is also saved for diagnostics. Raw and debug filenames use the same frame index. Use fresh output directories for each run; images in a reused directory can be overwritten. Raw images may contain visible account/player information. Both image options are intended for short diagnostic runs; normal live runs need only JSON logs.

`--frames folder` reads the folder's PNGs alphabetically. Its `t` values are frame indices. Live `t` values are Unix timestamps; video values are nominal sample interval times, not exact source presentation timestamps. `--limit 10` stops after ten samples.

## Output

- `board` and `hero.cards`: rank/suit codes, e.g. `Td`, `Ac`; `T` means ten.
- `card_scores`: template similarities, **not calibrated probabilities**. Low or ambiguous matches contain `?`.
- `pot_cents`, `contribution_cents`, `stack_cents`, `bet_cents`: integer euro cents, avoiding floating-point currency errors.
- `null`: unavailable or uncertain, **not zero**. A blank bet region is also `null` because this prototype does not distinguish absence from a missed read.
- `seats`: clockwise from bottom, numbered 1–6. Seat 1 is the bottom player; this assumes you use the same preferred seat as the recording.
- `label_raw`, `status_raw`, `bet_raw`: local OCR readings for inspection. Names can disappear when an action label replaces them.
- `dealer_seat`, `to_act_seat`: calibrated visual heuristics; `null` when no unique marker is found. These are not comprehensively validated.
- `cards_visible`: detected hole cards at the bottom or red backs elsewhere. It is **not** a reliable in-hand flag at showdown.
- `street`: flop/turn/river based on visible board size; `no_board` intentionally does not assert preflop.
- `participation_id_raw`: displayed participation identifier, not a unique hand identifier.
- `issues`: detected recognition problems; an empty list does not certify the entire snapshot.

## Project layout and storage

| Path | Purpose |
| --- | --- |
| `stars_reader.py` | Recognition pipeline and CLI |
| `mac_capture.py` | macOS window capture |
| `hand_results.py` | Dealer-chat payout observations |
| `native/` | Swift capture source |
| `assets/` | Small card recognition templates; required at runtime |
| `tests/` | Regression tests and selected fixture images |
| `sessions/` | Automatically saved live JSON logs and hand-result observations |
| `sessions/archive/2026-09-30/` | Preserved earlier sessions, with SHA-256 manifest |
| `diagnostics/` | Optional, temporary screenshot output; not needed for normal use |
| `.build/` | Compiled helpers and regenerable compiler cache |
| `.venv/` | Installed Python dependencies |

Normal live use saves JSON only. PNG/JPEG files are written only when image diagnostics are explicitly enabled. The small images in `assets/` and `tests/fixtures/` are intentional: templates and regression examples, not an accumulating capture history.

Historical capture batches and compiler caches were deleted during cleanup. All 22 original JSON logs were preserved byte-for-byte in the dated archive; verify them there with `shasum -a 256 -c manifest.sha256`. The reader remains stopped after cleanup.

## Current limits

- Single-table, same-theme prototype. Automatic location uses the largest green felt region at startup; default live mode then locks the window and recalibrates geometry after resizing. Different themes, small windows, overlays, and cropping may fail. Locking does not guarantee perfect OCR or card recognition.
- Text OCR still sometimes returns null for visible bets/stacks/pots. It can also misread characters; inspect raw text and debug images.
- Stable felt patches and community-card visibility are checked on every frame. A blacked-out board is rejected by regression tests; arbitrary partial occlusion is still not guaranteed to be detected.
- Overlapping bottom-player cards are supported. Opponent face-up showdown cards are not decoded.
- It emits snapshots and explicit chat payout observations, not a reconstructed action history. Even at the default 5 fps it can miss rapid actions and transitional states. It does not preserve player identities under temporary action labels, infer side pots, or detect hand boundaries reliably.
- No assertion of complete five-minute recognition accuracy or production readiness is made.


## Validation

The regression suite has 26 test methods. See [validation history](docs/validation.md) for calibration details, measurements, and limitations. Passing these tests does not establish perfect live recognition.
