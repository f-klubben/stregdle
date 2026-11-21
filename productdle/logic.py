"""Core game logic for Stregsystemdle.

The target product is fixed for the whole day so everyone plays the same round
(like Wordle). The pick is deterministic per date and memoized in-process so it
never flips mid-day when products change.

Nothing here touches the database: product data is handed in as ``Product``
objects from ``productdle.repository``.
"""

from __future__ import annotations

import datetime

import random

import re

from django.utils import timezone

from . import wares

# Seed prefix of the daily answer. Kept identical to the original in-app game so
# the answer of the day does not change when the game moves to its own project.
SEED_PREFIX = "stregdle"

# Column order shared by the guess board and the search table. The leading
# "id" column sits right next to the product name, like the main menu.
COLUMNS = [
    {"key": "id", "label": "ID"},
    {"key": "price", "label": "Pris"},
    {"key": "category", "label": "Kategori"},
    {"key": "alcohol", "label": "Alkohol"},
    {"key": "rooms", "label": "Rum"},
    {"key": "sales", "label": "Salg/md"},
    {"key": "total", "label": "Total"},
    {"key": "last_sale", "label": "Sidste salg"},
    {"key": "named", "label": "Kortnavn"},
]


# answer date (ISO) -> product id, so the answer is stable for the whole day.
_target_cache: dict = {}


def _num(value):
    return value if value is not None else 0


def money(value) -> str:
    return "{0:.2f}".format(_num(value) / 100.0)


def ml_str(value) -> str:
    return f"{_num(value):.1f} ml"


def sales_str(sales: float) -> str:
    return f"{sales:.0f}"


def total_str(total: int) -> str:
    return str(int(total))


# Answers come from wares that have been sold within this window; an item nobody
# has bought for years cannot be reasoned towards. Guessing stays open to all.
ANSWER_MAX_AGE_DAYS = 3 * 365


def answer_pool(products) -> list:
    """The only products that can be the answer: wares sold in the last three years."""
    return [p for p in products if p.last_sale_days is not None and p.last_sale_days <= ANSWER_MAX_AGE_DAYS]


def daily_target(products, day=None):
    """The product of the day (deterministic per date, stable for that date)."""
    pool = sorted(answer_pool(products), key=lambda product: product.id)
    if not pool:
        return None
    day = day or timezone.localdate()
    key = day.isoformat()

    cached_id = _target_cache.get(key)
    if cached_id is not None:
        for product in products:
            if product.id == cached_id:
                return product

    rng = random.Random(f"{SEED_PREFIX}-{key}")
    target = rng.choice(pool)
    _target_cache.clear()
    _target_cache[key] = target.id
    return target


def last_sale_str(days) -> str:
    if days is None:
        return "aldrig"
    if days == 0:
        return "i dag"
    if days == 1:
        return "1 dag"
    return f"{int(days)} dage"


def named_str(product) -> str:
    return "Ja" if product.alias else "Nej"


def _field_str(product, key) -> str:
    if key == "id":
        return str(_num(product.id))
    if key == "price":
        return money(product.price)
    if key == "category":
        return ", ".join(sorted(product.categories)) or "-"
    if key == "alcohol":
        return ml_str(product.alcohol_ml)
    if key == "rooms":
        return ", ".join(sorted(product.rooms)) or "-"
    if key == "sales":
        return sales_str(product.avg_monthly_sales)
    if key == "total":
        return total_str(product.total_sales)
    if key == "last_sale":
        return last_sale_str(product.last_sale_days)
    if key == "named":
        return named_str(product)
    return "-"


def _field_value(product, key):
    if key == "id":
        return product.id
    if key == "price":
        return product.price
    if key == "alcohol":
        return product.alcohol_ml
    if key == "sales":
        return product.avg_monthly_sales
    if key == "total":
        return product.total_sales
    if key == "last_sale":
        return product.last_sale_days
    if key == "named":
        return 1 if product.alias else 0
    return None


def _set_members(product, key):
    if key == "category":
        return set(product.categories)
    if key == "rooms":
        return set(product.rooms)
    return set()


def _status(guess, target, key) -> str:
    if key in ("id", "price", "alcohol", "total"):
        g, t = _field_value(guess, key), _field_value(target, key)
        return "low" if g < t else ("high" if g > t else "correct")
    if key == "last_sale":
        g, t = _field_value(guess, key), _field_value(target, key)
        if g is None or t is None:
            return "correct" if g == t else "wrong"
        return "low" if g < t else ("high" if g > t else "correct")
    if key == "named":
        return "correct" if _field_value(guess, key) == _field_value(target, key) else "wrong"
    if key == "sales":
        g, t = _field_value(guess, key), _field_value(target, key)
        if abs(g - t) < 2.0:
            return "correct"
        return "low" if g < t else "high"
    if key in ("category", "rooms"):
        g, t = _set_members(guess, key), _set_members(target, key)
        if g == t:
            return "correct"
        # Yellow when only some of the guessed categories/rooms are in the answer.
        return "partial" if (g & t) else "wrong"
    return "wrong"


def compare(guess, target):
    """Compare a guess against the target and return per-attribute states.

    Each entry carries the guess's own displayed value, so the board can show
    the actual stats for every guessed product.

    Status values:
      correct - the attribute matches the target
      high/low - the guess is above/below the target (shown as text)
      partial - some of the guessed categories/rooms are in the target
      wrong   - no connection
    """
    return [
        {
            "key": column["key"],
            "label": column["label"],
            "status": _status(guess, target, column["key"]),
            "value": _field_str(guess, column["key"]),
        }
        for column in COLUMNS
    ]


TAG_RE = re.compile(r"<[^>]+>")


def clean_name(name: str) -> str:
    """Some product names are stored with HTML markup; strip it for display."""
    return TAG_RE.sub("", name)


def product_stats(product) -> dict:
    """Display values for a product, for search rows / board rows.

    Keys match the COLUMNS order so search and guess rows share one format.
    """
    stats = {
        "id": str(product.id),
        "name": clean_name(product.name),
        "alias": clean_name(product.alias or ""),
        "image": wares.image_for(product.name),
    }
    for column in COLUMNS:
        stats[column["key"]] = _field_str(product, column["key"])
    return stats


def search_products(products, query: str, limit: int) -> list:
    """Products matching name, short name (alias) or ID.

    Matched with casefold() so it is fully case-insensitive, including Danish
    letters that a plain SQL LIKE on a non-unicode collation would not fold.
    """
    query = query.strip()
    if not query:
        return []

    try:
        query_id = int(query)
    except ValueError:
        query_id = None
    query_lower = query.casefold()

    matched = []
    for product in products:
        if query_id is not None and product.id == query_id:
            matched.append(product)
            continue
        name = clean_name(product.name).casefold()
        alias = clean_name(product.alias or "").casefold()
        if query_lower in name or (alias and query_lower in alias):
            matched.append(product)
    return matched[:limit]
