#!/bin/bash

# ─────────────────────────────────────────────
#  Speak a Loud Universal — Installer
# ─────────────────────────────────────────────

set -e

BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RESET="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}${BOLD}║   Speak a Loud Universal — One-Click Installer   ║${RESET}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1: System packages ──────────────────
echo -e "${BOLD}[1/7] Installing system dependencies...${RESET}"
sudo apt update -qq

# Check if mpv is already installed
if command -v mpv &> /dev/null; then
    echo -e "${GREEN}✓ mpv already installed${RESET}"
    MPV_INSTALL=""
else
    echo -e "${YELLOW}mpv not found, will install${RESET}"
    MPV_INSTALL="mpv"
fi

# Install packages with validation
PACKAGES=(pipx xsel yad socat wl-clipboard python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-pil python3-pip file)
[ -n "$MPV_INSTALL" ] && PACKAGES+=("$MPV_INSTALL")
echo "Installing packages: ${PACKAGES[*]}"

if sudo apt install -y "${PACKAGES[@]}"; then
    echo -e "${GREEN}✓ System packages installed successfully${RESET}"
else
    echo -e "${YELLOW}⚠ Some packages may have failed to install${RESET}"
    # Check critical packages
    MISSING_CRITICAL=""
    for pkg in pipx mpv xsel; do
        if ! command -v "$pkg" &>/dev/null; then
            MISSING_CRITICAL="$MISSING_CRITICAL $pkg"
        fi
    done
    if [ -n "$MISSING_CRITICAL" ]; then
        echo -e "${YELLOW}⚠ Critical packages missing:$MISSING_CRITICAL${RESET}"
        echo -e "Please install them manually: ${CYAN}sudo apt install$MISSING_CRITICAL${RESET}"
    fi
fi

# ── Step 2: edge-tts ─────────────────────────
echo -e "${BOLD}[2/6] Installing edge-tts...${RESET}"
pipx ensurepath --force > /dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"
pipx install edge-tts 2>/dev/null || pipx upgrade edge-tts

# Verify edge-tts is actually callable
if command -v edge-tts &>/dev/null; then
    echo -e "${GREEN}✓ edge-tts ready${RESET}"
else
    echo -e "${YELLOW}⚠ edge-tts not in PATH. You may need to:${RESET}"
    echo -e "  ${CYAN}source ~/.profile && export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
fi

# Optional: pystray for the system-tray icon (GUI app degrades gracefully without it)
if ! python3 -c "import pystray" 2>/dev/null; then
    echo "Installing pystray (system-tray support)..."
    if python3 -m pip install --user pystray 2>/dev/null; then
        echo -e "${GREEN}✓ pystray installed (user)${RESET}"
    elif python3 -m pip install --break-system-packages pystray 2>/dev/null; then
        echo -e "${GREEN}✓ pystray installed (system)${RESET}"
    else
        echo -e "${YELLOW}⚠ pystray install failed — tray icon will be disabled (GUI still works)${RESET}"
    fi
fi
echo ""

# ── Step 3: Config files ─────────────────────
echo -e "${BOLD}[3/7] Setting up config files...${RESET}"
mkdir -p ~/.config/tts_settings

[ ! -f ~/.config/tts_settings/voice ]        && echo "en-US-ChristopherNeural" > ~/.config/tts_settings/voice
[ ! -f ~/.config/tts_settings/arabic_voice ] && echo "ar-SA-HamedNeural"       > ~/.config/tts_settings/arabic_voice
[ ! -f ~/.config/tts_settings/german_voice ] && echo "de-DE-ConradNeural"      > ~/.config/tts_settings/german_voice
[ ! -f ~/.config/tts_settings/rate ]         && echo "+50%"                    > ~/.config/tts_settings/rate
[ ! -f ~/.config/tts_settings/arabic_rate ]  && echo "+30%"                    > ~/.config/tts_settings/arabic_rate
[ ! -f ~/.config/tts_settings/german_rate ]  && echo "+30%"                    > ~/.config/tts_settings/german_rate
[ ! -f ~/.config/tts_settings/global_speed ] && echo "1.5"                     > ~/.config/tts_settings/global_speed

echo -e "${GREEN}✓ Config files ready at ~/.config/tts_settings/${RESET}"
echo ""

