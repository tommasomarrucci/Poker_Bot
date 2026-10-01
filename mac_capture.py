"""Read-only macOS window discovery and capture; no browser automation."""
import ctypes
import io
import json
import os
import plistlib
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image


def stream_helper():
    root = Path(__file__).resolve().parent
    source = root/'native'/'WindowStream.swift'
    binary = root/'.build'/'window-stream'
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        binary.parent.mkdir(exist_ok=True)
        subprocess.run(['xcrun', 'swiftc', '-parse-as-library', '-O', '-module-cache-path',
                        str(binary.parent/'swift-cache'), '-o', str(binary), str(source)],
                       check=True, capture_output=True, timeout=120)
    return binary


class WindowStreamCapture:
    def __init__(self, window_id, fps=5):
        self.errors = tempfile.TemporaryFile()
        self.process = subprocess.Popen([str(stream_helper()), str(window_id), str(fps)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.errors, bufsize=0)
        self.info = {}

    def _read(self, count):
        data = bytearray()
        deadline = time.monotonic() + 10
        while len(data) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise RuntimeError('Window stream timed out; no current image available')
            chunk = os.read(self.process.stdout.fileno(), min(count - len(data), 65536))
            if not chunk:
                self.errors.seek(0)
                reason = self.errors.read().decode(errors='replace').strip()
                raise RuntimeError('Window stream stopped: ' + reason)
            data.extend(chunk)
        return bytes(data)

    def read(self):
        if self.process.poll() is not None:
            self.errors.seek(0)
            raise RuntimeError('Window stream stopped: ' + self.errors.read().decode(errors='replace').strip())
        self.process.stdin.write(b'capture\n')
        header = bytearray()
        while not header.endswith(b'\n'):
            if len(header) > 8192:
                raise RuntimeError('Invalid window stream response')
            header.extend(self._read(1))
        self.info = json.loads(header)
        size = self.info.get('bytes', 0)
        if not 0 <= size <= 128 * 1024 * 1024:
            raise RuntimeError('Invalid window stream image size')
        data = self._read(size)
        if 'error' in self.info:
            raise RuntimeError(self.info['error'])
        if self.info.get('format') == 'BGRA':
            width, height, stride = (self.info[k] for k in ('width', 'height', 'stride'))
            if not (0 < width <= 1710 and 0 < height <= 10000 and stride >= width * 4 and len(data) == stride * height):
                raise RuntimeError('Invalid window stream dimensions')
            return Image.frombytes('RGB', (width, height), data, 'raw', 'BGRX', stride)
        with Image.open(io.BytesIO(data)) as im:
            return im.convert('RGB')

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdout.close()
        self.errors.close()


def list_windows():
    """Read WindowServer metadata using CoreGraphics, without extra packages."""
    if sys.platform != 'darwin':
        raise RuntimeError('Window capture requires macOS')
    cg = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cf.CFPropertyListCreateData.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_long, ctypes.c_ulong, ctypes.c_void_p]
    cf.CFPropertyListCreateData.restype = ctypes.c_void_p
    cf.CFDataGetLength.argtypes = [ctypes.c_void_p]
    cf.CFDataGetLength.restype = ctypes.c_long
    cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    cf.CFDataGetBytePtr.restype = ctypes.c_void_p
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    # Include windows on other Spaces; omit desktop elements (option 16).
    windows = cg.CGWindowListCopyWindowInfo(16, 0)
    if not windows:
        raise RuntimeError('Cannot access macOS windows; check Screen Recording permission')
    data = None
    try:
        data = cf.CFPropertyListCreateData(None, windows, 100, 0, None)
        if not data:
            raise RuntimeError('Cannot decode macOS window metadata')
        rows = plistlib.loads(ctypes.string_at(cf.CFDataGetBytePtr(data), cf.CFDataGetLength(data)))
    finally:
        if data:
            cf.CFRelease(data)
        cf.CFRelease(windows)
    return [{'id': w['kCGWindowNumber'], 'pid': w['kCGWindowOwnerPID'],
             'owner': w.get('kCGWindowOwnerName', ''), 'title': w.get('kCGWindowName', ''),
             'bounds': w['kCGWindowBounds'], 'onscreen': bool(w.get('kCGWindowIsOnscreen'))}
            for w in rows if w.get('kCGWindowLayer') == 0
            and w['kCGWindowBounds'].get('Width', 0) >= 300
            and w['kCGWindowBounds'].get('Height', 0) >= 200]


