"""
Part I: the morning reveal for Sleep bot for pet. Reads the night's log, lists when the camera
actually saw the pet and how long each visit to the bowls lasted, lets Qwen guess what the pet was
"saying" at those moments, and writes a web page with all of it plus the time-lapse, so the owner
can look at it on a phone the next day.

    python morning_pet.py                                   # print the report and write report/index.html
    python morning_pet.py --serve                           # then serve the page at http://pipi.local:8000 until Ctrl-C
    python morning_pet.py --speak                           # also read the guess aloud with espeak-ng (makes a sound)
    python morning_pet.py --dir real_nights/run1_30min_every10s   # a night kept in another folder
    python morning_pet.py --log fake_nights/fake_night2.jsonl
    python morning_pet.py --model qwen3:0.6b

It is honest about a quiet night: if the log never shows a pet, it says so and does not ask the model.
The page only goes into report/, and --serve only serves that folder, so it stays on the Pi and your home network.
"""
import argparse
import collections
import datetime
import html
import json
import os
import pathlib
import shutil
import subprocess

import requests

PETS = ("cat", "dog")                       # same list as interpret() in yolo_to_qwen.py
VISIT_GAP = 120                             # seconds away from the bowls that still count as the same visit
MAX_SHOTS = 24                              # snapshots on the page, spread over the night

parser = argparse.ArgumentParser()
parser.add_argument("--dir", default=".", help="folder with night_log.jsonl, snaps/ and lapse.mp4")
parser.add_argument("--log", help="the log to read (default: night_log.jsonl in --dir)")
parser.add_argument("--model", default="qwen3.5:0.8b")
parser.add_argument("--speak", action="store_true", help="read the guess aloud with espeak-ng (makes a sound)")
parser.add_argument("--serve", action="store_true", help="serve the page on port 8000 after writing it")
args = parser.parse_args()
night = pathlib.Path(args.dir)
log_path = pathlib.Path(args.log) if args.log else night / "night_log.jsonl"


def has_pet(e):
    return any(f" {p}(s) at " in e["reading"] for p in PETS)


def when(e):
    return datetime.datetime.fromisoformat(e["t"])


entries = [json.loads(line) for line in open(log_path) if line.strip()]
readings = [e for e in entries if "reading" in e]
pet_seen = [e for e in readings if has_pet(e)]
handoff = next((e for e in entries if "handoff" in e), None)
beats = sum(1 for e in entries if e.get("alive"))
end_t = entries[-1]["t"] if entries else ""
frames = sorted((night / "lapse").glob("*.jpg"))
if frames:                                  # a quiet stretch writes nothing new to the log, but the time-lapse keeps going
    f = frames[-1].stem
    end_t = max(end_t, f"{f[:4]}-{f[4:6]}-{f[6:8]}T{f[9:11]}:{f[11:13]}:{f[13:15]}")
span = f"{entries[0]['t'][11:16]} to {end_t[11:16]}" if entries else "no entries"
per_hour = dict(sorted(collections.Counter(e["t"][11:13] + ":00" for e in pet_seen).items()))

# A visit: the pet is in view from a reading with a pet until the next reading without one,
# and stretches less than VISIT_GAP apart are joined, so stepping out of frame for a moment does not split it.
visits = []
for e, nxt in zip(readings, readings[1:] + [None]):
    if not has_pet(e):
        continue
    start, end = when(e), when(nxt) if nxt else when(entries[-1])
    if visits and (start - visits[-1][1]).total_seconds() < VISIT_GAP:
        visits[-1][1] = end
    else:
        visits.append([start, end])


def length(a, b):
    secs = (b - a).total_seconds()
    return "under a minute" if secs < 60 else f"{round(secs / 60)} min"


visit_lines = [f"{a:%H:%M}-{b:%H:%M} ({length(a, b)})" for a, b in visits]

print(f"Watched {span}" + (f", handed over at {handoff['t'][11:16]} with an OK sign" if handoff else ""))
print(f"{len(readings)} changes, {len(pet_seen)} with a pet in view, {beats} heartbeats")
print("pet sightings per hour:", per_hour)
print("visits to the bowls:", ", ".join(visit_lines) or "none")


