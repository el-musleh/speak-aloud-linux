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
echo -e "${BOLD}[1/4] Installing system dependencies...${RESET}"
sudo apt update -qq
sudo apt install -y pipx mpv xsel yad socat
echo -e "${GREEN}✓ System packages ready${RESET}"
echo ""

# ── Step 2: edge-tts ─────────────────────────
echo -e "${BOLD}[2/4] Installing edge-tts...${RESET}"
pipx ensurepath --force > /dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"
pipx install edge-tts 2>/dev/null || pipx upgrade edge-tts
echo -e "${GREEN}✓ edge-tts ready${RESET}"
echo ""

# ── Step 3: Config files ─────────────────────
echo -e "${BOLD}[3/4] Setting up config files...${RESET}"
mkdir -p ~/.config/tts_settings

[ ! -f ~/.config/tts_settings/voice ]         && echo "en-US-ChristopherNeural" > ~/.config/tts_settings/voice
[ ! -f ~/.config/tts_settings/arabic_voice ]  && echo "ar-SA-HamedNeural"       > ~/.config/tts_settings/arabic_voice
[ ! -f ~/.config/tts_settings/rate ]          && echo "+50%"                    > ~/.config/tts_settings/rate
[ ! -f ~/.config/tts_settings/arabic_rate ]   && echo "+30%"                    > ~/.config/tts_settings/arabic_rate

echo -e "${GREEN}✓ Config files ready at ~/.config/tts_settings/${RESET}"
echo ""

# ── Step 4: Make scripts executable ──────────
echo -e "${BOLD}[4/4] Setting permissions...${RESET}"
chmod +x "$SCRIPT_DIR/speak.sh"
chmod +x "$SCRIPT_DIR/speak-pause.sh"
chmod +x "$SCRIPT_DIR/tts-settings.sh"
echo -e "${GREEN}✓ Scripts are executable${RESET}"
echo ""

# ── Done ─────────────────────────────────────
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  Installation complete!${RESET}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "${BOLD}Last step: add these keyboard shortcuts in Linux Mint.${RESET}"
echo ""
echo -e "  Go to: ${CYAN}Mint Menu → System Settings → Keyboard → Shortcuts → Custom Shortcuts${RESET}"
echo ""
echo -e "  ${YELLOW}┌──────────────────────┬────────────────────────────────────────────────────────────┬──────────────────────┐${RESET}"
echo -e "  ${YELLOW}│ Name                 │ Command                                                    │ Shortcut             │${RESET}"
echo -e "  ${YELLOW}├──────────────────────┼────────────────────────────────────────────────────────────┼──────────────────────┤${RESET}"
echo -e "  ${YELLOW}│ Speak Selection      │ ${RESET}/home/${USERNAME}/speak-aloud-linux/speak.sh           ${YELLOW}│ Super + S            │${RESET}"
echo -e "  ${YELLOW}│ Pause / Resume       │ ${RESET}/home/${USERNAME}/speak-aloud-linux/speak-pause.sh    ${YELLOW}│ Super + P            │${RESET}"
echo -e "  ${YELLOW}│ Stop Speech          │ ${RESET}pkill -f mpv                                          ${YELLOW}│ Super + Shift + S    │${RESET}"
echo -e "  ${YELLOW}│ TTS Settings         │ ${RESET}/home/${USERNAME}/speak-aloud-linux/tts-settings.sh   ${YELLOW}│ Super + T            │${RESET}"
echo -e "  ${YELLOW}└──────────────────────┴────────────────────────────────────────────────────────────┴──────────────────────┘${RESET}"
echo ""
echo -e "  ${BOLD}Tips:${RESET}"
echo -e "  • Highlight any text → ${CYAN}Super + S${RESET} to hear it"
echo -e "  • Arabic and English are detected and spoken with separate voices and speeds"
echo -e "  • ${CYAN}Super + P${RESET} pauses or resumes mid-playback"
echo -e "  • ${CYAN}Super + T${RESET} opens the settings GUI to change voices and speeds"
echo ""
