# Observant Systems: Overnight Sensation

**Team:** <mark>TODO: write Solo, or your team name and teammates.</mark>

**Members:** Simin Xu (sx333, Simonehina)

**Project name:** <mark>TODO: fill in once the Part 2 idea is decided.</mark>

<details>
	<summary><strong>Instructions for Students (Click to Expand)</strong></summary>
  
	**Submission Cleanup Reminder:**
	- This README.md contains extra instructional text for guidance.
	- Before submitting, remove all instructional text and example prompts from this file.
	- You may delete these sections or use the toggle/hide feature in VS Code to collapse them for a cleaner look.
	- Your final submission should be neat, focused on your own work, and easy to read for grading.
  
	This helps ensure your README.md is clear, professional, and uniquely yours!
</details>


<details>
<summary>Instructions</summary>

For lab this week, we focus on creating interactive systems that can detect and respond to events or stimuli in the environment of the Pi, like the Boat Detector we mentioned in lecture. 
Your **observant device** could, for example, count items, find objects, recognize an event or continuously monitor a room.

This lab will help you think through the design of observant systems, particularly corner cases that the algorithms need to be aware of.

**New this year: the AI runs on the Pi.** Your Pi 5 can run an object detector ([YOLO](https://docs.ultralytics.com/)) and a small language model ([Qwen](https://ollama.com/library/qwen3.5) through [Ollama](https://ollama.com)) completely offline. In Part 1 you get both running and connect them: YOLO *sees*, Qwen *reasons* about what was seen. These models are slow, but they have all night. In Part 2 you use them to design a **night-time interaction**: what you tell the device before bed, what it does while you sleep, and what it shows you when you wake up.

</details>

**Please indicate anyone that helped with this Lab here.**

<details>
<summary>Instructions</summary>

Be generous in acknowledging their contributions! And also recognizing any other influences (e.g. from YouTube, Github, Twitter) that informed your design. 

</details>

Claude (Anthropic's AI assistant) helped me break down the Lab 5 requirements and set up the structure of this README.

## Overview

<details>
<summary>Instructions</summary>

**Part 1: the tools**

A) [Set up your Pi for on-device AI](#part-a)

B) [See: recognize people in real time with YOLO](#part-b)

C) [See more: hands and pose with MediaPipe](#part-c)

D) [Reason: run Qwen on the Pi with Ollama](#part-d)

E) [Connect: from YOLO readings to Qwen reasoning](#part-e)

**Part 2: Overnight Sensation**

F) [Read Part 2 and storyboard your night-time interaction](#part-f)

G) [Design the interaction before bed](#part-g)

H) [Incorporate the observant system during sleep](#part-h)

I) [Design the interaction when awake](#part-i)

The tools from earlier versions of this lab (MobileNet, Teachable Machine, Moondream, audio analysis, classic OpenCV) live in the [legacy folder](legacy/README.md). They are optional, but any of them can be the sensor in your Part 2 system.

</details>


## Prep for Part 1

<details>
<summary>Instructions</summary>

Please check the instructions in [prep.md](prep.md) and complete them before lab. The installs in Part A take a while, so prep.md also tells you how to get a head start.

</details>

## The Report

<details>
<summary>Instructions</summary>

This readme.md page in your own repository should be edited to include the work you have done. You can delete everything but the headers and the sections between the \*\*\***stars**\*\*\*. Write the answers to the questions under the starred sentences. Include any material that explains what you did in this lab hub folder, and link it in the readme.

</details>

---

# Part 1

## Part A. 
### Set up your Pi for on-device AI

<details>
<summary>Instructions</summary>

Create a virtual environment and install the requirements. They include `ultralytics` (YOLO), which pulls in torch, so this takes a while:

```
pi@raspberrypi:~$ cd Interactive-Lab-Hub/Lab\ 5
pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python3 -m venv .venv
pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ source .venv/bin/activate
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ pip install -r requirements.txt
```

As in Lab 3, [`uv`](https://docs.astral.sh/uv/) is a much faster drop-in for `pip`: `pip install uv && uv pip install -r requirements.txt`.

</details>

### YOLO: download the nano model and export it for the Pi

<details>
<summary>Instructions</summary>

We use the nano model of [YOLO26](https://docs.ultralytics.com/models/yolo26/), exported once to NCNN, the format that runs fastest on the Pi. This downloads the weights:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python -c "from ultralytics import YOLO; YOLO('yolo26n.pt').export(format='ncnn')"
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ yolo export model=yolo26n.pt format=ncnn
```
If every ultralytics message is followed by a `--- Logging error ---` traceback ending in `UnicodeEncodeError: 'latin-1' codec can't encode character`, fix your shell's locale once::

```
echo 'export LANG=C.UTF-8' >> ~/.bashrc
echo 'export LC_ALL=C.UTF-8' >> ~/.bashrc
echo 'export PYTHONIOENCODING=utf-8' >> ~/.bashrc
source ~/.bashrc
```

The second command converts the .pt model to a .ncnn model.

Test it on an image from the internet. `project="$PWD"` keeps the output in `predict` in the current lab folder; without it, ultralytics writes to a `runs/` folder at the top of your git repo, where you will not think to look.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ yolo predict model=yolo26n_ncnn_model source=https://ultralytics.com/images/bus.jpg project="$PWD"
```

The result is in `predict/bus.jpg`: boxes around the people and the bus.

Now a photo of your own. Plug in the webcam and take one with `snap.py` (`--delay 3` gives you three seconds to get into the frame), or choose any picture you downloaded from the internet and put under this folder. Put your selected picture after the `source=` Then run the same command on it:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python snap.py --delay 3
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ yolo predict model=yolo26n_ncnn_model source=snap.jpg project=runs
```

Every run gets its own numbered folder, so this one is in `runs/predict2/snap.jpg`; the command prints where it saved. Keep `snap.jpg`, you will show it to Qwen in Part D.

</details>

### Ollama: install it and pull Qwen

<details>
<summary>Instructions</summary>

[Ollama](https://ollama.com) runs language models locally. Nothing leaves the Pi: no API key, no internet after the download.

```
pi@raspberrypi:~ $ curl -fsSL https://ollama.com/install.sh | sh
pi@raspberrypi:~ $ ollama pull qwen3.5:0.8b
pi@raspberrypi:~ $ ollama pull qwen3:0.6b
pi@raspberrypi:~ $ ollama list
```

| model | download | what it does |
|---|---|---|
| `qwen3.5:0.8b` | ~1.3 GB | text **and images**; the one we use in this lab |
| `qwen3:0.6b` | ~0.5 GB | text only, smaller and faster (~16 tokens/s on a Pi 5) |

</details>

\*\*\***Include a screenshot of `ollama list` showing your models.**\*\*\*

![ollama list on my Pi](images/ollama_list.png)


## Part B. 
### See: recognize people in real time with YOLO

<details>
<summary>Instructions</summary>

YOLO is an *object detector*: it finds every person, cup, cat and so on (the 80 [COCO](https://cocodataset.org/) classes), draws a box around each, and gives a confidence. For an observant system that is exactly what you want: *how many*, *where*, *how sure*.

Connect your webcam, connect to your Pi through **VNC** (the script opens a window), and run the person detector. Read `yolo_person.py` first; the loop at the bottom is the whole idea.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py
```

While it runs, walk in and out of the frame, sit down, turn your back, hold up a photo of a person on your phone. Watch the confidence number on the box change with each.

Then press q to quit and run it again with a flag. Each one changes a single thing:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --conf 0.2     # lower the bar: see what the model is unsure about
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --conf 0.7     # raise the bar: see what you lose
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --all          # all 80 classes, not only people: what else is on your desk, and what does it get wrong?
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --headless     # no window, only the printed readings: how it runs over ssh, and at night
```

</details>

\*\*\***Include a short video or screenshots of your experiments with the person detection. Write down three situations where it did not see you, or saw a person who was not there, and what you think the cause was.**\*\*\*

I ran `yolo_person.py` on the Pi and watched the window through Raspberry Pi Connect screen sharing. The frame-by-frame readings of every run are in [logs/](logs/).

**Default (`python yolo_person.py`, conf 0.4)**

- With two people in the frame, both were detected, and both detections were correct.
- With only my shoulders in the frame, I was detected on and off, at 0.45–0.56.
- With my face in the frame, the confidence was 0.90.
- A sculpture of a person shown on my phone was also detected as a person, with a high confidence of about 0.65.
- Anime characters and photos of people on my phone were also detected: the two photos at 0.48 and 0.71, the anime character at 0.61.

| Sculpture on my phone | Photos on my phone | Anime character on my phone |
|---|---|---|
| ![sculpture](images/partB_phone_sculpture.webp) | ![photos](images/partB_phone_photos.webp) | ![anime](images/partB_phone_anime.webp) |

**`--conf 0.2`**

- Even a small part of my hand was detected as a person: my palm filling the frame at 0.72, my fingers at 0.22. In a dark frame with only my neck, hair and collar, I was detected at 0.35.

| Palm | Fingers | Neck and collar |
|---|---|---|
| ![palm](images/partB_conf02_palm.webp) | ![fingers](images/partB_conf02_fingers.webp) | ![neck](images/partB_conf02_neck.webp) |

**`--conf 0.7`**

- Many things were no longer detected. The photo of a man was detected only on and off, at about 0.70. The sculpture was no longer detected.

| Palm, no box | Palm and face, 0.72 | Sculpture not detected |
|---|---|---|
| ![no box](images/partB_conf07_palm_nobox.webp) | ![face](images/partB_conf07_palm_face.webp) | ![sculpture](images/partB_conf07_sculpture.webp) |

| Photo, no box | Photo, 0.70 |
|---|---|
| ![photo no box](images/partB_conf07_photo_nobox.webp) | ![photo 0.70](images/partB_conf07_photo_070.webp) |

**`--all`**

- On my first run only "person" appeared. On my second run I held objects up to the camera: my phone was labeled cell phone (0.88), a cardboard box was labeled laptop (0.83), and a plastic milk-tea cup was labeled bottle (0.45). Over the whole second run (about 2,470 frames) it also reported tie, bird, cat, skateboard, remote, cup, vase, umbrella, toothbrush, tennis racket, teddy bear, fork and bed.
- The box was probably labeled a laptop because its shape looks like a laptop; it was actually a cardboard box.
- With more things it can recognize, the steps of recognizing and checking get longer, there are more possibilities, and it is more likely to make mistakes and be inaccurate. (Note from Claude: YOLO actually computes all 80 classes on every frame. The default setting keeps only "person", and `--all` shows the other classes that were filtered out before, so those wrong labels became visible.)

| Phone → cell phone | Cardboard box → laptop | Milk-tea cup → bottle |
|---|---|---|
| ![phone](images/partB_all_phone.webp) | ![box](images/partB_all_box_laptop.webp) | ![cup](images/partB_all_cup_bottle.webp) |

**`--headless`**

- No window, only one printed line per frame, such as `person at x=358, height=439 px, conf=0.46 | 1 object(s)`. The readings are in [logs/partB_run6_headless.log](logs/partB_run6_headless.log).

<mark>TODO (write this yourself; rubric: No AI assistance): pick three situations above where it did not see you or saw a person who was not there, and write the cause you think for each.</mark>



## Part C. 
### See more: hands and pose with MediaPipe

<details>
<summary>Instructions</summary>

YOLO tells you that a person is there. Google's [MediaPipe](https://mediapipe.dev/) tells you what their hands and body are doing: face, hand and body pose detection, fast on the Pi.

![Media pipe](Readme_files/mp.gif)

The demo plays a looping audio file, so make the helper script executable first:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ chmod +x loop_audio.sh
```

Connect your webcam, connect to your Pi through **VNC**, and run the hand pose script:
(***it will not work if you use ssh from your laptop***)

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python hand_pose.py
```

Try the two main features of this script: 1) pinching for percentage control (the thumb-to-index distance sets the volume), and 2) "[Quiet Coyote](https://www.youtube.com/watch?v=qsKlNVpY7zg)" for instant percentage setting (the gesture mutes it). Notice how this example uses hardcoded positions and relates those positions with a desired set of events, in `hand_pose.py`: a hand is 21 landmark coordinates, and an *event* is a rule you write over them. That is the same job as `interpret()` in Part E.

Consider how you might use this position based approach to create an interaction, and write how you might use it on either face, hand or body pose tracking.

</details>

\*\*\***Include a screenshot or short video of the hand pose demo, and write how you might use face, hand or body pose tracking in your observant system.**\*\*\*

| Pinch: 0 % | Pinch: 14 % | Quiet Coyote |
|---|---|---|
| ![pinch 0%](images/partC_pinch_0.webp) | ![pinch 14%](images/partC_pinch_14.webp) | ![quiet coyote](images/partC_quiet_coyote.webp) |

MediaPipe tracks the user's hand gestures and reads them as commands. When a deaf or mute user cannot speak, gestures become an efficient way to give instructions.

- **Before bed:** the user makes an OK 👌 gesture to tell the device "tonight is yours". Why a gesture instead of a button or voice: deaf or mute users may not be able to speak, and a button is inconvenient for giving commands from a distance. A gesture lets the user give a command while lying down, without getting close to the device.
- **While asleep:** what the system watches can be seen from the person's hands and posture.
- **When awake:** the user mutes the sound with a gesture, the Italian gesture of pinching all five fingertips together. The volume follows the earlier setting.
- **When it goes wrong (Bellotti's Accident):** if a gesture is misrecognized, the way photos on a phone were recognized as people in Part B, the user may be confused.


## Part D. 
### Reason: run Qwen on the Pi with Ollama

<details>
<summary>Instructions</summary>

Talk to the model in the terminal first. Qwen3 models "think" before they answer, which is slow on a Pi, so turn it off. Then ask about something you can check:

```
pi@raspberrypi:~ $ ollama run qwen3.5:0.8b
>>> /set nothink
>>> Tell me a bit about the history of Roosevelt Island. Three sentences.
>>> /bye
```

Roosevelt Island is a good first question because you know the ground truth: it was Blackwell's Island, then Welfare Island, got its current name in 1973, and Cornell Tech opened on it in 2017. Count how many of the model's facts are true.

From Python, qwen requests can be triggered by the `ask_qwen.py` script. It turns thinking off, tells the model to answer in at most three sentences, and cuts it off after 120 tokens (`--max-tokens` changes that), because a small model left alone writes an essay. Read the script, then run:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python ask_qwen.py "Tell me a bit about the history of Roosevelt Island."
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python ask_qwen.py --model qwen3:0.6b "Tell me a bit about the history of Roosevelt Island."
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python ask_qwen.py --image snap.jpg "What is in this photo?"
```

Things in the [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md) worth knowing:

* `think: false` skips the reasoning trace. Always, on a Pi. `ask_qwen.py` sends it on every request; `--think` turns the trace back on for one question, so you can see what you are skipping and how long it takes.
* `format` makes the model answer as JSON with the fields you name (`--json`). Handy when a display or a servo has to read the answer.
* `images` sends a photo along with the prompt (`--image snap.jpg`, the photo from Part A). `qwen3.5:0.8b` can look at pictures.

A 0.8B model is slow and sometimes wrong. It will invent events that are not in the data and agree with a wrong premise. Give it the data, keep its job narrow, and decide what the device does when the model is unsure.

</details>

\*\*\***Ask Qwen three questions to answer. Paste the questions, the answers and how long each took. Try one of them with `qwen3:0.6b` and compare.**\*\*\*

<details>
  Q&A here
  <mark>TODO (needs the Pi): paste three questions, Qwen's answers and how long each took; ask one of them again with `qwen3:0.6b` and compare. Write the questions and the comparison yourself (rubric: No AI assistance).</mark>
</details>


## Part E. 
### Connect: from YOLO readings to Qwen reasoning

<details>
<summary>Instructions</summary>

An observant system is a pipeline: a **detector** turns pixels into boxes, an **interpreter** turns boxes into readings in words ("one person, left, close"), the readings pile up in a **log**, and a **reasoner** answers a question about the log. The language model never sees pixels, only the words you chose in the interpreter. That makes the interpreter the most important design decision in the system.

`yolo_to_qwen.py` is the pipeline in one file, one function per stage. Read it before you run it:

* `interpret(r)` is the interpreter. It takes one YOLO result and returns one reading. A person is *left*, *center* or *right* by which third of the frame the middle of their box is in, and *close* if the box is taller than 60% of the frame, *far* otherwise. The reading is a string like `1 person(s) at center/close`, or `nobody`. Fifteen lines, and they decide everything the model can know.
* `watch(seconds)` is the detector and the log. Twice a second it reads a frame, runs YOLO on it and calls `interpret()`. A time-stamped reading goes into the log **only when it differs from the previous one**, so a minute of sitting still is one line, not 120.
* `ask(log, question)` is the reasoner. It pastes the log and your question into one prompt, tells Qwen to answer in at most three sentences using only what is in the log, and sends it to Ollama with thinking off.

Run it through VNC and a window opens with YOLO's boxes, the current reading and the seconds left. Press q to stop watching early. Over plain ssh add `--headless` and you get the same thing minus the window.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_to_qwen.py
```

It watches for a minute, saves the log to `watch_log.txt` and asks Qwen the default question. The terminal looks something like this:

```
14:02:11 nobody
14:02:19 1 person(s) at right/far
14:02:24 1 person(s) at center/close
14:02:51 nobody

4 lines saved to watch_log.txt
asking Qwen...

Qwen (18.4 s):
One person came in from the right, moved close to the camera, and left after about half a minute. ...
```

</details>

---

# Lab 5 Part 2: Overnight Sensation

<details>
<summary>Instructions</summary>

For Part 2, you will use the observant system from Part 1 to design a night-time interaction. On-device AI is slow, so let it work while you sleep. The person meets the device twice: **before bed**, when they hand the night over, and **when awake**, when the device gives something back. In between, the pipeline from Part E runs on its own.

Two flavors, pick one or mix them:

* **Sense all night.** The Pi watches, listens or measures from bedtime until morning and keeps a log.
* **Process all night.** You already have the data (a day of phone photos, a long recording) and the Pi needs hours to get through it.

Two house rules. Sample rather than stream: one look every 5 to 30 seconds is plenty, and it keeps the Pi cool. And keep everything on the Pi: tell the people you live with, point the camera at things rather than at beds, and delete the snapshots after the demo.

</details>

## Part F. 
### Read Part 2 and storyboard your night-time interaction

<details>
<summary>Instructions</summary>

Storyboard a night-time interaction built on your observant system, in three panels:

1. **Before bed.** How does the person hand the night over, and how does the device acknowledge it?
2. **While asleep.** What does the device watch or work through?
3. **When awake.** What is the one thing the person learns, and in what medium?

Stuck? A kitchen that tells you who raided the fridge. A desk that reports whether you actually went to bed. A window that names the quietest hour. A plant that describes its night. Find something better.

Use storyboards and/or [Verplank diagrams](https://ccrma.stanford.edu/courses/250a-fall-2004/IDSketchbok.pdf).

</details>

\*\*\***Insert ideas, sketches, Verplank diagrams and storyboards for your night-time interaction here.**\*\*\*

<mark>TODO Ideas:</mark>

<mark>TODO Storyboard panel 1 (before bed): how does the person hand the night over, and how does the device acknowledge it?</mark>

<mark>TODO Storyboard panel 2 (while asleep): what does the device watch or work through?</mark>

<mark>TODO Storyboard panel 3 (when awake): what is the one thing the person learns, and in what medium?</mark>

<mark>TODO Verplank diagram (optional):</mark>

## Prep for Part 2

<details>
<summary>Instructions</summary>

1. Look at and give feedback on the Part F storyboards.

</details>

   **Put the feedback for your ideas here.**

   <mark>TODO: feedback from classmates.</mark>

<details>
<summary>Instructions</summary>

2. [Update your Lab Hub](prep.md#get-the-latest-content) to get the latest content for Part 2.
3. Decide where the device will spend the night and who else lives there. Get their OK before the first run.
4. Revise your storyboard with the feedback and with what you learned in Part E about where the pipeline breaks.

</details>

\*\*\***Post your revised storyboard here.**\*\*\*

<mark>TODO (Part 2): revised storyboard.</mark>

## Part G. 
### Design the interaction before

<details>
<summary>Instructions</summary>

The hand-off: the person tells the device what to watch tonight, and the device acknowledges it. Keep it to a thirty-second ritual. A button or a touch (Lab 4), a spoken sentence (Lab 3), a wave or a Quiet Coyote at the camera (Part C). The acknowledgement can be a line on the display, a tone, or an LED that dims rather than lights up. At its simplest, the hand-off just sets the question that the morning will answer.

</details>

\*\*\***Describe the interaction before.**\*\*\*

<mark>TODO (Part 2): description of the bedtime hand-off.</mark>

## Part H. 
### Incorporate the observant system

<details>
<summary>Instructions</summary>

The Part E pipeline becomes the night shift. `overnight.py` runs your `interpret()` from `yolo_to_qwen.py` every few seconds, people only unless you pass `--all`, and writes the readings to `night_log.jsonl`; the reasoning waits for the morning. Start it inside `tmux` so it keeps running after you close your laptop, and stop it with Ctrl-C in the morning:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ tmux new -s night
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python overnight.py
```

Fake a night first: run it for thirty seconds while you walk around, stop it, and run `morning.py` from Part I. When that looks right, run a real night. If your storyboard needs a sensor rather than the camera, swap in the Lab 4 example code and log its reading the same way.

</details>

\*\*\***Screenshots or videos of the running system.**\*\*\*

<mark>TODO (Part 2): screenshots or videos of the running system.</mark>

## Part I. 
### Design the interaction after

<details>
<summary>Instructions</summary>

The reveal. The night produced a log; the morning turns it into something a half-awake person can take in. `morning.py` is the smallest version: it asks Qwen for a three-sentence report.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python morning.py
```

Make it yours: show the report on the Mini PiTFT, read it aloud with Piper from Lab 3, plot the night as a timeline, or ask for JSON (`--json`, Part D) and move a servo. Whatever you pick, make sure it is honest about a night in which nothing happened.

</details>

## Final documentation

<details>
<summary>Instructions</summary>

Document all the prototypes and iterations you have designed and worked on. The deliverables for this lab are writings, sketches, photos, and videos that show what your system:

* "Looks like": how the device sits in the room at night, and what it looks like at bedtime and in the morning.
* "Works like": the pipeline from detector to interpreter to log to reasoner, with a real night's data.
* "Acts like": how a person hands the night over and what they get back.

</details>

\*\*\***Include a short video of the whole system**\*\*\*

<mark>TODO (Part 2): short video of the whole system.</mark>

<details>
<summary>Instructions</summary>

As always, make sure you document contributions and ideas from others (and AI) explicitly in your writeup.

You are permitted (but not required) to work in groups and share a turn in; you are expected to make equal contribution on any group work you do, and N people's group project should look like N times the work of a single person's lab. Make sure the page for the group turn in is linked to your personal Interactive Lab Hub page.

</details>

## Deliverables & Submission for Lab 5

<details>
<summary>Instructions</summary>

For submission, the readme.md page for this lab should be edited to include the work you have done:
* Upload any materials that explain what you did, including your code and night log, into your Lab 5 repository, and link them in your Lab 5 readme.md.
* Labs are due on Sundays, make sure to submit your Lab 5 readme.md to Canvas.

</details>

<details>
  <summary><strong>Submission Cleanup Reminder (Click to Expand)</strong></summary>

  **Before submitting your README.md:**
  - This readme.md file has a lot of extra text for guidance.
  - Remove all instructional text and example prompts from this file.
  - You may either delete these sections or use the toggle/hide feature in VS Code to collapse them for a cleaner look.
  - Your final submission should be neat, focused on your own work, and easy to read for grading.
</details>
