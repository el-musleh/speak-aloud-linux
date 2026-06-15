#!/bin/bash

# Add local bin directory to PATH for mpv
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$SCRIPT_DIR/bin:$PATH"

CONFIG_DIR="$HOME/.config/tts_settings"
# Use system temp directory for portability
TEMP_DIR="${TMPDIR:-/tmp}"
WORK_DIR="$TEMP_DIR/speak-aloud-work"

# ── Parse optional CLI args ───────────────────────────────────────────────────
OVERRIDE_TEXT=""
OVERRIDE_EN_VOICE=""
OVERRIDE_AR_VOICE=""
OVERRIDE_DE_VOICE=""
OVERRIDE_EN_RATE=""
OVERRIDE_AR_RATE=""
OVERRIDE_DE_RATE=""
OVERRIDE_SPEED=""     # mpv speed multiplier (e.g. 1.5) — used in GUI mode only
OUTPUT_FILE=""        # optional: export concatenated audio to this path
OVERRIDE_SOURCE_LANG=""   # optional: force source language (auto, en, ar, de, ...)
OVERRIDE_TRANSLATE_ENABLED=""  # optional: yes/no
OVERRIDE_TRANSLATE_PROVIDER="" # optional: deepl, google
OVERRIDE_TRANSLATE_TARGET=""   # optional: target language code
OVERRIDE_TRANSLATE_KEY=""  # optional: API key string

show_help() {
    cat << 'EOF'
Usage: speak.sh [OPTIONS]

Options:
  --text TEXT              Speak explicit text
  --en-voice VOICE         Override English voice
  --ar-voice VOICE         Override Arabic voice
  --de-voice VOICE         Override German voice
  --en-rate RATE           Override English rate (e.g., +50%)
  --ar-rate RATE           Override Arabic rate (e.g., +30%)
  --de-rate RATE           Override German rate (e.g., +30%)
  --speed MULTIPLIER       Playback speed for GUI mode (e.g., 1.5)
  --output FILE.mp3        Export concatenated audio to file
  --source-lang LANG         Force source language (auto, en, ar, de, ...)
  --translate-enabled yes/no Enable/disable translation
  --translate-provider     Translation provider (deepl, google)
  --translate-target LANG  Target language for translation
  --translate-api-key KEY  API key for translation service
  --help                   Show this help message

Audio file locations:
  Cache folder (30-day persistent): ~/.cache/speak-aloud/
  Temp work folder (segments):      /tmp/speak-aloud-work/
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --text)     OVERRIDE_TEXT="$2";     shift 2 ;;
        --en-voice) OVERRIDE_EN_VOICE="$2"; shift 2 ;;
        --ar-voice) OVERRIDE_AR_VOICE="$2"; shift 2 ;;
        --de-voice) OVERRIDE_DE_VOICE="$2"; shift 2 ;;
        --en-rate)  OVERRIDE_EN_RATE="$2";  shift 2 ;;
        --ar-rate)  OVERRIDE_AR_RATE="$2";  shift 2 ;;
        --de-rate)  OVERRIDE_DE_RATE="$2";  shift 2 ;;
        --speed)    OVERRIDE_SPEED="$2";    shift 2 ;;
        --output)   OUTPUT_FILE="$2";       shift 2 ;;
        --source-lang)       OVERRIDE_SOURCE_LANG="$2";       shift 2 ;;
        --translate-enabled) OVERRIDE_TRANSLATE_ENABLED="$2"; shift 2 ;;
        --translate-provider) OVERRIDE_TRANSLATE_PROVIDER="$2"; shift 2 ;;
        --translate-target)  OVERRIDE_TRANSLATE_TARGET="$2";  shift 2 ;;
        --translate-api-key) OVERRIDE_TRANSLATE_KEY="$2"; shift 2 ;;
        --help)     show_help; exit 0 ;;
        *) shift ;;
    esac
done

# ── Session lock: only one speak.sh at a time (held until exit) ────────────
LOCK_FILE="$TEMP_DIR/speak-aloud.lock"
MPV_SOCKET="$TEMP_DIR/speak-aloud-mpv.sock"
INTERRUPT_FLAG="$TEMP_DIR/speak-aloud.interrupt"

# Clean up stale interrupt flag from a crashed previous run
rm -f "$INTERRUPT_FLAG"

# Open lock file
exec 200>"$LOCK_FILE"

# Try to acquire lock without blocking
if ! flock -n 200 2>/dev/null; then
    # Another instance is running — ask it to stop and wait for the lock.
    touch "$INTERRUPT_FLAG"
    if [ -S "$MPV_SOCKET" ]; then
        echo '{"command":["quit"]}' | socat - "$MPV_SOCKET" 2>/dev/null
    fi
    # Block up to 5 seconds for the previous instance to release the lock
    if ! flock -w 5 200 2>/dev/null; then
        rm -f "$INTERRUPT_FLAG"
        exit 0
    fi
    rm -f "$INTERRUPT_FLAG"
