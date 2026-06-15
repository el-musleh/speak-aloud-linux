#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

import atexit
import json
import os
import shutil
import signal
import socket as _sock
import subprocess
import sys
import glob
import tempfile
import threading
import time
from enum import Enum, auto
from threading import Lock, Event

def _notify(title: str, body: str = '', icon: str = 'audio-speakers') -> None:
    """Fire-and-forget desktop notification."""
    def _do():
        try:
            subprocess.run(
                ['notify-send', '-i', icon, '-h', 'int:transient:1',
                 '-t', '4000', title, body],
                capture_output=True, timeout=5)
        except Exception:
            pass
    threading.Thread(target=_do, daemon=True).start()

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')   # voice catalog only (read-only)
SPEAK_SH    = os.path.join(SCRIPT_DIR, 'speak.sh')

# Single source of truth for user settings — shared with speak.sh / tts-settings.sh
SHELL_CFG_DIR = os.path.expanduser('~/.config/tts_settings')

# Shared catalog + defaults (single source of truth with tts-settings.sh)
_SHARED_PATH = os.path.join(SCRIPT_DIR, 'tts-shared.json')
try:
    with open(_SHARED_PATH) as _f:
        _SHARED = json.load(_f)
except (FileNotFoundError, json.JSONDecodeError, OSError) as _e:
    print(f'Warning: could not load {_SHARED_PATH}: {_e}')
    _SHARED = {}


def read_setting(name: str, default: str) -> str:
    """Read one setting file from ~/.config/tts_settings, with fallback."""
    try:
        with open(os.path.join(SHELL_CFG_DIR, name)) as f:
            value = f.read().strip()
        return value if value else default
    except OSError:
        return default


def read_rate(name: str, default: int) -> int:
    """Parse a '+50%'-style rate file into an int, clamped to 0–100."""
    raw = read_setting(name, f'+{default}%').strip('+%')
    try:
        return max(0, min(100, int(raw)))
    except ValueError:
        return default


def read_bool_setting(name: str, default: bool = False) -> bool:
    """Read a yes/no setting file and return a bool."""
    raw = read_setting(name, 'yes' if default else 'no').lower().strip()
    return raw in ('yes', 'true', '1', 'on')


# ── Language data (loaded from tts-shared.json) ─────────────────────────────

SOURCE_LANGUAGES = [
    (item['code'], item['name']) for item in _SHARED.get('source_languages', [])
]
TRANSLATION_LANGUAGES = [
    (item['code'], item['name']) for item in _SHARED.get('translation_languages', [])
]
TRANSLATION_PROVIDERS = [
    (item['code'], item['name']) for item in _SHARED.get('translation_providers', [])
]

# Use system temp directory for portability
TEMP_DIR = tempfile.gettempdir()
MPV_SOCKET  = os.path.join(TEMP_DIR, 'speak-aloud-mpv.sock')
WORK_DIR    = os.path.join(TEMP_DIR, 'speak-aloud-work')
SAVED_DIR   = os.path.join(TEMP_DIR, 'speak-aloud-saved')  # snapshot for "Save Audio"
MAX_CHARS   = 5000

DEFAULT_CONFIG = {'voices': _SHARED.get('voices', {})}


class AppState(Enum):
    IDLE       = auto()
    GENERATING = auto()
    RETRYING   = auto()
    PLAYING    = auto()


def get_selection() -> str:
    """Grab primary selection. Runs in a background thread — never on main loop."""
    try:
        cmd = ['wl-paste', '-p', '--no-newline'] \
              if os.environ.get('WAYLAND_DISPLAY') else ['xsel', '-p']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        return r.stdout.strip()
    except Exception:
        return ''


# ─────────────────────────────────────────────────────────────────────────────
# Audio Engine
# ─────────────────────────────────────────────────────────────────────────────

