#!/bin/bash

# Load current settings
CURRENT_VOICE=$(cat ~/.config/tts_settings/voice)
CURRENT_ARABIC_VOICE=$(cat ~/.config/tts_settings/arabic_voice 2>/dev/null || echo "ar-SA-HamedNeural")
CURRENT_RATE=$(cat ~/.config/tts_settings/rate | tr -d '+%')

# Open the GUI
RESULTS=$(yad --title="TTS Settings" --form --width=400 \
    --field="English Voice:CB" "en-US-ChristopherNeural!en-GB-RyanNeural!en-US-GuyNeural" \
    --field="Arabic Voice:CB" "ar-SA-HamedNeural!ar-SA-ZariyahNeural!ar-EG-SalmaNeural" \
    --field="Playback Speed (+%):HSCALE" "$CURRENT_RATE" \
    --button="Save":0 --button="Cancel":1)

# If user clicked Save
if [ $? -eq 0 ]; then
    # Extract data from Yad output (Pipe separated)
    VOICE=$(echo $RESULTS | cut -d'|' -f1)
    ARABIC_VOICE=$(echo $RESULTS | cut -d'|' -f2)
    RATE=$(echo $RESULTS | cut -d'|' -f3)

    # Save to config files
    echo "$VOICE" > ~/.config/tts_settings/voice
    echo "$ARABIC_VOICE" > ~/.config/tts_settings/arabic_voice
    echo "+${RATE}%" > ~/.config/tts_settings/rate

    notify-send "TTS Updated" "EN: $VOICE | AR: $ARABIC_VOICE | Speed: +${RATE}%"
fi
