"""Lab 2 timer: A starts/resets; B switches clock/timer views.

Adapted from the student's Part 1 timer with AI assistance for audio playback.
Keep whitenoise.mp3 in the same folder as this script.
"""

import time
import subprocess
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import digitalio
import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

DURATION = 20  # Demo: 20 seconds. Normal session: 25 * 60.
AUDIO_FILE = Path(__file__).resolve().with_name("whitenoise.mp3")
AUDIO_DEVICE = "plughw:CARD=UACDemoV10,DEV=0"
AUDIO_VOLUME = 32768
LOCAL_TIMEZONE = ZoneInfo("America/New_York")
audio_process = None


def stop_audio():
    """Stop only the player started by this program and reap it."""
    global audio_process
    if audio_process is None:
        return
    if audio_process.poll() is None:
        audio_process.terminate()
        try:
            audio_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            audio_process.kill()
            audio_process.wait()
    else:
        audio_process.wait()
    audio_process = None


def start_audio():
    """Play in a separate process so the screen and buttons keep working."""
    global audio_process
    stop_audio()
    if not AUDIO_FILE.is_file():
        raise FileNotFoundError(f"Audio file missing: {AUDIO_FILE}")
    audio_process = subprocess.Popen(
        [
            "mpg123", "--no-control", "--loop", "-1",
            "-o", "alsa", "-a", AUDIO_DEVICE,
            "-f", str(AUDIO_VOLUME), str(AUDIO_FILE),
        ],
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)
spi = board.SPI()
disp = st7789.ST7789(
    spi, cs=cs_pin, dc=dc_pin, rst=None,
    baudrate=64000000,
    width=135, height=240, x_offset=53, y_offset=40,
)

height = disp.width
width = disp.height
rotation = 90
image = Image.new("RGB", (width, height))
draw = ImageDraw.Draw(image)
font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
)

backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output()
backlight.value = True

button_a = digitalio.DigitalInOut(board.D23)
button_b = digitalio.DigitalInOut(board.D24)
button_a.switch_to_input(pull=digitalio.Pull.UP)
button_b.switch_to_input(pull=digitalio.Pull.UP)

state = "ready"
end_time = 0
previous_a = False
previous_b = False
view = "timer"

try:
    while True:
        a_pressed = not button_a.value
        b_pressed = not button_b.value

        if b_pressed and not previous_b:
            view = "clock" if view == "timer" else "timer"

        if a_pressed and not previous_a:
            if state == "ready":
                start_audio()
                end_time = time.monotonic() + DURATION
                state = "running"
            else:
                stop_audio()
                state = "ready"
                end_time = 0

        previous_a = a_pressed
        previous_b = b_pressed
        remaining = 0
        if state == "running":
            remaining = max(0, end_time - time.monotonic())
            if remaining <= 0:
                stop_audio()
                state = "done"
            elif audio_process is not None and audio_process.poll() is not None:
                raise RuntimeError(
                    "Audio player stopped unexpectedly. Check its messages above."
                )

        draw.rectangle((0, 0, width, height), fill="#000000")
        if view == "clock":
            now = datetime.now(LOCAL_TIMEZONE)
            draw.text((10, 3), now.strftime("New York  %Z"), font=font, fill="#FFAA55")
            draw.text((10, 30), now.strftime("%H:%M:%S"), font=font, fill="white")
            draw.text((10, 57), now.strftime("%Y-%m-%d"), font=font, fill="white")
            status = {"ready": "Ready / A: Start", "running": "Focus / A: Reset", "done": "Done / A: Reset"}[state]
            draw.text((10, 84), status, font=font, fill="#88FF88")
            draw.text((10, 111), "B: Timer", font=font, fill="white")
        elif state == "ready":
            draw.text((10, 5), "Ready to focus", font=font, fill="white")
            draw.text((10, 35), f"Session: {DURATION}s", font=font, fill="white")
            draw.text((10, 70), "A: Start", font=font, fill="white")
            draw.text((10, 105), "B: Clock", font=font, fill="white")
        elif state == "running":
            seconds = int(remaining)
            if remaining > seconds:
                seconds += 1
            draw.text((10, 3), "Focus", font=font, fill="#FFAA55")
            draw.text((10, 30), f"Time left: {seconds}s", font=font, fill="white")
            bar_end = 10 + int((width - 20) * remaining / DURATION)
            draw.rectangle((10, 65, width - 10, 80), outline="white")
            draw.rectangle((10, 65, bar_end, 80), fill="#FFAA55")
            draw.text((10, 84), "A: Reset", font=font, fill="white")
            draw.text((10, 111), "B: Clock", font=font, fill="white")
        else:
            draw.text((10, 20), "Take a break!", font=font, fill="#88FF88")
            draw.text((10, 65), "A: Reset", font=font, fill="white")
            draw.text((10, 105), "B: Clock", font=font, fill="white")

        disp.image(image, rotation)
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nTimer stopped.")
finally:
    stop_audio()
