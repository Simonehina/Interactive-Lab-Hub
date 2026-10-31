"""
Part I: the morning reveal for Sleep bot for pet. Reads night_log.jsonl, lists what the
camera actually saw of the pet, then lets Qwen guess what the pet was "saying" at those moments.

    python morning_pet.py                                   # print the report
    python morning_pet.py --speak                           # also read the guess aloud with espeak-ng (makes a sound)
    python morning_pet.py --log fake_nights/fake_night2.jsonl
    python morning_pet.py --model qwen3:0.6b

It is honest about a quiet night: if the log never shows a pet, it says so and does not ask the model.
"""
import argparse
import collections
import json
import subprocess

import requests

PETS = ("cat", "dog")                       # same list as interpret() in yolo_to_qwen.py

parser = argparse.ArgumentParser()
parser.add_argument("--log", default="night_log.jsonl")
parser.add_argument("--model", default="qwen3.5:0.8b")
parser.add_argument("--speak", action="store_true", help="read the guess aloud with espeak-ng (makes a sound)")
args = parser.parse_args()

entries = [json.loads(line) for line in open(args.log) if line.strip()]
readings = [e for e in entries if "reading" in e]
pet_seen = [e for e in readings if any(f" {p}(s) at " in e["reading"] for p in PETS)]
handoff = next((e for e in entries if "handoff" in e), None)
beats = sum(1 for e in entries if e.get("alive"))
span = f"{entries[0]['t'][11:16]} to {entries[-1]['t'][11:16]}" if entries else "no entries"
per_hour = dict(sorted(collections.Counter(e["t"][11:13] + ":00" for e in pet_seen).items()))

print(f"Watched {span}" + (f", handed over at {handoff['t'][11:16]} with an OK sign" if handoff else ""))
print(f"{len(readings)} changes, {len(pet_seen)} with a pet in view, {beats} heartbeats")
print("pet sightings per hour:", per_hour)


def say(text):
    print("\n" + text)
    if args.speak:
        subprocess.run(["espeak-ng", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if not pet_seen:                            # nothing to guess from: say so, do not ask the model
    say(f"Quiet night. The camera watched from {span} and did not see your pet.")
    raise SystemExit

digest = "\n".join(f'{e["t"][11:19]} {e["reading"]}' for e in pet_seen[-60:])   # keep the prompt small
print("\nWhat the camera saw (from the log):\n" + digest)

prompt = f"""You are a bedside device that watched a pet overnight, from {span}. Below is every moment
the camera saw the pet (time, then what it saw; "nobody" means no person was in view).

{digest}

Guess what the pet might have been saying at up to three of these moments. Write one short line per
moment, starting with the time from the log, in the pet's own voice. Only use times and places that
appear in the log. Do not invent any other events."""

r = requests.post("http://localhost:11434/api/generate", json={
    "model": args.model,
    "prompt": prompt,
    "think": False,
    "stream": False,
    "options": {"num_ctx": 4096, "temperature": 0.5, "num_predict": 200},
}, timeout=600)
r.raise_for_status()
print("\nWhat your pet might have said (a guess by Qwen):")
say(r.json()["response"].strip())