# ── Step 4: Make scripts executable ──────────
echo -e "${BOLD}[4/6] Setting permissions...${RESET}"
chmod +x "$SCRIPT_DIR/speak.sh"
chmod +x "$SCRIPT_DIR/speak-pause.sh"
chmod +x "$SCRIPT_DIR/speak-stop.sh"
chmod +x "$SCRIPT_DIR/tts-settings.sh"
chmod +x "$SCRIPT_DIR/tts-app.py"
chmod +x "$SCRIPT_DIR/setup-tts-shortcuts.sh"
echo -e "${GREEN}✓ Scripts are executable${RESET}"
echo ""

# ── Step 5: Desktop entry ────────────────────
echo -e "${BOLD}[5/6] Adding to app menu...${RESET}"
DESKTOP_FILE="$HOME/.local/share/applications/speak-aloud.desktop"
mkdir -p "$HOME/.local/share/applications"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Speak a Loud
Comment=Text-to-Speech with GTK4 GUI
Exec=python3 $SCRIPT_DIR/tts-app.py
Icon=audio-speakers
Type=Application
Terminal=false
Categories=AudioVideo;Audio;Utility;
Keywords=tts;speech;text-to-speech;audio;read aloud;
EOF
echo -e "${GREEN}✓ App menu entry created${RESET}"
echo ""

# ── Step 6: Verify GTK4 / Libadwaita ─────────
echo -e "${BOLD}[6/7] Verifying GTK4 + Libadwaita Python bindings...${RESET}"
MISSING=0
if ! python3 -c "import gi; gi.require_version('Gtk', '4.0')" 2>/dev/null; then
    echo -e "${YELLOW}⚠ GTK 4.0 Python bindings not found.${RESET}"
    MISSING=1
fi
if ! python3 -c "import gi; gi.require_version('Adw', '1')" 2>/dev/null; then
    echo -e "${YELLOW}⚠ Libadwaita (Adw) 1.0 Python bindings not found.${RESET}"
    MISSING=1
fi

if [ $MISSING -eq 0 ]; then
    echo -e "${GREEN}✓ GTK4 / Libadwaita bindings OK${RESET}"
else
    echo -e "${YELLOW}The GUI app (tts-app.py) requires these bindings to run.${RESET}"
    echo -e "Try installing them manually: ${CYAN}sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1${RESET}"
fi
echo ""

# ── Step 6: Keyboard shortcuts (Cinnamon) ────
echo -e "${BOLD}[7/7] Keyboard shortcuts...${RESET}"

SHORTCUTS_CONFIGURED=0

add_or_update_shortcut() {
    local name="$1" command="$2" binding="$3"
    local schema="org.cinnamon.desktop.keybindings"
    local list slot num existing_cmd

    list=$(gsettings get "$schema" custom-list)

    # Look for an existing slot with the same command (idempotent update)
    for slot in $(echo "$list" | grep -o "custom[0-9]*"); do
        local path="/org/cinnamon/desktop/keybindings/custom-keybindings/${slot}/"
        existing_cmd=$(gsettings get "${schema}.custom-keybinding:${path}" command 2>/dev/null | sed "s/^'//;s/'$//")
        if [ "$existing_cmd" = "$command" ]; then
            gsettings set "${schema}.custom-keybinding:${path}" name "$name"
            gsettings set "${schema}.custom-keybinding:${path}" binding "$binding"
            echo -e "  ${GREEN}✓ Updated:${RESET} $name (${slot})"
            return 0
        fi
    done

    # Find next free slot number
    num=0
    while echo "$list" | grep -q "'custom${num}'"; do
        num=$((num + 1))
    done
    slot="custom${num}"

    local path="/org/cinnamon/desktop/keybindings/custom-keybindings/${slot}/"
    gsettings set "${schema}.custom-keybinding:${path}" name "$name"
    gsettings set "${schema}.custom-keybinding:${path}" command "$command"
    gsettings set "${schema}.custom-keybinding:${path}" binding "$binding"

    # Append slot to custom-list
    if [ "$list" = "[]" ] || [ "$list" = "@as []" ]; then
        gsettings set "$schema" custom-list "['${slot}']"
    else
        local replacement=", '${slot}']"
        gsettings set "$schema" custom-list "${list//]/$replacement}"
    fi
    echo -e "  ${GREEN}✓ Added:${RESET} $name (${slot})"
}

