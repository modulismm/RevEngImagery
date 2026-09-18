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


# --------------------------------------------------------------------------- #
# Memory-linked sounds.
#
# The workshops are with older participants, and the brief asked for sounds tied
# to memory rather than generic effects: a rotary telephone, a typewriter, a
# kettle, a music box. These are domestic and mid-century on purpose.
# --------------------------------------------------------------------------- #

def _tone(buf, freq, start, length, amp, decay=4.0, harmonics=(1.0,)):
    """Add a decaying tone with optional harmonics at `start` (samples)."""
    n = len(buf)
    for h_ratio in harmonics:
        for i in range(length):
            if start + i >= n:
                break
            frac = i / length
            buf[start + i] += (amp / len(harmonics)) * math.exp(-decay * frac) \
                * math.sin(2 * math.pi * freq * h_ratio * i / RATE)


def clock(seconds=6.0):
    """A mantel clock: alternating tick and tock, one second apart."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    for beat in range(int(seconds)):
        at = int(beat * RATE)
        freq = 2400 if beat % 2 == 0 else 1900
        length = int(0.03 * RATE)
        click = OnePole(1200, highpass=True)
        for i in range(length):
            if at + i >= n:
                break
            decay = math.exp(-40.0 * i / length)
            buf[at + i] += 0.6 * decay * click(random.uniform(-1, 1))
        _tone(buf, freq, at, int(0.02 * RATE), 0.25, 30.0)
    return normalise(envelope(buf, 0.01, 0.2))


def metronome(seconds=6.0):
    """Wooden metronome at roughly 72 beats per minute."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    period = 60.0 / 72
    t = 0.1
    while t < seconds:
        at = int(t * RATE)
        length = int(0.02 * RATE)
        for i in range(length):
            if at + i >= n:
                break
            buf[at + i] += 0.7 * math.exp(-50.0 * i / length) * random.uniform(-1, 1)
        _tone(buf, 1100, at, int(0.05 * RATE), 0.3, 24.0, (1.0, 2.7))
        t += period
    return normalise(envelope(buf, 0.01, 0.2))


def telephone(seconds=6.0):
    """A rotary telephone: two tones cut into the old double ring."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    t = 0.2
    while t < seconds - 1.2:
        for burst in (0.0, 0.42):
            at = int((t + burst) * RATE)
            length = int(0.36 * RATE)
            for i in range(length):
                if at + i >= n:
                    break
                # 20Hz tremolo is what makes a bell sound mechanical.
                trem = 0.5 + 0.5 * math.sin(2 * math.pi * 20 * i / RATE)
                env = min(1.0, i / (0.01 * RATE)) * math.exp(-1.2 * i / length)
                sample = (math.sin(2 * math.pi * 1050 * i / RATE)
                          + 0.7 * math.sin(2 * math.pi * 1320 * i / RATE))
                buf[at + i] += 0.32 * env * trem * sample
        t += 2.0
    return normalise(envelope(buf, 0.01, 0.3))


def typewriter(seconds=6.0):
    """Irregular key strikes, with a carriage return partway through."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    t = 0.15
    while t < seconds - 0.4:
        at = int(t * RATE)
        length = int(0.04 * RATE)
        strike = OnePole(2800, highpass=True)
        for i in range(length):
            if at + i >= n:
                break
            buf[at + i] += 0.65 * math.exp(-34.0 * i / length) * strike(random.uniform(-1, 1))
        _tone(buf, random.uniform(700, 1100), at, int(0.03 * RATE), 0.2, 28.0)
        t += random.uniform(0.11, 0.3)
        if random.random() < 0.08:                 # carriage return
            at = int(t * RATE)
            ratchet = int(0.25 * RATE)
            for i in range(ratchet):
                if at + i >= n:
                    break
                if i % int(0.012 * RATE) < int(0.004 * RATE):
                    buf[at + i] += 0.3 * random.uniform(-1, 1)
            _tone(buf, 1800, at + ratchet, int(0.4 * RATE), 0.3, 6.0, (1.0, 2.4))
            t += 0.6
    return normalise(envelope(buf, 0.02, 0.25))


