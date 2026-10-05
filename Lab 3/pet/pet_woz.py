"""Wizard-of-Oz pixel pet clock for Lab 3 Part 2.

The Pi shows the pet, reacts to the hand sensor, and speaks. A hidden wizard
chooses what it says from a browser controller. Participant speech is
transcribed on the Pi so the wizard can read it, and every turn is logged to
results/woz/<time>/events.jsonl as an interaction dataset.

  Pi (from Lab 3/):  .venv/bin/python pet/pet_woz.py [--demo]
  Mac preview:       python3 pet/pet_woz.py --preview
  Controller:        http://<pi-hostname>.local:5000  (preview: http://localhost:5050)

Buttons: B shows the next page (during focus: studying together <-> tree). A goes back to the pet;
on the pet it starts focusing. Hold A for 2 s to stop a session.
A hand near the sensor is a head pat. The sun and moon follow the real local time.
"""
import argparse
from collections import deque
from datetime import datetime, timedelta
import io
import json
import logging
import os
from pathlib import Path
import queue
import random
import socket
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
LAB3 = HERE.parent
STATE = LAB3 / 'results' / 'pet-state'
MOODS = ('eat', 'study', 'bored', 'pacing', 'stomp', 'sick', 'sleep', 'happy')
PAGES = ('home', 'tree', 'todo', 'clock', 'status')  # B cycles these; 'game' is wizard-only
MAX_TASKS = 4
RATE = 16000  # Whisper and the VAD work at 16 kHz, as in the course listen.py


