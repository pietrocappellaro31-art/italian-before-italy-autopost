"""
Cartoon Pietro: the owner's own stylised likeness, drawn from his photos (owner request 26 Nov 2026).
Original vector art in PIL, no AI image generation.

    frame = pietro.render(state, height)          -> RGBA image
    state = pietro.State(mouth=0.6, expr="grin", blink=0, brow=0.3, look=(0.2, 0), gesture="wave", phase=0.4,
                         outfit="shirt", tilt=3)

Features from the photos: dark brown messy hair with forward tufts, thick dark straight brows, brown eyes that
squint when he smiles, long straight nose, big bright toothy grin, defined jaw, light olive skin with a few
freckles, white shirt with navy pinstripes, shell necklace.

Honesty rule: the mouth only moves to Pietro's own recordings. During the AI English narration he reacts
(smiles, nods, gestures) but does not lip-sync, so the AI voice is never presented as his.
"""

import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

S = 2                        # supersampling
CW, CH = 800, 880            # design canvas
SKIN, SKIN_D, SKIN_L = (226, 176, 138), (196, 140, 104), (238, 196, 160)
LINE = (70, 42, 32)
HAIR, HAIR_L = (36, 26, 22), (82, 60, 48)
IRIS, MOUTH_IN, TONGUE, TEETH = (78, 50, 30), (110, 34, 40), (214, 100, 104), (252, 250, 244)
SHIRT, STRIPE, NAVY, BLUE, CREAM, GOLD, RED = ((250, 248, 242), (54, 72, 120), (11, 33, 75), (5, 53, 129),
                                              (242, 239, 230), (227, 169, 59), (196, 62, 52))
SHELL, SHELL_D = (246, 236, 214), (214, 196, 164)
GESTURES = ("none", "wave", "point_up", "think", "ear", "celebrate", "thumbs")
EXPRS = ("smile", "grin", "talk", "surprised", "think", "wink")


@dataclass(frozen=True)
class State:
    mouth: float = 0.0       # 0 closed .. 1 wide open (talking)
    expr: str = "smile"
    blink: float = 0.0       # 0 open .. 1 closed
    brow: float = 0.0        # -1 frown .. 1 raised
    look: tuple = (0.0, 0.0)
    gesture: str = "none"
    phase: float = 0.0       # gesture animation phase 0..1
    outfit: str = "shirt"    # shirt | barista | waiter
    tilt: float = 0.0        # degrees, applied after drawing


class _D:
    """ImageDraw proxy in design units."""
    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img)

    def __getattr__(self, name):
        f = getattr(self.d, name)

        def g(xy, *a, **k):
            if "width" in k:
                k["width"] = max(1, int(k["width"] * S))
            if "radius" in k:
                k["radius"] = k["radius"] * S
            pts = [tuple(v * S for v in p) if isinstance(p, tuple) else p * S for p in xy]
            return f(pts, *a, **k)
        return g


def smooth(pts, n=10, closed=True):
    """Catmull-Rom spline through pts -> dense polygon."""
    out = []
    m = len(pts)
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p0, p1, p2, p3 = (pts[(i - 1) % m], pts[i], pts[(i + 1) % m], pts[(i + 2) % m])
        if not closed:
            p0 = pts[max(i - 1, 0)]
            p3 = pts[min(i + 2, m - 1)]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    if not closed:
        out.append(pts[-1])
    return out


def mirror(half, cx):
    """half: points on the right side from top to bottom -> closed symmetric outline."""
    return half + [(2 * cx - x, y) for x, y in reversed(half)]


def _ell(d, cx, cy, rx, ry, **k):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], **k)


def stroke_line(d, pts, w, col, outline=LINE, ow=4):
    d.line(pts, fill=outline, width=w + 2 * ow, joint="curve")
    for p in (pts[0], pts[-1]):
        _ell(d, p[0], p[1], (w + 2 * ow) / 2, (w + 2 * ow) / 2, fill=outline)
    d.line(pts, fill=col, width=w, joint="curve")
    for p in (pts[0], pts[-1]):
        _ell(d, p[0], p[1], w / 2, w / 2, fill=col)


CX = CW / 2
HEAD_Y = 330            # head centre


