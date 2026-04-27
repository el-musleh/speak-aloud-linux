#!/bin/bash

CONFIG_DIR="$HOME/.config/tts_settings"
WORK_DIR="/tmp/tts_work"

# ── Parse optional CLI args ───────────────────────────────────────────────────
OVERRIDE_TEXT=""
OVERRIDE_EN_VOICE=""
OVERRIDE_AR_VOICE=""
OVERRIDE_EN_RATE=""
OVERRIDE_AR_RATE=""
OVERRIDE_SPEED=""     # mpv speed multiplier (e.g. 1.5) — used in GUI mode only

while [[ $# -gt 0 ]]; do
    case "$1" in
        --text)     OVERRIDE_TEXT="$2";     shift 2 ;;
        --en-voice) OVERRIDE_EN_VOICE="$2"; shift 2 ;;
        --ar-voice) OVERRIDE_AR_VOICE="$2"; shift 2 ;;
        --en-rate)  OVERRIDE_EN_RATE="$2";  shift 2 ;;
        --ar-rate)  OVERRIDE_AR_RATE="$2";  shift 2 ;;
        --speed)    OVERRIDE_SPEED="$2";    shift 2 ;;
        *) shift ;;
    esac
done

# ── Dependency check ──────────────────────────────────────────────────────────
for cmd in edge-tts mpv python3; do
    if ! command -v "$cmd" &>/dev/null; then
        notify-send "TTS Error" "Missing dependency: $cmd"; exit 1
    fi
done
if [ -z "$OVERRIDE_TEXT" ] && ! command -v xsel &>/dev/null; then
    notify-send "TTS Error" "Missing dependency: xsel"; exit 1
fi

# ── Kill previous audio and clean work dir ────────────────────────────────────
pkill -f "input-ipc-server=/tmp/mpvsocket" 2>/dev/null
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# ── Get text ──────────────────────────────────────────────────────────────────
TEXT="${OVERRIDE_TEXT:-$(xsel -p)}"
[ -z "$TEXT" ] && exit 0

# ── Read config with CLI overrides taking priority ────────────────────────────
EN_VOICE="${OVERRIDE_EN_VOICE:-$(cat "$CONFIG_DIR/voice"        2>/dev/null || echo "en-US-ChristopherNeural")}"
AR_VOICE="${OVERRIDE_AR_VOICE:-$(cat "$CONFIG_DIR/arabic_voice" 2>/dev/null || echo "ar-SA-HamedNeural")}"
EN_RATE="${OVERRIDE_EN_RATE:-$(cat   "$CONFIG_DIR/rate"         2>/dev/null || echo "+50%")}"
AR_RATE="${OVERRIDE_AR_RATE:-$(cat   "$CONFIG_DIR/arabic_rate"  2>/dev/null || echo "+30%")}"

# ── Split text into language segments ─────────────────────────────────────────
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

# ═════════════════════════════════════════════════════════════════════════════
# GUI MODE  (--text was provided)
# ─────────────────────────────────────────────────────────────────────────────
# Two-pass approach:
#   Pass 1 — generate all MP3s at normal pitch/speed (no --rate flag).
#             The speed is controlled entirely by mpv in real-time via IPC.
#   Pass 2 — play all files as a single mpv playlist so the IPC socket
#             remains alive for the full duration, allowing tts-app.py to
#             adjust speed live without interrupting playback.
# ═════════════════════════════════════════════════════════════════════════════
if [ -n "$OVERRIDE_TEXT" ]; then

    echo "STATUS:GENERATING"

    for i in $(seq 0 $((SEG_COUNT - 1))); do
        PAD=$(printf "%03d" "$i")
        LANG=$(cat "$WORK_DIR/seg_${PAD}.lang")
        SEG_TEXT=$(cat "$WORK_DIR/seg_${PAD}.txt")
        AUDIO="$WORK_DIR/seg_${PAD}.mp3"
        [ "$LANG" = "ar" ] && VOICE="$AR_VOICE" || VOICE="$EN_VOICE"

        if ! edge-tts --voice "$VOICE" --text "$SEG_TEXT" --write-media "$AUDIO" 2>/dev/null; then
            echo "STATUS:ERROR"
            notify-send "TTS Error" "Failed to generate speech (no internet?)"; exit 1
        fi
    done

    echo "STATUS:PLAYING"

    INITIAL_SPEED="${OVERRIDE_SPEED:-1.5}"
    mapfile -t FILES < <(ls -1 "$WORK_DIR"/seg_*.mp3 | sort)
    rm -f /tmp/mpvsocket
    mpv "${FILES[@]}" --no-terminal --input-ipc-server=/tmp/mpvsocket &
    MPV_PID=$!

    # Wait for socket, then set initial playback speed
    for _ in $(seq 1 30); do
        sleep 0.1
        if [ -S /tmp/mpvsocket ]; then
            printf '{"command":["set_property","speed",%s]}\n' "$INITIAL_SPEED" \
                | socat - /tmp/mpvsocket 2>/dev/null
            break
        fi
    done

    wait "$MPV_PID"
    rm -f /tmp/mpvsocket

# ═════════════════════════════════════════════════════════════════════════════
# SHORTCUT MODE  (keyboard shortcut, no --text arg)
# ─────────────────────────────────────────────────────────────────────────────
# Original per-segment approach: edge-tts --rate controls speed so the
# keyboard shortcut still works without the GUI app being open.
# ═════════════════════════════════════════════════════════════════════════════
else

    for i in $(seq 0 $((SEG_COUNT - 1))); do
        PAD=$(printf "%03d" "$i")
        LANG=$(cat "$WORK_DIR/seg_${PAD}.lang")
        SEG_TEXT=$(cat "$WORK_DIR/seg_${PAD}.txt")
        AUDIO="$WORK_DIR/seg_${PAD}.mp3"

        [ "$LANG" = "ar" ] && VOICE="$AR_VOICE" RATE="$AR_RATE" \
                           || VOICE="$EN_VOICE" RATE="$EN_RATE"

        if ! edge-tts --voice "$VOICE" --rate="$RATE" --text "$SEG_TEXT" \
                      --write-media "$AUDIO" 2>/dev/null; then
            notify-send "TTS Error" "Failed to generate speech (no internet?)"; exit 1
        fi

        mpv "$AUDIO" --no-terminal --input-ipc-server=/tmp/mpvsocket
    done

fi
