#!/usr/bin/env python3
"""
Build a short MP4 slideshow from still images (for Facebook product posts).

Requires ffmpeg on PATH.

Usage:
  python scripts/make_slideshow_video.py img1.jpg img2.jpg -o out.mp4
  python scripts/make_slideshow_video.py dir/*.jpg -o promo.mp4 --seconds 2.5
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _which_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for candidate in (
        Path(r"C:\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe"),
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    sys.exit("ffmpeg not found on PATH. Install ffmpeg and retry.")


def build(
    images: list[Path],
    output: Path,
    *,
    seconds: float = 2.5,
    width: int = 1080,
    height: int = 1080,
    fps: int = 30,
) -> None:
    if len(images) < 2:
        sys.exit("Need at least 2 images.")
    for p in images:
        if not p.is_file():
            sys.exit(f"Missing image: {p}")

    ffmpeg = _which_ffmpeg()
    n = len(images)

    # Per-input: hold still → scale/pad square → force CFR → short fade in/out
    # Then concat. More reliable than xfade on looped stills.
    fade_d = min(0.35, seconds / 4)
    filter_parts: list[str] = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x1a1410,"
            f"setsar=1,fps={fps},format=yuv420p,"
            f"fade=t=in:st=0:d={fade_d},"
            f"fade=t=out:st={seconds - fade_d:.3f}:d={fade_d}"
            f"[v{i}]"
        )
    concat_in = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")
    filter_complex = ";".join(filter_parts)

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for img in images:
        cmd += ["-loop", "1", "-t", f"{seconds:.3f}", "-i", str(img)]
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-movflags",
        "+faststart",
        "-an",
        str(output),
    ]

    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Building slideshow: {n} images → {output}")
    print(f"  {width}x{height} @ {fps}fps, {seconds}s/slide")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed (exit {r.returncode})")
    size_kb = output.stat().st_size // 1024
    print(f"OK {output} ({size_kb} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Still images → MP4 slideshow")
    ap.add_argument("images", nargs="+", type=Path, help="Image paths in order")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--seconds", type=float, default=2.5, help="Seconds per slide")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()
    build(
        list(args.images),
        args.output,
        seconds=args.seconds,
        width=args.width,
        height=args.height,
        fps=args.fps,
    )


if __name__ == "__main__":
    main()
