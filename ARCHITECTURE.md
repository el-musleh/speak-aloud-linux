# System Architecture

Speak a Loud Universal is designed as a decoupled system where a Python-based GUI acts as an orchestrator for a set of Bash-based worker scripts. This architecture ensures that the core speech logic can be used both as a standalone CLI tool and as part of a rich graphical application.

## 🧱 Component Overview

### 1. The Frontend (`tts-app.py`)
Built using **GTK4** and **Libadwaita**, the frontend manages the user's configuration and provides a controlled environment for generating and playing speech.
- **State Machine:** Manages three states: `IDLE`, `GENERATING`, and `PLAYING`.
- **TTSManager:** A dedicated class that handles the lifecycle of the backend process. It uses `subprocess.Popen` with a new process group to ensure clean termination of all child processes (like `mpv` and `edge-tts`).
- **Asynchronous I/O:** Clipboard grabbing and stdout reading are performed in background threads to keep the UI responsive.

### 2. The Orchestrator (`speak.sh`)
This script is the "brain" of the operation. It handles:
- **Language Detection:** Uses a Python regex bridge to split text into English and Arabic segments.
- **Speech Generation:** Calls `edge-tts` to convert text segments into MP3 files in `/tmp/tts_work/`.
- **Audio Routing:** Depending on the mode (GUI vs. Shortcut), it either plays files sequentially or launches `mpv` with an IPC server.

### 3. The Audio Engine (`mpv`)
`mpv` is used not just for playback, but as a controllable server. By launching with `--input-ipc-server=/tmp/mpvsocket`, it allows the Python app (or other scripts) to:
- Cycle pause/resume.
- Change playback speed in real-time using JSON-IPC commands.

## 📡 Inter-Process Communication (IPC)

The system uses three primary IPC methods:
1.  **CLI Arguments:** `tts-app.py` passes user settings (voices, rates) to `speak.sh` via command-line flags.
2.  **Stdout Streams:** `speak.sh` emits `STATUS:GENERATING` and `STATUS:PLAYING` messages. The Python app parses these in real-time to update the UI buttons and status labels.
3.  **Unix Sockets:** Real-time playback control (speed/pause) is handled via the `mpv` JSON-IPC socket at `/tmp/mpvsocket`.

## 📂 File System Usage

- **`/tmp/tts_work/`**: Temporary storage for generated MP3 segments and language metadata.
- **`/tmp/mpvsocket`**: The Unix socket for `mpv` control.
- **`~/.config/tts_settings/`**: Persistent storage for voice and rate preferences (used by the shortcut mode).
- **`config.json`**: UI-specific configuration and voice database.

## 🔄 Execution Flow (GUI Mode)

1.  User clicks **Speak**.
2.  `tts-app.py` kills any existing `speak.sh` process group.
3.  `tts-app.py` launches `bash speak.sh --text "..." --en-voice "..." ...`.
4.  `speak.sh` outputs `STATUS:GENERATING`.
5.  `speak.sh` runs `edge-tts` for each segment.
6.  `speak.sh` outputs `STATUS:PLAYING` and launches `mpv`.
7.  `tts-app.py` detects the socket and sends the initial speed command.
8.  User moves a slider; `tts-app.py` sends a `set_property speed` command to the socket.
9.  Playback ends; `mpv` exits; `speak.sh` exits; `tts-app.py` returns to `IDLE`.
