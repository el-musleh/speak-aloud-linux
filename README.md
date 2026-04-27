# Linux Text-to-Speech with Speed Control
### Speak a Loud Universal

Highlight any text on screen, press a keyboard shortcut, and hear it spoken aloud. Automatically switches between English and Arabic voices based on the script detected in the selected text.

---

## 1. Install System Dependencies

Open your terminal and run:

```bash
sudo apt update
sudo apt install pipx mpv xsel yad
pipx ensurepath
```

> **Note:** After running `pipx ensurepath`, close your terminal and open a new one so the path changes take effect.

---

## 2. Install the TTS Engine

```bash
pipx install edge-tts
```

This uses Microsoft's free neural TTS servers — no API key required.

---

## 3. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/speak-aloud-linux.git ~/speak-aloud-linux
chmod +x ~/speak-aloud-linux/speak.sh ~/speak-aloud-linux/tts-settings.sh
```

---

## 4. Create the Config Files

The scripts read voice and speed settings from `~/.config/tts_settings/`. Run these once to set the defaults:

```bash
mkdir -p ~/.config/tts_settings
echo "en-US-ChristopherNeural" > ~/.config/tts_settings/voice
echo "ar-SA-HamedNeural"       > ~/.config/tts_settings/arabic_voice
echo "+50%"                    > ~/.config/tts_settings/rate
```

---

## 5. How It Works

### `speak.sh`
- Grabs whatever text you have highlighted (primary selection)
- Detects Arabic characters (Unicode block U+0600–U+06FF)
- Picks the matching voice from your config
- Generates an MP3 with `edge-tts` and plays it via `mpv`

### `tts-settings.sh`
Opens a small GUI (powered by `yad`) where you can change:
- **English voice** — e.g. `en-US-ChristopherNeural`, `en-GB-RyanNeural`
- **Arabic voice** — e.g. `ar-SA-HamedNeural`, `ar-SA-ZariyahNeural`
- **Playback speed** — as a percentage offset (e.g. `+50%` = 1.5×)

Settings are saved back to `~/.config/tts_settings/` immediately.

---

## 6. Map Keyboard Shortcuts

Link the scripts to hotkeys so they work anywhere in Linux Mint.

**Open Keyboard Settings:**
Mint Menu → **System Settings** → **Keyboard** → **Shortcuts** tab → **Custom Shortcuts** → **Add custom shortcut**

| Name | Command | Suggested shortcut |
|---|---|---|
| Speak Selection | `/home/YOUR_USERNAME/speak-aloud-linux/speak.sh` | `Super + S` |
| Stop Speech | `pkill -f mpv` | `Super + Shift + S` |
| TTS Settings | `/home/YOUR_USERNAME/speak-aloud-linux/tts-settings.sh` | `Super + T` |

Replace `YOUR_USERNAME` with your actual Linux username (run `whoami` if unsure).

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

To browse all available voices:

```bash
edge-tts --list-voices
```