fi

# Lock (fd 200) is held for the entire lifetime of this script, including
# playback. New invocations interrupt us via the mpv socket + interrupt flag.
trap 'cleanup_temp_files' EXIT

# Temporary file management
declare -a TEMP_FILES=()
cleanup_temp_files() {
    for temp_file in "${TEMP_FILES[@]}"; do
        rm -f "$temp_file" 2>/dev/null
    done
    rm -f "$MPV_SOCKET" 2>/dev/null
}

create_temp_file() {
    local suffix="${1:-}"
    local temp_file
    temp_file=$(mktemp -t "tts-XXXXXX$suffix")
    TEMP_FILES+=("$temp_file")
    echo "$temp_file"
}

# ── Dependency check ──────────────────────────────────────────────────────────
for cmd in edge-tts mpv python3; do
    if ! command -v "$cmd" &>/dev/null; then
        notify-send "TTS Error" "Missing dependency: $cmd"; exit 1
    fi
done
if [ -z "$OVERRIDE_TEXT" ] && ! command -v xsel &>/dev/null; then
    notify-send "TTS Error" "Missing dependency: xsel"; exit 1
fi

# ── Clean work dir (no killing - we have the lock) ────────────────────────────
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# ── Get text ──────────────────────────────────────────────────────────────────
TEXT="${OVERRIDE_TEXT:-$(xsel -p)}"
[ -z "$TEXT" ] && exit 0

