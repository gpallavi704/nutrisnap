"""Serving-size normalization and the arithmetic self-check.

Two products are only comparable on one basis, and the basis a label chooses is
not the one a person eats. A 20 oz bottle declaring "2.5 servings" reports a
quarter of what you actually drink. Restating everything per container — and per
100 g for cross-product comparison — is most of what this app does.

The macro check is the safety net for the vision path: calories are determined
by the macros, so a panel whose numbers don't reconcile was misread.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.model import KCAL_PER_G, Nutrients, Product

# Panels round, "net carbs" conventions vary, and fibre is counted
# inconsistently, so agreement is never exact. Beyond a quarter off, something
# is actually wrong rather than merely rounded.
MACRO_TOLERANCE = 0.25


BEVERAGE_UNITS = ("ml", "millilit", "fl oz", "fluid ounce", "litre", "liter")


def detect_beverage(*texts: str | None) -> bool:
    """A serving measured in volume is a drink, and drinks get their own bands."""
    blob = " ".join(t.lower() for t in texts if t)
    return any(u in blob for u in BEVERAGE_UNITS)


def per_container(product: Product) -> Nutrients | None:
    """The whole package, which is what people actually consume."""
    n = product.servings_per_container
    if n is None or n <= 0 or product.per_serving.is_empty:
        return None
    return product.per_serving.scaled(n)


def per_100g(product: Product) -> Nutrients | None:
    """Common basis for comparing two products of different sizes."""
    grams = product.serving_grams
    if not grams or grams <= 0 or product.per_serving.is_empty:
        return None
    return product.per_serving.scaled(100.0 / grams)


@dataclass
class MacroCheck:
    stated: float | None
    computed: float | None
    delta_pct: float | None
    ok: bool
    message: str | None = None


def macro_check(n: Nutrients) -> MacroCheck:
    """Verify calories ≈ 4·carb + 4·protein + 9·fat.

    This is how an OCR misread announces itself. A decimal slip that turns 2.6 g
    of fat into 26 g breaks the arithmetic by a wide margin, so the app can flag
    the reading instead of confidently reporting a wrong number.
    """
    if n.calories is None or any(
        v is None for v in (n.total_carb_g, n.protein_g, n.total_fat_g)
    ):
        return MacroCheck(n.calories, None, None, True)  # not enough to judge

    computed = (
        n.total_carb_g * KCAL_PER_G["carb"]
        + n.protein_g * KCAL_PER_G["protein"]
        + n.total_fat_g * KCAL_PER_G["fat"]
    )
    if n.calories <= 0:
        return MacroCheck(n.calories, computed, None, True)

    delta = abs(computed - n.calories) / n.calories
    ok = delta <= MACRO_TOLERANCE
    msg = None
    if not ok:
        msg = (
            f"The macros don't reconcile with the calorie count "
            f"({computed:.0f} kcal from carbs, protein and fat vs {n.calories:.0f} "
            f"stated). One of these numbers was probably misread — check the panel."
        )
    return MacroCheck(n.calories, computed, delta * 100, ok, msg)


def analyze_servings(product: Product, multipack_above: float = 4.0) -> list[str]:
    """Notes about the serving declaration itself, worth surfacing verbatim.

    Only meaningful for packages a person might finish in one go. Telling
    someone that a twelve-bar box "is 1/12 of what's in your hand" describes a
    box nobody is holding, and the multipack note in ``analyze`` covers it
    better.
    """
    notes: list[str] = []
    n = product.servings_per_container

    if n is None:
        notes.append("No servings-per-container figure, so per-package totals are unavailable.")
        return notes

    if n > multipack_above:
        return notes

    if n > 1.2:
        notes.append(
            f"This package is {_pretty(n)} servings. Every number on the panel is "
            f"for {_fraction(n)} of what's in your hand."
        )
    # A fractional count like 2.5 is the clearest sign the serving was chosen to
    # flatter the panel rather than to describe a portion.
    if n % 1 not in (0.0,) and n > 1:
        notes.append(
            f"The serving size divides the package into {_pretty(n)} — an amount "
            "nobody measures out."
        )
    return notes


def _pretty(n: float) -> str:
    return f"{n:g}"


def _fraction(n: float) -> str:
    return f"1/{n:g}" if n else "part"
