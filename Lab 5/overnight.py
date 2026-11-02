"""
Part H: the night shift. Log the interpreter's readings all night, headless.
It only senses and logs; the reasoning waits for the morning (morning.py).

    python overnight.py                  # one look every 5 s until Ctrl-C
    python overnight.py --interval 30    # look less often
    python overnight.py --all            # log the other objects too, not only people (see Part E)
    python overnight.py --minutes 30     # stop by itself after half an hour
    python overnight.py --lapse 10       # also save a frame every 10 s into lapse/, and make lapse.mp4 when the night ends

Fake a night first: run it for thirty seconds while you walk around, Ctrl-C, then run morning.py.

Writes night_log.jsonl (one JSON object per line) and a snapshot in snaps/ whenever
the reading changes to something other than "nobody". Writes an "alive" line every
10 minutes so you can tell a quiet night from a crashed one.
Start it in tmux or with nohup so it survives the ssh disconnect (see the README).
"""
import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time

import cv2

from yolo_to_qwen import interpret, model      # the interpreter you tuned in Part E

parser = argparse.ArgumentParser()
parser.add_argument("--interval", type=float, default=5, help="seconds between looks")
parser.add_argument("--all", action="store_true", help="detect all 80 classes, not only people")
parser.add_argument("--minutes", type=float, default=0, help="stop after this many minutes (0: until Ctrl-C)")
parser.add_argument("--lapse", type=float, default=0, help="save a frame every this many seconds into lapse/ (0: off)")
args = parser.parse_args()
classes = None if args.all else [0]        # class 0 is "person", as in yolo_to_qwen.py

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
pathlib.Path("snaps").mkdir(exist_ok=True)
if args.lapse:
    pathlib.Path("lapse").mkdir(exist_ok=True)
log = open("night_log.jsonl", "a")
last, last_beat = None, 0.0
t_end = time.time() + args.minutes * 60 if args.minutes else None
next_lapse = time.time()


def write(entry):
    log.write(json.dumps(entry) + "\n")
    log.flush()


print("night shift started, Ctrl-C to stop", flush=True)
while t_end is None or time.time() < t_end:
    try:
        for _ in range(4):          # the webcam buffers a few frames; skip the stale ones
            cap.grab()
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("no frame")
        r = model.predict(frame, imgsz=640, conf=0.25, classes=classes, verbose=False)[0]   # bigger frame and a lower bar so a pet across the room is not missed; interpret() keeps 0.4 for everything but pets
        reading = interpret(r)
        now = datetime.datetime.now()
        ts = now.isoformat(timespec="seconds")
        if reading != last:
            write({"t": ts, "reading": reading})
            if reading != "nobody":
                cv2.imwrite(f"snaps/{now:%Y%m%d-%H%M%S}.jpg", frame)
            last = reading
        if args.lapse and time.time() >= next_lapse:   # on a schedule, so the frames average one per --lapse seconds
            view = r.plot()                             # the frame with YOLO's boxes drawn on it, as in yolo_to_qwen.py
            for color, thick in (((0, 0, 0), 4), ((0, 255, 0), 2)):   # black outline, then green, at the bottom so it clears YOLO's labels
                cv2.putText(view, f"{now:%H:%M:%S} {reading}", (10, view.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, thick)
            cv2.imwrite(f"lapse/{now:%Y%m%d-%H%M%S}.jpg", view)
            next_lapse += args.lapse
        if time.time() - last_beat > 600:
            write({"t": ts, "alive": True})
            last_beat = time.time()
        time.sleep(args.interval)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("hiccup:", e, flush=True)
        time.sleep(args.interval)

cap.release()
write({"t": datetime.datetime.now().isoformat(timespec="seconds"), "stopped": True})   # so the morning knows when the watch ended
print("night shift stopped", flush=True)
if args.lapse:                              # the time-lapse is part of what the night leaves behind
    subprocess.run([sys.executable, "lapse.py"])
