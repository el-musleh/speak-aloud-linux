# Speak a Loud Universal

A production-grade Text-to-Speech (TTS) solution for Linux with seamless trilingual (English, Arabic, and German) support. Speak a Loud Universal allows you to highlight text anywhere on your screen and hear it spoken aloud using high-quality neural voices from Microsoft Edge, with zero API keys required.

## 🚀 Features

- **Trilingual Intelligence:** Automatically detects English, Arabic, and German segments within the same text and switches voices seamlessly — Arabic by script, German by word-level analysis (umlauts and vocabulary markers).
- **Modern GTK4 UI:** A polished, native Linux interface built with Python and Libadwaita for voice selection, per-language speed control, and text preview.
- **System Tray:** Optional tray icon (via `pystray`) with play/pause, stop, seek (±10s), and playback speed presets — the app keeps playing when the window is closed.
- **Audio Caching:** Generated segments are cached in `~/.cache/speak-aloud` (keyed by voice + rate + text), so repeated text plays instantly. Stale entries are pruned automatically after 30 days; a toolbar button clears the cache manually.
- **Parallel Generation:** All segments are synthesized concurrently with automatic retry on connection issues and rate limits.
- **Save Audio:** Export the last playback as a single MP3 from the GUI, or pass `--output file.mp3` to `speak.sh`.
- **Global Shortcuts:** Deep system integration with global keyboard shortcuts (Super+S to speak, Super+P to pause, Shift+Super+S to stop).
- **Real-time Speed Control:** Adjust playback speed on-the-fly without restarting the audio, including a global speed slider shared between GUI and shortcuts.
- **Single Source of Truth:** All settings live in `~/.config/tts_settings/` — the GUI, the CLI settings dialog, and the keyboard-shortcut script always agree.
- **Wayland & X11 Support:** Works across different display servers using `wl-clipboard` and `xsel`.
- **High-Quality Neural Voices:** Uses the `edge-tts` engine for natural-sounding speech.
- **Minimal Footprint:** Fast, lightweight, and uses standard system components like `mpv`.

## 🛠️ Dependencies

The project relies on several system-level packages. The included `install.sh` script will attempt to install these for you on Debian/Ubuntu-based systems (like Linux Mint).

### Local Dependencies
- **mpv** - Included locally in `bin/` directory (no system installation required)

### System Packages
- **Python 3** & **PyGObject** (`python3-gi`, `python3-gi-cairo`)
- **Libadwaita** (`gir1.2-adw-1`, `gir1.2-gtk-4.0`)
- **edge-tts:** The core neural speech engine (installed via `pipx`).
- **xsel** / **wl-clipboard:** For reading the primary selection (highlighted text).
- **socat:** For Inter-Process Communication with the audio player.
- **yad:** (Optional) For the legacy CLI-based settings dialog.
- **pystray** + **Pillow:** (Optional) For the system-tray icon; the GUI degrades gracefully without them.
- **ffmpeg:** (Optional) For gapless MP3 export with "Save Audio" / `--output`.

Install manually if needed:
```bash
sudo apt install xsel yad socat wl-clipboard python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-pil
python3 -m pip install --user pystray
```

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/speak-aloud-linux.git ~/speak-aloud-linux
cd ~/speak-aloud-linux

# Run the installer
chmod +x install.sh
./install.sh
```

The installer handles system packages, `edge-tts` setup via `pipx`, configuration defaults, file permissions, and (with your confirmation) keyboard shortcuts.

## ⌨️ Keyboard Shortcuts

### Automated Setup (Cinnamon / Linux Mint)

The installer asks whether to register the keyboard shortcuts automatically. Answer `Y` and all five shortcuts below are configured for you — re-running the installer updates them in place without creating duplicates.

### Manual Setup (other desktops)

If you skipped the automated setup or use a different desktop environment, add these custom shortcuts manually (e.g., Mint Menu → System Settings → Keyboard → Shortcuts):

| Action | Command | Recommended Shortcut |
| :--- | :--- | :--- |
| **Speak Selection** | `./speak.sh` | `Super + S` |
| **Pause / Resume** | `./speak-pause.sh` | `Super + P` |
| **Stop Speech** | `./speak-stop.sh` | `Shift + Super + S` |
| **TTS Settings (CLI)** | `./tts-settings.sh` | `Super + T` |
| **Open GUI App** | `python3 tts-app.py` | `Super + A` |

**Note:** Automated setup only works with the Cinnamon desktop environment. Use absolute paths to the scripts when configuring shortcuts manually. `speak-stop.sh` stops only this app's playback via its IPC socket — it never touches other mpv instances (e.g., a video you're watching).

A standalone `setup-tts-shortcuts.sh` is also provided to (re)register just the Speak/Stop shortcuts; it is idempotent and updates existing entries by name.

## 🖥️ Usage

### Using the GUI
Launch the app with `python3 tts-app.py`. Highlight any text on your screen, then click the **↺ Refresh** button to preview it, or hit **Speak** to start playback. Per-language rate sliders (English/Arabic/German) and a global playback-speed slider can be adjusted live during playback. After playback, a **Save Audio** button exports the result as MP3. Closing the window hides the app to the system tray (if available) without stopping playback.

### Using the Shortcut
Highlight text in any application (browser, PDF viewer, terminal) and press your assigned shortcut (`Super + S`). The script detects the languages and starts speaking immediately. Pressing it again while audio is playing stops the old playback and starts the new selection.

### CLI options (`speak.sh`)
```bash
./speak.sh --text "Hello مرحبا Grüße"          # speak explicit text
./speak.sh --output out.mp3                    # also export concatenated audio
./speak.sh --en-voice en-GB-RyanNeural \
           --de-rate "+40%" --speed 1.25       # one-off overrides
```

### Settings architecture
All user settings are plain files in `~/.config/tts_settings/` (`voice`, `arabic_voice`, `german_voice`, `rate`, `arabic_rate`, `german_rate`, `global_speed`). The GUI, `tts-settings.sh`, and `speak.sh` read and write the same files — `config.json` only holds the voice catalog.

## ❓ Troubleshooting

### "Namespace Gtk not available for version 4.0"
If you see this error when running `tts-app.py`, it means the GTK 4 introspection libraries are missing. Fix it by running:
```bash
sudo apt update
sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1
```

### Wayland Selection Issues
If you are on Wayland and the app cannot grab highlighted text, ensure `wl-clipboard` is installed:
```bash
sudo apt install wl-clipboard
```

### Missing mpv dependency
If you see "TTS Error: Missing dependency: mpv", verify the local binary exists:
```bash
ls -la bin/mpv
```
The mpv binary is included locally in the `bin/` directory and should be automatically used by `speak.sh`.

---

*Powered by Microsoft Edge TTS and mpv.*
