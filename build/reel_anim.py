"""
Animated native-audio Reel renderer (1080x1920, 30 fps, H.264 + AAC).

    python3 build/reel_anim.py BEATS.json CLIPS_DIR OUT_DIR

Motion language (owner reference videos, 22 Nov 2026): segmented progress bar, chapter tag per
section, text revealed word by word, illustration panel that builds itself, stickers that pop,
quick slide transitions, animated outro. Every frame is drawn in code from original shapes.

Audio = the owner's approved native clips at measured positions, silence elsewhere, two-pass
loudnorm (-16 LUFS, -1.5 dBTP). The voice is never pitch-shifted, stretched or synthesised.
The sound-wave meter is driven by the clip's real loudness, so it moves exactly with the voice.

Beat kinds: hook, listen, meaning, turn, pair, cta (see the example beats in docs/reel-beats.md).
"""

import json
import math
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
BLUE, CREAM, NAVY, GOLD, RULE, WHITE = (5, 53, 129), (242, 239, 230), (11, 33, 75), (227, 169, 59), (201, 196, 181), (255, 253, 248)
SERIF = "/usr/share/fonts/truetype/google-fonts/Lora-Variable.ttf"
SANS = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
SANS_SB = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
HANDLE = "@italianbeforeitaly"
PURE = (255, 255, 255)
# Grid rotation (owner 26 Nov 2026): every post is blue, white or cream. Hook/cta use the hero colour.
THEMES = {"blue": {"hero": BLUE, "body": CREAM}, "white": {"hero": PURE, "body": PURE},
          "cream": {"hero": CREAM, "body": CREAM}}
THEME = "blue"
BOOK_TEXT = "Want to speak like this? Book an intro session with Pietro"


def bg_for(kind):
    return THEMES[THEME]["hero" if kind in ("hook", "cta") else "body"]


def is_dark(kind):
    return bg_for(kind) == BLUE


def tint(bg, k=0.04):
    """A barely different shade of the background for moving shapes."""
    if bg == BLUE:
        return (12 + int(60 * k), 64 + int(60 * k), 148 + int(40 * k))
    if bg == CREAM:                                  # warm sand tints on cream, never grey
        return (int(242 - 60 * k), int(239 - 110 * k), int(230 - 260 * k))
    if bg == PURE:                                   # light blue tints on white, never grey
        return (int(255 - 420 * k), int(255 - 300 * k), int(255 - 120 * k))
    return tuple(int(c - c * k) for c in bg)


CREDIT = "Italian: Pietro, native speaker (original recording)"
CREDIT_VO = "Italian: Pietro, native speaker \u00b7 English narration: AI voice"
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import icons  # noqa: E402
import pietro as PIE  # noqa: E402

PIETRO_ON = True        # cartoon Pietro in every Reel (owner 26 Nov 2026); set per Reel with beats[0]["pietro"]
OUTFITS = {"barista": "barista", "waiter": "waiter", "cameriere": "waiter"}


def draw_pietro(img, t, level, mode, cx, bottom, height, outfit="shirt", seed=0, enter=0.35):
    """Cartoon Pietro. His mouth moves only with his own recording (level > 0 only while his clip plays)."""
    st = PIE.animate(t, level, mode, speaking=level > 0.04, outfit=outfit, seed=seed)
    im = PIE.render(st, height, t)
    k = ease(t / enter) if enter else 1.0
    squash = 1 + 0.025 * min(level, 1)
    if squash > 1.005:
        im = im.resize((im.width, int(im.height * squash)))
    y = bottom - im.height + (1 - k) * height * 0.6 + 7 * math.sin(t * 3.1 + seed)
    img.paste(im, (int(cx - im.width / 2), int(y)), im)

AVATARS = {"barista": "barista", "you": "you", "waiter": "waiter", "cameriere": "waiter", "clerk": "clerk",
           "ticket office": "clerk", "pharmacist": "pharmacist", "farmacista": "pharmacist"}


def speaker_avatar(label):
    return AVATARS.get((label or "").strip().lower(), "friend")


def pics_row(img, names, cx, cy, size, t, start=0.3, gap=None):
    gap = gap or size + 40
    x0 = cx - gap * (len(names) - 1) / 2
    for k, nm in enumerate(names):
        icons.paste_icon(img, nm, x0 + k * gap, cy, size, (t - start - 0.18 * k) / 0.45, t)
M = 90
_fonts = {}


def font(path, size, weight=None):
    key = (path, size, weight)
    if key not in _fonts:
        f = ImageFont.truetype(path, size)
        if weight:
            try:
                f.set_variation_by_axes([weight])
            except Exception:
                pass
        _fonts[key] = f
    return _fonts[key]


def ease(p):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def pop(p):
    """0 -> overshoot -> 1 scale curve for stickers."""
    p = min(max(p, 0.0), 1.0)
    return 1 + 0.18 * math.sin(p * math.pi) if p < 1 else 1.0


def wrap(d, text, f, width):
    lines, cur = [], []
    for word in text.split():
        if cur and d.textlength(" ".join(cur + [word]), font=f) > width:
            lines.append(cur)
            cur = []
        cur.append(word)
    return lines + [cur] if cur else lines


