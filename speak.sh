#!/bin/bash

CONFIG_DIR="$HOME/.config/tts_settings"
WORK_DIR="/tmp/tts_work"

# Dependency check
for cmd in edge-tts mpv xsel python3; do
    if ! command -v "$cmd" &>/dev/null; then
        notify-send "TTS Error" "Missing dependency: $cmd"
        exit 1
    fi
done

# Kill previous audio and clean work dir
pkill -f mpv 2>/dev/null
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# Get text from primary selection
TEXT=$(xsel -p)
[ -z "$TEXT" ] && exit 0

# Read config with safe fallbacks
EN_VOICE=$(cat "$CONFIG_DIR/voice"         2>/dev/null || echo "en-US-ChristopherNeural")
AR_VOICE=$(cat "$CONFIG_DIR/arabic_voice"  2>/dev/null || echo "ar-SA-HamedNeural")
EN_RATE=$(cat  "$CONFIG_DIR/rate"          2>/dev/null || echo "+50%")
AR_RATE=$(cat  "$CONFIG_DIR/arabic_rate"   2>/dev/null || echo "+30%")

# Split text into language segments.
# Writes seg_NNN.lang and seg_NNN.txt into WORK_DIR; prints segment count.
SEG_COUNT=$(python3 - "$TEXT" "$WORK_DIR" <<'PYEOF'
import sys, re

text, workdir = sys.argv[1], sys.argv[2]

arabic = re.compile(
    r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]'
    r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿\s]*'
)

segs, last = [], 0
for m in arabic.finditer(text):
    if m.start() > last:
        chunk = text[last:m.start()].strip()
        if chunk:
            segs.append(('en', chunk))
    ar_chunk = m.group().strip()
    if ar_chunk:
        segs.append(('ar', ar_chunk))
    last = m.end()
if last < len(text):
    chunk = text[last:].strip()
    if chunk:
        segs.append(('en', chunk))
if not segs:
    segs.append(('en', text))

for i, (lang, chunk) in enumerate(segs):
    open(f'{workdir}/seg_{i:03d}.lang', 'w').write(lang)
    open(f'{workdir}/seg_{i:03d}.txt',  'w').write(chunk)

print(len(segs))
PYEOF
)

# Speak each segment with its matching voice and rate
for i in $(seq 0 $((SEG_COUNT - 1))); do
    PAD=$(printf "%03d" "$i")
    LANG=$(cat "$WORK_DIR/seg_${PAD}.lang")
    SEG_TEXT=$(cat "$WORK_DIR/seg_${PAD}.txt")
    AUDIO="$WORK_DIR/seg_${PAD}.mp3"

    [ "$LANG" = "ar" ] && VOICE="$AR_VOICE" RATE="$AR_RATE" || VOICE="$EN_VOICE" RATE="$EN_RATE"

    if ! edge-tts --voice "$VOICE" --rate="$RATE" --text "$SEG_TEXT" --write-media "$AUDIO" 2>/dev/null; then
        notify-send "TTS Error" "Failed to generate speech (no internet?)"
        exit 1
    fi

    mpv "$AUDIO" --no-terminal --input-ipc-server=/tmp/mpvsocket
done
