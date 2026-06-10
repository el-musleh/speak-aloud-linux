#!/bin/bash

# Toggle pause/resume for currently playing TTS audio
# Use system temp directory for portability
TEMP_DIR="${TMPDIR:-/tmp}"
SOCKET="$TEMP_DIR/speak-aloud-mpv.sock"
[ -S "$SOCKET" ] || exit 0
echo '{"command":["cycle","pause"]}' | socat - "$SOCKET"