def words_reveal(d, text, f, x, y, width, t, per_word, color, dim, gap=1.2, center=False):
    """Draw text whose words light up one by one (dim -> color)."""
    n = 0
    for line in wrap(d, text, f, width):
        lw = d.textlength(" ".join(line), font=f)
        cx = x + (width - lw) / 2 if center else x
        for word in line:
            k = ease((t - n * per_word) / max(per_word, 0.01))
            col = tuple(int(dim[i] + (color[i] - dim[i]) * k) for i in range(3))
            d.text((cx, y), word, font=f, fill=col)
            cx += d.textlength(word + " ", font=f)
            n += 1
        y += int(f.size * gap)
    return y


def text_block(d, text, f, x, y, width, color, gap=1.2, center=False):
    for line in wrap(d, text, f, width):
        s = " ".join(line)
        lx = x + (width - d.textlength(s, font=f)) / 2 if center else x
        d.text((lx, y), s, font=f, fill=color)
        y += int(f.size * gap)
    return y


def sticker(img, text, cx, cy, p, fill=GOLD, color=NAVY, angle=-6, size=40):
    if p <= 0:
        return
    f = font(SANS_SB, size)
    tmp = Image.new("RGBA", (10, 10))
    tw = ImageDraw.Draw(tmp).textlength(text, font=f)
    w, h = int(tw + 48), int(size * 1.9)
    s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(s)
    sd.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 3, fill=fill + (255,))
    sd.text((24, (h - size * 1.2) / 2), text, font=f, fill=color)
    k = pop(p) * ease(p * 1.6)
    s = s.resize((max(1, int(w * k)), max(1, int(h * k)))).rotate(angle, expand=True, resample=Image.BICUBIC)
    x = int(min(max(cx - s.width / 2, M / 2), img.width - s.width - M / 2))   # always fully on screen
    img.paste(s, (x, int(cy - s.height / 2)), s)


def progress(d, idx, n, p, color, track):
    gap, x0, x1, y = 10, M, W - M, 120
    seg = (x1 - x0 - gap * (n - 1)) / n
    for i in range(n):
        a = x0 + i * (seg + gap)
        d.rounded_rectangle([a, y, a + seg, y + 8], radius=4, fill=track)
        fill = 1.0 if i < idx else (p if i == idx else 0.0)
        if fill > 0:
            d.rounded_rectangle([a, y, a + max(8, seg * fill), y + 8], radius=4, fill=color)


def tag(d, text, p, bg, fg, y=170):
    if p <= 0:
        return
    f = font(SANS_SB, 34)
    w = d.textlength(text.upper(), font=f) + 40
    shown = w * ease(p * 2)
    d.rounded_rectangle([M, y, M + shown, y + 58], radius=10, fill=bg)
    if p > 0.25:
        d.text((M + 20, y + 10), text.upper(), font=f, fill=fg)


def cup(d, cx, cy, p, t, with_face=False, happy=False):
    """Espresso cup drawn in stages: saucer, cup, handle, crema, steam."""
    s = 1.0
    if p > 0:
        k = ease(p * 3)
        d.ellipse([cx - 190 * k, cy + 70, cx + 190 * k, cy + 120], fill=WHITE, outline=BLUE, width=6)
    if p > 0.2:
        k = ease((p - 0.2) * 3)
        top, bot = cy - 90 * k, cy + 85
        d.polygon([(cx - 130, top), (cx + 130, top), (cx + 95, bot), (cx - 95, bot)], fill=WHITE, outline=BLUE)
        d.line([(cx - 130, top), (cx - 95, bot)], fill=BLUE, width=6)
        d.line([(cx + 130, top), (cx + 95, bot)], fill=BLUE, width=6)
        d.line([(cx - 95, bot), (cx + 95, bot)], fill=BLUE, width=6)
    if p > 0.45:
        d.arc([cx + 95, cy - 55, cx + 185, cy + 35], -90, 90, fill=BLUE, width=10)
    if p > 0.55:
        k = ease((p - 0.55) * 4)
        d.ellipse([cx - 125, cy - 108, cx + 125, cy - 72], fill=(120, 72, 40), outline=BLUE, width=6)
        d.ellipse([cx - 110 * k, cy - 102, cx + 110 * k, cy - 80], fill=(196, 140, 84))
    if p > 0.7:
        for j, off in enumerate((-55, 0, 55)):
            pts = []
            for k in range(28):
                yy = cy - 130 - k * 6
                xx = cx + off + 14 * math.sin(k / 4 + t * 4 + j)
                pts.append((xx, yy))
            a = min(1, (p - 0.7) * 4)
            d.line(pts[: max(2, int(len(pts) * a))], fill=RULE, width=6, joint="curve")
    if with_face and p > 0.4:
        face(d, cx, cy + 10, t, happy)


def cornetto(d, cx, cy, p):
    if p <= 0:
        return
    x = cx + (1 - ease(p * 1.5)) * 500
    pts = []
    for a in range(200, 341, 4):
        r = math.radians(a)
        pts.append((x + 210 * math.cos(r), cy + 30 + 150 * math.sin(r) * -1 * -1))
    for a in range(340, 199, -4):
        r = math.radians(a)
        pts.append((x + 120 * math.cos(r), cy + 40 + 70 * math.sin(r)))
    d.polygon(pts, fill=GOLD, outline=BLUE)
    d.line(pts + [pts[0]], fill=BLUE, width=6)
    for k in (-80, -30, 20, 70):
        d.line([(x + k, cy - 95 + abs(k) * 0.55), (x + k * 0.8, cy - 10 + abs(k) * 0.3)], fill=BLUE, width=5)


