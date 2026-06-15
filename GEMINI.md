# Speak a Loud Universal - Project Context

Speak a Loud Universal is a specialized Text-to-Speech (TTS) toolkit for Linux, optimized for bilingual (English and Arabic) environments. It provides high-quality neural speech synthesis without requiring API keys, using `edge-tts` (Microsoft Edge neural voices).

## Project Overview

Speak a Loud Universal is a shell-first TTS toolkit with a YAD-based settings GUI. The primary interaction patterns are:
1.  **Keyboard Shortcut:** `speak.sh` reads the current text selection and speaks it immediately.
2.  **Settings GUI:** `tts-settings.sh` (YAD) configures voices, rates, translation, and pauses.
3.  **Tray Daemon:** `tts-daemon.py` provides a cross-desktop tray icon (via `pystray`) with play/pause/stop/seek controls, desktop notifications, structured logging, and optional media-key support (gated to active TTS playback).

### Core Technologies
- **Speech Engine:** `edge-tts` (Python)
- **Playback & Control:** `mpv` with Unix IPC socket support (`/tmp/speak-aloud-mpv.sock`).
- **Settings GUI:** `yad` (shell-based GTK dialog).
- **Text Processing:** Python-based regex segmentation for English/Arabic/German detection.
- **System Integration:** `xsel` (X11) and `wl-clipboard` (Wayland) for clipboard access; `socat` for IPC.

## Architecture

- **`speak.sh`**: The central orchestration script.
    - Segments input text into language-specific blocks.
    - Generates and plays audio segments with progressive playback (starts mpv as soon as the first segment is ready).
    - Supports `--output` for exporting concatenated MP3.
- **`tts-settings.sh`**: The settings GUI.
    - YAD form for voice selection, per-language rate sliders, translation config, and pause-at-punctuation settings.
    - Writes all values to `~/.config/tts_settings/` so `speak.sh` sees them immediately.
- **`tts-shared.json`**: Central repository for available voices and default settings.
- **`install.sh`**: Handles system dependency resolution (`apt`), Python package management (`pipx`), and initial configuration.

## Building and Running

### Installation
```bash
chmod +x install.sh
./install.sh
```

### Running the Application
- **Speak Selection:** `./speak.sh` (reads current selection via keyboard shortcut)
- **Toggle Pause:** `./speak-pause.sh`
- **Stop Speech:** `./speak-stop.sh`
- **Settings:** `./tts-settings.sh` (requires `yad`)

## Development Conventions

- **Process Management:** `speak.sh` uses process groups and flock-based session locking to ensure clean termination of all child processes (`edge-tts`, `mpv`) when a new speech request is made.
- **IPC:** Playback control is performed by sending JSON-formatted commands to `/tmp/speak-aloud-mpv.sock`.
- **Language Detection:** The project uses a specific Unicode-range regex for Arabic (`[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]`). Any segmenting logic should respect this to ensure correct voice assignment.
- **Configuration Persistence:** All settings live as plain files in `~/.config/tts_settings/` — shared between `tts-settings.sh`, `speak.sh`, and the tray daemon.
