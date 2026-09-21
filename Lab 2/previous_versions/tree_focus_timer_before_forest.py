"""Pixel focus garden for Lab 2.

A starts/resets; B switches garden/clock without interrupting focus.
Four completed 25-minute sessions grow one tree per New York calendar day.
Use --demo for 20-second sessions and a separate demo progress file.
This button prototype does not yet connect a physical touch sensor.
Created with AI assistance; based on the student's tested MiniPiTFT timer.
"""

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
LOCAL_TZ = ZoneInfo("America/New_York")
AUDIO_DEVICE = "plughw:CARD=UACDemoV10,DEV=0"
AUDIO_VOLUME = 32768
BG = (12, 18, 27)
FONT = ImageFont.load_default(size=8)


class Progress:
    """Persist completed sessions only; write atomically after each completion."""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if data.get("version") != 1 or not isinstance(data.get("days"), dict):
                raise ValueError(f"Invalid progress file: {self.path}")
            self.days = data["days"]
            if any(type(n) is not int or n < 0 for n in self.days.values()):
                raise ValueError(f"Invalid session counts: {self.path}")
        else:
            self.days = {}

    def count(self, day):
        return self.days.get(day, 0)

    def complete(self, day):
        updated = dict(self.days)
        updated[day] = updated.get(day, 0) + 1
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.path.parent, prefix=".tree-progress-",
                suffix=".tmp", delete=False,
            ) as output:
                temp_name = output.name
                json.dump({"version": 1, "days": updated}, output, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_name, self.path)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
        self.days = updated


class Timer:
    def __init__(self, progress, duration, day):
        self.progress = progress
        self.duration = duration
        self.day = day
        self.state = "ready"
        self.view = "garden"
        self.started_at = 0.0
        self.remaining = 0.0

    @property
    def stage(self):
        return min(4, self.progress.count(self.day))

    def press_a(self, now, day):
        if self.state == "ready":
            self.day = day
            self.started_at = now
            self.remaining = self.duration
            self.state = "running"
            return "start"
        self.state = "ready"
        self.remaining = 0.0
        self.day = day
        return "stop"

    def press_b(self):
        self.view = "clock" if self.view == "garden" else "garden"

    def tick(self, now, day):
        if self.state == "ready":
            self.day = day
        elif self.state == "running":
            self.remaining = max(0.0, self.duration - (now - self.started_at))
            if self.remaining <= 0:
                # A session crossing midnight belongs to its starting day.
                self.progress.complete(self.day)
                self.state = "done"
                return "stop"
        return None


class Audio:
    def __init__(self, path):
        self.path = Path(path)
        self.process = None

    def start(self):
        self.stop()
        if not self.path.is_file():
            raise FileNotFoundError(f"Audio file missing: {self.path}")
        self.process = subprocess.Popen(
            ["mpg123", "--no-control", "--loop", "-1", "-o", "alsa",
             "-a", AUDIO_DEVICE, "-f", str(AUDIO_VOLUME), str(self.path)],
            stdin=subprocess.DEVNULL, start_new_session=True,
        )

    def check(self):
        if self.process is not None and self.process.poll() is not None:
            raise RuntimeError("Audio player exited. Check its messages above.")

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        else:
            self.process.wait()
        self.process = None


def pixel_text(canvas, xy, message, color):
    # Threshold the glyph mask so lettering stays crisp at 2x scale.
    mask = Image.new("L", canvas.size)
    ImageDraw.Draw(mask).text(xy, message, font=FONT, fill=255)
    mask = mask.point(lambda value: 255 if value >= 100 else 0)
    canvas.paste(color, (0, 0), mask)


