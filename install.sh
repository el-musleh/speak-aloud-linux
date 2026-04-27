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
USERNAME="$(whoami)"

echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}${BOLD}║   Speak a Loud Universal — Installer     ║${RESET}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1: System packages ──────────────────
echo -e "${BOLD}[1/5] Installing system dependencies...${RESET}"
sudo apt update -qq
sudo apt install -y pipx mpv xsel yad socat wl-clipboard \
                    python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
echo -e "${GREEN}✓ System packages ready${RESET}"
echo ""

# ── Step 2: edge-tts ─────────────────────────
echo -e "${BOLD}[2/5] Installing edge-tts...${RESET}"
pipx ensurepath --force > /dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"
pipx install edge-tts 2>/dev/null || pipx upgrade edge-tts
echo -e "${GREEN}✓ edge-tts ready${RESET}"
echo ""

# ── Step 3: Config files ─────────────────────
echo -e "${BOLD}[3/5] Setting up config files...${RESET}"
mkdir -p ~/.config/tts_settings

[ ! -f ~/.config/tts_settings/voice ]        && echo "en-US-ChristopherNeural" > ~/.config/tts_settings/voice
[ ! -f ~/.config/tts_settings/arabic_voice ] && echo "ar-SA-HamedNeural"       > ~/.config/tts_settings/arabic_voice
[ ! -f ~/.config/tts_settings/rate ]         && echo "+50%"                    > ~/.config/tts_settings/rate
[ ! -f ~/.config/tts_settings/arabic_rate ]  && echo "+30%"                    > ~/.config/tts_settings/arabic_rate

echo -e "${GREEN}✓ Config files ready at ~/.config/tts_settings/${RESET}"
echo ""

# ── Step 4: Make scripts executable ──────────
echo -e "${BOLD}[4/5] Setting permissions...${RESET}"
chmod +x "$SCRIPT_DIR/speak.sh"
chmod +x "$SCRIPT_DIR/speak-pause.sh"
chmod +x "$SCRIPT_DIR/tts-settings.sh"
chmod +x "$SCRIPT_DIR/tts-app.py"
echo -e "${GREEN}✓ Scripts are executable${RESET}"
echo ""

# ── Step 5: Verify GTK4 / Libadwaita ─────────
echo -e "${BOLD}[5/5] Verifying GTK4 + Libadwaita Python bindings...${RESET}"
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

# ── Done ─────────────────────────────────────
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  Installation complete!${RESET}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "${BOLD}Run the GUI app anytime with:${RESET}"
echo -e "  ${CYAN}python3 $SCRIPT_DIR/tts-app.py${RESET}"
echo ""
echo -e "${BOLD}Add these keyboard shortcuts in Linux Mint:${RESET}"
echo -e "  ${CYAN}Mint Menu → System Settings → Keyboard → Shortcuts → Custom Shortcuts${RESET}"
echo ""
echo -e "  ${YELLOW}┌──────────────────────┬──────────────────────────────────────────────────────────────────┬──────────────────────┐${RESET}"
echo -e "  ${YELLOW}│ Name                 │ Command                                                          │ Shortcut             │${RESET}"
echo -e "  ${YELLOW}├──────────────────────┼──────────────────────────────────────────────────────────────────┼──────────────────────┤${RESET}"
echo -e "  ${YELLOW}│ Speak Selection      │ ${RESET}/home/${USERNAME}/speak-aloud-linux/speak.sh                 ${YELLOW}│ Super + S            │${RESET}"
echo -e "  ${YELLOW}│ Pause / Resume       │ ${RESET}/home/${USERNAME}/speak-aloud-linux/speak-pause.sh          ${YELLOW}│ Super + P            │${RESET}"
echo -e "  ${YELLOW}│ Stop Speech          │ ${RESET}pkill -f mpv                                                ${YELLOW}│ Super + Shift + S    │${RESET}"
echo -e "  ${YELLOW}│ TTS Settings (CLI)   │ ${RESET}/home/${USERNAME}/speak-aloud-linux/tts-settings.sh         ${YELLOW}│ Super + T            │${RESET}"
echo -e "  ${YELLOW}│ TTS App (GUI)        │ ${RESET}python3 /home/${USERNAME}/speak-aloud-linux/tts-app.py      ${YELLOW}│ Super + A            │${RESET}"
echo -e "  ${YELLOW}└──────────────────────┴──────────────────────────────────────────────────────────────────┴──────────────────────┘${RESET}"
echo ""
echo -e "  ${BOLD}Tips:${RESET}"
echo -e "  • ${CYAN}Super + S${RESET}  — highlight text anywhere, press to hear it"
echo -e "  • ${CYAN}Super + A${RESET}  — open the GTK4 GUI app (voice/speed controls + preview)"
echo -e "  • ${CYAN}Super + P${RESET}  — pause or resume mid-playback"
echo -e "  • Arabic and English segments are detected and spoken with separate voices"
echo ""
