#!/usr/bin/env python3
"""Remote 95: a small, 90s-styled GTK 3 remote for Google TV / Android TV
sets (e.g. TCL 55Q750G).

Uses the same protocol as the Google TV phone remote, via the
androidtvremote2 library. The first run pairs with the TV: a code appears
on the TV screen and you type it into this terminal.

Usage:
    python googletv_remote.py <tv-ip>   # first time (remembers the IP)
    python googletv_remote.py                # afterwards

Keyboard shortcuts:
    Arrows = move, Enter = OK, Backspace/Esc = Back, H = Home,
    Space = Play/Pause, + / - = Volume, M = Mute, S = Settings,
    P = Power, Y = YouTube, N = Menu, < / > (or , / .) = Rewind / Fast forward
"""
import asyncio
import sys
import threading
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from androidtvremote2 import (AndroidTVRemote, CannotConnect,
                              ConnectionClosed, InvalidAuth)

CONFIG_DIR = Path.home() / '.googletv_remote'
CERT = CONFIG_DIR / 'cert.pem'
KEY = CONFIG_DIR / 'key.pem'
HOST_FILE = CONFIG_DIR / 'host.txt'
CLICKS_FILE = CONFIG_DIR / 'clicks.txt'   # the footer's "hit counter"
CLIENT_NAME = 'PC Remote'

# App name -> what to launch. Deep links open the app directly and are the
# most reliable. A bare package name (no "://") is launched through the Play
# Store's "launch" link instead, which works only if the TV's Play Store
# cooperates - so deep links are used wherever an app has one.
APPS = [
    ('YouTube', 'https://www.youtube.com'),
    ('Netflix', 'https://www.netflix.com/title'),
    ('Prime Video', 'https://app.primevideo.com'),
    ('Disney+', 'https://www.disneyplus.com'),
    ('Plex', 'plex://'),
    ('Spotify', 'spotify://'),
    ('Hulu', 'com.hulu.livingroomplus'),
    ('Max', 'com.wbd.stream'),
]

KEYBOARD = {
    Gdk.KEY_Up: 'DPAD_UP', Gdk.KEY_Down: 'DPAD_DOWN',
    Gdk.KEY_Left: 'DPAD_LEFT', Gdk.KEY_Right: 'DPAD_RIGHT',
    Gdk.KEY_Return: 'DPAD_CENTER', Gdk.KEY_KP_Enter: 'DPAD_CENTER',
    Gdk.KEY_BackSpace: 'BACK', Gdk.KEY_Escape: 'BACK',
    Gdk.KEY_h: 'HOME', Gdk.KEY_space: 'MEDIA_PLAY_PAUSE',
    Gdk.KEY_plus: 'VOLUME_UP', Gdk.KEY_equal: 'VOLUME_UP',
    Gdk.KEY_KP_Add: 'VOLUME_UP',
    Gdk.KEY_minus: 'VOLUME_DOWN', Gdk.KEY_KP_Subtract: 'VOLUME_DOWN',
    Gdk.KEY_m: 'VOLUME_MUTE', Gdk.KEY_s: 'SETTINGS',
    Gdk.KEY_p: 'POWER', Gdk.KEY_y: 'YOUTUBE', Gdk.KEY_n: 'MENU',
    Gdk.KEY_comma: 'MEDIA_REWIND', Gdk.KEY_less: 'MEDIA_REWIND',
    Gdk.KEY_period: 'MEDIA_FAST_FORWARD',
    Gdk.KEY_greater: 'MEDIA_FAST_FORWARD',
}
# Buttons that open an app rather than send a key
APP_BUTTONS = {'YOUTUBE': ('YouTube', 'https://www.youtube.com')}

