"""
Carousel (1080x1350 JPEG slides) and Story (1080x1920 JPEG) renderer, same visual system as the
Reels: blue cover, cream lesson slides, Lora for Italian, Inter for English, gold stickers.

    python3 build/slides.py carousel SPEC.json OUT_DIR PREFIX     -> PREFIX-01.jpg ... PREFIX-NN.jpg
    python3 build/slides.py story    SPEC.json OUT_DIR NAME       -> NAME.jpg

Carousel SPEC: {"series": "...", "slides": [ ...slide... ]}, 4 to 8 slides. Slide kinds:
  cover   {"title", "sub"?}
  phrase  {"it", "en", "note"?, "label"?}
  compare {"label"?, "left": {"tag","it","en"}, "right": {"tag","it","en"}}
  list    {"label", "items": [{"it","en"}, ...]}        (2 to 5 items)
  quiz    {"q", "options": [...], "label"?}              (answer on the next slide)
  answer  {"text", "explain"?}
  cta     {"text"}
Story SPEC: {"q", "options": [...], "prev": {"q","answer","why"}?}   (no stickers: API Stories have none)
Every slide is checked for size, and text that would overflow raises an error instead of clipping.
"""

import json
import pathlib
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from reel_anim import (BLUE, CREAM, GOLD, HANDLE, M, NAVY, RULE, SANS, SANS_SB, SERIF, WHITE, arch, font,  # noqa: E402
                       sticker, wrap)

CW, CH = 1080, 1350
SW, SH = 1080, 1920


class Overflow(Exception):
    pass


def block(d, text, f, x, y, width, color, gap=1.22, center=False, limit=None):
    lines = wrap(d, text, f, width)
    for line in lines:
        s = " ".join(line)
        lx = x + (width - d.textlength(s, font=f)) / 2 if center else x
        d.text((lx, y), s, font=f, fill=color)
        y += int(f.size * gap)
    if limit and y > limit:
        raise Overflow(f"text overflows: {text[:40]}...")
    return y


def frame(d, idx, total, dark, w, h):
    col = CREAM if dark else NAVY
    d.text((M, h - 90), HANDLE, font=font(SANS, 30), fill=col)
    if total:
        label = f"{idx}/{total}"
        d.text((w - M - d.textlength(label, font=font(SANS, 30)), h - 90), label, font=font(SANS, 30), fill=col)


def tag(d, text, x, y, bg, fg):
    f = font(SANS_SB, 30)
    w = d.textlength(text.upper(), font=f) + 36
    d.rounded_rectangle([x, y, x + w, y + 52], radius=10, fill=bg)
    d.text((x + 18, y + 9), text.upper(), font=f, fill=fg)


