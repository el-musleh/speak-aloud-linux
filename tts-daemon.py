#!/usr/bin/env python3
"""
TTS Tray Daemon — always-running GTK3 tray icon for Cinnamon.

Polls /tmp/tts-status (written by speak.sh) every 500ms and updates
the XApp.StatusIcon accordingly.  Menu actions call speak-pause.sh and
speak-stop.sh directly — no sockets, no IPC, no race conditions.

Auto-started on login via ~/.config/autostart/tts-daemon.desktop.
Single-instance enforced via /tmp/tts-daemon.lock.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, GLib, XApp

import fcntl
import os
import subprocess
import sys

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = '/tmp/tts-status'
LOCK_FILE   = '/tmp/tts-daemon.lock'
MPV_SOCKET  = '/tmp/speak-aloud-mpv.sock'

_STATE_LABELS = {
    'IDLE':       '○  Ready',
    'GENERATING': '⟳  Generating…',
    'RETRYING':   '⟳  Retrying…',
    'PLAYING':    '♪  Playing',
}

_STATE_ICONS = {
    'IDLE':       'audio-speakers',
    'GENERATING': 'emblem-synchronizing',
    'RETRYING':   'network-error',
    'PLAYING':    'audio-volume-high',
}


class TTSDaemon:
    def __init__(self):
        self._current_state = ''
        self._icon = None
        self._lock_fd = None
        self._acquire_lock()
        self._build_icon()
        GLib.timeout_add(500, self._poll_status)

    # ── Single-instance lock ───────────────────────────────────────────────────

    def _acquire_lock(self):
        try:
            fd = open(LOCK_FILE, 'w')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(str(os.getpid()))
            fd.flush()
            self._lock_fd = fd
        except (IOError, OSError):
            sys.stderr.write('tts-daemon: already running, exiting.\n')
            sys.exit(0)

    # ── Tray icon ──────────────────────────────────────────────────────────────

    def _build_icon(self):
        icon = XApp.StatusIcon()
        icon.set_icon_name('audio-speakers')
        icon.set_tooltip_text('Speak a Loud — ○ Ready')
        icon.set_label('')
        icon.set_visible(True)
        self._icon = icon
        self._rebuild_menu('IDLE')

    def _rebuild_menu(self, state: str):
        label = _STATE_LABELS.get(state, '○  Ready')

        status_item = Gtk.MenuItem(label=label)
        status_item.set_sensitive(False)

        show_item = Gtk.MenuItem(label='Show App')
        show_item.connect('activate', self._on_show_app)

        pause_item = Gtk.MenuItem(label='Play / Pause')
        pause_item.connect('activate', self._on_pause)

        stop_item = Gtk.MenuItem(label='Stop')
        stop_item.connect('activate', self._on_stop)

        quit_item = Gtk.MenuItem(label='Quit Daemon')
        quit_item.connect('activate', self._on_quit)

        menu = Gtk.Menu()
        for w in [status_item,
                  Gtk.SeparatorMenuItem(),
                  show_item,
                  Gtk.SeparatorMenuItem(),
                  pause_item,
                  stop_item,
                  Gtk.SeparatorMenuItem(),
                  quit_item]:
            menu.append(w)
        menu.show_all()

        self._icon.set_primary_menu(menu)
        self._icon.set_secondary_menu(menu)

    # ── Status polling ─────────────────────────────────────────────────────────

    def _poll_status(self):
        try:
            with open(STATUS_FILE) as f:
                state = f.read().strip()
        except (FileNotFoundError, OSError):
            state = 'IDLE'

        if state != self._current_state:
            self._current_state = state
            label = _STATE_LABELS.get(state, '○  Ready')
            icon  = _STATE_ICONS.get(state, 'audio-speakers')
            self._icon.set_icon_name(icon)
            self._icon.set_tooltip_text(f'Speak a Loud — {label}')
            self._rebuild_menu(state)

        return GLib.SOURCE_CONTINUE  # keep polling

    # ── Menu actions ───────────────────────────────────────────────────────────

    def _run(self, *args):
        try:
            subprocess.Popen(list(args), stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except Exception as e:
            sys.stderr.write(f'tts-daemon: run {args} failed: {e}\n')

    def _on_show_app(self, _item):
        app = os.path.join(SCRIPT_DIR, 'tts-app.py')
        self._run(sys.executable, app)

    def _on_pause(self, _item):
        pause_sh = os.path.join(SCRIPT_DIR, 'speak-pause.sh')
        self._run('bash', pause_sh)

    def _on_stop(self, _item):
        stop_sh = os.path.join(SCRIPT_DIR, 'speak-stop.sh')
        self._run('bash', stop_sh)
        # Immediately reflect IDLE in the tray
        try:
            with open(STATUS_FILE, 'w') as f:
                f.write('IDLE')
        except OSError:
            pass

    def _on_quit(self, _item):
        Gtk.main_quit()


def main():
    daemon = TTSDaemon()
    Gtk.main()


if __name__ == '__main__':
    main()
