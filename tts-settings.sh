#!/bin/bash

CONFIG_DIR="$HOME/.config/tts_settings"

# Load current settings with fallbacks
CURRENT_VOICE=$(cat    "$CONFIG_DIR/voice"         2>/dev/null || echo "en-US-ChristopherNeural")
CURRENT_AR_VOICE=$(cat "$CONFIG_DIR/arabic_voice"  2>/dev/null || echo "ar-SA-HamedNeural")
CURRENT_RATE=$(cat     "$CONFIG_DIR/rate"           2>/dev/null | tr -d '+%')
CURRENT_AR_RATE=$(cat  "$CONFIG_DIR/arabic_rate"   2>/dev/null | tr -d '+%')
[ -z "$CURRENT_RATE" ]    && CURRENT_RATE=50
[ -z "$CURRENT_AR_RATE" ] && CURRENT_AR_RATE=30

# Build voice lists with current value first so it appears pre-selected
EN_VOICES="$CURRENT_VOICE!en-US-ChristopherNeural!en-GB-RyanNeural!en-US-GuyNeural"
AR_VOICES="$CURRENT_AR_VOICE!ar-SA-HamedNeural!ar-SA-ZariyahNeural!ar-EG-SalmaNeural"

RESULTS=$(yad --title="TTS Settings" --form --width=450 \
    --field="English Voice:CB"              "$EN_VOICES" \
    --field="Arabic Voice:CB"               "$AR_VOICES" \
    --field="English Speed (+%):HSCALE"     "$CURRENT_RATE" \
    --field="Arabic Speed (+%):HSCALE"      "$CURRENT_AR_RATE" \
    --field="Custom Voice ID (optional):TEXT" "" \
    --button="Save":0 --button="Cancel":1)

if [ $? -eq 0 ]; then
    EN_VOICE=$(echo    "$RESULTS" | cut -d'|' -f1)
    AR_VOICE=$(echo    "$RESULTS" | cut -d'|' -f2)
    EN_RATE=$(echo     "$RESULTS" | cut -d'|' -f3 | cut -d'.' -f1)
    AR_RATE=$(echo     "$RESULTS" | cut -d'|' -f4 | cut -d'.' -f1)
    CUSTOM_VOICE=$(echo "$RESULTS" | cut -d'|' -f5)

    # Custom voice ID overrides the English voice dropdown if filled in
    [ -n "$CUSTOM_VOICE" ] && EN_VOICE="$CUSTOM_VOICE"

    echo "$EN_VOICE"     > "$CONFIG_DIR/voice"
    echo "$AR_VOICE"     > "$CONFIG_DIR/arabic_voice"
    echo "+${EN_RATE}%"  > "$CONFIG_DIR/rate"
    echo "+${AR_RATE}%"  > "$CONFIG_DIR/arabic_rate"

    notify-send "TTS Updated" "EN: $EN_VOICE (+${EN_RATE}%) | AR: $AR_VOICE (+${AR_RATE}%)"
fi
