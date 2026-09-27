#!/usr/bin/env python3
"""
Base ambiental sin copyright para los reels, sintetizada con ffmpeg.

Por que generada y no una pista comercial: una cancion con derechos hace que
Meta silencie el reel, lo bloquee por region o le recorte el alcance.

ESTRUCTURA. Una sola voz de notas sueltas suena a ejercicio de piano, no a
musica. Aqui hay cuatro capas que se sostienen entre si:

  1. PAD      Acordes largos y sordos que sostienen el fondo. Es lo que hace
              que el resto suene "dentro" de algo en vez de en el vacio.
  2. MELODIA  La voz principal, con la campana de ataque rapido y cola larga.
  3. BAJO     La tonica una octava abajo en los cambios de acorde. Da peso.
  4. BRILLO   Notas agudas ocasionales, muy suaves, dos octavas arriba.

ARMONIA. Progresion Am - F - C - G, la mas comun de la musica popular, en vez
de notas de una escala al azar: da sensacion de ir a algun sitio y volver. La
melodia solo usa notas del acorde que suena, asi que nunca choca.

    python3 scripts/build_reel_audio.py --dur 19 --out /root/bed.m4a
"""
from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

# Am - F - C - G. Cada acorde: (notas del pad, tonica del bajo, notas melodia)
PROGRESION = [
    {"pad": [220.00, 261.63, 329.63], "bajo": 110.00, "mel": [440.00, 523.25, 659.25]},
    {"pad": [174.61, 220.00, 261.63], "bajo": 87.31,  "mel": [349.23, 440.00, 523.25]},
    {"pad": [196.00, 261.63, 329.63], "bajo": 130.81, "mel": [392.00, 523.25, 659.25]},
    {"pad": [196.00, 246.94, 293.66], "bajo": 98.00,  "mel": [392.00, 493.88, 587.33]},
]

COMPAS = 4.4   # segundos por acorde
PASO_MEL = 1.1  # entre notas de melodia
COLA_MEL = 3.0  # cuanto tarda en apagarse una nota de melodia


def _mk(tmp: Path, idx: int, expr: str, dur: float, fade: float = 0.3) -> Path:
    dst = tmp / f"s{idx:04d}.wav"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d={dur:.2f}",
        "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={max(dur-fade,0.05):.2f}:d={fade}",
        "-c:a", "pcm_s16le", str(dst),
    ], check=True)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description="Base ambiental para reels.")
    ap.add_argument("--dur", type=float, default=19.0)
    ap.add_argument("--out", default="/root/bed.m4a")
    ap.add_argument("--fade-out", type=float, default=3.0)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        piezas: list[tuple[Path, float]] = []  # (archivo, retardo en s)
        i = 0
        compas = 0
        t = 0.0

        while t < args.dur:
            ac = PROGRESION[compas % len(PROGRESION)]
            largo = min(COMPAS + 1.2, args.dur - t + 1.2)

            # 1. PAD: tres ondas con leve desafinacion entre si. Ese batido
            #    lento es lo que da textura; sin el suena a tono de test.
            for k, f in enumerate(ac["pad"]):
                expr = (f"0.30*sin(2*PI*{f}*t)"
                        f"+0.22*sin(2*PI*{f * 1.003:.3f}*t)"
                        f"+0.12*sin(2*PI*{f * 2}*t)")
                piezas.append((_mk(tmp, i, expr, largo, fade=1.4), t)); i += 1

            # 2. BAJO: tonica grave, entra con el acorde y se apaga solo.
            fb = ac["bajo"]
            expr = f"0.55*sin(2*PI*{fb}*t)*exp(-0.9*t)+0.2*sin(2*PI*{fb*2}*t)*exp(-1.6*t)"
            piezas.append((_mk(tmp, i, expr, min(largo, 3.5), fade=0.6), t)); i += 1

            # 3. MELODIA sobre las notas del acorde: no puede desafinar.
            mt = t
            paso = 0
            while mt < t + COMPAS and mt < args.dur:
                fm = ac["mel"][paso % len(ac["mel"])]
                dur = min(COLA_MEL, args.dur - mt + 0.8)
                expr = (f"0.50*sin(2*PI*{fm}*t)*exp(-2.4*t)"
                        f"+0.16*sin(2*PI*{fm*2}*t)*exp(-3.2*t)"
                        f"+0.06*sin(2*PI*{fm*3}*t)*exp(-4.5*t)")
                piezas.append((_mk(tmp, i, expr, dur), mt)); i += 1
                mt += PASO_MEL
                paso += 1

            # 4. BRILLO: una nota aguda por compas, muy suave, a contratiempo.
            fa = ac["mel"][-1] * 2
            expr = f"0.16*sin(2*PI*{fa}*t)*exp(-2.8*t)"
            piezas.append((_mk(tmp, i, expr, 2.2), t + COMPAS * 0.55)); i += 1

            t += COMPAS
            compas += 1

        inputs: list[str] = []
        delays: list[str] = []
        for n, (p, retardo) in enumerate(piezas):
            inputs += ["-i", str(p)]
            ms = int(retardo * 1000)
            delays.append(f"[{n}:a]adelay={ms}|{ms}[d{n}]")
        mix = "".join(f"[d{n}]" for n in range(len(piezas)))
        ganancia = math.sqrt(len(piezas)) * 0.42

        chain = (
            ";".join(delays)
            + f";{mix}amix=inputs={len(piezas)}:duration=longest:dropout_transition=0[m]"
            + f";[m]volume={ganancia:.2f},"
              # Un filtro paso bajo quita el filo metalico de las ondas puras.
              f"lowpass=f=5200,"
              # Reverb barata por eco corto: separa el sonido del altavoz.
              f"aecho=0.8:0.85:420|780:0.22|0.13,"
              f"aformat=sample_rates=44100:channel_layouts=stereo,"
              f"atrim=0:{args.dur:.2f},"
              f"afade=t=in:st=0:d=1.6,"
              f"afade=t=out:st={args.dur - args.fade_out:.2f}:d={args.fade_out:.2f},"
              # Sin loudnorm la mezcla queda inaudible en un movil (~-35 dBFS).
              f"loudnorm=I=-16:TP=-1.5:LRA=11,"
              # loudnorm remuestrea a 96 kHz por dentro; Meta espera 44.1/48.
              f"aresample=48000,"
              f"alimiter=limit=0.95[a]"
        )
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", *inputs,
            "-filter_complex", chain, "-map", "[a]",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", args.out,
        ], check=True)

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", args.out], capture_output=True, text=True).stdout.strip()
    print(f"  {args.out} — {float(out):.1f}s, {len(piezas)} capas, {compas} acordes")


if __name__ == "__main__":
    main()