def face_outline():
    half = [(CX, 120), (CX + 120, 150), (CX + 168, 250), (CX + 170, 340), (CX + 158, 420), (CX + 128, 490),
            (CX + 74, 540), (CX, 556)]
    return smooth(mirror(half, CX)[:-1], 8)


def _hand(d, cx, cy, ang, pose="open", scale=1.0):
    """Cartoon hand with outline. ang in degrees (0 = fingers up)."""
    a = math.radians(ang)
    ca, sa = math.cos(a), math.sin(a)

    def P(x, y):
        x, y = x * scale, y * scale
        return (cx + x * ca - y * sa, cy + x * sa + y * ca)
    fingers = {"open": [(-27, -62), (-9, -74), (9, -72), (26, -60)], "point": [(-16, -88)], "fist": [],
               "thumb": []}[pose]
    thumb = [P(-30, 6), P(-60, -26)] if pose != "thumb" else [P(-24, -10), P(-30, -72)]
    for fx, fy in fingers:
        d.line([P(fx * 0.85, -14), P(fx, fy)], fill=LINE, width=int(26 * scale))
    d.line(thumb, fill=LINE, width=int(28 * scale))
    _ell(d, *P(0, 8), 42 * scale, 40 * scale, fill=LINE)
    for fx, fy in fingers:
        d.line([P(fx * 0.85, -14), P(fx, fy)], fill=SKIN, width=int(18 * scale))
        _ell(d, *P(fx, fy), 9 * scale, 9 * scale, fill=SKIN)
    d.line(thumb, fill=SKIN, width=int(20 * scale))
    _ell(d, *thumb[1], 10 * scale, 10 * scale, fill=SKIN)
    _ell(d, *P(0, 8), 37 * scale, 35 * scale, fill=SKIN)
    if pose in ("fist", "thumb", "point"):
        for k in range(3):
            d.arc([*P(-28, -26 + k * 16), *P(24, -6 + k * 16)], 200, 340, fill=SKIN_D, width=3)


def _arm(d, shoulder, elbow, hand, outfit):
    col = SHIRT if outfit != "waiter" else (30, 34, 50)
    stroke_line(d, [shoulder, elbow, hand], 64, col)
    if outfit != "waiter":
        for seg in ((shoulder, elbow), (elbow, hand)):
            (x0, y0), (x1, y1) = seg
            n = math.hypot(x1 - x0, y1 - y0) or 1
            for k in (-2, -1, 0, 1, 2):
                ox, oy = -(y1 - y0) / n * k * 11, (x1 - x0) / n * k * 11
                d.line([(x0 + ox, y0 + oy), (x1 + ox, y1 + oy)], fill=STRIPE, width=2)
    d.line([elbow, hand], fill=col, width=1)


def torso_outline():
    half = [(CX + 60, 600), (CX + 150, 628), (CX + 232, 672), (CX + 280, 760), (CX + 300, 880)]
    pts = [(CX, 600)] + half + [(CX - x + CX, y) for x, y in reversed(half)][::-1][::-1]
    left = [(2 * CX - x, y) for x, y in half]
    return smooth([(CX - 60, 600)] + [(CX + 60, 600)] + half[1:] + [(CX + 300, 900), (CX - 300, 900)]
                  + list(reversed(left[1:])), 6)


