# Speak a Loud Universal
Linux Text-to-Speech with automatic English / Arabic detection and speed control.

Highlight any text on screen → press a shortcut → hear it spoken aloud.
No API key required. Uses Microsoft's free neural TTS voices via `edge-tts`.

---

## Quick Setup

```bash
git clone https://github.com/YOUR_USERNAME/speak-aloud-linux.git ~/speak-aloud-linux
cd ~/speak-aloud-linux
chmod +x install.sh
./install.sh
```

The installer handles everything: system packages, `edge-tts`, config files, and script permissions. At the end it prints the exact keyboard shortcut commands to add in Linux Mint.

> **Note:** Re-opening your terminal after install ensures `edge-tts` is on your PATH.

---

## Scripts

| Script | What it does |
|---|---|
| `speak.sh` | Reads highlighted text, auto-detects Arabic vs English, speaks it aloud |
| `tts-settings.sh` | GUI to change English voice, Arabic voice, and playback speed |
| `install.sh` | One-time setup installer |

---

## Available Voices

| Language | Voice ID | Style |
|---|---|---|
| English (US) | `en-US-ChristopherNeural` | Male, clear |
| English (US) | `en-US-GuyNeural` | Male, conversational |
| English (UK) | `en-GB-RyanNeural` | Male, British |
| Arabic (Saudi) | `ar-SA-HamedNeural` | Male |
| Arabic (Saudi) | `ar-SA-ZariyahNeural` | Female |
| Arabic (Egypt) | `ar-EG-SalmaNeural` | Female |

To see all voices: `edge-tts --list-voices`
