#!/bin/bash

# Setup TTS keyboard shortcuts for Cinnamon
# This script configures two custom keyboard shortcuts for TTS functionality

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# TTS shortcut configurations (parallel arrays)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHORTCUT_NAMES=(
    "Speak Selection"
    "Stop Speech"
)
SHORTCUT_COMMANDS=(
    "${SCRIPT_DIR}/speak.sh"
    "${SCRIPT_DIR}/speak-stop.sh"
)
SHORTCUT_BINDINGS=(
    "['<Super>s']"
    "['<Shift><Super>s']"
)

KEYBINDINGS_SCHEMA="org.cinnamon.desktop.keybindings"
CUSTOM_SCHEMA="org.cinnamon.desktop.keybindings.custom-keybinding"

# Function to find next available custom slot
find_next_slot() {
    local custom_list
    custom_list=$(gsettings get "$KEYBINDINGS_SCHEMA" custom-list)

    local next_num=0
    while echo "$custom_list" | grep -q "'custom${next_num}'"; do
        next_num=$((next_num + 1))
    done

    echo "custom${next_num}"
}

# Function to find an existing slot by shortcut name (for idempotency)
find_slot_by_name() {
    local name="$1"
    local custom_list slot existing_name
    custom_list=$(gsettings get "$KEYBINDINGS_SCHEMA" custom-list)

    for slot in $(echo "$custom_list" | grep -o "custom[0-9]\+"); do
        local path="/org/cinnamon/desktop/keybindings/custom-keybindings/${slot}/"
        existing_name=$(gsettings get "${CUSTOM_SCHEMA}:${path}" name 2>/dev/null | tr -d "'")
        if [[ "$existing_name" == "$name" ]]; then
            echo "$slot"
            return 0
        fi
    done
    return 1
}

# Function to append a slot to custom-list (safe GVariant manipulation)
append_to_custom_list() {
    local slot="$1"
    local current_list new_list
    current_list=$(gsettings get "$KEYBINDINGS_SCHEMA" custom-list)

    # Already present? Nothing to do.
    if echo "$current_list" | grep -q "'${slot}'"; then
        return 0
    fi

    if [[ "$current_list" == "[]" || "$current_list" == "@as []" ]]; then
        new_list="['${slot}']"
    else
        new_list="${current_list%]}, '${slot}']"
    fi

    gsettings set "$KEYBINDINGS_SCHEMA" custom-list "$new_list"
}

# Function to add or update a custom shortcut
add_shortcut() {
    local name="$1"
    local command="$2"
    local binding="$3"
    local slot action

    if slot=$(find_slot_by_name "$name"); then
        action="Updating"
    else
        slot=$(find_next_slot)
        action="Adding"
    fi

    local path="/org/cinnamon/desktop/keybindings/custom-keybindings/${slot}/"

    echo -e "${GREEN}${action} shortcut: ${name}${NC}"
    echo "  Slot: ${slot}"
    echo "  Command: ${command}"
    echo "  Binding: ${binding}"

    gsettings set "${CUSTOM_SCHEMA}:${path}" name "'${name}'"
    gsettings set "${CUSTOM_SCHEMA}:${path}" command "'${command}'"
    gsettings set "${CUSTOM_SCHEMA}:${path}" binding "${binding}"

    append_to_custom_list "$slot"

    echo -e "${GREEN}✓ Shortcut configured successfully${NC}"
}

# Main execution
echo -e "${YELLOW}=== TTS Keyboard Shortcuts Setup ===${NC}"
echo ""

# Check if running on Cinnamon
if ! gsettings list-schemas | grep -q "^${KEYBINDINGS_SCHEMA}$"; then
    echo -e "${RED}Error: Cinnamon desktop environment not detected${NC}"
    echo "This script only works with Cinnamon (Linux Mint default)"
    exit 1
fi

# Add each shortcut
for i in "${!SHORTCUT_NAMES[@]}"; do
    add_shortcut "${SHORTCUT_NAMES[$i]}" "${SHORTCUT_COMMANDS[$i]}" "${SHORTCUT_BINDINGS[$i]}"
    echo ""
done

echo -e "${GREEN}=== Setup Complete ===${NC}"
echo "You can now use the following shortcuts:"
echo "  • Super+S: Speak Selection"
echo "  • Shift+Super+S: Stop Speech"
echo ""
echo "To verify: open 'cinnamon-settings keyboard' and check the Custom Shortcuts tab"
