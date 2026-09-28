#!/usr/bin/env bash
# Part 1B: ask for a number out loud, record the answer, and transcribe it.
# Uses the course tools: Piper (as in piper_demo.sh), arecord, and transcribe.py.
# Run it with the Lab 3 venv active.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir voices \
  --output-raw \
  -- "How many pets do you have? Please answer with a number." \
  | aplay -q -r 22050 -f S16_LE -t raw -

echo "Recording the answer for 5 seconds..."
arecord -q -d 5 -f cd -c 1 -r 16000 pets_answer.wav
echo "Saved pets_answer.wav"

python speech-scripts/transcribe.py pets_answer.wav --model base.en | tee pets_answer.txt
