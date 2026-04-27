#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

import json
import os
import subprocess
import threading

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')
SPEAK_SH    = os.path.join(SCRIPT_DIR, 'speak.sh')
PAUSE_SH    = os.path.join(SCRIPT_DIR, 'speak-pause.sh')


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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title('Speak a Loud')
        self.set_default_size(440, 620)

        with open(CONFIG_PATH) as f:
            self.config = json.load(f)

        self._is_paused = False
        self._build_ui()
        self._load_saved_settings()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        tv = Adw.ToolbarView()
        self.set_content(tv)

        # Header bar
        hb = Adw.HeaderBar()
        grab_btn = Gtk.Button(icon_name='view-refresh-symbolic',
                              tooltip_text='Grab highlighted text (refresh preview)')
        grab_btn.connect('clicked', lambda _: self._grab_and_preview())
        hb.pack_start(grab_btn)
        tv.add_top_bar(hb)

        # Scrollable clamp
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
            'Highlight text anywhere on screen, then press ↺ above or click Speak.')

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
        speed_group = Adw.PreferencesGroup(title='Playback Speed  (0 % = normal, 100 % = 2×)')

        self._en_speed_lbl, en_speed_row = self._make_speed_row('English', 50)
        self._ar_speed_lbl, ar_speed_row = self._make_speed_row('Arabic',  30)

        speed_group.add(en_speed_row)
        speed_group.add(ar_speed_row)
        root.append(speed_group)

        # ── Control buttons ───────────────────────────────────────────────────
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                          spacing=8, homogeneous=True)

        self._speak_btn = Gtk.Button(label='▶  Speak', hexpand=True)
        self._speak_btn.add_css_class('suggested-action')
        self._speak_btn.add_css_class('pill')
        self._speak_btn.connect('clicked', self._on_speak)

        self._pause_btn = Gtk.Button(label='⏸  Pause', hexpand=True, sensitive=False)
        self._pause_btn.add_css_class('pill')
        self._pause_btn.connect('clicked', self._on_pause_resume)

        self._stop_btn = Gtk.Button(label='■  Stop', hexpand=True, sensitive=False)
        self._stop_btn.add_css_class('destructive-action')
        self._stop_btn.add_css_class('pill')
        self._stop_btn.connect('clicked', self._on_stop)

        btn_box.append(self._speak_btn)
        btn_box.append(self._pause_btn)
        btn_box.append(self._stop_btn)
        root.append(btn_box)

    def _make_speed_row(self, title: str, default: int):
        """Return (label_widget, ActionRow) for a speed slider row."""
        lbl = Gtk.Label(label=f'+{default}%', width_chars=6, xalign=1.0)
        lbl.add_css_class('dim-label')

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        scale.set_value(default)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.set_size_request(160, -1)
        scale.connect('value-changed',
                      lambda s, l=lbl: l.set_label(f'+{int(s.get_value())}%'))

        if title == 'English':
            self._en_scale = scale
        else:
            self._ar_scale = scale

        suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                         spacing=6, valign=Gtk.Align.CENTER)
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
        self._en_speed_lbl.set_label(f'+{en_spd}%')
        self._ar_speed_lbl.set_label(f'+{ar_spd}%')

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _grab_and_preview(self) -> str:
        text = get_selection()
        self._tbuf.set_text(
            text if text else '(Nothing selected — highlight some text first.)')
        return text

    def _on_speak(self, _btn):
        text = self._grab_and_preview()
        if not text:
            return

        en_idx   = self._en_combo.get_selected()
        ar_idx   = self._ar_combo.get_selected()
        en_voice = self.config['voices']['english'][en_idx]['id']
        ar_voice = self.config['voices']['arabic'][ar_idx]['id']
        en_rate  = f"+{int(self._en_scale.get_value())}%"
        ar_rate  = f"+{int(self._ar_scale.get_value())}%"

        self._save_settings(en_idx, ar_idx)
        self._set_playing(True)

        def _run():
            try:
                proc = subprocess.run(
                    ['bash', SPEAK_SH,
                     '--text',     text,
                     '--en-voice', en_voice,
                     '--ar-voice', ar_voice,
                     '--en-rate',  en_rate,
                     '--ar-rate',  ar_rate],
                    capture_output=True,
                )
                if proc.returncode != 0:
                    GLib.idle_add(self._show_error,
                                  'speak.sh failed.\nCheck your internet connection.')
            finally:
                GLib.idle_add(self._set_playing, False)

        threading.Thread(target=_run, daemon=True).start()

    def _on_pause_resume(self, _btn):
        subprocess.run(['bash', PAUSE_SH], capture_output=True)
        self._is_paused = not self._is_paused
        self._pause_btn.set_label('▶  Resume' if self._is_paused else '⏸  Pause')

    def _on_stop(self, _btn):
        subprocess.run(['pkill', '-f', 'mpv'], capture_output=True)
        self._set_playing(False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_playing(self, playing: bool):
        self._speak_btn.set_sensitive(not playing)
        self._pause_btn.set_sensitive(playing)
        self._stop_btn.set_sensitive(playing)
        if not playing:
            self._is_paused = False
            self._pause_btn.set_label('⏸  Pause')

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