class TTSManager:
    """
    Subprocess lifecycle manager.

    Key design decisions:
    - stdout is read in a background thread (never blocks the main loop)
    - GLib.idle_add routes all UI-touching callbacks back to the main loop
    - A session counter ensures callbacks from killed/replaced processes are
      silently discarded — prevents stale "error" dialogs and double-IDLE
    - kill() is fully non-blocking: sends SIGTERM and hands the wait() off
      to a background thread; the UI updates instantly
    """

    def __init__(self, on_state_change: callable, on_error: callable):
        self._proc     = None
        self._session  = 0
        self._on_state = on_state_change
        self._on_error = on_error
        self._lock     = Lock()  # Thread synchronization
        self._shutdown = Event()  # Shutdown signal
        atexit.register(self._hard_kill)

    # ── Public API ────────────────────────────────────────────────────────────

    def speak(self, cmd_args: list) -> None:
        """Replace any running process with a new one. Never blocks."""
        self._terminate()           # SIGKILL old process (fast), no state callback
        self._session += 1
        session = self._session

        self._proc = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,   # own process group → killpg reaches all children
        )
        proc = self._proc
        threading.Thread(
            target=self._stdout_reader, args=(proc, session), daemon=True
        ).start()

    def kill(self) -> None:
        """
        User-triggered stop.  Sends SIGTERM immediately (main thread returns at
        once), then escalates to SIGKILL after 3 s in a background thread.
        Fires the IDLE state callback instantly.
        """
        self._session += 1          # discard any pending end-of-process callbacks
        proc = self._proc
        self._proc = None

        def _graceful_shutdown():
            if proc and proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=3)
                except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
            self._cleanup()         # pkill + socket + work dir — all in background

        threading.Thread(target=_graceful_shutdown, daemon=True).start()
        self._on_state(AppState.IDLE)   # instant UI feedback on main loop

    def shutdown(self) -> None:
        """
        Window-close path.  Sends SIGTERM but does NOT wait — atexit handles
        any remaining cleanup.  Returns immediately so the window can close.
        """
        self._session += 1
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        threading.Thread(target=self._cleanup, daemon=True).start()

    def send_mpv(self, command: list) -> None:
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

    def send_mpv_query(self, command: list) -> dict | None:
        """Send command and return mpv's JSON response."""
        s = None
        try:
            s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(MPV_SOCKET)
            s.sendall((json.dumps({'command': command}) + '\n').encode())
            s.settimeout(2.0)
            buf = b''
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                for raw in buf.split(b'\n'):
                    if not raw:
                        continue
                    try:
                        resp = json.loads(raw.decode())
                        if 'error' in resp:
                            return resp
                    except json.JSONDecodeError:
                        continue
            return None
        except Exception:
            return None
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass

    def get_mpv_state(self) -> dict | None:
        """Returns {position, duration, paused} or None if mpv is not running."""
        pos_resp = self.send_mpv_query(['get_property', 'time-pos'])
        if not pos_resp or pos_resp.get('error') != 'success':
            return None
        dur_resp = self.send_mpv_query(['get_property', 'duration'])
        pause_resp = self.send_mpv_query(['get_property', 'pause'])
        return {
            'position': pos_resp.get('data', 0) or 0,
            'duration': dur_resp.get('data', 0) or 0 if dur_resp else 0,
            'paused': pause_resp.get('data', False) if pause_resp else False,
        }

    # ── Background stdout reader ──────────────────────────────────────────────

    def _stdout_reader(self, proc, session: int) -> None:
        """Runs in a daemon thread. Reads lines, dispatches to main loop."""
        try:
            for raw in proc.stdout:
                line = raw.decode(errors='replace').strip()
                if line:
                    GLib.idle_add(self._dispatch, line, session)
        except Exception:
            pass
        finally:
            rc = proc.poll()
            if rc is None:
                try:
                    rc = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    rc = -1
            GLib.idle_add(self._on_proc_done, rc, session)

    def _dispatch(self, line: str, session: int) -> bool:
        if session != self._session:
            return GLib.SOURCE_REMOVE   # stale — from a replaced or killed process
        if line == 'STATUS:GENERATING':
            self._on_state(AppState.GENERATING)
        elif line == 'STATUS:RETRYING':
            self._on_state(AppState.RETRYING)
        elif line == 'STATUS:PLAYING':
            self._on_state(AppState.PLAYING)
        elif line == 'STATUS:ERROR':
            self._on_error('Failed to generate speech.\n'
                           'Check your internet connection.')
        return GLib.SOURCE_REMOVE

    def _on_proc_done(self, rc: int, session: int) -> bool:
        if session != self._session:
            return GLib.SOURCE_REMOVE   # user already stopped this session
        self._proc = None
        # NOTE: do NOT auto-cleanup here — work dir is needed for "Save Audio"
        # and will be cleaned up by speak.sh on the next session start.
        if rc != 0:
            self._on_error('speak.sh exited with an error.\n'
                           'Check your internet connection.')
        self._on_state(AppState.IDLE)
        return GLib.SOURCE_REMOVE

    # ── Private helpers ───────────────────────────────────────────────────────

    def _terminate(self) -> None:
        """Fast internal kill for the 'replace with new process' path."""
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            try:
                # Ask speak.sh to release its flock gracefully before SIGKILL
                s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
                s.settimeout(0.2)
                s.connect(MPV_SOCKET)
                s.sendall(b'{"command":["quit"]}\n')
                s.close()
            except Exception:
                pass
            try:
                # start_new_session=True puts speak.sh AND its mpv child in
                # their own process group — killpg stops the audio too.
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=0.5)
            except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
                pass
        # Remove stale socket so the new mpv can bind to it
        try:
            os.unlink(MPV_SOCKET)
        except (FileNotFoundError, OSError):
            pass

    @staticmethod
    def _cleanup() -> None:
        """Delete socket, remove work dir."""
        # No killing - speak.sh handles its own mpv via the lock
        try:
            os.unlink(MPV_SOCKET)
        except (FileNotFoundError, OSError):
            pass
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    def _hard_kill(self) -> None:
        """atexit: best-effort cleanup with no GLib/GTK calls."""
        try:
            proc = self._proc
            if proc and proc.poll() is None:
                try:
                    # Kill the whole group (speak.sh + mpv) on app exit
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
            try:
                os.unlink(MPV_SOCKET)
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
        AppState.RETRYING:   ('■  Stop',  'destructive-action', False, '⟳', 'Network issue — retrying…'),
        AppState.PLAYING:    ('■  Stop',  'destructive-action', True,  '♪', 'Playing…'),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title('Speak a Loud')
        self.set_default_size(440, 800)

        # Voice catalog with graceful fallback so a missing/corrupt file doesn't crash.
        # User selections live in ~/.config/tts_settings (shared with CLI tools).
        try:
            with open(CONFIG_PATH) as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.config = json.loads(json.dumps(DEFAULT_CONFIG))

        self._state     = AppState.IDLE
        self._is_paused = False
        self._has_audio = False  # Track if audio was successfully generated
        self._manager   = TTSManager(
            on_state_change=self._set_state,
            on_error=self._show_error,
        )
        self._build_ui()
        self._load_saved_settings()
        self.connect('close-request', self._on_close_request)
        self.connect('realize', self._resize_to_content)
        GLib.idle_add(self._check_wayland_clipboard)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        tv = Adw.ToolbarView()
        self.set_content(tv)

        hb = Adw.HeaderBar()
        # ↺ button grabs selection asynchronously — never blocks the main loop
        grab_btn = Gtk.Button(icon_name='view-refresh-symbolic',
                              tooltip_text='Grab highlighted text (refresh preview)')
        grab_btn.connect('clicked', self._on_grab_clicked)
        hb.pack_start(grab_btn)

        tv.add_top_bar(hb)

        self._scroll = Gtk.ScrolledWindow(vexpand=True,
                                          hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=520, tightening_threshold=420)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        root.set_margin_top(16);  root.set_margin_bottom(24)
        root.set_margin_start(16); root.set_margin_end(16)
        clamp.set_child(root)
        self._scroll.set_child(clamp)
        tv.set_content(self._scroll)

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

        self._char_lbl = Gtk.Label(label='', xalign=1.0)
        self._char_lbl.add_css_class('caption')
        self._char_lbl.add_css_class('dim-label')
        root.append(self._char_lbl)

        # ── Voice selection ───────────────────────────────────────────────────
        voice_group = Adw.PreferencesGroup(title='Voices')

        self._en_combo = Adw.ComboRow(title='English')
        self._en_combo.set_model(
            Gtk.StringList.new([v['name'] for v in self.config['voices']['english']]))

        self._ar_combo = Adw.ComboRow(title='Arabic')
        self._ar_combo.set_model(
            Gtk.StringList.new([v['name'] for v in self.config['voices']['arabic']]))

        self._de_combo = Adw.ComboRow(title='German')
        self._de_combo.set_model(
            Gtk.StringList.new([v['name'] for v in self.config['voices']['german']]))

        voice_group.add(self._en_combo)
        voice_group.add(self._ar_combo)
        voice_group.add(self._de_combo)
        root.append(voice_group)

        # ── Speed sliders ─────────────────────────────────────────────────────
        speed_group = Adw.PreferencesGroup(
            title='Playback Speed',
            description='Drag during playback for instant real-time adjustment')

        _d = _SHARED.get('defaults', {})
        self._en_speed_lbl, en_row = self._make_speed_row('English', _d.get('rate', 50))
        self._ar_speed_lbl, ar_row = self._make_speed_row('Arabic',  _d.get('arabic_rate', 30))
        self._de_speed_lbl, de_row = self._make_speed_row('German',  _d.get('german_rate', 30))
        speed_group.add(en_row)
        speed_group.add(ar_row)
        speed_group.add(de_row)
        root.append(speed_group)

        # ── Source language ───────────────────────────────────────────────────
        lang_group = Adw.PreferencesGroup(title='Source Language')
        self._source_lang_combo = Adw.ComboRow(title='Detected Language')
        self._source_lang_combo.set_model(
            Gtk.StringList.new([label for _, label in SOURCE_LANGUAGES]))
        lang_group.add(self._source_lang_combo)
        root.append(lang_group)

        # ── Translation ───────────────────────────────────────────────────────
        trans_group = Adw.PreferencesGroup(title='Translation')

        self._trans_enabled = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._trans_enabled.connect('state-set', self._on_trans_enabled_changed)
        trans_toggle = Adw.ActionRow(title='Enable Translation')
        trans_toggle.add_suffix(self._trans_enabled)
        trans_toggle.set_activatable_widget(self._trans_enabled)
        trans_group.add(trans_toggle)

        self._trans_provider_combo = Adw.ComboRow(title='Provider')
        self._trans_provider_combo.set_model(
            Gtk.StringList.new([label for _, label in TRANSLATION_PROVIDERS]))
        trans_group.add(self._trans_provider_combo)

        self._trans_target_combo = Adw.ComboRow(title='Target Language')
        self._trans_target_combo.set_model(
            Gtk.StringList.new([label for _, label in TRANSLATION_LANGUAGES]))
        trans_group.add(self._trans_target_combo)

        self._trans_api_entry = Adw.PasswordEntryRow(title='API Key')
        self._trans_api_entry.set_show_apply_button(False)
        trans_group.add(self._trans_api_entry)

        root.append(trans_group)

        # ── File Actions ──────────────────────────────────────────────────────
        file_group = Adw.PreferencesGroup(title='File Actions')
        folder_row = Adw.ActionRow(title='Open Cache Folder')
        folder_btn = Gtk.Button(label='Open')
        folder_btn.add_css_class('pill')
        folder_btn.connect('clicked', self._on_open_folder)
        folder_row.add_suffix(folder_btn)
        folder_row.set_activatable_widget(folder_btn)
        file_group.add(folder_row)

        cache_row = Adw.ActionRow(title='Clear Audio Cache')
        cache_btn = Gtk.Button(label='Clear')
        cache_btn.add_css_class('pill')
        cache_btn.connect('clicked', self._on_clear_cache)
        cache_row.add_suffix(cache_btn)
        cache_row.set_activatable_widget(cache_btn)
        file_group.add(cache_row)

        root.append(file_group)

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

        self._status_lbl = Gtk.Label(
            label='○  Ready — highlight text and press Speak',
            xalign=0.5, wrap=True,
        )
        self._status_lbl.add_css_class('dim-label')
        self._status_lbl.add_css_class('caption')
        root.append(self._status_lbl)

        # Save Audio button — shown after successful playback
        self._save_btn = Gtk.Button(label='💾  Save Audio', visible=False)
        self._save_btn.add_css_class('pill')
        self._save_btn.connect('clicked', self._on_save_audio)
        root.append(self._save_btn)

    def _resize_to_content(self, _widget=None):
        """Resize window to fit all content, capped at 90% of screen height."""
        def do_resize():
            # Measure the clamp widget (contains all content)
            clamp = self._scroll.get_child()
            if clamp:
                _, nat_h, _, _ = clamp.measure(Gtk.Orientation.VERTICAL, -1)
                content_h = nat_h
            else:
                content_h = 600
            # Header bar (~80px) + window decorations (~40px)
            total_h = content_h + 120
            # Cap at 90% of screen height
            monitor = self.get_display().get_monitor_at_surface(self.get_surface())
            if monitor:
                max_h = int(monitor.get_geometry().height * 0.9)
                total_h = min(total_h, max_h)
            self.set_default_size(440, max(total_h, 500))
            return GLib.SOURCE_REMOVE
        GLib.idle_add(do_resize)

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
        elif title == 'Arabic':
            self._ar_scale = scale
        else:
            self._de_scale = scale

        suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                         spacing=8, valign=Gtk.Align.CENTER)
        suffix.append(scale)
        suffix.append(lbl)

        row = Adw.ActionRow(title=title)
        row.add_suffix(suffix)
        row.set_activatable_widget(scale)
        return lbl, row

    def _load_saved_settings(self):
        """Load selections from ~/.config/tts_settings (shared with CLI tools)."""
        def voice_index(voices, saved_id):
            return next((i for i, v in enumerate(voices) if v['id'] == saved_id), 0)

        en_voices = self.config['voices']['english']
        ar_voices = self.config['voices']['arabic']
        de_voices = self.config['voices']['german']
        _d = _SHARED.get('defaults', {})
        self._en_combo.set_selected(
            voice_index(en_voices, read_setting('voice', _d.get('voice', 'en-US-ChristopherNeural'))))
        self._ar_combo.set_selected(
            voice_index(ar_voices, read_setting('arabic_voice', _d.get('arabic_voice', 'ar-SA-HamedNeural'))))
        self._de_combo.set_selected(
            voice_index(de_voices, read_setting('german_voice', _d.get('german_voice', 'de-DE-ConradNeural'))))

        en_spd = read_rate('rate', _d.get('rate', 50))
        ar_spd = read_rate('arabic_rate', _d.get('arabic_rate', 30))
        de_spd = read_rate('german_rate', _d.get('german_rate', 30))
        self._en_scale.set_value(en_spd)
        self._ar_scale.set_value(ar_spd)
        self._de_scale.set_value(de_spd)
        self._en_speed_lbl.set_label(f'+{en_spd}%  ({(100+en_spd)/100:.1f}×)')
        self._ar_speed_lbl.set_label(f'+{ar_spd}%  ({(100+ar_spd)/100:.1f}×)')
        self._de_speed_lbl.set_label(f'+{de_spd}%  ({(100+de_spd)/100:.1f}×)')

        # Source language
        saved_src = read_setting('source_language', _d.get('source_language', 'auto'))
        src_idx = next((i for i, (code, _) in enumerate(SOURCE_LANGUAGES) if code == saved_src), 0)
        self._source_lang_combo.set_selected(src_idx)

        # Translation
        trans_enabled = read_bool_setting('translate_enabled', _d.get('translate_enabled', False))
        self._trans_enabled.set_active(trans_enabled)
        self._on_trans_enabled_changed(self._trans_enabled, trans_enabled)

        prov_saved = read_setting('translate_provider', _d.get('translate_provider', 'deepl'))
        prov_idx = next((i for i, (code, _) in enumerate(TRANSLATION_PROVIDERS) if code == prov_saved), 0)
        self._trans_provider_combo.set_selected(prov_idx)

        tgt_saved = read_setting('translate_target', _d.get('translate_target', ''))
        tgt_idx = next((i for i, (code, _) in enumerate(TRANSLATION_LANGUAGES) if code == tgt_saved), 0)
        self._trans_target_combo.set_selected(tgt_idx)

        self._trans_api_entry.set_text(read_setting('translate_api_key', _d.get('translate_api_key', '')))

    # ── State machine ─────────────────────────────────────────────────────────

    def _set_state(self, state: AppState):
        self._state = state
        label, css, pause_on, icon, status = self._STATE_UI[state]

        self._primary_btn.set_label(label)
        for cls in ('suggested-action', 'destructive-action'):
            self._primary_btn.remove_css_class(cls)
        self._primary_btn.add_css_class(css)
        self._primary_btn.set_sensitive(True)   # always re-enable after any state change

        self._pause_btn.set_sensitive(pause_on)
        self._status_lbl.set_label(f'{icon}  {status}')

        if state == AppState.IDLE:
            self._is_paused = False
            self._pause_btn.set_label('⏸  Pause')
            # Only show save button if we actually have audio
            self._save_btn.set_visible(self._has_audio)
        elif state == AppState.GENERATING:
            self._has_audio = False
            self._save_btn.set_visible(False)
            _notify('TTS: Generating audio…',
                    'Converting text to speech…',
                    'audio-speakers')
        elif state == AppState.RETRYING:
            self._has_audio = False
            self._save_btn.set_visible(False)
            _notify('TTS: Retrying network…',
                    'Connection issue — trying again…',
                    'network-error')
        elif state == AppState.PLAYING:
            self._has_audio = True
            self._snapshot_segments()
            _notify('TTS: Playing',
                    'Audio is now playing',
                    'audio-speakers')

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_primary(self, _btn):
        if self._state == AppState.IDLE:
            # Disable button immediately to prevent double-click during async grab
            self._primary_btn.set_sensitive(False)
            threading.Thread(target=self._async_grab_then_speak, daemon=True).start()
        else:
            self._manager.kill()

    def _on_grab_clicked(self, _btn):
        threading.Thread(target=self._async_grab_preview_only, daemon=True).start()

    def _on_pause_resume(self, _btn):
        # Uses send_mpv (async socket) — never touches subprocess on main thread
        self._is_paused = not self._is_paused
        self._pause_btn.set_label('▶  Resume' if self._is_paused else '⏸  Pause')
        self._manager.send_mpv(['cycle', 'pause'])

    def _on_speed_changed(self, scale, lbl):
        val = int(scale.get_value())
        mpv_speed = (100 + val) / 100
        lbl.set_label(f'+{val}%  ({mpv_speed:.1f}×)')
        # NOTE: Per-language rates only affect edge-tts generation.
        # Live playback speed is controlled solely by global speed slider.

    def _on_trans_enabled_changed(self, switch, state):
        self._trans_provider_combo.set_sensitive(state)
        self._trans_target_combo.set_sensitive(state)
        self._trans_api_entry.set_sensitive(state)
        return False  # let GTK propagate the state change

    # ── Async selection helpers ───────────────────────────────────────────────

    def _async_grab_then_speak(self):
        """Background thread: grab text, then hand off to main loop."""
        text = get_selection()
        GLib.idle_add(self._on_text_ready_for_speaking, text)

    def _async_grab_preview_only(self):
        """Background thread: grab text and update preview only."""
        text = get_selection()
        GLib.idle_add(self._update_preview, text)

    def _on_text_ready_for_speaking(self, text: str) -> bool:
        """Called on main loop after async selection grab."""
        self._update_preview(text)
        # Re-enable button now that we have the text (or didn't get any)
        if not text or self._state != AppState.IDLE:
            self._primary_btn.set_sensitive(True)
            return GLib.SOURCE_REMOVE
        if len(text) > MAX_CHARS:
            self._primary_btn.set_sensitive(True)
            self._show_char_limit_warning(len(text))
            return GLib.SOURCE_REMOVE
        # _start_speaking calls _set_state(GENERATING) which re-enables the button
        self._start_speaking(text)
        return GLib.SOURCE_REMOVE

    def _update_preview(self, text: str) -> bool:
        self._tbuf.set_text(
            text if text else '(Nothing selected — highlight some text first.)')
        n = len(text)
        if n > 0:
            color = 'error' if n > MAX_CHARS else 'dim-label'
            self._char_lbl.set_label(f'{n:,} / {MAX_CHARS:,} characters')
            self._char_lbl.set_css_classes(['caption', color])
        else:
            self._char_lbl.set_label('')
        return GLib.SOURCE_REMOVE

    # ── Core action ───────────────────────────────────────────────────────────

    def _start_speaking(self, text: str):
        en_idx   = self._en_combo.get_selected()
        ar_idx   = self._ar_combo.get_selected()
        de_idx   = self._de_combo.get_selected()
        en_voice = self.config['voices']['english'][en_idx]['id']
        ar_voice = self.config['voices']['arabic'][ar_idx]['id']
        de_voice = self.config['voices']['german'][de_idx]['id']
        en_rate  = f"+{int(self._en_scale.get_value())}%"
        ar_rate  = f"+{int(self._ar_scale.get_value())}%"
        de_rate  = f"+{int(self._de_scale.get_value())}%"

        src_lang = SOURCE_LANGUAGES[self._source_lang_combo.get_selected()][0]
        trans_enabled = 'yes' if self._trans_enabled.get_active() else 'no'
        trans_provider = TRANSLATION_PROVIDERS[self._trans_provider_combo.get_selected()][0]
        trans_target = TRANSLATION_LANGUAGES[self._trans_target_combo.get_selected()][0]
        trans_key = self._trans_api_entry.get_text()

        self._save_settings(en_idx, ar_idx, de_idx, src_lang, trans_enabled, trans_provider, trans_target, trans_key)
        self._set_state(AppState.GENERATING)   # instant feedback before first STATUS line

        cmd = [
            'bash', SPEAK_SH,
            '--text',     text,
            '--en-voice', en_voice,
            '--ar-voice', ar_voice,
            '--de-voice', de_voice,
            '--en-rate',  en_rate,
            '--ar-rate',  ar_rate,
            '--de-rate',  de_rate,
            '--source-lang', src_lang,
            '--translate-enabled', trans_enabled,
            '--translate-provider', trans_provider,
        ]
        if trans_target:
            cmd += ['--translate-target', trans_target]
        if trans_key:
            cmd += ['--translate-api-key', trans_key]
        self._manager.speak(cmd)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_wayland_clipboard(self) -> bool:
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
        return GLib.SOURCE_REMOVE

    def _save_settings(self, en_idx: int, ar_idx: int, de_idx: int,
                       src_lang: str = None,
                       trans_enabled: str = None,
                       trans_provider: str = None,
                       trans_target: str = None,
                       trans_key: str = None):
        """Persist all selections to ~/.config/tts_settings (single source of truth)."""
        _d = _SHARED.get('defaults', {})
        if src_lang is None:
            src_lang = _d.get('source_language', 'auto')
        if trans_enabled is None:
            trans_enabled = 'yes' if _d.get('translate_enabled', False) else 'no'
        if trans_provider is None:
            trans_provider = _d.get('translate_provider', 'deepl')
        if trans_target is None:
            trans_target = _d.get('translate_target', '')
        if trans_key is None:
            trans_key = _d.get('translate_api_key', '')
        en_rate = int(self._en_scale.get_value())
        ar_rate = int(self._ar_scale.get_value())
        de_rate = int(self._de_scale.get_value())
        en_voice = self.config['voices']['english'][en_idx]['id']
        ar_voice = self.config['voices']['arabic'][ar_idx]['id']
        de_voice = self.config['voices']['german'][de_idx]['id']
        settings = {
            'voice':        en_voice,
            'arabic_voice': ar_voice,
            'german_voice': de_voice,
            'rate':         f'+{en_rate}%',
            'arabic_rate':  f'+{ar_rate}%',
            'german_rate':  f'+{de_rate}%',
            'source_language': src_lang,
            'translate_enabled': trans_enabled,
            'translate_provider': trans_provider,
            'translate_target': trans_target,
            'translate_api_key': trans_key,
        }
        try:
            os.makedirs(SHELL_CFG_DIR, exist_ok=True)
            for name, value in settings.items():
                with open(os.path.join(SHELL_CFG_DIR, name), 'w') as f:
                    f.write(value)
        except OSError:
            pass

    @staticmethod
    def _snapshot_segments():
        import glob
        try:
            shutil.rmtree(SAVED_DIR, ignore_errors=True)
            os.makedirs(SAVED_DIR, exist_ok=True)
            for seg in sorted(glob.glob(f'{WORK_DIR}/seg_*.mp3')):
                shutil.copy(seg, SAVED_DIR)
        except OSError:
            pass

    def _on_save_audio(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title('Save Audio')
        dialog.set_initial_name('tts_output.mp3')
        filter_mp3 = Gtk.FileFilter()
        filter_mp3.add_suffix('mp3')
        filter_mp3.set_name('MP3 audio')
        dialog.set_default_filter(filter_mp3)
        dialog.save(self, None, self._on_save_dialog_result)

    def _on_save_dialog_result(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file is None:
                return
            dest = file.get_path()
            # Concatenate all segment MP3s to the destination.
            # Prefer the snapshot dir (immune to speak.sh's work-dir cleanup).
            segments = sorted(glob.glob(f'{SAVED_DIR}/seg_*.mp3'))
            if not segments:
                segments = sorted(glob.glob(f'{WORK_DIR}/seg_*.mp3'))
            if not segments:
                self._show_error('No audio files found to save.')
                return
            
            # Validate that all segment files exist and are readable
            valid_segments = []
            for seg in segments:
                if os.path.isfile(seg) and os.access(seg, os.R_OK) and os.path.getsize(seg) > 0:
                    valid_segments.append(seg)
                else:
                    print(f"Warning: Skipping invalid segment file: {seg}")
            
            if not valid_segments:
                self._show_error('No valid audio files found to save.')
                return
                
            if len(valid_segments) == 1:
                shutil.copy(valid_segments[0], dest)
            else:
                # Use ffmpeg concat if available, else cat (best-effort)
                ffmpeg = shutil.which('ffmpeg')
                if ffmpeg:
                    with tempfile.NamedTemporaryFile(
                            'w', suffix='.txt', delete=False) as f:
                        list_file = f.name
                        for seg in valid_segments:
                            f.write(f"file '{seg}'\n")
                    try:
                        subprocess.run([ffmpeg, '-y', '-f', 'concat', '-safe', '0',
                                        '-i', list_file, '-c', 'copy', dest],
                                       capture_output=True, check=True)
                    finally:
                        os.remove(list_file)
                else:
                    # Fallback: cat MP3s (works in most players for sequential files)
                    with open(dest, 'wb') as out:
                        for seg in valid_segments:
                            with open(seg, 'rb') as inp:
                                out.write(inp.read())
            self._show_notification(f'Saved audio to {dest}')
        except Exception as e:
            self._show_error(f'Failed to save audio: {e}')

    def _on_open_folder(self, _btn):
        cache_dir = os.path.expanduser('~/.cache/speak-aloud')
        try:
            os.makedirs(cache_dir, exist_ok=True)
            subprocess.run(['xdg-open', cache_dir], check=False)
        except Exception as e:
            self._show_error(f'Failed to open folder: {e}')

    def _on_clear_cache(self, _btn):
        cache_dir = os.path.expanduser('~/.cache/speak-aloud')
        try:
            count = 0
            for f in os.listdir(cache_dir):
                if f.endswith('.mp3'):
                    os.remove(os.path.join(cache_dir, f))
                    count += 1
            self._show_notification(f'Cleared {count} cached audio files')
        except Exception as e:
            self._show_error(f'Failed to clear cache: {e}')

    def _show_notification(self, message: str) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self, heading='Speak a Loud', body=message)
        dialog.add_response('ok', 'OK')
        dialog.present()

    def _show_error(self, message: str) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self, heading='TTS Error', body=message)
        dialog.add_response('ok', 'OK')
        dialog.add_response('retry', 'Retry')
        dialog.set_response_appearance('retry', Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == 'retry':
                text = self._tbuf.get_text(
                    self._tbuf.get_start_iter(),
                    self._tbuf.get_end_iter(), False,
                )
                # Only retry if there's actual text (not the placeholder)
                if text and not text.startswith('(Nothing selected'):
                    self._on_text_ready_for_speaking(text)
            dialog.destroy()

        dialog.connect('response', on_response)
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

    def _quit_app(self):
        self._manager.shutdown()
        self.get_application().quit()

    # ── Override close to hide to tray ────────────────────────────────────────

    def _on_close_request(self, _win) -> bool:
        self._manager.shutdown()
        return False


# ─────────────────────────────────────────────────────────────────────────────

class TTSApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.speakaloud')
        self.connect('activate', self._on_activate)

    def _on_activate(self, _app):
        TTSWindow(application=self).present()


if __name__ == '__main__':
    TTSApp().run(sys.argv)
