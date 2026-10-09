# Vídeo v4 en 4K, para subir a YouTube

`video_v4_4k.mp4` es el archivo para subir a YouTube: 3840×2160, 30 fps, H.264 y audio AAC estéreo a 256 kb/s.
GitHub no admite archivos de más de 100 MB, así que está partido en trozos de 95 MB. Hay que unirlos antes de subirlo.

## Cómo unir los trozos

Descarga todos los archivos `video_v4_4k.mp4.partN` en la misma carpeta y ejecuta en ella uno de estos comandos.

**Windows (CMD):**

```
copy /b video_v4_4k.mp4.part0 + video_v4_4k.mp4.part1 + video_v4_4k.mp4.part2 video_v4_4k.mp4
```

Si hay más trozos, añádelos en orden con `+`.

**PowerShell, para comprobar que el archivo unido es idéntico al original:**

```
Get-FileHash video_v4_4k.mp4 -Algorithm SHA256
```

El resultado tiene que coincidir con el que aparece en `SHA256.txt`.

**Mac / Linux:**

```
cat video_v4_4k.mp4.part* > video_v4_4k.mp4
shasum -a 256 video_v4_4k.mp4
```

## Por qué en 4K

Para los vídeos que se suben en 1440p o 4K, YouTube usa códecs mejores (VP9 o AV1) y más bitrate, también para quien los ve en 1080p.
El vídeo se renderiza a 1080p sin pérdidas visibles y se escala ×2 con Lanczos, así que el texto y los gráficos se ven nítidos.

`../video_v4.mp4` (menos de 95 MB) es una copia en 1080p para verlo rápido. No es la versión para subir.
