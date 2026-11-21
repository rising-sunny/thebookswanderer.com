"""Score three original story cues. Requires FluidSynth CLI, GeneralUser GS and ffmpeg.

Usage: python score.py /path/to/GeneralUser-GS.sf2 /path/to/output
The instrument bank is used offline, under its music-production license:
https://github.com/mrbumpy409/GeneralUser-GS/blob/main/documentation/LICENSE.txt
"""

import argparse
import random
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

PPQ = 480


def variable_length(number):
    data = [number & 127]
    number >>= 7
    while number:
        data.insert(0, 128 + (number & 127))
        number >>= 7
    return bytes(data)


class Cue:
    def __init__(self, bpm, seed):
        self.bpm = bpm
        self.rng = random.Random(seed)
        us = int(60_000_000 / bpm)
        self.events = [(0, 0, b"\xff\x51\x03" + us.to_bytes(3, "big"))]

    def instrument(self, channel, program, volume, pan):
        for message in [
            [0xC0 + channel, program],
            [0xB0 + channel, 7, volume],
            [0xB0 + channel, 10, pan],
            [0xB0 + channel, 91, 38],
        ]:
            self.events.append((0, 1, bytes(message)))

    def note(self, channel, beat, length, pitch, velocity):
        start = max(0, round(beat * PPQ) + self.rng.randint(-4, 4))
        velocity = max(1, min(127, velocity + self.rng.randint(-3, 3)))
        self.events += [
            (start, 3, bytes([0x90 + channel, pitch, velocity])),
            (start + round(length * PPQ), 2, bytes([0x80 + channel, pitch, 0])),
        ]

    def save(self, path):
        data, last = bytearray(), 0
        for tick, _, msg in sorted(self.events):
            data.extend(variable_length(tick - last) + msg)
            last = tick
        data.extend(b"\x00\xff\x2f\x00")
        path.write_bytes(
            b"MThd"
            + struct.pack(">IHHH", 6, 0, 1, PPQ)
            + b"MTrk"
            + struct.pack(">I", len(data))
            + data
        )


def reading_room():
    cue = Cue(108, 19)
    cue.instrument(0, 0, 99, 53)  # piano
    cue.instrument(1, 32, 101, 63)  # upright bass
    cue.instrument(2, 24, 87, 82)  # nylon guitar
    cue.instrument(9, 40, 77, 68)  # brush kit
    bars = [
        (50, [57, 60, 64, 65]),
        (43, [53, 59, 62, 64]),
        (48, [55, 59, 62, 64]),
        (45, [55, 60, 64, 67]),
        (50, [53, 57, 60, 64]),
        (43, [53, 59, 62, 65]),
        (48, [55, 59, 62, 64]),
    ]
    phrases = [
        [(0, 72, 0.7), (0.85, 76, 0.38), (1.55, 77, 0.7), (2.75, 74, 0.8)],
        [(0.45, 71, 0.7), (1.40, 74, 0.4), (2.05, 76, 1.1)],
        [(0.15, 79, 0.68), (1.5, 76, 0.6), (2.7, 74, 0.4), (3.34, 72, 0.56)],
        [(0, 76, 0.8), (1.35, 79, 0.45), (2, 81, 1.1)],
        [(0.3, 77, 0.6), (1.2, 76, 0.45), (2, 74, 0.9)],
        [(0, 71, 0.58), (0.80, 74, 0.55), (1.56, 77, 0.7), (2.75, 74, 0.55)],
        [(0, 72, 2.6)],
    ]
    for i, (root, chord) in enumerate(bars):
        pos = 4 * i
        for b, n, d in phrases[i]:
            cue.note(0, pos + b, d, n, 80 if b < 1 else 71)
        last = i == len(bars) - 1
        for b, vel in [(0, 56)] if last else [(0.62, 61), (2.03, 67), (3.62, 50)]:
            for k, p in enumerate(chord):
                cue.note(2, pos + b + k * 0.025, 1.7 if last else 0.49, p, vel)
        cue.note(1, pos, 2.3 if last else 1.3, root, 85)
        if not last:
            cue.note(1, pos + 2, 0.92, root + 7, 74)
            if i in (1, 3, 5):
                cue.note(1, pos + 3.47, 0.39, bars[i + 1][0] - 1, 57)
            for b in range(4):
                cue.note(9, pos + b, 0.12, 42, 40 if b % 2 else 50)
                if i > 0:
                    cue.note(9, pos + b + 0.64, 0.1, 42, 32)
            for b in (1, 3):
                cue.note(9, pos + b, 0.22, 38, 49)
            cue.note(9, pos, 0.16, 36, 59)
    return cue, 15.4


