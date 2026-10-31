"""
Part G: the bedtime hand-off for Sleep bot for pet. Hold an OK sign up to the camera;
the device says good night and starts the night shift (overnight.py --all).

    python bedtime.py              # wait for the OK sign, then start the night shift
    python bedtime.py --show       # also open a window with the hand drawn on it (Pi desktop / Pi Connect)
    python bedtime.py --speak      # also say "good night" out loud with espeak-ng (makes a sound)

Run it inside tmux (README Part H) so the night shift keeps going after you close the laptop:
    tmux new -s night
    python bedtime.py

The OK sign is a rule over MediaPipe's 21 hand landmarks, like the gestures in hand_pose.py:
thumb tip touches index tip, and the middle, ring and pinky fingers stay straight.
It has to be held for HOLD frames in a row, so a hand passing by does not start the night.
"""
import argparse
import datetime
import json
import math
import os
import subprocess
import sys
import time

import cv2

import HandTrackingModule as htm

HOLD = 15                                   # frames in a row (about a second)

parser = argparse.ArgumentParser()
parser.add_argument("--show", action="store_true", help="open a window (needs the Pi desktop)")
parser.add_argument("--speak", action="store_true", help="say good night with espeak-ng (makes a sound)")
args = parser.parse_args()


def dist(a, b):
    return math.hypot(a[1] - b[1], a[2] - b[2])


def is_ok_sign(lm):
    """Thumb tip (4) touches index tip (8); middle, ring and pinky tips are farther from the wrist than their middle joints."""
    size = dist(lm[0], lm[9])               # wrist to middle knuckle: the hand's own ruler, so distance to the camera does not matter
    if size < 1:
        return False
    pinch = dist(lm[4], lm[8]) < 0.35 * size
    straight = all(dist(lm[0], lm[tip]) > dist(lm[0], lm[pip]) for tip, pip in ((12, 10), (16, 14), (20, 18)))
    return pinch and straight


detector = htm.handDetector(maxHands=1, detectionCon=0)   # same setting as hand_pose.py (this value reaches MediaPipe as model_complexity 0, the fast model)
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    raise SystemExit("no webcam found: is it plugged in?")

print("Bedtime: hold up an OK sign to hand the night over (Ctrl-C to cancel)", flush=True)
held = 0
try:
    while held < HOLD:
        ok, img = cap.read()
        if not ok:
            time.sleep(0.5)
            continue
        img = detector.findHands(img, draw=args.show)
        lm = detector.findPosition(img, draw=False)
        held = held + 1 if lm and is_ok_sign(lm) else 0
        if args.show:
            cv2.putText(img, f"OK sign: {held}/{HOLD}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
            cv2.imshow("Bedtime", img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                raise KeyboardInterrupt
except KeyboardInterrupt:
    print("cancelled, the night shift was not started")
    sys.exit()

# the acknowledgement
now = datetime.datetime.now()
message = "Good night. I will watch for your pet until morning."
print(f"{now:%H:%M:%S} {message}", flush=True)
if args.show:
    cv2.putText(img, "Good night", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 0), 3)
    cv2.imshow("Bedtime", img)
    cv2.waitKey(3000)
    cv2.destroyAllWindows()
if args.speak:
    subprocess.run(["espeak-ng", message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
cap.release()                               # the night shift needs the camera

with open("night_log.jsonl", "a") as log:   # so the morning knows when the night was handed over
    log.write(json.dumps({"t": now.isoformat(timespec="seconds"), "handoff": "ok sign"}) + "\n")

os.execv(sys.executable, [sys.executable, "overnight.py", "--all"])
