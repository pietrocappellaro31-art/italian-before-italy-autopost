"""
Cartoon Pietro, "cute big-head" style (picked by the owner on 28 Nov 2026), drawn as SVG and rasterised with
rsvg-convert. Original vector art from his photos: messy dark hair with swept locks, thick straight brows,
brown eyes, big grin, pinstriped white shirt, shell necklace. No AI image generation.

    im = pietro.render(pietro.State(mouth=0.6, expr="talk", gesture="wave", phase=0.3), height=600)
    st = pietro.animate(t, talk_level, mode, speaking, outfit, seed)

Honesty rule: the mouth only moves to Pietro's own recordings. During the AI English narration he reacts
(smiles, nods, gestures) but never lip-syncs, so the AI voice is never presented as his.
"""

import io
import math
import subprocess
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image

VB_X, VB_W, VB_H = -60, 720, 740        # viewBox
GESTURES = ("none", "wave", "point_up", "think", "ear", "celebrate", "thumbs")
EXPRS = ("smile", "grin", "talk", "surprised", "think", "wink")
LINE = "#2A1A14"
L = f'stroke="{LINE}" stroke-width="4" stroke-linejoin="round"'


@dataclass(frozen=True)
class State:
    mouth: float = 0.0
    expr: str = "smile"
    blink: float = 0.0
    brow: float = 0.0
    look: tuple = (0.0, 0.0)
    gesture: str = "none"
    phase: float = 0.0
    outfit: str = "sweater"   # owner's favourite (28 Nov): navy sweater, white collar, red bow tie
    tilt: float = 0.0


DEFS = ('<defs><pattern id="pin" width="13" height="13" patternUnits="userSpaceOnUse">'
        '<rect width="13" height="13" fill="#FBFAF6"/><rect x="6" width="2" height="13" fill="#3E5A99"/></pattern>'
        '<radialGradient id="skin" cx="0.42" cy="0.36" r="0.72"><stop offset="0" stop-color="#F3C6A0"/>'
        '<stop offset="1" stop-color="#E0A67D"/></radialGradient>'
        '<linearGradient id="hair" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3A2A22"/>'
        '<stop offset="1" stop-color="#1E1511"/></linearGradient></defs>')

HEAD_T = "translate(-90,-40) scale(1.3)"      # head drawn in a 600x720 space, enlarged (big-head style)
HAIR = ("M168,320 C150,248 160,176 206,132 C232,108 262,96 296,96 C300,80 306,66 320,56 C318,72 320,84 326,94 "
        "C346,84 366,80 388,84 C376,92 370,100 368,108 C406,122 432,150 440,188 C446,228 446,282 432,320 "
        "C430,284 422,260 410,246 C406,264 396,278 382,284 C388,264 386,248 378,238 C368,258 352,272 334,278 "
        "C342,260 342,244 336,232 C322,254 302,268 280,272 C290,254 292,240 288,228 C272,248 252,262 232,266 "
        "C242,250 244,238 240,228 C220,242 198,266 186,302 C184,308 184,314 184,320 Z")
HAIR_HI = ["M214,176 C232,146 258,128 290,122", "M322,116 C352,114 380,130 400,158",
           "M262,214 C280,196 304,190 326,196", "M354,206 C372,212 388,224 398,240"]
HEAD = ("M300,150 C392,150 436,210 436,300 C436,400 384,470 300,474 C216,470 164,400 164,300 "
        "C164,210 208,150 300,150 Z")
EAR = "M174,300 C150,292 144,330 150,352 C156,374 172,384 182,378 Z"
BROW = "M208,282 C232,272 260,270 284,276 L282,290 C258,286 234,288 212,296 Z"
SHIRT = "M128,742 C132,660 186,612 248,598 L352,598 C414,612 468,660 472,742 Z"
COLLAR = "M262,596 L218,624 L282,676 L296,650 Z"
SKIN_H = "#F0B48A"


def mirror(s):
    return f'<g transform="translate(600,0) scale(-1,1)">{s}</g>'


def eye(cx, cy, st, side):
    closed = False                                        # owner (28 Nov): eyes always open...
    if st.gesture == "celebrate":                         # ...except the joyful ^ ^ eyes when he celebrates
        return (f'<path d="M{cx - 24},{cy + 8} C{cx - 12},{cy - 16} {cx + 12},{cy - 16} {cx + 24},{cy + 8}" '
                f'fill="none" stroke="{LINE}" stroke-width="7" stroke-linecap="round"/>')
    if closed:
        return (f'<path d="M{cx - 24},{cy + 2} C{cx - 12},{cy + 14} {cx + 12},{cy + 14} {cx + 24},{cy + 2}" '
                f'fill="none" stroke="{LINE}" stroke-width="7" stroke-linecap="round"/>')
    ry = 31 * (1.15 if st.expr == "surprised" else 1.0)
    lx, ly = st.look
    ix, iy = cx + 3 + 7 * lx * side, cy + 4 + 4 * ly       # side flips because the right eye is mirrored
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="27" ry="{ry}" fill="#fff" {L}/>'
            f'<circle cx="{ix}" cy="{iy}" r="19" fill="#4A2E1C"/><circle cx="{ix}" cy="{iy}" r="9" fill="#120A06"/>'
            f'<circle cx="{ix + 8 * side * -1}" cy="{iy - 10}" r="7" fill="#fff"/>'
            f'<circle cx="{ix + 7 * side}" cy="{iy + 8}" r="3.5" fill="#fff"/>')


