"""
Deterministic native-audio Reel renderer (1080x1920, H.264 + AAC, 30 fps).

    python3 build/reel.py BEATS.json CLIPS_DIR OUT_DIR

BEATS.json describes the Reel as a list of beats. Each beat is one still frame held for
  (clip duration, measured with ffprobe) + "hold" seconds, or "seconds" when it has no clip.
Beat kinds:
  hook     {"kind":"hook","title":..., "series":...}
  phrase   {"kind":"phrase","it":..., "en":(optional), "note":(optional), "label":(optional), "clip":ID, "hold":s}
  turn     {"kind":"turn","it":..., "seconds":s}            learner repeats in silence
  cta      {"kind":"cta","text":..., "seconds":s}
The audio track is the owner's approved clips placed exactly at their beats, silence elsewhere,
then loudness-normalised (two-pass loudnorm, -16 LUFS, -1.5 dBTP). Voice is never pitch-shifted,
stretched or synthesised. Writes reel.mp4, cover.jpg, frames contact sheet and timeline.json.
"""

import json
import pathlib
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BLUE, CREAM, NAVY, RULE = (5, 53, 129), (242, 239, 230), (11, 33, 75), (201, 196, 181)
SERIF = "/usr/share/fonts/truetype/google-fonts/Lora-Variable.ttf"
SANS = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
SANS_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
HANDLE = "@italianbeforeitaly"
CREDIT = "Italian pronunciation: original native-speaker recording"
SAFE_TOP, SAFE_BOTTOM, MARGIN = 260, 1480, 96     # clear of Reels UI overlays


