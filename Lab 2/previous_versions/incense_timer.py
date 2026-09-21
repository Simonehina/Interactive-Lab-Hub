"""
Incense Timer -- a pomodoro you can smell.

You light a stick of incense, put it in the holder, and press the button.
The screen shows the stick burning down. When it is gone, a bell rings.
Time is not counted in minutes here, it is counted in one stick of incense.

Hardware: Raspberry Pi 5 + Adafruit Mini PiTFT (buttons on D23 / D24),
and optionally an APDS9960 on the PiTFT's STEMMA QT port so you can wave
your hand over the holder instead of pressing anything.
Sound goes to whatever ALSA plays to, so pair a Bluetooth speaker first.

How you use it (INPUT_MODE = "wave"):
  IDLE     pass your hand over the sensor = light the incense (start)
           bottom PiTFT button = change the length of the stick
  BURNING  hold your hand over the sensor 2s = put it out (cancel)
  DONE     wave again = clear the ash

With INPUT_MODE = "button" the two PiTFT buttons do the same things.
"""

import math
import os
import random
import struct
import subprocess
import time
import wave

import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# --- settings ---------------------------------------------------------------

# "wave"   = hand over the APDS9960 (falls back to the buttons if it is missing)
# "button" = the two buttons on the PiTFT
INPUT_MODE = "wave"

# How far above the resting reading counts as a hand. Raise it if the incense
# smoke or a passer-by sets it off, lower it if you have to get too close.
PROX_DELTA = 30

# Lengths of incense you own, in minutes. Measure a real stick and put it here.
STICK_LENGTHS = [25, 45, 60]

# The assignment discourages literal clocks, so the numbers are off by default.
# Flip this to True while you are debugging.
SHOW_NUMBERS = False

HOLD_TO_CANCEL = 2.0  # seconds
BELL_PATH = "/tmp/incense_bell.wav"

# --- display ----------------------------------------------------------------

cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)

disp = st7789.ST7789(
    board.SPI(),
    cs=cs_pin,
    dc=dc_pin,
    rst=None,
    baudrate=64000000,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)

# Rotate to landscape.
WIDTH = disp.height
HEIGHT = disp.width
ROTATION = 90

image = Image.new("RGB", (WIDTH, HEIGHT))
draw = ImageDraw.Draw(image)

font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)

backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output()
backlight.value = True

# --- input ------------------------------------------------------------------
# The two buttons on the Mini PiTFT. They read False while held down.
#
# To move the button off the Pi and into the holder itself, swap these for a
# SparkFun Qwiic Button (one Qwiic cable, no soldering):
#     import qwiic_button
#     btn = qwiic_button.QwiicButton(); btn.begin()
#     ... and return btn.is_button_pressed() from primary()

button_a = digitalio.DigitalInOut(board.D23)
button_b = digitalio.DigitalInOut(board.D24)
for b in (button_a, button_b):
    b.switch_to_input(pull=digitalio.Pull.UP)


def pressed(button):
    return not button.value


# The APDS9960 sits under the rim of the holder, facing up. Its proximity
# channel drives its own IR LED, so daylight does not upset it much.
apds = None
if INPUT_MODE == "wave":
    try:
        import busio
        import adafruit_apds9960.apds9960

        apds = adafruit_apds9960.apds9960.APDS9960(busio.I2C(board.SCL, board.SDA))
        apds.enable_proximity = True
    except Exception as err:  # no sensor plugged in -> just use the buttons
        print("APDS9960 not found (%s), falling back to the buttons" % err)

_baseline = None


def hand_over_sensor():
    """True while a hand is hovering above the sensor."""
    global _baseline
    reading = apds.proximity
    if _baseline is None:
        _baseline = float(reading)
    if reading < _baseline + PROX_DELTA:
        # Nothing there: drift slowly, so soot on the window or a change of
        # room does not leave us stuck above or below the threshold.
        _baseline += (reading - _baseline) * 0.02
        return False
    return True


def primary():
    """Start / cancel / clear. A wave of the hand, or the top button."""
    if apds is not None:
        return hand_over_sensor() or pressed(button_a)
    return pressed(button_a)


def secondary():
    """Change the length of the stick. Always the bottom PiTFT button."""
    return pressed(button_b)


# --- bell -------------------------------------------------------------------


def make_bell(path, seconds=4.0, rate=44100, base=261.6):
    """Synthesise a singing-bowl-ish tone so there is no audio file to ship."""
    # Inharmonic partials are what make a bell sound like a bell rather than
    # like a beep. Higher partials fade faster.
    partials = [(1.0, 1.0, 1.2), (2.76, 0.6, 2.0), (5.40, 0.25, 3.5), (8.93, 0.1, 5.0)]
    frames = bytearray()
    total = int(rate * seconds)
    for i in range(total):
        t = i / rate
        sample = 0.0
        for ratio, amp, decay in partials:
            sample += amp * math.sin(2 * math.pi * base * ratio * t) * math.exp(-decay * t)
        attack = min(1.0, t / 0.005)  # tiny fade-in so it does not click
        value = int(max(-1.0, min(1.0, sample * attack * 0.3)) * 32767)
        frames += struct.pack("<h", value)

    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(bytes(frames))


