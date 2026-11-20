"""Verify that the queries in ``productdle/repository.py`` match the live database.

Useful right after deploying or when the stregsystem schema changes: it runs
the same SELECTs the game runs and reports what it found.
"""

from django.core.management.base import BaseCommand, CommandError

from productdle import logic
from productdle.repository import DatabaseUnavailable, repository


class Command(BaseCommand):
    help = "Read the stregsystem database through the game's own SQL and report what came back."

    def handle(self, *args, **options):
        try:
            products = repository.refresh()
        except DatabaseUnavailable as exc:
            raise CommandError(f"Database unavailable: {exc}") from exc

        if not products:
            raise CommandError("No products returned - does the stregsystem database have any?")

        with_sales = sum(1 for p in products if p.total_sales)
        with_category = sum(1 for p in products if p.categories)
        with_alias = sum(1 for p in products if p.alias)
        target = logic.daily_target(products)

        self.stdout.write(f"Products: {len(products)}")
        self.stdout.write(f"  with sales: {with_sales}")
        self.stdout.write(f"  with categories: {with_category}")
        self.stdout.write(f"  with short names: {with_alias}")
        self.stdout.write(f"Today's answer: {logic.clean_name(target.name)} (ID {target.id})")
        self.stdout.write(self.style.SUCCESS("Queries match the database."))