def garden_frame(stage, state, elapsed=0.0, demo=False):
    """Draw at 120x67 then scale by 2 for the 240x135 MiniPiTFT."""
    scene = Image.new("RGB", (120, 67), BG)
    draw = ImageDraw.Draw(scene)

    # Stationary, subdued warm light; nested pixel shapes, no flashing.
    draw.polygon([(69, 0), (80, 0), (93, 47), (35, 47)], fill=(23, 28, 32))
    draw.polygon([(71, 0), (78, 0), (82, 47), (46, 47)], fill=(32, 34, 34))
    draw.polygon([(73, 0), (76, 0), (72, 47), (54, 47)], fill=(43, 40, 34))
    draw.rectangle((0, 48, 119, 66), fill=(17, 23, 25))
    draw.rectangle((28, 47, 91, 49), fill=(99, 86, 59))
    draw.rectangle((32, 50, 87, 52), fill=(57, 47, 37))
    draw.rectangle((39, 53, 80, 54), fill=(36, 33, 29))
    for x, y in [(36, 48), (49, 50), (73, 49), (84, 48), (60, 52)]:
        draw.point((x, y), fill=(146, 118, 70))

    # Five discrete growth stages. Partial sessions never earn a stage.
    if stage == 0:
        draw.rectangle((58, 44, 62, 47), fill=(152, 110, 63))
        draw.rectangle((59, 43, 61, 45), fill=(207, 167, 98))
        draw.point((60, 44), fill=(243, 210, 135))
    else:
        top = {1: 40, 2: 33, 3: 28, 4: 24}[stage]
        draw.rectangle((59, top, 61, 47), fill=(107, 129, 73) if stage < 3 else (126, 91, 59))
        draw.line((61, top, 61, 46), fill=(174, 148, 84))
        if stage <= 2:
            draw.rectangle((53, top - 2, 58, top), fill=(131, 170, 96))
            draw.rectangle((55, top + 1, 59, top + 2), fill=(92, 138, 79))
            draw.rectangle((62, top - 4, 67, top - 2), fill=(167, 194, 110))
            draw.rectangle((61, top - 1, 65, top), fill=(109, 157, 85))
            if stage == 2:
                draw.rectangle((53, 40, 59, 42), fill=(106, 145, 79))
                draw.rectangle((62, 38, 67, 40), fill=(139, 168, 87))
        else:
            if stage == 3:
                blocks = [(51, 24, 68, 33), (47, 27, 72, 31), (55, 20, 64, 26)]
            else:
                blocks = [(44, 20, 76, 32), (40, 23, 80, 29), (49, 15, 71, 23), (55, 12, 66, 19)]
            for box in blocks:
                draw.rectangle(box, fill=(76, 116, 76))
            draw.rectangle((52, top - 5, 67, top + 1), fill=(110, 151, 85))
            draw.rectangle((58, top - 8, 66, top - 5), fill=(153, 177, 97))
            draw.rectangle((68, top - 1, 70, top + 2), fill=(137, 165, 88))
            draw.line((58, 35, 55, 32), fill=(126, 91, 59))
    if state == "running":
        # Deterministic slow rain, 1 pixel wide, clipped above the soil.
        for index in range(12):
            y = int((elapsed * 9 + index * 13) % 44) + 3
            x = (index * 29 + 9 - y // 6) % 120
            draw.line((x, y, x, min(46, y + 2)), fill=(70, 95, 106))

    heading = {"ready": "READY", "running": "FOCUS", "done": "REST"}[state]
    if state == "done" and stage == 4:
        heading = "TREE GROWN"
    pixel_text(scene, (3, 2), heading, (184, 193, 180))
    pixel_text(scene, (103, 2), f"{stage}/4", (216, 184, 122))
    hint = "A start   B clock" if state == "ready" else "A reset   B clock"
    pixel_text(scene, (3, 57), hint, (125, 139, 137))
    if demo:
        pixel_text(scene, (3, 12), "DEMO", (135, 124, 105))
    scaled = scene.resize((240, 134), Image.Resampling.NEAREST)
    output = Image.new("RGB", (240, 135), BG)
    output.paste(scaled, (0, 0))
    return output


def clock_frame(timer, local_now, demo=False):
    scene = Image.new("RGB", (120, 67), BG)
    pixel_text(scene, (4, 3), local_now.strftime("NEW YORK %Z"), (214, 181, 122))
    # Larger numbers remain pixelated by drawing on the small canvas.
    clock_font = ImageFont.load_default(size=17)
    mask = Image.new("L", scene.size)
    ImageDraw.Draw(mask).text((4, 16), local_now.strftime("%H:%M:%S"), font=clock_font, fill=255)
    scene.paste((223, 228, 216), (0, 0), mask.point(lambda n: 255 if n >= 100 else 0))
    pixel_text(scene, (4, 37), local_now.strftime("%Y-%m-%d"), (149, 159, 151))
    if timer.state == "running":
        seconds = math.ceil(timer.remaining)
        status = f"Focus {seconds // 60:02}:{seconds % 60:02}  {timer.stage}/4"
    else:
        status = f"{'Ready' if timer.state == 'ready' else 'Rest'}  {timer.stage}/4"
    pixel_text(scene, (4, 47), status, (164, 184, 138))
    pixel_text(scene, (4, 57), "A start" if timer.state == "ready" else "A reset", (125, 139, 137))
    pixel_text(scene, (65, 57), "B garden", (125, 139, 137))
    output = Image.new("RGB", (240, 135), BG)
    output.paste(scene.resize((240, 134), Image.Resampling.NEAREST), (0, 0))
    return output


def fade_in(frame, elapsed):
    """A gentle, single fade from black when a new focus session starts."""
    amount = max(0.0, min(1.0, elapsed / 1.5))
    if amount == 1.0:
        return frame
    return Image.blend(Image.new("RGB", frame.size), frame, amount)


def run(demo=False):
    # Import hardware libraries only on the Pi, keeping drawing testable on Mac.
    import board
    import digitalio
    import adafruit_rgb_display.st7789 as st7789

    progress = Progress(HERE / ("tree_progress_demo.json" if demo else "tree_progress.json"))
    timer = Timer(progress, 20 if demo else 25 * 60, datetime.now(LOCAL_TZ).date().isoformat())
    audio = Audio(HERE / "whitenoise.mp3")
    cs = digitalio.DigitalInOut(board.D5)
    dc = digitalio.DigitalInOut(board.D25)
    display = st7789.ST7789(board.SPI(), cs=cs, dc=dc, rst=None,
                            baudrate=64000000, width=135, height=240,
                            x_offset=53, y_offset=40)
    backlight = digitalio.DigitalInOut(board.D22)
    backlight.switch_to_output(value=True)
    a = digitalio.DigitalInOut(board.D23)
    b = digitalio.DigitalInOut(board.D24)
    for button in (a, b):
        button.switch_to_input(pull=digitalio.Pull.UP)
    previous_a = previous_b = False
    last_a = last_b = -1.0
    print(f"Garden ready: {timer.duration}s/session. A start/reset, B garden/clock.")
    print(f"Progress: {progress.path}")
    try:
        while True:
            now = time.monotonic()
            local_now = datetime.now(LOCAL_TZ)
            day = local_now.date().isoformat()
            a_pressed, b_pressed = not a.value, not b.value
            if b_pressed and not previous_b and now - last_b >= 0.2:
                timer.press_b()
                last_b = now
            if a_pressed and not previous_a and now - last_a >= 0.2:
                action = timer.press_a(now, day)
                if action == "start":
                    audio.start()
                else:
                    audio.stop()
                last_a = now
            previous_a, previous_b = a_pressed, b_pressed
            if timer.tick(now, day) == "stop":
                audio.stop()
            if timer.state == "running":
                audio.check()
            if timer.view == "clock":
                frame = clock_frame(timer, local_now, demo)
            else:
                frame = garden_frame(timer.stage, timer.state, now - timer.started_at, demo)
            if timer.state == "running":
                frame = fade_in(frame, now - timer.started_at)
            display.image(frame, 90)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nGarden stopped. Completed sessions are saved.")
    finally:
        audio.stop()
        display.image(Image.new("RGB", (240, 135)), 90)
        backlight.value = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="20-second sessions; separate demo progress")
    args = parser.parse_args()
    run(demo=args.demo)
