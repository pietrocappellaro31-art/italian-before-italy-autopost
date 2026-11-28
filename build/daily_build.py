"""
Build and queue one day of posts (Reel + carousel + Story) from a day spec.

    python3 build/daily_build.py DAY_SPEC.json CLIPS_DIR [--manifest posts.json]

DAY_SPEC (written by the daily scheduled session in the private repo, specs/YYYY-MM-DD.json):
{
  "date": "2026-11-23",
  "reel":     {"id_slug": "bar-dialogue", "lesson": "IBI-L0003", "beats": [...reel beats...], "caption": "..."},
  "carousel": {"id_slug": "cafe-phrases", "lesson": "IBI-L0004", "spec": {...slides spec...}, "caption": "..."},
  "story":    {"id_slug": "quiz", "lesson": "IBI-L0005", "spec": {...story spec...}}
}
Any of the three may be omitted (a gate failed). Renders into media/, writes captions to build/captions/,
lints captions, queues each post at its fixed slot (Story 07:30, Carousel 08:10, Reel 12:35 ET) and
validates the manifest. Nothing is published here: GitHub Actions publishes when the slot comes.
Exit code 0 = all requested posts queued.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
BUILD = REPO / "build"
EM_DASH = "—"


def lint_caption(text):
    problems = []
    first = text.strip().splitlines()[0] if text.strip() else ""
    if not first:
        problems.append("empty caption")
    if len(first) > 125:
        problems.append(f"first line {len(first)} chars > 125")
    tags = re.findall(r"#\w+", text)
    if len(tags) > 5:
        problems.append(f"{len(tags)} hashtags > 5")
    if any(t.lower() in ("#fyp", "#viral", "#explore") for t in tags):
        problems.append("banned hashtag")
    if EM_DASH in text:
        problems.append("em dash")
    if "​" in text or "﻿" in text:
        problems.append("invisible characters")
    if len(text) > 2200:
        problems.append("caption > 2200 chars")
    return problems


EPOCH = "2026-11-22"
CYCLE = ["blue", "white", "cream"]          # grid colour rotation, post after post (owner 26 Nov 2026)
BEAT_MOODS = ["pop", "bounce", "lofi"]      # upbeat original music, rotated by day
BOOK_VO = "Want to speak like this? Book an intro session with Pietro. Link in bio."


def house_plan(date):
    """Deterministic per-day choices: colours, music, booking ending (every 3rd Reel), booking Story (Mon/Wed/Fri)."""
    from datetime import date as D
    d = D.fromisoformat(date)
    o = (d - D.fromisoformat(EPOCH)).days
    return {"carousel": CYCLE[(2 * o) % 3], "reel": CYCLE[(2 * o + 1) % 3], "story": CYCLE[(2 * o + 2) % 3],
            "mood": BEAT_MOODS[o % 3], "book": o % 3 == 2, "promo": d.weekday() in (0, 2, 4),
            "promo_variant": ((o // 7) * 3 + {0: 0, 2: 1, 4: 2}.get(d.weekday(), 0)) % 3}


def apply_house_plan(day):
    hp = house_plan(day["date"])
    if "carousel" in day:
        day["carousel"]["spec"]["theme"] = hp["carousel"]
        for sl in day["carousel"]["spec"]["slides"]:       # cartoon Pietro is always on (owner 26-28 Nov)
            sl.pop("pietro", None)
    if "story" in day:
        day["story"]["spec"]["theme"] = hp["story"]
    if "reel" in day:
        beats = day["reel"]["beats"]
        beats[0]["theme"], beats[0]["mood"] = hp["reel"], hp["mood"]
        beats[0]["pietro"] = True                          # always on; outfit is his navy sweater by default
        for b in beats:
            b.pop("outfit", None)
        cta = beats[-1]
        if hp["book"] and cta.get("kind") == "cta":
            cta["book"], cta["vo"] = True, BOOK_VO
    return hp


def lint_graphics(day):
    """Carousel and Story graphics standard (owner 26 Nov 2026)."""
    sys.path.insert(0, str(BUILD))
    import icons
    problems = []
    if "carousel" in day:
        for i, sl in enumerate(day["carousel"]["spec"]["slides"]):
            if sl["kind"] in ("cover", "phrase", "list", "compare") and not sl.get("pics"):
                problems.append(f"carousel slide {i + 1} ({sl['kind']}) has no pics")
            for nm in sl.get("pics", []):
                if nm not in icons.ICONS:
                    problems.append(f"carousel slide {i + 1}: unknown picture '{nm}'")
    if "story" in day:
        pic = day["story"]["spec"].get("pic")
        if not pic:
            problems.append("story has no pic")
        elif pic not in icons.ICONS:
            problems.append(f"story: unknown picture '{pic}'")
    return problems


def lint_reel_standard(r):
    """House standard for every Reel (owner decisions 22 Nov 2026). Returns a list of problems."""
    sys.path.insert(0, str(BUILD))
    import icons
    import voice
    beats, problems = r["beats"], []
    if not beats or beats[0]["kind"] != "hook" or beats[-1]["kind"] != "cta":
        problems.append("Reel must start with a hook and end with a cta")
    hook = beats[0] if beats else {}
    if "Pietro" not in (hook.get("sub", "") + hook.get("vo", "")):
        problems.append("hook must name the voice: 'Pietro, a native speaker' (sub or vo)")
    if "Pietro" not in r.get("caption", ""):
        problems.append("Reel caption must say it is voiced by Pietro, a native speaker")
    for i, b in enumerate(beats):
        if b["kind"] in ("hook", "listen", "meaning", "pair") and not b.get("pics") and not b.get("art"):
            problems.append(f"beat {i} ({b['kind']}) has no pics")
        for nm in b.get("pics", []) + b.get("option_icons", []):
            if nm not in icons.ICONS:
                problems.append(f"beat {i}: unknown picture '{nm}'")
        if b.get("option_icons") and len(b["option_icons"]) != len(b.get("options", [])):
            problems.append(f"beat {i}: option_icons must match options")
        if b["kind"] in ("hook", "quiz", "turn", "cta") and not b.get("vo"):
            problems.append(f"beat {i} ({b['kind']}) has no English narration (vo)")
        if b.get("vo"):
            try:
                voice.check_english(b["vo"])
            except voice.ItalianInNarration as e:
                problems.append(f"beat {i}: {e}")
        if not b.get("particles"):
            problems.append(f"beat {i} has no particles")
    if not any(b["kind"] == "quiz" for b in beats):
        problems.append("Reel needs at least one quiz")
    if len(hook.get("title", "")) > 60:
        problems.append("hook title over 60 characters: make it punchier")
    if beats and beats[-1].get("book") and "link in bio" not in r.get("caption", "").lower():
        problems.append("booking Reel: caption must say 'Book an intro session with Pietro: link in bio'")
    return problems


def run(cmd):
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"FAILED: {' '.join(map(str, cmd))}\n{out.stdout[-800:]}\n{out.stderr[-800:]}")
    return out.stdout.strip()


def main(argv):
    spec_path, clips = pathlib.Path(argv[1]), pathlib.Path(argv[2]).resolve()
    manifest = argv[argv.index("--manifest") + 1] if "--manifest" in argv else str(REPO / "posts.json")
    day = json.loads(spec_path.read_text())
    date = day["date"]
    media, captions = REPO / "media", BUILD / "captions"
    media.mkdir(exist_ok=True)
    captions.mkdir(exist_ok=True)
    queued = []
    hp = apply_house_plan(day)
    gfx = lint_graphics(day)
    if gfx:
        raise SystemExit("Graphics standard not met:\n  " + "\n  ".join(gfx))
    print(f"house plan {date}: {hp}")

    if "story" in day:
        s = day["story"]
        name = f"{date}-s-{s['id_slug']}"
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "spec.json").write_text(json.dumps(s["spec"], ensure_ascii=False))
            run(["python3", BUILD / "slides.py", "story", pathlib.Path(tmp, "spec.json"), media, name])
        run(["python3", BUILD / "schedule.py", "--type", "story", "--id", name, "--lesson", s["lesson"], "--date", date,
             "--approval", f"AUTO-{date}", "--ai-generated", "false", "--media", f"{name}.jpg", "--manifest", manifest])
        queued.append(name)

    if "carousel" in day:
        c = day["carousel"]
        name = f"{date}-c-{c['id_slug']}"
        problems = lint_caption(c["caption"])
        if problems:
            raise SystemExit(f"caption lint ({name}): {problems}")
        cap = captions / f"{name}.clean.txt"
        cap.write_text(c["caption"].strip() + "\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "spec.json").write_text(json.dumps(c["spec"], ensure_ascii=False))
            files = run(["python3", BUILD / "slides.py", "carousel", pathlib.Path(tmp, "spec.json"), media, name]).split()
        run(["python3", BUILD / "schedule.py", "--type", "carousel", "--id", name, "--lesson", c["lesson"], "--date", date,
             "--approval", f"AUTO-{date}", "--ai-generated", "false", "--media", *files,
             "--caption", str(cap.relative_to(REPO)), "--manifest", manifest])
        queued.append(name)

    if "reel" in day:
        r = day["reel"]
        std = lint_reel_standard(r)
        if std:
            raise SystemExit("Reel standard not met:\n  " + "\n  ".join(std))
        if any(b.get("vo") for b in r["beats"]) and not (os.environ.get("KOKORO_DIR") and os.environ.get("SHERPA_DIR")):
            print("WARNING: English narrator not set up; building this Reel without narration")
            for b in r["beats"]:
                b.pop("vo", None)
        name = f"{date}-r-{r['id_slug']}"
        problems = lint_caption(r["caption"])
        if problems:
            raise SystemExit(f"caption lint ({name}): {problems}")
        cap = captions / f"{name}.clean.txt"
        cap.write_text(r["caption"].strip() + "\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "beats.json").write_text(json.dumps(r["beats"], ensure_ascii=False))
            run(["python3", BUILD / "reel_anim.py", pathlib.Path(tmp, "beats.json"), clips, pathlib.Path(tmp, "out")])
            shutil.copy(pathlib.Path(tmp, "out", "reel.mp4"), media / f"{name}.mp4")
            shutil.copy(pathlib.Path(tmp, "out", "cover.jpg"), media / f"{name}-cover.jpg")
        probe = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height:format=duration",
                     "-of", "compact=p=0", media / f"{name}.mp4"])
        if "h264" not in probe or "aac" not in probe or "width=1080" not in probe:
            raise SystemExit(f"bad reel encode: {probe}")
        run(["python3", BUILD / "schedule.py", "--type", "reel", "--id", name, "--lesson", r["lesson"], "--date", date,
             "--approval", f"AUTO-{date}", "--ai-generated",
             "true" if any(b.get("vo") for b in r["beats"]) else "false", "--media", f"{name}.mp4",
             "--cover", f"{name}-cover.jpg", "--caption", str(cap.relative_to(REPO)),
             "--audio-kind", "native_recording", "--manifest", manifest])
        queued.append(name)

    if hp["promo"] and day.get("promo", True):
        name = f"{date}-s-book"
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "spec.json").write_text(json.dumps({"variant": hp["promo_variant"], "pietro": True}))
            run(["python3", BUILD / "slides.py", "promo", pathlib.Path(tmp, "spec.json"), media, name])
        run(["python3", BUILD / "schedule.py", "--type", "story", "--id", name, "--lesson", "IBI-BOOK", "--date", date,
             "--approval", f"AUTO-{date}", "--ai-generated", "false", "--media", f"{name}.jpg", "--at", "18:30",
             "--promo", "--manifest", manifest])
        queued.append(name)

    sys.path.insert(0, str(REPO))
    import publish
    problems = publish.validate_manifest(json.loads(pathlib.Path(manifest).read_text()))
    if problems:
        raise SystemExit(f"manifest invalid after queueing: {problems}")
    print("queued:", ", ".join(queued))


if __name__ == "__main__":
    main(sys.argv)
