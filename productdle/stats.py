"""Daily guess tally behind the statistics page.

The game has no database, so each day's events are appended to
``<STREGDLE_STATS_DIR>/<date>.jsonl``, one JSON object per line. Writes are a
single ``os.write`` on an O_APPEND handle; failures are logged, never raised.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re

from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PLAYER_RE = re.compile(r"^[a-z0-9]{8,32}$")

GUESS = "guess"
GAVE_UP = "gaveup"

MAX_ATTEMPT = 6


def _directory():
    configured = getattr(settings, "STREGDLE_STATS_DIR", "")
    return Path(configured) if configured else None


def _path(day) -> Path:
    return _directory() / f"{day.isoformat()}.jsonl"


def valid_player(raw) -> str | None:
    player = (raw or "").strip().lower()
    return player if PLAYER_RE.match(player) else None


def _append(day, event) -> None:
    directory = _directory()
    if directory is None:
        return
    line = (json.dumps(event, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(_path(day), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except OSError as exc:
        logger.warning("Could not record guess stats: %s", exc)


def _events(day) -> list:
    directory = _directory()
    if directory is None:
        return []
    try:
        handle = open(_path(day), encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        logger.warning("Could not read guess stats: %s", exc)
        return []

    events = []
    with handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("k") in (GUESS, GAVE_UP):
                events.append(event)
    return events


def _timestamp(when) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(when)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return timezone.localtime().isoformat(timespec="seconds")


def guess_counts(events) -> dict:
    counts: dict = {}
    for event in events:
        if event.get("k") == GUESS and event.get("p"):
            counts[event["p"]] = counts.get(event["p"], 0) + 1
    return counts


def record_guess(player, product_id, won: bool, day=None) -> int:
    """Append a guess and return which attempt of the day it was for that player."""
    day = day or timezone.localdate()
    player = valid_player(player)
    attempt = guess_counts(_events(day)).get(player, 0) + 1 if player else 1
    _append(
        day,
        {
            "k": GUESS,
            "t": _now(),
            "p": player or "",
            "id": int(product_id),
            "a": attempt,
            "won": bool(won),
        },
    )
    return attempt


def record_gave_up(player, day=None) -> int:
    """Append a give-up with the number of guesses made before it."""
    day = day or timezone.localdate()
    player = valid_player(player)
    attempt = guess_counts(_events(day)).get(player, 0) if player else 0
    _append(day, {"k": GAVE_UP, "t": _now(), "p": player or "", "a": attempt})
    return attempt


def summary(day=None) -> dict:
    """Today's aggregates. Product ids and names never leave this function."""
    day = day or timezone.localdate()
    events = _events(day)

    guesses = 0
    players: set = set()
    solved: dict = {}  # player -> attempt number of their first win
    anonymous_wins = 0
    gave_up: set = set()
    hour_counts = [0] * 24

    for event in events:
        when = _timestamp(event.get("t"))
        player = event.get("p") or ""
        if event.get("k") == GAVE_UP:
            if player:
                gave_up.add(player)
            continue

        guesses += 1
        if when is not None:
            hour_counts[when.hour] += 1
        if not player:
            if event.get("won"):
                anonymous_wins += 1
            continue
        players.add(player)
        try:
            attempt = max(1, int(event.get("a") or 1))
        except (TypeError, ValueError):
            attempt = 1
        if event.get("won"):
            solved[player] = min(solved.get(player, attempt), attempt)

    solvers = len(solved) + anonymous_wins
    player_count = len(players)
    attempts = list(solved.values())
    average = sum(attempts) / len(attempts) if attempts else None

    buckets = [0] * (MAX_ATTEMPT + 1)
    for attempt in attempts:
        buckets[min(attempt, MAX_ATTEMPT + 1) - 1] += 1
    top = max(buckets) or 1
    distribution = [
        {
            "label": str(index + 1) if index < MAX_ATTEMPT else f"{MAX_ATTEMPT + 1}+",
            "players": count,
            "pct": max(2, round(count * 100 / top)) if count else 0,
        }
        for index, count in enumerate(buckets)
    ]

    peak = max(hour_counts) or 1
    hours = [
        {
            "hour": hour,
            "label": f"{hour:02d}" if hour % 3 == 0 else "",
            "guesses": count,
            "pct": max(2, round(count * 100 / peak)) if count else 0,
        }
        for hour, count in enumerate(hour_counts)
    ]

    return {
        "players": player_count,
        "guesses": guesses,
        "solvers": solvers,
        # Anonymous wins cannot be matched to a participant, so solvers may
        # outnumber players; the percentage must not exceed 100.
        "solved_pct": min(100, round(solvers * 100 / player_count)) if player_count else 0,
        "gave_up": len(gave_up - solved.keys()),
        "average": average,
        "distribution": distribution,
        "hours": hours,
    }


def yesterday(day=None) -> dict:
    day = day or timezone.localdate()
    return summary(day - datetime.timedelta(days=1))
