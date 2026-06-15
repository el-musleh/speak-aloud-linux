# System Architecture

Speak a Loud Universal is a shell-first TTS system. The core logic lives entirely in Bash scripts, with `speak.sh` acting as the orchestrator. A lightweight YAD-based settings dialog (`tts-settings.sh`) provides configuration, while keyboard shortcuts offer instant access from anywhere on the desktop.

## 🧱 Component Overview

### 1. The Orchestrator (`speak.sh`)
This script is the "brain" of the operation. It handles:
- **Language Detection:** Uses a Python regex bridge to split text into English, Arabic, and German segments.
- **Speech Generation:** Calls `edge-tts` to convert text segments into MP3 files in `/tmp/speak-aloud-work/`.
- **Audio Routing:** Progressive playback — starts `mpv` as soon as the first segment is ready and appends remaining segments via IPC while generation continues.

### 2. The Settings GUI (`tts-settings.sh`)
A YAD-based form for selecting voices, adjusting per-language rates, configuring translation, and setting pause-at-punctuation options. All values are written to `~/.config/tts_settings/` so `speak.sh` sees them immediately.

### 3. The Audio Engine (`mpv`)
`mpv` is used not just for playback, but as a controllable server. By launching with `--input-ipc-server=/tmp/speak-aloud-mpv.sock`, other scripts can:
- Cycle pause/resume (`speak-pause.sh`).
- Stop playback (`speak-stop.sh`).

## 📡 Inter-Process Communication (IPC)

The system uses three primary IPC methods:
1.  **CLI Arguments:** `tts-settings.sh` and keyboard shortcuts pass user settings to `speak.sh` via command-line flags.
2.  **Unix Sockets:** Playback control (pause/stop/seek) is handled via the `mpv` JSON-IPC socket at `/tmp/speak-aloud-mpv.sock`.
3.  **Status File:** `speak.sh` writes its current state (`IDLE`, `GENERATING`, `PLAYING`, `PAUSED`) to `/tmp/tts-status`, which the tray daemon polls to update its icon, send notifications, and activate media-key listeners.

## 📂 File System Usage

- **`/tmp/speak-aloud-work/`**: Temporary storage for generated MP3 segments and language metadata.
- **`/tmp/speak-aloud-mpv.sock`**: The Unix socket for `mpv` control.
- **`~/.config/tts_settings/`**: Persistent storage for voice, rate, and pause preferences.
- **`tts-shared.json`**: Shared voice catalog and default settings (read by both `tts-settings.sh` and `speak.sh`).
