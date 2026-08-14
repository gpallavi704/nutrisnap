"""The one pass that turns a raw Product into everything the UI shows.

Pure: no network, no disk, no clock. Give it the same product and it returns the
same verdict every time, which is what makes the whole thing testable and what
separates this from asking a model to have an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import additives as add
from core import allergens as alg
from core import diet, normalize, sugars
from core.model import Flag, Nutrients, Product
from core.score import Score, score

MULTIPACK_SERVINGS = 4


@dataclass
class Analysis:
    product: Product
    per_serving: Nutrients
    per_container: Nutrients | None
    per_100g: Nutrients | None
    sugars: sugars.SugarReading
    additives: list[tuple[str, str]]
    additive_summary: str | None
    flags: list[Flag]
    verdict: str
    score: Score
    notes: list[str]
    macro_ok: bool
    basis_label: str = "serving"
    counterpoint: str | None = None
    headline_basis: Nutrients | None = None

    @property
    def headline_sugar_g(self) -> float | None:
        """Sugar in the amount a person actually consumes."""
        basis = self.headline_basis or self.per_serving
        return basis.total_sugars_g

    @property
    def headline_teaspoons(self) -> float | None:
        return sugars.teaspoons(self.headline_sugar_g)


def _counterpoint(n100, is_beverage: bool, goal: str) -> str | None:
    """Name the dimension the chosen goal is ignoring.

    A cola scores well on "less sodium" because it contains none, which is true
    and useless — the score and the eight teaspoons on the same card look like
    they are describing different products. This says the quiet part.
    """
    if n100 is None:
        return None
    balanced = score(n100, 0, "balanced", is_beverage=is_beverage)
    goal_fit = score(n100, 0, goal, is_beverage=is_beverage)
    if goal_fit.total is None or goal_fit.total < 65:
        return None

    weak = [c for c in balanced.components
            if c.subscore is not None and c.subscore < 35]
    if not weak:
        return None
    worst = min(weak, key=lambda c: c.subscore)
    return (f"Scores well on this goal, but {worst.label.lower()} is high at "
            f"{worst.value:g} {worst.unit} — pick a different goal to see it weighed.")


def analyze(product: Product, goal: str = "balanced", diets: list[str] | None = None,
            allergens: list[str] | None = None) -> Analysis:
    diets = diets or []
    allergens = allergens or []
    notes: list[str] = []

    container = normalize.per_container(product)
    # A 30-bar box is a real package total and a useless headline -- nobody eats
    # the box. Above this many servings it is a multipack, not a sitting.
    n_serv = product.servings_per_container or 0
    headline_container = container if 0 < n_serv <= MULTIPACK_SERVINGS else None
    hundred = normalize.per_100g(product)
    notes.extend(normalize.analyze_servings(product))

    check = normalize.macro_check(product.per_serving)
    if check.message:
        notes.append(check.message)

    sugar_basis = (headline_container or product.per_serving).total_sugars_g
    reading = sugars.read_sugars(product.ingredients_text, sugar_basis)
    if (line := sugars.describe(reading)):
        notes.append(line)

    found = add.find_additives(product.ingredients_text)
    flags = diet.check(product.ingredients_text, diets) if diets else []
    flags += alg.check(product.ingredients_text, allergens)

    if reading.alcohols:
        flags.append(Flag(
            "caution", "Sugar alcohols",
            f"Contains {', '.join(reading.alcohols)} — not counted as sugar, but a "
            "common cause of digestive upset.",
        ))

    # Saying "per serving" when the label declares no serving is a small lie;
    # the number is really per 100 g and should say so.
    if headline_container is not None:
        basis_label = "whole package"
    elif product.serving_size and "no serving declared" in product.serving_size:
        basis_label = "100 ml" if product.is_beverage else "100 g"
    elif product.serving_size:
        basis_label = f"serving ({product.serving_size})"
    else:
        basis_label = "serving"

    if container is not None and headline_container is None:
        notes.append(
            f"This box holds about {n_serv:g} servings, so the figures below are "
            "for one serving rather than the whole pack."
        )

    return Analysis(
        headline_basis=headline_container,
        basis_label=basis_label,
        counterpoint=_counterpoint(hundred, product.is_beverage, goal),
        product=product,
        per_serving=product.per_serving,
        per_container=container,
        per_100g=hundred,
        sugars=reading,
        additives=found,
        additive_summary=add.summarize(found),
        flags=flags,
        verdict=diet.verdict(flags) if flags else "ok",
        # None, not zero, when there was no list to count — see score().
        score=score(hundred, len(found) if product.ingredients_text else None, goal,
                    is_beverage=product.is_beverage),
        notes=notes,
        macro_ok=check.ok,
    )
