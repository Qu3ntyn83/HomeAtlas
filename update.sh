#!/bin/sh
# Aktualisiert LabVis auf den Stand des Repos und zeigt danach, welche Version wirklich läuft.
set -e
cd "$(dirname "$0")"
echo "== Repo =="
git pull --ff-only
git log -1 --format='Stand: %h %s (%cd)' --date=short
echo "== Container neu bauen und starten =="
docker compose up -d --build --force-recreate
sleep 6
echo "== Läuft jetzt =="
docker compose exec -T labvis python -c "import os,urllib.request as u;print(u.urlopen('http://127.0.0.1:%s/healthz'%os.environ['LABVIS_PORT'],timeout=5).read().decode())"
docker compose ps --format 'Container: {{.Name}} · {{.Status}} · Image {{.Image}}'