def wave(d, level, cx, y, t, color):
    """Sound-wave meter driven by the real clip loudness (0..1)."""
    for i in range(-6, 7):
        h = 14 + 120 * level * (0.55 + 0.45 * math.sin(i * 1.7 + t * 18)) * (1 - abs(i) / 9)
        d.rounded_rectangle([cx + i * 34 - 10, y - h / 2, cx + i * 34 + 10, y + h / 2], radius=10, fill=color)


def ring(d, cx, cy, frac, color, track):
    d.ellipse([cx - 110, cy - 110, cx + 110, cy + 110], outline=track, width=16)
    if frac > 0:
        d.arc([cx - 110, cy - 110, cx + 110, cy + 110], -90, -90 + 360 * frac, fill=color, width=16)


def arch(d, cx, cy, size, p, color, width=10):
    if p <= 0:
        return
    k = ease(p)
    d.arc([cx - size, cy - size, cx + size, cy + size], 180, 180 + 180 * k, fill=color, width=width)
    if k > 0.95:
        d.line([(cx - size + width / 2, cy), (cx - size + width / 2, cy + size * 0.7)], fill=color, width=width)
        d.line([(cx + size - width / 2, cy), (cx + size - width / 2, cy + size * 0.7)], fill=color, width=width)


def bg_motion(d, t, bg):
    """Large soft circles and a Roman arch outline drifting behind everything."""
    c = tint(bg, 0.035)
    for i, (r, sp) in enumerate(((420, 0.11), (300, 0.17), (360, 0.08))):
        cx = W * (0.15 + 0.35 * i) + 120 * math.sin(t * sp * 2 + i * 2)
        cy = H * (0.25 + 0.27 * i) + 90 * math.cos(t * sp * 2.6 + i)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    ax, ay = W - 170 + 20 * math.sin(t * 0.5), 1500 + 15 * math.cos(t * 0.4)
    d.arc([ax - 150, ay - 150, ax + 150, ay + 150], 180, 360, fill=tint(bg, 0.07), width=14)
    d.line([ax - 150, ay, ax - 150, ay + 260], fill=tint(bg, 0.07), width=14)
    d.line([ax + 150, ay, ax + 150, ay + 260], fill=tint(bg, 0.07), width=14)


def burst(d, cx, cy, p, color, r=120, n=10):
    """Radial spark burst for pops and reveals (p 0..1)."""
    if not 0 < p < 1:
        return
    for k in range(n):
        a = k * 2 * math.pi / n + 0.3
        r0, r1 = r * (0.3 + 0.7 * p), r * (0.55 + 0.75 * p)
        d.line([cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a)],
               fill=color, width=max(2, int(9 * (1 - p))))


def particles(d, t, kind, dark, bg=None):
    """Slow drifting background shapes: coffee beans or letters. Deterministic per index."""
    col = (30, 72, 145) if dark else tint(bg or CREAM, 0.08)
    for i in range(14):
        x = (i * 157 + 60) % (W - 80) + 40 + 18 * math.sin(t * 0.8 + i)
        y = (1700 - ((t * (22 + i % 5 * 6) + i * 233) % 1500))
        if kind == "beans":
            d.ellipse([x - 16, y - 24, x + 16, y + 24], outline=col, width=5)
            d.arc([x - 8, y - 22, x + 8, y + 22], 100, 260, fill=col, width=4)
        else:
            d.text((x, y), "aeiolrst"[i % 8], font=font(SERIF, 64, 500), fill=col)


def awning(d, p):
    """Cafe awning: striped canopy with scalloped edge that drops in."""
    k = ease(p)
    h = 120 * k
    stripes = 9
    sw = W / stripes
    a, b = (CREAM, (230, 224, 210)) if THEME == "blue" else (BLUE, (40, 86, 160))
    for i in range(stripes):
        d.rectangle([i * sw, 0, (i + 1) * sw, h], fill=a if i % 2 else b)
        d.pieslice([i * sw, h - sw / 2, (i + 1) * sw, h + sw / 2], 0, 180, fill=a if i % 2 else b)
    d.line([0, h, W, h], fill=GOLD, width=4)


def face(d, cx, cy, t, happy=False):
    blink = (t % 2.6) < 0.12
    for ex in (-38, 38):
        if blink:
            d.line([cx + ex - 12, cy, cx + ex + 12, cy], fill=NAVY, width=6)
        else:
            d.ellipse([cx + ex - 11, cy - 13, cx + ex + 11, cy + 13], fill=NAVY)
    r = 34 if happy else 24
    d.arc([cx - r, cy + 4, cx + r, cy + 14 + r], 20, 160, fill=NAVY, width=6)
    d.ellipse([cx - 72, cy + 18, cx - 48, cy + 34], fill=(240, 178, 160))
    d.ellipse([cx + 48, cy + 18, cx + 72, cy + 34], fill=(240, 178, 160))


