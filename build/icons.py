"""
Flat vector illustrations for Reels, drawn with PIL in the brand palette (original art, no external images).

    paste_icon(img, "train", cx, cy, size, p, t)   # p = pop-in progress 0..1, t = seconds (gentle bob)
    avatar(img, "barista", cx, cy, size, p, t, talking)

Icons: see ICONS. Avatars: barista, you, friend, waiter, clerk, pharmacist.
"""

import math
from functools import lru_cache

from PIL import Image, ImageDraw

BLUE, NAVY, CREAM, GOLD = (5, 53, 129), (11, 33, 75), (242, 239, 230), (227, 169, 59)
WHITE, RED, GREEN, BROWN = (255, 255, 255), (196, 62, 52), (46, 140, 90), (120, 72, 38)
LIGHT, SKIN, TAN = (160, 185, 225), (238, 196, 160), (214, 160, 90)
S = 4  # supersampling; icons are designed on a 240 x 240 grid


def _c(v):
    return [tuple(y * S for y in x) if isinstance(x, tuple) else x * S for x in v]


def _draw(fn):
    im = Image.new("RGBA", (240 * S, 240 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    class P:  # proxy that scales design coordinates
        def __getattr__(self, name):
            f = getattr(d, name)

            def g(xy, *a, **k):
                if "width" in k:
                    k["width"] = int(k["width"] * S)
                if "radius" in k:
                    k["radius"] = k["radius"] * S
                if name == "text":
                    return f([xy[0] * S, xy[1] * S], *a, **k)
                return f(_c(xy), *a, **k)
            return g
    fn(P())
    return im


def i_coffee(d):
    d.ellipse([30, 178, 210, 206], fill=WHITE, outline=NAVY, width=5)
    d.rounded_rectangle([60, 100, 170, 190], radius=22, fill=WHITE, outline=NAVY, width=6)
    d.arc([150, 118, 200, 166], -90, 90, fill=NAVY, width=7)
    d.rectangle([66, 106, 164, 122], fill=BROWN)
    for x in (85, 115, 145):
        d.arc([x - 12, 40, x + 12, 70], 90, 270, fill=LIGHT, width=5)
        d.arc([x - 12, 66, x + 12, 96], 270, 90, fill=LIGHT, width=5)


def i_croissant(d):
    segs = [(-70, 18), (-42, 26), (0, 34), (42, 26), (70, 18)]
    for dx, r in segs:
        cy = 135 + abs(dx) * 0.55
        d.ellipse([120 + dx * 1.15 - r * 1.3, cy - r * 1.4, 120 + dx * 1.15 + r * 1.3, cy + r * 1.4], fill=TAN,
                  outline=BROWN, width=5)


def i_train(d):
    d.rounded_rectangle([40, 40, 200, 180], radius=30, fill=BLUE)
    d.rounded_rectangle([60, 60, 180, 110], radius=10, fill=LIGHT)
    d.rectangle([40, 130, 200, 140], fill=GOLD)
    d.ellipse([60, 148, 84, 172], fill=CREAM)
    d.ellipse([156, 148, 180, 172], fill=CREAM)
    d.line([70, 180, 40, 220], fill=NAVY, width=8)
    d.line([170, 180, 200, 220], fill=NAVY, width=8)
    d.line([20, 220, 220, 220], fill=NAVY, width=6)


def i_ticket(d):
    d.rounded_rectangle([20, 70, 220, 170], radius=14, fill=GOLD)
    d.ellipse([8, 104, 40, 136], fill=(0, 0, 0, 0))
    for y in range(80, 165, 14):
        d.line([160, y, 160, y + 7], fill=NAVY, width=4)
    d.rectangle([40, 94, 140, 104], fill=NAVY)
    d.rectangle([40, 118, 120, 126], fill=NAVY)
    d.rectangle([40, 138, 130, 146], fill=NAVY)


def i_pin(d):
    d.pieslice([50, 20, 190, 160], 150, 390, fill=RED)
    d.polygon([(60, 115), (180, 115), (120, 220)], fill=RED)
    d.ellipse([94, 56, 146, 108], fill=CREAM)


def i_pharmacy(d):
    d.rounded_rectangle([30, 30, 210, 210], radius=30, fill=WHITE, outline=NAVY, width=5)
    d.rectangle([95, 50, 145, 190], fill=GREEN)
    d.rectangle([50, 95, 190, 145], fill=GREEN)


def i_clock(d):
    d.ellipse([25, 25, 215, 215], fill=WHITE, outline=BLUE, width=12)
    for k in range(12):
        a = k * math.pi / 6
        d.line([120 + 78 * math.cos(a), 120 + 78 * math.sin(a), 120 + 88 * math.cos(a), 120 + 88 * math.sin(a)],
               fill=NAVY, width=5)
    d.line([120, 120, 120, 62], fill=NAVY, width=9)
    d.line([120, 120, 165, 140], fill=GOLD, width=9)
    d.ellipse([110, 110, 130, 130], fill=NAVY)


def i_cinema(d):
    d.polygon([(55, 90), (185, 90), (170, 220), (70, 220)], fill=WHITE, outline=RED)
    for x in (80, 120, 160):
        d.rectangle([x - 8, 92, x + 8, 218], fill=RED)
    for x, y in ((70, 70), (105, 55), (140, 60), (172, 75), (90, 40), (128, 35)):
        d.ellipse([x - 22, y - 20, x + 22, y + 20], fill=(250, 236, 190))


def i_plate(d):
    d.ellipse([50, 50, 190, 190], fill=WHITE, outline=NAVY, width=5)
    d.ellipse([80, 80, 160, 160], outline=LIGHT, width=4)
    d.rounded_rectangle([18, 50, 30, 200], radius=6, fill=NAVY)
    for x in (12, 24, 36):
        d.line([x, 40, x, 90], fill=NAVY, width=5)
    d.pieslice([200, 40, 236, 140], 270, 90, fill=NAVY)
    d.rounded_rectangle([206, 90, 220, 200], radius=6, fill=NAVY)


def i_bill(d):
    d.polygon([(55, 20), (185, 20), (185, 210), (170, 222), (155, 210), (140, 222), (125, 210), (110, 222),
               (95, 210), (80, 222), (70, 210), (55, 222)], fill=WHITE, outline=NAVY)
    for y in (55, 85, 115, 145):
        d.rectangle([75, y, 140, y + 8], fill=LIGHT)
        d.rectangle([150, y, 168, y + 8], fill=NAVY)
    d.rectangle([75, 178, 168, 188], fill=GOLD)


def i_card(d):
    d.rounded_rectangle([20, 55, 220, 185], radius=18, fill=BLUE)
    d.rectangle([20, 80, 220, 105], fill=NAVY)
    d.rounded_rectangle([40, 125, 80, 155], radius=6, fill=GOLD)
    d.rectangle([100, 140, 200, 150], fill=LIGHT)


def i_tree(d):
    for k, (w, y) in enumerate(((60, 40), (85, 85), (105, 130))):
        d.polygon([(120, y), (120 - w, y + 70), (120 + w, y + 70)], fill=GREEN)
    d.rectangle([105, 200, 135, 228], fill=BROWN)
    star(d, 120, 36, 22, GOLD)
    for x, y, c in ((95, 105, RED), (145, 120, GOLD), (80, 165, GOLD), (150, 170, RED), (118, 150, CREAM)):
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=c)


def star(d, cx, cy, r, c):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=c)