def disappearing_ink():
    cue = Cue(84, 27)
    cue.instrument(0, 11, 103, 61)  # vibraphone
    cue.instrument(1, 45, 99, 71)  # pizzicato strings
    cue.instrument(2, 73, 83, 47)  # flute
    cue.instrument(3, 8, 81, 82)  # celesta
    bars = [
        (50, [69, 72, 76]),
        (46, [65, 69, 74]),
        (43, [67, 70, 74]),
        (45, [64, 68, 74]),
        (50, [69, 72, 77]),
        (48, [67, 72, 76]),
        (50, [65, 69, 74]),
    ]
    motifs = [
        [(0, 81, 0.8), (1.55, 77, 0.36), (2.12, 76, 0.65)],
        [(0.5, 74, 0.8), (2.0, 77, 0.65)],
        [(0, 79, 0.85), (1.6, 82, 0.38), (2.18, 81, 0.48)],
        [(0.5, 80, 0.45), (1.2, 76, 0.62)],
        [(0, 81, 0.85), (1.38, 84, 0.75), (2.48, 81, 0.42)],
        [(0, 79, 0.95), (1.6, 76, 0.7)],
        [(0, 74, 1.9)],
    ]
    for i, (root, chord) in enumerate(bars):
        pos = i * 3
        cue.note(1, pos, 0.57, root, 82)
        if i < 6:
            cue.note(1, pos + 1.47, 0.32, root + 12, 63)
            if i != 3:
                cue.note(1, pos + 2.35, 0.32, root + 7, 54)
        for b, n, d in motifs[i]:
            cue.note(0, pos + b, d, n, 83 if b == 0 else 72)
        if i in (1, 3, 4, 5):
            cue.note(2, pos + 0.12, 1.85, chord[0], 63)
        if i in (2, 4, 6):
            for k, n in enumerate(chord):
                cue.note(3, pos + 0.09 + k * 0.13, 0.85, n + 12, 53)
    return cue, 15.4


def walnut():
    cue = Cue(103, 61)
    cue.instrument(0, 24, 106, 55)  # fingerpicked nylon guitar
    cue.instrument(1, 32, 90, 67)
    cue.instrument(2, 4, 87, 81)  # electric piano
    cue.instrument(9, 0, 69, 68)
    bars = [
        (50, [57, 62, 66, 69]),
        (47, [54, 59, 62, 66]),
        (43, [55, 59, 62, 66]),
        (45, [55, 61, 64, 69]),
        (50, [57, 62, 66, 69]),
    ]
    for i, (bass, chord) in enumerate(bars):
        pos = 4 * i
        for k, (offset, index) in enumerate(
            [(0, 0), (0.48, 1), (1.10, 2), (1.74, 1), (2.48, 3), (3.18, 2)]
        ):
            if i == 4 and k > 3:
                break
            cue.note(
                0,
                pos + offset,
                0.75 if i != 4 else 1.65,
                chord[index],
                90 - 5 * (k % 3),
            )
        cue.note(1, pos, 1.55, bass, 76)
        if i < 4:
            cue.note(1, pos + 2.55, 0.68, bass + 7, 65)
            for off in [0.60, 1.60, 2.60, 3.60]:
                cue.note(9, pos + off, 0.12, 82, 42 if off < 2 else 48)
        if i in [1, 2, 4]:
            cue.note(2, pos + 0.08, 1.75, chord[2] + 12, 62)
    return cue, 12.8


def main():
    a = argparse.ArgumentParser()
    a.add_argument("bank", type=Path)
    a.add_argument("output", type=Path)
    args = a.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        mid, wav = Path(tmp) / "cue.mid", Path(tmp) / "cue.wav"
        for name, build in [
            ("reading-room", reading_room),
            ("disappearing-ink", disappearing_ink),
            ("walnut", walnut),
        ]:
            cue, duration = build()
            cue.save(mid)
            subprocess.run(
                [
                    shutil.which("fluidsynth") or "fluidsynth",
                    "-ni",
                    "-q",
                    "-g",
                    "0.65",
                    "-r",
                    "44100",
                    "-F",
                    str(wav),
                    str(args.bank),
                    str(mid),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(wav),
                    "-af",
                    f"atrim=duration={duration},afade=t=out:st={duration - 0.8}:d=0.8,loudnorm=I=-16:TP=-1.8:LRA=9,aresample=48000",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(args.output / (name + ".m4a")),
                ],
                check=True,
            )


if __name__ == "__main__":
    main()
