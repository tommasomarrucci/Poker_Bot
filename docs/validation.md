# Validation history

Historical observations below describe development checkpoints, not a claim that every field is accurate. The full diagnostic image batches have been deleted; selected regression fixtures remain under `tests/fixtures/`. Original logs are archived under `sessions/archive/2026-09-30/`.

## What was actually checked

The supplied recording is 309.87 seconds, 3420 × 2214 pixels. Fifteen frames were sampled at roughly 20-second intervals. Templates were built from selected frames and one earlier screenshot, covering all 13 ranks and four suits. Tests on those calibration frames are not independent accuracy evidence.

Three additional frames at 143, 218 and 258 seconds were manually annotated and held out from template creation. The checked outputs matched:

- 17 visible board and bottom-player cards;
- 3 pot amounts;
- 15 visible numeric stack amounts, with 3 nonnumeric all-in/sit-out fields left null.

These frames come from the same recording and some of the same hands as calibration. They do not establish accuracy on other themes, machines, or all game states. The bundled tests also check one moved/resized frame and rejection of a blank screen. Video decoding was smoke-tested separately.

## Window-lock verification (2026-09-30)

The expanded suite covers locked geometry, window identity/closure/tab changes/resizing, stale-capture rejection, existing-log preservation, board occlusion, and lossless video-pipe framing in addition to the original fixtures. The image and folder modes were exercised locally. A short H.264 video made from fixture 218 decoded the expected seven cards and pot after replacing the intermediate JPEG pipe with PNG; one stack remained unreadable, so this is not evidence of perfect OCR.

macOS window discovery and locked capture were exercised on the live Renzia IV table in Brave (window ID 21467 in that session). Two bounded runs saved 55 source captures. Manually inspected examples confirmed board/hero cards, pot, visible bets, and dealer position. These captures exposed uncertain amount OCR and a false hero-turn signal from the red "Torna a giocare" button. An isolated grayscale OCR retry now recovers some uncertain amounts, and the return-to-play button no longer counts as hero action controls. Two captured examples were added as regression fixtures; they are development examples, not independent held-out evidence.

Replaying all 55 captures with the updated reader accepted 52 and rejected 3 for layout/visibility checks; 40 produced no reported issues. Remaining warnings included a dealing transition/unknown card and unreadable bet/stack regions. Empty issue lists are not ground-truth accuracy measurements. All 15 test methods passed locally. A subsequent live startup attempt found the PokerStars window no longer available, so the final OCR changes were checked against saved live captures rather than a second fresh live session.

`ocr_retries` records region-indexed retry text, confidence, and whether the retry was accepted. Retry acceptance requires at least 60 OCR confidence and agreement with the original numeric value when the original text was parseable. This does not make OCR confidence a calibrated accuracy probability.

## Continuous capture and live calibration update

The default is now a bounded-memory ScreenCaptureKit stream at a 5 fps target. The Swift receiver retains one latest image and requests an OS queue depth of three. Python's OCR cache holds at most 16 byte-identical inputs. A local process-memory sample measured approximately 125 MiB for Python plus 31 MiB for the helper; this is a point-in-time measurement, not a guaranteed bound on total system/WindowServer memory.

Three runs at the 5 fps target processed 150, 160, and 300 frames without capture rejections, averaging 3.92, 4.11, and 4.12 processed frames/second respectively. In the first two runs, 15 and 6 readable frames were marked offscreen by macOS. The latter runs used a 1078 x 718 point window. This demonstrates background capture and recognition at that smaller window size in this session, not perfect OCR or universal support for minimized windows. Live resizing within a single run still requires broader verification; automatic geometry replacement is covered by a resize regression test.

Recognition corrections include removing detached Q descenders from uncertain suit crops, a conservative antialiasing retry for uncertain ranks (same winning label, raw score >= .86/raw margin >= .08, softened score >= .95/margin >= .08), and manually verified rank variants for 3, 4 and Q. The new fixtures are calibration/regression evidence, not independent accuracy evidence. The Q-clubs/6-hearts example was verified visually and by the user.

Visible dealer-chat results are parsed only when an explicit hand ID, winner and payout are read with sufficient OCR confidence. Two successive matching observations are required before emitting `new_hand_results`; repeated messages are deduplicated in a bounded 512-entry session cache. Separate payouts for the same hand are retained separately. `visible_at_start` identifies a message present at startup; results can refer to older hands and are never automatically assigned to the currently displayed cards. OCR can still miss or misread messages. The results file is not a complete hand history or profit/loss ledger.
