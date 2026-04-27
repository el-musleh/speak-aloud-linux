# Contributing to Speak a Loud Universal

Thank you for your interest in improving Speak a Loud! We follow a structured development process to ensure stability across both the Python UI and Bash backend.

## 📐 Development Principles

1.  **Non-Blocking UI:** Always perform I/O (sockets, files, subprocesses) in background threads. Use `GLib.idle_add` to sync results back to the GTK main loop.
2.  **Surgical Scripting:** Keep `speak.sh` lightweight. It should be usable as a standalone CLI tool without any GUI dependencies.
3.  **Process Integrity:** Always clean up child processes. If you launch a subprocess, ensure it is part of a process group that is killed on exit.

## 🏷️ Semantic Versioning (SemVer)

We strictly adhere to [Semantic Versioning 2.0.0](https://semver.org/). Version numbers follow the `MAJOR.MINOR.PATCH` format:

-   **MAJOR (`1.0.0`):** Significant architectural changes or breaking IPC changes. If a change requires users to manually update their keyboard shortcut commands, it's a MAJOR update.
-   **MINOR (`0.1.0`):** New features that are backwards-compatible. For example, adding support for a new TTS engine or a new UI theme.
-   **PATCH (`0.0.1`):** Backwards-compatible bug fixes, performance improvements, or documentation updates.

## 🛠️ Testing Your Changes

Before submitting a pull request, please verify:

```bash
# Check shell scripts for syntax errors
bash -n *.sh

# Check Python app for syntax errors
python3 -m py_compile tts-app.py
```

### Manual Test Suite:
1.  **Bilingual Switch:** Test with text containing both Arabic and English.
2.  **Real-time Speed:** Adjust the GUI slider while audio is playing.
3.  **Shortcut Sync:** Change settings in the GUI, close it, and then run `speak.sh` to confirm the settings persisted.
