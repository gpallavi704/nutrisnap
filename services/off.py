"""Open Food Facts client — the exact path.

When a barcode resolves here we have real, community-verified figures rather
than a model's reading of a photograph, so this is always tried first. The
database is strongest in Europe and thinner for small regional brands, which is
the entire reason the vision path exists.

Units are the trap: Open Food Facts stores sodium and salt in grams while every
US panel prints milligrams. Getting that wrong understates sodium by 1000x.
"""

from __future__ import annotations

import httpx

from core.model import Nutrients, Product
from core.normalize import detect_beverage

API = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
FIELDS = (
    "code,product_name,product_name_en,brands,ingredients_text,ingredients_text_en,"
    "serving_size,serving_quantity,product_quantity,quantity,nutriments,"
    "image_nutrition_url,image_front_url"
)
UA = "NutriSnap/0.1 (educational project; contact via GitHub)"
TIMEOUT = 8.0

_cache: dict[str, Product | None] = {}


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # drop NaN


def _nutrients(n: dict, suffix: str, scale: float = 1.0) -> Nutrients:
    def g(key: str) -> float | None:
        v = _num(n.get(f"{key}{suffix}"))
        return None if v is None else v * scale

    sodium_g = g("sodium")
    if sodium_g is None:
        salt_g = g("salt")
        # Salt is sodium chloride; the standard conversion divides by 2.5.
        sodium_g = None if salt_g is None else salt_g / 2.5

    # Contributor entries sometimes put milligrams in the grams field, giving
    # values like 0.0002 mg of sodium. A real product is either 0 or >= 1 mg.
    sodium_mg = None if sodium_g is None else sodium_g * 1000.0
    if sodium_mg is not None and 0 < sodium_mg < 1:
        sodium_mg = None

    return Nutrients(
        calories=g("energy-kcal"),
        total_fat_g=g("fat"),
        saturated_fat_g=g("saturated-fat"),
        sodium_mg=sodium_mg,
        total_carb_g=g("carbohydrates"),
        fiber_g=g("fiber"),
        total_sugars_g=g("sugars"),
        protein_g=g("proteins"),
    )


def to_product(raw: dict) -> Product:
    n = raw.get("nutriments") or {}
    serving_q = _num(raw.get("serving_quantity"))
    package_q = _num(raw.get("product_quantity"))

    per_serving = _nutrients(n, "_serving")
    serving_size = raw.get("serving_size")
    basis_grams = serving_q

    if per_serving.is_empty and serving_q:
        # Rescale the per-100g column, which is almost always populated.
        per_serving = _nutrients(n, "_100g", scale=serving_q / 100.0)

    if per_serving.is_empty:
        # Plenty of entries declare no serving at all. Report the 100 g column
        # as-is rather than nothing — it is a real, comparable basis, and saying
        # so beats showing an empty panel.
        per_serving = _nutrients(n, "_100g")
        if not per_serving.is_empty:
            basis_grams = 100.0
            serving_size = serving_size or "100 g (no serving declared)"

    servings = None
    if package_q and basis_grams and basis_grams > 0:
        servings = round(package_q / basis_grams, 2)

    # Ingredient text comes back in the product's own language; the rules engine
    # is English, so prefer the translated field when it exists.
    ingredients = raw.get("ingredients_text_en") or raw.get("ingredients_text") or None

    return Product(
        name=(raw.get("product_name_en") or raw.get("product_name")
              or "Unknown product").strip(),
        brand=(raw.get("brands") or None),
        barcode=raw.get("code"),
        source="openfoodfacts",
        serving_size=serving_size,
        serving_grams=basis_grams,
        servings_per_container=servings,
        per_serving=per_serving,
        ingredients_text=ingredients,
        image_url=raw.get("image_nutrition_url") or raw.get("image_front_url"),
        is_beverage=detect_beverage(serving_size, raw.get("quantity")),
    )


async def lookup(barcode: str) -> Product | None:
    """Fetch one product. Returns None when the database doesn't know it."""
    barcode = (barcode or "").strip()
    if not barcode.isdigit():
        return None
    if barcode in _cache:
        return _cache[barcode]

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}) as client:
            r = await client.get(API.format(barcode=barcode), params={"fields": FIELDS})
        if r.status_code != 200:
            _cache[barcode] = None
            return None
        body = r.json()
    except Exception:
        return None  # not cached: a network blip should not become a permanent miss

    if body.get("status") != 1 or not body.get("product"):
        _cache[barcode] = None
        return None

    product = to_product(body["product"])
    _cache[barcode] = product
    return product
