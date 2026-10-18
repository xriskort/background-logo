---
name: edicion-estilo-rubius
description: Edita el video principal de YouTube con un estilo natural y gracioso inspirado en El Rubius — música elegida por escena con ducking bajo la voz, cortes de silencios y partes aburridas sin perder las reacciones, zooms y efectos de sonido puntuales, cold open breve y final natural. Úsala cuando el usuario pida editar, montar, cortar o musicalizar su video principal de YouTube, un gameplay o un vlog "estilo Rubius", o con un ritmo de YouTuber de entretenimiento. Aplica la edición al archivo real con ffmpeg; no te limites a explicar cómo hacerlo.
---

# Edición del video principal — estilo inspirado en El Rubius

Objetivo: un video **sencillo, natural, gracioso y entretenido**. La edición está al
servicio del contenido: sabe cuándo dejar que el momento hable solo y cuándo darle
fuerza. Nada de transiciones, animaciones ni efectos cada pocos segundos.

El Rubius es **referencia de estilo, no fuente de material**: no copies sus videos,
montajes exactos ni audios. Nunca descargues ni reutilices canciones o efectos de sus
videos.

**Regla de acción:** si hay herramientas de edición disponibles (ffmpeg/ffprobe,
Python), aplica las decisiones al video real y exporta el resultado. Explicar sin
editar no cumple la tarea.

---

## Flujo de trabajo

### 0. Inventario
1. Localiza el video fuente y las carpetas de música y efectos (SFX) del usuario.
   Pregunta solo si no existen.
2. `ffprobe` del video: duración, resolución, fps, pistas de audio (¿voz y juego van
   en pistas separadas? aprovéchalo).
3. Música y SFX: usa **solo** archivos con licencia apta para YouTube (Biblioteca de
   audio de YouTube, Epidemic/Artlist del usuario, CC0/CC-BY con atribución, o lo que
   el usuario aporte con licencia). Registra en `licencias.txt` el origen de cada pista.
   Si no hay música con licencia disponible, edita sin música y dilo; no la inventes
   ni la descargues de fuentes dudosas.

### 1. Entender el contenido antes de cortar
- Transcribe la voz (whisper si está instalado; si no, analiza por energía/silencios
  con `scripts/analizar_audio.py`) y genera un **mapa de escenas** con marcas de
  tiempo: qué pasa, tono (normal / gracioso / tensión / sorpresa / tranquilo /
  absurdo) y si hay reacción del creador.
- Marca los **mejores momentos** (candidatos al cold open) y los tramos muertos.
- Escribe el mapa en `edicion/plan.md`. Ahí van todas las decisiones con su motivo.

### 2. Cortes y ritmo
- `python3 scripts/analizar_audio.py video.mp4` → lista de silencios y segmentos con
  voz. Úsala como **propuesta**, no como verdad: revisa cada corte contra el contexto.
- Elimina: silencios largos (orientativo > 0.8–1.2 s sin acción en pantalla), pausas
  innecesarias, tomas repetidas (quédate con la mejor), tramos que se alargan sin
  aportar.
- Conserva: reacciones espontáneas, risas, conversaciones interesantes, y la **pausa
  que hace gracioso un chiste**. Un silencio después de algo absurdo puede ser el
  chiste.
- Deja ~0.15–0.3 s de colchón antes y después de cada frase para que no suene
  recortado. No cortes tan rápido que no se entienda lo que pasa.
- Zoom puntual (1.1–1.3×, corte seco o empuje rápido) solo cuando una reacción,
  expresión o detalle lo merezca. Como referencia, unas pocas veces por cada 10 min,
  nunca de forma constante.
- Recetas concretas en `references/recetas-ffmpeg.md`.

### 3. Música — cada pista con un motivo
Para cada escena del plan decide: **música / sin música (audio original) / cambio**.
Anota en el plan *por qué*.