def i_star(d):
    star(d, 120, 125, 100, GOLD)


def i_gift(d):
    d.rectangle([40, 100, 200, 215], fill=RED)
    d.rectangle([30, 75, 210, 105], fill=(220, 80, 70))
    d.rectangle([108, 75, 132, 215], fill=GOLD)
    d.ellipse([70, 40, 120, 85], outline=GOLD, width=10)
    d.ellipse([120, 40, 170, 85], outline=GOLD, width=10)


def i_panettone(d):
    d.chord([40, 30, 200, 150], 180, 360, fill=(170, 105, 45))
    d.rectangle([40, 90, 200, 210], fill=(250, 214, 120))
    d.rectangle([36, 120, 204, 210], fill=(250, 236, 200), outline=GOLD, width=5)
    for x, y in ((70, 110), (100, 95), (140, 105), (170, 98)):
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(150, 60, 50))


def i_pandoro(d):
    star(d, 120, 135, 105, (240, 200, 110))
    star(d, 120, 135, 62, (250, 226, 160))
    for x, y in ((90, 60), (150, 80), (110, 170), (160, 160), (75, 140)):
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=WHITE)


def i_fireworks(d):
    for cx, cy, r, c in ((85, 90, 60, GOLD), (165, 130, 50, RED), (110, 175, 35, LIGHT)):
        for k in range(12):
            a = k * math.pi / 6
            d.line([cx + r * 0.35 * math.cos(a), cy + r * 0.35 * math.sin(a), cx + r * math.cos(a),
                    cy + r * math.sin(a)], fill=c, width=6)


def i_toast(d):
    for x, ang in ((85, -12), (155, 12)):
        d.polygon([(x - 28, 40), (x + 28, 40), (x + 18, 120), (x - 18, 120)], fill=(250, 226, 150), outline=NAVY)
        d.line([x, 120, x, 190], fill=NAVY, width=6)
        d.line([x - 26, 192, x + 26, 192], fill=NAVY, width=6)
    for x, y in ((120, 30), (105, 15), (138, 18)):
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=GOLD)


