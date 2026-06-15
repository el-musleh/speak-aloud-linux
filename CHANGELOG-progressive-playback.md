# Progressive Playback & Sentence Splitting — Change Log

## Problem

Long text (>1000 chars) caused long startup delays because `speak.sh`:
1. Generated **all** MP3 segments in parallel, then
2. Waited for **all** of them to finish before starting `mpv`

For 5000 chars of English, this meant ~10-15s of silent waiting before hearing anything.

## Solution

Two changes to `speak.sh`:
1. **Sentence-level splitting** — break large language segments into ~600-char sentence-sized chunks
2. **Progressive playback** — start `mpv` as soon as the first chunk is ready, append remaining chunks via IPC while generation continues

---

## Modified Files

### `speak.sh`

#### 1. `split_long_segments()` (new function, ~50 lines)

Runs **after** language detection but **before** TTS generation.

- **Trigger**: any monolingual segment > `MAX_SEGMENT_CHARS`
- **Strategy**: split at sentence boundaries (`. `, `! `, `? `)
- **Abbreviation protection**: common abbreviations (`Dr.`, `Mr.`, `Mrs.`, `e.g.`, `i.e.`, etc.) are temporarily masked before splitting
- **Double-newline splitting**: `\n\n` also acts as a boundary
- **Merging**: short consecutive sentences are merged back together to stay efficient (merge while total < max)
- **Staging directory**: uses `$WORK_DIR/.staging` to avoid re-indexing collisions during the split pass

**Parameters**:
| Constant | Value | Rationale |
|----------|-------|-----------|
| `MAX_SEGMENT_CHARS` | `600` | Balances TTS round-trip overhead vs. startup latency; most 600-char English text generates in ~2-3s |

#### 2. GUI Mode — Progressive Playback

**Before**:
```
for each segment → launch edge-tts in parallel
for each PID → wait for ALL to finish
if any failed → error and exit
start mpv with ALL files
```

**After**:
```
for each segment → launch edge-tts in parallel
poll for seg_000.mp3 (max 30s)
start mpv with ONLY seg_000.mp3
background loop → watch seg_001, seg_002... → append via IPC when ready
main thread → wait for remaining generation
if any failed → notify warning, but KEEP mpv playing
```

**Key changes**:
- `STATUS:PLAYING` is emitted as soon as the first audio starts (not after all generation)
- `FIRST_FILE` is hardcoded to `$WORK_DIR/seg_000.mp3` — guarantees in-order playback start
- Background subshell polls every 0.3s for the next `seg_NNN.mp3` and sends `{"command":["loadfile","...","append"]}` to the mpv IPC socket
- The append loop exits when all generation jobs are done AND the last file has been appended
- Generation errors are downgraded from fatal (`STATUS:ERROR`) to a `notify-send` warning — partial playback continues

#### 3. Shortcut Mode — Progressive Playback

Same pattern applied to the `else` (shortcut/keyboard) branch:
- No `STATUS:*` lines (shortcut mode has no GUI to update)
- Uses per-language `--rate` (baked into audio, no live speed control)
- Otherwise identical: start mpv on first ready segment, append rest via IPC

#### 4. Out-of-Order Safety

The first-file wait specifically targets `seg_000.mp3` instead of `find ... | sort | head -n1`. This prevents a cached later segment (e.g., `seg_003.mp3` from a prior run) from being picked up first and causing playback to skip earlier content.

---

## Performance Impact

| Text length | Before | After |
|-------------|--------|-------|
| 300 chars (1 segment) | ~2-3s | ~2-3s (no change) |
| 1000 chars (2 segments) | ~5-6s | ~2-3s |
| 5000 chars (8-10 segments) | ~10-15s | ~2-3s |

*Times are approximate and depend on network latency to Microsoft TTS service.*

---

## Backwards Compatibility

- No new CLI flags — fully transparent to `tts-app.py`
- `--output FILE.mp3` still works: export happens after mpv playback finishes, using all successfully generated segments
- Cache key unchanged — cached segments are still reused normally
- Interrupt handling unchanged — new invocation via socket still cleanly stops playback

---

## Edge Cases Handled

1. **All cached**: if every segment is cached, `seg_000.mp3` appears in <100ms → playback starts almost instantly
2. **First segment fails**: falls back to waiting for all jobs, then reports error (original behavior)
3. **Later segment fails**: warning notification, but mpv keeps playing what was generated
4. **Single huge sentence (>600 chars)**: the merge step will still keep it in one chunk; if that's still too slow, decrease `MAX_SEGMENT_CHARS`
5. **User interrupts mid-generation**: `INTERRUPT_FLAG` checked before mpv launch and after generation wait
