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
    if mood in BEATS:
        return beat_score(seconds, mood, seed)
    if mood in PIANO_PROGS:
        return piano_score(seconds, mood, seed)
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


# ---------------------------------------------------------------- piano + violin (owner, 22 Nov: "relaxing piano/violin")

def piano_note(freq, dur, vel=0.8):
    """Additive piano: slightly inharmonic partials, faster decay for higher partials, soft hammer."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    out = np.zeros(n)
    B = 0.00035
    for k in range(1, 11):
        fk = k * freq * np.sqrt(1 + B * k * k)
        if fk > SR / 2.2:
            break
        amp = (1 / k ** 1.25) * (0.6 + 0.4 * vel)
        decay = 0.9 + 0.55 * k + freq / 900
        for detune in (-0.6, 0.6):                        # two strings per note, gentle chorus
            out += amp * 0.5 * np.sin(2 * np.pi * (fk + detune) * t) * np.exp(-t * decay)
    hammer = np.random.default_rng(int(freq)).normal(0, 1, n) * np.exp(-t * 140) * 0.02
    env = np.minimum(1, t / 0.004) * np.minimum(1, (dur - t) / 0.08)
    return (out + hammer) * env * vel


def violin_note(freq, dur, vel=0.5):
    """Bowed string: band-limited saw with vibrato, slow bow attack and release."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    vib = 1 + 0.0035 * np.sin(2 * np.pi * 5.3 * t) * np.minimum(1, t / 0.8)
    phase = 2 * np.pi * np.cumsum(freq * vib) / SR
    out = sum(np.sin(k * phase) / k ** 1.6 for k in range(1, 14) if k * freq < SR / 2.5)
    env = np.minimum(1, t / 0.7) * np.minimum(1, (dur - t) / 0.9)
    return out * env * vel


def reverb(x, seconds=2.4, mix=0.32):
    n = int(SR * seconds)
    rng = np.random.default_rng(3)
    ir = rng.normal(0, 1, n) * np.exp(-np.linspace(0, 7, n))
    ir = np.convolve(ir, np.ones(24) / 24, mode="same")    # darker tail
    ir /= np.sqrt((ir ** 2).sum())
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return (1 - mix) * x + mix * wet * 3


PIANO_PROGS = {
    "piano": (72, [("F2", ["F3", "A3", "C4", "E4"]), ("A1", ["A3", "C4", "E4", "G4"]),
                   ("D2", ["D3", "F3", "A3", "C4"]), ("G1", ["G3", "B3", "D4", "F4"])]),
    "piano2": (66, [("C2", ["C4", "E4", "G4", "B4"]), ("A1", ["A3", "C4", "E4", "G4"]),
                    ("F1", ["F3", "A3", "C4", "E4"]), ("G1", ["G3", "B3", "D4", "A4"])]),
}


def piano_score(seconds, mood="piano", seed=7):
    bpm, prog = PIANO_PROGS[mood]
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    track = np.zeros(int(SR * (seconds + 4)))
    t, bar = 0.0, 0
    while t < seconds:
        root, tones = prog[bar % len(prog)]
        place(track, piano_note(hz(root), beat * 4, 0.55), t, 0.9)
        pattern = [0, 2, 1, 3, 2, 1, 3, 2]
        for i, k in enumerate(pattern):                    # flowing eighth-note arpeggio
            place(track, piano_note(hz(tones[k]), beat * 1.6, 0.42 + 0.08 * (i % 2 == 0)), t + i * beat / 2, 0.55)
        if bar % 2 == 0:                                   # sparse right-hand melody, an octave up
            for step in (0, 2.5):
                top = tones[rng.integers(1, len(tones))]
                up = top[:-1] + str(int(top[-1]) + 1)
                place(track, piano_note(hz(up), beat * 2.2, 0.5), t + step * beat, 0.5)
        line = tones[1 if bar % 2 else 2]                  # violin holds a chord tone across the bar
        place(track, violin_note(hz(line), beat * 4.1, 0.5), t, 0.22)
        if bar % 4 == 3:
            place(track, violin_note(hz(tones[3]), beat * 2.0, 0.45), t + beat * 2, 0.18)
        t += 4 * beat
        bar += 1
    track = reverb(track[: int(SR * seconds)])
    fade = int(SR * 1.6)
    track[-fade:] *= np.linspace(1, 0, fade)
    track[: int(SR * 0.5)] *= np.linspace(0, 1, int(SR * 0.5))
    return track / (np.abs(track).max() + 1e-9) * 0.7


# ---- Upbeat original beats (owner request 26 Nov 2026: "viral" energy). Original compositions only. ----
def kick(vel=1.0):
    t = np.arange(int(SR * 0.35)) / SR
    f = 50 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * vel


def snare(rng, clap=False, vel=1.0):
    n = int(SR * (0.22 if clap else 0.18))
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - np.convolve(noise, np.ones(6) / 6, "same")          # brighten
    env = np.exp(-t * (22 if clap else 26))
    if clap:
        env = env * (1 + 0.8 * (np.sin(2 * np.pi * 90 * t) > 0) * (t < 0.03))
    body = 0 if clap else np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.5
    return (noise * env * 0.45 + body) * vel


