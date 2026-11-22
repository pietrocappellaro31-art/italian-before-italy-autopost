"""
Original background music and sound effects, synthesised from scratch with numpy.
No samples, no SoundFonts, no third-party recordings: every sound is generated here, so the
rights are entirely ours (decision 22 Nov 2026: owner asked for music; commercial tracks are banned).

    python3 build/music.py OUT.wav SECONDS [mood] [seed]

Moods: "caffe" (bright plucked mandolin-like melody, bass, brushes, about 100 bpm),
       "piazza" (gentler, slower, warm pad + plucks), "lab" (sparse, playful staccato).
sfx(kind) returns a short mono array for: pop, tick, whoosh, ding, swipe.
"""

import sys
import wave

import numpy as np

SR = 48000
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(name):
    """'A4' -> 440.0"""
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[pitch] + 12 * (octave + 1) - 69) / 12)


def pluck(freq, dur, bright=0.5, rng=None):
    """Karplus-Strong plucked string (mandolin-like when doubled)."""
    rng = rng or np.random.default_rng(0)
    n = int(SR * dur)
    period = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, period)
    out = np.empty(n)
    decay = 0.996 - 0.004 * (1 - bright)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = decay * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    return out * np.exp(-np.linspace(0, 3.2, n))


def bass(freq, dur):
    t = np.arange(int(SR * dur)) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return tone * np.exp(-t * 3.5) * np.minimum(1, t * 200)


def pad(freqs, dur):
    t = np.arange(int(SR * dur)) / SR
    tone = sum(np.sin(2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 0.2 * t)) for f in freqs) / len(freqs)
    env = np.minimum(1, t / 0.4) * np.minimum(1, (dur - t) / 0.4)
    return tone * env


def brush(dur, rng, level=1.0):
    n = int(SR * dur)
    noise = rng.normal(0, 1, n)
    noise = np.diff(np.concatenate([[0], noise]))           # high-passed
    return noise * np.exp(-np.linspace(0, 9, n)) * 0.25 * level


def place(track, sound, at, gain=1.0):
    i = int(at * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(sound))
    track[i:j] += sound[: j - i] * gain


CHORDS = {   # (bass root, chord tones) in C major / A minor
    "C": ("C2", ["C4", "E4", "G4"]), "Am": ("A1", ["A3", "C4", "E4"]), "F": ("F1", ["F3", "A3", "C4"]),
    "G": ("G1", ["G3", "B3", "D4"]), "Dm": ("D2", ["D4", "F4", "A4"]), "E": ("E2", ["E3", "G#3", "B3"]),
}
MOODS = {
    "caffe": {"bpm": 102, "prog": ["C", "Am", "F", "G"], "density": 1.0, "pad": 0.10},
    "piazza": {"bpm": 84, "prog": ["F", "C", "Dm", "G"], "density": 0.6, "pad": 0.22},
    "lab": {"bpm": 112, "prog": ["Am", "F", "C", "E"], "density": 0.7, "pad": 0.06},
}


def score(seconds, mood="caffe", seed=7):
    cfg, rng = MOODS[mood], np.random.default_rng(seed)
    beat = 60 / cfg["bpm"]
    track = np.zeros(int(SR * (seconds + 2)))
    t, bar = 0.0, 0
    while t < seconds:
        root, tones = CHORDS[cfg["prog"][bar % len(cfg["prog"])]]
        place(track, bass(hz(root), beat * 1.8), t, 0.55)
        place(track, bass(hz(root), beat * 1.8), t + 2 * beat, 0.45)
        if cfg["pad"]:
            place(track, pad([hz(x) for x in tones], beat * 4), t, cfg["pad"])
        for step in range(8):                                   # eighth-note plucks
            if rng.random() > cfg["density"] * (0.9 if step % 2 == 0 else 0.55):
                continue
            note = tones[rng.integers(len(tones))]
            octave_up = note[:-1] + str(int(note[-1]) + 1) if rng.random() < 0.35 else note
            f = hz(octave_up)
            s = pluck(f, beat * 1.2, 0.6, rng) + 0.6 * pluck(f * 1.003, beat * 1.2, 0.6, rng)  # doubled course
            place(track, s, t + step * beat / 2, 0.16)
        for step in range(4):
            place(track, brush(beat * 0.5, rng, 1.0 if step % 2 else 0.55), t + step * beat, 0.5)
        t += 4 * beat
        bar += 1
    track = track[: int(SR * seconds)]
    fade = int(SR * 1.2)
    track[-fade:] *= np.linspace(1, 0, fade)
    track[: int(SR * 0.3)] *= np.linspace(0, 1, int(SR * 0.3))
    return track / (np.abs(track).max() + 1e-9) * 0.7


def sfx(kind):
    rng = np.random.default_rng({"pop": 1, "tick": 2, "whoosh": 3, "ding": 4, "swipe": 5}[kind])
    if kind == "pop":
        t = np.arange(int(SR * 0.09)) / SR
        f = 900 - 5000 * t
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * 0.6
    if kind == "tick":
        t = np.arange(int(SR * 0.03)) / SR
        return np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 180) * 0.4
    if kind == "ding":
        t = np.arange(int(SR * 0.7)) / SR
        return (np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 1975.5 * t)) * np.exp(-t * 5) * 0.35
    n = int(SR * (0.28 if kind == "whoosh" else 0.18))
    noise = rng.normal(0, 1, n)
    k = np.exp(-np.linspace(-2, 2, n) ** 2)
    smooth = np.convolve(noise, np.ones(30) / 30, mode="same")
    return smooth * k * (0.5 if kind == "whoosh" else 0.35)


def write_wav(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    out, secs = sys.argv[1], float(sys.argv[2])
    mood = sys.argv[3] if len(sys.argv) > 3 else "caffe"
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 7
    write_wav(out, score(secs, mood, seed))
    print(out, secs, mood)
