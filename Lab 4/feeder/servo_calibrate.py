"""Find the two rotor end angles for the MS18 servo on Servo pHAT channel 0.

    python feeder/servo_calibrate.py

Type an angle (0-180) and press Enter to move there. When a pocket is centred
under the inlet, type `a` to save that angle as end A; turn ~180 degrees until
the other pocket is centred, type `b` to save end B. `q` saves and quits.
If the servo buzzes at an end, back off a few degrees.
"""

import json
from pathlib import Path

import pi_servo_hat

CONFIG = Path(__file__).resolve().parent / "feeder_config.json"
SERVO_CH = 0

hat = pi_servo_hat.PiServoHat(min_pt=0.5, max_pt=2.5)  # MS18: 500-2500 us
hat.restart()
cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
angle = 90
hat.move_servo_position(SERVO_CH, angle, 180)
print("At 90 (middle). Mount the double-arm horn vertical now if it is not on yet.")

while True:
    cmd = input(f"[{angle}] angle / a / b / q: ").strip().lower()
    if cmd == "q":
        break
    if cmd in ("a", "b"):
        cfg[f"end_{cmd}"] = angle
        print(f"end {cmd.upper()} = {angle}")
        continue
    try:
        angle = max(0, min(180, int(cmd)))
    except ValueError:
        print("type a number 0-180, a, b or q")
        continue
    hat.move_servo_position(SERVO_CH, angle, 180)

CONFIG.write_text(json.dumps(cfg, indent=2))
print(f"saved {CONFIG.name}: {cfg}")
