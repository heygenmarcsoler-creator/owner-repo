# EuroindexLab: producción de vídeos

| Carpeta | Contenido |
|---|---|
| `research/analisis_competencia_seo.md` | Análisis de competencia, tendencias (octubre de 2026) y paquete SEO |
| `video/script.py` | Guion (inglés) + escenas v2: una frase por escena, pausas interactivas (`Q`), sellos, donuts, cara a cara, líneas del tiempo, cintas de titulares |
| `video/data.py` | Datos: MSCI World net EUR 2000–2026, bonos de gobierno euro, simulaciones |
| `video/engine.py` | Motor gráfico con el estilo del canal (Space Grotesk, JetBrains Mono, Inter) |
| `video/tts.py` | Narración con Gemini TTS (voz `Iapetus`), un bloque por capítulo |
| `video/sphinx_align.py` | Alineación forzada palabra a palabra (PocketSphinx) para los subtítulos |
| `video/music.py` | Música de fondo y efectos generados por código (sin derechos de terceros) |
| `video/build.py` | Línea de tiempo (voz ×1,05, pausas recortadas) → mezcla con efectos → render 1080p30 con cámara, transiciones y barra de capítulos → MP4 |
| `video/thumbnail.py` | 3 miniaturas para prueba A/B (1280×720) |
| `video/metadata.py` | Título, descripción con capítulos, etiquetas y miniatura |
| `video/assets/tts/` | Narración generada (FLAC), para no tener que regenerarla |

## Cómo regenerar

```bash
pip install numpy pillow pocketsphinx
cd video
mkdir -p build/tts && for f in assets/tts/*.flac; do ffmpeg -y -i $f build/tts/$(basename $f .flac).wav; done && cp assets/tts/*.json build/tts/
GEMINI_API_KEY=... python3 tts.py      # solo genera los bloques que faltan
python3 build.py all                   # alineación, audio y vídeo -> output/video.mp4
python3 metadata.py                    # output/youtube_metadata.md + output/thumbnail.jpg
```

La clave de la API **nunca** se guarda en el repositorio: se pasa por `GEMINI_API_KEY` o con un `.env` externo (`ENV_FILE`).
