"""Pixel art for the pet clock: an original egg-shaped pet in a Tamagotchi style.

Everything is drawn on the same 120x67 canvas as the Lab 2 garden and scaled 2x
for the 240x135 Mini PiTFT. The tree and clock pages reuse tree_focus_timer.py.
"""
import math

from PIL import Image, ImageDraw, ImageFont, ImageOps

import tree_focus_timer as garden

PAL = {
    'K': (40, 28, 36), 'W': (255, 255, 255), 'R': (205, 60, 80), 'N': (38, 64, 48),
    'P': (139, 94, 60), 'p': (176, 128, 84), 'T': (206, 160, 110), 'Y': (240, 90, 90),
    'D': (120, 190, 240), 'G': (95, 100, 110),
}
PET_COLORS = {  # outline, body, highlight, shade, cheeks, feet
    'mint': [(38, 74, 64), (163, 219, 190), (214, 243, 226), (112, 176, 148), (250, 150, 140), (238, 186, 104)],
    'butter': [(92, 62, 36), (255, 220, 124), (255, 243, 200), (226, 176, 84), (248, 136, 104), (226, 140, 84)],
    'lilac': [(64, 46, 96), (190, 176, 242), (230, 222, 255), (146, 130, 208), (246, 150, 186), (250, 200, 120)],
}
SICK = {}


def mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def set_color(name):
    outline, body, light, shade, cheeks, feet = PET_COLORS[name]
    PAL.update(O=outline, B=body, L=light, S=shade, C=cheeks, F=feet)
    pale = (186, 190, 176)
    SICK.clear()
    SICK.update(PAL, B=mix(body, pale, .7), L=mix(light, pale, .7), S=mix(shade, pale, .7), C=mix(body, pale, .7))


set_color('butter')
EMPTY_HEART = dict(PAL, R=(70, 76, 84))
GLASSES = (176, 124, 60)

BODY = [
    "................",
    "..OO........OO..",
    ".OBBO......OBBO.",
    ".OBBBOOOOOOBBBO.",
    "OBLLBBBBBBBBBBBO",
    "OBLBBBBBBBBBBBBO",
    "OBBBBBBBBBBBBBBO",
    "OBBBBBBBBBBBBBBO",
    "OBBBBBBBBBBBBBBO",
    "OBBBBBBBBBBBBBBO",
    "OBBBBBBBBBBBBBSO",
    ".OBBBBBBBBBBBSO.",
    "..OSSBBBBBBSSO..",
    "...OOOOOOOOOO...",
    "...OFFO..OFFO...",
    "...OOOO..OOOO...",
]
EYES = {
    'open': ["WK", "KK"], 'blink': ["..", "KK"], 'up': ["KK", ".."], 'side': [".K", ".K"],
    'happy': [".K.", "K.K"], 'angry': ["K..", ".KK"], 'dizzy': ["K.K", ".K.", "K.K"],
}
MIRRORED = {'angry'}  # drawn mirrored for the right eye
MOUTHS = {
    'smile': ["K..K", ".KK."], 'flat': [".KK."], 'frown': [".KK.", "K..K"],
    'open': [".KK.", "KRRK", ".KK."], 'o': [".K.", "K.K", ".K."], 'wavy': ["K.K.", ".K.K"],
}
ONIGIRI = ["...W...", "..WWW..", ".WWWWW.", "WWWWWWW", "WWNNNWW", "WWNNNWW"]
CUP = ["...Y.", "..Y..", "KKKKK", "KTTTK", "KTTTK", ".KKK."]
POOP = ["..P..", ".PPP.", "PPpPP", "PPPPP"]
HEART = [".R.R.", "RRRRR", ".RRR.", "..R.."]
SWEAT = [".D", "DD", "DD"]
NIGHT, DAY = (24, 28, 62), (170, 214, 240)
SKY = [(0, NIGHT), (5, NIGHT), (6.5, (250, 186, 150)), (8, DAY), (17, DAY), (18.5, (246, 160, 122)),
       (20, NIGHT), (24, NIGHT)]