# Shown in the tooltips and the status bar when hovering a button
SHORTCUTS = {
    'DPAD_UP': 'Up arrow', 'DPAD_DOWN': 'Down arrow',
    'DPAD_LEFT': 'Left arrow', 'DPAD_RIGHT': 'Right arrow',
    'DPAD_CENTER': 'Enter', 'BACK': 'Backspace / Esc', 'HOME': 'H',
    'MEDIA_PLAY_PAUSE': 'Space', 'VOLUME_UP': '+', 'VOLUME_DOWN': '-',
    'VOLUME_MUTE': 'M', 'SETTINGS': 'S', 'POWER': 'P', 'YOUTUBE': 'Y',
    'MENU': 'N', 'MEDIA_REWIND': '< or ,', 'MEDIA_FAST_FORWARD': '> or .',
}

MARQUEE = ('*** WELCOME 2 REMOTE 95!!! *** '
           'Now connected to {host} *** Sign my guestbook! *** '
           'Best viewed at 800x600 *** ')


# --------------------------------------------------------------------------
# 90s look: 16x16 pixel-art icons and a GTK stylesheet
# --------------------------------------------------------------------------

PALETTE = {
    'k': (0, 0, 0), 'w': (255, 255, 255), 'g': (192, 192, 192),
    'd': (128, 128, 128), 'r': (255, 0, 0), 'y': (255, 255, 0),
    'b': (0, 0, 128), 'B': (0, 0, 255), 'c': (0, 255, 255),
    'G': (0, 192, 0), 'o': (128, 64, 0),
}

