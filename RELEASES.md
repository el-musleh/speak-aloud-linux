# Releases

### [v1.0.0] — 2026-04-27
**"The Stability & Documentation Update"**

This first official release transitions the project from a set of scripts into a production-grade Linux application with full bilingual support and a polished GUI.

#### 🚀 New Features
*   **Bilingual Intelligence:** Automatic detection and voice-switching for mixed Arabic and English text.
*   **Real-time Speed Control:** Adjust playback speed on-the-fly via the GUI sliders without restarting the audio.
*   **Architecture Mapping:** Added full internal documentation (`ARCHITECTURE.md`) explaining the IPC and state machine.

#### ⚡ Improvements
*   **Settings Synchronization:** The GUI app now automatically mirrors your voice and speed choices to your keyboard shortcuts (`speak.sh`).
*   **Threaded I/O:** Moved clipboard grabbing and audio generation to background threads to ensure the UI remains buttery smooth.
*   **Universal Clipboard:** Full support for both X11 (`xsel`) and Wayland (`wl-clipboard`) environments.

#### 🛠️ Bug Fixes
*   **Process Isolation:** Narrowed the `pkill` scope to only target `mpv` instances managed by Speak a Loud, preventing accidental closure of other media players.
*   **Socket Cleanup:** Resolved a "stale socket" bug where the IPC server would fail to bind if a previous session crashed.
*   **Zombie Protection:** Implemented robust process group termination to ensure `edge-tts` and `mpv` always exit cleanly with the main app.
