#!/bin/bash

CONFIG_DIR="$HOME/.config/tts_settings"

# Load current settings with fallbacks
CURRENT_VOICE=$(cat    "$CONFIG_DIR/voice"         2>/dev/null || echo "en-US-ChristopherNeural")
CURRENT_AR_VOICE=$(cat "$CONFIG_DIR/arabic_voice"  2>/dev/null || echo "ar-SA-HamedNeural")
CURRENT_DE_VOICE=$(cat "$CONFIG_DIR/german_voice" 2>/dev/null || echo "de-DE-ConradNeural")
CURRENT_RATE=$(tr -d '+%' < "$CONFIG_DIR/rate" 2>/dev/null)
CURRENT_AR_RATE=$(tr -d '+%' < "$CONFIG_DIR/arabic_rate" 2>/dev/null)
CURRENT_DE_RATE=$(tr -d '+%' < "$CONFIG_DIR/german_rate" 2>/dev/null)
CURRENT_GLOBAL_SPEED=$(tr -d ' ' < "$CONFIG_DIR/global_speed" 2>/dev/null)
CURRENT_SOURCE_LANG=$(cat "$CONFIG_DIR/source_language" 2>/dev/null || echo "auto")
CURRENT_TRANSLATE_ENABLED=$(cat "$CONFIG_DIR/translate_enabled" 2>/dev/null || echo "no")
CURRENT_TRANSLATE_PROVIDER=$(cat "$CONFIG_DIR/translate_provider" 2>/dev/null || echo "deepl")
CURRENT_TRANSLATE_TARGET=$(cat "$CONFIG_DIR/translate_target" 2>/dev/null || echo "")
CURRENT_TRANSLATE_KEY=$(cat "$CONFIG_DIR/translate_api_key" 2>/dev/null || echo "")
[ -z "$CURRENT_RATE" ]        && CURRENT_RATE=50
[ -z "$CURRENT_AR_RATE" ]     && CURRENT_AR_RATE=30
[ -z "$CURRENT_DE_RATE" ]     && CURRENT_DE_RATE=30
[ -z "$CURRENT_GLOBAL_SPEED" ] && CURRENT_GLOBAL_SPEED=1.5

# Build voice lists with current value first so it appears pre-selected
EN_VOICES="$CURRENT_VOICE!en-US-ChristopherNeural!en-GB-RyanNeural!en-US-GuyNeural"
AR_VOICES="$CURRENT_AR_VOICE!ar-SA-HamedNeural!ar-SA-ZariyahNeural!ar-EG-SalmaNeural"
DE_VOICES="$CURRENT_DE_VOICE!de-DE-ConradNeural!de-DE-KatjaNeural!de-DE-KillianNeural"

SRC_LANGS="$CURRENT_SOURCE_LANG!auto!en!ar!de"
TRANS_PROVIDERS="$CURRENT_TRANSLATE_PROVIDER!deepl!google"
TRANS_TARGETS="$CURRENT_TRANSLATE_TARGET!!en!ar!de!fr!es!pt!it!nl!ru!zh!ja!ko!tr!pl!hi"