def serif(size, weight=500):
    font = ImageFont.truetype(SERIF, size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:
        pass
    return font


def wrap(draw, text, font, width):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def block(draw, text, font, y, fill, width=W - 2 * MARGIN, gap=1.22, center=False):
    for line in wrap(draw, text, font, width):
        x = (W - draw.textlength(line, font=font)) / 2 if center else MARGIN
        draw.text((x, y), line, font=font, fill=fill)
        y += int(font.size * gap)
    return y


def arch(draw, x, y, w, color, thick=6):
    draw.arc([x, y, x + w, y + w], 180, 360, fill=color, width=thick)
    draw.line([x + thick // 2, y + w // 2, x + thick // 2, y + w // 2 + w // 3], fill=color, width=thick)
    draw.line([x + w - thick // 2, y + w // 2, x + w - thick // 2, y + w // 2 + w // 3], fill=color, width=thick)


def footer(draw, color):
    f = ImageFont.truetype(SANS, 34)
    draw.text((MARGIN, SAFE_BOTTOM + 40), HANDLE, font=f, fill=color)


def frame(beat):
    kind = beat["kind"]
    bg, fg = (BLUE, CREAM) if kind in ("hook", "cta") else (CREAM, BLUE)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    if kind == "hook":
        tag = ImageFont.truetype(SANS_MED, 36)
        d.rounded_rectangle([MARGIN, SAFE_TOP, MARGIN + d.textlength(beat["series"], font=tag) + 40, SAFE_TOP + 64],
                            radius=10, fill=CREAM)
        d.text((MARGIN + 20, SAFE_TOP + 10), beat["series"], font=tag, fill=BLUE)
        arch(d, MARGIN, 700, 120, CREAM)
        y = block(d, beat["title"], serif(104, 600), 860, CREAM)
        if beat.get("sub"):
            block(d, beat["sub"], ImageFont.truetype(SANS, 46), y + 30, CREAM)
    elif kind in ("phrase", "turn"):
        lab = ImageFont.truetype(SANS_MED, 38)
        label = beat.get("label") or ("Your turn: say it out loud" if kind == "turn" else "Listen")
        d.text((MARGIN, SAFE_TOP), label, font=lab, fill=BLUE)
        d.line([MARGIN, SAFE_TOP + 70, W - MARGIN, SAFE_TOP + 70], fill=RULE, width=3)
        y = block(d, beat["it"], serif(96, 600), 620, BLUE)
        if beat.get("en"):
            y = block(d, beat["en"], ImageFont.truetype(SANS, 50), y + 40, NAVY)
        if beat.get("note"):
            d.line([MARGIN, y + 50, MARGIN + 160, y + 50], fill=RULE, width=4)
            block(d, beat["note"], ImageFont.truetype(SANS, 40), y + 90, NAVY, gap=1.35)
    elif kind == "cta":
        arch(d, (W - 120) // 2, 640, 120, CREAM)
        y = block(d, beat["text"], serif(92, 600), 820, CREAM, center=True)
        block(d, CREDIT, ImageFont.truetype(SANS, 32), y + 80, CREAM, center=True, width=W - 2 * MARGIN - 80)
    footer(d, fg)
    return img


def clip_seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout)


def loudnorm_args(src):
    first = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af",
                            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    m = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    return (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def main(argv):
    beats = json.loads(pathlib.Path(argv[1]).read_text())
    clips, out = pathlib.Path(argv[2]), pathlib.Path(argv[3])
    (out / "frames").mkdir(parents=True, exist_ok=True)
    timeline, t, inputs, delays = [], 0.0, [], []
    for i, beat in enumerate(beats):
        lead = 0.25 if beat.get("clip") else 0.0
        if beat.get("clip"):
            path = clips / f"{beat['clip']}.wav"
            dur = lead + clip_seconds(path) + beat.get("hold", 1.0)
            inputs.append(path)
            delays.append(int((t + lead) * 1000))
        else:
            dur = beat["seconds"]
        img = frame(beat)
        fpath = out / "frames" / f"{i:02d}.png"
        img.save(fpath)
        timeline.append({"beat": i, "kind": beat["kind"], "start": round(t, 3), "seconds": round(dur, 3),
                         "clip": beat.get("clip"), "frame": fpath.name})
        t += dur
    total = round(t, 3)
    # video: concat stills with exact durations
    listing = out / "frames.txt"
    listing.write_text("".join(f"file 'frames/{x['frame']}'\nduration {x['seconds']}\n" for x in timeline)
                       + f"file 'frames/{timeline[-1]['frame']}'\n")
    # audio: each clip delayed to its beat, mixed over silence
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=48000:cl=mono"]
    for p in inputs:
        cmd += ["-i", str(p)]
    chains = [f"[{k + 1}:a]adelay={ms}|{ms}[a{k}]" for k, ms in enumerate(delays)]
    mix = "".join(f"[a{k}]" for k in range(len(inputs)))
    chains.append(f"[0:a]{mix}amix=inputs={len(inputs) + 1}:normalize=0:duration=first[m]")
    raw_audio = out / "audio_raw.wav"
    subprocess.run(cmd + ["-filter_complex", ";".join(chains), "-map", "[m]", "-c:a", "pcm_s16le", str(raw_audio)],
                   check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(raw_audio),
                    "-af", loudnorm_args(raw_audio) + ",aresample=48000", "-vf", "fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-profile:v", "high",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", str(total),
                    "-movflags", "+faststart", str(out / "reel.mp4")], check=True)
    frame(beats[0]).save(out / "cover.jpg", quality=92)
    sheet = Image.new("RGB", (270 * min(len(timeline), 6), 480 * ((len(timeline) + 5) // 6)), "white")
    for i, x in enumerate(timeline):
        sheet.paste(Image.open(out / "frames" / x["frame"]).resize((270, 480)), (270 * (i % 6), 480 * (i // 6)))
    sheet.save(out / "contact-sheet.jpg", quality=88)
    (out / "timeline.json").write_text(json.dumps({"total_seconds": total, "beats": timeline}, indent=1))
    print(f"reel.mp4 {total:.1f}s, {len(timeline)} beats")


if __name__ == "__main__":
    main(sys.argv)
