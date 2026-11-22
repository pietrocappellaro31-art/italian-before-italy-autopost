"""
Script-aware splitter for long native recordings whose pauses are irregular.

The recording is cut into speech chunks at every silence of >= MIN_SIL seconds. Dynamic
programming then groups consecutive chunks into exactly one group per script line, choosing the
grouping whose group durations best match each line's expected length (from its syllable count,
scaled to the speaker's measured pace) and whose boundaries fall on the longest pauses.
Chunks may be left out as discarded takes (e.g. a retake), at a cost, so a repeated line
does not shift everything after it.

    python3 build/align_session.py RECORDING.m4a SCRIPT.json OUT_DIR

SCRIPT.json = [{"id": "IBI-W01-001", "text": "pala", "slow": false}, ...]
Output: OUT_DIR/<id>.wav (mono 48 kHz PCM, cut only, voice unaltered) and OUT_DIR/align-report.json
with a confidence flag per clip. Every clip still needs a human listen before approval.
"""

import json
import math
import pathlib
import re
import subprocess
import sys

MIN_SIL = 0.25
NOISE_DB = -42
PAD = 0.2
DISCARD_COST = 6.0


def syllables(text):
    t = text.lower()
    t = re.sub(r"[^a-zàèéìòóù' ]", " ", t)
    t = re.sub(r"\bgli\b", "li", t)
    t = re.sub(r"(ch|gh|sc)i(?=[aeouàèéòóù])", r"\1", t)   # chiesa -> chesa
    t = re.sub(r"([cg])i(?=[aouàòóù])", r"\1", t)            # ciao -> cao, giorno
    t = re.sub(r"gli(?=[aeouàèéòóù])", "l", t)              # famiglia
    t = re.sub(r"u(?=[aeioàèéìòó])", "", t)                  # buon, quanto
    t = re.sub(r"i(?=[aeouàèéòóù])", "", t)                  # piacere, dieci
    groups = re.findall(r"[aeiouàèéìòóù]+", t)
    return max(1, len(groups))


def speech_chunks(path):
    """Speech regions from a 10 ms loudness envelope, with thresholds relative to this file's own
    noise floor, so taps and breaths are not mistaken for words."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "<i2").astype(float) / 32768
    hop = 160
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-7)
    db = np.convolve(db, np.ones(5) / 5, mode="same")
    floor = np.percentile(db, 20)
    on = db > floor + 14
    chunks, start = [], None
    for i, v in enumerate(list(on) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            chunks.append([start / 100, i / 100, float(db[start:i].max())])
            start = None
    merged = []
    for c in chunks:                                     # join micro-gaps inside a word
        if merged and c[0] - merged[-1][1] < MIN_SIL:
            merged[-1][1], merged[-1][2] = c[1], max(merged[-1][2], c[2])
        else:
            merged.append(c)
    keep = [[s, e] for s, e, peak in merged if e - s >= 0.12 and peak > floor + 28]
    return keep, n / 100


def align(chunks, lines, pace):
    n, m = len(chunks), len(lines)
    exp = [pace * syllables(l["text"]) * (1.6 if l.get("slow") else 1.0) + 0.15 for l in lines]
    gap_after = [chunks[i + 1][0] - chunks[i][1] if i + 1 < n else 3.0 for i in range(n)]
    gap_before = [chunks[i][0] - chunks[i - 1][1] if i else 3.0 for i in range(n)]
    INF = float("inf")

    def group_cost(i, j, k):           # chunks i..j-1 form line k
        dur = chunks[j - 1][1] - chunks[i][0]
        c = 4.0 * math.log(dur / exp[k]) ** 2
        inner = sum(gap_after[t] for t in range(i, j - 1))
        c += 1.5 * sum(max(0.0, gap_after[t] - 0.7) for t in range(i, j - 1)) + 0.2 * inner
        c -= 0.8 * min(gap_before[i], 2.0) + 0.8 * min(gap_after[j - 1], 2.0)
        return c

    # dp[i][k] = best cost using first i chunks for first k lines
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for k in range(m + 1):
            if dp[i][k] == INF:
                continue
            if i < n:                                    # discard chunk i
                c = dp[i][k] + DISCARD_COST
                if c < dp[i + 1][k]:
                    dp[i + 1][k], back[i + 1][k] = c, ("skip", i, k)
            if k < m:
                for j in range(i + 1, min(n, i + 6) + 1):
                    c = dp[i][k] + group_cost(i, j, k)
                    if c < dp[j][k + 1]:
                        dp[j][k + 1], back[j][k + 1] = c, ("line", i, k)
    out, skipped, i, k = [None] * m, [], n, m
    while i > 0 or k > 0:
        kind, pi, pk = back[i][k]
        if kind == "line":
            out[pk] = (pi, i)
        else:
            skipped.append(pi)
        i, k = pi, pk
    return out, exp, sorted(skipped)


def main(argv):
    src, script, outdir = pathlib.Path(argv[1]), json.loads(pathlib.Path(argv[2]).read_text()), pathlib.Path(argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    chunks, total = speech_chunks(src)
    speech = sum(e - s for s, e in chunks)
    syl = sum(syllables(l["text"]) * (1.6 if l.get("slow") else 1.0) for l in script)
    pace = speech / syl * 0.9
    for _ in range(3):                                   # refine pace from the aligned result
        groups, exp, skipped = align(chunks, script, pace)
        durs = [chunks[j - 1][1] - chunks[i][0] for i, j in groups]
        pace *= math.exp(sum(math.log(d / e) for d, e in zip(durs, exp)) / len(durs))
    groups, exp, skipped = align(chunks, script, pace)
    report = {"source": src.name, "chunks": len(chunks), "pace_s_per_syllable": round(pace, 3),
              "discarded": [[round(c, 2) for c in chunks[i]] for i in skipped], "clips": []}
    for line, (i, j), e in zip(script, groups, exp):
        a, b = max(0.0, chunks[i][0] - PAD), min(total, chunks[j - 1][1] + PAD)
        ratio = (chunks[j - 1][1] - chunks[i][0]) / e
        flag = "check" if not 0.55 <= ratio <= 1.8 else "ok"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
                        "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(outdir / f"{line['id']}.wav")],
                       check=True)
        report["clips"].append({"id": line["id"], "text": line["text"], "start": round(a, 2), "end": round(b, 2),
                                "ratio": round(ratio, 2), "flag": flag})
    (outdir / "align-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(src.name, f"{len(chunks)} chunks, pace {pace:.3f}s/syl, discarded {len(skipped)},",
          sum(c['flag'] == 'check' for c in report['clips']), "flagged")


if __name__ == "__main__":
    main(sys.argv)