ICONS = {
    'power': [
        '................', '.......kk.......', '......krrk......',
        '...kk.krrk.kk...', '..krrkkrrkkrrk..', '.krrk.krrk.krrk.',
        '.krk..krrk..krk.', 'krrk..krrk..krrk', 'krk...kkkk...krk',
        'krk..........krk', 'krrk........krrk', '.krk........krk.',
        '.krrkk....kkrrk.', '..krrrkkkkrrrk..', '...kkrrrrrrkk...',
        '.....kkkkkk.....'],
    'back': [
        '................', '................', '......k.........',
        '.....kk.........', '....kyk.........', '...kyykkkkkkkk..',
        '..kyyyyyyyyyyyk.', '.kyyyyyyyyyyyyk.', '..kyyyyyyyyyyyk.',
        '...kyykkkkkkkk..', '....kyk.........', '.....kk.........',
        '......k.........', '................', '................',
        '................'],
    'home': [
        '.......kk.......', '......krrk......', '.....krrrrk.....',
        '....krrrrrrk....', '...krrrrrrrrk...', '..krrrrrrrrrrk..',
        '.kkkkkkkkkkkkkk.', '..kwwwwwwwwwwk..', '..kwccwwwwccwk..',
        '..kwccwwwwccwk..', '..kwwwwwwwwwwk..', '..kwwwwoowwwwk..',
        '..kwwwwoowwwwk..', '..kwwwwoowwwwk..', '..kkkkkkkkkkkk..',
        '................'],
    'gear': [
        '................', '......kkkk......', '..kk..kddk..kk..',
        '.kddkkkddkkkddk.', '.kddddddddddddk.', '..kdddkkkkdddk..',
        'kkkddk....kddkkk', 'kdddk......kdddk', 'kdddk......kdddk',
        'kkkddk....kddkkk', '..kdddkkkkdddk..', '.kddddddddddddk.',
        '.kddkkkddkkkddk.', '..kk..kddk..kk..', '......kkkk......',
        '................'],
    'tv': [
        '....k.....k.....', '.....k...k......', '......k.k.......',
        '.kkkkkkkkkkkkkk.', '.kggggggggggggk.', '.kgkkkkkkkkgggk.',
        '.kgkcccccckgrgk.', '.kgkcwcccckgggk.', '.kgkcccccckgkgk.',
        '.kgkcccccckgggk.', '.kgkcccccckgkgk.', '.kgkkkkkkkkgggk.',
        '.kggggggggggggk.', '.kkkkkkkkkkkkkk.', '..kk........kk..',
        '................'],
    'menu': [
        '..kkkkkkkkk.....', '..kwwwwwwwkk....', '..kwwwwwwwkwk...',
        '..kwwwwwwwkkkk..', '..kwbbbbbbwwwk..', '..kwwwwwwwwwwk..',
        '..kwbbbbbbbbwk..', '..kwwwwwwwwwwk..', '..kwbbbbbbbbwk..',
        '..kwwwwwwwwwwk..', '..kwbbbbbwwwwk..', '..kwwwwwwwwwwk..',
        '..kwbbbbbbbbwk..', '..kwwwwwwwwwwk..', '..kkkkkkkkkkkk..',
        '................'],
    'rewind': [
        '................', '................', '................',
        '.......k......k.', '......kk.....kk.', '.....kbk....kbk.',
        '....kbbk...kbbk.', '...kbbbk..kbbbk.', '..kbbbbk.kbbbbk.',
        '...kbbbk..kbbbk.', '....kbbk...kbbk.', '.....kbk....kbk.',
        '......kk.....kk.', '.......k......k.', '................',
        '................'],
    'play': [
        '................', '................', '.k.......bb.bb..',
        '.kk......bb.bb..', '.kGk.....bb.bb..', '.kGGk....bb.bb..',
        '.kGGGk...bb.bb..', '.kGGGGk..bb.bb..', '.kGGGGk..bb.bb..',
        '.kGGGk...bb.bb..', '.kGGk....bb.bb..', '.kGk.....bb.bb..',
        '.kk......bb.bb..', '.k.......bb.bb..', '................',
        '................'],
    'up': [
        '................', '................', '................',
        '................', '.......kk.......', '......kbbk......',
        '.....kbbbbk.....', '....kbbbbbbk....', '...kbbbbbbbbk...',
        '..kbbbbbbbbbbk..', '.kbbbbbbbbbbbbk.', '.kkkkkkkkkkkkkk.',
        '................', '................', '................',
        '................'],
    'speaker': [
        '................', '................', '......k.........',
        '.....kk.........', '....kdk.........', 'kkkkddk.........',
        'kwwkddk.........', 'kwwkddk.........', 'kwwkddk.........',
        'kwwkddk.........', 'kkkkddk.........', '....kdk.........',
        '.....kk.........', '......k.........', '................',
        '................'],
    'youtube': [
        '................', '................', '................',
        '..rrrrrrrrrrrr..', '.rrrrrrrrrrrrrr.', 'rrrrrrwrrrrrrrrr',
        'rrrrrrwwwrrrrrrr', 'rrrrrrwwwwwrrrrr', 'rrrrrrwwwwwrrrrr',
        'rrrrrrwwwrrrrrrr', 'rrrrrrwrrrrrrrrr', '.rrrrrrrrrrrrrr.',
        '..rrrrrrrrrrrr..', '................', '................',
        '................'],
    'remote': [
        '....kkkkkkkk....', '...kddddddddk...', '...kdrddddddk...',
        '...kddddddddk...', '...kdddwwdddk...', '...kddwccwddk...',
        '...kdddwwdddk...', '...kddddddddk...', '...kdwwddwwdk...',
        '...kddddddddk...', '...kdwwddwwdk...', '...kddddddddk...',
        '...kddrGyBddk...', '...kddddddddk...', '....kkkkkkkk....',
        '................'],
    'globe': [
        '.....kkkkkk.....', '...kkBBGGBBkk...', '..kBBGGGGBBBBk..',
        '.kBBGGGGGBBBBBk.', '.kBGGGGGBBBGGBk.', 'kBBGGGGBBBGGGGBk',
        'kBBBGGBBBGGGGGBk', 'kBBBBGBBBBGGGBBk', 'kBBBBBBBBBBGGBBk',
        'kBBBBGGBBBBBBBBk', '.kBBBGGGBBBBBBk.', '.kBBBBGGGBBBBBk.',
        '..kBBBBGGBBBBk..', '...kkBBBBBBkk...', '.....kkkkkk.....',
        '................'],
    'construction': [
        '.......kk.......', '......kyyk......', '.....kyyyyk.....',
        '....kyykkyyk....', '...kyyykkyyyk...', '..kyyyykkyyyyk..',
        '.kyyyyykkyyyyyk.', 'kyyyyyykkyyyyyyk', 'kyyyyyykkyyyyyyk',
        '.kyyyyyyyyyyyyk.', '..kyyyykkyyyyk..', '...kyyykkyyyk...',
        '....kyyyyyyk....', '.....kyyyyk.....', '......kyyk......',
        '.......kk.......'],
}