def _body(d, st):
    outfit = st.outfit
    shirt = SHIRT if outfit != "waiter" else (30, 34, 50)
    stroke_line(d, [(CX, 520), (CX, 620)], 110, SKIN, ow=4)                      # neck
    poly = torso_outline()
    d.polygon(poly, fill=shirt, outline=LINE, width=5)
    if outfit != "waiter":                                                        # pinstripes clipped to torso
        mask = Image.new("L", d.img.size, 0)
        ImageDraw.Draw(mask).polygon([(x * S, y * S) for x, y in poly], fill=255)
        stripes = Image.new("RGBA", d.img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(stripes)
        for x in range(int(CX - 320), int(CX + 330), 24):
            sd.line([(x * S, 590 * S), ((x + 10) * S, 900 * S)], fill=STRIPE + (255,), width=2 * S)
        d.img.paste(stripes, (0, 0), Image.composite(stripes.getchannel("A"), Image.new("L", d.img.size, 0), mask))
        d.line(poly + [poly[0]], fill=LINE, width=5)
    d.polygon([(CX - 56, 606), (CX + 56, 606), (CX, 742)], fill=SKIN)               # open V-neck
    for sgn in (-1, 1):                                                            # collar flaps
        d.polygon([(CX + sgn * 58, 594), (CX + sgn * 140, 640), (CX + sgn * 26, 760), (CX + sgn * 6, 720)],
                  fill=shirt, outline=LINE, width=4)
    if outfit == "shirt":
        for k in range(11):                                                       # shell necklace
            t = (k - 5) / 5
            x, y = CX + t * 58, 676 - 28 * (1 - t * t)
            _ell(d, x, y, 10, 7, fill=SHELL, outline=SHELL_D, width=2)
    if outfit in ("barista", "waiter"):
        d.polygon([(CX, 700), (CX - 46, 674), (CX - 46, 726)], fill=RED, outline=LINE)
        d.polygon([(CX, 700), (CX + 46, 674), (CX + 46, 726)], fill=RED, outline=LINE)
        _ell(d, CX, 700, 11, 11, fill=RED, outline=LINE, width=2)
    if outfit == "barista":
        d.polygon([(CX - 100, 760), (CX + 100, 760), (CX + 120, 880), (CX - 120, 880)], fill=NAVY)
        d.line([(CX - 100, 760), (CX - 118, 650)], fill=NAVY, width=12)
        d.line([(CX + 100, 760), (CX + 118, 650)], fill=NAVY, width=12)


def hair_shape(sway):
    """Volume of messy dark hair (fringe edge; locks are drawn on top)."""
    top = [(CX - 158, 330), (CX - 176, 240), (CX - 160, 150), (CX - 96, 96), (CX - 10, 80), (CX + 80, 84),
           (CX + 148, 122), (CX + 178, 200), (CX + 170, 300), (CX + 158, 330)]
    fringe = [(CX + 150, 246), (CX + 100, 222), (CX + 40, 212), (CX - 20, 214), (CX - 80, 222), (CX - 130, 240),
              (CX - 154, 268)]
    return smooth(top + fringe, 6)


def _lock(d, root, tip, width, bend, col=HAIR):
    """A curved, tapering strand of hair from root to tip."""
    (x0, y0), (x1, y1) = root, tip
    mx, my = (x0 + x1) / 2 + bend, (y0 + y1) / 2
    left = smooth([(x0 - width, y0), (mx - width * 0.6, my), (x1, y1)], 6, closed=False)
    right = smooth([(x1, y1), (mx + width * 0.6, my), (x0 + width, y0)], 6, closed=False)
    d.polygon(left + right, fill=col)


def _hair_back(d, sway):
    d.polygon(smooth([(CX - 164, 360), (CX - 180, 230), (CX + 180, 230), (CX + 164, 360)], 4), fill=HAIR)


def _hair_front(d, sway):
    d.polygon(hair_shape(sway), fill=HAIR)
    # locks swept forward and to his right, falling onto the forehead (as in his photos)
    for rx, ry, tx, ty, w, bend in ((110, 200, 70, 268, 26, -10), (60, 196, 14, 280, 30, -14),
                                    (6, 196, -40, 274, 30, -12), (-50, 200, -96, 262, 28, -10),
                                    (-100, 206, -140, 280, 24, -8), (150, 210, 128, 262, 18, -6)):
        _lock(d, (CX + rx, ry), (CX + tx + sway * 0.6, ty), w, bend)
    for rx, ry, tx, ty, w, bend in ((-10, 120, -40, 34, 20, -18), (30, 110, 52, 28, 18, 14),
                                    (70, 118, 120, 60, 16, 18), (-70, 130, -128, 84, 16, -16),
                                    (6, 104, 0, 46, 14, 8)):          # messy strands sticking up
        _lock(d, (CX + rx, ry), (CX + tx + sway, ty), w, bend)
    for x0, y0, x1, y1, x2, y2 in ((-120, 160, -70, 118, -36, 168), (-6, 120, 40, 108, 62, 158),
                                   (84, 136, 118, 150, 126, 196), (20, 214, 0, 236, -18, 258)):  # wet-look shine
        d.line(smooth([(CX + x0, y0), (CX + x1, y1), (CX + x2, y2)], 6, closed=False), fill=HAIR_L, width=6)


def _face(d, st, t):
    e = st.expr
    talking = st.mouth > 0.05
    happy = e in ("grin", "smile", "wink") or talking
    for sgn in (-1, 1):                                                           # ears
        _ell(d, CX + sgn * 166, 352, 26, 42, fill=SKIN, outline=LINE, width=4)
        d.arc([CX + sgn * 166 - 12, 330, CX + sgn * 166 + 12, 372], 90 - sgn * 90, 270 - sgn * 90, fill=SKIN_D,
              width=4)
    d.polygon(face_outline(), fill=SKIN, outline=LINE, width=5)
    if happy:
        _ell(d, CX - 100, 440, 34, 20, fill=(236, 156, 132))
        _ell(d, CX + 100, 440, 34, 20, fill=(236, 156, 132))
    for fx, fy in ((-84, 404), (-70, 418), (-96, 422), (74, 406), (90, 420), (-18, 392), (16, 396), (60, 426)):
        _ell(d, CX + fx, fy, 3, 3, fill=SKIN_D)                                   # freckles

    squint = 0.5 if (e == "grin" and not talking) else (0.25 if happy else 0.0)
    lx, ly = st.look
    for side in (-1, 1):
        ex, ey = CX + side * 66, 338
        closed = 1.0 if (e == "wink" and side == 1) else st.blink
        h = 27 * (1 - squint) * (1 - closed) * (1.25 if e == "surprised" else 1.0)
        if h > 3:
            d.chord([ex - 36, ey - h, ex + 36, ey + h], 0, 360, fill=(255, 255, 255))
            ix, iy = ex + 11 * lx, ey + 5 * ly
            r = min(18, h + 1)
            _ell(d, ix, iy, r, r, fill=IRIS)
            _ell(d, ix, iy, r * 0.5, r * 0.5, fill=(22, 12, 10))
            _ell(d, ix + 6, iy - 6, 5, 5, fill=(255, 255, 255))
            _ell(d, ix - 5, iy + 6, 2.5, 2.5, fill=(255, 255, 255))
            d.arc([ex - 38, ey - h - 1, ex + 38, ey + h + 1], 185, 355, fill=LINE, width=7)    # lash line
            d.arc([ex - 36, ey - h, ex + 36, ey + h], 15, 165, fill=SKIN_D, width=2)
        else:
            d.arc([ex - 32, ey - 14, ex + 32, ey + 14], 20 if happy else 200, 160 if happy else 340, fill=LINE,
                  width=7)
        if squint:
            d.arc([ex - 36, ey + 2, ex + 36, ey + 34], 205, 335, fill=SKIN_D, width=4)
    for side in (-1, 1):                                                          # thick straight dark brows
        bx = CX + side * 66
        lift = 18 * st.brow + (12 if e == "surprised" else 0) + (16 if (e == "think" and side == 1) else 0)
        y0 = 286 - lift
        inner_drop = 8 if e == "think" and side == -1 else 0
        pts = [(bx - side * 50, y0 + 6 + inner_drop), (bx + side * 44, y0 - 2), (bx + side * 48, y0 + 12),
               (bx - side * 48, y0 + 24 + inner_drop)]
        d.polygon(smooth(pts, 4), fill=HAIR)
    d.polygon(smooth([(CX + 6, 340), (CX + 22, 410), (CX + 30, 432), (CX + 8, 420)], 5), fill=SKIN_D)   # nose side
    d.arc([CX - 30, 414, CX + 30, 448], 15, 165, fill=LINE, width=5)
    _ell(d, CX - 16, 436, 6, 3.5, fill=(150, 96, 76))
    _ell(d, CX + 16, 436, 6, 3.5, fill=(150, 96, 76))

    my = 486
    o = st.mouth
    if talking:                                    # lip-sync to his own recording (no dark slit at low levels)
        o = 0.25 + 0.75 * o
        w, h = 52 + (10 if e == "grin" else 0) - 6 * o, 12 + 44 * o
        d.chord([CX - w, my - h * 0.45, CX + w, my + h], 0, 360, fill=MOUTH_IN, outline=LINE, width=5)
        d.chord([CX - w * 0.62, my + h * 0.3, CX + w * 0.62, my + h * 0.98], 180, 360, fill=TONGUE)
        th = min(18, h * 0.42)
        d.chord([CX - w * 0.86, my - h * 0.45 + 3, CX + w * 0.86, my - h * 0.45 + 3 + th * 2.2], 180, 360, fill=TEETH)
    elif e in ("grin", "wink"):                    # his signature big toothy grin
        d.chord([CX - 92, my - 40, CX + 92, my + 62], 0, 180, fill=MOUTH_IN, outline=LINE, width=5)
        d.chord([CX - 84, my - 30, CX + 84, my + 30], 0, 180, fill=TEETH)
        d.line([(CX - 80, my + 2), (CX + 80, my + 2)], fill=TEETH, width=18)
        for k in (-40, 0, 40):
            d.line([(CX + k, my + 4), (CX + k, my + 26)], fill=(226, 222, 214), width=2)
        d.chord([CX - 40, my + 30, CX + 40, my + 60], 180, 360, fill=TONGUE)
        for sgn in (-1, 1):
            d.arc([CX + sgn * 92 - 14, my - 22, CX + sgn * 92 + 14, my + 20], 270 if sgn < 0 else 90,
                  90 if sgn < 0 else 270, fill=SKIN_D, width=4)
    elif e == "surprised":
        _ell(d, CX, my + 10, 20, 26, fill=MOUTH_IN, outline=LINE, width=5)
    elif e == "think":
        d.line(smooth([(CX - 32, my + 10), (CX, my + 4), (CX + 30, my - 6)], 4, closed=False), fill=LINE, width=6)
    else:
        d.arc([CX - 58, my - 40, CX + 58, my + 24], 25, 155, fill=LINE, width=7)


def _arms(d, st, t):
    g, ph = st.gesture, st.phase
    wob = math.sin(ph * math.pi * 4)
    if g == "wave":
        _arm(d, (CX - 230, 690), (CX - 330, 560), (CX - 318, 420), st.outfit)
        _hand(d, CX - 318, 370, -12 + 24 * wob, "open", 1.2)
    elif g == "point_up":
        _arm(d, (CX + 230, 690), (CX + 330, 580), (CX + 318, 430), st.outfit)
        _hand(d, CX + 318, 382 - 12 * abs(wob), 6, "point", 1.2)
    elif g == "ear":
        _arm(d, (CX + 230, 690), (CX + 340, 580), (CX + 268, 420), st.outfit)
        _hand(d, CX + 246, 362, -58, "open", 1.0)          # cupped behind his left ear
        for k in range(3):                                   # sound waves coming in from outside
            r = 40 + k * 26 + 8 * math.sin(t * 5)
            d.arc([CX + 440 - r, 352 - r, CX + 440 + r, 352 + r], 150, 210, fill=GOLD, width=7)
    elif g == "think":
        _arm(d, (CX + 230, 700), (CX + 210, 760), (CX + 100, 590), st.outfit)
        _hand(d, CX + 96, 560, -16, "fist", 1.0)
        stroke_line(d, [(CX + 80, 528), (CX + 70, 486)], 13, SKIN, ow=3)
    elif g == "celebrate":
        b = 16 * math.sin(ph * math.pi * 6)
        for sgn in (-1, 1):
            _arm(d, (CX + sgn * 230, 690), (CX + sgn * 330, 540 - b / 2), (CX + sgn * 300, 380 - b), st.outfit)
            _hand(d, CX + sgn * 300, 336 - b, sgn * 10, "fist", 1.15)
    elif g == "thumbs":
        _arm(d, (CX - 230, 700), (CX - 300, 800), (CX - 200, 640), st.outfit)
        _hand(d, CX - 196, 596 - 10 * wob, 0, "thumb", 1.15)


def _outfit_head(d, st):
    if st.outfit == "barista":                       # small white barista cap on the messy hair
        d.polygon(smooth([(CX - 150, 150), (CX - 120, 92), (CX + 120, 92), (CX + 150, 150)], 5),
                  fill=(255, 255, 255), outline=LINE, width=4)
        d.rounded_rectangle([CX - 164, 138, CX + 164, 168], radius=12, fill=(255, 255, 255), outline=LINE, width=4)


@lru_cache(maxsize=1024)
def _draw(st, t_q):
    img = Image.new("RGBA", (CW * S, CH * S), (0, 0, 0, 0))
    d = _D(img)
    sway = 6 * math.sin(t_q * 2.3)
    _hair_back(d, sway)
    _body(d, st)
    _face(d, st, t_q)
    _hair_front(d, sway)
    _outfit_head(d, st)
    _arms(d, st, t_q)
    return img


@lru_cache(maxsize=1024)
def _scaled(st, t_q, height):
    im = _draw(st, t_q)
    w = int(CW * height / CH)
    return im.resize((w, height), Image.LANCZOS)


def render(st, height, t=0.0):
    """Return an RGBA image of Pietro at the given height (tilt applied)."""
    q = State(round(st.mouth * 6) / 6, st.expr, round(st.blink * 2) / 2, round(st.brow * 3) / 3,
              (round(st.look[0] * 2) / 2, round(st.look[1] * 2) / 2), st.gesture, round(st.phase * 12) / 12,
              st.outfit, 0.0)
    im = _scaled(q, round((t * 2) % 6) / 2, height)
    if abs(st.tilt) > 0.3:
        im = im.rotate(st.tilt, resample=Image.BICUBIC, center=(im.width / 2, im.height * 0.8))
    return im


def animate(t, talk_level=0.0, mode="idle", speaking=False, outfit="shirt", seed=0):
    """Lively default motion: blinks, eye darts, nods, brow pops, gestures by mode.
    mode: idle | hook | listen | think | celebrate | turn | book | wave"""
    rnd = math.sin(seed * 12.9898) * 43758.5453 % 1
    talk_level = max(0.0, (talk_level - 0.22) / 0.78)      # ignore room noise and breaths
    speaking = speaking and talk_level > 0.05
    blink = 1.0 if (t + rnd * 3) % 3.1 < 0.12 else 0.0
    look = (math.sin(t * 0.9 + seed) * 0.6, 0.0) if not speaking else (0.0, 0.0)
    tilt = 3.5 * math.sin(t * 1.7 + seed) + (2.5 * talk_level if speaking else 0)
    mouth = 0.0
    if speaking:                                         # lip-sync to his own audio level, with syllable flutter
        mouth = min(1.0, talk_level * (0.75 + 0.35 * abs(math.sin(t * 17))))
    expr = {"hook": "grin", "think": "think", "celebrate": "grin", "turn": "smile", "book": "grin",
            "wave": "grin", "listen": "smile", "idle": "smile"}.get(mode, "smile")
    if speaking:
        expr = "grin" if mode in ("hook", "celebrate") else "talk"
    brow = 0.6 * talk_level if speaking else (0.8 if mode in ("hook", "celebrate") else 0.15 * math.sin(t * 1.3))
    gesture = {"hook": "wave", "think": "think", "celebrate": "celebrate", "turn": "ear", "book": "point_up",
               "wave": "wave", "thumbs": "thumbs"}.get(mode, "none")
    if mode == "listen" and not speaking and (t % 6) < 1.2:
        expr = "wink" if (t % 12) < 6 else "grin"
    return State(mouth, expr, blink, brow, look, gesture, (t % 1.5) / 1.5, outfit, tilt)


if __name__ == "__main__":
    import sys
    poses = [("smile", "none", 0), ("grin", "wave", 0), ("talk", "none", 0.5), ("talk", "none", 1.0),
             ("think", "think", 0), ("surprised", "none", 0), ("grin", "celebrate", 0), ("smile", "ear", 0),
             ("grin", "point_up", 0), ("wink", "thumbs", 0)]
    sheet = Image.new("RGB", (5 * 400, 2 * 450), CREAM)
    for k, (e, g, m) in enumerate(poses):
        outfit = "barista" if k == 3 else "shirt"
        im = render(State(mouth=m, expr=e, gesture=g, brow=0.5 if e == "surprised" else 0.0, outfit=outfit), 430)
        sheet.paste(im, (400 * (k % 5) + (400 - im.width) // 2, 450 * (k // 5) + 10), im)
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pietro.jpg", quality=92)
