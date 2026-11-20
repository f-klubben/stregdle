#!/bin/bash
# Pull the next release of Stregsystemdle and restart it.
#
# Run once by stregdle-cutover.timer, scheduled for the midnight after a deploy,
# so a game already being played is never changed mid-day. The timer and this
# script remove themselves afterwards; to deploy again, reinstall the timer with
# the next date.
set -euo pipefail
logger -t stregdle-cutover "starting cutover in /data/stregdle"
cd /data/stregdle
sudo -u stregdle git pull --ff-only
sudo -u stregdle ./venv/bin/python -m pip install --quiet '.[prod]'
sudo -u stregdle ./venv/bin/python manage.py collectstatic --noinput
systemctl restart stregdle
sleep 3
systemctl is-active stregdle
logger -t stregdle-cutover "deployed $(sudo -u stregdle git rev-parse --short HEAD)"
systemctl disable --now stregdle-cutover.timer || true
rm -f /etc/systemd/system/stregdle-cutover.timer /etc/systemd/system/stregdle-cutover.service
systemctl daemon-reload