def i_calendar(d):
    d.rounded_rectangle([30, 45, 210, 215], radius=16, fill=WHITE, outline=NAVY, width=5)
    d.rectangle([32, 47, 208, 90], fill=RED)
    for x in (75, 165):
        d.rounded_rectangle([x - 8, 25, x + 8, 65], radius=6, fill=NAVY)
    for r in range(3):
        for c in range(4):
            d.rectangle([52 + c * 40, 108 + r * 34, 76 + c * 40, 128 + r * 34], fill=LIGHT if (r, c) != (1, 2) else GOLD)


def i_phone(d):
    d.rounded_rectangle([70, 20, 170, 220], radius=20, fill=NAVY)
    d.rectangle([80, 45, 160, 185], fill=LIGHT)
    d.ellipse([110, 194, 130, 212], fill=CREAM)


def i_bubble(d):
    d.rounded_rectangle([20, 30, 220, 160], radius=40, fill=WHITE, outline=BLUE, width=6)
    d.polygon([(60, 155), (100, 155), (50, 210)], fill=WHITE, outline=BLUE)
    d.line([62, 154, 98, 154], fill=WHITE, width=10)
    for x in (80, 120, 160):
        d.ellipse([x - 12, 83, x + 12, 107], fill=BLUE)


def i_question(d):
    d.ellipse([20, 20, 220, 220], fill=GOLD)
    d.arc([75, 50, 165, 140], 180, 60, fill=NAVY, width=20)
    d.line([142, 128, 120, 150, 120, 162], fill=NAVY, width=20)
    d.ellipse([108, 172, 132, 196], fill=NAVY)


def i_wave_hand(d):
    d.rounded_rectangle([70, 90, 170, 215], radius=40, fill=SKIN)
    for k, h in enumerate((70, 50, 55, 75)):
        x = 75 + k * 24
        d.rounded_rectangle([x, h, x + 22, 140], radius=11, fill=SKIN)
    d.rounded_rectangle([40, 130, 95, 158], radius=13, fill=SKIN)
    for k in range(3):
        d.arc([150 + k * 14, 50 - k * 6, 200 + k * 14, 110 - k * 6], -60, 20, fill=BLUE, width=6)


def i_arrows(d):
    d.line([120, 220, 120, 110], fill=BLUE, width=18)
    d.polygon([(120, 30), (80, 90), (160, 90)], fill=BLUE)
    d.line([110, 150, 40, 150], fill=GOLD, width=16)
    d.polygon([(10, 150), (50, 120), (50, 180)], fill=GOLD)
    d.line([130, 150, 200, 150], fill=RED, width=16)
    d.polygon([(232, 150), (190, 120), (190, 180)], fill=RED)


def i_station(d):
    d.polygon([(20, 90), (120, 30), (220, 90)], fill=BLUE)
    d.rectangle([35, 90, 205, 210], fill=CREAM, outline=NAVY, width=5)
    for x in (60, 105, 150):
        d.rounded_rectangle([x, 120, x + 30, 210], radius=14, fill=LIGHT)
    d.ellipse([105, 48, 135, 78], fill=WHITE, outline=NAVY, width=3)
    d.rectangle([20, 210, 220, 222], fill=NAVY)


def i_moon(d):
    d.ellipse([40, 30, 200, 190], fill=GOLD)
    d.ellipse([85, 15, 235, 165], fill=(0, 0, 0, 0))
    for x, y in ((190, 190), (60, 210), (210, 60)):
        star(d, x, y, 14, CREAM)


def i_bowl(d):  # lentils
    d.chord([30, 50, 210, 210], 0, 180, fill=WHITE, outline=NAVY, width=5)
    d.ellipse([40, 110, 200, 150], fill=BROWN)
    for x, y in ((70, 125), (100, 118), (130, 130), (160, 122), (90, 138), (150, 140)):
        d.ellipse([x - 7, y - 5, x + 7, y + 5], fill=TAN)


def i_wine(d):
    d.chord([65, 20, 175, 140], 0, 180, fill=(150, 30, 60))
    d.arc([65, 20, 175, 140], 180, 360, fill=NAVY, width=4)
    d.line([65, 80, 65, 80], fill=NAVY)
    d.line([120, 140, 120, 205], fill=NAVY, width=6)
    d.line([85, 208, 155, 208], fill=NAVY, width=7)


def i_water(d):
    d.rounded_rectangle([85, 60, 155, 220], radius=20, fill=LIGHT, outline=BLUE, width=5)
    d.rectangle([100, 25, 140, 60], fill=BLUE)
    d.rectangle([85, 120, 155, 160], fill=WHITE)


