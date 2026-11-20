"""Read-only SQL access to the stregsystem database.

This project is deliberately separate from the stregsystem: it has no ORM
models and never imports stregsystem code. Everything it knows about the shop
comes from the SELECT statements below, run on a short-lived MySQL connection
with a user that only has SELECT rights.

The table names are Django's defaults for the stregsystem app, so they are
stable as long as that project's models keep their names.
"""

from __future__ import annotations

import threading

import time

from dataclasses import dataclass

from typing import Protocol

import pymysql

from django.conf import settings

# One "month" of sales is approximated as 30 days, so the average monthly
# figure is the sale count of the last 90 days divided by three.
SALES_WINDOW_DAYS = 90

# How long a product snapshot is reused before the database is read again.
SNAPSHOT_TTL_SECONDS = 60

PRODUCTS_SQL = """
SELECT p.id,
       p.name,
       p.price,
       COALESCE(p.alcohol_content_ml, 0) AS alcohol_ml,
       COALESCE(p.caffeine_content_mg, 0) AS caffeine_mg,
       (SELECT COUNT(*)
          FROM stregsystem_sale s
         WHERE s.product_id = p.id
           AND s.timestamp > NOW() - INTERVAL %s DAY) AS sales_window,
       (SELECT COUNT(*)
          FROM stregsystem_sale s
         WHERE s.product_id = p.id) AS total_sales,
       DATEDIFF(NOW(), (SELECT MAX(s.timestamp)
                          FROM stregsystem_sale s
                         WHERE s.product_id = p.id)) AS last_sale_days
  FROM stregsystem_product p
 ORDER BY p.id
"""

CATEGORIES_SQL = """
SELECT pc.product_id, c.name
  FROM stregsystem_product_categories pc
  JOIN stregsystem_category c ON c.id = pc.category_id
"""

ROOMS_SQL = """
SELECT pr.product_id, r.name
  FROM stregsystem_product_rooms pr
  JOIN stregsystem_room r ON r.id = pr.room_id
"""

ALIASES_SQL = """
SELECT product_id, name
  FROM stregsystem_namedproduct
"""


class DatabaseUnavailable(Exception):
    """The stregsystem database could not be read."""


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    price: int
    alcohol_ml: float
    caffeine_mg: int
    categories: frozenset
    rooms: frozenset
    alias: str
    sales_window: int
    total_sales: int
    last_sale_days: int | None = None

    @property
    def avg_monthly_sales(self) -> float:
        return self.sales_window * 30.0 / SALES_WINDOW_DAYS


class Repository(Protocol):
    def products(self) -> list[Product]: ...

    def product(self, product_id: int) -> Product | None: ...


def _connect():
    cfg = settings.STREG_DB
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
    )


def _group_names(rows, column="name") -> dict:
    grouped = {}
    for row in rows:
        grouped.setdefault(row["product_id"], set()).add(row[column])
    return grouped


class SqlRepository:
    """Reads the product pool from the stregsystem database.

    A snapshot (one connection, four queries) is cached for a short while so a
    page of guesses does not hammer the shop's database.
    """

    def __init__(self, ttl: int = SNAPSHOT_TTL_SECONDS):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._snapshot = None
        self._snapshot_at = 0.0

    # -- public API ---------------------------------------------------------

    def products(self) -> list[Product]:
        return self._load()

    def product(self, product_id: int) -> Product | None:
        for product in self._load():
            if product.id == product_id:
                return product
        return None

    def refresh(self) -> list[Product]:
        with self._lock:
            self._snapshot = None
            self._snapshot_at = 0.0
        return self._load()

    # -- internals ----------------------------------------------------------

    def _load(self) -> list[Product]:
        with self._lock:
            fresh = self._snapshot is not None and (time.monotonic() - self._snapshot_at) < self._ttl
            if fresh:
                return self._snapshot
        products = self._fetch()
        with self._lock:
            self._snapshot = products
            self._snapshot_at = time.monotonic()
        return products

    def _fetch(self) -> list[Product]:
        try:
            connection = _connect()
        except pymysql.Error as exc:
            raise DatabaseUnavailable(str(exc)) from exc

        try:
            with connection.cursor() as cursor:
                cursor.execute(PRODUCTS_SQL, (SALES_WINDOW_DAYS,))
                products = cursor.fetchall()
                cursor.execute(CATEGORIES_SQL)
                categories = _group_names(cursor.fetchall())
                cursor.execute(ROOMS_SQL)
                rooms = _group_names(cursor.fetchall())
                cursor.execute(ALIASES_SQL)
                aliases = {row["product_id"]: row["name"] for row in cursor.fetchall()}
        except pymysql.Error as exc:
            raise DatabaseUnavailable(str(exc)) from exc
        finally:
            connection.close()

        return [
            Product(
                id=row["id"],
                name=row["name"],
                price=row["price"],
                alcohol_ml=float(row["alcohol_ml"] or 0),
                caffeine_mg=int(row["caffeine_mg"] or 0),
                categories=frozenset(categories.get(row["id"], ())),
                rooms=frozenset(rooms.get(row["id"], ())),
                alias=aliases.get(row["id"], ""),
                sales_window=int(row["sales_window"] or 0),
                total_sales=int(row["total_sales"] or 0),
                last_sale_days=None if row["last_sale_days"] is None else int(row["last_sale_days"]),
            )
            for row in products
        ]


# Shared instance used by the views.
repository = SqlRepository()