def poker_windows(windows, window_id=None):
    if window_id is not None:
        matches = [w for w in windows if w['id'] == window_id]
    else:
        matches = [w for w in windows if 'pokerstars' in (w['title'] + ' ' + w['owner']).lower()]
    if not matches:
        raise RuntimeError('PokerStars window not found. Keep the table tab selected and allow '
                           'Screen Recording for the app running Python. Use --list-windows to inspect.')
    return matches


def capture_window(window_id, path):
    """Capture precisely one window, excluding its shadow and other windows."""
    path = Path(path)
    # A failed capture must never replay the previous frame.
    path.unlink(missing_ok=True)
    subprocess.run(['/usr/sbin/screencapture', '-x', '-o', '-l', str(window_id), str(path)],
                   check=True, capture_output=True, timeout=15)
    with Image.open(path) as im:
        return im.convert('RGB')


def check_locked_window(locked, windows, allow_resize=False):
    current = next((w for w in windows if w['id'] == locked['id'] and w['pid'] == locked['pid']), None)
    if current is None:
        raise RuntimeError('Locked PokerStars window was closed; restart to select a new window')
    if current['title'] != locked['title']:
        raise RuntimeError('Locked window title changed; restore the PokerStars table tab or restart')
    if not allow_resize and any(current['bounds'][k] != locked['bounds'][k] for k in ('Width', 'Height')):
        raise RuntimeError('Locked window was resized; restore its size or restart to recalibrate')
    return current


class LockedWindowCapture:
    """Select one valid table once. Never switch automatically after selection."""

    def __init__(self, path, validator, window_id=None, probe_dir=None, backend='legacy', allow_resize=False, fps=5):
        candidates = poker_windows(list_windows(), window_id)
        valid = []
        errors = []
        streams = {}
        self.allow_resize = allow_resize
        self.backend = backend
        self.fps = fps
        self.layout_revision = 0
        for window in candidates:
            stream = None
            try:
                if backend == 'stream':
                    stream = WindowStreamCapture(window['id'], fps)
                    im = stream.read()
                else:
                    im = capture_window(window['id'], path)
                if probe_dir:
                    im.save(Path(probe_dir)/f"startup-{window['id']}.png")
                validator(im)
                valid.append(window)
                streams[window['id']] = stream
            except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as e:
                if stream:
                    stream.close()
                errors.append(f"window {window['id']}: {e}")
                continue
        if len(valid) != 1:
            for stream in streams.values():
                if stream:
                    stream.close()
            ids = ', '.join(str(w['id']) for w in valid)
            raise RuntimeError('No readable PokerStars table found (' + '; '.join(errors) + ')' if not valid else
                               f'Multiple PokerStars tables found ({ids}); choose --window-id')
        self.window = valid[0]
        self.path = path
        self.stream = streams[self.window['id']]

    def read(self):
        current = check_locked_window(self.window, list_windows(), self.allow_resize)
        resized = any(current['bounds'][k] != self.window['bounds'][k] for k in ('Width', 'Height'))
        if self.stream and (resized or self.stream.process.poll() is not None):
            self.stream.close()
            self.stream = WindowStreamCapture(self.window['id'], self.fps)
        if resized:
            self.layout_revision += 1
        self.window = current
        im = self.stream.read() if self.stream else capture_window(self.window['id'], self.path)
        # Check again in case a resize/tab switch happened during the capture.
        check_locked_window(self.window, list_windows())
        return im

    def close(self):
        if self.stream:
            self.stream.close()

    def metadata(self):
        return {'mode': 'window', 'window_id': self.window['id'],
                'owner_pid': self.window['pid'], 'owner': self.window['owner'],
                'title': self.window['title'], 'layout_locked': not self.allow_resize,
                'window_locked': True, 'backend': self.backend,
                'layout_revision': self.layout_revision, 'bounds': self.window['bounds'],
                'onscreen': self.window.get('onscreen'),
                'stream': self.stream.info if self.stream else None}
