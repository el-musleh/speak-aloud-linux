#!/usr/bin/env python3
"""
TTS Tray Daemon — cross-desktop tray icon with media keys, notifications, and logging.

Uses pystray for the tray icon (works on Cinnamon, GNOME, KDE, XFCE).
Listens to media keys only while TTS is actively playing.
Sends desktop notifications on state changes.
Logs to ~/.local/share/speak-aloud/daemon.log with rotation.

Auto-started on login via ~/.config/autostart/tts-daemon.desktop.
Single-instance enforced via /tmp/tts-daemon.lock.
"""

import fcntl
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time

from PIL import Image, ImageDraw

# Optional media-key support
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

import pystray

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = '/tmp/tts-status'
LOCK_FILE   = '/tmp/tts-daemon.lock'
MPV_SOCKET  = '/tmp/speak-aloud-mpv.sock'
LOG_DIR     = os.path.expanduser('~/.local/share/speak-aloud')
LOG_FILE    = os.path.join(LOG_DIR, 'daemon.log')

_STATE_LABELS = {
    'IDLE':       '○  Ready',
    'GENERATING': '⟳  Generating…',
    'RETRYING':   '⟳  Retrying…',
    'PLAYING':    '♪  Playing',
    'PAUSED':     '⏸  Paused',
}

_NOTIFICATIONS = {
    'GENERATING': ('TTS: Generating audio…', 'emblem-synchronizing'),
    'PLAYING':    ('TTS: Now speaking', 'audio-volume-high'),
    'PAUSED':     ('TTS: Paused', 'media-playback-pause'),
    'IDLE':       ('TTS: Finished speaking', 'audio-speakers'),
    'RETRYING':   ('TTS: Retrying…', 'network-error'),
}


def _setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger('tts-daemon')
    logger.setLevel(logging.DEBUG)

    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_048_576, backupCount=1
    )
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def _icon_idle():
    """Solid blue circle — ready / idle state."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=(33, 150, 243, 255))      # bright blue
    return img


def _icon_generating():
    """Purple circle with white spinner arc — generating audio."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=(156, 39, 176, 255))      # purple
    # white spinner arc
    d.pieslice([14, 14, 50, 50], start=0, end=270, fill=(255, 255, 255, 255))
    return img


def _icon_playing():
    """Green circle with white play triangle — actively playing."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=(76, 175, 80, 255))        # green
    # white play triangle centered
    d.polygon([(24, 18), (24, 46), (44, 32)], fill=(255, 255, 255, 255))
    return img


def _icon_paused():
    """Orange circle with white pause bars — paused."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=(255, 87, 34, 255))        # orange
    # two white pause bars
    d.rectangle([22, 18, 30, 46], fill=(255, 255, 255, 255))
    d.rectangle([34, 18, 42, 46], fill=(255, 255, 255, 255))
    return img


def _notify(title, icon='audio-speakers'):
    # Notifications disabled — tray icon only
    pass


def _send_mpv(cmd):
    try:
        payload = '{"command":' + str(cmd).replace("'", '"') + '}\n'
        subprocess.run(
            ['socat', '-', MPV_SOCKET],
            input=payload.encode(), capture_output=True, timeout=1
        )
    except Exception:
        pass