FLOOR_DAY, FLOOR_NIGHT = (236, 212, 168), (66, 62, 82)
STARS = [(8, 14), (19, 30), (36, 14), (47, 22), (66, 12), (83, 28), (97, 9), (112, 20), (40, 38), (104, 38)]
BADGES = {'listening': ('LISTENING', (46, 150, 90)), 'thinking': ('THINKING', (205, 140, 30)),
          'speaking': ('SPEAKING', (215, 85, 125))}
DIGITS = {  # the hand-drawn 5x7 digits from Lab 2, unambiguous on the small LCD
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    ":": ["0", "1", "0", "0", "1", "0", "0"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
}
BIG_FONT = ImageFont.load_default(size=17)


def stamp(img, rows, x, y, pal=PAL, mirror=False):
    px = img.load()
    for dy, row in enumerate(rows):
        for dx, c in enumerate(row[::-1] if mirror else row):
            if c != '.' and 0 <= x + dx < img.width and 0 <= y + dy < img.height:
                px[x + dx, y + dy] = pal[c]


def art(rows, scale=2, pal=PAL):
    img = Image.new('RGBA', (len(rows[0]), len(rows)))
    stamp(img, rows, 0, 0, pal)
    return img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)


def put(scene, rows, x, y, scale=2, pal=PAL):
    img = art(rows, scale, pal)
    scene.paste(img, (round(x), round(y)), img)


def pet(eyes='open', mouth='smile', sick=False, glasses=False, flip=False, scale=2):
    pal = SICK if sick else PAL
    img = Image.new('RGBA', (16, 16))
    stamp(img, BODY, 0, 0, pal)
    stamp(img, ["CC"], 2, 8, pal)
    stamp(img, ["CC"], 12, 8, pal)
    e = EYES[eyes]
    stamp(img, e, 6 - len(e[0]), 8 - len(e), pal)
    stamp(img, e, 10, 8 - len(e), pal, mirror=eyes in MIRRORED)
    m = MOUTHS[mouth]
    stamp(img, m, 8 - len(m[0]) // 2, 9, pal)
    if glasses:
        d = ImageDraw.Draw(img)
        for x0 in (3, 9):
            d.rectangle((x0, 5, x0 + 3, 8), outline=GLASSES)
        d.line((7, 6, 8, 6), fill=GLASSES)
    if flip:
        img = ImageOps.mirror(img)
    return img.resize((16 * scale, 16 * scale), Image.Resampling.NEAREST)


def runs(message):
    """Split into digit/colon runs and letter runs; digits use Lab 2's 5x7 glyphs."""
    out = []
    for c in message:
        kind = c in DIGITS
        if out and out[-1][0] == kind:
            out[-1][1] += c
        else:
            out.append([kind, c])
    return out


def text_width(message):
    measure = ImageDraw.Draw(Image.new('L', (1, 1)))
    return sum(sum(len(DIGITS[c][0]) + 1 for c in run) if digits else round(measure.textlength(run, font=garden.FONT))
               for digits, run in runs(message))


def text(scene, xy, message, color):
    x, y = xy
    draw = ImageDraw.Draw(scene)
    for digits, run in runs(message):
        if not digits:
            garden.pixel_text(scene, (x, y), run, color)
            x += text_width(run)
            continue
        for c in run:
            for dy, row in enumerate(DIGITS[c]):
                for dx, bit in enumerate(row):
                    if bit == '1':
                        draw.point((x + dx, y + dy + 1), fill=color)
            x += len(DIGITS[c][0]) + 1


def text_right(scene, right, y, message, color):
    text(scene, (right - text_width(message), y), message, color)


def badge(scene, kind):
    label, color = BADGES[kind]
    width = text_width(label)
    ImageDraw.Draw(scene).rectangle((115 - width, 1, 119, 10), fill=color)
    text(scene, (117 - width, 1), label, (255, 255, 255))


def sky(hour):
    """Sky color and daylight (0 night .. 1 day) for an hour in 0..24."""
    for (h0, c0), (h1, c1) in zip(SKY, SKY[1:]):
        if h0 <= hour <= h1:
            color = mix(c0, c1, (hour - h0) / (h1 - h0))
            break
    light = sum(color) - sum(NIGHT)
    return color, max(0.0, min(1.0, light / (sum(DAY) - sum(NIGHT))))


def sun_and_moon(scene, hour, color):
    """Both travel one big circle centered below the screen: rise left, set right."""
    d = ImageDraw.Draw(scene)
    for start in (6, 18):  # the sun is up 6:00-18:00, the moon 18:00-6:00
        progress = ((hour - start) % 24) / 12
        if progress > 1:
            continue
        angle = math.pi * (1 - progress)
        x, y = 60 + 68 * math.cos(angle), 78 - 68 * math.sin(angle)
        if start == 6:
            for dx, dy in ((0, -9), (0, 9), (-9, 0), (9, 0), (-6, -6), (6, -6), (-6, 6), (6, 6)):
                d.point((x + dx, y + dy), fill=(255, 214, 110))
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 196, 64))
            d.ellipse((x - 4, y - 5, x - 1, y - 2), fill=(255, 226, 140))
        else:
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(244, 238, 206))
            d.ellipse((x - 2, y - 7, x + 7, y + 2), fill=color)  # crescent