def check(d, cx, cy, size, color, width=12):
    d.line([(cx - size, cy), (cx - size / 3, cy + size * 0.7), (cx + size, cy - size * 0.7)], fill=color, width=width,
           joint="curve")


def confetti(d, cx, cy, p):
    if not 0 < p < 1:
        return
    for i in range(26):
        a = i / 26 * 2 * math.pi
        r = 60 + 420 * ease(p) * (0.6 + 0.4 * ((i * 37) % 10) / 10)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a) + 300 * p * p
        col = (GOLD, BLUE, NAVY, (196, 140, 84))[i % 4]
        d.rectangle([x - 9, y - 5, x + 9, y + 5], fill=col)


def double_highlight(d, word, f, x, y, color, accent):
    """Draw a word with any doubled consonant in the accent colour."""
    i, cx = 0, x
    while i < len(word):
        dbl = i + 1 < len(word) and word[i] == word[i + 1] and word[i] not in "aeiou"
        part = word[i:i + 2] if dbl else word[i]
        d.text((cx, y), part, font=f, fill=accent if dbl else color)
        cx += d.textlength(part, font=f)
        i += 2 if dbl else 1


def hook_title(d, text, hl, x, y, t, color, dim, dark):
    """Hook title: words slam in fast (all visible by ~0.5 s), highlighted words get a gold marker swipe."""
    f = font(SERIF, 118 if len(text) < 34 else 100, 600)
    hls = {w.strip(".,!?:;\"'").lower() for w in hl.split()} if hl else set()
    n = 0
    for line in wrap(d, text, f, W - 2 * M):
        cx = x
        for word in line:
            k = ease((t - n * 0.025) / 0.12)   # every word visible from frame 0; only a quick drop-in motion
            bare = word.strip(".,!?:;\"'").lower()
            ww = d.textlength(word, font=f)
            if bare in hls:
                m = ease((t - 0.45 - 0.1 * n * 0) / 0.3)
                d.rounded_rectangle([cx - 10, y + f.size * 0.18, cx - 10 + (ww + 20) * m, y + f.size * 1.12],
                                    radius=14, fill=GOLD)
            col = NAVY if bare in hls and t > 0.6 else color
            d.text((cx, y - 36 * (1 - k)), word, font=f, fill=col)
            cx += d.textlength(word + " ", font=f)
            n += 1
        y += int(f.size * 1.18)
    return y


def sound_pill(img, t, dark, y0=1440):
    d = ImageDraw.Draw(img)
    f = font(SANS_SB, 38)
    label = "Sound on"
    w = d.textlength(label, font=f) + 130
    x0 = (W - w) / 2
    q = ease((t - 0.3) / 0.3)
    col = CREAM if dark else BLUE
    d.rounded_rectangle([x0, y0 + 30 * (1 - q), x0 + w, y0 + 80 + 30 * (1 - q)], radius=40, outline=col, width=4)
    for k in range(4):
        h = 10 + 18 * abs(math.sin(t * 6 + k))
        bx = x0 + 34 + k * 14
        d.line([bx, y0 + 40 - h / 2, bx, y0 + 40 + h / 2], fill=GOLD, width=6)
    d.text((x0 + 105, y0 + 18), label, font=f, fill=col)


def fly_in(img, d, names, cx, cy, size, t, start):
    """Icons burst out of the centre to their slots with overshoot, then bob."""
    gap = size + 40
    x0 = cx - gap * (len(names) - 1) / 2
    for k, nm in enumerate(names):
        p = ease((t - start - 0.12 * k) / 0.45)
        tx, ty = x0 + k * gap, cy
        x, y = cx + (tx - cx) * p, cy + 200 * (1 - p) + (ty - cy) * p
        icons.paste_icon(img, nm, x, y, size, (t - start - 0.12 * k) / 0.35, t)
        burst(d, tx, ty, (t - start - 0.12 * k - 0.35) / 0.4, GOLD, size * 0.75)


