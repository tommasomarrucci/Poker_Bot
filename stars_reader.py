"""Read-only PokerStars browser-table prototype calibrated to the supplied theme."""
import argparse
import csv
import io
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage
from hand_results import parse_results, ResultObserver
from hand_tracker import HandTracker
from poker_store import PokerStore
from dry_run import command, control_regions, preview

ROOT = Path(__file__).resolve().parent
SIZE = (1710, 1107)
# Clockwise from the bottom: hero, lower left, upper left, top, upper right, lower right.
PANELS = [(790, 819, 1035, 933), (275, 704, 483, 797), (275, 461, 483, 557),
          (704, 305, 912, 401), (1234, 461, 1440, 557), (1234, 704, 1440, 797)]
BETS = [(880, 773, 983, 810), (541, 727, 642, 770), (541, 486, 642, 529),
        (802, 410, 883, 452), (1092, 485, 1172, 529), (1092, 726, 1172, 770)]
BACKS = [(0, 0, 1, 1), (280, 648, 380, 699), (280, 407, 380, 458),
         (808, 248, 908, 299), (1338, 407, 1438, 458), (1338, 648, 1438, 699)]
DEALERS = [(1075, 853), (449, 819), (320, 585), (449, 397), (1284, 397), (1389, 626)]
ACTION = re.compile(r'^(check|fold|vedi|punta|puntata|rilancia|all.?in|in sit.?out|vinci|vince|vinto)\b', re.I)


@dataclass(frozen=True)
class TableGeometry:
    source_size: tuple
    scaled_size: tuple
    crop: tuple

    def apply(self, im):
        if im.size != self.source_size:
            raise ValueError('Locked capture size changed; restart to recalibrate')
        return im.convert('RGB').resize(self.scaled_size).crop(self.crop).resize(SIZE)


def green_mask(a):
    r, g, b = a.astype(np.int16).transpose(2, 0, 1)
    return (g > 40) & (g > r * 1.4) & (g > b * 1.25)


def locate_table(im):
    """Locate once; the live reader retains this geometry for the entire session."""
    source_size = im.size
    im = im.convert('RGB')
    scale = min(1, 1710 / im.width)
    im = im.resize((round(im.width * scale), round(im.height * scale)))
    mask = green_mask(np.asarray(im))
    lab, n = ndimage.label(mask)
    if not n:
        raise ValueError('Table not found')
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    k = int(sizes.argmax())
    y, x = ndimage.find_objects(lab)[k - 1]
    w, h = x.stop - x.start, y.stop - y.start
    if w < 450 or not 1.96 < w / h < 2.08 or sizes[k] / (w * h) < .53:
        raise ValueError('Table obscured, too small, or unsupported layout')
    sx, sy = w / 1138, h / 563
    left, top = x.start - 285 * sx, y.start - 319 * sy
    return TableGeometry(source_size, im.size,
                         (round(left), round(top), round(left + 1710 * sx),
                          round(top + 1107 * sy)))


def canonical(im):
    return locate_table(im).apply(im)


def validate_layout(im):
    # Stable felt patches away from cards, betting amounts, and player panels.
    anchors = [(520, 370, 680, 420), (950, 360, 1100, 420),
               (500, 780, 590, 825), (1150, 650, 1200, 700)]
    if sum(green_mask(np.asarray(im.crop(b))).mean() > .65 for b in anchors) < 3:
        raise ValueError('Locked table layout missing, moved, or obscured')
    a = np.asarray(im.crop((570, 530, 1140, 690)))
    visible = green_mask(a) | (a.min(2) > 180)
    if visible.mean() < .65:
        raise ValueError('Community-card region obscured or unsupported')


