# Recetas ffmpeg para la edición

Todas las rutas de la EDL son relativas a la carpeta del `edl.json`.

## Flujo mínimo
```bash
python3 scripts/analizar_audio.py crudo.mp4 > edicion/silencios.json   # propuesta de cortes
# → escribir edicion/plan.md (escenas, tono, decisiones y motivos)
# → escribir edicion/edl.json (segmentos, zooms, música, sfx)
python3 scripts/render.py edicion/edl.json final.mp4                    # render + loudnorm 2 pasadas
python3 scripts/analizar_audio.py final.mp4 --loudness                  # revisión de niveles
```

## Ajustar la detección de silencios
- Micro con ruido de fondo / juego alto: sube el umbral (`--umbral -30`).
- Voz suave o susurros: bájalo (`--umbral -42`).
- Si la voz va en una pista separada, analiza esa: `--pista 1`. En la EDL usa
  `"pista_voz": 1`. Si voz y juego van en pistas distintas, mézclalas antes en un
  archivo intermedio y mantén la de voz para el sidechain.

## Zoom puntual
En un segmento: `"zoom": 1.2, "centro": [x, y]` (0–1, fracción de ancho/alto).
Para un zoom solo en parte de una toma, divide el segmento en dos/tres segmentos
contiguos y pon el zoom solo en el del medio (corte seco = estilo YouTube natural).

## Música
- `"en"`: segundo de la línea de tiempo **final** donde entra.
- `"desde"`/`"duracion"`: qué fragmento de la canción se usa.
- `"entrada"`/`"salida"`: fundidos en segundos. `0` = entrada/corte seco (útil para
  sorpresas o cuando el corte es el chiste).
- `"ganancia_db"`: nivel base antes del ducking. Ambiental ≈ −8 a −12 dB, cómica
  breve ≈ −4 a −6 dB (dependen del master de la pista: mide y ajusta).
- Para calcular "en", suma las duraciones de los segmentos anteriores.

## Ducking
Activado por defecto (`sidechaincompress` sobre la voz: threshold 0.03, ratio 8,
attack 20 ms, release 400 ms). Si la música "bombea" demasiado, sube `release`
(600–800 ms) editando `render.py`, o baja la `ganancia_db` de la pista.

## Comprobaciones rápidas
```bash
# Fotograma de un zoom para revisarlo
ffmpeg -ss 47.2 -i final.mp4 -frames:v 1 revision_zoom.png
# Recorte de 10 s alrededor de un cambio de música
ffmpeg -ss 42 -t 10 -i final.mp4 -c copy revision_cambio.mp4
# Loudness integrado y true peak final
ffmpeg -i final.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -12
```

## Fuentes de música y SFX con licencia
Biblioteca de audio de YouTube (Studio → Biblioteca de audio), suscripciones del
usuario (Epidemic Sound, Artlist…), Pixabay Music/Freesound (revisa la licencia de
cada archivo; CC-BY requiere atribución en la descripción). Anótalo todo en
`licencias.txt`: archivo, fuente, licencia, atribución requerida.