def hat(rng, open_=False, vel=1.0):
    n = int(SR * (0.16 if open_ else 0.045))
    x = rng.standard_normal(n)
    x = x - np.convolve(x, np.ones(3) / 3, "same")
    return x * np.exp(-np.arange(n) / SR * (18 if open_ else 90)) * 0.22 * vel


def synth_bass(freq, dur):
    t = np.arange(int(SR * dur)) / SR
    x = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t) + 0.12 * np.sin(6 * np.pi * freq * t)
    env = np.minimum(1, t / 0.008) * np.exp(-t * 2.2)
    return np.tanh(1.6 * x * env) * 0.6


def keys(freqs, dur):
    t = np.arange(int(SR * dur)) / SR
    x = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 6) for f in freqs)
    return x * np.minimum(1, t / 0.006) * np.exp(-t * 5) / len(freqs)


def marimba(freq, dur):
    t = np.arange(int(SR * dur)) / SR
    x = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * 4 * freq * t) * np.exp(-t * 30)
    return x * np.minimum(1, t / 0.003) * np.exp(-t * 7)


def up(note, k=1):
    return note[:-1] + str(int(note[-1]) + k)


# bpm, swing, progression (root, tones), drum pattern per 16th step: K kick, S snare, C clap, h hat, o open hat
BEATS = {
    "pop":    (112, 0.0, [("C2", ["C4", "E4", "G4", "B4"]), ("A1", ["A3", "C4", "E4", "G4"]),
                          ("F1", ["F3", "A3", "C4", "E4"]), ("G1", ["G3", "B3", "D4", "F4"])],
               "K.h.S.h.K.hKS.ho"),
    "lofi":   (86, 0.18, [("D2", ["D4", "F4", "A4", "C5"]), ("G1", ["G3", "B3", "D4", "F4"]),
                          ("C2", ["C4", "E4", "G4", "B4"]), ("A1", ["A3", "C4", "E4", "G4"])],
               "K.h.S.h..hKS.h."),
    "bounce": (122, 0.0, [("F1", ["F3", "A3", "C4", "E4"]), ("G1", ["G3", "B3", "D4", "F4"]),
                          ("E1", ["E3", "G3", "B3", "D4"]), ("A1", ["A3", "C4", "E4", "G4"])],
               "K.hhC.hhK.hhC.ho"),
}
HOOKS = [[0, 2, 1, 2, -1, 3, 2, -1], [2, -1, 1, 0, 2, -1, 3, 1], [0, 0, 2, -1, 3, 2, 1, -1]]


def beat_score(seconds, mood="pop", seed=7):
    bpm, swing, prog, pat = BEATS[mood]
    rng = np.random.default_rng(seed)
    six = 60 / bpm / 4
    track = np.zeros(int(SR * (seconds + 3)))
    side = np.ones_like(track)                       # sidechain pump from the kick
    hook = HOOKS[seed % len(HOOKS)]
    t, bar = 0.0, 0
    while t < seconds:
        root, tones = prog[bar % len(prog)]
        intro = bar == 0
        for i, ch in enumerate(pat):
            at = t + i * six + (swing * six if i % 2 else 0)
            if ch == "K":
                place(track, kick(), at, 0.9)
                a = int(at * SR)
                n = min(int(SR * 0.22), len(side) - a)
                if n > 0:
                    side[a:a + n] = np.minimum(side[a:a + n], 0.45 + 0.55 * np.linspace(0, 1, n) ** 0.6)
            elif ch in "SC" and not intro:
                place(track, snare(rng, clap=ch == "C"), at, 0.7)
            elif ch == "h":
                place(track, hat(rng, vel=0.7 + 0.3 * rng.random()), at, 0.8)
            elif ch == "o" and not intro:
                place(track, hat(rng, True), at, 0.7)
        for k in (0, 3, 6, 10, 12):                   # syncopated bass
            place(track, synth_bass(hz(root) * (2 if k == 10 else 1), six * 2.2), t + k * six, 0.55)
        for k in (2, 6, 10, 14):                      # off-beat chord stabs
            place(track, keys([hz(x) for x in tones[:3]], six * 1.6), t + k * six, 0.33)
        if bar % 4 not in (3,) and not intro:         # catchy 8-step marimba hook, answered every 4th bar
            for k, idx in enumerate(hook):
                if idx >= 0:
                    place(track, marimba(hz(up(tones[idx % len(tones)])), six * 2), t + k * 2 * six, 0.38)
        else:
            for k in (0, 3, 6):
                place(track, marimba(hz(up(tones[(k + bar) % len(tones)])), six * 2), t + k * 2 * six, 0.3)
        t += 16 * six
        bar += 1
    track = track * side
    track = track[: int(SR * seconds)]
    track = reverb(track, 1.2, 0.12)
    fade = int(SR * 1.2)
    track[-fade:] *= np.linspace(1, 0, fade)
    return track / (np.abs(track).max() + 1e-9) * 0.75


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
