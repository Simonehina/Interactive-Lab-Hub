# Previous versions

Earlier stages of the Lab 2 timer, kept so the iteration is visible. The
version that runs is `tree_focus_timer.py` in the Lab 2 folder above.

| File | What it was |
|---|---|
| `incense_timer.py` | The first direction: an incense holder as the timer. The screen drew a stick burning down and a bell rang when it was gone. Dropped because sensing when a stick has actually finished burning turned out to be the hard part. |
| `part2_focus_timer.py` | The first working build. Two PiTFT buttons, a plain countdown, and white noise during a session. |
| `tree_focus_timer_before_forest.py` | Added the pixel garden. Four completed sessions grew one tree, capped at one tree per day. |
| `tree_focus_timer_before_hand.py` | Removed the daily cap so trees accumulate into a permanent forest. Still button-only, no sensor yet. |

The final version replaces the button with an APDS9960 proximity sensor, so a
hand passing over the holder starts a session.
