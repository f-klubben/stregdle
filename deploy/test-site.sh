#!/bin/bash
# Build or refresh the Stregsystemdle test site: own checkout, venv, unit and Caddy
# block, replaying yesterday's answer. Run as root after pushing.
set -uo pipefail
exec >/tmp/stregdle-test-setup.out 2>&1

APP=/data/stregdle-test
HOST=test.stregdle.fklub.dk
PROD=/data/stregdle/stregdle.env
ENVF=$APP/stregdle-test.env
PY=/usr/local/bin/python3.11
HERE=$(cd "$(dirname "$0")" && pwd)

if [ -d "$APP/.git" ]; then
    sudo -H -u stregdle git -C "$APP" fetch --quiet origin
    sudo -H -u stregdle git -C "$APP" reset --quiet --hard origin/main
else
    install -d -o stregdle -g stregdle "$APP"
    sudo -H -u stregdle git clone --quiet --depth 1 https://github.com/f-klubben/stregdle.git "$APP"
fi
echo "HEAD: $(sudo -H -u stregdle git -C "$APP" rev-parse --short HEAD)"

if [ ! -x "$APP/venv/bin/gunicorn" ]; then
    sudo -u stregdle "$PY" -m venv "$APP/venv"
    sudo -u stregdle "$APP/venv/bin/pip" install --quiet --upgrade pip
fi
sudo -u stregdle bash -c "cd '$APP' && ./venv/bin/pip install --quiet '.[prod]'" || echo "pip install failed"

# Copy production's env so the read-only database credentials carry over, then
# override everything that makes this instance the test site.
[ -f "$ENVF" ] || cp "$PROD" "$ENVF"
sed -i -e '/^STREGDLE_SECRET_KEY=/d' -e '/^STREGDLE_ALLOWED_HOSTS=/d' -e '/^STREGDLE_HTTPS=/d' -e '/^STREGDLE_STATS_DIR=/d' -e '/^STREGDLE_DAY_OFFSET=/d' "$ENVF"
printf '%s=%s\n' STREGDLE_ALLOWED_HOSTS "$HOST" STREGDLE_HTTPS 1 STREGDLE_STATS_DIR "$APP/var" STREGDLE_DAY_OFFSET 1 >>"$ENVF"
grep -q '^STREGDLE_SECRET_KEY=' "$ENVF" || printf '%s=%s\n' STREGDLE_SECRET_KEY "$("$PY" -c 'import secrets; print(secrets.token_urlsafe(50))')" >>"$ENVF"
chown stregdle:stregdle "$ENVF"
chmod 600 "$ENVF"
install -d -o stregdle -g stregdle "$APP/var" "$APP/staticfiles"

sudo -u stregdle bash -c "cd '$APP' && ./venv/bin/python manage.py collectstatic --noinput" | tail -2
sudo -u stregdle bash -c "cd '$APP' && set -a && . ./stregdle-test.env && set +a && ./venv/bin/python manage.py dbcheck" 2>&1 | tail -8

install -m 644 -o root -g root "$HERE/stregdle-test.service" /etc/systemd/system/stregdle-test.service
systemctl daemon-reload
systemctl enable stregdle-test.service
systemctl restart stregdle-test.service
sleep 3
echo "active: $(systemctl is-active stregdle-test.service)"

if grep -q "$HOST" /srv/infra/caddy/Caddyfile; then
    echo "caddy block already present"
else
    cp -a /srv/infra/caddy/Caddyfile "/root/Caddyfile.bak-$(date +%Y%m%d-%H%M%S)"
    printf '\n' >>/srv/infra/caddy/Caddyfile
    cat "$HERE/caddy-test.conf" >>/srv/infra/caddy/Caddyfile
    echo "caddy block appended"
fi
if /usr/local/bin/caddy validate --config /srv/infra/caddy/Caddyfile --adapter caddyfile >/tmp/caddy-validate.out 2>&1; then
    /usr/local/bin/caddy reload --config /srv/infra/caddy/Caddyfile --adapter caddyfile
    echo "caddy reloaded"
else
    echo "caddy validate failed:"
    tail -5 /tmp/caddy-validate.out
fi

curl -s -o /dev/null -w 'app healthz: %{http_code}\n' -H "Host: $HOST" -H 'X-Forwarded-Proto: https' http://127.0.0.1:8002/healthz
curl -s -o /dev/null -w 'caddy healthz: %{http_code}\n' -H "Host: $HOST" http://127.0.0.1/healthz
