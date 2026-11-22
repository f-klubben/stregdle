#!/bin/bash
# Nightly deploy, run from cron: `auto-deploy.sh test` follows origin/main,
# `auto-deploy.sh prod` takes the newest commit at least 24 hours old. Moves a
# checkout forward only, and refuses a dirty one.
set -uo pipefail

MODE=${1:-}
LOG=/var/log/stregdle-deploy.log

log() { printf '%s %s\n' "$(date -Is)" "$*" >>"$LOG"; }

case "$MODE" in
prod) APP=/data/stregdle; UNIT=stregdle; CUTOFF=1 ;;
test) APP=/data/stregdle-test; UNIT=stregdle-test; CUTOFF=0 ;;
*) echo "usage: $0 prod|test" >&2; exit 2 ;;
esac

git_app() { sudo -H -u stregdle git -C "$APP" "$@"; }

[ -d "$APP/.git" ] || { log "$MODE: $APP is not a checkout"; exit 1; }

if [ -n "$(git_app status --porcelain --untracked-files=no)" ]; then
    log "$MODE: $APP has local changes, refusing to deploy"
    exit 1
fi

git_app fetch --quiet --prune origin || { log "$MODE: git fetch failed"; exit 1; }

if [ "$CUTOFF" = 1 ]; then
    cutoff=$(date -d '24 hours ago' --iso-8601=seconds)
    target=$(git_app rev-list -1 --before="$cutoff" origin/main)
    [ -n "$target" ] || { log "$MODE: no commit older than $cutoff yet"; exit 0; }
else
    target=$(git_app rev-parse origin/main)
fi

head=$(git_app rev-parse HEAD)
if [ "$head" = "$target" ]; then
    log "$MODE: already at $(git_app rev-parse --short HEAD)"
    exit 0
fi
git_app merge-base --is-ancestor "$head" "$target" || {
    log "$MODE: HEAD $(git_app rev-parse --short HEAD) is ahead of $(git_app rev-parse --short "$target"), nothing to do"
    exit 0
}

git_app reset --quiet --hard "$target" || { log "$MODE: reset to $target failed"; exit 1; }
sudo -H -u stregdle bash -c "cd '$APP' && ./venv/bin/pip install --quiet '.[prod]'" || log "$MODE: pip install failed"
sudo -H -u stregdle bash -c "cd '$APP' && ./venv/bin/python manage.py collectstatic --noinput" >/dev/null 2>&1 || log "$MODE: collectstatic failed"
systemctl restart "$UNIT"
sleep 3
if systemctl is-active --quiet "$UNIT"; then
    log "$MODE: deployed $(git_app rev-parse --short HEAD), restarted $UNIT"
else
    log "$MODE: $UNIT is NOT active after deploying $target"
    exit 1
fi