# Validate and sanitize input text
validate_text() {
    local text="$1"
    # Remove ASCII control characters only — must NOT touch bytes >= 0x80,
    # otherwise multibyte UTF-8 (Arabic, umlauts, …) would be destroyed.
    text=$(printf '%s' "$text" | tr -d '\000-\010\013\014\016-\037\177')
    # Limit to reasonable length (10000 chars)
    if [ ${#text} -gt 10000 ]; then
        echo "Text too long (${#text} chars), truncating to 10000" >&2
        text="${text:0:10000}"
    fi
    echo "$text"
}

TEXT=$(validate_text "$TEXT")
[ -z "$TEXT" ] && exit 0

# ── Minimum-content guard ───────────────────────────────────────────────────────────────────
# Require at least 2 Unicode letters/digits before invoking TTS. Accidental
# tiny selections (single letter, space, punctuation) are skipped silently
# in shortcut mode; GUI mode still reports an error for deliberate input.
SPEAKABLE_COUNT=$(python3 -c '
import sys, unicodedata
text = sys.argv[1]
print(sum(1 for ch in text if unicodedata.category(ch)[0] in ("L", "N")))
' "$TEXT" 2>/dev/null || echo 0)
if [ "$SPEAKABLE_COUNT" -lt 2 ] 2>/dev/null; then
    if [ -n "$OVERRIDE_TEXT" ]; then
        echo "STATUS:ERROR"
        notify-send "TTS Error" "Text contains no speakable content (e.g., only punctuation)."
        exit 1
    fi
    exit 0
fi

# ── Read config with CLI overrides taking priority ────────────────────────────
EN_VOICE="${OVERRIDE_EN_VOICE:-$(cat "$CONFIG_DIR/voice"        2>/dev/null || echo "en-US-ChristopherNeural")}"
AR_VOICE="${OVERRIDE_AR_VOICE:-$(cat "$CONFIG_DIR/arabic_voice" 2>/dev/null || echo "ar-SA-HamedNeural")}"
DE_VOICE="${OVERRIDE_DE_VOICE:-$(cat "$CONFIG_DIR/german_voice" 2>/dev/null || echo "de-DE-ConradNeural")}"
EN_RATE="${OVERRIDE_EN_RATE:-$(cat   "$CONFIG_DIR/rate"         2>/dev/null || echo "+50%")}"
AR_RATE="${OVERRIDE_AR_RATE:-$(cat   "$CONFIG_DIR/arabic_rate"  2>/dev/null || echo "+30%")}"
DE_RATE="${OVERRIDE_DE_RATE:-$(cat   "$CONFIG_DIR/german_rate"  2>/dev/null || echo "+30%")}"
# Note: OVERRIDE_SPEED is read directly where needed (GUI mode only)

SOURCE_LANG="${OVERRIDE_SOURCE_LANG:-$(cat "$CONFIG_DIR/source_language" 2>/dev/null || echo "auto")}"
TRANSLATE_ENABLED="${OVERRIDE_TRANSLATE_ENABLED:-$(cat "$CONFIG_DIR/translate_enabled" 2>/dev/null || echo "no")}"
TRANSLATE_PROVIDER="${OVERRIDE_TRANSLATE_PROVIDER:-$(cat "$CONFIG_DIR/translate_provider" 2>/dev/null || echo "deepl")}"
TRANSLATE_TARGET="${OVERRIDE_TRANSLATE_TARGET:-$(cat "$CONFIG_DIR/translate_target" 2>/dev/null || echo "")}"
TRANSLATE_KEY="${OVERRIDE_TRANSLATE_KEY:-$(cat "$CONFIG_DIR/translate_api_key" 2>/dev/null || echo "")}"

# ── Cache helpers ─────────────────────────────────────────────────────────────
CACHE_DIR="$HOME/.cache/speak-aloud"
mkdir -p "$CACHE_DIR"

# Prune cache entries not used in the last 30 days (keeps cache bounded)
find "$CACHE_DIR" -name '*.mp3' -type f -atime +30 -delete 2>/dev/null &

cache_key() {
    # Hash the full raw inputs — no sanitizing/truncation, so distinct
    # (voice, rate, text) combinations can never collide.
    local voice="$1" rate="$2" text="$3"
    if [ -z "$voice" ] || [ -z "$text" ]; then
        echo "invalid"
        return 1
    fi
    # Include translation settings so translated vs. original text don't collide
    local extra=""
    if [ "$TRANSLATE_ENABLED" = "yes" ] && [ -n "$TRANSLATE_TARGET" ]; then
        extra="${TRANSLATE_PROVIDER}:${TRANSLATE_TARGET}"
    fi
    printf '%s\x1f%s\x1f%s\x1f%s' "$voice" "$rate" "$text" "$extra" | sha256sum | cut -d' ' -f1
}

cache_path() {
    echo "$CACHE_DIR/$(cache_key "$1" "$2" "$3").mp3"
}

# Atomically store a generated file in the cache (parallel-safe).
cache_store() {
    local src="$1" dest="$2" tmp
    tmp="${dest}.tmp.$$"
    cp "$src" "$tmp" && mv "$tmp" "$dest"
}

# Runs edge-tts with retry and real error parsing.
# Args: VOICE RATE TEXT AUDIO   (RATE may be empty → no --rate flag)
# Returns 0 on success, prints human-readable error to stderr on failure.
generate_audio() {
    local voice="$1" rate="$2" text="$3" audio="$4"
    local tmp_stderr tmp_audio attempt delay
    local rate_args=()
    [ -n "$rate" ] && rate_args=(--rate="$rate")
    tmp_stderr=$(create_temp_file)
    tmp_audio=$(create_temp_file ".mp3")

    for attempt in 1 2 3; do
        : > "$tmp_stderr"
        if edge-tts --voice "$voice" "${rate_args[@]}" --text "$text" --write-media "$tmp_audio" 2>"$tmp_stderr"; then
            # Validate the generated audio file
            if [ -s "$tmp_audio" ] && file "$tmp_audio" 2>/dev/null | grep -qi "audio\|mpeg"; then
                mv "$tmp_audio" "$audio"
                rm -f "$tmp_stderr" "$tmp_audio"
                return 0
            else
                echo "Generated file is not valid audio" >&2
            fi
        fi

        # Parse stderr for known errors
        local err_msg=""
        if grep -q "NoAudioReceived" "$tmp_stderr"; then
            err_msg="Text contains no speakable content (e.g., only punctuation)."
        elif grep -q -i "timeout\|connection\|websocket" "$tmp_stderr"; then
            if [ "$attempt" -lt 3 ]; then
                delay=$(( attempt * 2 ))
                notify-send "TTS Retry" "Connection issue — retrying in ${delay}s (attempt $attempt/3)"
                sleep "$delay"
                continue
            fi
            err_msg="Connection timed out after 3 attempts. Check your internet."
        elif grep -q -i "rate.*limit\|429\|too many" "$tmp_stderr"; then
            if [ "$attempt" -lt 3 ]; then
                delay=$(( attempt * 3 ))
                notify-send "TTS Retry" "Rate limited — waiting ${delay}s (attempt $attempt/3)"
                sleep "$delay"
                continue
            fi
            err_msg="Rate limited by Microsoft TTS service. Try again later."
        else
            err_msg="Failed to generate speech. Check your internet connection."
        fi

        echo "$err_msg" >&2
        rm -f "$tmp_stderr" "$tmp_audio"
        return 1
    done
}

# ── Optional: translate text before TTS ─────────────────────────────────────
if [ "$TRANSLATE_ENABLED" = "yes" ] && [ -n "$TRANSLATE_TARGET" ] && [ -n "$TRANSLATE_KEY" ]; then
    SCRIPT_DIR_TR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    TRANSLATED=$(printf '%s' "$TEXT" | python3 "$SCRIPT_DIR_TR/translate_text.py" \
        --provider "$TRANSLATE_PROVIDER" \
        --target "$TRANSLATE_TARGET" \
        --api-key "$TRANSLATE_KEY" 2>&1)
    TRANSLATE_STATUS=$?
    if [ "$TRANSLATE_STATUS" -ne 0 ]; then
        if [ -n "$OVERRIDE_TEXT" ]; then
            echo "STATUS:ERROR"
            notify-send "TTS Translation Error" "${TRANSLATED:-Translation failed.}"
            exit 1
        fi
        # Shortcut mode: skip silently on translation error
        exit 0
    fi
    TEXT="$TRANSLATED"
fi

# ── Source-language override: bypass auto-detection ─────────────────────────
if [ "$SOURCE_LANG" != "auto" ]; then
    mkdir -p "$WORK_DIR"
    printf '%s' "$SOURCE_LANG" > "$WORK_DIR/seg_000.lang"
    printf '%s' "$TEXT"        > "$WORK_DIR/seg_000.txt"
    SEG_COUNT=1
else

# ── Split text into language segments ─────────────────────────────────────────
PY_SCRIPT=$(mktemp)
cat > "$PY_SCRIPT" <<'PYEOF'
import sys, re

text, workdir = sys.argv[1], sys.argv[2]

arabic = re.compile(
    r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]'
    r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s]*'
)

GERMAN_CHARS = re.compile(r'[äöüßÄÖÜẞ]')

# Words that are German and essentially never appear in English text.
STRONG_DE = {
    'der', 'das', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'eines',
    'und', 'oder', 'aber', 'mit', 'zu', 'von', 'aus', 'bei', 'nach', 'wie',
    'wenn', 'weil', 'dass', 'ist', 'sind', 'waren', 'wird', 'werden',
    'wurde', 'wurden', 'haben', 'hatte', 'hatten', 'kann', 'wollen',
    'soll', 'sollen', 'muss', 'darf',
    'ich', 'du', 'wir', 'ihr', 'sie', 'mir', 'dir', 'ihm', 'uns', 'euch',
    'nicht', 'kein', 'keine', 'ja', 'nein', 'bitte', 'danke', 'guten',
    'abend', 'hallo', 'wiedersehen', 'auf',
    'schlecht', 'klein', 'neu',
    'heute', 'gestern', 'jetzt', 'hier', 'dort',
    'viel', 'wenig', 'mehr', 'meiste', 'alle', 'jede', 'jeder', 'jedes',
    'mann', 'frau', 'freund', 'freundin', 'haus', 'stadt', 'welt',
    'essen', 'trinken', 'gehen', 'kommen', 'sprechen', 'lesen',
    'schreiben', 'machen', 'tun', 'geben', 'nehmen', 'finden', 'denken',
    'wissen', 'wasser', 'brot', 'milch', 'kaffee', 'bier',
    'eins', 'zwei', 'drei', 'vier', 'sechs', 'sieben', 'acht', 'neun',
    'zehn',
}

# Words that exist in both German and English. They only count as German
# when directly adjacent to an already-German token (e.g. "Guten Morgen").
AMBIG_DE = {
    'die', 'den', 'war', 'hat', 'will', 'es', 'er', 'da', 'als', 'mag',
    'tag', 'morgen', 'kind', 'alt', 'land', 'wein', 'gut', 'tee',
}

WORD_RE = re.compile(r'\S+')
TRIM_RE = re.compile(r'^\W+|\W+$', re.UNICODE)

def classify_block(chunk):
    """Split a non-Arabic block into ('en'/'de', text) phrase segments.

    English is the default; tokens are marked German only with strong
    evidence (umlauts/eszett or unambiguous German words). Ambiguous
    words are promoted to German only when adjacent to German tokens.
    A German run is kept only if it has an umlaut token, or 2+ strong
    markers, or a strong marker plus at least one neighbour.
    """
    toks = [(m.group(), m.start(), m.end()) for m in WORD_RE.finditer(chunk)]
    n = len(toks)
    if n == 0:
        return []
    kind = []
    for w, _, _ in toks:
        key = TRIM_RE.sub('', w).lower()
        if GERMAN_CHARS.search(w):
            kind.append('umlaut')
        elif key in STRONG_DE:
            kind.append('strong')
        elif key in AMBIG_DE:
            kind.append('ambig')
        else:
            kind.append('en')
    # Promote ambiguous tokens that touch a German token (chains allowed),
    # and bridge unknown tokens flanked by German tokens on BOTH sides so
    # full German sentences with out-of-list words stay in one run.
    GERMANISH = ('umlaut', 'strong', 'de')
    changed = True
    while changed:
        changed = False
        for i in range(n):
            if kind[i] == 'ambig':
                if (i > 0 and kind[i-1] in GERMANISH) or \
                   (i + 1 < n and kind[i+1] in GERMANISH):
                    kind[i] = 'de'
                    changed = True
            elif kind[i] == 'en':
                # Bridge an unknown word when both neighbours are German
                # (one side may still be an unpromoted ambiguous word).
                if 0 < i < n - 1:
                    left, right = kind[i-1], kind[i+1]
                    if (left in GERMANISH and right in GERMANISH + ('ambig',)) or \
                       (right in GERMANISH and left in GERMANISH + ('ambig',)):
                        kind[i] = 'de'
                        changed = True
    # Group tokens into runs and decide each run's language
    out = []  # (lang, first_tok_idx, last_tok_idx_exclusive)
    i = 0
    while i < n:
        german_ish = kind[i] in ('umlaut', 'strong', 'de')
        j = i
        while j < n and (kind[j] in ('umlaut', 'strong', 'de')) == german_ish:
            j += 1
        if german_ish:
            has_umlaut = any(kind[k] == 'umlaut' for k in range(i, j))
            strong_cnt = sum(1 for k in range(i, j)
                             if kind[k] in ('umlaut', 'strong'))
            if has_umlaut or strong_cnt >= 2 or (strong_cnt >= 1 and j - i >= 2):
                out.append(('de', i, j))
            else:
                out.append(('en', i, j))
        else:
            out.append(('en', i, j))
        i = j
    # Absorb a single sentence-final unknown word into a preceding German
    # run of 3+ tokens (e.g. "... nach Hause." where "Hause" is unlisted).
    for idx in range(len(out) - 1):
        lang, a, b = out[idx]
        nlang, na, nb = out[idx + 1]
        if lang == 'de' and nlang == 'en' and b - a >= 3 \
                and toks[na][0].rstrip('"\')')[-1:] in '.!?':
            out[idx] = ('de', a, na + 1)
            out[idx + 1] = ('en', na + 1, nb)
    out = [(lang, a, b) for lang, a, b in out if b > a]
    return [(lang, chunk[toks[a][1]:toks[b-1][2]]) for lang, a, b in out]

# Pass 1: split out Arabic runs (highest priority)
raw_segs, last = [], 0
for m in arabic.finditer(text):
    if m.start() > last:
        chunk = text[last:m.start()].strip()
        if chunk:
            raw_segs.append(chunk)
    ar_chunk = m.group().strip()
    if ar_chunk:
        raw_segs.append(('ar', ar_chunk))
    last = m.end()
if last < len(text):
    chunk = text[last:].strip()
    if chunk:
        raw_segs.append(chunk)
if not raw_segs:
    raw_segs.append(text)

# Pass 2: split each non-Arabic block into English/German phrase segments
segs = []
for item in raw_segs:
    if isinstance(item, tuple):
        segs.append(item)
        continue
    chunk = item.strip()
    if not chunk:
        continue
    segs.extend(classify_block(chunk))

# Skip segments that contain only whitespace / punctuation (no letters to speak)
import unicodedata

def speakable_count(s):
    return sum(1 for ch in s if unicodedata.category(ch)[0] in ('L', 'N'))

# Merge adjacent segments of the same language, skipping empty/punctuation-only
# chunks and single-character fragments (they often yield NoAudioReceived)
merged, last_lang, acc = [], None, ''
for lang, chunk in segs:
    stripped = chunk.strip()
    if not stripped or speakable_count(stripped) < 2:
        continue
    if lang == last_lang:
        acc += ' ' + stripped
    else:
        if last_lang is not None:
            merged.append((last_lang, acc))
        last_lang = lang
        acc = stripped
if last_lang is not None:
    merged.append((last_lang, acc))
segs = merged

# Sanitize segments: strip characters the assigned voice cannot pronounce.
# This prevents edge-tts NoAudioReceived on text in unsupported scripts.
def sanitize_for_voice(lang, text):
    if lang == 'ar':
        # Arabic voice: keep Arabic script, basic punctuation, whitespace
        return re.sub(r'[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s\d.,;:!?\'"\-–—()\[\]]+', ' ', text)
    else:
        # Latin voices (en/de): keep Latin scripts, basic punctuation, whitespace
        # Strip CJK, Cyrillic, Arabic, Hebrew, emojis, symbols, zero-width chars
        return re.sub(r'[^\u0000-\u024F\u1E00-\u1EFF\u2000-\u206F\s\d.,;:!?\'"\-–—()\[\]]+|\u200B|\u200C|\u200D|\uFEFF|[\U0001F300-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]', ' ', text)

sanitized = []
for lang, chunk in segs:
    cleaned = sanitize_for_voice(lang, chunk).strip()
    if cleaned and speakable_count(cleaned) >= 2:
        sanitized.append((lang, cleaned))
segs = sanitized

# Fallback: if all segments were sanitized away but original text had content,
# try transliterating unsupported scripts so the selected voice can speak them.
if not segs and speakable_count(text) >= 2:
    try:
        from unidecode import unidecode
        roman = unidecode(text)
        roman = re.sub(r'\s+', ' ', roman).strip()
        if speakable_count(roman) >= 2:
            segs = [('en', roman)]  # Use English voice for transliterated text
    except Exception:
        pass

for i, (lang, chunk) in enumerate(segs):
    open(f'{workdir}/seg_{i:03d}.lang', 'w').write(lang)
    open(f'{workdir}/seg_{i:03d}.txt',  'w').write(chunk)

print(len(segs))
PYEOF
SEG_COUNT=$(python3 "$PY_SCRIPT" "$TEXT" "$WORK_DIR")
rm -f "$PY_SCRIPT"

fi  # end of source-language override / auto-detection block

# ── Split long monolingual segments at sentence boundaries ────────────────────
# If a language segment exceeds MAX_SEGMENT_CHARS, break it into smaller
# sentence-sized chunks so progressive playback can start sooner.
MAX_SEGMENT_CHARS=600
split_long_segments() {
    local max=$1 old_count=$2 new_idx=0
    local i tmp_txt tmp_lang text lang
    for i in $(seq 0 $((old_count - 1))); do
        tmp_txt="$WORK_DIR/seg_$(printf "%03d" "$i").txt"
        tmp_lang="$WORK_DIR/seg_$(printf "%03d" "$i").lang"
        [ -f "$tmp_txt" ] || continue
        text=$(cat "$tmp_txt")
        lang=$(cat "$tmp_lang" 2>/dev/null || echo en)
        if [ ${#text} -le "$max" ]; then
            mv "$tmp_txt" "$WORK_DIR/seg_$(printf "%03d" "$new_idx").txt"
            printf '%s' "$lang" > "$WORK_DIR/seg_$(printf "%03d" "$new_idx").lang"
            new_idx=$((new_idx + 1))
            continue
        fi
        # Split at sentence boundaries using Python
        py_script=$(mktemp)
        cat > "$py_script" <<'PYEOF'
import sys, re, os
text, max_len, lang, workdir, start_idx = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
abbrev = r'\b(?:Dr|Mr|Mrs|Ms|Prof|Jr|Sr|vs|etc|e\.g|i\.e|Inc|Ltd|Corp|No|no|fig|Fig|vol|pg|p)\.'
text = re.sub(abbrev, lambda m: m.group().replace('.', '\x00'), text)
parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'\u0600-\u06FF])', text)
parts = [p.replace('\x00', '.') for p in parts]
result = []
for p in parts:
    for s in p.split('\n\n'):
        s = s.strip()
        if s:
            result.append(s)
chunks, current = [], ''
for p in result:
    if not current:
        current = p
    elif len(current) + len(p) + 1 <= max_len:
        current += ' ' + p
    else:
        chunks.append(current)
        current = p
if current:
    chunks.append(current)
idx = start_idx
for ch in chunks:
    with open(os.path.join(workdir, f'seg_{idx:03d}.txt'), 'w') as f:
        f.write(ch)
    with open(os.path.join(workdir, f'seg_{idx:03d}.lang'), 'w') as f:
        f.write(lang)
    idx += 1
print(idx)
PYEOF
        new_idx=$(python3 "$py_script" "${text}" "$max" "$lang" "$WORK_DIR" "$new_idx")
        rm -f "$py_script" "$tmp_txt" "$tmp_lang"
    done
    echo "$new_idx"
}
SEG_COUNT=$(split_long_segments "$MAX_SEGMENT_CHARS" "$SEG_COUNT")

if [ -z "$SEG_COUNT" ] || ! [ "$SEG_COUNT" -ge 1 ] 2>/dev/null; then
    if [ -n "$OVERRIDE_TEXT" ]; then
        echo "STATUS:ERROR"
        notify-send "TTS Error" "Text contains no speakable content (e.g., only punctuation)."
        exit 1
    fi
    # Shortcut mode: accidental tiny/punctuation selection — skip silently
    exit 0
fi

# ═════════════════════════════════════════════════════════════════════════════
# GUI MODE  (--text was provided)
# ─────────────────────────────────────────────────────────────────────────────
# Progressive playback: start mpv as soon as the first segment is ready,
# then append remaining segments via IPC while generation continues.
# ═════════════════════════════════════════════════════════════════════════════
if [ -n "$OVERRIDE_TEXT" ]; then

    echo "STATUS:GENERATING"

    # Launch all edge-tts jobs in parallel
    PIDS=""
    for i in $(seq 0 $((SEG_COUNT - 1))); do
        PAD=$(printf "%03d" "$i")
        LANG=$(cat "$WORK_DIR/seg_${PAD}.lang")
        SEG_TEXT=$(cat "$WORK_DIR/seg_${PAD}.txt")
        AUDIO="$WORK_DIR/seg_${PAD}.mp3"
        if [ "$LANG" = "ar" ]; then VOICE="$AR_VOICE"
        elif [ "$LANG" = "de" ]; then VOICE="$DE_VOICE"
        else VOICE="$EN_VOICE"; fi

        (
            # GUI mode: no --rate — playback speed is controlled live via mpv
            CACHED=$(cache_path "$VOICE" "_GUI_" "$SEG_TEXT")
            if [ -f "$CACHED" ]; then
                cp "$CACHED" "$AUDIO"
            else
                if ! generate_audio "$VOICE" "" "$SEG_TEXT" "$AUDIO" 2>"$WORK_DIR/err_${PAD}.txt"; then
                    exit 1
                fi
                cache_store "$AUDIO" "$CACHED"
            fi
        ) &
        PIDS="$PIDS $!"
    done

    # ── Wait for first MP3, then start mpv immediately ──────────────────────
    FIRST_FILE=""
    for _ in $(seq 1 300); do
        FIRST_FILE=$(find "$WORK_DIR" -maxdepth 1 -name 'seg_*.mp3' | sort | head -n1)
        [ -n "$FIRST_FILE" ] && break
        sleep 0.1
    done

    if [ -z "$FIRST_FILE" ]; then
        FAILED=0
        for pid in $PIDS; do
            wait "$pid" || FAILED=1
        done
        ERR_MSG=$(cat "$WORK_DIR"/err_*.txt 2>/dev/null | grep -v '^+' | grep . | head -1)
        echo "STATUS:ERROR"
        notify-send "TTS Error" "${ERR_MSG:-Failed to generate speech. Check your internet connection.}"
        exit 1
    fi

    # A newer invocation may have asked us to stop while we were generating
    if [ -f "$INTERRUPT_FLAG" ]; then
        exit 0
    fi

    echo "STATUS:PLAYING"

    INITIAL_SPEED="${OVERRIDE_SPEED:-1.5}"
    rm -f "$MPV_SOCKET"
    mpv "$FIRST_FILE" --no-terminal --input-ipc-server="$MPV_SOCKET" &
    MPV_PID=$!

    # Wait for socket, then set initial playback speed
    for _ in $(seq 1 30); do
        sleep 0.1
        if [ -S "$MPV_SOCKET" ]; then
            printf '{"command":["set_property","speed",%s]}\n' "$INITIAL_SPEED" \
                | socat - "$MPV_SOCKET" 2>/dev/null
            break
        fi
    done

    # ── Background: append remaining segments in order via IPC ──────────────
    (
        CURRENT_IDX=0
        while true; do
            NEXT_IDX=$((CURRENT_IDX + 1))
            NEXT_FILE="$WORK_DIR/seg_$(printf "%03d" "$NEXT_IDX").mp3"

            if [ -f "$NEXT_FILE" ] && [ -s "$NEXT_FILE" ]; then
                if [ -S "$MPV_SOCKET" ]; then
                    printf '{"command":["loadfile","%s","append"]}\n' "$NEXT_FILE" \
                        | socat - "$MPV_SOCKET" 2>/dev/null
                fi
                CURRENT_IDX=$NEXT_IDX
            fi

            # Check if all generation jobs are done
            ALL_DONE=1
            for pid in $PIDS; do
                if kill -0 "$pid" 2>/dev/null; then
                    ALL_DONE=0
                    break
                fi
            done

            if [ "$ALL_DONE" -eq 1 ] && [ "$NEXT_IDX" -ge "$SEG_COUNT" ]; then
                break
            fi
            sleep 0.3
        done
    ) &

    # ── Wait for all generation to complete (foreground) ──────────────────
    FAILED=0
    for pid in $PIDS; do
        wait "$pid" || FAILED=1
    done

    if [ "$FAILED" -ne 0 ]; then
        ERR_MSG=$(cat "$WORK_DIR"/err_*.txt 2>/dev/null | grep -v '^+' | grep . | head -1)
        # Don't kill mpv — let partial playback continue for better UX
        notify-send "TTS Warning" "${ERR_MSG:-Some segments failed to generate.}"
    fi

    # A newer invocation may have asked us to stop
    if [ -f "$INTERRUPT_FLAG" ]; then
        exit 0
    fi

    # Hold the lock while mpv plays; a new instance interrupts us by sending
    # "quit" over the socket, which makes this wait return.
    wait "$MPV_PID"
    rm -f "$MPV_SOCKET"

    # Export to file if --output was requested
    if [ -n "$OUTPUT_FILE" ]; then
        mapfile -t FILES < <(find "$WORK_DIR" -maxdepth 1 -name 'seg_*.mp3' | sort)
        if command -v ffmpeg &>/dev/null; then
            LIST_FILE=$(mktemp)
            for f in "${FILES[@]}"; do
                printf "file '%s'\n" "$f" >> "$LIST_FILE"
            done
            ffmpeg -y -f concat -safe 0 -i "$LIST_FILE" -c copy "$OUTPUT_FILE" 2>/dev/null
            rm -f "$LIST_FILE"
        else
            cat "${FILES[@]}" > "$OUTPUT_FILE"
        fi
        notify-send "TTS Export" "Saved audio to $OUTPUT_FILE"
    fi

# ═════════════════════════════════════════════════════════════════════════════
# SHORTCUT MODE  (keyboard shortcut, no --text arg)
# ─────────────────────────────────────────────────────────────────────────────
# Progressive playback: start mpv as soon as the first segment is ready,
# then append remaining segments via IPC while generation continues.
# ═════════════════════════════════════════════════════════════════════════════
else

    # Generate all audio files in parallel
    PIDS=""
    for i in $(seq 0 $((SEG_COUNT - 1))); do
        PAD=$(printf "%03d" "$i")
        LANG=$(cat "$WORK_DIR/seg_${PAD}.lang")
        SEG_TEXT=$(cat "$WORK_DIR/seg_${PAD}.txt")
        AUDIO="$WORK_DIR/seg_${PAD}.mp3"

        if [ "$LANG" = "ar" ]; then VOICE="$AR_VOICE"; RATE="$AR_RATE"
        elif [ "$LANG" = "de" ]; then VOICE="$DE_VOICE"; RATE="$DE_RATE"
        else VOICE="$EN_VOICE"; RATE="$EN_RATE"; fi

        (
            CACHED=$(cache_path "$VOICE" "$RATE" "$SEG_TEXT")
            if [ -f "$CACHED" ]; then
                cp "$CACHED" "$AUDIO"
            else
                if ! generate_audio "$VOICE" "$RATE" "$SEG_TEXT" "$AUDIO" 2>"$WORK_DIR/err_${PAD}.txt"; then
                    exit 1
                fi
                cache_store "$AUDIO" "$CACHED"
            fi
        ) &
        PIDS="$PIDS $!"
    done

    # ── Progressive playback: start mpv on first ready segment ──────────────
    FIRST_FILE=""
    for _ in $(seq 1 300); do
        FIRST_FILE=$(find "$WORK_DIR" -maxdepth 1 -name 'seg_*.mp3' | sort | head -n1)
        [ -n "$FIRST_FILE" ] && break
        sleep 0.1
    done

    if [ -z "$FIRST_FILE" ]; then
        FAILED=0
        for pid in $PIDS; do
            wait "$pid" || FAILED=1
        done
        ERR_MSG=$(cat "$WORK_DIR"/err_*.txt 2>/dev/null | grep -v '^+' | grep . | head -1)
        notify-send "TTS Error" "${ERR_MSG:-Failed to generate speech. Check your internet connection.}"
        exit 1
    fi

    # A newer invocation may have asked us to stop while we were generating
    if [ -f "$INTERRUPT_FLAG" ]; then
        exit 0
    fi

    rm -f "$MPV_SOCKET"
    mpv "$FIRST_FILE" --no-terminal --input-ipc-server="$MPV_SOCKET" &
    MPV_PID=$!

    # ── Background: append remaining segments in order via IPC ──────────────
    (
        CURRENT_IDX=0
        while true; do
            NEXT_IDX=$((CURRENT_IDX + 1))
            NEXT_FILE="$WORK_DIR/seg_$(printf "%03d" "$NEXT_IDX").mp3"

            if [ -f "$NEXT_FILE" ] && [ -s "$NEXT_FILE" ]; then
                if [ -S "$MPV_SOCKET" ]; then
                    printf '{"command":["loadfile","%s","append"]}\n' "$NEXT_FILE" \
                        | socat - "$MPV_SOCKET" 2>/dev/null
                fi
                CURRENT_IDX=$NEXT_IDX
            fi

            ALL_DONE=1
            for pid in $PIDS; do
                if kill -0 "$pid" 2>/dev/null; then
                    ALL_DONE=0
                    break
                fi
            done

            if [ "$ALL_DONE" -eq 1 ] && [ "$NEXT_IDX" -ge "$SEG_COUNT" ]; then
                break
            fi
            sleep 0.3
        done
    ) &

    # ── Wait for all generation to complete (foreground) ────────────────────
    FAILED=0
    for pid in $PIDS; do
        wait "$pid" || FAILED=1
    done

    if [ "$FAILED" -ne 0 ]; then
        ERR_MSG=$(cat "$WORK_DIR"/err_*.txt 2>/dev/null | grep -v '^+' | grep . | head -1)
        notify-send "TTS Warning" "${ERR_MSG:-Some segments failed to generate.}"
    fi

    # A newer invocation may have asked us to stop
    if [ -f "$INTERRUPT_FLAG" ]; then
        exit 0
    fi

    # Export to file if --output was requested
    if [ -n "$OUTPUT_FILE" ]; then
        mapfile -t FILES < <(find "$WORK_DIR" -maxdepth 1 -name 'seg_*.mp3' | sort)
        if command -v ffmpeg &>/dev/null; then
            LIST_FILE=$(mktemp)
            for f in "${FILES[@]}"; do
                printf "file '%s'\n" "$f" >> "$LIST_FILE"
            done
            ffmpeg -y -f concat -safe 0 -i "$LIST_FILE" -c copy "$OUTPUT_FILE" 2>/dev/null
            rm -f "$LIST_FILE"
        else
            cat "${FILES[@]}" > "$OUTPUT_FILE"
        fi
        notify-send "TTS Export" "Saved audio to $OUTPUT_FILE"
    fi

    # Hold the lock while mpv plays; a new instance interrupts us by sending
    # "quit" over the socket, which makes this wait return.
    wait "$MPV_PID"
    rm -f "$MPV_SOCKET"

fi