def desk(scene, t):
    """Desk with a lamp, pencils and an open book; three-frame loop: read, write, turn page."""
    d = ImageDraw.Draw(scene)
    frame = int(t * 1.5) % 3
    d.rectangle((37, 46, 88, 47), fill=(196, 146, 92))
    d.line((38, 48, 87, 48), fill=(150, 104, 62))
    d.rectangle((39, 49, 40, 56), fill=(150, 104, 62))
    d.rectangle((85, 49, 86, 56), fill=(150, 104, 62))
    d.rectangle((40, 41, 43, 45), fill=(110, 150, 196))  # pencil cup
    d.line((41, 38, 41, 40), fill=(226, 82, 82))
    d.line((42, 39, 42, 40), fill=(240, 196, 70))
    d.rectangle((81, 44, 85, 45), fill=(70, 70, 80))  # lamp
    d.line((84, 43, 82, 36), fill=(70, 70, 80))
    d.polygon([(78, 37), (82, 33), (87, 37)], fill=(240, 200, 90))
    d.rectangle((52, 43, 68, 45), fill=(250, 248, 238))  # open book
    d.line((60, 42, 60, 45), fill=(170, 160, 150))
    for x0 in (53, 62):
        d.line((x0, 44, x0 + 4, 44), fill=(170, 170, 180))
    if frame == 1:  # pencil scribbles on the right page
        d.line((64, 42, 67, 39), fill=(240, 196, 70))
        d.point((64, 43), fill=(40, 28, 36))
    elif frame == 2:  # page turning
        d.polygon([(61, 42), (65, 37), (67, 38), (63, 43)], fill=(250, 248, 238))


