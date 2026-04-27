#!/bin/bash

# Toggle pause/resume for currently playing TTS audio
SOCKET="/tmp/mpvsocket"
[ -S "$SOCKET" ] || exit 0
echo '{"command":["cycle","pause"]}' | socat - "$SOCKET"
