#!/bin/sh
# Aktualisiert HomeAtlas auf den Stand des Repos, zeigt danach, welche Version wirklich läuft.
set -e
cd "$(dirname "$0")"
echo "== Repo =="
git pull --ff-only
git log -1 --format='Stand: %h %s (%cd)' --date=short
echo "== Container neu bauen und starten =="
# Umbenennung LabVis → HomeAtlas: der alte Container „labvis“ würde sonst den Port belegen
if docker ps -a --format '{{.Names}}' | grep -qx labvis; then docker rm -f labvis >/dev/null && echo "alter Container labvis entfernt"; fi
# Der Compose-Projektname ist fest „homeatlas“. Ein Container aus dem alten Projekt (früher nach dem
# Ordner benannt, z. B. /opt/labvis) wird entfernt und neu angelegt. Die Daten liegen in ./data.
old=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' homeatlas 2>/dev/null || true)
if [ -n "$old" ] && [ "$old" != "homeatlas" ]; then docker rm -f homeatlas >/dev/null && echo "Container aus altem Projekt $old entfernt"; fi
docker compose up -d --build --force-recreate --remove-orphans
if docker image inspect labvis:latest >/dev/null 2>&1; then docker image rm labvis:latest >/dev/null 2>&1 && echo "altes Image labvis entfernt" || true; fi
sleep 6
echo "== Läuft jetzt =="
docker compose exec -T homeatlas python -c "import os,urllib.request as u;print(u.urlopen('http://127.0.0.1:%s/healthz'%os.environ['HOMEATLAS_PORT'],timeout=5).read().decode())"
docker compose ps --format 'Container: {{.Name}} · {{.Status}} · Image {{.Image}}'
