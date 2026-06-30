# garmin-coach

[English](README.md) | Español

`garmin-coach` es un proyecto personal en Python construido sobre `python-garminconnect` para:

- sincronizar datos de Garmin Connect en local
- generar artefactos JSON deterministas
- construir resúmenes y exports derivados
- crear y subir entrenamientos de running y bicicleta a Garmin

## Alcance

Funciones actuales:

- autenticación local segura con `.env` y reutilización de tokens Garmin
- sincronización diaria y por ventana de fechas
- resúmenes por actividad
- exports derivados de Garmin en niveles low / medium / full
- generación, subida y programación opcional de workouts de running y bicicleta

El proyecto está pensado para uso local. Guarda datos Garmin en disco para análisis personal y uso posterior.

## Requisitos

- Python 3.12 o superior
- una cuenta de Garmin Connect
- ejecutar los comandos desde la raíz del repositorio

## Instalación

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

## Configuración

1. Copiar `.env.example` a `.env`
2. Completar al menos `GARMIN_EMAIL` y `GARMIN_PASSWORD`
3. Mantener `.env`, `.secrets/`, `data/` y los logs locales fuera del control de versiones

```bash
cp .env.example .env
```

## Privacidad

Este proyecto maneja datos personales de salud y actividad.

- no subas `.env`, `.secrets/` ni `data/`
- tratá `data/raw/` y `data/summaries/` como información privada
- los exports `full` pueden incluir payloads raw de Garmin y no deberían compartirse públicamente
- la salida de CLI intenta omitir datos de identidad cuando es posible, pero los JSON locales siguen conteniendo datos sensibles

## Comandos principales

Validar autenticación Garmin:

```bash
garmin-coach login-test
```

Sincronizar un día:

```bash
garmin-coach sync-daily --date 2026-03-24
```

Sincronizar un día y construir exports:

```bash
garmin-coach sync-daily --date 2026-03-24 --build-exports
```

Sincronizar una ventana reciente y el detalle de actividades:

```bash
garmin-coach sync-last-30-days --end-date 2026-03-24
```

Sincronizar una ventana reciente y construir sólo el export `medium`:

```bash
garmin-coach sync-last-30-days --end-date 2026-03-24 --build-exports --export-level medium
```

Sincronizar 30 días, construir un único `medium` y resumir también cada actividad:

```bash
garmin-coach sync-last-30-days --end-date 2026-03-24 --days 30 --build-exports --export-level medium --build-activity-summaries
```

Sincronizar hasta una fecha límite e indicar cuántos días hacia atrás traer:

```bash
garmin-coach sync-last-30-days --end-date 2026-04-01 --days 7
```

Eso trae una ventana inclusiva desde `2026-03-26` hasta `2026-04-01`.

Sincronizar ayer y hoy, construyendo también el resumen diario y los ejercicios separados por fecha:

```bash
garmin-coach sync-last-30-days --end-date 2026-04-01 --days 2 --build-exports --export-level medium --build-activity-summaries
```

Si preferís hacerlo día por día:

```bash
garmin-coach sync-daily --date 2026-03-31 --build-exports --export-level medium --build-activity-summaries
garmin-coach sync-daily --date 2026-04-01 --build-exports --export-level medium --build-activity-summaries
```

Construir el contexto derivado de Garmin:

```bash
garmin-coach coach-build-context --date 2026-03-24
```

Construir exports:

```bash
garmin-coach coach-build-exports --date 2026-03-24
garmin-coach coach-build-exports --date 2026-03-24 --level medium
garmin-coach coach-build-exports --date 2026-03-24 --days 30 --level medium
```

Construir resúmenes para todas las actividades sincronizadas:

```bash
garmin-coach activities-build-summaries
```

Construir resúmenes de actividades para un rango de fechas:

```bash
garmin-coach activities-build-summaries --start-date 2026-03-31 --end-date 2026-04-01
```

Construir resúmenes de actividades para una única fecha:

```bash
garmin-coach activities-build-summaries --date 2026-04-01
```

Construir el resumen de una actividad puntual:

```bash
garmin-coach activities-build-summaries --activity-id 21964227769
```

Crear un workout de running y guardarlo localmente como JSON:

```bash
garmin-coach workout-create-running-intervals \
  --name "Media maraton 5x1000m 5:15-5:25" \
  --warmup-km 2 \
  --repeats 5 \
  --interval-m 1000 \
  --pace-range 5:15-5:25 \
  --recovery 2:00 \
  --cooldown-km 1-2
```

Crear el mismo workout y subirlo a Garmin Connect:

```bash
garmin-coach workout-create-running-intervals \
  --name "Media maraton 5x1000m 5:15-5:25" \
  --warmup-km 2 \
  --repeats 5 \
  --interval-m 1000 \
  --pace-range 5:15-5:25 \
  --recovery 2:00 \
  --cooldown-km 1-2 \
  --upload
```

Subirlo y programarlo para una fecha concreta del calendario Garmin:

```bash
garmin-coach workout-create-running-intervals \
  --name "Media maraton 5x1000m 5:15-5:25" \
  --warmup-km 2 \
  --repeats 5 \
  --interval-m 1000 \
  --pace-range 5:15-5:25 \
  --recovery 2:00 \
  --cooldown-km 1-2 \
  --upload \
  --schedule-date 2026-03-28
```

Crear un workout de bicicleta y guardarlo localmente como JSON:

```bash
garmin-coach workout-create-cycling-intervals \
  --name "Bici 5x4min Z4" \
  --warmup 15:00 \
  --repeats 5 \
  --interval-duration 4:00 \
  --recovery 2:00 \
  --cooldown 10:00 \
  --interval-target "Z4"
```

Crear el mismo workout de bicicleta y subirlo a Garmin Connect:

```bash
garmin-coach workout-create-cycling-intervals \
  --name "Bici 5x4min Z4" \
  --warmup 15:00 \
  --repeats 5 \
  --interval-duration 4:00 \
  --recovery 2:00 \
  --cooldown 10:00 \
  --interval-target "Z4" \
  --upload
```

Subirlo y programarlo para una fecha concreta del calendario Garmin:

```bash
garmin-coach workout-create-cycling-intervals \
  --name "Bici 5x4min Z4" \
  --warmup 15:00 \
  --repeats 5 \
  --interval-duration 4:00 \
  --recovery 2:00 \
  --cooldown 10:00 \
  --interval-target "Z4" \
  --upload \
  --schedule-date 2026-03-28
```

Cargar un workout de bicicleta con bloque aeróbico separado y objetivos por paso:

```bash
garmin-coach workout-create-cycling-intervals \
  --name "Bici 4x8 controlado + aerobico" \
  --warmup 15:00 \
  --warmup-target "Suave, RPE 3/10, cadencia 85-95 rpm" \
  --repeats 4 \
  --interval-duration 8:00 \
  --interval-target "Fuerte controlado, RPE 7/10, sostenible, cadencia 85-95 rpm" \
  --recovery 4:00 \
  --recovery-target "Suave, RPE 3/10, recuperar bien" \
  --keep-last-recovery \
  --steady-duration 20:00 \
  --steady-target "Zona comoda/media, RPE 5/10, sin apretar" \
  --cooldown 10:00 \
  --cooldown-target "Muy suave" \
  --upload
```

Ver qué JSON se borrarían:

```bash
garmin-coach purge-json --dry-run
```

Borrar artefactos JSON generados bajo `data/raw`, `data/normalized` y `data/summaries`:

```bash
garmin-coach purge-json
```

## Datos generados

Los payloads raw de Garmin se guardan en rutas deterministas como:

- `data/raw/account/profile/current.json`
- `data/raw/daily/user_summary/2026-03-24.json`
- `data/raw/daily/sleep/2026-03-24.json`
- `data/raw/activities/by_id/<activity_id>/details.json`

El proyecto también escribe artefactos derivados como:

- `data/normalized/coach/athlete_profile/current.json`
- `data/summaries/coach/packets/<date>.json`
- `data/summaries/coach/exports/low/<date>.json`
- `data/summaries/coach/exports/medium/<date>.json`
- `data/summaries/coach/exports/full/<date>.json`
- `data/summaries/coach/exports/<level>/latest.json`
- `data/summaries/activities/by_date/<activity_date>_<time>_<activity_name>_<activity_id>.json`
- `data/summaries/workouts/running/<timestamp>_<workout_name>.json`

Niveles de export:

- `low`: snapshot liviano de Garmin más carga reciente
- `medium`: contexto diario más completo, sesiones recientes, tiempos en zonas y métricas por disciplina
- `full`: resumen derivado más payloads raw de Garmin para la fecha o ventana

SQLite se usa localmente para trackear hashes de artefactos y reportes de sync, evitando reescrituras innecesarias.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Notas

- la disponibilidad de métricas depende del dispositivo Garmin, la cuenta y el soporte real de cada endpoint
- el sync intenta continuar aunque una métrica puntual no esté disponible
- algunos recursos se superponen según el dispositivo, especialmente `stress` y `body_battery`


garmin-coach sync-last-30-days --end-date 2026-06-10 --days 7 --build-exports --export-level medium --build-activity-summaries