def overlay(base, top):
    """Draw the non-transparent pixels of one icon over another."""
    return [''.join(t if t != '.' else b for b, t in zip(brow, trow))
            for brow, trow in zip(base, top)]


BLANK = ['.' * 16] * 16
ICONS['ffwd'] = [row[::-1] for row in ICONS['rewind']]
ICONS['down'] = ICONS['up'][::-1]
ICONS['left'] = [''.join(col) for col in zip(*ICONS['up'])]
ICONS['right'] = [row[::-1] for row in ICONS['left']]
ICONS['vol_down'] = overlay(ICONS['speaker'], BLANK[:7] + [
    '.........bbbbbb.'] * 2 + BLANK[9:])
ICONS['vol_up'] = overlay(ICONS['speaker'], BLANK[:5] + [
    '...........bb...'] * 2 + ['.........bbbbbb.'] * 2 + [
    '...........bb...'] * 2 + BLANK[11:])
ICONS['mute'] = overlay(ICONS['speaker'], BLANK[:5] + [
    '.........rr..rr.', '..........rrrr..', '...........rr...',
    '...........rr...', '..........rrrr..', '.........rr..rr.'] + BLANK[11:])


def pixbuf_from_rows(rows, scale=1):
    """Turn a list of palette strings into a (scaled-up, blocky) pixbuf."""
    width, height = len(rows[0]), len(rows)
    data = bytearray()
    for row in rows:
        assert len(row) == width, row
        for char in row:
            data += bytes(PALETTE[char] + (255,)) if char != '.' else bytes(4)
    pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(bytes(data)), GdkPixbuf.Colorspace.RGB, True, 8,
        width, height, width * 4)
    return pixbuf.scale_simple(width * scale, height * scale,
                               GdkPixbuf.InterpType.NEAREST)


def icon(name, scale=2):
    return Gtk.Image.new_from_pixbuf(pixbuf_from_rows(ICONS[name], scale))


def starfield_tile(path):
    size = 64
    grid = [list('k' * size) for _ in range(size)]
    small = [(5, 9), (22, 3), (40, 14), (58, 6), (13, 30), (33, 27),
             (50, 38), (3, 47), (27, 52), (45, 59), (61, 28), (18, 41)]
    for x, y in small:
        grid[y][x] = 'g'
    for x, y, colour in [(11, 17, 'w'), (47, 24, 'y'), (30, 44, 'w'),
                         (56, 52, 'c')]:
        for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]:
            grid[y + dy][x + dx] = colour
        grid[y][x] = 'w'
    pixbuf_from_rows([''.join(row) for row in grid]).savev(
        str(path), 'png', [], [])