def mouth(st):
    o, e = st.mouth, st.expr
    if o > 0.05:                                          # talking, size from his own audio level
        h, w, top = 16 + 36 * o, 40 - 6 * o, 402
        bot, th = top + h, min(12, (16 + 36 * o) * 0.3)
        return (f'<path d="M{300 - w},{top} C{300 - w * 0.4},{top + 6} {300 + w * 0.4},{top + 6} {300 + w},{top} '
                f'C{300 + w * 0.9},{bot - 6} {300 + w * 0.4},{bot} 300,{bot} C{300 - w * 0.4},{bot} '
                f'{300 - w * 0.9},{bot - 6} {300 - w},{top} Z" fill="#8E2633" {L}/>'
                f'<path d="M{300 - w * 0.8},{top + 3} C{300 - w * 0.3},{top + 8} {300 + w * 0.3},{top + 8} '
                f'{300 + w * 0.8},{top + 3} L{300 + w * 0.72},{top + 4 + th} C{300 + w * 0.3},{top + 8 + th} '
                f'{300 - w * 0.3},{top + 8 + th} {300 - w * 0.72},{top + 4 + th} Z" fill="#fff"/>'
                f'<ellipse cx="300" cy="{bot - h * 0.22}" rx="{w * 0.5}" ry="{h * 0.18}" fill="#FF7B7F"/>')
    if e in ("grin", "wink"):
        return ('<path d="M252,398 C280,408 320,408 348,398 C344,444 322,458 300,458 C278,458 256,444 252,398 Z" '
                f'fill="#8E2633" {L}/><path d="M258,401 C284,410 316,410 342,401 L339,417 C316,423 284,423 261,417 Z" '
                'fill="#fff"/><ellipse cx="300" cy="446" rx="22" ry="8" fill="#FF7B7F"/>')
    if e == "surprised":
        return f'<ellipse cx="300" cy="418" rx="16" ry="20" fill="#8E2633" {L}/>'
    if e == "think":
        return (f'<path d="M282,416 C294,412 306,410 318,404" fill="none" stroke="{LINE}" stroke-width="5" '
                'stroke-linecap="round"/>')
    return (f'<path d="M270,404 C284,424 316,424 330,404" fill="none" stroke="{LINE}" stroke-width="6" '
            'stroke-linecap="round"/>')


def head(st):
    lift = -14 * st.brow - (8 if st.expr == "surprised" else 0)
    think = st.expr == "think"
    brow_l = f'<g transform="translate(0,{lift + (6 if think else 0)})"><path d="{BROW}" fill="#1A100B"/></g>'
    brow_r = f'<g transform="translate(0,{lift - (12 if think else 0)})"><path d="{BROW}" fill="#1A100B"/></g>'
    cap = ""
    if st.outfit == "barista":
        cap = (f'<path d="M206,124 C214,52 386,52 394,124 Z" fill="#fff" {L}/>'
               f'<rect x="196" y="114" width="208" height="24" rx="11" fill="#fff" {L}/>'
               '<rect x="196" y="122" width="208" height="7" fill="#053581"/>')
    return (f'<path d="{EAR}" fill="{SKIN_H}" {L}/>' + mirror(f'<path d="{EAR}" fill="{SKIN_H}" {L}/>') +
            f'<path d="{HEAD}" fill="url(#skin)" {L}/>'
            '<ellipse cx="226" cy="392" rx="28" ry="15" fill="#FF8A7A" opacity="0.55"/>'
            '<ellipse cx="374" cy="392" rx="28" ry="15" fill="#FF8A7A" opacity="0.55"/>'
            + "".join(f'<circle cx="{x}" cy="{y}" r="2.4" fill="#C08058" opacity="0.7"/>' for x, y in
                      ((214, 372), (228, 380), (238, 368), (362, 368), (372, 380), (386, 372))) +
            eye(246, 330, st, -1) + mirror(eye(246, 330, st, 1)) + brow_l + mirror(brow_r) +
            '<path d="M292,372 C298,380 306,380 312,372" stroke="#B8775A" stroke-width="4" fill="none" '
            'stroke-linecap="round"/>' + mouth(st) +
            f'<path d="{HAIR}" fill="url(#hair)" {L} transform="translate(0,-6)"/>'
            + "".join(f'<path d="{h}" stroke="#5C4436" stroke-width="6" fill="none" stroke-linecap="round" '
                      'transform="translate(0,-6)"/>' for h in HAIR_HI) + cap)