def ring():
    try:
        subprocess.Popen(
            ["aplay", "-q", BELL_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # no audio on this machine, the screen still works


# --- drawing ----------------------------------------------------------------

VERB = "wave" if apds is not None else "press"

STICK_X = 60  # the stick stands here
STICK_TOP = 18  # y of an unburnt tip
STICK_BOTTOM = HEIGHT - 26  # y where the stick meets the holder
FULL_LENGTH = STICK_BOTTOM - STICK_TOP

smoke = []  # drifting particles, each [x, y, age, drift]


def draw_holder():
    draw.polygon(
        [
            (STICK_X - 26, HEIGHT - 8),
            (STICK_X + 26, HEIGHT - 8),
            (STICK_X + 16, STICK_BOTTOM),
            (STICK_X - 16, STICK_BOTTOM),
        ],
        fill=(70, 58, 52),
    )


def draw_ash(burnt_fraction):
    """A little pile that grows as the stick disappears."""
    w = int(4 + 18 * burnt_fraction)
    h = int(1 + 5 * burnt_fraction)
    draw.ellipse(
        (STICK_X - w // 2, STICK_BOTTOM - h, STICK_X + w // 2, STICK_BOTTOM + h // 2),
        fill=(150, 146, 140),
    )


def draw_stick(remaining_fraction, lit):
    tip_y = STICK_BOTTOM - int(FULL_LENGTH * remaining_fraction)

    # The stick itself.
    if remaining_fraction > 0:
        draw.rectangle((STICK_X - 2, tip_y, STICK_X + 2, STICK_BOTTOM), fill=(120, 74, 48))

    if not lit or remaining_fraction <= 0:
        return

    # Ember: a flickering dot, brightest in the middle.
    flicker = random.uniform(0.75, 1.0)
    draw.ellipse(
        (STICK_X - 4, tip_y - 4, STICK_X + 4, tip_y + 4),
        fill=(int(190 * flicker), int(60 * flicker), 20),
    )
    draw.ellipse(
        (STICK_X - 2, tip_y - 2, STICK_X + 2, tip_y + 2),
        fill=(255, int(190 * flicker), 90),
    )

    # Smoke rises from the ember and wanders off to one side.
    if random.random() < 0.5:
        smoke.append([float(STICK_X), float(tip_y - 5), 0.0, random.uniform(-0.25, 0.55)])
    for p in smoke:
        p[1] -= random.uniform(0.6, 1.3)
        p[0] += p[3] + random.uniform(-0.3, 0.3)
        p[2] += 1
    smoke[:] = [p for p in smoke if p[1] > 0 and p[2] < 70]
    for p in smoke:
        fade = max(0, 110 - int(p[2] * 1.6))
        r = 1 + p[2] / 28
        draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=(fade, fade, fade))


def draw_screen(state, remaining_fraction, minutes_total, seconds_left, interrupted=False):
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(12, 10, 14))

    lit = state == "BURNING"
    draw_holder()
    draw_ash(1.0 - remaining_fraction)
    draw_stick(remaining_fraction, lit)

    right = STICK_X + 48
    if state == "IDLE":
        draw.text((right, 44), "one stick", font=font, fill=(200, 190, 175))
        draw.text((right, 62), "%d min" % minutes_total, font=font, fill=(150, 120, 90))
        draw.text((right, 96), VERB + " to light", font=font_small, fill=(95, 90, 85))
    elif state == "BURNING":
        draw.text((right, 44), "burning", font=font, fill=(205, 140, 80))
        if SHOW_NUMBERS:
            draw.text(
                (right, 62),
                "%02d:%02d" % (seconds_left // 60, seconds_left % 60),
                font=font,
                fill=(120, 110, 100),
            )
        draw.text((right, 96), "hold to stop", font=font_small, fill=(70, 66, 62))
    else:  # DONE
        draw.text((right, 38), "one stick", font=font, fill=(200, 190, 175))
        draw.text((right, 56), "has burned", font=font, fill=(200, 190, 175))
        if interrupted:
            draw.text((right, 80), "put out early", font=font_small, fill=(150, 90, 70))
        draw.text((right, 100), VERB + " to clear", font=font_small, fill=(95, 90, 85))

    disp.image(image, ROTATION)


# --- main loop --------------------------------------------------------------


def main():
    if not os.path.exists(BELL_PATH):
        make_bell(BELL_PATH)

    state = "IDLE"
    length_index = 0
    started_at = 0.0
    held_since = None
    interrupted = False

    while True:
        minutes = STICK_LENGTHS[length_index]
        duration = minutes * 60

        if state == "IDLE":
            remaining = 1.0
            seconds_left = duration
            if primary():
                # Wait until the hand is out of the way, otherwise the hold
                # gesture below would fire straight away.
                while primary():
                    time.sleep(0.02)
                smoke.clear()
                started_at = time.monotonic()
                interrupted = False
                state = "BURNING"
            elif secondary():
                while secondary():
                    time.sleep(0.02)
                length_index = (length_index + 1) % len(STICK_LENGTHS)

        elif state == "BURNING":
            elapsed = time.monotonic() - started_at
            seconds_left = max(0, int(duration - elapsed))
            remaining = max(0.0, 1.0 - elapsed / duration)

            # Holding still over the sensor (or on the button) puts it out early.
            if primary():
                if held_since is None:
                    held_since = time.monotonic()
                elif time.monotonic() - held_since >= HOLD_TO_CANCEL:
                    interrupted = True
                    state = "DONE"
                    held_since = None
                    while primary():
                        time.sleep(0.02)
            else:
                held_since = None

            if remaining <= 0:
                ring()
                state = "DONE"

        else:  # DONE
            remaining = 0.0
            seconds_left = 0
            if primary() or secondary():
                while primary() or secondary():
                    time.sleep(0.02)
                smoke.clear()
                state = "IDLE"

        draw_screen(state, remaining, minutes, seconds_left, interrupted)
        time.sleep(0.05)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(0, 0, 0))
        disp.image(image, ROTATION)
        backlight.value = False
