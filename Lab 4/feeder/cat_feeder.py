"""Cat feeder: APDS-9960 sees the cat -> speaker says dinner time -> the servo
turns the two-pocket rotor 180 degrees -> one portion drops into the bowl.

Run from the Lab 4 folder with the Lab 4 venv active:
    python feeder/cat_feeder.py              # wait for the cat
    python feeder/cat_feeder.py --feed-now   # dispense one portion and exit
    python feeder/cat_feeder.py --record     # also record 10 s of video after each feed

Hardware: Servo pHAT on Qwiic (own USB-C power), MS18 servo on channel 0,
APDS-9960 on Qwiic, Mini PiTFT on the GPIO header, USB speaker, USB webcam.
Run feeder/servo_calibrate.py first to find the two rotor end angles.
"""

import argparse
import csv
import json
import shutil
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

import board
import digitalio
import pi_servo_hat
from adafruit_apds9960.apds9960 import APDS9960
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "feeder_config.json"
LOG = HERE / "feed_log.csv"
VIDEOS = HERE / "videos"
SERVO_CH = 0
DEFAULTS = {
    "end_a": 10,         # rotor end angles from servo_calibrate.py
    "end_b": 170,
    "threshold": 30,     # APDS proximity (0-255) that counts as "cat at the bowl"
    "hold_s": 0.5,       # proximity must stay above threshold this long
    "cooldown_s": 60,    # minimum time between two portions
    "max_per_day": 8,
    "step_deg": 2,       # slow sweep so kibble is pushed, not crushed
    "step_delay": 0.02,
}


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text()))
    return cfg


class Screen:
    """Mini PiTFT, same pins as the Lab 2/3 code. Prints instead if it fails."""

    def __init__(self):
        try:
            import adafruit_rgb_display.st7789 as st7789
            self.disp = st7789.ST7789(board.SPI(), cs=digitalio.DigitalInOut(board.D5),
                                      dc=digitalio.DigitalInOut(board.D25), rst=None,
                                      baudrate=64000000, width=135, height=240,
                                      x_offset=53, y_offset=40)
            backlight = digitalio.DigitalInOut(board.D22)
            backlight.switch_to_output(value=True)
        except Exception as error:
            print(f"PiTFT unavailable: {error}")
            self.disp = None
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        try:
            self.big, self.small = ImageFont.truetype(font, 34), ImageFont.truetype(font, 16)
        except OSError:
            self.big = self.small = ImageFont.load_default()

    def show(self, title, line, color=(255, 255, 255)):
        if self.disp is None:
            return
        img = Image.new("RGB", (240, 135), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((10, 25), title, font=self.big, fill=color)
        draw.text((10, 90), line, font=self.small, fill=(180, 180, 180))
        self.disp.image(img, 90)


class Rotor:
    """Two-pocket rotor: every move between end A and end B drops one pocket."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.hat = pi_servo_hat.PiServoHat(min_pt=0.5, max_pt=2.5)  # MS18: 500-2500 us
        self.hat.restart()
        self.angle = cfg["end_a"]
        self.hat.move_servo_position(SERVO_CH, self.angle, 180)
        time.sleep(0.5)

    def dispense(self):
        a, b = self.cfg["end_a"], self.cfg["end_b"]
        target = b if abs(self.angle - a) < abs(self.angle - b) else a
        step = self.cfg["step_deg"] if target > self.angle else -self.cfg["step_deg"]
        for angle in range(int(self.angle), int(target), step):
            self.hat.move_servo_position(SERVO_CH, angle, 180)
            time.sleep(self.cfg["step_delay"])
        self.hat.move_servo_position(SERVO_CH, target, 180)
        time.sleep(0.4)
        self.angle = target


def say(text):
    if shutil.which("espeak"):
        subprocess.Popen(["espeak", "-s", "150", text], stderr=subprocess.DEVNULL)
    elif (HERE / "dinner.wav").exists():
        subprocess.Popen(["aplay", "-q", str(HERE / "dinner.wav")])


def record_clip(seconds=10):
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found, skipping video")
        return
    VIDEOS.mkdir(exist_ok=True)
    out = VIDEOS / f"feed_{datetime.now():%Y%m%d_%H%M%S}.mp4"
    subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "v4l2", "-video_size", "640x480",
                      "-t", str(seconds), "-i", "/dev/video0", "-c:v", "libx264", "-preset", "veryfast",
                      "-pix_fmt", "yuv420p", str(out)])
    print(f"recording {out.name}")


def log_feed(proximity):
    new = not LOG.exists()
    with LOG.open("a", newline="") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(["time", "proximity"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), proximity])


def feed(rotor, screen, args, proximity, count):
    screen.show("Feeding", "Dinner time!", (255, 200, 0))
    say("Dinner time!")
    time.sleep(1.0)
    rotor.dispense()
    log_feed(proximity)
    if args.record:
        record_clip()
    screen.show("Done", f"portions today: {count}", (0, 220, 120))
    print(f"{datetime.now():%H:%M:%S} fed one portion (proximity {proximity}, today {count})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed-now", action="store_true", help="dispense one portion and exit")
    parser.add_argument("--record", action="store_true", help="record a 10 s clip after each feed")
    args = parser.parse_args()
    cfg = load_config()
    screen = Screen()
    rotor = Rotor(cfg)

    if args.feed_now:
        feed(rotor, screen, args, -1, 1)
        return

    apds = APDS9960(board.I2C())
    apds.enable_proximity = True
    above_since, armed = None, True
    last_feed, today, count = -cfg["cooldown_s"], date.today(), 0
    print(f"Ready. threshold={cfg['threshold']}  ends={cfg['end_a']}/{cfg['end_b']}  Ctrl+C to stop")
    screen.show("Ready", "waiting for the cat")
    try:
        while True:
            now, p = time.monotonic(), apds.proximity
            if date.today() != today:
                today, count = date.today(), 0
            if p >= cfg["threshold"]:
                above_since = above_since or now
                held = now - above_since >= cfg["hold_s"]
                if armed and held and now - last_feed >= cfg["cooldown_s"] and count < cfg["max_per_day"]:
                    count += 1
                    feed(rotor, screen, args, p, count)
                    last_feed, armed = time.monotonic(), False
            else:
                above_since = None
                if p < cfg["threshold"] - 10:      # cat left: next visit can trigger again
                    armed = True
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        screen.show("Off", "")


if __name__ == "__main__":
    main()