NAVY_OUTFITS = ("sweater", "waiter", "barista")


def body(st):
    waiter = st.outfit in NAVY_OUTFITS
    s = (f'<path d="{SHIRT}" fill="{"#2B3350" if waiter else "url(#pin)"}" {L}/>'
         '<path d="M262,598 L338,598 L300,660 Z" fill="#E7AE86"/>'
         f'<path d="{COLLAR}" fill="#fff" {L}/>' + mirror(f'<path d="{COLLAR}" fill="#fff" {L}/>'))
    if st.outfit == "shirt":                              # shell necklace
        for k in range(9):
            t = (k - 4) / 4
            s += (f'<ellipse cx="{300 + t * 34:.1f}" cy="{628 - 16 * (1 - t * t):.1f}" rx="7" ry="5" fill="#FFF4DD" '
                  'stroke="#B9A17A" stroke-width="1.5"/>')
    else:                                                 # bow tie for barista / waiter
        s += ('<path d="M300,630 L268,614 L268,646 Z M300,630 L332,614 L332,646 Z" fill="#C43E34" stroke="#2A1A14" '
              'stroke-width="3"/><circle cx="300" cy="630" r="8" fill="#C43E34" stroke="#2A1A14" stroke-width="3"/>')
    return s


def sleeve(x0, y0, x1, y1, waiter=False):
    col = "#2B3350" if waiter else "#FBFAF6"
    s = (f'<path d="M{x0},{y0} L{x1},{y1}" stroke="{LINE}" stroke-width="62" stroke-linecap="round"/>'
         f'<path d="M{x0},{y0} L{x1},{y1}" stroke="{col}" stroke-width="54" stroke-linecap="round"/>')
    if not waiter:
        n = math.hypot(x1 - x0, y1 - y0) or 1
        for k in (-2, -1, 0, 1, 2):
            ox, oy = -(y1 - y0) / n * k * 9, (x1 - x0) / n * k * 9
            s += f'<path d="M{x0 + ox:.1f},{y0 + oy:.1f} L{x1 + ox:.1f},{y1 + oy:.1f}" stroke="#3E5A99" stroke-width="2"/>'
    return s


def hand(cx, cy, ang, pose):
    """Chunky cartoon hand. pose: open | point | fist | thumb."""
    s = f'<g transform="translate({cx:.1f},{cy:.1f}) rotate({ang:.1f})">'
    fingers = {"open": [(-21, -40, -18), (-7, -48, -5), (7, -48, 5), (21, -40, 18)], "point": [(-4, -58, 0)],
               "fist": [], "thumb": []}[pose]
    for fx, fy, a in fingers:
        s += (f'<rect x="{fx - 8}" y="{fy}" width="16" height="40" rx="8" fill="{SKIN_H}" {L} '
              f'transform="rotate({a * 0.4},{fx},{fy + 40})"/>')
    s += f'<ellipse cx="0" cy="0" rx="32" ry="30" fill="{SKIN_H}" {L}/>'
    if pose == "thumb":
        s += f'<rect x="-12" y="-62" width="20" height="44" rx="10" fill="{SKIN_H}" {L}/>'
    else:
        s += f'<rect x="-46" y="-14" width="34" height="18" rx="9" fill="{SKIN_H}" {L} transform="rotate(-30,-20,-5)"/>'
    if pose in ("fist", "point", "thumb"):
        for k in range(3):
            s += (f'<path d="M-20,{-14 + k * 11} C-6,{-10 + k * 11} 6,{-10 + k * 11} 20,{-14 + k * 11}" '
                  'stroke="#C88A64" stroke-width="3" fill="none"/>')
    return s + "</g>"


