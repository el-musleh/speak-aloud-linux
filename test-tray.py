#!/usr/bin/env python3
"""
Tray Icon Test — demonstrates the TTS tray status feature.

Run this to verify the tray icon appears and updates correctly.
"""

import gi
try:
    gi.require_version('AppIndicator3', '0.1')
except ValueError:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3
    import sys
    mod = type(sys)('gi.repository.AppIndicator3')
    for attr in dir(AyatanaAppIndicator3):
        if not attr.startswith('_'):
            setattr(mod, attr, getattr(AyatanaAppIndicator3, attr))
    sys.modules['gi.repository.AppIndicator3'] = mod

import pystray
from PIL import Image, ImageDraw
import time
import threading


def create_icon(color=(66, 133, 244)):
    """Create a simple colored circle icon."""
    img = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
    dc = ImageDraw.Draw(img)
    dc.ellipse([4, 4, 60, 60], fill=(*color, 255))
    return img


# Simulate the TTS states
STATES = [
    ('○  Ready', (100, 100, 100)),
    ('⟳  Generating audio…', (255, 193, 7)),
    ('⟳  Retrying network…', (255, 87, 34)),
    ('♪  Playing', (76, 175, 80)),
    ('○  Ready', (100, 100, 100)),
]


def build_menu():
    return pystray.Menu(
        pystray.MenuItem('Show TTS App', lambda i, item: print('Show clicked')),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: current_status, None, enabled=False),
        pystray.MenuItem('▶  Play / Pause', lambda i, item: print('Play/Pause clicked')),
        pystray.MenuItem('⏹  Stop', lambda i, item: print('Stop clicked')),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Quit', lambda i, item: i.stop()),
    )


current_status = '○  Ready'
icon = None


def cycle_states():
    """Cycle through states every 3 seconds to demonstrate updates."""
    global current_status, icon
    for status, color in STATES:
        if not icon.visible:
            break
        current_status = status
        icon.title = f'Speak a Loud — {status}'
        icon.icon = create_icon(color)
        try:
            icon.update_menu()
        except Exception:
            pass
        print(f'  → State: {status}')
        time.sleep(3)
    icon.stop()


def main():
    global icon
    print('Starting tray icon test...')
    print('Look for a colored circle in your system tray (near the clock).')
    print('Right-click it to see the menu with status.')
    print('')

    icon = pystray.Icon(
        'tts-test',
        icon=create_icon(),
        title='Speak a Loud — ○ Ready',
        menu=build_menu(),
    )

    # Start state cycler in background
    threading.Thread(target=cycle_states, daemon=True).start()

    print('Running for ~15 seconds, cycling through states...')
    icon.run()
    print('\nTest complete. Tray icon closed.')


if __name__ == '__main__':
    main()
