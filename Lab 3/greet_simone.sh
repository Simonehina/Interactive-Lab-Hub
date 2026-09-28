#!/usr/bin/env bash
# Part 1A: greet me by name with my favorite engine, Piper.
# Written in the style of speech-scripts/piper_demo.sh; run it with the Lab 3 venv active.
set -euo pipefail

VOICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/voices"

python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --output-raw \
  -- "Hi Simone, Hi Simone" \
  | aplay -r 22050 -f S16_LE -t raw -
