# Translation & Language Override Feature — Change Log

## New Files

### `translate_text.py` (119 lines)
- Standalone Python helper for pre-speech text translation.
- **No external dependencies** — uses only `urllib` from stdlib.
- **DeepL backend**: calls `api-free.deepl.com` (default) or `api.deepl.com` (with `--pro`). Accepts target language, API key. Returns translated text or human-readable error.
- **Google Cloud Translation v2 backend**: POSTs to `translation.googleapis.com` with API key in query string. Same interface.
- Reads text from `--text` argument or **stdin**.
- Exits `0` on success (translated text on stdout), `1` on failure (error on stderr).

## Modified Files

### `speak.sh`
1. **New CLI flags**:
   - `--source-lang` — force source language (`auto`, `en`, `ar`, `de`, …)
   - `--translate-enabled` (`yes`/`no`)
   - `--translate-provider` (`deepl` | `google`)
   - `--translate-target` — ISO language code
   - `--translate-api-key` — free-form key string

2. **Config file reading** — reads 5 new settings from `~/.config/tts_settings/`:
   - `source_language`, `translate_enabled`, `translate_provider`, `translate_target`, `translate_api_key`

3. **Cache key updated** — includes `provider:target` when translation is active so "same text, different target" doesn't collide.

4. **Translation step** — before segmentation, if `translate_enabled=yes` and key/target are set, calls `translate_text.py` via stdin. On error:
   - GUI mode: `STATUS:ERROR` + notification
   - Shortcut mode: silent exit (no interrupting the user)

5. **Source-language override** — when `source_lang != auto`, skips the entire Python segmentation/classification heredoc. Writes a single `seg_000` with the forced language.

6. **`sanitize_for_voice()`** — strips characters the assigned voice cannot pronounce:
   - Arabic voice: keeps Arabic script + basic punctuation
   - Latin voices (en/de): strips CJK, Cyrillic, Hebrew, emojis, zero-width chars, symbols
   - Prevents `edge-tts` `NoAudioReceived` on unsupported-script text.

7. **`unidecode` transliteration fallback** — if sanitization strips everything (pure CJK/Cyrillic text), attempts to romanize with `unidecode` (if installed) and speaks the result via the English voice.
   - `你好世界` → `Ni Hao Shi Jie`
   - `Привет мир` → `Privet mir`

8. **Error message cleanup** — both `ERR_MSG` extraction sites now filter `grep -v '^+'` to prevent `bash -x` trace lines from leaking into user-facing notifications.

### `tts-app.py`
1. **New helper** `read_bool_setting()` — parses `yes`/`no` setting files into booleans.

2. **New data tables**:
   - `SOURCE_LANGUAGES` — `auto`, `en`, `ar`, `de`
   - `TRANSLATION_LANGUAGES` — 16 entries (`None`, `en`, `ar`, `de`, `fr`, `es`, `pt`, `it`, `nl`, `ru`, `zh`, `ja`, `ko`, `tr`, `pl`, `hi`)
   - `TRANSLATION_PROVIDERS` — `deepl`, `google`

3. **New UI controls** in `_build_ui()`:
   - **Source Language** dropdown (`Adw.ComboRow`) — selects auto-detect or forced language
   - **Translation section** (`Adw.PreferencesGroup`):
     - Enable toggle (`Gtk.Switch`) — sensitives/desenitizes the fields below
     - Provider dropdown (`Adw.ComboRow`)
     - Target language dropdown (`Adw.ComboRow`)
     - API key entry (`Adw.PasswordEntryRow` — password-style with reveal)

4. **`_on_trans_enabled_changed()`** — callback linked to the toggle. Enables/disables provider, target, and API key fields when translation is turned on/off.

5. **`_load_saved_settings()`** — loads and restores all 5 new persisted settings on app startup.

6. **`_start_speaking()`** — collects new settings from UI, passes them to `speak.sh` via new CLI flags, and saves settings before starting generation.

7. **`_save_settings()` signature expanded** — accepts `src_lang`, `trans_enabled`, `trans_provider`, `trans_target`, `trans_key`. Persists all 5 new settings to `~/.config/tts_settings/`.

### `tts-settings.sh`
1. **Loads 5 new settings** from `~/.config/tts_settings/` with defaults.

2. **New `yad` form fields**:
   - Source Language (`CB`) — `auto!en!ar!de`
   - Translate Enabled (`CHK`) — checkbox
   - Translate Provider (`CB`) — `deepl!google`
   - Translate Target (`CB`) — 16 language options
   - Translate API Key (`TEXT`) — plain text field

3. **Field extraction** — reads fields 9–13 from the `|` delimited `yad` output.

4. **Persistence** — writes all 5 new values back to `~/.config/tts_settings/` on Save.

## Settings Persistence

All new settings are stored in `~/.config/tts_settings/` as single-line flat files (same pattern as existing voice/rate/speed settings):

| File | Default | GUI Widget | speak.sh flag |
|------|---------|------------|---------------|
| `source_language` | `auto` | `Adw.ComboRow` | `--source-lang` |
| `translate_enabled` | `no` | `Gtk.Switch` | `--translate-enabled` |
| `translate_provider` | `deepl` | `Adw.ComboRow` | `--translate-provider` |
| `translate_target` | `*`empty* | `Adw.ComboRow` | `--translate-target` |
| `translate_api_key` | `*`empty* | `Adw.PasswordEntryRow` | `--translate-api-key` |

## Interaction Matrix

| Source Lang | Translate | Effective Behavior |
|-------------|-----------|--------------------|
| `auto` | Off | Auto-detect Arabic/German/English per segment (existing behavior) |
| `auto` | On → `ar` | Translate input to Arabic, then detect as Arabic voice |
| `en` | Off | Force English voice for all text |
| `en` | On → `de` | Translate to German, then force English voice (override wins) |
| `ar` | Off | Force Arabic voice for all text |
| `ar` | On → `en` | Translate to English, then force Arabic voice (override wins) |

## Backwards Compatibility

- All new CLI flags are optional — existing scripts continue to work unchanged.
- All new config files have defaults — existing installations need no migration.
- `tts-settings.sh` is optional — users of the GTK GUI don't need `yad`.

## Dependencies

- `unidecode` — **optional**. If present, enables transliteration of unsupported scripts (CJK, Cyrillic, etc.). If absent, pure unsupported-script text gracefully errors with *"Text contains no speakable content"*.