CSS = '''
window.retro {
    background-color: #000000;
    background-image: url("%(tile)s");
}
.retro * {
    font-family: "MS Sans Serif", "Microsoft Sans Serif", Tahoma, Arial,
                 sans-serif;
    font-size: 11px;
}

/* Win95-style raised panel / button bevels */
.panel {
    background-color: #c0c0c0;
    padding: 4px;
    box-shadow: inset -1px -1px #000000, inset 1px 1px #dfdfdf,
                inset -2px -2px #808080, inset 2px 2px #ffffff;
}
button {
    background-color: #c0c0c0;
    background-image: none;
    color: #000000;
    border: none;
    border-radius: 0;
    outline: none;
    text-shadow: none;
    -gtk-icon-shadow: none;
    padding: 3px 6px;
    box-shadow: inset -1px -1px #000000, inset 1px 1px #ffffff,
                inset -2px -2px #808080, inset 2px 2px #dfdfdf;
}
button:active, button:checked {
    background-color: #c0c0c0;
    background-image: none;
    padding: 4px 5px 2px 7px;
    box-shadow: inset 1px 1px #000000, inset -1px -1px #ffffff,
                inset 2px 2px #808080, inset -2px -2px #dfdfdf;
}
button:checked {
    background-image: linear-gradient(45deg, #c0c0c0 25%%, #ffffff 25%%,
                                      #ffffff 50%%, #c0c0c0 50%%,
                                      #c0c0c0 75%%, #ffffff 75%%);
    background-size: 2px 2px;
}
button.ok label { font-weight: bold; font-size: 14px; }

/* Title bar, like a 95 window caption */
.caption {
    background-image: linear-gradient(to right, #000080, #1084d0);
    color: #ffffff;
    font-weight: bold;
    padding: 3px 4px;
}
.caption label { color: #ffffff; font-weight: bold; }

/* Group boxes */
frame > border {
    border: 1px solid #808080;
    border-radius: 0;
    box-shadow: inset 1px 1px #ffffff, 1px 1px #ffffff;
}
frame > label, .grouplabel {
    color: #000080;
    font-weight: bold;
}

/* Drop-down menus */
menu, .menu {
    background-color: #c0c0c0;
    border: none;
    padding: 2px;
    box-shadow: inset -1px -1px #000000, inset 1px 1px #ffffff,
                inset -2px -2px #808080, inset 2px 2px #dfdfdf;
}
menuitem { color: #000000; padding: 2px 16px; }
menuitem:hover { background-color: #000080; }
menuitem:hover label { color: #ffffff; }

/* Yellow sticky-note tooltips */
tooltip, tooltip.background {
    background-color: #ffffe1;
    border: 1px solid #000000;
    border-radius: 0;
    box-shadow: none;
}
tooltip label { color: #000000; }

/* Geocities bits */
.marquee {
    background-color: #000000;
    color: #ffff00;
    font-family: "Courier New", Courier, monospace;
    font-weight: bold;
    padding: 2px 4px;
}
.statusbar {
    padding: 2px 4px;
    box-shadow: inset 1px 1px #808080, inset -1px -1px #ffffff;
}
.lcd {
    background-color: #000000;
    color: #00ff00;
    font-family: "Courier New", Courier, monospace;
    font-weight: bold;
    font-size: 13px;
    padding: 1px 4px;
    box-shadow: inset 1px 1px #808080, inset -1px -1px #ffffff;
}
.footer { color: #ffff00; font-family: "Times New Roman", Times, serif; }
.footer label { color: #ffff00; }
'''


def rainbow(text):
    """Pango markup for WordArt-ish rainbow letters."""
    colours = ['#ff0000', '#ff8000', '#ffff00', '#00ff00', '#00ffff',
               '#ff00ff']
    out, i = [], 0
    for char in text:
        if char == ' ':
            out.append(' ')
            continue
        out.append('<span foreground="{}">{}</span>'.format(
            colours[i % len(colours)], GLib.markup_escape_text(char)))
        i += 1
    return ('<span font_family="Comic Sans MS, Comic Neue, cursive" '
            'size="xx-large" weight="bold">{}</span>'.format(''.join(out)))


def load_clicks():
    """Button presses so far, from earlier runs. Creates the file if needed."""
    try:
        return int(CLICKS_FILE.read_text().strip())
    except (OSError, ValueError):
        save_clicks(0)
        return 0