| Situación | Tratamiento |
|---|---|
| Escena normal | Ambiental discreta, o audio original |
| Algo gracioso / absurdo | Fragmento cómico o cambio musical que remate el chiste |
| Tensión, espera, expectativa | Música que construye; deja que el momento se desarrolle |
| Sorpresa / giro inesperado | La música **se corta en seco** o cambia justo en el golpe |
| Momento tranquilo | Música muy baja o ninguna |
| Tras el chiste | Micro-pausa (0.3–0.8 s) antes de volver a la música |

Reglas:
- No hace falta música todo el rato. No cambies de canción sin motivo, y no dejes la
  misma canción si ya no encaja con lo que pasa.
- Entradas/salidas: fundidos suaves (0.5–2 s) en transiciones normales; cortes secos
  cuando el corte **es** el chiste o la sorpresa.
- Corta la música en compases/frases musicales cuando sea posible, no a mitad de nota.
- **Ducking:** la música baja automáticamente cuando hablas (sidechain sobre la voz).
  Niveles orientativos: voz ≈ −16 a −14 LUFS en la mezcla; música bajo voz ≈ −28 a
  −24 LUFS; música sola (sin voz) ≈ −20 a −18 LUFS.

### 4. Humor y efectos de sonido
- SFX solo si mejoran el chiste o destacan una reacción: un golpe, un "boing", un
  silencio repentino, un acorde de sorpresa. Pocos y bien colocados.
- Nunca: lluvia de memes, sonidos fuertes repetidos, imágenes superpuestas
  constantes, el mismo efecto una y otra vez.
- Si una escena no necesita chiste, no lo fuerces. Pausa + zoom + corte suelen
  bastar.
- SFX nunca por encima de la voz; normaliza su pico a ≈ −6 dBFS antes de mezclar.

### 5. Estructura
1. **Cold open** (opcional, 3–10 s): uno de los mejores momentos, si engancha. Corta
   antes del remate para no destriparlo.
2. Entrada directa al contenido; nada de intros largas.
3. Alterna momentos intensos y tranquilos; que la curva de energía respire.
4. Mantén el contexto: no es un montaje de clips sueltos.
5. Final natural: cuando la historia acaba, el video acaba. Sin estirarlo.

### 6. Montaje y exportación
- Construye una **lista de edición** (`edicion/edl.json`: segmentos de origen,
  zooms, entradas de música con fundidos, SFX con tiempos) y renderiza desde ella
  con `scripts/render.py edicion/edl.json salida.mp4`. Así es reproducible y fácil de
  retocar.
- Exporta: H.264 (`-crf 18 -preset medium`, `yuv420p`), AAC 320k 48 kHz, misma
  resolución/fps de la fuente, loudness final **−14 LUFS integrado, true peak
  ≤ −1 dBTP** (`loudnorm` en dos pasadas).

### 7. Revisión obligatoria antes de entregar
Revisa el resultado completo (no solo el plan):
- [ ] La voz se entiende en todo momento (`analizar_audio.py --loudness` sobre el
      export y revisa los tramos con música bajo la voz).
- [ ] Ninguna transición de audio brusca no intencionada (clics en cortes → micro
      fundidos de 10–20 ms en cada empalme).
- [ ] Cada pista musical encaja con su escena y tiene motivo en el plan.
- [ ] No hay efectos que distraigan sin aportar. Si dudas de uno, quítalo.
- [ ] Los chistes respiran; ningún corte se come un remate o una reacción.
- [ ] Inicio enganchante, final sin relleno.
- [ ] `licencias.txt` completo.
- [ ] Extrae fotogramas de los zooms y escucha (o analiza) 5–10 s alrededor de cada
      cambio de música y cada SFX.

Entrega: el video exportado, `edicion/plan.md` (decisiones y motivos) y
`licencias.txt`. Resume al usuario qué se cortó, dónde va la música y por qué, y
cualquier punto que convenga que revise a ojo.
