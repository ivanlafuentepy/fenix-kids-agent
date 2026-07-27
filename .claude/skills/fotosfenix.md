---
name: fotosfenix
description: Pipeline semanal de fotos - ordena la bandeja FENIX FOTOS/FOTOS por fecha, publica las fotos nuevas en fenixkidsacademy.com/fotos/ y avisa a Ivan por WhatsApp con el link
---

# FOTOSFENIX — Publicar fotos nuevas de los entrenamientos

## Overview

Todo el pipeline vive en UN script (misma fuente de verdad que el botón
"FOTOS FENIX.bat" del Escritorio de Iván):

```bash
py -3 "C:\Users\IVAN LAFUENTE\Projects\fenixkidsacademy-web\scripts\publicar_fotos.py"
```

Qué hace (incremental y re-ejecutable, si no hay nada nuevo no comitea ni avisa):
1. Ordena la bandeja `Desktop\FENIX FOTOS\FOTOS` en carpetas por fecha (fotos Y videos; los videos NO se suben).
2. Publica las fotos nuevas (optimizar → commit solo `fotos/assets` → push → Cloudflare Pages).
3. Taggea caras para los links familiares (`--solo-incremental`: aborta solo si el batch inicial nunca fue aplicado).
4. Verifica que la web sirva el total nuevo y le manda WhatsApp a Iván (595982790407) via Railway.

## Steps

1. Correr el script con `PYTHONIOENCODING=utf-8`.
2. Leer TODO el output y reportar: fotos publicadas y de qué fechas, videos ordenados,
   archivos "Sin fecha", si el tagueo corrió o quedó pendiente, y si el WhatsApp salió.
3. Si algo falló a mitad de camino, decir QUÉ paso quedó hecho y qué no.
4. Cerrar con "✅ Verificado: [qué se revisó]".

## Reglas duras

- El WhatsApp va SOLO a 595982790407 — avisar a familias es otro flujo (con OK explícito de Iván).
- No "arreglar" a mano lo que el script ya hace: si falla, diagnosticar la causa raíz en el script.
