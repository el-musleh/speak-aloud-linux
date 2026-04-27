#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

import atexit
import fcntl
import json
import os
import shutil
import signal
import socket as _sock
import subprocess
import threading
from enum import Enum, auto

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')
SPEAK_SH    = os.path.join(SCRIPT_DIR, 'speak.sh')
PAUSE_SH    = os.path.join(SCRIPT_DIR, 'speak-pause.sh')
MPV_SOCKET  = '/tmp/mpvsocket'
WORK_DIR    = '/tmp/tts_work'
MAX_CHARS   = 5000


class AppState(Enum):
    IDLE       = auto()
    GENERATING = auto()
    PLAYING    = auto()


def get_selection() -> str:
    """Grab primary selection (mouse-highlighted text) from X11 or Wayland."""
    try:
        cmd = ['wl-paste', '-p', '--no-newline'] \
              if os.environ.get('WAYLAND_DISPLAY') else ['xsel', '-p']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        return r.stdout.strip()
    except Exception:
        return ''


# ─────────────────────────────────────────────────────────────────────────────
# Audio Engine — separated from the UI layer
# ─────────────────────────────────────────────────────────────────────────────

class TTSManager:
    """
    Manages the TTS subprocess lifecycle.

    All I/O monitoring is done via GLib.io_add_watch (event-driven, runs on
    the GLib main loop — no background thread needed for reading stdout).
    State callbacks are invoked on the main loop, so they are safe to call
    GTK code directly.
    """

    def __init__(self, on_state_change: callable, on_error: callable):
        self._proc      = None
        self._io_watch  = None
        self._on_state  = on_state_change   # (AppState) → None
        self._on_error  = on_error          # (str) → None
        atexit.register(self._hard_kill)    # best-effort cleanup on unexpected exit

    # ── Public API ────────────────────────────────────────────────────────────

    def speak(self, cmd_args: list) -> None:
        """Kill any running process, then launch a new TTS subprocess."""
        self._terminate()   # stop old process without firing state callbacks

        self._proc = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,     # own process group: killpg kills children too
        )

        # Non-blocking stdout so io_add_watch reads never stall the main loop
        fd = self._proc.stdout.fileno()
        fcntl.fcntl(fd, fcntl.F_SETFL,
                    fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

        self._io_watch = GLib.io_add_watch(
            fd,
            GLib.IOCondition.IN | GLib.IOCondition.HUP,
            self._on_stdout,
        )

    def kill(self) -> None:
        """Graceful stop: SIGTERM → 3 s grace period → SIGKILL. Fires IDLE callback."""
        self._cancel_watch()
        self._sigterm_proc(self._proc)
        self._proc = None
        self._cleanup()
        self._on_state(AppState.IDLE)

    def send_mpv(self, command: list) -> None:
        """Fire-and-forget: send a JSON command to the running mpv IPC socket."""
        def _do():
            try:
                s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
                s.settimeout(0.3)
                s.connect(MPV_SOCKET)
                s.sendall((json.dumps({'command': command}) + '\n').encode())
                s.close()
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()

    # ── GLib I/O callback ─────────────────────────────────────────────────────

    def _on_stdout(self, fd: int, condition: GLib.IOCondition) -> bool:
        """
        Called by GLib on the main loop whenever the subprocess stdout has data
        (IN) or the write-end of the pipe is closed because the process exited
        (HUP).  Returning SOURCE_REMOVE unregisters this watch.
        """
        if condition & GLib.IOCondition.IN:
            try:
                data = os.read(fd, 4096).decode(errors='replace')
                for line in data.splitlines():
                    self._dispatch(line.strip())
            except OSError:
                pass

        if condition & GLib.IOCondition.HUP:
            self._io_watch = None
            rc = self._proc.wait() if self._proc else 0
            self._proc = None
            self._cleanup()
            if rc != 0:
                self._on_error(
                    'speak.sh exited with an error.\n'
                    'Check your internet connection.')
            self._on_state(AppState.IDLE)
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE

    def _dispatch(self, line: str) -> None:
        if line == 'STATUS:GENERATING':
            self._on_state(AppState.GENERATING)
        elif line == 'STATUS:PLAYING':
            self._on_state(AppState.PLAYING)
        elif line == 'STATUS:ERROR':
            self._on_error(
                'Failed to generate speech.\n'
                'Check your internet connection.')

    # ── Private helpers ───────────────────────────────────────────────────────

    def _terminate(self) -> None:
        """Stop the running process without firing any state callbacks."""
        self._cancel_watch()
        self._sigterm_proc(self._proc)
        self._proc = None

    def _cancel_watch(self) -> None:
        if self._io_watch is not None:
            GLib.source_remove(self._io_watch)
            self._io_watch = None

    @staticmethod
    def _sigterm_proc(proc) -> None:
        """Send SIGTERM to the process group; escalate to SIGKILL after 3 s."""
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

    @staticmethod
    def _cleanup() -> None:
        subprocess.run(['pkill', '-f', 'mpv'], capture_output=True)
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    def _hard_kill(self) -> None:
        """atexit handler: best-effort kill with no GLib/GTK calls."""
        try:
            proc = self._proc
            if proc and proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
            try:
                subprocess.run(['pkill', '-f', 'mpv'], timeout=2,
                               capture_output=True)
            except Exception:
                pass
            shutil.rmtree(WORK_DIR, ignore_errors=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# UI layer
# ─────────────────────────────────────────────────────────────────────────────

class TTSWindow(Adw.ApplicationWindow):

    _STATE_UI = {
        AppState.IDLE:       ('▶  Speak', 'suggested-action',  False, '○', 'Ready — highlight text and press Speak'),
        AppState.GENERATING: ('■  Stop',  'destructive-action', False, '⟳', 'Generating audio…'),
        AppState.PLAYING:    ('■  Stop',  'destructive-action', True,  '♪', 'Playing…'),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title('Speak a Loud')
        self.set_default_size(440, 620)

        with open(CONFIG_PATH) as f:
            self.config = json.load(f)

        self._state     = AppState.IDLE
        self._is_paused = False

        # TTSManager callbacks run on the GLib main loop (via io_add_watch),
        # so they are safe to update GTK widgets directly.
        self._manager = TTSManager(
            on_state_change=self._set_state,
            on_error=self._show_error,
        )

        self._build_ui()
        self._load_saved_settings()
        self.connect('close-request', self._on_close_request)
        GLib.idle_add(self._check_wayland_clipboard)   # warn once after window shows

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        tv = Adw.ToolbarView()
        self.set_content(tv)

        hb = Adw.HeaderBar()
        grab_btn = Gtk.Button(icon_name='view-refresh-symbolic',
                              tooltip_text='Grab highlighted text (refresh preview)')
        grab_btn.connect('clicked', lambda _: self._grab_and_preview())
        hb.pack_start(grab_btn)
        tv.add_top_bar(hb)

        scroll = Gtk.ScrolledWindow(vexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=520, tightening_threshold=420)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        root.set_margin_top(16);  root.set_margin_bottom(24)
        root.set_margin_start(16); root.set_margin_end(16)
        clamp.set_child(root)
        scroll.set_child(clamp)
        tv.set_content(scroll)

        # ── Text preview ──────────────────────────────────────────────────────
        preview_group = Adw.PreferencesGroup(title='Selected Text')

        self._tbuf = Gtk.TextBuffer()
        self._tbuf.set_text(
            'Highlight text anywhere on screen, then press ↺ or click Speak.')

        tview = Gtk.TextView(
            buffer=self._tbuf,
            editable=False,
            cursor_visible=False,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=10, bottom_margin=10,
            left_margin=10, right_margin=10,
        )
        tview.add_css_class('card')

        tscroll = Gtk.ScrolledWindow(
            min_content_height=90, max_content_height=160,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        tscroll.set_child(tview)
        preview_group.add(tscroll)
        root.append(preview_group)

        # ── Char counter row ──────────────────────────────────────────────────
        self._char_lbl = Gtk.Label(label='', xalign=1.0)
        self._char_lbl.add_css_class('dim-label')
        self._char_lbl.add_css_class('caption')
        root.append(self._char_lbl)

        # ── Voice selection ───────────────────────────────────────────────────
        voice_group = Adw.PreferencesGroup(title='Voices')

        self._en_combo = Adw.ComboRow(title='English')
        self._en_combo.set_model(
            Gtk.StringList.new([v['name'] for v in self.config['voices']['english']]))

        self._ar_combo = Adw.ComboRow(title='Arabic')
        self._ar_combo.set_model(
            Gtk.StringList.new([v['name'] for v in self.config['voices']['arabic']]))

        voice_group.add(self._en_combo)
        voice_group.add(self._ar_combo)
        root.append(voice_group)

        # ── Speed sliders ─────────────────────────────────────────────────────
        speed_group = Adw.PreferencesGroup(
            title='Playback Speed',
            description='Drag during playback for instant real-time adjustment')

        self._en_speed_lbl, en_row = self._make_speed_row('English', 50)
        self._ar_speed_lbl, ar_row = self._make_speed_row('Arabic',  30)
        speed_group.add(en_row)
        speed_group.add(ar_row)
        root.append(speed_group)

        # ── Controls ──────────────────────────────────────────────────────────
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                          spacing=8, homogeneous=True)

        self._primary_btn = Gtk.Button(label='▶  Speak', hexpand=True)
        self._primary_btn.add_css_class('suggested-action')
        self._primary_btn.add_css_class('pill')
        self._primary_btn.connect('clicked', self._on_primary)

        self._pause_btn = Gtk.Button(label='⏸  Pause', hexpand=True, sensitive=False)
        self._pause_btn.add_css_class('pill')
        self._pause_btn.connect('clicked', self._on_pause_resume)

        btn_box.append(self._primary_btn)
        btn_box.append(self._pause_btn)
        root.append(btn_box)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_lbl = Gtk.Label(
            label='○  Ready — highlight text and press Speak',
            xalign=0.5, wrap=True,
        )
        self._status_lbl.add_css_class('dim-label')
        self._status_lbl.add_css_class('caption')
        root.append(self._status_lbl)

    def _make_speed_row(self, title: str, default: int):
        lbl = Gtk.Label(label=f'+{default}%  ({(100+default)/100:.1f}×)',
                        width_chars=12, xalign=1.0)
        lbl.add_css_class('dim-label')

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        scale.set_value(default)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.set_size_request(140, -1)
        scale.connect('value-changed', self._on_speed_changed, lbl)

        if title == 'English':
            self._en_scale = scale
        else:
            self._ar_scale = scale

        suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                         spacing=8, valign=Gtk.Align.CENTER)
        suffix.append(scale)
        suffix.append(lbl)

        row = Adw.ActionRow(title=title)
        row.add_suffix(suffix)
        row.set_activatable_widget(scale)
        return lbl, row

    def _load_saved_settings(self):
        sel = self.config.get('selected', {})
        self._en_combo.set_selected(sel.get('english_voice_index', 0))
        self._ar_combo.set_selected(sel.get('arabic_voice_index',  0))
        en_spd = sel.get('english_speed', 50)
        ar_spd = sel.get('arabic_speed',  30)
        self._en_scale.set_value(en_spd)
        self._ar_scale.set_value(ar_spd)
        self._en_speed_lbl.set_label(f'+{en_spd}%  ({(100+en_spd)/100:.1f}×)')
        self._ar_speed_lbl.set_label(f'+{ar_spd}%  ({(100+ar_spd)/100:.1f}×)')

    # ── State machine ─────────────────────────────────────────────────────────

    def _set_state(self, state: AppState):
        self._state = state
        label, css, pause_on, icon, status = self._STATE_UI[state]

        self._primary_btn.set_label(label)
        for cls in ('suggested-action', 'destructive-action'):
            self._primary_btn.remove_css_class(cls)
        self._primary_btn.add_css_class(css)

        self._pause_btn.set_sensitive(pause_on)
        self._status_lbl.set_label(f'{icon}  {status}')

        if state == AppState.IDLE:
            self._is_paused = False
            self._pause_btn.set_label('⏸  Pause')

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_primary(self, _btn):
        if self._state == AppState.IDLE:
            text = self._grab_and_preview()
            if not text:
                return
            if len(text) > MAX_CHARS:
                self._show_char_limit_warning(len(text))
                return
            self._start_speaking(text)
        else:
            self._manager.kill()

    def _on_pause_resume(self, _btn):
        subprocess.run(['bash', PAUSE_SH], capture_output=True)
        self._is_paused = not self._is_paused
        self._pause_btn.set_label('▶  Resume' if self._is_paused else '⏸  Pause')

    def _on_speed_changed(self, scale, lbl):
        val = int(scale.get_value())
        mpv_speed = (100 + val) / 100
        lbl.set_label(f'+{val}%  ({mpv_speed:.1f}×)')
        if self._state == AppState.PLAYING:
            self._manager.send_mpv(['set_property', 'speed', round(mpv_speed, 3)])

    def _on_close_request(self, _win) -> bool:
        self._manager.kill()
        return False    # allow the window to close

    # ── Core actions ──────────────────────────────────────────────────────────

    def _start_speaking(self, text: str):
        en_idx   = self._en_combo.get_selected()
        ar_idx   = self._ar_combo.get_selected()
        en_voice = self.config['voices']['english'][en_idx]['id']
        ar_voice = self.config['voices']['arabic'][ar_idx]['id']
        en_rate  = f"+{int(self._en_scale.get_value())}%"
        ar_rate  = f"+{int(self._ar_scale.get_value())}%"
        speed    = round((100 + int(self._en_scale.get_value())) / 100, 3)

        self._save_settings(en_idx, ar_idx)
        self._set_state(AppState.GENERATING)   # immediate feedback before first STATUS line

        self._manager.speak([
            'bash', SPEAK_SH,
            '--text',     text,
            '--en-voice', en_voice,
            '--ar-voice', ar_voice,
            '--en-rate',  en_rate,
            '--ar-rate',  ar_rate,
            '--speed',    str(speed),
        ])

    def _grab_and_preview(self) -> str:
        text = get_selection()
        self._tbuf.set_text(
            text if text else '(Nothing selected — highlight some text first.)')
        n = len(text)
        if n > 0:
            color = 'error' if n > MAX_CHARS else 'dim-label'
            self._char_lbl.set_label(f'{n:,} / {MAX_CHARS:,} characters')
            self._char_lbl.set_css_classes(['caption', color])
        else:
            self._char_lbl.set_label('')
        return text

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_wayland_clipboard(self) -> bool:
        """Show a one-time warning if on Wayland and wl-clipboard is missing."""
        if os.environ.get('WAYLAND_DISPLAY') and not shutil.which('wl-paste'):
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading='Missing Dependency',
                body='You are on Wayland but wl-clipboard is not installed.\n'
                     'Highlighted text selection will not work.\n\n'
                     'Fix with:  sudo apt install wl-clipboard',
            )
            dialog.add_response('ok', 'OK')
            dialog.present()
        return GLib.SOURCE_REMOVE   # run once via idle_add, then stop

    def _save_settings(self, en_idx: int, ar_idx: int):
        self.config.setdefault('selected', {})
        self.config['selected']['english_voice_index'] = en_idx
        self.config['selected']['arabic_voice_index']  = ar_idx
        self.config['selected']['english_speed'] = int(self._en_scale.get_value())
        self.config['selected']['arabic_speed']  = int(self._ar_scale.get_value())
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=2)

    def _show_error(self, message: str) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self, heading='TTS Error', body=message)
        dialog.add_response('ok', 'OK')
        dialog.present()

    def _show_char_limit_warning(self, char_count: int) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading='Selection Too Long',
            body=f'Selected text is {char_count:,} characters '
                 f'(limit: {MAX_CHARS:,}).\n\n'
                 'Please select a shorter passage.',
        )
        dialog.add_response('ok', 'OK')
        dialog.present()


# ─────────────────────────────────────────────────────────────────────────────

class TTSApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.speakaloud')
        self.connect('activate', self._on_activate)

    def _on_activate(self, _app):
        TTSWindow(application=self).present()


if __name__ == '__main__':
    import sys
    TTSApp().run(sys.argv)