def home_frame(v, t):
    """v: mood, indicator, talking, clock, focus (countdown or None), poops, tree_stage, hour."""
    mood = v['mood']
    color, daylight = sky(v['hour'])
    scene = Image.new('RGB', (120, 67), color)
    d = ImageDraw.Draw(scene)
    if daylight < 0.4:
        for i, (sx, sy) in enumerate(STARS):
            if int(t * 1.3 + i * 0.7) % 5:
                d.point((sx, sy), fill=mix(color, (255, 250, 220), 0.9 - daylight))
    sun_and_moon(scene, v['hour'], color)
    d.rectangle((0, 57, 119, 66), fill=mix(FLOOR_NIGHT, FLOOR_DAY, daylight))
    d.line((0, 57, 119, 57), fill=mix((96, 88, 110), (198, 168, 124), daylight))
    # The pet's pot shows the same plant as the focus garden.
    garden.place_tree(scene, v['tree_stage'], 106, 52, 0.5)
    d.rectangle((101, 52, 111, 56), fill=(190, 110, 80))
    for i, x in enumerate((2, 12, 22, 32)[:v['poops']]):
        put(scene, POOP, x, 49)
        if int(t * 2 + i) % 2:
            d.point((x + 3, 45), fill=(130, 150, 110))
            d.point((x + 6, 44), fill=(130, 150, 110))

    x, y = 44, 25  # 32x32 pet, feet on the floor line
    eyes, mouth, look = 'open', 'smile', {}
    if mood == 'eat':
        y += int(t * 2) % 2
        mouth = 'o' if int(t * 3) % 2 else 'flat'
        put(scene, ONIGIRI if int(t / 8) % 2 == 0 else CUP, 80, 45)
    elif mood == 'study':
        look['glasses'] = True
        frame = int(t * 1.5) % 3
        y, mouth = 22 + (frame == 1), 'flat'
        eyes = 'blink' if frame == 1 else 'open'
    elif mood == 'bored':
        x += round(3 * math.sin(t * 0.8))
        eyes, mouth = 'side', 'o' if t % 7 < 1 else 'flat'
        text(scene, (80, 20), '...', mix((200, 205, 230), (90, 100, 120), daylight))
    elif mood == 'pacing':
        x = 44 + round(32 * math.sin(t * 1.2))
        look['flip'] = math.cos(t * 1.2) < 0
        mouth = 'frown'
        if int(t * 2) % 2:
            put(scene, SWEAT, x + 28, y + 4)
    elif mood == 'stomp':
        landed = int(t * 6) % 2 == 0
        y -= 0 if landed else 3
        eyes, mouth = 'angry', 'open'
        text(scene, (x + 32, y + 2), '!!', (220, 50, 60))
        text(scene, (x - 6, y + 2), '!!', (220, 50, 60))
        if landed:
            d.point((x + 4, 56), fill=(170, 150, 120))
            d.point((x + 27, 56), fill=(170, 150, 120))
    elif mood == 'sick':
        look['sick'] = True
        y += 2 + int(t) % 2
        eyes, mouth = 'dizzy', 'wavy'
    elif mood == 'sleep':
        eyes, mouth = 'blink', 'flat'
        y += int(t) % 2
        for i, letter in enumerate('zZ'):
            rise = (t * 4 + i * 6) % 12
            text(scene, (x + 30 + i * 6, y + 2 - round(rise)), letter, (200, 205, 235))
    elif mood == 'happy':
        y -= round(6 * abs(math.sin(t * 6)))
        eyes = 'happy'
        put(scene, HEART, x + 28, y - 2 - int(t * 4) % 4)

    if mood != 'study' and eyes == 'open' and t % 4 < 0.15:
        eyes = 'blink'
    if mood not in ('sleep', 'sick', 'study'):
        if v['indicator'] == 'listening':
            eyes = 'open'
        elif v['indicator'] == 'thinking':
            eyes = 'up'
    if v['talking']:
        mouth = 'open' if int(t * 7) % 2 else 'flat'
    sprite = pet(eyes, mouth, **look)
    scene.paste(sprite, (x, y), sprite)
    if mood == 'study':
        desk(scene, t)
    if mood == 'sick':
        d.line((x + 17, y + 20, x + 26, y + 16), fill=(245, 245, 245))
        d.point((x + 26, y + 16), fill=PAL['R'])

    text(scene, (3, 1), v['clock'], mix((220, 222, 240), (60, 70, 95), daylight))
    floor_text = v.get('hint') or v['focus']
    if floor_text:
        text(scene, (60 - text_width(floor_text) // 2, 58), floor_text, mix((230, 220, 200), (90, 70, 50), daylight))
    kind = 'speaking' if v['talking'] else v['indicator']
    if kind:
        badge(scene, kind)
    return garden.scale_frame(scene)


def page(title, clock):
    scene = Image.new('RGB', (120, 67), garden.BG)
    text(scene, (3, 2), title, (214, 181, 122))
    text_right(scene, 117, 2, clock, (149, 159, 151))
    return scene


def todo_frame(tasks, clock):
    """tasks: list of (task, status) where status is done/overdue/soon/ok."""
    scene = page('TODAY', clock)
    d = ImageDraw.Draw(scene)
    if not tasks:
        text(scene, (3, 24), 'NO TASKS YET', (223, 228, 216))
        text(scene, (3, 36), 'SAY "ADD A TASK"', (149, 159, 151))
    for i, (task, status) in enumerate(tasks[:4]):
        y = 15 + i * 12
        color = {'done': (110, 120, 115), 'soon': (240, 200, 120),
                 'overdue': (240, 130, 120)}.get(status, (223, 228, 216))
        text(scene, (3, y), f"{i + 1} {task['title'][:12].upper()}", color)
        text(scene, (84, y), task['due'], color)
        if status == 'done':
            d.line((111, y + 5, 113, y + 7), fill=(120, 200, 120))
            d.line((113, y + 7, 118, y + 2), fill=(120, 200, 120))
        elif status == 'overdue':
            put(scene, POOP, 113, y + 3, scale=1)
    return garden.scale_frame(scene)


def status_frame(v):
    scene = page('STATUS', v['clock'])
    face = {4: 'happy', 3: 'open', 2: 'open', 1: 'side'}.get(v['hearts'], 'dizzy')
    sprite = pet(face, 'smile' if v['hearts'] >= 2 else 'frown', sick=v['hearts'] == 0)
    scene.paste(sprite, (4, 20), sprite)
    grey = (164, 184, 138)
    text(scene, (44, 13), 'MOOD', grey)
    for i in range(4):
        put(scene, HEART, 72 + i * 11, 15, pal=PAL if i < v['hearts'] else EMPTY_HEART)
    text(scene, (44, 24), f"FOCUS TODAY {v['focus_today']}", grey)
    text(scene, (44, 34), f"TASKS DONE {v['done']}/{v['total']}", grey)
    text(scene, (44, 44), f"HEAD PATS {v['pats']}", grey)
    text(scene, (44, 54), f"TREES {v['trees']}", grey)
    return garden.scale_frame(scene)


def game_frame(game, clock, t):
    scene = page('GUESS 1 TO 5', clock)
    d = ImageDraw.Draw(scene)
    result = game.get('result')
    eyes = {'lose': 'happy', 'win': 'angry'}.get(result, 'side')
    y = 22 - (round(3 * abs(math.sin(t * 5))) if result else 0)
    sprite = pet(eyes, 'open' if result else 'smile')
    scene.paste(sprite, (8, y), sprite)
    if result:
        # Cheeky: the pet gloats when you lose and sulks when you win.
        text(scene, (8, 56), 'HEHE' if result == 'lose' else 'HMPH', (240, 200, 120))
    d.rectangle((66, 15, 100, 60), fill=(245, 240, 225), outline=(214, 181, 122))
    shown = str(game['number']) if game.get('shown') and game.get('number') else '?'
    width = d.textlength(shown, font=BIG_FONT)
    mask = Image.new('L', scene.size)
    ImageDraw.Draw(mask).text((83 - width / 2, 28), shown, font=BIG_FONT, fill=255)
    scene.paste((74, 45, 52), (0, 0), mask.point(lambda n: 255 if n >= 100 else 0))
    return garden.scale_frame(scene)


_lab2_footer = garden.footer


def footer(scene, state, countdown, clock_view=False):
    """Lab 2 footer with this project's button hints (A: focus, B: next page)."""
    _lab2_footer(scene, state, countdown, clock_view)
    ImageDraw.Draw(scene).rectangle((0, 56, 84, 66), fill=scene.getpixel((1, 66)))
    text(scene, (3, 57), 'A:BACK HOLD:STOP' if state == 'running' else 'A:BACK B:NEXT', (125, 139, 137))


garden.footer = footer
