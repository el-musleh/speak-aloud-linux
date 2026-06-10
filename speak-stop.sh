#!/bin/bash

# Stop currently playing TTS audio (targets only our mpv via its IPC socket)
TEMP_DIR="${TMPDIR:-/tmp}"
SOCKET="$TEMP_DIR/speak-aloud-mpv.sock"
[ -S "$SOCKET" ] || exit 0
echo '{"command":["quit"]}' | socat - "$SOCKET" 2>/dev/null
