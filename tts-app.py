#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

import json
import os
import select
import shutil
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

class TTSWindow(Adw.ApplicationWindow):

    # State machine configuration: maps AppState → (button_label, button_css,
    # pause_sensitive, status_icon, status_text)
    _STATE_UI = {
        AppState.IDLE:       ('▶  Speak',    'suggested-action', False,
                              '○', 'Ready — highlight text and press Speak'),
        AppState.GENERATING: ('■  Stop',     'destructive-action', False,
                              '⟳', 'Generating audio…'),
        AppState.PLAYING:    ('■  Stop',     'destructive-action', True,
                              '♪', 'Playing…'),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title('Speak a Loud')
        self.set_default_size(440, 620)

        with open(CONFIG_PATH) as f:
            self.config = json.load(f)

        self._state   = AppState.IDLE
        self._proc    = None          # active subprocess.Popen
        self._poll_id = None          # GLib timer source ID
        self._is_paused = False

        self._build_ui()
        self._load_saved_settings()
        self.connect('close-request', self._on_close_request)

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
            min_content_height=90,
            max_content_height=160,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        tscroll.set_child(tview)
        preview_group.add(tscroll)
        root.append(preview_group)

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

        self._en_speed_lbl, en_speed_row = self._make_speed_row('English', 50)
        self._ar_speed_lbl, ar_speed_row = self._make_speed_row('Arabic',  30)

        speed_group.add(en_speed_row)
        speed_group.add(ar_speed_row)
        root.append(speed_group)

        # ── Controls: Speak/Stop toggle + Pause ───────────────────────────────
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
            xalign=0.5,
            wrap=True,
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

        # Update primary button
        self._primary_btn.set_label(label)
        for cls in ('suggested-action', 'destructive-action'):
            self._primary_btn.remove_css_class(cls)
        self._primary_btn.add_css_class(css)

        # Update pause button
        self._pause_btn.set_sensitive(pause_on)

        # Update status label
        self._status_lbl.set_label(f'{icon}  {status}')

        if state == AppState.IDLE:
            self._is_paused = False
            self._pause_btn.set_label('⏸  Pause')

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_primary(self, _btn):
        if self._state == AppState.IDLE:
            text = self._grab_and_preview()
            if text:
                self._start_speaking(text)
        else:
            # GENERATING or PLAYING → stop
            self._kill_process()

    def _on_pause_resume(self, _btn):
        subprocess.run(['bash', PAUSE_SH], capture_output=True)
        self._is_paused = not self._is_paused
        self._pause_btn.set_label('▶  Resume' if self._is_paused else '⏸  Pause')

    def _on_speed_changed(self, scale, lbl):
        val = int(scale.get_value())
        mpv_speed = (100 + val) / 100
        lbl.set_label(f'+{val}%  ({mpv_speed:.1f}×)')
        if self._state == AppState.PLAYING:
            self._send_mpv(['set_property', 'speed', round(mpv_speed, 3)])

    def _on_close_request(self, _win):
        self._kill_process()
        return False

    # ── Process lifecycle ─────────────────────────────────────────────────────

    def _start_speaking(self, text: str):
        en_idx   = self._en_combo.get_selected()
        ar_idx   = self._ar_combo.get_selected()
        en_voice = self.config['voices']['english'][en_idx]['id']
        ar_voice = self.config['voices']['arabic'][ar_idx]['id']
        en_rate  = f"+{int(self._en_scale.get_value())}%"
        ar_rate  = f"+{int(self._ar_scale.get_value())}%"
        initial_speed = round((100 + int(self._en_scale.get_value())) / 100, 3)

        self._save_settings(en_idx, ar_idx)
        self._set_state(AppState.GENERATING)

        self._proc = subprocess.Popen(
            ['bash', SPEAK_SH,
             '--text',     text,
             '--en-voice', en_voice,
             '--ar-voice', ar_voice,
             '--en-rate',  en_rate,
             '--ar-rate',  ar_rate,
             '--speed',    str(initial_speed)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        # Start polling loop: 100 ms ticks to read stdout and detect completion
        if self._poll_id is not None:
            GLib.source_remove(self._poll_id)
        self._poll_id = GLib.timeout_add(100, self._poll_process)

    def _poll_process(self) -> bool:
        """Called every 100 ms by GLib to check process state and read stdout."""
        if self._proc is None:
            self._poll_id = None
            return GLib.SOURCE_REMOVE

        # Non-blocking read — select() returns immediately if no data ready
        readable, _, _ = select.select([self._proc.stdout], [], [], 0)
        if readable:
            line = self._proc.stdout.readline().decode(errors='replace').strip()
            if line == 'STATUS:GENERATING':
                self._set_state(AppState.GENERATING)
            elif line == 'STATUS:PLAYING':
                self._set_state(AppState.PLAYING)
            elif line == 'STATUS:ERROR':
                self._show_error('speak.sh failed.\nCheck your internet connection.')

        # Check if the process has finished on its own
        if self._proc.poll() is not None:
            self._poll_id = None
            self._handle_process_end(self._proc.returncode)
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE

    def _handle_process_end(self, returncode: int):
        self._proc = None
        self._cleanup_temp_files()
        if returncode == 0:
            self._set_state(AppState.IDLE)
        else:
            self._set_state(AppState.IDLE)
            self._show_error('speak.sh exited with an error.\n'
                             'Check your internet connection.')

    def _kill_process(self):
        proc = self._proc
        self._proc = None           # signal the poll loop to stop
        if self._poll_id is not None:
            GLib.source_remove(self._poll_id)
            self._poll_id = None
        if proc and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(['pkill', '-f', 'mpv'], capture_output=True)
        self._cleanup_temp_files()
        self._set_state(AppState.IDLE)

    @staticmethod
    def _cleanup_temp_files():
        """Delete temp MP3 segments and work directory."""
        if os.path.isdir(WORK_DIR):
            shutil.rmtree(WORK_DIR, ignore_errors=True)

    # ── mpv IPC ───────────────────────────────────────────────────────────────

    def _send_mpv(self, command: list):
        """Fire-and-forget: send a JSON command to the mpv IPC socket."""
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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _grab_and_preview(self) -> str:
        text = get_selection()
        self._tbuf.set_text(
            text if text else '(Nothing selected — highlight some text first.)')
        return text

    def _save_settings(self, en_idx: int, ar_idx: int):
        self.config.setdefault('selected', {})
        self.config['selected']['english_voice_index'] = en_idx
        self.config['selected']['arabic_voice_index']  = ar_idx
        self.config['selected']['english_speed'] = int(self._en_scale.get_value())
        self.config['selected']['arabic_speed']  = int(self._ar_scale.get_value())
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=2)

    def _show_error(self, message: str):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading='TTS Error',
            body=message,
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
