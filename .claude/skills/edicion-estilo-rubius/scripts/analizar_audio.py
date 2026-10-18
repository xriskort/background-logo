#!/usr/bin/env python3
"""Analiza el audio de un video: silencios, segmentos con voz y loudness por segundo.

Uso:
  analizar_audio.py VIDEO [--umbral -35] [--min-silencio 0.8] [--pista 0]
  analizar_audio.py VIDEO --loudness      # LUFS short-term por segundo (revisar mezcla)

Salida: JSON por stdout. Los cortes son una propuesta; revísalos contra el contexto.
"""
import argparse
import json
import re
import subprocess
import sys


def duracion(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def silencios(video, umbral, minimo, pista):
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-map", f"0:a:{pista}",
           "-af", f"silencedetect=noise={umbral}dB:d={minimo}", "-f", "null", "-"]
    log = subprocess.run(cmd, capture_output=True, text=True).stderr
    inicios = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    finales = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    total = duracion(video)
    res = []
    for i, ini in enumerate(inicios):
        fin = finales[i] if i < len(finales) else total
        res.append({"inicio": round(max(ini, 0), 3), "fin": round(fin, 3),
                    "duracion": round(fin - max(ini, 0), 3)})
    return res, total


def segmentos_voz(sil, total, colchon=0.2):
    segs, cursor = [], 0.0
    for s in sil:
        if s["inicio"] > cursor:
            segs.append({"inicio": round(max(cursor - colchon, 0), 3),
                         "fin": round(min(s["inicio"] + colchon, total), 3)})
        cursor = s["fin"]
    if cursor < total:
        segs.append({"inicio": round(max(cursor - colchon, 0), 3), "fin": round(total, 3)})
    return segs


def loudness(video, pista):
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "verbose", "-i", video,
           "-map", f"0:a:{pista}", "-af", "ebur128", "-f", "null", "-"]
    log = subprocess.run(cmd, capture_output=True, text=True).stderr
    por_seg = {}
    for t, s in re.findall(r"t:\s*([\d.]+)\s.*?S:\s*(-?[\d.]+)", log):
        if float(s) > -70:  # por debajo es silencio digital
            por_seg[int(float(t))] = round(float(s), 1)
    integ = re.search(r"Integrated loudness:\s*I:\s*(-?[\d.]+)", log)
    return {"integrado_lufs": float(integ.group(1)) if integ else None,
            "short_term_por_segundo": por_seg}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--umbral", type=float, default=-35, help="dB bajo los que se considera silencio")
    p.add_argument("--min-silencio", type=float, default=0.8, help="segundos mínimos de silencio")
    p.add_argument("--pista", type=int, default=0, help="índice de pista de audio (voz)")
    p.add_argument("--loudness", action="store_true")
    a = p.parse_args()

    if a.loudness:
        json.dump(loudness(a.video, a.pista), sys.stdout, indent=1)
        return
    sil, total = silencios(a.video, a.umbral, a.min_silencio, a.pista)
    json.dump({"duracion": round(total, 3), "silencios": sil,
               "segmentos_con_audio": segmentos_voz(sil, total),
               "tiempo_eliminable": round(sum(s["duracion"] for s in sil), 3)},
              sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