def save_clicks(count):
    try:
        CONFIG_DIR.mkdir(exist_ok=True)
        CLICKS_FILE.write_text(str(count))
    except OSError:
        pass  # a lost count isn't worth crashing the remote over


def install_theme():
    CONFIG_DIR.mkdir(exist_ok=True)
    tile = CONFIG_DIR / 'stars.png'
    if not tile.exists():
        starfield_tile(tile)
    provider = Gtk.CssProvider()
    provider.load_from_data((CSS % {'tile': tile.as_uri()}).encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    # App icon (taskbar / title bar): a lil pixel remote, in a few sizes
    Gtk.Window.set_default_icon_list(
        [pixbuf_from_rows(ICONS['remote'], scale) for scale in (1, 2, 3, 4)])


# --------------------------------------------------------------------------
# asyncio runs in a background thread; GTK owns the main thread
# --------------------------------------------------------------------------

class AsyncRunner:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def run(self, coro, timeout=None):
        """Run a coroutine on the loop and wait for its result."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def call(self, func, *args):
        """Call a plain function on the loop thread (fire and forget)."""
        self.loop.call_soon_threadsafe(func, *args)


def connect(runner, host):
    """Create the remote, pairing first if needed. Returns the remote."""
    CONFIG_DIR.mkdir(exist_ok=True)

    async def setup():
        remote = AndroidTVRemote(CLIENT_NAME, str(CERT), str(KEY), host)
        if await remote.async_generate_cert_if_missing():
            print('Created a new client certificate.')
        try:
            await remote.async_connect()
            return remote, False
        except InvalidAuth:
            return remote, True

    remote, needs_pairing = runner.run(setup(), timeout=20)

    while needs_pairing:
        print('Pairing with the TV - a code should appear on the TV screen.')
        runner.run(remote.async_start_pairing(), timeout=20)
        code = input('Enter the code shown on the TV: ').strip()
        try:
            runner.run(remote.async_finish_pairing(code), timeout=20)
        except InvalidAuth:
            print('That code was wrong, try again.')
            continue
        except ConnectionClosed:
            print('The TV closed the pairing session, starting again.')
            continue
        print('Paired!')
        runner.run(remote.async_connect(), timeout=20)
        needs_pairing = False

    return remote


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

class RemoteWindow(Gtk.Window):
    def __init__(self, runner, remote, host):
        super().__init__(title='Remote 95 - ' + host)
        self.runner = runner
        self.remote = remote
        self.set_border_width(10)
        self.set_resizable(False)
        self.get_style_context().add_class('retro')
        self.connect('destroy', self.on_destroy)
        self.connect('key-press-event', self.on_key)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(page)

        # ---- Geocities header ----
        title = Gtk.Label()
        title.set_markup(rainbow('Remote 95'))
        page.pack_start(title, False, False, 0)

        self.marquee_text = MARQUEE.format(host=host)
        self.marquee_pos = 0
        self.marquee = Gtk.Label(xalign=0, width_chars=38, max_width_chars=38)
        self.add_class(self.marquee, 'marquee')
        page.pack_start(self.marquee, False, False, 0)
        self.tick_marquee()
        GLib.timeout_add(150, self.tick_marquee)

        # ---- the remote itself: a grey 95-style window ----
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_class(body, 'panel')
        page.pack_start(body, False, False, 0)

        caption = Gtk.Box(spacing=4)
        self.add_class(caption, 'caption')
        caption.pack_start(icon('remote', 1), False, False, 0)
        caption.pack_start(Gtk.Label(label='Remote Control - ' + host),
                           False, False, 0)
        body.pack_start(caption, False, False, 0)

        nav = self.group(body, 'Navigation')
        nav.pack_start(self.row([('Power', 'POWER', 'power'),
                                 ('Back', 'BACK', 'back'),
                                 ('Home', 'HOME', 'home')]), False, False, 0)

        pad = Gtk.Grid(row_spacing=2, column_spacing=2,
                       halign=Gtk.Align.CENTER)
        for name, key, col, row in [('up', 'DPAD_UP', 1, 0),
                                    ('left', 'DPAD_LEFT', 0, 1),
                                    ('right', 'DPAD_RIGHT', 2, 1),
                                    ('down', 'DPAD_DOWN', 1, 2)]:
            btn = self.button(None, key, name)
            btn.set_size_request(52, 52)
            pad.attach(btn, col, row, 1, 1)
        ok_btn = self.button('OK', 'DPAD_CENTER')
        ok_btn.set_size_request(52, 52)
        self.add_class(ok_btn, 'ok')
        pad.attach(ok_btn, 1, 1, 1, 1)
        nav.pack_start(pad, False, False, 0)

        nav.pack_start(self.row([('Settings', 'SETTINGS', 'gear'),
                                 ('YouTube', 'YOUTUBE', 'youtube'),
                                 ('Menu', 'MENU', 'menu')]), False, False, 0)

        media = self.group(body, 'Media')
        media.pack_start(self.row([('Rew', 'MEDIA_REWIND', 'rewind'),
                                   ('Play/Pause', 'MEDIA_PLAY_PAUSE', 'play'),
                                   ('FF', 'MEDIA_FAST_FORWARD', 'ffwd')]),
                         False, False, 0)
        media.pack_start(self.row([('Vol -', 'VOLUME_DOWN', 'vol_down'),
                                   ('Mute', 'VOLUME_MUTE', 'mute'),
                                   ('Vol +', 'VOLUME_UP', 'vol_up')]),
                         False, False, 0)

        apps_box = self.group(body, 'Apps')
        app_row = Gtk.Box(spacing=4)
        app_row.pack_start(icon('globe'), False, False, 0)
        apps = Gtk.ComboBoxText()
        apps.append(None, 'Launch app...')
        for name, link in APPS:
            apps.append(link, name)
        apps.set_active(0)
        apps.connect('changed', self.on_app)
        app_row.pack_start(apps, True, True, 0)
        apps_box.pack_start(app_row, False, False, 0)

        self.hover_hint = None
        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(40)
        self.add_class(self.status, 'statusbar')
        body.pack_start(self.status, False, False, 0)
        self.update_status()

        # ---- footer: under construction + hit counter ----
        footer = Gtk.Box(spacing=6)
        self.add_class(footer, 'footer')
        footer.pack_start(icon('construction'), False, False, 0)
        footer.pack_start(Gtk.Label(
            label='Under construction!\nBest viewed in Netscape Navigator',
            xalign=0), False, False, 0)
        self.presses = load_clicks()
        self.counter = Gtk.Label(label=self.counter_text(),
                                 tooltip_text='Buttons pressed')
        self.add_class(self.counter, 'lcd')
        footer.pack_end(self.counter, False, False, 0)
        page.pack_start(footer, False, False, 0)

        # Library callbacks fire on the asyncio thread -> hop to GTK thread
        refresh = lambda *_a: GLib.idle_add(self.update_status)
        remote.add_is_on_updated_callback(refresh)
        remote.add_current_app_updated_callback(refresh)
        remote.add_volume_info_updated_callback(refresh)
        remote.add_is_available_updated_callback(refresh)
        runner.call(remote.keep_reconnecting)

    # ---- helpers ----
    @staticmethod
    def add_class(widget, name):
        widget.get_style_context().add_class(name)

    def button(self, label, key, icon_name=None):
        btn = Gtk.Button(label=label)
        if icon_name:
            btn.set_image(icon(icon_name))
            btn.set_always_show_image(True)
            btn.set_image_position(Gtk.PositionType.TOP)
        btn.set_size_request(76, 0)
        btn.set_can_focus(False)  # keep arrow keys for the remote
        if key in SHORTCUTS:
            hint = 'Shortcut: ' + SHORTCUTS[key]
            btn.set_tooltip_text(hint)
            btn.connect('enter-notify-event', self.on_hover, hint)
            btn.connect('leave-notify-event', self.on_hover, None)
        btn.connect('clicked', lambda _b: self.press(key))
        return btn

    def row(self, items):
        hbox = Gtk.Box(spacing=4, homogeneous=True)
        for label, key, icon_name in items:
            hbox.pack_start(self.button(label, key, icon_name), True, True, 0)
        return hbox

    def group(self, parent, title):
        """A 95-style group box; returns the box to pack widgets into."""
        frame = Gtk.Frame(label=' {} '.format(title))
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                        border_width=6)
        frame.add(inner)
        parent.pack_start(frame, False, False, 0)
        return inner

    def tick_marquee(self):
        text, pos = self.marquee_text, self.marquee_pos
        self.marquee.set_text((text[pos:] + text[:pos])[:38])
        self.marquee_pos = (pos + 1) % len(text)
        return True

    def safe_call(self, func, *args):
        """Run a library send_* call on the asyncio thread."""
        def wrapped():
            try:
                func(*args)
            except ConnectionClosed:
                GLib.idle_add(self.status.set_text,
                              'Disconnected - reconnecting…')
        self.runner.call(wrapped)

    def update_status(self):
        parts = []
        on = self.remote.is_on
        if on is not None:
            parts.append('TV on' if on else 'TV off')
        if self.remote.current_app:
            parts.append(self.remote.current_app)
        vol = self.remote.volume_info
        if vol:
            parts.append('muted' if vol['muted'] else
                         'vol {}/{}'.format(vol['level'], vol['max']))
        if self.hover_hint:
            self.status.set_markup('<b>{}</b>'.format(
                GLib.markup_escape_text(self.hover_hint)))
        else:
            self.status.set_text(' · '.join(parts) or 'Connected')
        return False

    def on_hover(self, _btn, _event, hint):
        # Like an old browser showing a link's URL in the status bar
        self.hover_hint = hint
        self.update_status()
        return False

    def press(self, key):
        if key in APP_BUTTONS:
            name, link = APP_BUTTONS[key]
            self.status.set_text('Launching ' + name + '…')
            self.safe_call(self.remote.send_launch_app_command, link)
        else:
            self.safe_call(self.remote.send_key_command, key)
        self.presses += 1
        self.counter.set_text(self.counter_text())
        save_clicks(self.presses)

    def counter_text(self):
        return '{:06d}'.format(self.presses % 1000000)

    # ---- handlers ----
    def on_app(self, combo):
        link = combo.get_active_id()
        if link:
            self.status.set_text('Launching ' + combo.get_active_text() + '…')
            self.safe_call(self.remote.send_launch_app_command, link)
            combo.set_active(0)

    def on_key(self, _win, event):
        key = KEYBOARD.get(Gdk.keyval_to_lower(event.keyval))
        if key:
            self.press(key)
            return True
        return False

    def on_destroy(self, _win):
        self.runner.call(self.remote.disconnect)
        Gtk.main_quit()


def main():
    if len(sys.argv) > 1:
        host = sys.argv[1]
    elif HOST_FILE.exists():
        host = HOST_FILE.read_text().strip()
    else:
        print('Give the TV\'s IP address the first time, e.g.\n'
              '  python googletv_remote.py <tv-ip>')
        return

    runner = AsyncRunner()
    print('Connecting to ' + host + '…')
    try:
        remote = connect(runner, host)
    except (CannotConnect, ConnectionClosed, OSError,
            asyncio.TimeoutError) as err:
        print('Could not connect to {}: {}'.format(host, str(err) or type(err).__name__))
        print('Is the TV on, and is the IP right? (TV: Settings → Network)')
        return

    HOST_FILE.write_text(host)
    install_theme()
    RemoteWindow(runner, remote, host).show_all()
    Gtk.main()


if __name__ == '__main__':
    main()