class TTSDaemon:
    def __init__(self):
        self.log = _setup_logging()
        self._state = 'IDLE'
        self._last_notify = None
        self._listener = None
        self._lock_fd = None
        self._running = True

        self._icons = {
            'IDLE':       _icon_idle(),
            'GENERATING': _icon_generating(),
            'PLAYING':    _icon_playing(),
            'PAUSED':     _icon_paused(),
        }

        self._acquire_lock()
        self.log.info('Daemon started (PID %d)', os.getpid())

        self._build_icon()
        self._start_poll()

        if PYNPUT_AVAILABLE:
            self.log.debug('pynput available')
        else:
            self.log.warning('pynput not installed; media keys disabled')

    def _acquire_lock(self):
        try:
            fd = open(LOCK_FILE, 'w')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(str(os.getpid()))
            fd.flush()
            self._lock_fd = fd
        except (IOError, OSError):
            self.log.error('Already running — exiting')
            sys.exit(0)

    def _build_icon(self):
        menu = pystray.Menu(
            pystray.MenuItem('Show Settings', self._on_show),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Play / Pause', self._on_pause),
            pystray.MenuItem('Stop', self._on_stop),
            pystray.MenuItem('Seek -10s', self._on_seek_back),
            pystray.MenuItem('Seek +10s', self._on_seek_forward),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self._on_quit),
        )

        self._icon = pystray.Icon(
            'tts-daemon',
            icon=self._icons['IDLE'],
            title='Speak a Loud — ○ Ready',
            menu=menu
        )

    def _start_poll(self):
        def loop():
            while self._running:
                self._tick()
                time.sleep(0.5)
        threading.Thread(target=loop, daemon=True).start()

    def _tick(self):
        try:
            with open(STATUS_FILE) as f:
                state = f.read().strip()
        except (FileNotFoundError, OSError):
            state = 'IDLE'

        # Self-correction: if status is active but speak.sh is gone, force IDLE
        if state in ('PLAYING', 'GENERATING', 'PAUSED', 'RETRYING'):
            try:
                result = subprocess.run(
                    ['pgrep', '-f', 'speak.sh'],
                    capture_output=True, timeout=1
                )
                if result.returncode != 0:
                    state = 'IDLE'
                    try:
                        with open(STATUS_FILE, 'w') as f:
                            f.write('IDLE')
                    except OSError:
                        pass
                    self.log.info('Self-correct: speak.sh gone — forcing IDLE')
            except Exception:
                pass

        if state != self._state:
            self._state = state
            label = _STATE_LABELS.get(state, '○  Ready')
            self._icon.title = f'Speak a Loud — {label}'
            new_icon = self._icons.get(state, self._icons['IDLE'])
            self._icon.icon = new_icon
            # Aggressive refresh: hide → show forces indicator recreation
            if hasattr(self._icon, '_hide') and hasattr(self._icon, '_show'):
                self._icon._hide()
                self._icon._show()
            elif hasattr(self._icon, '_update_icon'):
                self._icon._update_icon()
            self.log.info('State: %s — icon updated', state)
            self._do_notify(state)
            self._sync_media_keys(state)

    def _do_notify(self, state):
        if state == self._last_notify:
            return
        self._last_notify = state
        info = _NOTIFICATIONS.get(state)
        if info:
            _notify(info[0], info[1])

    def _sync_media_keys(self, state):
        if not PYNPUT_AVAILABLE:
            return
        active = state in ('PLAYING', 'PAUSED')
        if active and self._listener is None:
            self._start_keys()
        elif not active and self._listener is not None:
            self._stop_keys()

    def _start_keys(self):
        try:
            self._listener = keyboard.Listener(on_press=self._on_key)
            self._listener.start()
            self.log.debug('Media keys active')
        except Exception as e:
            self.log.warning('Media keys failed: %s', e)
            self._listener = None

    def _stop_keys(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
            self.log.debug('Media keys released')

    def _on_key(self, key):
        try:
            name = getattr(key, 'name', None)
            if name in ('media_play_pause', 'play_pause'):
                self._on_pause()
            elif name == 'media_stop':
                self._on_stop()
            elif name in ('media_previous', 'previous'):
                self._on_seek_back()
            elif name in ('media_next', 'next'):
                self._on_seek_forward()
        except Exception as e:
            self.log.error('Key handler error: %s', e)

    def _run(self, script):
        path = os.path.join(SCRIPT_DIR, script)
        self.log.info('Run: %s', script)
        try:
            subprocess.Popen(
                ['bash', path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            self.log.error('Failed to run %s: %s', script, e)

    def _on_show(self, icon, item):
        if subprocess.run(['pgrep', '-f', 'tts-settings.sh'],
                         capture_output=True).returncode == 0:
            return
        self._run('tts-settings.sh')

    def _on_pause(self, icon=None, item=None):
        self._run('speak-pause.sh')

    def _on_stop(self, icon=None, item=None):
        self._run('speak-stop.sh')
        try:
            with open(STATUS_FILE, 'w') as f:
                f.write('IDLE')
        except OSError:
            pass

    def _on_seek_back(self, icon=None, item=None):
        self.log.info('Seek -10s')
        _send_mpv(['seek', '-10'])

    def _on_seek_forward(self, icon=None, item=None):
        self.log.info('Seek +10s')
        _send_mpv(['seek', '10'])

    def _on_quit(self, icon, item):
        self.log.info('Quit requested')
        self._running = False
        self._stop_keys()
        if self._lock_fd:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                self._lock_fd.close()
            except OSError:
                pass
        self._icon.stop()

    def run(self):
        self._icon.run()


def main():
    TTSDaemon().run()


if __name__ == '__main__':
    main()
