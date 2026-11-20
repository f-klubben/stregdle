"""HTTP endpoints for the game: the page plus the three JSON calls it uses."""

import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from . import logic, wares
from .repository import DatabaseUnavailable, repository

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 10


def index(request):
    day = timezone.localdate()
    return render(
        request,
        "productdle/index.html",
        {
            "stregsystem_url": settings.STREGSYSTEM_URL,
            "source_url": settings.SOURCE_URL,
            "today": day.isoformat(),
            # The board layout switches at midnight, see logic.NEW_LAYOUT_FROM.
            "columns": logic.columns(day),
        },
    )


@require_GET
def healthz(request):
    """Liveness check for the reverse proxy and for deploy scripts.

    Deliberately does not touch the database: the page already reports when the
    shop's database is unreachable.
    """
    return JsonResponse({"status": "ok"})


def _products():
    """The product pool, or None if the stregsystem database is unreachable."""
    try:
        return repository.products()
    except DatabaseUnavailable as exc:
        # A database outage would otherwise log a traceback on every request.
        logger.warning("Could not read products from the stregsystem database: %s", exc)
        return None


@require_GET
def search(request):
    """Autocomplete: products matching name, short name (alias) or ID."""
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"products": []})

    products = _products()
    if products is None:
        return JsonResponse({"error": "Kan ikke læse varerne lige nu."}, status=503)

    day = timezone.localdate()
    matched = logic.search_products(products, query, SEARCH_LIMIT)
    return JsonResponse({"products": [logic.product_stats(product, day=day) for product in matched]})


@require_GET
def guess(request):
    """Compare a guessed product against today's target."""
    products = _products()
    if products is None:
        return JsonResponse({"error": "Kan ikke læse varerne lige nu."}, status=503)

    target = logic.daily_target(products)
    if target is None:
        return JsonResponse({"error": "Ingen varer tilgængelige lige nu."}, status=503)

    try:
        product_id = int(request.GET.get("id", ""))
    except ValueError:
        return JsonResponse({"error": "Ukendt vare."}, status=404)

    product = next((p for p in products if p.id == product_id), None)
    if product is None:
        return JsonResponse({"error": "Ukendt vare."}, status=404)

    day = timezone.localdate()
    return JsonResponse(
        {
            "guess": logic.product_stats(product, day=day),
            "columns": logic.compare(product, target, day=day),
            "won": product.id == target.id,
        }
    )


@require_GET
def reveal(request):
    """Show today's target (when giving up)."""
    products = _products()
    if products is None:
        return JsonResponse({"error": "Kan ikke læse varerne lige nu."}, status=503)

    target = logic.daily_target(products)
    if target is None:
        return JsonResponse({"error": "Ingen varer tilgængelige lige nu."}, status=503)

    return JsonResponse(
        {
            "name": logic.clean_name(target.name),
            "alias": target.alias or "",
            "image": wares.image_for(target.name),
            "columns": logic.compare(target, target, day=timezone.localdate()),
        }
    )
