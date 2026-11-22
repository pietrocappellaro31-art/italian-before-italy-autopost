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

    sys.path.insert(0, str(REPO))
    import publish
    problems = publish.validate_manifest(json.loads(pathlib.Path(manifest).read_text()))
    if problems:
        raise SystemExit(f"manifest invalid after queueing: {problems}")
    print("queued:", ", ".join(queued))


if __name__ == "__main__":
    main(sys.argv)