def carousel_slide(s, idx, total, series):
    kind = s["kind"]
    dark = kind in ("cover", "cta")
    img = Image.new("RGB", (CW, CH), BLUE if dark else CREAM)
    d = ImageDraw.Draw(img)
    width, limit = CW - 2 * M, CH - 130
    if kind == "cover":
        tag(d, series, M, 110, CREAM, BLUE)
        arch(d, M + 60, 420, 60, 1.0, CREAM, 8)
        y = block(d, s["title"], font(SERIF, 100, 600), M, 520, width, CREAM, limit=limit)
        if s.get("sub"):
            block(d, s["sub"], font(SANS, 44), M, y + 30, width, CREAM, limit=limit)
        sticker(img, "swipe", CW - 190, CH - 220, 1.0, angle=-6)
    elif kind == "phrase":
        tag(d, s.get("label", "Say it like this"), M, 110, BLUE, CREAM)
        y = block(d, s["it"], font(SERIF, 88, 600), M, 300, width, BLUE, limit=limit)
        d.line([M, y + 30, M + 160, y + 30], fill=GOLD, width=6)
        y = block(d, s["en"], font(SANS_SB, 52), M, y + 70, width, NAVY, limit=limit)
        if s.get("note"):
            block(d, s["note"], font(SANS, 40), M, y + 50, width, NAVY, gap=1.35, limit=limit)
    elif kind == "compare":
        tag(d, s.get("label", "Compare"), M, 110, BLUE, CREAM)
        y = 260
        for side in ("left", "right"):
            c = s[side]
            d.rounded_rectangle([M, y, CW - M, y + 400], radius=28, fill=WHITE)
            tag(d, c["tag"], M + 30, y + 30, GOLD, NAVY)
            yy = block(d, c["it"], font(SERIF, 70, 600), M + 30, y + 110, width - 60, BLUE, limit=y + 390)
            block(d, c["en"], font(SANS, 40), M + 30, yy + 10, width - 60, NAVY, limit=y + 390)
            y += 440
    elif kind == "list":
        tag(d, s["label"], M, 110, BLUE, CREAM)
        y = 230
        for item in s["items"]:
            y = block(d, item["it"], font(SERIF, 64, 600), M, y, width, BLUE, limit=limit)
            y = block(d, item["en"], font(SANS, 40), M, y + 2, width, NAVY, limit=limit) + 34
    elif kind == "quiz":
        tag(d, s.get("label", "Quick quiz"), M, 110, GOLD, NAVY)
        y = block(d, s["q"], font(SERIF, 72, 600), M, 260, width, BLUE, limit=limit) + 40
        for k, opt in enumerate(s["options"]):
            d.rounded_rectangle([M, y, CW - M, y + 130], radius=24, fill=WHITE, outline=BLUE, width=3)
            d.text((M + 36, y + 34), f"{'ABCD'[k]}", font=font(SANS_SB, 50), fill=GOLD)
            d.text((M + 110, y + 32), opt, font=font(SERIF, 56, 600), fill=BLUE)
            y += 160
        if y > limit:
            raise Overflow("quiz options overflow")
        block(d, "Answer on the next slide", font(SANS, 36), M, y + 10, width, NAVY)
    elif kind == "answer":
        tag(d, "Answer", M, 110, GOLD, NAVY)
        y = block(d, s["text"], font(SERIF, 84, 600), M, 300, width, BLUE, limit=limit)
        if s.get("explain"):
            block(d, s["explain"], font(SANS, 44), M, y + 40, width, NAVY, gap=1.35, limit=limit)
    elif kind == "cta":
        arch(d, CW // 2, 470, 90, 1.0, CREAM, 9)
        y = block(d, s["text"], font(SERIF, 84, 600), M, 600, width, CREAM, center=True, limit=limit)
        block(d, "New lesson every day · native-speaker audio in the Reels", font(SANS, 34), M, y + 40, width,
              CREAM, center=True)
    else:
        raise ValueError(f"unknown slide kind {kind}")
    frame(d, idx, total, dark, CW, CH)
    return img


def story(spec):
    img = Image.new("RGB", (SW, SH), CREAM)
    d = ImageDraw.Draw(img)
    width = SW - 2 * M
    top, limit = 250, 1650                      # keep clear of the Story header and reply bar
    d.rectangle([0, 0, SW, 210], fill=BLUE)
    d.text((M, 120), "Daily Italian challenge", font=font(SANS_SB, 40), fill=CREAM)
    y = top
    if spec.get("prev"):
        p = spec["prev"]
        tag(d, "Yesterday's answer", M, y, GOLD, NAVY)
        y = block(d, f"{p['q']} Answer: {p['answer']}", font(SERIF, 52, 600), M, y + 80, width, BLUE, limit=limit)
        if p.get("why"):
            y = block(d, p["why"], font(SANS, 38), M, y + 10, width, NAVY, limit=limit)
        d.line([M, y + 40, SW - M, y + 40], fill=RULE, width=3)
        y += 90
    tag(d, "Today's question", M, y, BLUE, CREAM)
    y = block(d, spec["q"], font(SERIF, 76, 600), M, y + 90, width, BLUE, limit=limit) + 40
    for k, opt in enumerate(spec["options"]):
        d.rounded_rectangle([M, y, SW - M, y + 140], radius=26, fill=WHITE, outline=BLUE, width=3)
        d.text((M + 40, y + 38), "ABCD"[k], font=font(SANS_SB, 54), fill=GOLD)
        d.text((M + 120, y + 36), opt, font=font(SERIF, 60, 600), fill=BLUE)
        y += 170
    if y > limit:
        raise Overflow("story overflows")
    block(d, "Answer tomorrow. Follow so you don't miss it.", font(SANS, 38), M, y + 20, width, NAVY)
    d.text((M, SH - 200), HANDLE, font=font(SANS, 34), fill=NAVY)
    return img


def main(argv):
    mode, spec, out, name = argv[1], json.loads(pathlib.Path(argv[2]).read_text()), pathlib.Path(argv[3]), argv[4]
    out.mkdir(parents=True, exist_ok=True)
    if mode == "carousel":
        slides = spec["slides"]
        if not 4 <= len(slides) <= 8:
            raise SystemExit("carousel needs 4 to 8 slides")
        files = []
        for i, s in enumerate(slides, 1):
            img = carousel_slide(s, i, len(slides), spec["series"])
            assert img.size == (CW, CH)
            path = out / f"{name}-{i:02d}.jpg"
            img.save(path, quality=90)
            files.append(path.name)
        print(" ".join(files))
    elif mode == "story":
        img = story(spec)
        assert img.size == (SW, SH)
        img.save(out / f"{name}.jpg", quality=90)
        print(f"{name}.jpg")


if __name__ == "__main__":
    main(sys.argv)
