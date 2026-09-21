"""Pixel focus garden for Lab 2.

A starts/resets; B switches garden/clock without interrupting focus.
Every four completed 25-minute sessions grow one permanent tree, without a cap.
The current plant and two recent trees share the screen; all trees remain saved.
Use --demo for 20-second sessions and a separate demo progress file.
APDS9960 near-hand entry also acts as A after running --calibrate-hand.
The sensor reports reflected IR intensity, not a distance in centimeters.
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
HAND_CONFIG = HERE / "hand_calibration.json"


class NearHand:
    """One A event per approach; sustained withdrawal is required to re-arm."""

    def __init__(self, near, far):
        if type(near) is not int or type(far) is not int or not 0 <= far < near <= 255:
            raise ValueError("Hand thresholds must satisfy 0 <= far < near <= 255.")
        self.near = near
        self.far = far
        self.armed = False  # First see clear space; do not trigger at startup.
        self.near_since = None
        self.far_since = None
        self.last_trigger = -float("inf")

    def update(self, value, now):
        if not self.armed:
            self.near_since = None
            if value <= self.far:
                if self.far_since is None:
                    self.far_since = now
                if now - self.far_since >= 0.35 and now - self.last_trigger >= 0.6:
                    self.armed = True
                    self.far_since = None
            else:
                self.far_since = None
            return False
        if value >= self.near:
            if self.near_since is None:
                self.near_since = now
            if now - self.near_since >= 0.08:
                self.armed = False
                self.near_since = self.far_since = None
                self.last_trigger = now
                return True
        else:
            self.near_since = None
        return False


def open_hand_sensor():
    import board
    from adafruit_apds9960.apds9960 import APDS9960

    sensor = APDS9960(board.I2C())
    sensor.enable_gesture = False  # Use quick proximity reads, not blocking gesture().
    sensor.enable_color = False
    sensor.proximity_gain = 0  # Fixed 1x gain for calibration and normal operation.
    sensor.enable_proximity = True
    time.sleep(0.15)
    return sensor


def percentile(samples, fraction):
    return sorted(samples)[round((len(samples) - 1) * fraction)]


def hand_thresholds(empty, outside, near):
    """Accept calibration only when 3 cm and 5 cm readings are separated."""
    outside_high = max(percentile(empty, 0.95), percentile(outside, 0.95))
    near_low = percentile(near, 0.10)
    if near_low - outside_high < 8:
        raise ValueError(
            f"3 cm and 5 cm cannot be separated reliably: "
            f"outside high={outside_high}, near low={near_low}. "
            "Keep the sensor uncovered, use the same palm angle, and recalibrate. "
            "If readings saturate or overlap, share the printed results."
        )
    return {"version": 1, "gain": 0, "near": near_low,
            "far": (outside_high + near_low) // 2, "reference_cm": 3}


def calibrate_hand(path=HAND_CONFIG):
    """Interactive real-device calibration; never invent a 3 cm threshold."""
    sensor = open_hand_sensor()
    print("APDS9960 connected. Values are 0..255 IR intensity, not centimeters.")

    def sample(prompt):
        input(prompt + " 然后按回车，保持姿势约 3 秒。")
        time.sleep(0.2)
        values = []
        for _ in range(50):
            values.append(sensor.proximity)
            print(f"读取中: {values[-1]:3d}", end="\r", flush=True)
            time.sleep(0.05)
        print(f"最低={min(values)}, 中间值={percentile(values, 0.5)}, 最高={max(values)}")
        return values

    try:
        empty = sample("第 1 步：把手和其他物体移开传感器正面至少 20 cm。")
        outside = sample("第 2 步：手掌正对传感器，停在约 5 cm 处。")
        near = sample("第 3 步：同一只手、同一角度，停在约 3 cm 处。")
        config = hand_thresholds(empty, outside, near)
        # Commit the new calibration atomically; a failed attempt keeps the old one.
        path = Path(path)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent,
                                             prefix=".hand-calibration-", delete=False) as f:
                temp_name = f.name
                json.dump(config, f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, path)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
        print(f"校准完成：near={config['near']}, far={config['far']}。已保存到 {path}")
        print("先把手移开，再运行种树程序。挥近一次相当于按一次 A。")
    finally:
        sensor.enable_proximity = False


def load_hand_control(path=HAND_CONFIG):
    path = Path(path)
    if not path.is_file():
        print("Hand control off: run python tree_focus_timer.py --calibrate-hand first.")
        return None, None
    config = json.loads(path.read_text())
    if config.get("version") != 1 or config.get("gain") != 0:
        raise ValueError("Unsupported hand calibration; run --calibrate-hand again.")
    gate = NearHand(config["near"], config["far"])
    sensor = open_hand_sensor()
    print(f"Hand control on: near={gate.near}, release={gate.far}. Move hand away to arm.")
    return sensor, gate


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

    @property
    def total(self):
        # Compatible with the original daily save file: no migration or reset.
        return sum(self.days.values())

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
        self.completed_at = None

    @property
    def stage(self):
        total = self.progress.total
        if self.state == "done" and total and total % 4 == 0:
            return 4  # Celebrate the new tree in the center until A resets.
        return total % 4

    @property
    def tree_count(self):
        return self.progress.total // 4

    @property
    def old_trees(self):
        last = self.tree_count
        if self.stage == 4:
            last -= 1  # The newest tree is already visible in the center.
        return [(number, min(11, 4 + self.progress.total - number * 4))
                for number in range(max(1, last - 1), last + 1)]

    @property
    def countdown(self):
        seconds = self.duration if self.state == "ready" else math.ceil(self.remaining)
        return f"{seconds // 60:02}:{seconds % 60:02}"

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
                self.completed_at = now
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


def tree_sprite(stage, tree_id=0, transition_elapsed=10.0):
    """Pixel stages 0..11: seed through growth, flowers, fruit and autumn."""
    sprite = Image.new("RGBA", (49, 49))
    d = ImageDraw.Draw(sprite)
    if stage == 0:
        d.rectangle((22, 41, 26, 44), fill=(152, 110, 63))
        d.rectangle((23, 40, 25, 42), fill=(207, 167, 98))
        d.point((24, 41), fill=(243, 210, 135))
        return sprite
    top = {1: 37, 2: 30, 3: 25}.get(stage, 21)
    d.rectangle((23, top, 25, 44), fill=(107, 129, 73) if stage < 3 else (126, 91, 59))
    d.line((25, top, 25, 43), fill=(174, 148, 84))
    if stage <= 2:
        d.rectangle((17, top - 2, 22, top), fill=(131, 170, 96))
        d.rectangle((19, top + 1, 23, top + 2), fill=(92, 138, 79))
        d.rectangle((26, top - 4, 31, top - 2), fill=(167, 194, 110))
        d.rectangle((25, top - 1, 29, top), fill=(109, 157, 85))
        if stage == 2:
            d.rectangle((17, 37, 23, 39), fill=(106, 145, 79))
            d.rectangle((26, 35, 31, 37), fill=(139, 168, 87))
        return sprite

    # A tree's stable ID gives slight color variation without random redrawing.
    tint = (tree_id % 3) * 5
    if stage == 3:
        colors = [(94, 138, 80), (136, 173, 92), (177, 196, 111)]
        blocks = [(15, 21, 32, 30), (11, 24, 36, 28), (19, 17, 28, 23)]
    else:
        if stage == 4:
            colors = [(91, 134, 77), (130, 167, 87), (166, 187, 105)]
        elif stage == 11:
            colors = [(156, 111, 48), (197, 152, 61), (226, 184, 84)]
        else:
            colors = [(46, 94, 68), (67, 122, 77), (107, 152, 87)]
        blocks = [(8, 17, 40, 29), (4, 20, 44, 26), (13, 12, 35, 20), (19, 9, 30, 16)]
    colors = [(r, min(255, g + tint), b) for r, g, b in colors]
    for box in blocks:
        d.rectangle(box, fill=colors[0])
    d.rectangle((16, top - 5, 31, top + 1), fill=colors[1])
    d.rectangle((22, top - 8, 30, top - 5), fill=colors[2])
    d.rectangle((32, top - 1, 34, top + 2), fill=colors[2])
    d.line((22, 32, 19, 29), fill=(126, 91, 59))

    blooms = [(14, 21), (23, 14), (33, 22)]
    if stage == 6:  # buds
        for x, y in blooms:
            d.rectangle((x, y, x + 1, y + 2), fill=(202, 137, 143))
            d.point((x, y - 1), fill=(240, 179, 163))
    elif stage == 7:  # flowers
        for x, y in blooms:
            d.rectangle((x - 2, y - 1, x + 2, y + 1), fill=(231, 160, 166))
            d.rectangle((x - 1, y - 2, x + 1, y + 2), fill=(244, 186, 178))
            d.point((x, y), fill=(251, 215, 122))
    elif stage == 8:  # flowers fall once, then petals rest on the soil
        for i, (x, y) in enumerate(blooms):
            amount = min(1.0, max(0.0, transition_elapsed - i * 0.25) / 3.0)
            px = x + int(math.sin(amount * math.pi) * (3 if i % 2 else -3))
            py = round(y + (44 - y) * amount)
            d.rectangle((px, py, px + 1, py + 1), fill=(224, 155, 158))
    elif stage in (9, 10, 11):
        for i, (x, y) in enumerate(blooms):
            if stage == 9:
                fy = y + 1
            elif stage == 10:
                amount = min(1.0, max(0.0, transition_elapsed - i * 0.4) / 2.5)
                fy = round(y + 1 + (43 - y - 1) * amount * amount)
            else:
                fy = 43
            d.rectangle((x - 1, fy, x + 1, fy + 2), fill=(218, 124, 69))
            d.point((x, fy), fill=(253, 184, 95))
    return sprite


def place_tree(scene, stage, x, base_y, scale=1.0, tree_id=0, transition_elapsed=10.0):
    sprite = tree_sprite(stage, tree_id, transition_elapsed)
    size = round(49 * scale)
    if size != 49:
        sprite = sprite.resize((size, size), Image.Resampling.NEAREST)
    scene.paste(sprite, (x - round(24 * scale), base_y - round(44 * scale)), sprite)


def scale_frame(scene):
    output = Image.new("RGB", (240, 135), BG)
    output.paste(scene.resize((240, 134), Image.Resampling.NEAREST), (0, 0))
    return output


def footer(scene, state, countdown, clock_view=False):
    action = "start" if state == "ready" else "reset"
    target = "tree" if clock_view else "time"
    pixel_text(scene, (3, 57), f"A:{action} B:{target}", (125, 139, 137))
    # Hand-drawn 5x7 digits keep the small countdown unambiguous on the LCD.
    glyphs = {
        "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
        "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
        "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
        "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
        "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
        "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
        "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
        "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
        "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
        "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
        ":": ["0", "1", "0", "0", "1", "0", "0"],
    }
    text_width = sum(len(glyphs[c][0]) + 1 for c in countdown) - 1
    x = 117 - text_width
    draw = ImageDraw.Draw(scene)
    for character in countdown:
        for y, row in enumerate(glyphs[character]):
            for offset, bit in enumerate(row):
                if bit == "1":
                    draw.point((x + offset, 57 + y), fill=(223, 204, 153))
        x += len(glyphs[character][0]) + 1


def garden_frame(timer, elapsed=0.0, demo=False, transition_elapsed=10.0):
    """Current plant plus up to two permanent trees. No daily growth reset."""
    scene = Image.new("RGB", (120, 67), BG)
    draw = ImageDraw.Draw(scene)
    draw.polygon([(69, 0), (80, 0), (93, 47), (35, 47)], fill=(23, 28, 32))
    draw.polygon([(71, 0), (78, 0), (82, 47), (46, 47)], fill=(32, 34, 34))
    draw.polygon([(73, 0), (76, 0), (72, 47), (54, 47)], fill=(43, 40, 34))
    draw.rectangle((0, 48, 119, 66), fill=(17, 23, 25))
    draw.rectangle((0, 47, 119, 49), fill=(81, 75, 53))
    draw.rectangle((0, 50, 119, 52), fill=(45, 40, 33))
    draw.rectangle((30, 47, 88, 49), fill=(103, 89, 61))
    for x, y in [(9, 49), (27, 50), (36, 48), (49, 50), (73, 49), (84, 48), (105, 49)]:
        draw.point((x, y), fill=(129, 106, 66))

    old_trees = timer.old_trees
    positions = [101] if len(old_trees) == 1 else [18, 101]
    for (tree_id, stage), x in zip(old_trees, positions):
        place_tree(scene, stage, x, 46, 0.70, tree_id, transition_elapsed)
    current_id = timer.tree_count if timer.stage == 4 else timer.tree_count + 1
    place_tree(scene, timer.stage, 60, 47, tree_id=current_id)

    if timer.state == "running":
        for index in range(12):
            y = int((elapsed * 9 + index * 13) % 44) + 3
            x = (index * 29 + 9 - y // 6) % 120
            draw.line((x, y, x, min(46, y + 2)), fill=(70, 95, 106))
    heading = {"ready": "READY", "running": "FOCUS", "done": "REST"}[timer.state]
    if timer.state == "done" and timer.stage == 4:
        heading = "TREE GROWN"
    pixel_text(scene, (3, 2), heading, (184, 193, 180))
    if demo:
        pixel_text(scene, (95, 2), "DEMO", (135, 124, 105))
    footer(scene, timer.state, timer.countdown)
    return scale_frame(scene)


def clock_frame(timer, local_now, demo=False):
    scene = Image.new("RGB", (120, 67), BG)
    pixel_text(scene, (4, 3), local_now.strftime("NEW YORK %Z"), (214, 181, 122))
    clock_font = ImageFont.load_default(size=17)
    mask = Image.new("L", scene.size)
    ImageDraw.Draw(mask).text((4, 16), local_now.strftime("%H:%M:%S"), font=clock_font, fill=255)
    scene.paste((223, 228, 216), (0, 0), mask.point(lambda n: 255 if n >= 100 else 0))
    pixel_text(scene, (4, 37), local_now.strftime("%Y-%m-%d"), (149, 159, 151))
    status = {"ready": "Ready", "running": "Focus", "done": "Rest"}[timer.state]
    pixel_text(scene, (4, 47), f"{status}   Trees: {timer.tree_count}", (164, 184, 138))
    footer(scene, timer.state, timer.countdown, clock_view=True)
    return scale_frame(scene)


def fade_in(frame, elapsed):
    """A gentle, single fade from black when a new focus session starts."""
    amount = max(0.0, min(1.0, elapsed / 1.5))
    if amount == 1.0:
        return frame
    return Image.blend(Image.new("RGB", frame.size), frame, amount)


def run(demo=False, no_hand=False):
    # Import hardware libraries only on the Pi, keeping drawing testable on Mac.
    import board
    import digitalio
    import adafruit_rgb_display.st7789 as st7789

    progress = Progress(HERE / ("tree_progress_demo.json" if demo else "tree_progress.json"))
    timer = Timer(progress, 20 if demo else 25 * 60, datetime.now(LOCAL_TZ).date().isoformat())
    audio = Audio(HERE / "whitenoise.mp3")
    sensor = hand_gate = None
    if not no_hand:
        try:
            sensor, hand_gate = load_hand_control(HERE / "hand_calibration.json")
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            print(f"Hand sensor unavailable: {error}. Physical A/B still work.")
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
            hand_event = False
            if sensor is not None and hand_gate is not None:
                try:
                    hand_event = hand_gate.update(sensor.proximity, now)
                except (OSError, RuntimeError) as error:
                    print(f"Hand sensor read failed: {error}. Using physical buttons until restart.")
                    hand_gate = None
            if b_pressed and not previous_b and now - last_b >= 0.2:
                timer.press_b()
                last_b = now
            a_event = a_pressed and not previous_a and now - last_a >= 0.2
            # A button press and nearby hand in the same motion count only once.
            hand_event = hand_event and not a_pressed and now - last_a >= 0.6
            if a_event or hand_event:
                action = timer.press_a(now, day)
                if action == "start":
                    audio.start()
                else:
                    audio.stop()
                last_a = now
                if hand_event:
                    print(f"Hand -> A: {action}")
            previous_a, previous_b = a_pressed, b_pressed
            if timer.tick(now, day) == "stop":
                audio.stop()
            if timer.state == "running":
                audio.check()
            if timer.view == "clock":
                frame = clock_frame(timer, local_now, demo)
            else:
                transition_elapsed = now - timer.completed_at if timer.completed_at is not None else 10.0
                frame = garden_frame(timer, now - timer.started_at, demo, transition_elapsed)
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
        if sensor is not None:
            try:
                sensor.enable_proximity = False
            except (OSError, RuntimeError):
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="20-second sessions; separate demo progress")
    parser.add_argument("--calibrate-hand", action="store_true", help="measure APDS9960 at 3 cm and save thresholds")
    parser.add_argument("--no-hand", action="store_true", help="use physical buttons only")
    args = parser.parse_args()
    if args.calibrate_hand:
        calibrate_hand()
    else:
        run(demo=args.demo, no_hand=args.no_hand)