def kettle(seconds=6.0):
    """A kettle coming to the whistle: noise, then a rising two-tone."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    boil = OnePole(3000)
    for i in range(n):
        t = i / seconds / RATE
        buf[i] += boil(random.uniform(-1, 1)) * 0.25 * min(1.0, t * 2)
    start = int(seconds * 0.35 * RATE)
    phase1 = phase2 = 0.0
    for i in range(start, n):
        frac = (i - start) / max(1, n - start)
        freq = 1750 + 320 * frac
        phase1 += 2 * math.pi * freq / RATE
        phase2 += 2 * math.pi * (freq * 1.5) / RATE
        env = min(1.0, frac * 4) * 0.5
        buf[i] += env * (math.sin(phase1) + 0.45 * math.sin(phase2)) * 0.45
    return normalise(envelope(buf, 0.3, 0.4))


def music_box(seconds=6.0):
    """A simple music-box phrase: plucked, bell-like, slightly detuned."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    # A gentle major phrase; semitone offsets from C5.
    phrase = [0, 4, 7, 12, 7, 4, 0, 4]
    for index, semitone in enumerate(phrase):
        at = int((0.25 + index * 0.62) * RATE)
        freq = 523.25 * (2 ** (semitone / 12))
        _tone(buf, freq, at, int(1.6 * RATE), 0.5, 4.5, (1.0, 2.01, 3.03, 5.1))
    return normalise(envelope(buf, 0.01, 0.4))


def steam_train(seconds=6.0):
    """Chuffs accelerating, with a whistle over the top."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    t, period = 0.2, 0.62
    while t < seconds - 0.3:
        at = int(t * RATE)
        length = int(0.3 * RATE)
        chuff = OnePole(900)
        for i in range(length):
            if at + i >= n:
                break
            env = math.exp(-9.0 * i / length)
            buf[at + i] += 0.55 * env * chuff(random.uniform(-1, 1))
        t += period
        period = max(0.24, period * 0.9)           # picking up speed
    at = int(seconds * 0.55 * RATE)
    length = int(1.1 * RATE)
    for i in range(length):
        if at + i >= n:
            break
        frac = i / length
        env = min(1.0, frac * 8) * math.exp(-1.6 * frac)
        for ratio, amp in ((1.0, 1.0), (1.5, 0.6), (2.02, 0.3)):
            buf[at + i] += 0.16 * amp * env * math.sin(2 * math.pi * 520 * ratio * i / RATE)
    return normalise(envelope(buf, 0.05, 0.3))


def train_whistle(seconds=3.0):
    """A distant whistle on its own -- a chord of three detuned tones."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    for i in range(n):
        frac = i / n
        env = min(1.0, frac * 6) * math.exp(-1.5 * frac)
        for ratio, amp in ((1.0, 1.0), (1.26, 0.7), (1.5, 0.5)):
            buf[i] += 0.16 * amp * env * math.sin(2 * math.pi * 440 * ratio * i / RATE)
    return normalise(envelope(buf, 0.05, 0.5))


def door_creak(seconds=2.6):
    """A hinge: a swept resonance over a noise bed, in stick-slip steps."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    phase = 0.0
    for i in range(n):
        frac = i / n
        freq = 320 + 700 * frac + 120 * math.sin(2 * math.pi * 11 * frac)
        phase += 2 * math.pi * freq / RATE
        # Stick-slip: the hinge grabs and releases rather than sliding smoothly.
        grip = 0.6 + 0.4 * (1 if math.sin(2 * math.pi * 26 * frac) > 0 else 0.3)
        env = math.sin(math.pi * frac) ** 0.6
        buf[i] += 0.4 * env * grip * math.sin(phase) + 0.05 * env * random.uniform(-1, 1)
    return normalise(envelope(buf, 0.03, 0.3))


def floor_creak(seconds=2.2):
    """Old floorboards: lower and slower than a hinge."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    phase = 0.0
    body = OnePole(600)
    for i in range(n):
        frac = i / n
        freq = 120 + 180 * math.sin(math.pi * frac)
        phase += 2 * math.pi * freq / RATE
        env = math.sin(math.pi * frac) ** 0.8
        creak = 1.0 if math.sin(2 * math.pi * 17 * frac) > -0.2 else 0.2
        buf[i] += 0.45 * env * creak * math.sin(phase) + body(random.uniform(-1, 1)) * 0.08 * env
    return normalise(envelope(buf, 0.04, 0.35))