def i_heart(d):
    d.ellipse([30, 50, 125, 145], fill=RED)
    d.ellipse([115, 50, 210, 145], fill=RED)
    d.polygon([(37, 118), (203, 118), (120, 215)], fill=RED)


def i_ear(d):  # headphones = listen
    d.arc([40, 30, 200, 190], 180, 360, fill=NAVY, width=16)
    d.rounded_rectangle([28, 110, 78, 200], radius=18, fill=BLUE)
    d.rounded_rectangle([162, 110, 212, 200], radius=18, fill=BLUE)


def i_mouth(d):  # say it out loud
    d.ellipse([30, 60, 170, 200], fill=SKIN)
    d.chord([70, 120, 140, 170], 0, 180, fill=NAVY)
    for k in range(3):
        d.arc([150 + k * 14 - 30, 70 - k * 10, 190 + k * 14, 190 + k * 10], -50, 50, fill=GOLD, width=7)


ICONS = {k[2:]: v for k, v in globals().items() if k.startswith("i_")}


def avatar_draw(kind, talking):
    def fn(d):
        shirt = {"barista": NAVY, "waiter": NAVY, "you": GOLD, "friend": RED, "clerk": BLUE,
                 "pharmacist": WHITE}.get(kind, BLUE)
        d.pieslice([30, 140, 210, 320], 180, 360, fill=shirt, outline=NAVY if shirt == WHITE else None, width=4)
        if kind in ("barista", "waiter"):
            d.polygon([(95, 160), (145, 160), (150, 230), (90, 230)], fill=WHITE)
            d.polygon([(105, 150), (120, 162), (135, 150), (135, 170), (120, 162), (105, 170)], fill=RED)
        if kind == "pharmacist":
            d.rectangle([140, 185, 170, 192], fill=GREEN)
            d.rectangle([151, 174, 159, 203], fill=GREEN)
        d.ellipse([70, 40, 170, 140], fill=SKIN)
        hair = {"you": BROWN, "friend": NAVY}.get(kind, (60, 40, 30))
        d.chord([66, 34, 174, 120], 180, 360, fill=hair)
        if kind == "barista":
            d.rounded_rectangle([72, 30, 168, 62], radius=12, fill=WHITE)
        d.ellipse([96, 84, 106, 96], fill=NAVY)
        d.ellipse([134, 84, 144, 96], fill=NAVY)
        if talking:
            d.ellipse([108, 106, 132, 128], fill=NAVY)
        else:
            d.arc([104, 100, 136, 122], 20, 160, fill=NAVY, width=4)
    return fn


@lru_cache(maxsize=256)
def _base(name, size, talking=None):
    fn = avatar_draw(name, talking) if talking is not None else ICONS[name]
    return _draw(fn).resize((size, size), Image.LANCZOS)


def _place(img, im, cx, cy, p, t, bob, wiggle):
    p = max(0.0, min(1.0, p))
    if p <= 0:
        return
    s = 1 + 0.25 * math.sin(math.pi * p) if p < 1 else 1  # overshoot pop
    s *= min(1, p * 2)
    w = max(1, int(im.width * s))
    im2 = im.resize((w, w), Image.LANCZOS) if w != im.width else im
    if wiggle:
        im2 = im2.rotate(4 * math.sin(t * 5), resample=Image.BICUBIC)
    dy = bob * math.sin(t * 2.4 + cx * 0.01)
    img.paste(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2 + dy)), im2)


def paste_icon(img, name, cx, cy, size, p, t, bob=10, wiggle=False):
    if name not in ICONS:
        raise KeyError(f"unknown icon '{name}'; choose from {sorted(ICONS)}")
    _place(img, _base(name, size), cx, cy, p, t, bob, wiggle)


def avatar(img, kind, cx, cy, size, p, t, talking=False):
    _place(img, _base(kind, size, bool(talking)), cx, cy, p, t, 4, False)


if __name__ == "__main__":  # preview sheet
    import sys
    names = sorted(ICONS)
    cols = 8
    sheet = Image.new("RGB", (cols * 200, (len(names) // cols + 2) * 200), CREAM)
    for k, n in enumerate(names):
        paste_icon(sheet, n, 100 + (k % cols) * 200, 100 + (k // cols) * 200, 170, 1, 0, bob=0)
    for k, a in enumerate(("barista", "you", "friend", "waiter", "clerk", "pharmacist")):
        avatar(sheet, a, 100 + k * 200, 100 + (len(names) // cols + 1) * 200, 180, 1, 0, talking=k % 2)
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "/tmp/icons.jpg")
