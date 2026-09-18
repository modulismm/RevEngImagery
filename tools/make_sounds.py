#!/usr/bin/env python3
"""Synthesise the part of the sound bank that scraping could not supply.

Wikimedia Commons rate-limits hard (600s backoff after a handful of requests),
and its audio search is dominated by Wiktionary pronunciation clips. Rather than
ship a thin or mislabelled bank, the ambient sounds are generated here: filtered
noise and simple oscillators, which is how these textures are built in sound
design anyway.

Everything this produces is original and CC0. Standard library only -- no numpy,
no ffmpeg (conversion to MP3 happens later, in a container).

    python3 tools/make_sounds.py app/static/sounds/_raw
"""
import math
import os
import random
import struct
import sys
import wave

RATE = 44100
DEPTH = 32767


# --------------------------------------------------------------------------- #
# Small signal helpers. Everything works on plain float lists in [-1, 1].
# --------------------------------------------------------------------------- #

def silence(seconds):
    return [0.0] * int(RATE * seconds)


class OnePole:
    """A one-pole filter: the cheapest way to colour noise convincingly."""

    def __init__(self, cutoff_hz, highpass=False):
        self.a = math.exp(-2.0 * math.pi * cutoff_hz / RATE)
        self.z = 0.0
        self.highpass = highpass

    def __call__(self, x):
        self.z = (1 - self.a) * x + self.a * self.z
        return x - self.z if self.highpass else self.z


def white(n):
    return [random.uniform(-1, 1) for _ in range(n)]


def envelope(buf, attack=0.01, release=0.05):
    """Fade the ends, so a sound that loops does not click."""
    n = len(buf)
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    for i in range(min(a, n)):
        buf[i] *= i / a
    for i in range(min(r, n)):
        buf[n - 1 - i] *= i / r
    return buf


def normalise(buf, peak=0.82):
    top = max((abs(v) for v in buf), default=0.0)
    if top < 1e-9:
        return buf
    gain = peak / top
    return [v * gain for v in buf]


def write_wav(path, buf):
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, v)) * DEPTH)) for v in buf))


# --------------------------------------------------------------------------- #
# The sounds
# --------------------------------------------------------------------------- #

def rain(seconds=6.0):
    """Hiss from band-passed noise, plus individual droplet transients."""
    n = int(RATE * seconds)
    low, high = OnePole(5200), OnePole(700, highpass=True)
    buf = [high(low(v)) * 0.34 for v in white(n)]
    for _ in range(int(seconds * 42)):          # scattered drops
        at = random.randrange(0, n - 900)
        freq = random.uniform(900, 2600)
        length = random.randint(200, 700)
        amp = random.uniform(0.05, 0.16)
        for i in range(length):
            decay = math.exp(-6.0 * i / length)
            buf[at + i] += amp * decay * math.sin(2 * math.pi * freq * i / RATE)
    return normalise(envelope(buf, 0.25, 0.4))


def wind(seconds=6.0):
    """Brown-ish noise under two slow gusts."""
    n = int(RATE * seconds)
    shape, tone = OnePole(380), OnePole(120, highpass=True)
    buf = []
    for i, v in enumerate(white(n)):
        t = i / RATE
        gust = (0.55
                + 0.45 * math.sin(2 * math.pi * 0.11 * t)
                + 0.25 * math.sin(2 * math.pi * 0.31 * t + 1.3))
        buf.append(tone(shape(v)) * max(0.0, gust) * 0.9)
    return normalise(envelope(buf, 0.6, 0.8))


def fire(seconds=6.0):
    """A low rumble with sharp crackles on top."""
    n = int(RATE * seconds)
    rumble = OnePole(220)
    buf = [rumble(v) * 0.5 for v in white(n)]
    for _ in range(int(seconds * 34)):
        at = random.randrange(0, n - 2000)
        length = random.randint(120, 900)
        amp = random.uniform(0.15, 0.55)
        crack = OnePole(2400, highpass=True)
        for i in range(length):
            decay = math.exp(-11.0 * i / length)
            buf[at + i] += crack(random.uniform(-1, 1)) * amp * decay
    return normalise(envelope(buf, 0.2, 0.5))


