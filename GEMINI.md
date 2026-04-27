# Speak a Loud Universal - Project Context

Speak a Loud Universal is a specialized Text-to-Speech (TTS) toolkit for Linux, optimized for bilingual (English and Arabic) environments. It provides high-quality neural speech synthesis without requiring API keys, using `edge-tts` (Microsoft Edge neural voices).

## Project Overview

The project is a hybrid of Python and Bash, providing two main interaction patterns:
1.  **GUI Mode:** A modern GTK4/Libadwaita application (`tts-app.py`) for previewing text, selecting voices, and adjusting speed in real-time.
2.  **Shortcut Mode:** Minimalist shell scripts (`speak.sh`, `speak-pause.sh`) intended to be bound to global keyboard shortcuts for instant reading of highlighted text.

### Core Technologies
- **Speech Engine:** `edge-tts` (Python)
- **Playback & Control:** `mpv` with Unix IPC socket support (`/tmp/mpvsocket`).
- **GUI Framework:** GTK4 + Libadwaita (via PyGObject/`gi`).
- **Text Processing:** Python-based regex segmentation for English/Arabic detection.
- **System Integration:** `xsel` (X11) and `wl-clipboard` (Wayland) for clipboard access; `socat` for IPC.

## Architecture

- **`speak.sh`**: The central orchestration script.
    - Segments input text into language-specific blocks.
    - In **Shortcut Mode**, it generates and plays audio segments sequentially.
    - In **GUI Mode** (triggered by `--text`), it generates all segments first, then starts a single `mpv` instance with an IPC server to allow real-time control from the Python app.
- **`tts-app.py`**: The primary user interface.
    - Uses a `TTSManager` to manage the lifecycle of `speak.sh` subprocesses.
    - Communicates with `mpv` via JSON-IPC to handle pausing and real-time speed adjustments.
    - Implements asynchronous clipboard grabbing to prevent UI freezes.
- **`config.json`**: Central repository for available voices and default settings.
- **`install.sh`**: Handles system dependency resolution (`apt`), Python package management (`pipx`), and initial configuration.

## Building and Running

### Installation
```bash
chmod +x install.sh
./install.sh
```

### Running the Application
- **Main GUI:** `python3 tts-app.py`
- **CLI/Shortcut:** `./speak.sh` (Reads current selection)
- **Toggle Pause:** `./speak-pause.sh`
- **Legacy Settings:** `./tts-settings.sh` (Requires `yad`)

## Development Conventions

- **Concurrency:** Never block the GTK main loop. Use `threading.Thread` for I/O bound tasks (clipboard, subprocess, socket) and `GLib.idle_add` to update the UI from background threads.
- **Process Management:** Use `os.killpg` with `signal.SIGKILL` to ensure that `speak.sh` and its child processes (`edge-tts`, `mpv`) are fully terminated when a new speech request is made or the app closes.
- **IPC:** Playback control must be performed by sending JSON-formatted commands to `/tmp/mpvsocket`.
- **Language Detection:** The project uses a specific Unicode-range regex for Arabic (`[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]`). Any segmenting logic should respect this to ensure correct voice assignment.
- **Configuration Persistence:**
    - Python settings are saved to `config.json`.
    - Shell scripts read settings from `~/.config/tts_settings/`.
    - `tts-app.py` is responsible for syncing its internal state to the shell config files during speech generation.