if RESULTS=$(yad --title="TTS Settings" --form --width=450 \
    --field="English Voice:CB"              "$EN_VOICES" \
    --field="Arabic Voice:CB"               "$AR_VOICES" \
    --field="German Voice:CB"               "$DE_VOICES" \
    --field="English Speed (+%):HSCALE"     "$CURRENT_RATE" \
    --field="Arabic Speed (+%):HSCALE"      "$CURRENT_AR_RATE" \
    --field="German Speed (+%):HSCALE"      "$CURRENT_DE_RATE" \
    --field="Global Playback Speed:NUM"    "$CURRENT_GLOBAL_SPEED" \
    --field="Custom Voice ID (optional):TEXT" "" \
    --field="Source Language:CB"            "$SRC_LANGS" \
    --field="Translate Enabled:CHK"         "$CURRENT_TRANSLATE_ENABLED" \
    --field="Translate Provider:CB"         "$TRANS_PROVIDERS" \
    --field="Translate Target:CB"          "$TRANS_TARGETS" \
    --field="Translate API Key:TEXT"        "$CURRENT_TRANSLATE_KEY" \
    --button="Save":0 --button="Cancel":1); then
    EN_VOICE=$(echo    "$RESULTS" | cut -d'|' -f1)
    AR_VOICE=$(echo    "$RESULTS" | cut -d'|' -f2)
    DE_VOICE=$(echo    "$RESULTS" | cut -d'|' -f3)
    EN_RATE=$(echo     "$RESULTS" | cut -d'|' -f4 | cut -d'.' -f1)
    AR_RATE=$(echo     "$RESULTS" | cut -d'|' -f5 | cut -d'.' -f1)
    DE_RATE=$(echo     "$RESULTS" | cut -d'|' -f6 | cut -d'.' -f1)
    GLOBAL_SPEED=$(echo "$RESULTS" | cut -d'|' -f7)
    CUSTOM_VOICE=$(echo "$RESULTS" | cut -d'|' -f8)
    SOURCE_LANG=$(echo   "$RESULTS" | cut -d'|' -f9)
    TRANSLATE_ENABLED=$(echo "$RESULTS" | cut -d'|' -f10)
    TRANSLATE_PROVIDER=$(echo "$RESULTS" | cut -d'|' -f11)
    TRANSLATE_TARGET=$(echo "$RESULTS" | cut -d'|' -f12)
    TRANSLATE_KEY=$(echo "$RESULTS" | cut -d'|' -f13)

    # Validate inputs
    # Validate speed values (0-200%)
    EN_RATE=$(echo "$EN_RATE" | grep -o '[0-9]\+' | head -1)
    AR_RATE=$(echo "$AR_RATE" | grep -o '[0-9]\+' | head -1)
    DE_RATE=$(echo "$DE_RATE" | grep -o '[0-9]\+' | head -1)
    EN_RATE=${EN_RATE:-50}
    AR_RATE=${AR_RATE:-30}
    DE_RATE=${DE_RATE:-30}
    
    # Validate global speed (0.1-5.0)
    GLOBAL_SPEED=$(echo "$GLOBAL_SPEED" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1)
    GLOBAL_SPEED=${GLOBAL_SPEED:-1.5}
    # Use awk to ensure it's within bounds
    GLOBAL_SPEED=$(echo "$GLOBAL_SPEED" | awk '{if ($1 < 0.1) print 0.1; else if ($1 > 5.0) print 5.0; else print $1}')
    
    # Validate voice IDs (alphanumeric with hyphens); fallback per language
    validate_voice() {
        local voice="$1" fallback="$2"
        if echo "$voice" | grep -q '^[a-zA-Z][a-zA-Z0-9-]*$'; then
            echo "$voice"
        else
            echo "$fallback"
        fi
    }
    
    EN_VOICE=$(validate_voice "$EN_VOICE" "en-US-ChristopherNeural")
    AR_VOICE=$(validate_voice "$AR_VOICE" "ar-SA-HamedNeural")
    DE_VOICE=$(validate_voice "$DE_VOICE" "de-DE-ConradNeural")
    
    # Custom voice ID overrides the English voice dropdown if filled in
    if [ -n "$CUSTOM_VOICE" ]; then
        EN_VOICE=$(validate_voice "$CUSTOM_VOICE" "$EN_VOICE")
    fi

    echo "$EN_VOICE"     > "$CONFIG_DIR/voice"
    echo "$AR_VOICE"     > "$CONFIG_DIR/arabic_voice"
    echo "$DE_VOICE"     > "$CONFIG_DIR/german_voice"
    echo "+${EN_RATE}%"  > "$CONFIG_DIR/rate"
    echo "+${AR_RATE}%"  > "$CONFIG_DIR/arabic_rate"
    echo "+${DE_RATE}%"  > "$CONFIG_DIR/german_rate"
    echo "$GLOBAL_SPEED" > "$CONFIG_DIR/global_speed"
    echo "$SOURCE_LANG"  > "$CONFIG_DIR/source_language"
    echo "$TRANSLATE_ENABLED" > "$CONFIG_DIR/translate_enabled"
    echo "$TRANSLATE_PROVIDER" > "$CONFIG_DIR/translate_provider"
    echo "$TRANSLATE_TARGET"   > "$CONFIG_DIR/translate_target"
    echo "$TRANSLATE_KEY"  > "$CONFIG_DIR/translate_api_key"

    notify-send "TTS Updated" "EN: $EN_VOICE (+${EN_RATE}%) | AR: $AR_VOICE (+${AR_RATE}%) | DE: $DE_VOICE (+${DE_RATE}%) | Speed: ${GLOBAL_SPEED}×"
fi
