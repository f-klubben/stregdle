"""Report which wares have a picture and which do not.

Run it after the shop's product list changes: every product listed as missing
needs an alias in ``productdle/wares.py`` (or it simply has no photo yet).
"""

from django.core.management.base import BaseCommand, CommandError

from productdle import wares
from productdle.logic import clean_name
from productdle.repository import DatabaseUnavailable, repository


class Command(BaseCommand):
    help = "Check the ware photos against the products in the stregsystem database."

    def handle(self, *args, **options):
        try:
            products = repository.refresh()
        except DatabaseUnavailable as exc:
            raise CommandError(f"Database unavailable: {exc}") from exc

        if not products:
            raise CommandError("No products returned - does the stregsystem database have any?")

        matched, missing = [], []
        used = set()
        for product in products:
            image = wares.image_for(product.name)
            if image:
                matched.append((product, image))
                used.add(image.rsplit("/", 1)[-1])
            else:
                missing.append(product)

        self.stdout.write(f"{len(matched)} of {len(products)} products have a photo")
        for product, image in matched:
            self.stdout.write(f"  {product.id:>5}  {clean_name(product.name)}  ->  {image.rsplit('/', 1)[-1]}")

        if missing:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"{len(missing)} products without a photo:"))
            for product in missing:
                self.stdout.write(f"  {product.id:>5}  {clean_name(product.name)}")

        unused = [image.rsplit("/", 1)[-1] for image, _ in wares.WARES if image.rsplit("/", 1)[-1] not in used]
        if unused:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"{len(unused)} photos match no product:"))
            for name in unused:
                self.stdout.write(f"  {name}")