class Pet:
    def __init__(self, args):
        self.args = args
        self.lock = threading.RLock()
        STATE.mkdir(parents=True, exist_ok=True)
        self.session = LAB3 / 'results' / 'woz' / datetime.now().strftime('%Y%m%d-%H%M%S')
        self.session.mkdir(parents=True)
        self.log_file = (self.session / 'events.jsonl').open('a')
        self.feed, self.seq = deque(maxlen=80), 0
        self.tasks_path = STATE / 'tasks.json'
        today = self.now().date().isoformat()
        tasks = json.loads(self.tasks_path.read_text()) if self.tasks_path.exists() else []
        self.tasks = [task for task in tasks if task['day'] == today or not task['done']]
        suffix = '_demo' if args.demo else ''
        self.progress = garden.Progress(STATE / f'tree_progress{suffix}.json')
        self.timer = garden.Timer(self.progress, 60 if args.demo else 25 * 60, today)
        self.bored_after = 45 if args.demo else 300
        self.page, self.page_at = 'home', 0.0
        self.override = None
        self.reaction, self.reaction_until = None, 0.0
        self.indicator, self.indicator_until = None, 0.0
        self.talking, self.talk_end = False, 0.0
        self.active_at = time.monotonic()
        self.pats = 0
        self.hint, self.hint_until = None, 0.0  # short on-screen tip, e.g. HOLD A TO STOP
        self.game = {'number': None, 'shown': False, 'result': None}
        self.hw = {'mic': 'off', 'hand': 'off', 'speaker': 'preview' if args.preview else 'on'}
        self.frame = None
        self.voice = None
        self.started = time.monotonic()
        self.log('start', preview=args.preview, demo=args.demo)

    @staticmethod
    def now():
        return datetime.now(garden.LOCAL_TZ)

    def sky_hour(self, now, t):
        hour = now.hour + now.minute / 60 + now.second / 3600
        return (hour + (t - self.started) * (self.args.sky_speed - 1) / 3600) % 24

    def log(self, kind, **data):
        with self.lock:
            self.seq += 1
            entry = {'id': self.seq, 'time': self.now().isoformat(timespec='seconds'), 'kind': kind, **data}
            self.log_file.write(json.dumps(entry) + '\n')
            self.log_file.flush()
            self.feed.append(entry)

    # --- tasks -----------------------------------------------------------
    def due(self, task):
        clock = datetime.strptime(task['due'], '%H:%M').time()
        return datetime.combine(datetime.fromisoformat(task['day']).date(), clock, garden.LOCAL_TZ)

    def status(self, task, now):
        if task['done']:
            return 'done'
        left = self.due(task) - now
        return 'overdue' if left <= timedelta(0) else 'soon' if left <= timedelta(minutes=30) else 'ok'

    def task_rows(self, now):
        return [(task, self.status(task, now)) for task in sorted(self.tasks, key=self.due)]

    def save_tasks(self):
        self.tasks_path.write_text(json.dumps(self.tasks, indent=2) + '\n')

    def find(self, task_id):
        for task in self.tasks:
            if task['id'] == task_id:
                return task
        raise ValueError('Task not found.')

    # --- state -----------------------------------------------------------
    def react(self, mood, seconds):
        self.reaction, self.reaction_until = mood, time.monotonic() + seconds

    def set_indicator(self, kind, seconds=0.0):
        self.indicator, self.indicator_until = kind, time.monotonic() + seconds

    def mood(self, t, now):
        if self.reaction and t < self.reaction_until:
            return self.reaction
        if self.override:
            return self.override
        if self.timer.state == 'running':
            return 'study'  # stays quiet and studies with you; reminders wait
        statuses = [status for _, status in self.task_rows(now)]
        if statuses.count('overdue') >= 2:
            return 'sick'
        if 'overdue' in statuses:
            return 'stomp'
        if 'soon' in statuses:
            return 'pacing'
        return 'bored' if t - self.active_at > self.bored_after else 'eat'

    def pat(self, simulated=False):
        with self.lock:
            self.pats += 1
            self.active_at = time.monotonic()
            self.react('happy', 2.5)
            self.set_indicator('listening', 8)
            self.log('pat', simulated=simulated)

    def utterance_end(self):
        with self.lock:
            self.set_indicator('thinking', 15)

    def heard(self, text, **info):
        with self.lock:
            self.active_at = time.monotonic()
            self.set_indicator('thinking', 15)
            self.log('user', text=text, **info)

    def set_talking(self, talking):
        with self.lock:
            self.talking = talking
            if not talking:
                self.talk_end = time.monotonic()
                self.set_indicator('listening', 8)  # wait up to 8 s for a reply

    def press_a(self):
        """Short press: on another page, go back to the pet; on the pet, start focusing.

        A short press never stops a session; that needs a 2 s hold (hold_a).
        """
        with self.lock:
            t = time.monotonic()
            if self.page != 'home':
                self.page, self.page_at = 'home', t
            elif self.timer.state == 'running':
                self.hint, self.hint_until = 'HOLD A TO STOP', t + 2
            else:
                self.do('focus_start', {})

    def hold_a(self):
        """Holding A for 2 seconds stops a running session."""
        with self.lock:
            if self.timer.state == 'running':
                self.do('focus_stop', {})
                self.hint, self.hint_until = 'STOPPED', time.monotonic() + 2

    def next_page(self):
        with self.lock:
            if self.timer.state == 'running':
                self.page, self.page_at = ('tree' if self.page == 'home' else 'home'), time.monotonic()
                return
            index = PAGES.index(self.page) if self.page in PAGES else 0
            self.page, self.page_at = PAGES[(index + 1) % len(PAGES)], time.monotonic()

    def update(self, t):
        with self.lock:
            now = self.now()
            if self.timer.tick(t, now.date().isoformat()) == 'stop':
                self.react('happy', 4)
                self.log('focus_done', total=self.progress.total)
            if self.indicator and t > self.indicator_until:
                self.indicator = None
            focus_page = self.page == 'tree' and self.timer.state == 'running'
            if self.page not in ('home', 'game') and not focus_page and t - self.page_at > 30:
                self.page = 'home'

    def render(self, t):
        with self.lock:
            now = self.now()
            clock = now.strftime('%H:%M')
            rows = self.task_rows(now)
            timer = self.timer
            if self.page == 'tree':
                since_done = t - timer.completed_at if timer.completed_at is not None else 10.0
                frame = garden.garden_frame(timer, t - timer.started_at, False, since_done)
            elif self.page == 'clock':
                frame = garden.clock_frame(timer, now)
            elif self.page == 'todo':
                frame = pet_art.todo_frame(rows, clock)
            elif self.page == 'status':
                frame = pet_art.status_frame(self.stats(now, rows))
            elif self.page == 'game':
                frame = pet_art.game_frame(self.game, clock, t)
            else:
                frame = pet_art.home_frame({
                    'mood': self.mood(t, now), 'indicator': self.indicator, 'talking': self.talking,
                    'clock': clock, 'focus': timer.countdown if timer.state == 'running' else None,
                    'poops': min(4, sum(status == 'overdue' for _, status in rows)),
                    'tree_stage': timer.stage, 'hour': self.sky_hour(now, t),
                    'hint': self.hint if t < self.hint_until else None,
                }, t)
            self.frame = frame
            return frame

    def stats(self, now, rows):
        done = sum(status == 'done' for _, status in rows)
        overdue = sum(status == 'overdue' for _, status in rows)
        focus_today = self.progress.count(now.date().isoformat())
        hearts = max(0, min(4, 2 + focus_today + self.pats // 5 - 2 * overdue))
        return {'clock': now.strftime('%H:%M'), 'hearts': hearts, 'focus_today': focus_today,
                'done': done, 'total': len(rows), 'pats': self.pats, 'trees': self.timer.tree_count}

    def snapshot(self):
        with self.lock:
            t, now = time.monotonic(), self.now()
            return {
                'mood': self.mood(t, now), 'override': self.override or 'auto', 'page': self.page,
                'indicator': 'speaking' if self.talking else self.indicator,
                'focus': {'state': self.timer.state, 'countdown': self.timer.countdown},
                'tasks': [dict(task, status=status) for task, status in self.task_rows(now)],
                'game': self.game, 'hw': self.hw, 'feed': list(self.feed)[-40:],
            }

    # --- wizard actions --------------------------------------------------
    def do(self, action, data):
        with self.lock:
            t, now = time.monotonic(), self.now()
            value = data.get('value')
            if action == 'say':
                line = str(data.get('text', '')).strip()
                if not line:
                    raise ValueError('Nothing to say.')
                self.voice.say(line)
                self.log('pet', text=line)
            elif action == 'mood':
                if value == 'happy':
                    self.react('happy', 3)
                elif value == 'auto' or value in MOODS:
                    self.override = None if value == 'auto' else value
                    self.reaction = None
                else:
                    raise ValueError(f'Unknown mood: {value}')
                self.log('mood', value=value)
            elif action == 'page':
                if value not in PAGES + ('game',):
                    raise ValueError(f'Unknown page: {value}')
                self.page, self.page_at = value, t
                self.log('page', value=value)
            elif action == 'indicator':
                seconds = {'listening': 8, 'thinking': 15}.get(value)
                self.set_indicator(value if seconds else None, seconds or 0)
            elif action == 'pat':
                self.pat(simulated=True)
            elif action in ('heard', 'note'):
                line = str(data.get('text', '')).strip()
                if line and action == 'heard':
                    self.heard(line, typed=True)
                elif line:
                    self.log('note', text=line)
            elif action == 'focus_start':
                if self.timer.state != 'ready':
                    self.timer.press_a(t, now.date().isoformat())  # done -> ready
                self.timer.press_a(t, now.date().isoformat())
                self.log('focus_start', seconds=self.timer.duration)
            elif action == 'focus_stop':
                if self.timer.state == 'running':
                    self.timer.press_a(t, now.date().isoformat())
                    self.log('focus_stop')
            elif action == 'focus_finish':
                if self.timer.state == 'running':
                    self.timer.started_at = t - self.timer.duration  # completes on the next tick
            elif action == 'task_add':
                title = str(data.get('title', '')).strip()[:40]
                try:
                    due = datetime.strptime(str(data.get('due', '')), '%H:%M').strftime('%H:%M')
                except ValueError:
                    raise ValueError('Due time must look like 16:00.') from None
                if not title:
                    raise ValueError('Task needs a title.')
                if sum(not task['done'] for task in self.tasks) >= MAX_TASKS:
                    raise ValueError("Today's list is full (4 tasks).")
                day = now.date()
                if datetime.combine(day, datetime.strptime(due, '%H:%M').time(), now.tzinfo) < now - timedelta(hours=1):
                    day += timedelta(days=1)  # "due at 1 AM" said at 11 PM means tomorrow
                task = {'id': int(time.time() * 1000), 'title': title, 'due': due,
                        'day': day.isoformat(), 'done': False}
                self.tasks.append(task)
                self.save_tasks()
                self.log('task_add', title=title, due=due)
            elif action in ('task_done', 'task_later', 'task_delete'):
                task = self.find(data.get('id'))
                if action == 'task_done':
                    task['done'] = True
                    self.react('happy', 3)
                elif action == 'task_later':
                    moved = max(self.due(task), now) + timedelta(minutes=10)
                    task['day'], task['due'] = moved.date().isoformat(), moved.strftime('%H:%M')
                else:
                    self.tasks.remove(task)
                self.save_tasks()
                self.log(action, title=task['title'], due=task['due'])
            elif action == 'game_new':
                self.game = {'number': random.randint(1, 5), 'shown': False, 'result': None}
                self.page, self.page_at = 'game', t
                self.log('game_new', number=self.game['number'])
            elif action == 'game_show':
                self.game['shown'] = True
            elif action == 'game_result':
                if value not in ('win', 'lose'):
                    raise ValueError('Result must be win or lose.')
                self.game.update(result=value, shown=True)
                self.log('game_result', value=value)
            else:
                raise ValueError(f'Unknown action: {action}')


class Voice:
    """Speaks one line at a time with Piper through the default speaker."""

    def __init__(self, pet, args):
        self.pet, self.lines, self.piper = pet, queue.Queue(), None
        if not args.preview:
            if not args.voice.is_file():
                sys.exit(f'Piper voice missing: {args.voice}. Run: bash install.sh')
            from piper import PiperVoice
            self.piper = PiperVoice.load(str(args.voice))
        threading.Thread(target=self.work, daemon=True).start()

    def say(self, line):
        self.lines.put(line)

    def work(self):
        while True:
            line = self.lines.get()
            self.pet.set_talking(True)
            try:
                if self.piper is None:
                    print(f'[pet says] {line}', flush=True)
                    time.sleep(0.4 + 0.06 * len(line))  # preview: animate the mouth only
                else:
                    self.speak(line)
            except Exception as error:  # keep the session running if one line fails
                self.pet.log('error', text=f'speech failed: {error}')
            finally:
                self.pet.set_talking(False)

    def speak(self, line):
        # As in the course echo_bot.py: play Piper's audio on the default output device.
        import numpy as np
        import sounddevice as sd
        for chunk in self.piper.synthesize(line):
            sd.play(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16), samplerate=chunk.sample_rate)
            sd.wait()


def listen(pet, args):
    """VAD + Whisper from Part 1C; the microphone is ignored while the pet talks."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    from faster_whisper import WhisperModel
    sys.path.insert(0, str(LAB3 / 'speech-scripts'))
    from listen import build_vad

    vad_path = LAB3 / 'models' / 'silero_vad.onnx'
    if not vad_path.is_file():
        raise RuntimeError('VAD model missing. Run: bash install.sh')
    model = WhisperModel(args.model, device='cpu', compute_type='int8', local_files_only=True)
    vad, window = build_vad(vad_path, args.silence, 0.25)
    pending = queue.Queue()

    def transcribe():
        count = 0
        while True:
            audio = pending.get()
            began = time.perf_counter()
            segments, _ = model.transcribe(audio, beam_size=1)
            line = ' '.join(segment.text.strip() for segment in segments).strip()
            info = {'speech_s': round(len(audio) / RATE, 2),
                    'asr_s': round(time.perf_counter() - began, 2)}
            if args.save_audio:
                count += 1
                info['audio'] = f'utterance-{count:03}.wav'
                sf.write(str(pet.session / info['audio']), audio, RATE)
            if line:
                pet.heard(line, **info)

    threading.Thread(target=transcribe, daemon=True).start()
    buffer = np.empty(0, dtype=np.float32)
    muted = False
    with sd.InputStream(channels=1, dtype='float32', samplerate=RATE) as stream:
        pet.hw['mic'] = 'on'
        while True:
            chunk, _ = stream.read(int(0.1 * RATE))
            if pet.talking or time.monotonic() - pet.talk_end < 0.4:
                if not muted:  # drop anything half-heard so the pet never transcribes itself
                    buffer = buffer[:0]
                    if hasattr(vad, 'reset'):
                        vad.reset()
                    while not vad.empty():
                        vad.pop()
                    muted = True
                continue
            muted = False
            buffer = np.concatenate((buffer, chunk[:, 0]))
            while len(buffer) >= window:
                vad.accept_waveform(buffer[:window])
                buffer = buffer[window:]
            while not vad.empty():
                audio = np.array(vad.front.samples, dtype=np.float32)
                vad.pop()
                pet.utterance_end()
                pending.put(audio)


def listen_safely(pet, args):
    try:
        listen(pet, args)
    except Exception as error:
        pet.hw['mic'] = f'failed: {error}'
        pet.log('error', text=f'microphone stopped: {error}')


def make_app(pet):
    from flask import Flask, jsonify, request, send_file
    from PIL import Image

    app = Flask(__name__)

    @app.get('/')
    def controller():
        return send_file(HERE / 'controller.html', max_age=0)

    @app.get('/api/state')
    def state():
        return jsonify(pet.snapshot())

    @app.post('/api/do')
    def act():
        data = request.get_json(silent=True) or {}
        try:
            pet.do(data.get('action', ''), data)
        except ValueError as error:
            return jsonify(ok=False, error=str(error)), 400
        return jsonify(ok=True)

    @app.get('/screen.png')
    def screen():
        with pet.lock:
            frame = pet.frame or Image.new('RGB', (240, 135))
        output = io.BytesIO()
        frame.save(output, 'PNG')
        output.seek(0)
        return send_file(output, mimetype='image/png', max_age=0)

    return app


def run_screen(pet, args):
    if args.preview:
        while True:
            t = time.monotonic()
            pet.update(t)
            pet.render(t)
            time.sleep(0.1)

    import board
    import digitalio
    import adafruit_rgb_display.st7789 as st7789
    from PIL import Image

    sensor = gate = None
    if not args.no_hand:
        try:
            sensor, gate = garden.load_hand_control(args.lab2 / 'hand_calibration.json')
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            print(f'Hand sensor unavailable: {error}')
    pet.hw['hand'] = 'on' if gate else 'off (see terminal)'
    display = st7789.ST7789(board.SPI(), cs=digitalio.DigitalInOut(board.D5),
                            dc=digitalio.DigitalInOut(board.D25), rst=None, baudrate=64000000,
                            width=135, height=240, x_offset=53, y_offset=40)
    backlight = digitalio.DigitalInOut(board.D22)
    backlight.switch_to_output(value=True)
    a, b = digitalio.DigitalInOut(board.D23), digitalio.DigitalInOut(board.D24)
    for button in (a, b):
        button.switch_to_input(pull=digitalio.Pull.UP)
    a_down, a_held = None, False  # when A went down; whether the 2 s hold already fired
    previous_b, last_b, last_frame = False, -1.0, 0.0
    try:
        while True:
            t = time.monotonic()
            a_pressed, b_pressed = not a.value, not b.value
            if gate is not None:
                try:
                    if gate.update(sensor.proximity, t):
                        pet.pat()
                except (OSError, RuntimeError) as error:
                    print(f'Hand sensor read failed: {error}. Buttons still work.')
                    gate, pet.hw['hand'] = None, 'failed'
            # A acts on release (short press), or after a 2 s hold while focusing.
            if a_pressed and a_down is None:
                a_down, a_held = t, False
            elif a_pressed and not a_held and t - a_down >= 2.0 and pet.timer.state == 'running':
                pet.hold_a()
                a_held = True
            elif not a_pressed and a_down is not None:
                if not a_held:
                    pet.press_a()
                a_down = None
            if b_pressed and not previous_b and t - last_b >= 0.2:
                pet.next_page()
                last_b = t
            previous_b = b_pressed
            pet.update(t)
            if t - last_frame >= 0.1:  # 10 fps leaves CPU for speech recognition; buttons still poll at 20 Hz
                display.image(pet.render(t), 90)
                last_frame = t
            time.sleep(0.05)
    finally:
        display.image(Image.new('RGB', (240, 135)), 90)
        backlight.value = False
        if sensor is not None:
            try:
                sensor.enable_proximity = False
            except (OSError, RuntimeError):
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--preview', action='store_true', help='no Pi hardware; watch the screen in the controller')
    parser.add_argument('--demo', action='store_true', help='60-second focus and faster boredom, for user tests')
    parser.add_argument('--lab2', type=Path, default=LAB3.parent / 'Lab 2', help='folder with tree_focus_timer.py')
    parser.add_argument('--no-mic', action='store_true', help='no transcription; the wizard just listens')
    parser.add_argument('--no-hand', action='store_true', help='buttons only')
    parser.add_argument('--save-audio', action='store_true', help='keep each utterance as WAV (ask participants first)')
    parser.add_argument('--silence', type=float, default=0.8, help='seconds of silence that end a turn')
    parser.add_argument('--model', default='tiny.en', help='Whisper model (must already be cached)')
    parser.add_argument('--voice', type=Path, default=LAB3 / 'voices' / 'en_US-lessac-medium.onnx')
    parser.add_argument('--color', default='butter', choices=['mint', 'butter', 'lilac'], help='pet color')
    parser.add_argument('--sky-speed', type=float, default=1, help='e.g. 720 = one day in 2 minutes, for demo videos')
    parser.add_argument('--port', type=int, help='default 5000 on the Pi, 5050 in preview (macOS uses 5000)')
    args = parser.parse_args()
    args.port = args.port or (5050 if args.preview else 5000)
    if not (args.lab2 / 'tree_focus_timer.py').is_file():
        sys.exit(f'Cannot find Lab 2 tree_focus_timer.py in {args.lab2}. Use --lab2 PATH.')

    global garden, pet_art
    sys.path.insert(0, str(args.lab2))
    import tree_focus_timer as garden
    import pet_art
    pet_art.set_color(args.color)

    pet = Pet(args)
    pet.voice = Voice(pet, args)
    pet.render(time.monotonic())
    if not (args.preview or args.no_mic):
        threading.Thread(target=listen_safely, args=(pet, args), daemon=True).start()
    logging.getLogger('werkzeug').setLevel(logging.ERROR)  # hide per-request polling logs
    host = '127.0.0.1' if args.preview else '0.0.0.0'
    threading.Thread(target=make_app(pet).run, daemon=True,
                     kwargs={'host': host, 'port': args.port, 'threaded': True}).start()
    name = 'localhost' if args.preview else f'{socket.gethostname()}.local'
    print(f'Controller: http://{name}:{args.port}   Log: {pet.session}', flush=True)
    try:
        run_screen(pet, args)
    except KeyboardInterrupt:
        print(f'\nStopped. Session log: {pet.session / "events.jsonl"}', flush=True)
    # Exit now: letting the audio and speech threads tear down at interpreter exit can segfault.
    os._exit(0)


if __name__ == '__main__':
    main()
