# Speak a Loud Universal

A production-grade Text-to-Speech (TTS) solution for Linux, designed for seamless bilingual (English and Arabic) support. Speak a Loud Universal allows you to highlight text anywhere on your screen and hear it spoken aloud using high-quality neural voices from Microsoft Edge, with zero API keys required.

## 🚀 Features

- **Bilingual Intelligence:** Automatically detects English and Arabic segments within the same text and switches voices seamlessly.
- **Modern GTK4 UI:** A polished, native Linux interface built with Python and Libadwaita for voice selection, speed control, and text preview.
- **Global Shortcuts:** Designed for deep system integration with support for global keyboard shortcuts (Super+S to speak, Super+P to pause).
- **Real-time Speed Control:** Adjust playback speed on-the-fly without restarting the audio.
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

Install manually if needed:
```bash
sudo apt install xsel yad socat wl-clipboard python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
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

The installer handles system packages, `edge-tts` setup via `pipx`, configuration defaults, and file permissions.

## ⌨️ Keyboard Shortcuts

For the best experience, add these custom shortcuts in your desktop environment (e.g., Mint Menu → System Settings → Keyboard → Shortcuts):

| Action | Command | Recommended Shortcut |
| :--- | :--- | :--- |
| **Speak Selection** | `./speak.sh` | `Super + S` |
| **Pause / Resume** | `./speak-pause.sh` | `Super + P` |
| **Stop Speech** | `pkill -f mpv` | `Shift + Super + S` |
| **Open GUI App** | `python3 tts-app.py` | `Super + A` |

### Automated Setup

You can use the included `setup-tts-shortcuts.sh` script to automatically configure the keyboard shortcuts for Cinnamon (Linux Mint default):

```bash
./setup-tts-shortcuts.sh
```

This script will:
- Configure **Speak Selection** (Super + S) to run `./speak.sh`
- Configure **Stop Speech** (Shift + Super + S) to run `pkill -f mpv`

**Note:** This script only works with Cinnamon desktop environment. For other desktop environments, configure shortcuts manually using the table above.

## 🖥️ Usage

### Using the GUI
Launch the app with `python3 tts-app.py`. Highlight any text on your screen, then click the **↺ Refresh** button to preview it, or hit **Speak** to start playback. You can adjust the speed sliders for both English and Arabic independently during playback.

### Using the Shortcut
Highlight text in any application (browser, PDF viewer, terminal) and press your assigned shortcut (`Super + S`). The script will detect the languages and start speaking immediately.

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