if gsettings list-schemas 2>/dev/null | grep -q "org.cinnamon.desktop.keybindings"; then
    echo -e "This will register these shortcuts in Cinnamon:"
    echo -e "  ${CYAN}Super+S${RESET} Speak Selection   ${CYAN}Super+P${RESET} Pause/Resume   ${CYAN}Super+Shift+S${RESET} Stop"
    echo -e "  ${CYAN}Super+T${RESET} TTS Settings      ${CYAN}Super+A${RESET} TTS App (GUI)"
    read -r -p "Set up Cinnamon keyboard shortcuts automatically? [Y/n] " REPLY
    case "$REPLY" in
        [nN]*)
            echo -e "${YELLOW}Skipped. You can add them manually (see table below).${RESET}"
            ;;
        *)
            add_or_update_shortcut "Speak Selection"    "$SCRIPT_DIR/speak.sh"            "['<Super>s']"
            add_or_update_shortcut "Pause / Resume"     "$SCRIPT_DIR/speak-pause.sh"      "['<Super>p']"
            add_or_update_shortcut "Stop Speech"        "$SCRIPT_DIR/speak-stop.sh"       "['<Shift><Super>s']"
            add_or_update_shortcut "TTS Settings (CLI)" "$SCRIPT_DIR/tts-settings.sh"     "['<Super>t']"
            add_or_update_shortcut "TTS App (GUI)"      "python3 $SCRIPT_DIR/tts-app.py"  "['<Super>a']"
            SHORTCUTS_CONFIGURED=1
            echo -e "${GREEN}✓ Keyboard shortcuts configured${RESET}"
            ;;
    esac
else
    echo -e "${YELLOW}Cinnamon not detected — add shortcuts manually in your DE settings (see table below).${RESET}"
fi
echo ""

# ── Done ─────────────────────────────────────
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  Installation complete!${RESET}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "${BOLD}Launch the app:${RESET}"
echo -e "  • ${CYAN}App Menu → Speak a Loud${RESET} (GUI with tray icon)"
echo -e "  • ${CYAN}python3 $SCRIPT_DIR/tts-app.py${RESET}"
echo ""
if [ "$SHORTCUTS_CONFIGURED" -eq 1 ]; then
    echo -e "${GREEN}✓ Keyboard shortcuts are configured.${RESET}"
    echo -e "  ${YELLOW}Log out and back in (or press Alt+F2 then type 'r') for shortcuts to activate.${RESET}"
else
    echo -e "${BOLD}Add these keyboard shortcuts manually:${RESET}"
    echo -e "  ${CYAN}Linux Mint: System Settings → Keyboard → Shortcuts → Custom Shortcuts${RESET}"
    echo -e "  ${CYAN}GNOME:      Settings → Keyboard → Keyboard Shortcuts → Custom${RESET}"
    echo -e "  ${CYAN}KDE:        System Settings → Shortcuts → Custom Shortcuts${RESET}"
    echo ""
    echo -e "  ${YELLOW}Name                 │ Command                                          │ Shortcut${RESET}"
    echo -e "  ${YELLOW}─────────────────────┼──────────────────────────────────────────────────┼──────────────────${RESET}"
    echo -e "  Speak Selection      ${YELLOW}│${RESET} $SCRIPT_DIR/speak.sh ${YELLOW}│${RESET} Super + S"
    echo -e "  Pause / Resume       ${YELLOW}│${RESET} $SCRIPT_DIR/speak-pause.sh ${YELLOW}│${RESET} Super + P"
    echo -e "  Stop Speech          ${YELLOW}│${RESET} $SCRIPT_DIR/speak-stop.sh ${YELLOW}│${RESET} Super + Shift + S"
    echo -e "  TTS Settings (CLI)   ${YELLOW}│${RESET} $SCRIPT_DIR/tts-settings.sh ${YELLOW}│${RESET} Super + T"
    echo -e "  TTS App (GUI)        ${YELLOW}│${RESET} python3 $SCRIPT_DIR/tts-app.py ${YELLOW}│${RESET} Super + A"
fi
echo ""
echo -e "  ${BOLD}Quick start:${RESET}"
echo -e "  • ${CYAN}Super + S${RESET}  — highlight text anywhere, press to hear it"
echo -e "  • ${CYAN}Super + A${RESET}  — open the GTK4 GUI app (voice/speed controls + tray icon)"
echo -e "  • ${CYAN}Super + P${RESET}  — pause or resume mid-playback"
echo -e "  • Arabic and English segments are detected and spoken with separate voices"
echo ""
