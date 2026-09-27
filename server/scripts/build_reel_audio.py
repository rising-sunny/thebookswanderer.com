#!/usr/bin/env python3
"""
Base ambiental sin copyright para los reels, sintetizada con ffmpeg.

Por que generada y no una pista comercial: una cancion con derechos hace que
Meta silencie el reel, lo bloquee por region o le recorte el alcance. Esto es
100% libre y queda dentro del repo.

Que suena: notas de una pentatonica menor en La, cada una con ataque rapido y
cola larga (una envolvente de campana o piano con pedal), solapadas para que
nunca haya silencio. Pentatonica porque cualquier combinacion de sus notas
suena consonante: no hay riesgo de que dos colas solapadas choquen.

    python3 scripts/build_reel_audio.py --dur 19 --out /root/bed.m4a
"""
from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

# La menor pentatonica, dos octavas. Hz.
NOTAS = [220.00, 261.63, 293.66, 329.63, 392.00,
         440.00, 523.25, 587.33, 659.25, 783.99]

# Melodia por indices: sube, respira, baja. Suena intencional, no aleatoria.
PATRON = [0, 2, 4, 5, 4, 7, 5, 4, 2, 5, 4, 2, 0, 2, 4, 2, 0]

COLA = 3.2   # segundos que tarda una nota en apagarse
PASO = 1.15  # segundos entre ataques; menor que COLA -> se solapan


def main() -> None:
    ap = argparse.ArgumentParser(description="Base ambiental para reels.")
    ap.add_argument("--dur", type=float, default=19.0)
    ap.add_argument("--out", default="/root/bed.m4a")
    ap.add_argument("--fade-out", type=float, default=2.5)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        notas: list[Path] = []
        t = 0.0
        i = 0
        while t < args.dur:
            f = NOTAS[PATRON[i % len(PATRON)]]
            dur = min(COLA, args.dur - t + 0.8)
            dst = tmp / f"n{i:03d}.wav"
            # Fundamental + octava a un tercio: da cuerpo sin sonar a sintetizador.
            # La envolvente exponencial es lo que convierte un tono plano en
            # algo parecido a una cuerda pulsada.
            expr = (f"0.5*sin(2*PI*{f}*t)*exp(-2.6*t)"
                    f"+0.17*sin(2*PI*{f*2}*t)*exp(-3.4*t)")
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d={dur:.2f}",
                "-af", "afade=t=out:st=%.2f:d=0.35" % max(dur - 0.35, 0.1),
                "-c:a", "pcm_s16le", str(dst),
            ], check=True)
            notas.append(dst)
            t += PASO
            i += 1

        # amix normaliza por numero de entradas: sin compensar, cada nota
        # anadida baja el volumen de todas.
        inputs: list[str] = []
        delays: list[str] = []
        for n, p in enumerate(notas):
            inputs += ["-i", str(p)]
            ms = int(n * PASO * 1000)
            delays.append(f"[{n}:a]adelay={ms}|{ms}[d{n}]")
        mix = "".join(f"[d{n}]" for n in range(len(notas)))
        ganancia = math.sqrt(len(notas)) * 0.55
        chain = (
            ";".join(delays)
            + f";{mix}amix=inputs={len(notas)}:duration=longest:dropout_transition=0[m]"
            + f";[m]volume={ganancia:.2f},"
              f"aformat=sample_rates=44100:channel_layouts=stereo,"
              f"atrim=0:{args.dur:.2f},"
              f"afade=t=in:st=0:d=1.2,"
              f"afade=t=out:st={args.dur - args.fade_out:.2f}:d={args.fade_out:.2f},"
              # Sin loudnorm la mezcla sale a ~-35 LUFS (inaudible en un movil)
              # y sube sola hacia el final, porque las colas se acumulan.
              # loudnorm fija -16 LUFS, que es el objetivo de redes, y de paso
              # aplana esa deriva. El limitador va despues, como red de
              # seguridad contra picos.
              f"loudnorm=I=-16:TP=-1.5:LRA=11,"
              # loudnorm remuestrea a 96 kHz por dentro. Meta y TikTok esperan
              # 44.1/48 kHz; hay que volver a bajarlo DESPUES del filtro.
              f"aresample=48000,"
              f"alimiter=limit=0.95[a]"
        )
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", *inputs,
            "-filter_complex", chain, "-map", "[a]",
            "-c:a", "aac", "-b:a", "128k", args.out,
        ], check=True)

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", args.out], capture_output=True, text=True).stdout.strip()
    print(f"  {args.out} — {float(out):.1f}s, {len(notas)} notas")


if __name__ == "__main__":
    main()
