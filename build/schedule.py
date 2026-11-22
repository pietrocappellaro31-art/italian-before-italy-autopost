"""
Queue one approved, final asset set into posts.json.

    python3 build/schedule.py --type carousel --id 2026-12-01-c-coffee --lesson IBI-L0001 \
        --date 2026-12-01 --approval IBI-BATCH-2026W49 --ai-generated false \
        --media 2026-12-01-c-01.jpg 2026-12-01-c-02.jpg \
        --caption build/captions/2026-12-01-c.clean.txt

    Reels add:  --audio-kind native_recording --cover 2026-12-01-r-cover.jpg
    Stories:    no --caption; optional --requires 2026-11-30-s-quiz

Rules enforced here (see docs/publishing-runbook.md):
  * the slot time comes from SLOTS_ET for the format; UTC is computed per date with zoneinfo (DST-safe)
  * every media file must already be in media/; its sha256 is recorded, as is the caption's
  * one entry per format per Eastern day; ids are never reused
  * a published or in-flight entry is never replaced
Use --manifest to point at a draft manifest while testing.
"""

import argparse
import hashlib
import json
import pathlib
import sys
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
REPO = pathlib.Path(__file__).resolve().parent.parent
SLOTS_ET = {"story": time(7, 30), "carousel": time(8, 10), "reel": time(12, 35)}   # owner-approved hypotheses


def slot_utc(day, kind):
    local = datetime.combine(day, SLOTS_ET[kind], EASTERN)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True, choices=sorted(SLOTS_ET))
    ap.add_argument("--id", required=True)
    ap.add_argument("--lesson", required=True)
    ap.add_argument("--date", required=True, help="Eastern calendar date, YYYY-MM-DD")
    ap.add_argument("--approval", required=True)
    ap.add_argument("--ai-generated", required=True, choices=("true", "false"))
    ap.add_argument("--media", nargs="+", required=True)
    ap.add_argument("--caption")
    ap.add_argument("--cover")
    ap.add_argument("--audio-kind", default="none")
    ap.add_argument("--requires")
    ap.add_argument("--at", help="HH:MM Eastern, overrides the format's slot (owner-approved only)")
    ap.add_argument("--cap-exempt", help="reason, e.g. 'owner approved 2 Reels on 22 Nov in chat'")
    ap.add_argument("--manifest", default=str(REPO / "posts.json"))
    a = ap.parse_args(argv)

    manifest_path = pathlib.Path(a.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    day = date.fromisoformat(a.date)
    if a.at:
        hh, mm = map(int, a.at.split(":"))
        scheduled = datetime.combine(day, time(hh, mm), EASTERN).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        scheduled = slot_utc(day, a.type)

    for post in manifest["posts"]:
        if post["id"] == a.id:
            sys.exit(f"id {a.id} already exists (status {post['status']}); ids are never reused")
        same_day = datetime.fromisoformat(post["scheduled_utc"].replace("Z", "+00:00")).astimezone(EASTERN).date()
        if post["type"] == a.type and same_day == day and post["status"] not in ("missed", "rejected") and not a.cap_exempt:
            sys.exit(f"{a.type} already planned for {day}: {post['id']}")

    hashes = {}
    for name in a.media + ([a.cover] if a.cover else []):
        path = REPO / "media" / name
        if not path.is_file() or path.stat().st_size == 0:
            sys.exit(f"missing or empty media/{name}")
        hashes[name] = sha(path)
    if a.type == "story" and a.caption:
        sys.exit("stories take no caption")
    if a.caption:
        cap = REPO / a.caption
        hashes["caption"] = hashlib.sha256(cap.read_text(encoding="utf-8").strip().encode()).hexdigest()

    entry = {
        "id": a.id, "lesson_id": a.lesson, "type": a.type, "scheduled_utc": scheduled,
        "media": a.media, "caption_file": a.caption, "cover": a.cover,
        "audio_kind": a.audio_kind if a.type == "reel" else "none",
        "ai_generated": a.ai_generated == "true", "approval_id": a.approval,
        "asset_hashes": hashes, "requires_published": a.requires,
        "cap_exempt": a.cap_exempt, "status": "approved", "container_id": None, "published_id": None,
        "published_at_utc": None, "attempts": 0, "last_error": None,
    }
    manifest["posts"].append(entry)
    manifest["posts"].sort(key=lambda p: p["scheduled_utc"])
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"queued {a.id} for {day} = {scheduled}")


if __name__ == "__main__":
    main()