def crickets(seconds=6.0):
    """Chirp bursts: a high tone amplitude-modulated into pulses."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    t = 0.18
    while t < seconds - 0.5:
        base = random.uniform(3900, 4700)
        pulses = random.randint(3, 5)
        for p in range(pulses):
            start = int((t + p * 0.035) * RATE)
            length = int(0.022 * RATE)
            for i in range(length):
                if start + i >= n:
                    break
                env = math.sin(math.pi * i / length) ** 2
                buf[start + i] += 0.4 * env * math.sin(2 * math.pi * base * i / RATE)
        t += random.uniform(0.32, 0.7)
    return normalise(envelope(buf, 0.05, 0.2))


def birds(seconds=6.0):
    """Swept sine chirps in loose phrases -- a passable songbird."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    t = 0.2
    while t < seconds - 0.8:
        notes = random.randint(2, 4)
        for note in range(notes):
            start = int((t + note * random.uniform(0.09, 0.16)) * RATE)
            length = int(random.uniform(0.05, 0.11) * RATE)
            f0 = random.uniform(2300, 3400)
            f1 = f0 * random.uniform(1.15, 1.9)
            phase = 0.0
            for i in range(length):
                if start + i >= n:
                    break
                frac = i / length
                freq = f0 + (f1 - f0) * frac
                phase += 2 * math.pi * freq / RATE
                env = math.sin(math.pi * frac) ** 1.4
                buf[start + i] += 0.36 * env * math.sin(phase)
        t += random.uniform(0.7, 1.5)
    return normalise(envelope(buf, 0.05, 0.3))


def water_drop(seconds=1.6):
    """A falling pitch with a short resonant tail -- the classic drip."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    phase = 0.0
    length = int(0.35 * RATE)
    for i in range(length):
        frac = i / length
        freq = 1500 * math.exp(-5.0 * frac) + 320
        phase += 2 * math.pi * freq / RATE
        buf[i] += 0.85 * math.exp(-7.0 * frac) * math.sin(phase)
    tail = OnePole(1800)
    for i in range(length, min(n, length + int(0.5 * RATE))):
        frac = (i - length) / (0.5 * RATE)
        buf[i] += tail(random.uniform(-1, 1)) * 0.10 * math.exp(-9.0 * frac)
    return normalise(envelope(buf, 0.002, 0.15))


def chime(seconds=3.2):
    """Struck metal: inharmonic partials decaying at different rates."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    root = 660.0
    partials = [(1.0, 1.0, 3.0), (2.76, 0.52, 4.4), (5.40, 0.28, 6.0),
                (8.93, 0.14, 8.5), (13.34, 0.07, 11.0)]
    for ratio, amp, decay in partials:
        for i in range(n):
            t = i / RATE
            buf[i] += amp * math.exp(-decay * t) * math.sin(2 * math.pi * root * ratio * t)
    return normalise(envelope(buf, 0.002, 0.3))


GENERATED = [
    ("rain",     "Rain",       "Pluie",        rain),
    ("wind",     "Wind",       "Vent",         wind),
    ("fire",     "Fire",       "Feu",          fire),
    ("crickets", "Crickets",   "Grillons",     crickets),
    ("birds",    "Birds",      "Oiseaux",      birds),
    ("water",    "Water drop", "Goutte d'eau", water_drop),
    ("chime",    "Chime",      "Carillon",     chime),
]


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "app/static/sounds/_raw"
    os.makedirs(out_dir, exist_ok=True)
    random.seed(20260918)               # reproducible bank
    for slug, label_en, label_fr, fn in GENERATED:
        path = os.path.join(out_dir, f"{slug}.wav")
        write_wav(path, fn())
        print(f"  {slug:10} {os.path.getsize(path) // 1024:5}KB  {label_en} / {label_fr}")
    print(f"\n{len(GENERATED)} sounds synthesised -> {out_dir}")


if __name__ == "__main__":
    main()
