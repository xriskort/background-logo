#!/usr/bin/env python3
"""Renderiza el video final a partir de una lista de edición (EDL) en JSON.

Uso: render.py edl.json salida.mp4 [--sin-loudnorm]

Formato de la EDL (tiempos en segundos; ver references/recetas-ffmpeg.md):
{
  "fuente": "crudo.mp4",
  "pista_voz": 0,
  "segmentos": [                       # en orden de la línea de tiempo final
    {"inicio": 312.4, "fin": 318.0, "nota": "cold open"},
    {"inicio": 2.1, "fin": 45.8},
    {"inicio": 50.2, "fin": 53.0, "zoom": 1.25, "centro": [0.5, 0.4]}
  ],
  "musica": [                          # "en": tiempo en la línea FINAL
    {"archivo": "musica/ambiente.mp3", "en": 6.0, "desde": 0, "duracion": 40,
     "entrada": 1.5, "salida": 2.0, "ganancia_db": -6, "motivo": "escena normal"},
    {"archivo": "musica/comica.mp3", "en": 47.0, "duracion": 4,
     "entrada": 0, "salida": 0.3, "motivo": "remate del chiste"}
  ],
  "sfx": [{"archivo": "sfx/golpe.wav", "en": 49.6, "ganancia_db": -4, "motivo": "reacción"}],
  "ducking": true,                     # baja la música cuando hay voz
  "lufs": -14
}
"""
import argparse
import json
import os
import re
import subprocess
import sys

EMPALME = 0.015  # micro fundido en cada corte para evitar clics


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return s["width"], s["height"], float(num) / float(den)


def construir_filtro(edl):
    w, h, fps = probe(edl["fuente"])
    voz = edl.get("pista_voz", 0)
    partes, entradas = [], [edl["fuente"]]

    concat_in = ""
    for i, seg in enumerate(edl["segmentos"]):
        ini, fin = seg["inicio"], seg["fin"]
        dur = fin - ini
        v = f"[0:v]trim={ini}:{fin},setpts=PTS-STARTPTS"
        z = seg.get("zoom", 1.0)
        if z and z != 1.0:
            cx, cy = seg.get("centro", [0.5, 0.5])
            cw, ch = f"iw/{z}", f"ih/{z}"
            x = f"max(0\\,min(iw-{cw}\\,iw*{cx}-{cw}/2))"
            y = f"max(0\\,min(ih-{ch}\\,ih*{cy}-{ch}/2))"
            v += f",crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos"
        v += f",fps={fps},setsar=1[v{i}]"
        a = (f"[0:a:{voz}]atrim={ini}:{fin},asetpts=PTS-STARTPTS,"
             f"aformat=sample_rates=48000:channel_layouts=stereo,"
             f"afade=t=in:d={EMPALME},afade=t=out:st={max(dur - EMPALME, 0)}:d={EMPALME}[a{i}]")
        partes += [v, a]
        concat_in += f"[v{i}][a{i}]"
    n = len(edl["segmentos"])
    partes.append(f"{concat_in}concat=n={n}:v=1:a=1[vout][voz]")

    capas = []
    for k, pista in enumerate(edl.get("musica", []) + [dict(s, sfx=True) for s in edl.get("sfx", [])]):
        entradas.append(pista["archivo"])
        idx = len(entradas) - 1
        f = f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo"
        desde = pista.get("desde", 0)
        if "duracion" in pista:
            f += f",atrim={desde}:{desde + pista['duracion']}"
        elif desde:
            f += f",atrim=start={desde}"
        f += ",asetpts=PTS-STARTPTS"
        if pista.get("entrada"):
            f += f",afade=t=in:d={pista['entrada']}"
        if pista.get("salida") and "duracion" in pista:
            f += f",afade=t=out:st={max(pista['duracion'] - pista['salida'], 0)}:d={pista['salida']}"
        f += f",volume={pista.get('ganancia_db', 0)}dB"
        ms = int(round(pista["en"] * 1000))
        f += f",adelay={ms}|{ms}[c{k}]"
        partes.append(f)
        capas.append((f"[c{k}]", pista.get("sfx", False)))

    musica = [c for c, es_sfx in capas if not es_sfx]
    sfx = [c for c, es_sfx in capas if es_sfx]
    mezcla = ["[voz_m]"]
    partes.append("[voz]asplit=2[voz_m][voz_sc]")
    if musica:
        partes.append(f"{''.join(musica)}amix=inputs={len(musica)}:normalize=0:duration=longest[mus]")
        if edl.get("ducking", True):
            partes.append("[mus][voz_sc]sidechaincompress=threshold=0.03:ratio=8:"
                          "attack=20:release=400:makeup=1[mus_d]")
            mezcla.append("[mus_d]")
        else:
            partes.append("[voz_sc]anullsink")
            mezcla.append("[mus]")
    else:
        partes.append("[voz_sc]anullsink")
    mezcla += sfx
    partes.append(f"{''.join(mezcla)}amix=inputs={len(mezcla)}:normalize=0:duration=first,"
                  f"alimiter=limit=0.89[aout]")
    return entradas, ";".join(partes)


def ejecutar(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        sys.exit(r.returncode)
    return r.stderr


def main():
    p = argparse.ArgumentParser()
    p.add_argument("edl")
    p.add_argument("salida")
    p.add_argument("--sin-loudnorm", action="store_true")
    a = p.parse_args()

    with open(a.edl) as fh:
        edl = json.load(fh)
    salida = os.path.abspath(a.salida)
    os.chdir(os.path.dirname(os.path.abspath(a.edl)))  # rutas de la EDL relativas a su carpeta

    entradas, filtro = construir_filtro(edl)
    tmp = salida + ".premezcla.mkv"
    cmd = ["ffmpeg", "-y", "-hide_banner"]
    for e in entradas:
        cmd += ["-i", e]
    cmd += ["-filter_complex", filtro, "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s24le", "-ar", "48000", tmp]
    ejecutar(cmd)

    if a.sin_loudnorm:
        ejecutar(["ffmpeg", "-y", "-i", tmp, "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                  "-movflags", "+faststart", salida])
    else:
        objetivo = edl.get("lufs", -14)
        ln = f"loudnorm=I={objetivo}:TP=-1:LRA=11"
        log = ejecutar(["ffmpeg", "-hide_banner", "-i", tmp, "-af", ln + ":print_format=json",
                        "-f", "null", "-"])
        m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", log, re.S).group(0))
        ln2 = (f"{ln}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
               f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
               f"offset={m['target_offset']}:linear=true")
        ejecutar(["ffmpeg", "-y", "-hide_banner", "-i", tmp, "-af", ln2, "-ar", "48000",
                  "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", salida])
    os.remove(tmp)
    print(salida)


if __name__ == "__main__":
    main()