def arms(st):
    g, ph, w = st.gesture, st.phase, st.outfit in NAVY_OUTFITS
    wob = math.sin(ph * math.pi * 4)
    if g == "wave":
        return sleeve(196, 650, 120, 500, w) + hand(104, 456, -10 + 22 * wob, "open")
    if g == "point_up":
        return sleeve(404, 650, 482, 506, w) + hand(492, 462 - 10 * abs(wob), 6, "point")
    if g == "think":
        return (sleeve(404, 660, 370, 610, w) + hand(352, 574, -10, "fist") +
                f'<rect x="336" y="512" width="15" height="44" rx="7.5" fill="{SKIN_H}" {L} '
                'transform="rotate(-12,343,556)"/>')
    if g == "ear":
        out = sleeve(404, 650, 488, 470, w) + hand(500, 420, -50, "open")
        for k in range(3):
            r = 30 + k * 22
            out += (f'<path d="M{590 - r * 0.5:.1f},{420 - r * 0.87:.1f} A{r},{r} 0 0 0 {590 - r * 0.5:.1f},'
                    f'{420 + r * 0.87:.1f}" stroke="#E3A93B" stroke-width="7" fill="none" stroke-linecap="round"/>')
        return out
    if g == "celebrate":
        b = 14 * math.sin(ph * math.pi * 6)
        return (sleeve(196, 650, 120, 480 - b, w) + hand(110, 436 - b, -12, "fist") +
                sleeve(404, 650, 480, 480 - b, w) + hand(490, 436 - b, 12, "fist"))
    if g == "thumbs":
        return sleeve(196, 660, 170, 600, w) + hand(160, 566 - 8 * wob, 0, "thumb")
    return ""


def svg(st, bounce=0.0):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VB_X} 0 {VB_W} {VB_H}">' + DEFS + body(st) +
            f'<g transform="translate(0,{bounce:.1f}) {HEAD_T}">{head(st)}</g>' + arms(st) + "</svg>")


@lru_cache(maxsize=2048)
def _raster(st, bounce, height):
    png = subprocess.run(["rsvg-convert", "-h", str(height), "-f", "png"], input=svg(st, bounce).encode(),
                         capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def render(st, height, t=0.0):
    q = State(round(st.mouth * 6) / 6, st.expr, 1.0 if st.blink >= 0.5 else 0.0, round(st.brow * 3) / 3,
              (round(st.look[0] * 2) / 2, round(st.look[1] * 2) / 2), st.gesture, round(st.phase * 12) / 12,
              st.outfit, 0.0)
    im = _raster(q, float(round(3 * math.sin(t * 4))), int(height))
    if abs(st.tilt) > 0.3:
        im = im.rotate(st.tilt, resample=Image.BICUBIC, center=(im.width / 2, im.height * 0.85))
    return im


def animate(t, talk_level=0.0, mode="idle", speaking=False, outfit="sweater", seed=0):
    """Lively default motion: blinks, eye darts, nods, brow pops, gestures by mode."""
    rnd = math.sin(seed * 12.9898) * 43758.5453 % 1
    talk_level = max(0.0, (talk_level - 0.22) / 0.78)      # ignore room noise and breaths
    speaking = speaking and talk_level > 0.05
    blink = 0.0                                           # no blinks: eyes stay open (owner, 28 Nov)
    look = (math.sin(t * 0.9 + seed) * 0.8, 0.0) if not speaking else (0.0, 0.0)
    tilt = 4 * math.sin(t * 1.7 + seed) + (3 * talk_level if speaking else 0)
    mouth_v = min(1.0, 0.25 + 0.75 * talk_level * (0.75 + 0.35 * abs(math.sin(t * 17)))) if speaking else 0.0
    expr = {"hook": "grin", "think": "think", "celebrate": "grin", "turn": "smile", "book": "grin",
            "wave": "grin", "listen": "smile", "idle": "smile", "thumbs": "grin"}.get(mode, "smile")
    if speaking:
        expr = "talk"
    brow = 0.7 * talk_level if speaking else (0.8 if mode in ("hook", "celebrate") else 0.2 * math.sin(t * 1.3))
    gesture = {"hook": "wave", "think": "think", "celebrate": "celebrate", "turn": "ear", "book": "point_up",
               "wave": "wave", "thumbs": "thumbs"}.get(mode, "none")
    if mode == "listen" and not speaking and t > 2.0 and 3.0 < (t % 7) < 3.6:
        expr = "grin"
    if mode == "think" and (t % 2.5) < 0.4:
        expr = "surprised"
    return State(mouth_v, expr, blink, brow, look, gesture, (t % 1.5) / 1.5, outfit, tilt)


if __name__ == "__main__":
    import sys
    poses = [("smile", "none", 0, "sweater"), ("grin", "wave", 0, "sweater"), ("talk", "none", 0.4, "sweater"),
             ("talk", "none", 1.0, "barista"), ("think", "think", 0, "sweater"), ("surprised", "none", 0, "sweater"),
             ("grin", "celebrate", 0, "sweater"), ("smile", "ear", 0, "sweater"), ("grin", "point_up", 0, "sweater"),
             ("grin", "thumbs", 0, "sweater")]
    sheet = Image.new("RGB", (5 * 420, 2 * 450), (242, 239, 230))
    for k, (e, g, m, o) in enumerate(poses):
        im = render(State(mouth=m, expr=e, gesture=g, outfit=o, brow=0.6 if e == "surprised" else 0), 430)
        sheet.paste(im, (420 * (k % 5) + (420 - im.width) // 2, 450 * (k // 5) + 10), im)
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pietro.jpg", quality=92)