def say(text):
    print("\n" + text)
    if args.speak:
        subprocess.run(["espeak-ng", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


guess, digest = None, ""
if not pet_seen:                            # nothing to guess from: say so, do not ask the model
    say(f"Quiet night. The camera watched from {span} and did not see your pet.")
else:
    digest = "\n".join(f'{e["t"][11:19]} {e["reading"]}' for e in pet_seen[-60:])   # keep the prompt small
    print("\nWhat the camera saw (from the log):\n" + digest)

    # The small model copies raw log lines back, so it gets only the visits: when, and for how long.
    # YOLO only says where the pet was, not what it did; next to the bowls it was most likely eating or drinking.
    # The detector sometimes calls the same pet a dog, so the pet is whatever it was called most often.
    pet = collections.Counter(p for e in pet_seen for p in PETS if f" {p}(s) at " in e["reading"]).most_common(1)[0][0]
    longest = sorted(sorted(visits, key=lambda v: v[1] - v[0])[-3:])                 # up to three, in time order
    times = "\n".join(f"{a:%H:%M} (stayed {length(a, b)})" for a, b in longest)
    prompt = f"""A camera sits next to a {pet}'s food and water bowls. The {pet} came to the bowls at these times:
{times}

For each time, write one short line the {pet} might have said about eating or drinking, in the {pet}'s own voice.
Answer only with the lines, one per time, in this form:
[time] "[what the {pet} says]\""""

    r = requests.post("http://localhost:11434/api/generate", json={
        "model": args.model,
        "prompt": prompt,
        "think": False,
        "stream": False,
        "options": {"num_ctx": 4096, "temperature": 0.5, "num_predict": 200},
    }, timeout=600)
    r.raise_for_status()
    print("\nWhat your pet might have said (a guess by Qwen):")
    guess = r.json()["response"].strip()
    say(guess)

# The page: everything above, plus the time-lapse and a few snapshots, in report/ (yesterday's page is replaced).
out = pathlib.Path("report")
shutil.rmtree(out, ignore_errors=True)
(out / "snaps").mkdir(parents=True)
snaps = sorted((night / "snaps").glob("*.jpg"))
shots = snaps[::-(-len(snaps) // MAX_SHOTS) or 1]
for s in shots:
    shutil.copy(s, out / "snaps" / s.name)
lapse = night / "lapse.mp4"
if lapse.exists():
    shutil.copy(lapse, out / "lapse.mp4")

esc = html.escape
date = entries[0]["t"][:10] if entries else ""
bubbles = "".join(f"<p class='bubble'>{esc(line)}</p>" for line in (guess or "").splitlines() if line.strip())
figures = "".join(f"<figure><img src='snaps/{s.name}' loading='lazy' alt='snapshot'><figcaption>"
                  f"{s.stem[9:11]}:{s.stem[11:13]}:{s.stem[13:15]}</figcaption></figure>" for s in shots)
summary = (f"Watched {span}" + (f", handed over at {handoff['t'][11:16]} with an OK sign" if handoff else "")
           + f". {len(pet_seen)} of {len(readings)} changes had your pet in view.")
page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sleep bot for pet</title>
<style>
  :root {{ --bg: #fbf6ee; --ink: #2b2620; --soft: #7a6f62; --card: #fffdf8; --line: #e6dccd; --accent: #c8642c; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #1d1a17; --ink: #efe7dc; --soft: #a99d8f; --card: #27231f; --line: #3a342e; --accent: #e8925d; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 17px/1.5 -apple-system, system-ui, sans-serif; }}
  main {{ max-width: 680px; margin: 0 auto; padding: 24px 16px 48px; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1.05rem; margin: 32px 0 10px; color: var(--accent); }}
  .soft {{ color: var(--soft); margin: 0; }}
  ul {{ padding-left: 20px; margin: 0; }}
  .bubble {{ background: var(--card); border: 1px solid var(--line); border-radius: 18px 18px 18px 4px; padding: 10px 14px; margin: 0 0 10px; }}
  video {{ width: 100%; border-radius: 12px; background: #000; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }}
  figure {{ margin: 0; }} img {{ width: 100%; border-radius: 8px; display: block; }}
  figcaption {{ font-size: 0.8rem; color: var(--soft); }}
  details pre {{ white-space: pre-wrap; font-size: 0.8rem; background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
</style></head><body><main>
<h1>Sleep bot for pet</h1>
<p class="soft">{esc(date)} &middot; {esc(summary)}</p>
<h2>Visits to the bowls</h2>
{"<ul>" + "".join(f"<li>{esc(v)}</li>" for v in visit_lines) + "</ul>" if visits else
 f"<p>Quiet night. The camera watched from {esc(span)} and did not see your pet.</p>"}
{f"<h2>What your pet might have said</h2>{bubbles}<p class='soft'>A guess by Qwen ({esc(args.model)}). YOLO only sees where the pet is, not what it does.</p>" if guess else ""}
{"<h2>Time-lapse</h2><video src='lapse.mp4#t=0.1' controls playsinline muted preload='metadata'></video>" if lapse.exists() else ""}
{f"<h2>Snapshots</h2><div class='grid'>{figures}</div>" if shots else ""}
{f"<h2>The log</h2><details><summary>Moments with your pet in view</summary><pre>{esc(digest)}</pre></details>" if digest else ""}
</main></body></html>"""
(out / "index.html").write_text(page)
print(f"\nPage written to {out}/index.html ({len(shots)} snapshots" + (", time-lapse)" if lapse.exists() else ")"))

if args.serve:
    import functools
    import http.server

    class Handler(http.server.SimpleHTTPRequestHandler):
        """Adds byte ranges, which Safari on a phone needs before it will play the video."""
        left = None

        def send_head(self):
            path = self.translate_path(self.path)
            rng = self.headers.get("Range", "")
            if not rng.startswith("bytes=") or not os.path.isfile(path):
                return super().send_head()
            size = os.path.getsize(path)
            a, _, b = rng[6:].split(",")[0].partition("-")
            start, end = (size - int(b), size - 1) if not a else (int(a), min(int(b or size - 1), size - 1))
            f = open(path, "rb")
            f.seek(start)
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.left = end - start + 1
            return f

        def copyfile(self, source, outputfile):
            if self.left is None:
                return super().copyfile(source, outputfile)
            while self.left > 0:
                chunk = source.read(min(65536, self.left))
                if not chunk:
                    break
                outputfile.write(chunk)
                self.left -= len(chunk)

        def log_message(self, *a):          # keep the terminal quiet for the video
            pass

    print("Open http://pipi.local:8000 on a phone or laptop on the same Wi-Fi (Ctrl-C to stop)", flush=True)
    try:
        http.server.ThreadingHTTPServer(("", 8000), functools.partial(Handler, directory=str(out))).serve_forever()
    except KeyboardInterrupt:
        pass