def cards(im, box, hole=False):
    a = np.asarray(im.crop(box))
    mask = (a.min(2) > 180) & (a.max(2).astype(int) - a.min(2) < 65)
    lab, _ = ndimage.label(mask)
    out = []
    for sl in ndimage.find_objects(lab):
        y, x = sl
        w, h = x.stop - x.start, y.stop - y.start
        if not (65 < w < 210 and 105 < h < 190):
            continue
        X, Y = box[0] + x.start, box[1] + y.start
        if hole and w / h > .8:
            cw = round((h - 10) * .7)
            out.extend([(X, Y, X + cw, Y + h - 10),
                        (X + w - cw, Y + 10, X + w, Y + h)])
        elif .55 < w / h < .8:
            out.append((X, Y, X + w, Y + h))
    return sorted(out)


def glyph(im, box, clean=False):
    a = np.asarray(im.crop(box)).min(2)
    mask = a < 150
    if clean:
        labels, count = ndimage.label(mask)
        if count:
            sizes = np.bincount(labels.ravel()); sizes[0] = 0
            # Remove detached rank descenders (notably Q) from the suit crop.
            mask = (labels > 0) & (sizes[labels] >= sizes.max() * .1)
    ys, xs = np.nonzero(mask)
    if len(xs) < 8:
        return None
    # Tight crop and normalize with aspect ratio preserved.
    im = Image.fromarray((mask * 255).astype('uint8')).crop(
        (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    im.thumbnail((32, 40), Image.Resampling.LANCZOS)
    out = Image.new('L', (36, 44))
    out.paste(im, ((36 - im.width) // 2, (44 - im.height) // 2))
    return np.asarray(out).astype(float) / 255


def card_glyphs(im, box, clean_suit=False):
    im = im.crop(box).resize((100, 144))
    return glyph(im, (2, 2, 31, 42)), glyph(im, (2, 42, 32, 77), clean=clean_suit)


class CardReader:
    def __init__(self):
        self.bank = {'rank': [], 'suit': []}
        for kind in self.bank:
            for p in sorted((ROOT / 'assets' / kind).glob('*.png')):
                a = np.asarray(Image.open(p).convert('L')).astype(float) / 255
                self.bank[kind].append((p.stem.split('_')[0], a))
        if any(not v for v in self.bank.values()):
            raise ValueError('Missing card templates in assets/')
        self.soft_bank = {kind: [(key, ndimage.gaussian_filter(a, .7)) for key, a in bank]
                          for kind, bank in self.bank.items()}

    def match(self, a, kind):
        if a is None:
            return '?', 0.0
        scores = {}
        for key, b in self.bank[kind]:
            score = float(np.sum(a*b) / max(1e-9, np.linalg.norm(a)*np.linalg.norm(b)))
            scores[key] = max(score, scores.get(key, 0))
        best = sorted(scores, key=scores.get, reverse=True)
        score = scores[best[0]]
        margin = score - scores[best[1]] if len(best) > 1 else 0
        if kind == 'rank' and .86 <= score < .91 and margin >= .08:
            # Resizing changes antialiasing. Require the same, unambiguous winner
            # with a stricter score after modest smoothing, never guess a new label.
            soft = ndimage.gaussian_filter(a, .7)
            smooth_scores = {}
            for key, b in self.soft_bank[kind]:
                value = float(np.sum(soft*b) / max(1e-9, np.linalg.norm(soft)*np.linalg.norm(b)))
                smooth_scores[key] = max(value, smooth_scores.get(key, 0))
            order = sorted(smooth_scores, key=smooth_scores.get, reverse=True)
            if (order[0] == best[0] and smooth_scores[order[0]] >= .95
                    and smooth_scores[order[0]] - smooth_scores[order[1]] >= .08):
                return best[0], round(smooth_scores[order[0]], 3)
        return (best[0] if score >= .91 and margin >= .035 else '?'), round(score, 3)

    def read(self, im, box):
        r, s = card_glyphs(im, box)
        rank, rs = self.match(r, 'rank'); suit, ss = self.match(s, 'suit')
        if suit == '?':
            _, cleaned = card_glyphs(im, box, clean_suit=True)
            retry, score = self.match(cleaned, 'suit')
            if retry != '?':
                suit, ss = retry, score
        return {'card': rank + suit, 'score': min(rs, ss)}


@lru_cache(maxsize=16)
def tesseract_tsv(png, psm):
    """Reuse OCR only for byte-identical crops; errors are never cached."""
    p = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', str(psm), 'tsv'],
                       input=png, capture_output=True, check=True, timeout=30)
    return p.stdout.decode()


def ocr_regions(im, regions):
    """One local Tesseract call for independent, vertically stacked text crops."""
    canvas = Image.new('RGB', (750, len(regions) * 105), 'white')
    for i, box in enumerate(regions):
        patch = im.crop(box).convert('RGB')
        a = np.asarray(patch)
        # Retain bright text, invert against white; reduce dark panel/felt texture.
        bright = a.max(2) > 130
        patch = Image.fromarray(np.where(bright, 0, 255).astype('uint8'))
        patch = patch.resize((patch.width * 2, patch.height * 2), Image.Resampling.LANCZOS)
        patch.thumbnail((700, 78))
        canvas.paste(patch, (20, i * 105 + 12))
    data = io.BytesIO(); canvas.save(data, format='PNG')
    rows = [[] for _ in regions]
    for word in csv.DictReader(io.StringIO(tesseract_tsv(data.getvalue(), 6)), delimiter='\t'):
        if word['level'] != '5' or not word['text'].strip():
            continue
        y = int(word['top']) + int(word['height']) / 2
        i = int(y // 105)
        if 0 <= i < len(rows):
            rows[i].append((int(word['left']), word['text'], float(word['conf'])))
    return [(' '.join(x[1] for x in sorted(row)),
             min((x[2] for x in row), default=0)) for row in rows]


def amount(text, confidence):
    if confidence < 35:
        return None
    # Require a currency marker; never turn an empty/failed read into zero.
    m = re.search(r'[€£E]\s*(\d+(?:[.,]\d{1,2})?)(?![\d.,])', text)
    if not m:
        return None
    try:
        return int(Decimal(m[1].replace(',', '.')) * 100)
    except InvalidOperation:
        return None


def retry_amount(im, box, original):
    """Retry uncertain amounts alone, preserving antialiased text edges."""
    patch = ImageOps.invert(ImageOps.autocontrast(im.crop(box).convert('L')))
    patch = patch.resize((patch.width * 3, patch.height * 3), Image.Resampling.LANCZOS)
    patch = ImageOps.expand(patch, border=20, fill='white')
    data = io.BytesIO(); patch.save(data, format='PNG')
    words = [w for w in csv.DictReader(io.StringIO(tesseract_tsv(data.getvalue(), 7)), delimiter='\t')
             if w['level'] == '5' and w['text'].strip()]
    text = ' '.join(w['text'] for w in words)
    # Labels such as "Contributo" must not lower the confidence of a clear amount.
    confidence = min((float(w['conf']) for w in words if re.search(r'[\d€£]', w['text'])), default=0)
    value = amount(text, confidence) if confidence >= 60 else None
    initial = amount(original, 100)
    if initial is not None and value != initial:
        value = None  # Disagreement remains uncertain; never silently choose one value.
    return value, {'text': text, 'confidence': round(confidence, 2), 'accepted': value is not None}


def read_chat_results(im):
    patch = im.crop((930, 955, 1680, 1100)).convert('L')
    patch = ImageOps.invert(ImageOps.autocontrast(patch))
    patch = patch.resize((patch.width * 2, patch.height * 2), Image.Resampling.LANCZOS)
    data = io.BytesIO(); patch.save(data, format='PNG')
    words = [(w['text'], float(w['conf']))
             for w in csv.DictReader(io.StringIO(tesseract_tsv(data.getvalue(), 6)), delimiter='\t')
             if w['level'] == '5' and w['text'].strip()]
    return parse_results(words)


def red_fraction(im, box):
    a = np.asarray(im.crop(box)).astype(int)
    r, g, b = a.transpose(2, 0, 1)
    return float(((r > 130) & (r > 1.6*g) & (r > 1.6*b)).mean())


class TableReader:
    def __init__(self, lock_layout=False, allow_resize=False):
        self.cards = CardReader()
        self.lock_layout = lock_layout
        self.geometry = None
        self.allow_resize = allow_resize

    def read(self, im):
        geometry = self.geometry
        if geometry is None or (self.allow_resize and geometry.source_size != im.size):
            geometry = locate_table(im)
        im = geometry.apply(im)
        validate_layout(im)
        if self.lock_layout:
            self.geometry = geometry
        regions = [(770, 474, 947, 503), (770, 502, 947, 531)]
        for x0,y0,x1,y1 in PANELS:
            mid = (y0+y1)//2
            regions.extend([(x0,y0,x1,mid), (x0,mid,x1,y1)])
        regions.extend(BETS)
        regions.extend([(1410, 171, 1670, 216), (40, 266, 700, 305)])
        text = ocr_regions(im, regions)
        amounts = {}
        retries = {}
        for i in [0, 1, 3, 5, 7, 9, 11, 13, *range(14, 20)]:
            amounts[i] = amount(*text[i])
            if amounts[i] is None and re.search(r'[\d€£]', text[i][0]):
                amounts[i], retries[str(i)] = retry_amount(im, regions[i], text[i][0])
        board_boxes = cards(im, (570, 530, 1140, 690))
        hero_boxes = cards(im, (610, 750, 805, 950), True)
        board = [self.cards.read(im, b) for b in board_boxes]
        hero = [self.cards.read(im, b) for b in hero_boxes]
        seats = []
        active = []
        for i, box in enumerate(PANELS):
            name, nc = text[2+i*2]; stack, sc = text[3+i*2]
            action = name if ACTION.match(name) else None
            # Bright straight top edge belongs to the active panel; avatars/text excluded.
            x0,y0,x1,y1 = box
            strip = np.asarray(im.crop((x0, y0-6, x1, y0+1)))
            white = strip.min(2) > 210
            highlighted = bool((white.mean(1) > .7).any())
            if highlighted: active.append(i+1)
            empty = 'libero' in (name+' '+stack).lower()
            seats.append({'seat':i+1, 'name':name if nc >= 45 and not action and not empty else None,
                          'label_raw':name, 'status_raw':stack, 'action':action,
                          'stack_cents':amounts[3+i*2], 'bet_cents':amounts[14+i],
                          'bet_raw':text[14+i][0],
                          'cards_visible':len(hero)==2 if i==0 else red_fraction(im,BACKS[i])>.15,
                          'empty':empty, 'highlighted':highlighted})
        # Dealer marker: small circular white/red chip at one of the calibrated positions.
        dealer = []
        for i,(x,y) in enumerate(DEALERS):
            patch = im.crop((x-13,y-13,x+13,y+13))
            if red_fraction(patch,(0,0,26,26)) > .08 and (np.asarray(patch).min(2)>180).mean()>.18:
                dealer.append(i+1)
        hero_status = seats[0]['status_raw'].lower()
        hero_inactive = any(s in hero_status for s in ('all-in', 'all in', 'sit-out', 'sit out'))
        # The red "Torna a giocare" sit-out button is not an action control.
        hero_turn = len(hero) == 2 and not hero_inactive and red_fraction(im,(45,975,225,1070))>.45
        if hero_turn: active = [1]
        issues = []
        if len(board) not in (0,3,4,5): issues.append('board_in_transition')
        if len(hero) not in (0,2): issues.append('hole_cards_in_transition')
        all_cards = [x['card'] for x in board+hero]
        if any('?' in c for c in all_cards): issues.append('unknown_card')
        known = [c for c in all_cards if '?' not in c]
        if len(set(known)) != len(known): issues.append('duplicate_cards')
        pot = amounts[0]
        if pot is None: issues.append('pot_unreadable')
        for seat in seats:
            status = seat['status_raw'].lower()
            if seat['stack_cents'] is None and seat['name'] and not any(
                    word in status for word in ('all-in','sit-out','sit out')):
                issues.append(f"stack_unreadable_seat_{seat['seat']}")
            if seat['bet_cents'] is None and seat['bet_raw']:
                issues.append(f"bet_unreadable_seat_{seat['seat']}")
        # No board alone cannot distinguish preflop, sit-out, loading, or hand end.
        street = {3:'flop',4:'turn',5:'river'}.get(len(board), 'no_board' if not board else 'unknown')
        state = {'table_raw':text[20][0], 'participation_id_raw':text[21][0], 'street':street,
                 'board':[x['card'] for x in board], 'hero':{'seat':1,'cards':[x['card'] for x in hero]},
                 'card_scores':[x['score'] for x in board+hero], 'pot_cents':pot,
                 'contribution_cents':amounts[1], 'seats':seats, 'ocr_retries':retries,
                 'dealer_seat':dealer[0] if len(dealer)==1 else None,
                 'to_act_seat':active[0] if len(active)==1 else None,
                 'hero_controls_visible':hero_turn, 'issues':issues,
                 'scope':'visible_snapshot_not_complete_action_history'}
        state['chat_raw'], state['chat_result_candidates'] = read_chat_results(im)
        return state, im, board_boxes+hero_boxes


def frames(args):
    if args.image:
        yield 0.0, Image.open(args.image).convert('RGB')
    elif args.frames:
        for i,p in enumerate(sorted(Path(args.frames).glob('*.png'))):
            yield float(i), Image.open(p).convert('RGB')
    elif args.video:
        # ffmpeg normalizes resolution only; detection still locates the table.
        cmd = ['ffmpeg','-v','error','-i',args.video,'-vf',
               f'fps={args.fps},scale=1710:-1','-f','image2pipe','-vcodec','png','-']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        try:
            for i, im in enumerate(png_frames(p.stdout)):
                yield i/args.fps, im
            if p.wait(): raise RuntimeError('ffmpeg could not decode the recording')
        finally:
            if p.poll() is None: p.terminate()
            p.stdout.close(); p.wait()
    else:
        # Native macOS capture: no third-party screen-capture package required.
        if sys.platform != 'darwin':
            raise ValueError('Live capture is currently macOS-only; use --image or --video here')
        with tempfile.TemporaryDirectory(prefix='stars-reader-') as d:
            path = str(Path(d)/'screen.png')
            capture = None
            if not args.screen:
                from mac_capture import LockedWindowCapture
                capture = LockedWindowCapture(path, lambda im: validate_layout(canonical(im)),
                                              args.window_id, args.raw_dir, args.capture_backend, True, args.fps)
                args.capture_info = capture.metadata()
                print(f"Locked PokerStars window {capture.window['id']}: {capture.window['title']}",
                      file=sys.stderr)
            try:
                while True:
                    start = time.monotonic()
                    try:
                        if capture:
                            im = capture.read()
                        else:
                            Path(path).unlink(missing_ok=True)
                            subprocess.run(['screencapture','-x','-D',str(args.display),path],
                                           check=True, capture_output=True, timeout=15)
                            with Image.open(path) as image:
                                im = image.convert('RGB')
                    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
                        im = e
                    if capture:
                        args.capture_info = capture.metadata()
                    yield time.time(), im
                    time.sleep(max(0,1/args.fps-(time.monotonic()-start)))
            finally:
                if capture:
                    capture.close()


def png_frames(stream):
    """Read lossless ffmpeg PNG frames without adding JPEG recognition artifacts."""
    def exact(count):
        parts = bytearray()
        while len(parts) < count:
            data = stream.read(count - len(parts))
            if not data:
                raise ValueError('Truncated video frame')
            parts.extend(data)
        return bytes(parts)

    while True:
        first = stream.read(1)
        if not first:
            return
        data = bytearray(first + exact(7))
        if data != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Invalid video frame signature')
        while True:
            header = exact(8)
            length = int.from_bytes(header[:4], 'big')
            if length > 64 * 1024 * 1024 or len(data) + length > 128 * 1024 * 1024:
                raise ValueError('Video frame too large')
            data.extend(header)
            data.extend(exact(length + 4))
            if header[4:] == b'IEND':
                break
        with Image.open(io.BytesIO(data)) as im:
            yield im.convert('RGB')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group()
    src.add_argument('--image'); src.add_argument('--video'); src.add_argument('--frames')
    src.add_argument('--screen', action='store_true', help='Legacy full-display capture instead of locking a window')
    src.add_argument('--window-id', type=int, help='Lock a specific macOS window; otherwise find PokerStars automatically')
    ap.add_argument('--list-windows', action='store_true', help='List macOS window IDs and titles, then exit')
    ap.add_argument('--capture-backend', choices=['stream', 'legacy'], default='stream',
                    help='Continuous ScreenCaptureKit window stream (default) or legacy screencapture')
    ap.add_argument('--fps', type=float, default=5)
    ap.add_argument('--display', type=int, default=1)
    ap.add_argument('--log'); ap.add_argument('--debug-dir'); ap.add_argument('--limit',type=int,default=0)
    ap.add_argument('--db', help='SQLite observation database; defaults to LOG with .sqlite suffix')
    ap.add_argument('--raw-dir', help='Save source captures as PNG for recognition verification')
    ap.add_argument('--raw-every', type=int, default=1, help='With --raw-dir, save only every Nth capture')
    ap.add_argument('--quiet', action='store_true', help='Write logs without printing every snapshot')
    ap.add_argument('--dry-run-action', choices=['fold', 'check', 'call', 'raise'],
                    help='Preview a supplied command only; never clicks or types')
    ap.add_argument('--dry-run-amount', help='Requested total raise-to amount, e.g. 1,50; preview only')
    ap.add_argument('--detect-controls', action='store_true',
                    help='Report read-only action-control regions; never clicks or types')
    args = ap.parse_args()
    request = None
    try:
        if args.dry_run_amount is not None and args.dry_run_action is None:
            raise ValueError('--dry-run-amount requires --dry-run-action')
        if args.dry_run_action:
            request = command(args.dry_run_action, args.dry_run_amount)
    except ValueError as e:
        ap.error(str(e))
    if not math.isfinite(args.fps) or not 0 < args.fps <= 30 or args.display < 1 or args.limit < 0:
        ap.error('Use finite fps in (0, 30], positive display and nonnegative limit')
    if args.window_id is not None and args.window_id <= 0: ap.error('Use a positive window ID')
    if args.raw_every < 1: ap.error('Use a positive --raw-every')
    if args.list_windows:
        from mac_capture import list_windows
        try:
            print(json.dumps(list_windows(), ensure_ascii=False, indent=2))
        except RuntimeError as e:
            ap.exit(1, f'{e}\n')
        return
    if not shutil.which('tesseract'): ap.error('Install Tesseract first: brew install tesseract')
    if args.video and not shutil.which('ffmpeg'): ap.error('Video mode requires ffmpeg')
    live_window = not (args.image or args.video or args.frames or args.screen)
    if not (args.image or args.video or args.frames) and not args.log:
        sessions = ROOT/'sessions'
        sessions.mkdir(exist_ok=True)
        args.log = str(sessions / (time.strftime('%Y%m%d-%H%M%S') + f'-{time.time_ns() % 1000000:06d}.jsonl'))
    reader = TableReader(lock_layout=live_window, allow_resize=live_window)
    results = ResultObserver()
    tracker = HandTracker()
    # Preserve earlier sessions: choose a new path instead of truncating a log.
    try:
        log = open(args.log,'x') if args.log else None
    except FileExistsError:
        ap.error('Log already exists; choose a new --log filename')
    result_log = None
    event_log = None
    store = None
    if args.log:
        result_path = Path(args.log).with_suffix('.hands.jsonl')
        event_path = Path(args.log).with_suffix('.events.jsonl')
        db_path = Path(args.db) if args.db else Path(args.log).with_suffix('.sqlite')
        try:
            result_log = result_path.open('x')
            event_log = event_path.open('x')
            store = PokerStore(db_path, source='stars_reader', log_path=args.log)
        except OSError:
            log.close()
            if result_log:
                result_log.close()
            if event_log:
                event_log.close()
            ap.error('Cannot create hand-results log; choose a new --log filename')
        print(f'Snapshots: {Path(args.log).resolve()}\nHand results: {result_path.resolve()}'
              f'\nHand events: {event_path.resolve()}\nSQLite: {db_path.resolve()}', file=sys.stderr)
    elif args.db:
        store = PokerStore(args.db, source='stars_reader', log_path=args.log)
    if args.debug_dir: Path(args.debug_dir).mkdir(parents=True,exist_ok=True)
    if args.raw_dir: Path(args.raw_dir).mkdir(parents=True,exist_ok=True)
    source = frames(args)
    layout_revision = None
    try:
        for i,(t,im) in enumerate(source):
            try:
                if isinstance(im, Exception):
                    raise im
                if live_window and args.capture_info.get('layout_revision') != layout_revision:
                    reader.geometry = None
                    layout_revision = args.capture_info.get('layout_revision')
                if args.raw_dir and i % args.raw_every == 0:
                    im.save(Path(args.raw_dir)/f'{i:06d}.png')
                state,canon,boxes = reader.read(im)
                state['t'] = round(t,3)
                if args.detect_controls:
                    state['control_regions'] = control_regions(state)
                state['new_hand_results'] = results.update(state['chat_result_candidates'], state['t'])
                if args.debug_dir:
                    draw = ImageDraw.Draw(canon)
                    for box in boxes: draw.rectangle(box,outline='yellow',width=3)
                    if args.detect_controls:
                        for region in state['control_regions']:
                            draw.rectangle(region['box'], outline='cyan', width=3)
                            draw.text((region['box'][0], region['box'][1] - 18), region['role'],
                                      fill='cyan')
                    draw.text((45,945),json.dumps({'board':state['board'],'hero':state['hero']['cards'],
                              'pot_cents':state['pot_cents'],'issues':state['issues']}),fill='white')
                    canon.save(Path(args.debug_dir)/f'{i:06d}.jpg')
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as e:
                results.unreadable()
                state = {'t':round(t,3),'status':'unreadable','reason':str(e)}
            if live_window:
                state['capture'] = args.capture_info
            state['hand_tracker'] = tracker.update(state)
            if request is not None:
                state['command_preview'] = preview(request, state)
            if store:
                store.record_snapshot(i, state)
            line = json.dumps(state,ensure_ascii=False)
            if not args.quiet:
                print(line,flush=True)
            if log: log.write(line+'\n');log.flush()
            if result_log:
                for event in state.get('new_hand_results', []):
                    result_log.write(json.dumps(event, ensure_ascii=False)+'\n')
                result_log.flush()
            if event_log:
                for event in state.get('hand_tracker', {}).get('new_events', []):
                    event_log.write(json.dumps(event, ensure_ascii=False)+'\n')
                event_log.flush()
            if store:
                store.commit()
            if args.limit and i+1 >= args.limit: break
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as e:
        ap.exit(1, f'Reader stopped: {e}\n')
    finally:
        source.close()
        if log: log.close()
        if result_log: result_log.close()
        if event_log: event_log.close()
        if store: store.close()


if __name__ == '__main__':
    main()
