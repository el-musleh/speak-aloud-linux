#!/bin/bash

# 1. Kill previous audio
pkill -f mpv

# 2. Get text
TEXT=$(xsel -p)
[ -z "$TEXT" ] && exit

# 3. Get settings — auto-detect Arabic Unicode block (U+0600–U+06FF)
RATE=$(cat ~/.config/tts_settings/rate)
if printf '%s' "$TEXT" | grep -qP '[\x{0600}-\x{06FF}]'; then
    VOICE=$(cat ~/.config/tts_settings/arabic_voice 2>/dev/null || echo "ar-SA-HamedNeural")
else
    VOICE=$(cat ~/.config/tts_settings/voice)
fi

# 4. Generate and Play
AUDIO_FILE="/tmp/tts_output.mp3"
edge-tts --voice "$VOICE" --rate="$RATE" --text "$TEXT" --write-media "$AUDIO_FILE"
mpv "$AUDIO_FILE" --no-terminal
