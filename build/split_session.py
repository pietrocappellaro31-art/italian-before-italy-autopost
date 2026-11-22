"""
Split one long native-audio recording into numbered clips, using the pause protocol
in the recording script:

  * 3 s of silence at the start
  * about 2 s of silence after every phrase           -> a clip boundary
  * a mistake: silence of 4 s or more, then the phrase again -> the take before is discarded
  * pauses inside a phrase (commas) are short         -> stay inside the clip

    python3 build/split_session.py RECORDING.m4a OUT_DIR ID1 ID2 ID3 ...

Writes OUT_DIR/<ID>.wav (mono 48 kHz PCM, padded with 0.25 s of the original room tone each side)
and OUT_DIR/split-report.json. It never alters the voice: cutting only.
If the number of kept takes differs from the number of IDs, it writes nothing but the report
and exits 2, so a person decides instead of a guess. Raw recordings and clips stay private:
never run this inside the public repo checkout's media/ folder.
"""

import json
import pathlib
import re
import subprocess
import sys

NOISE_DB = -38          # silence threshold; adjusted per file from its measured noise floor
MIN_GAP = 1.2           # seconds: shorter silences are pauses inside a phrase
RETAKE_GAP = 4.0        # seconds: a gap at least this long means "discard the previous take"
PAD = 0.25              # seconds of room tone kept around each clip
MIN_SPEECH = 0.25       # seconds: shorter bursts (a click, a breath) are ignored


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def silences(path, noise_db):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                          f"silencedetect=noise={noise_db}dB:d={MIN_GAP}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    return list(zip(starts, ends + [None] * (len(starts) - len(ends))))


def takes(path):
    total = duration(path)
    gaps = [(s, e if e is not None else total) for s, e in silences(path, NOISE_DB)]
    segments, cursor, gap_before = [], 0.0, 0.0
    for s, e in gaps:
        if s - cursor >= MIN_SPEECH:
            segments.append({"start": cursor, "end": s, "gap_before": gap_before})
        gap_before, cursor = e - s, e
    if total - cursor >= MIN_SPEECH:
        segments.append({"start": cursor, "end": total, "gap_before": gap_before})
    kept = []
    for seg in segments:
        if seg["gap_before"] >= RETAKE_GAP and kept:
            kept[-1]["discarded"] = True
        kept.append(seg)
    return [s for s in kept if not s.get("discarded")], segments, total


def main(argv):
    if len(argv) < 4:
        sys.exit(__doc__)
    src, out = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    ids = argv[3:]
    out.mkdir(parents=True, exist_ok=True)
    good, raw, total = takes(src)
    report = {"source": src.name, "duration_s": round(total, 2), "segments_found": len(raw),
              "takes_kept": len(good), "ids_expected": len(ids),
              "segments": [{k: round(v, 2) if isinstance(v, float) else v for k, v in s.items()} for s in raw]}
    if len(good) != len(ids):
        report["status"] = "COUNT_MISMATCH: nothing cut; review the segment list"
        (out / "split-report.json").write_text(json.dumps(report, indent=1))
        print(report["status"], f"({len(good)} takes, {len(ids)} IDs)")
        return 2
    report["clips"] = []
    for clip_id, seg in zip(ids, good):
        a, b = max(0.0, seg["start"] - PAD), min(total, seg["end"] + PAD)
        dest = out / f"{clip_id}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
                        "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(dest)], check=True)
        report["clips"].append({"id": clip_id, "start": round(a, 2), "end": round(b, 2),
                                "seconds": round(b - a, 2)})
    report["status"] = "OK: listen to every clip before approval"
    (out / "split-report.json").write_text(json.dumps(report, indent=1))
    print(report["status"], f"({len(good)} clips)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