def spoon_cup(seconds=3.0):
    """A spoon stirred in a cup: repeated small chimes."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    t = 0.15
    while t < seconds - 0.2:
        at = int(t * RATE)
        freq = random.uniform(2300, 3200)
        _tone(buf, freq, at, int(0.16 * RATE), 0.42, 16.0, (1.0, 2.7, 4.3))
        t += random.uniform(0.17, 0.26)
    return normalise(envelope(buf, 0.01, 0.3))


def radio_static(seconds=5.0):
    """Tuning across a dial: hiss, with a voice-like formant drifting through."""
    n = int(RATE * seconds)
    band = OnePole(3400)
    high = OnePole(300, highpass=True)
    buf = []
    for i in range(n):
        t = i / RATE
        wobble = 0.5 + 0.5 * math.sin(2 * math.pi * 0.7 * t + math.sin(t * 3))
        buf.append(high(band(random.uniform(-1, 1))) * (0.35 + 0.5 * wobble))
    for _ in range(4):                              # stations drifting past
        at = random.randrange(0, n - int(0.7 * RATE))
        length = int(random.uniform(0.25, 0.6) * RATE)
        freq = random.uniform(280, 700)
        for i in range(length):
            env = math.sin(math.pi * i / length)
            buf[at + i] += 0.22 * env * math.sin(2 * math.pi * freq * i / RATE)
    return normalise(envelope(buf, 0.15, 0.35))


def rain_window(seconds=6.0):
    """Rain heard indoors: duller than open rain, with drips on the glass."""
    n = int(RATE * seconds)
    muffle = OnePole(1400)
    buf = [muffle(v) * 0.4 for v in white(n)]
    for _ in range(int(seconds * 16)):
        at = random.randrange(0, n - 1200)
        length = random.randint(300, 1000)
        freq = random.uniform(400, 1100)
        amp = random.uniform(0.08, 0.2)
        for i in range(length):
            buf[at + i] += amp * math.exp(-5.0 * i / length) \
                * math.sin(2 * math.pi * freq * i / RATE)
    return normalise(envelope(buf, 0.3, 0.45))


def snow_steps(seconds=5.0):
    """Footsteps in snow: a soft crunch, evenly paced."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    t = 0.3
    while t < seconds - 0.4:
        at = int(t * RATE)
        length = int(0.22 * RATE)
        crunch = OnePole(2200, highpass=True)
        for i in range(length):
            if at + i >= n:
                break
            frac = i / length
            env = math.sin(math.pi * frac) ** 1.6
            grain = random.uniform(-1, 1) if random.random() < 0.55 else 0.0
            buf[at + i] += 0.5 * env * crunch(grain)
        t += random.uniform(0.62, 0.78)
    return normalise(envelope(buf, 0.05, 0.3))


def heartbeat(seconds=5.0):
    """Lub-dub at about 66 beats per minute."""
    n = int(RATE * seconds)
    buf = silence(seconds)
    period = 60.0 / 66
    t = 0.2
    while t < seconds - 0.4:
        for offset, amp, freq in ((0.0, 0.85, 58), (0.26, 0.55, 44)):
            at = int((t + offset) * RATE)
            length = int(0.16 * RATE)
            for i in range(length):
                if at + i >= n:
                    break
                frac = i / length
                env = math.sin(math.pi * frac) ** 1.5
                buf[at + i] += amp * env * math.sin(2 * math.pi * freq * i / RATE)
        t += period
    return normalise(envelope(buf, 0.05, 0.35))


MEMORY = [
    ("clock",      "Clock",          "Horloge",              clock),
    ("metronome",  "Metronome",      "Métronome",            metronome),
    ("telephone",  "Rotary phone",   "Téléphone à cadran",   telephone),
    ("typewriter", "Typewriter",     "Machine à écrire",     typewriter),
    ("kettle",     "Kettle",         "Bouilloire",           kettle),
    ("musicbox",   "Music box",      "Boîte à musique",      music_box),
    ("train",      "Steam train",    "Train à vapeur",       steam_train),
    ("whistle",    "Train whistle",  "Sifflet de train",     train_whistle),
    ("door",       "Creaking door",  "Porte qui grince",     door_creak),
    ("floor",      "Creaking floor", "Plancher qui craque",  floor_creak),
    ("spoon",      "Spoon in a cup", "Cuillère dans une tasse", spoon_cup),
    ("radio",      "Radio tuning",   "Radio qu’on syntonise", radio_static),
    ("rainwindow", "Rain on a window", "Pluie sur la fenêtre", rain_window),
    ("snowsteps",  "Steps in snow",  "Pas dans la neige",    snow_steps),
    ("heartbeat",  "Heartbeat",      "Battement de cœur",    heartbeat),
]


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "app/static/sounds/_raw"
    os.makedirs(out_dir, exist_ok=True)
    random.seed(20260918)               # reproducible bank
    for slug, label_en, label_fr, fn in GENERATED + MEMORY:
        path = os.path.join(out_dir, f"{slug}.wav")
        write_wav(path, fn())
        print(f"  {slug:10} {os.path.getsize(path) // 1024:5}KB  {label_en} / {label_fr}")
    print(f"\n{len(GENERATED) + len(MEMORY)} sounds synthesised -> {out_dir}")


if __name__ == "__main__":
    main()