def draw_beat(beat, t, dur, idx, n, level, img):
    d = ImageDraw.Draw(img)
    p = t / dur if dur else 1
    kind = beat["kind"]
    dark = is_dark(kind)
    bg = bg_for(kind)
    fg, track = (CREAM, (40, 80, 150)) if dark else (BLUE, RULE)
    hfg, hdim = (CREAM, (40, 80, 150)) if dark else (BLUE, tint(bg, 0.16))
    bg_motion(d, t + idx * 5, bg)
    if beat.get("particles"):
        particles(d, t + idx * 3, beat["particles"], dark, bg)
    if kind == "hook" and beat.get("scene") == "cafe":
        awning(d, t / 0.6)
    progress(d, idx, n, p, GOLD if dark else BLUE, track)
    if kind == "hook":
        k = pop(t / 0.35)
        tag(d, beat["series"], min(t / 0.25, 1), CREAM if dark else BLUE, BLUE if dark else CREAM)
        y = hook_title(d, beat["title"], beat.get("hl", ""), M, 330, t, hfg, hdim, dark)
        if beat.get("sub") and t > 0.55:
            text_block(d, beat["sub"], font(SANS, 46), M, y + 20, W - 2 * M, hfg)
        if PIETRO_ON:
            draw_pietro(img, t, 0.0, "hook", W // 2, H + 40, 820, enter=0.45)
        if t > 0.3:
            sound_pill(img, t, dark, 1040 if PIETRO_ON else 1440)
        if beat.get("art") == "cup":
            cup(d, W // 2, 1150, (t - 0.3) / 1.6, t, with_face=True, happy=t > 1.8)
        elif beat.get("art") == "pairs":
            f = font(SERIF, 130, 600)
            pw = beat.get("pair_words", ["pala", "palla"])
            pf = font(SERIF, 130, 600)
            while max(d.textlength(w, font=pf) for w in pw) > 330 and pf.size > 60:
                pf = font(SERIF, pf.size - 8, 600)
            f = pf
            for k, (wd, xx) in enumerate(((pw[0], 230), (pw[1], 640))):
                q = ease((t - 0.4 - 0.3 * k) * 2.5)
                if q > 0:
                    d.rounded_rectangle([xx - 170, 1040 - 90 * q, xx + 210, 1250], radius=28, fill=WHITE, outline=RULE,
                                        width=4)
                    double_highlight(d, wd, f, xx - 130, 1080, BLUE, (176, 106, 0))
            sticker(img, beat.get("pair_sticker", "hear the difference?"), W // 2, 1340, (t - 1.2) / 0.5, angle=4)
        elif beat.get("pics"):
            if PIETRO_ON:
                fly_in(img, d, beat["pics"][:3], W // 2, 880, 190, t, 0.25)
            else:
                fly_in(img, d, beat["pics"][:3], W // 2, 1150, 260 if len(beat["pics"]) < 3 else 220, t, 0.25)
    elif kind in ("listen", "turn"):
        tag(d, beat.get("label", "Listen" if kind == "listen" else "Your turn"), t / 0.4, BLUE, CREAM)
        f = font(SERIF, 96 if len(beat["it"]) < 40 else 78, 600)
        k = ease(t / 0.35)
        y = 520 + (1 - k) * 60
        y = text_block(d, beat["it"], f, M, y, W - 2 * M, BLUE if k > 0.3 else RULE)
        if kind == "listen":
            wave(d, level, W // 2, y + 170, t, BLUE)
            if beat.get("sticker"):
                sticker(img, beat["sticker"], W - 260, y + 330, (t - 0.6) / 0.5)
                burst(d, W - 260, y + 330, (t - 0.75) / 0.4, GOLD, 200, 12)
            who = speaker_avatar(beat.get("label"))
            right = who == "you"
            ay = min(max(1310, y + 520), 1400)
            asz = 290 if ay <= 1310 else 240
            if PIETRO_ON:
                draw_pietro(img, t, level, "listen", 320, H + 30, 700, OUTFITS.get(who, "shirt"), seed=idx)
                pics = beat.get("pics", [])[:2]
                if pics:
                    pics_row(img, pics, W - 260, 1420, 170, t, 0.5, gap=190)
            elif beat.get("label"):
                icons.avatar(img, who, W - 220 if right else 220, ay, asz, t / 0.35, t, talking=level > 0.25 and
                             int(t * 9) % 2 == 0)
            pics = [] if PIETRO_ON else beat.get("pics", [])[:2]
            if pics:
                pics_row(img, pics, 330 if right else W - 330, ay, 190 if asz == 290 else 160, t, 0.5)
        else:
            frac = 1 - min(t / dur, 1)
            ring(d, W // 2, y + 240, frac, BLUE, RULE)
            text_block(d, "Say it out loud", font(SANS_SB, 44), M, y + 410, W - 2 * M, NAVY, center=True)
            if PIETRO_ON:
                draw_pietro(img, t, 0.0, "turn", W // 2, H + 40, 760, seed=idx)
            else:
                icons.avatar(img, "you", 260, 1330, 260, t / 0.35, t, talking=int(t * 4) % 2 == 0)
                icons.paste_icon(img, "mouth", W - 260, 1330, 210, (t - 0.3) / 0.4, t, wiggle=True)
    elif kind == "meaning":
        tag(d, "What it means", t / 0.4, BLUE, CREAM)
        y = text_block(d, beat["it"], font(SERIF, 72, 600), M, 330, W - 2 * M, BLUE)
        d.line([M, y + 30, M + 180 * ease(t / 0.5), y + 30], fill=GOLD, width=6)
        y = words_reveal(d, beat["en"], font(SANS_SB, 60), M, y + 70, W - 2 * M, t - 0.3, 0.16, NAVY, RULE)
        if beat.get("art") == "cup":
            cup(d, 330, y + 330, (t - 0.2) / 1.4, t, with_face=True)
        elif beat.get("art") == "cup+cornetto":
            cup(d, 300, y + 330, (t - 0.2) / 1.2, t)
            cornetto(d, 760, y + 330, (t - 0.8) / 0.8)
        elif beat.get("pics"):
            if PIETRO_ON:
                pics_row(img, beat["pics"][:2], 300, min(y + 260, 1250), 190, t, 0.6, gap=210)
            else:
                pics_row(img, beat["pics"][:3], W // 2, min(y + 300, 1300), 220, t, 0.6)
        if PIETRO_ON:
            draw_pietro(img, t, 0.0, "thumbs" if idx % 2 else "idle", W - 300, H + 40, 640, seed=idx)
        for s in beat.get("stickers", []):
            sticker(img, s["text"], s.get("x", 760), y + s.get("dy", 220), (t - s.get("at", 1.2)) / 0.45,
                    angle=s.get("angle", -6))
    elif kind == "pair":
        tag(d, beat.get("label", "Listen"), t / 0.4, BLUE, CREAM)
        f = font(SERIF, 150, 600)
        while d.textlength(beat["word"], font=f) > W - 2 * M - 60 and f.size > 60:
            f = font(SERIF, f.size - 8, 600)
        k = ease(t / 0.3)
        d.rounded_rectangle([M, 420 + (1 - k) * 80, W - M, 760], radius=32, fill=WHITE, outline=RULE, width=4)
        double_highlight(d, beat["word"], f, (W - d.textlength(beat["word"], font=f)) / 2, 500, BLUE, (176, 106, 0))
        text_block(d, beat["en"], font(SANS_SB, 52), M, 800, W - 2 * M, NAVY, center=True)
        wave(d, level, W // 2, 1060, t, BLUE)
        if beat.get("sticker"):
            sticker(img, beat["sticker"], W // 2, 1260, (t - 0.5) / 0.45, angle=beat.get("angle", -5))
        if PIETRO_ON:
            draw_pietro(img, t, level, "listen", W - 270, H + 30, 560, seed=idx)
            if beat.get("pics"):
                pics_row(img, beat["pics"][:2], 300, 1440, 150, t, 0.4)
        elif beat.get("pics"):
            pics_row(img, beat["pics"][:2], W // 2, 1420, 150, t, 0.4)
    elif kind == "quiz":
        tag(d, "Quiz", t / 0.4, GOLD, NAVY)
        text_block(d, beat["q"], font(SERIF, 76, 600), M, 300, W - 2 * M, BLUE)
        reveal = beat["_reveal"]
        opts = beat["options"]
        card_w = (W - 2 * M) // 2 - 15
        size = 104
        while size > 48 and max(d.textlength(o, font=font(SERIF, size, 600)) for o in opts) > card_w - 50:
            size -= 4
        oi = beat.get("option_icons")
        if oi:
            size = min(size, 64)
        f = font(SERIF, size, 600)
        for k, word in enumerate(opts):
            x0 = M + k * ((W - 2 * M) // 2 + 15)
            x1 = x0 + (W - 2 * M) // 2 - 15
            q = ease((t - 0.15 * k) / 0.35)
            y0 = 620 + (1 - q) * 120
            right = k == beat["answer"]
            done = t >= reveal
            fill = BLUE if (done and right) else WHITE
            col = CREAM if (done and right) else (RULE if done else BLUE)
            d.rounded_rectangle([x0, y0, x1, y0 + 300], radius=30, fill=fill, outline=BLUE if not done else fill, width=4)
            ty = y0 + (225 if oi else 150) - size * 0.6
            d.text((x0 + (x1 - x0 - d.textlength(word, font=f)) / 2, ty), word, font=f, fill=col)
            if oi:
                icons.paste_icon(img, oi[k], (x0 + x1) / 2, y0 + 100, 140, q, t, bob=4 if not done else 0)
            if done and right:
                check(d, x1 - 45 if oi else (x0 + x1) / 2, y0 + 45 if oi else y0 + 250, 26 * ease((t - reveal) / 0.3), GOLD, 10)
                h = ease((t - reveal) / 0.45)
                tx, tyy = (x0 + x1) / 2 + 110, y0 + 360
                press = 1 - 0.12 * max(0, math.sin(min(max(t - reveal - 0.45, 0) * 8, math.pi)))
                icons.paste_icon(img, "wave_hand", tx + (1 - h) * 200, tyy + (1 - h) * 400, int(150 * press), 1, t,
                                 bob=0)
        if t < beat["_clipend"]:
            wave(d, level, W // 2, 1080, t, BLUE)
        elif t < reveal:
            ring(d, W // 2, 1130, 1 - (t - beat["_clipend"]) / max(reveal - beat["_clipend"], 0.1), BLUE, RULE)
        else:
            sticker(img, beat.get("explain", "correct!"), W // 2, 1080, (t - reveal) / 0.4, angle=-3)
            confetti(d, W // 2, 800, (t - reveal) / 1.2)
        if PIETRO_ON:
            mode = "celebrate" if t >= reveal else ("listen" if t < beat["_clipend"] else "think")
            draw_pietro(img, t, level, mode, W // 2, H + 60, 600, seed=idx, enter=0.0)
    elif kind == "cta":
        book = beat.get("book")
        arch(d, W // 2, 700 if book else 760, 110, t / 0.9, hfg)
        y = 880 if not book else 820
        text = beat.get("text") if not book else BOOK_TEXT
        if t > 0.4:
            y = words_reveal(d, text, font(SERIF, 96 if not book else 84, 600), M, y, W - 2 * M, t - 0.4, 0.1, hfg,
                             hdim, center=True)
        if book and t > 1.0:
            q = pop((t - 1.0) / 0.4)
            pw, ph = 560 * q, 120 * q
            pulse = 1 + 0.04 * math.sin(t * 7)
            pw, ph = pw * pulse, ph * pulse
            d.rounded_rectangle([W / 2 - pw / 2, y + 60, W / 2 + pw / 2, y + 60 + ph], radius=60, fill=GOLD)
            if q > 0.8:
                f = font(SANS_SB, 52)
                d.text((W / 2 - d.textlength("Link in bio", font=f) / 2, y + 60 + ph / 2 - 32), "Link in bio", font=f,
                       fill=NAVY)
            y += 200
        if t > 1.3:
            text_block(d, CREDIT_VO if beat.get("_ai_vo") else CREDIT, font(SANS, 30), M, max(y + 30, 1160),
                       W - 2 * M, hfg, center=True)
        if PIETRO_ON:
            draw_pietro(img, t, 0.0, "book" if book else "wave", W // 2, H + 60, 520 if book else 600, seed=idx)
    if PIETRO_ON:                                    # handle top-right, clear of the character
        f = font(SANS, 30)
        d.text((W - M - d.textlength(HANDLE, font=f), 112), HANDLE, font=f, fill=fg if not dark else CREAM)
    else:
        d.text((M, 1560), HANDLE, font=font(SANS, 34), fill=fg)


def clip_path(clips, cid):
    """Approved clips may be WAV (local) or FLAC (private repo)."""
    for ext in (".wav", ".flac"):
        p = clips / f"{cid}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"AUDIO_NEEDED: no approved clip {cid} in {clips}")


def clip_env(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "<i2").astype(float) / 32768
    hop = 48000 // FPS
    n = len(x) // hop
    rms = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1))
    db = 20 * np.log10(rms + 1e-6)
    return np.clip((db + 50) / 35, 0, 1), len(x) / 48000


def loudnorm_filter(src):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af",
                          "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(out[out.rindex("{"):out.rindex("}") + 1])
    return (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def main(argv):
    beats = json.loads(pathlib.Path(argv[1]).read_text())
    global THEME, PIETRO_ON
    THEME = beats[0].get("theme", "blue")
    PIETRO_ON = beats[0].get("pietro", True)
    if THEME not in THEMES:
        raise SystemExit(f"unknown theme {THEME}")
    clips, out = pathlib.Path(argv[2]), pathlib.Path(argv[3])
    out.mkdir(parents=True, exist_ok=True)
    import tempfile
    vo_dir = pathlib.Path(tempfile.mkdtemp())
    any_vo = any(b.get("vo") for b in beats)
    if any_vo:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        import voice
    plan, t = [], 0.0
    for i, b in enumerate(beats):
        vo_path, vo_dur = None, 0.0
        if b.get("vo"):
            vo_path = voice.narrate(b["vo"], str(vo_dir / f"vo{i}.wav"))
            vo_dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                           "default=nw=1:nk=1", vo_path], capture_output=True, text=True).stdout)
        if b["kind"] == "cta":
            b["_ai_vo"] = any_vo
        lead = (0.3 + (vo_dur + 0.25 if vo_path else 0.0)) if b.get("clip") else 0.0
        env, cd = (clip_env(clip_path(clips, b['clip'])) if b.get("clip") else (None, 0.0))
        dur = lead + cd + b.get("hold", 0.8) if b.get("clip") else max(b["seconds"], vo_dur + 0.6)
        if b["kind"] == "quiz":
            b["_clipend"] = lead + cd
            b["_reveal"] = lead + cd + b.get("think", 2.0)
            dur = b["_reveal"] + b.get("after", 2.3)
        plan.append({"beat": b, "start": t, "dur": dur, "lead": lead, "env": env, "vo": vo_path})
        t += dur
    total = t
    n = len(plan)
    TR = 0.22                                            # slide transition between beats
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                            "-pix_fmt", "yuv420p", str(out / "video.mp4")], stdin=subprocess.PIPE)
    frames = int(round(total * FPS))
    snaps = {}
    for fi in range(frames):
        now = fi / FPS
        idx = max(i for i, x in enumerate(plan) if x["start"] <= now + 1e-9)
        x = plan[idx]
        lt = now - x["start"]
        level = 0.0
        if x["env"] is not None:
            k = int((lt - x["lead"]) * FPS)
            if 0 <= k < len(x["env"]):
                level = float(x["env"][k])
        img = Image.new("RGB", (W, H), bg_for(x["beat"]["kind"]))
        draw_beat(x["beat"], lt, x["dur"], idx, n, level, img)
        kb = x["beat"]["kind"]
        zoom = 0.0
        if lt < 0.4:                                     # camera punch-in at every beat (stronger on the hook)
            zoom = (0.14 if kb == "hook" else 0.05) * (1 - ease(lt / 0.4))
        if kb == "quiz" and 0 <= lt - x["beat"].get("_reveal", 1e9) < 0.35:
            zoom = max(zoom, 0.04 * (1 - (lt - x["beat"]["_reveal"]) / 0.35))
        if zoom > 0.002:
            cw, chh = int(W / (1 + zoom)), int(H / (1 + zoom))
            img = img.crop(((W - cw) // 2, (H - chh) // 2, (W - cw) // 2 + cw, (H - chh) // 2 + chh)).resize((W, H))
        if kb == "quiz" and 0 <= lt - x["beat"].get("_reveal", 1e9) < 0.3:
            dx = int(12 * math.sin((lt - x["beat"]["_reveal"]) * 60) * (1 - (lt - x["beat"]["_reveal"]) / 0.3))
            img = img.transform((W, H), Image.AFFINE, (1, 0, -dx, 0, 1, 0), fillcolor=bg_for(kb))
        if idx > 0 and lt < TR:                          # previous beat slides up and away
            prev = plan[idx - 1]
            pbg = bg_for(prev["beat"]["kind"])
            pimg = Image.new("RGB", (W, H), pbg)
            draw_beat(prev["beat"], prev["dur"], prev["dur"], idx - 1, n, 0.0, pimg)
            off = int(H * ease(lt / TR))
            img.paste(pimg.crop((0, off, W, H)), (0, 0))
        enc.stdin.write(img.tobytes())
        if lt >= x["dur"] * 0.75 and idx not in snaps:
            snaps[idx] = img.resize((270, 480))
    enc.stdin.close()
    enc.wait()
    # audio: native voice + sound effects + original music ducked under the voice
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import music
    SR = music.SR
    N = int(total * SR) + SR
    voice, fx = np.zeros(N), np.zeros(N)
    for x in plan:
        b = x["beat"]
        if x.get("vo"):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", x["vo"], "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                                 capture_output=True, check=True).stdout
            music.place(voice, np.frombuffer(raw, "<i2").astype(float) / 32768 * 0.9, x["start"] + 0.12)
        if b.get("clip"):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip_path(clips, b['clip'])), "-ac", "1", "-ar",
                                  str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
            music.place(voice, np.frombuffer(raw, "<i2").astype(float) / 32768, x["start"] + x["lead"])
        events = []
        if x["start"] > 0:
            events.append(("whoosh", 0.0, 0.5))
        for st in b.get("stickers", []):
            events.append(("pop", st.get("at", 1.2), 0.8))
        if b.get("sticker"):
            events.append(("pop", 0.6 if b["kind"] == "listen" else (1.2 if b["kind"] == "hook" else 0.5), 0.8))
        if b["kind"] == "turn":
            events += [("tick", k + 0.0, 0.6) for k in range(1, int(x["dur"]))]
        if b["kind"] == "quiz":
            events += [("tick", b["_clipend"] + k * 0.5, 0.5) for k in range(int((b["_reveal"] - b["_clipend"]) / 0.5))]
            events += [("ding", b["_reveal"], 1.0), ("pop", b["_reveal"] + 0.05, 0.6)]
        for kind, at, g in events:
            music.place(fx, music.sfx(kind), x["start"] + at, g)
    track = np.zeros(N)
    mood = plan[0]["beat"].get("mood", "caffe")
    if mood != "none":
        m = music.score(total + 0.5, mood, plan[0]["beat"].get("seed", 7))
        track[: len(m)] = m[:N]
    hop = SR // 100                                       # 10 ms voice-presence envelope -> ducking gain
    frames_v = len(voice) // hop
    env = np.sqrt((voice[: frames_v * hop].reshape(frames_v, hop) ** 2).mean(1)) > 0.01
    gain, g = np.ones(frames_v), 1.0
    for i, on in enumerate(env):
        target = 0.22 if on else 1.0
        g += (target - g) * (0.35 if target < g else 0.04)          # fast duck, slow release
        gain[i] = g
    look = 15                                              # duck 150 ms before the voice starts
    gain = np.minimum(gain, np.concatenate([gain[look:], np.ones(look)]))
    track[: frames_v * hop] *= np.repeat(gain, hop)
    mix = voice + 0.22 * track + 0.5 * fx
    music.write_wav(out / "audio_raw.wav", mix / max(1.0, np.abs(mix).max()))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out / "video.mp4"), "-i", str(out / "audio_raw.wav"),
                    "-af", loudnorm_filter(out / "audio_raw.wav") + ",alimiter=limit=0.79:attack=2:release=60,aresample=48000",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest", "-movflags", "+faststart",
                    str(out / "reel.mp4")], check=True)
    cover = Image.new("RGB", (W, H), bg_for("hook"))
    draw_beat(plan[0]["beat"], plan[0]["dur"], plan[0]["dur"], 0, n, 0.0, cover)
    cover.save(out / "cover.jpg", quality=92)
    sheet = Image.new("RGB", (270 * min(n, 6), 480 * ((n + 5) // 6)), "white")
    for i in range(n):
        if i in snaps:
            sheet.paste(snaps[i], (270 * (i % 6), 480 * (i // 6)))
    sheet.save(out / "contact-sheet.jpg", quality=88)
    (out / "timeline.json").write_text(json.dumps({"total_seconds": round(total, 3), "beats": [
        {"kind": x["beat"]["kind"], "start": round(x["start"], 3), "seconds": round(x["dur"], 3),
         "clip": x["beat"].get("clip")} for x in plan]}, indent=1))
    print(f"reel.mp4 {total:.1f}s, {n} beats, {frames} frames")


if __name__ == "__main__":
    main(sys.argv)
