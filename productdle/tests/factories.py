"""Shared test doubles: the game logic works on plain Product objects."""

from productdle.repository import Product


def make_product(
    id=1,
    name="Cola",
    price=2500,
    alcohol_ml=0.0,
    caffeine_mg=0,
    categories=(),
    rooms=(),
    alias="",
    sales_window=0,
    total_sales=0,
):
    return Product(
        id=id,
        name=name,
        price=price,
        alcohol_ml=alcohol_ml,
        caffeine_mg=caffeine_mg,
        categories=frozenset(categories),
        rooms=frozenset(rooms),
        alias=alias,
        sales_window=sales_window,
        total_sales=total_sales,
    )


class FakeRepository:
    """In-memory stand-in for SqlRepository."""

    def __init__(self, products):
        self._products = list(products)

    def products(self):
        return list(self._products)

    def product(self, product_id):
        return next((p for p in self._products if p.id == product_id), None)
