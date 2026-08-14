"""The one pass that turns a raw Product into everything the UI shows.

Pure: no network, no disk, no clock. Give it the same product and it returns the
same verdict every time, which is what makes the whole thing testable and what
separates this from asking a model to have an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import additives as add
from core import diet, normalize, sugars
from core.model import Flag, Nutrients, Product
from core.score import Score, score


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

    @property
    def headline_sugar_g(self) -> float | None:
        """Sugar in the amount a person actually consumes."""
        basis = self.per_container or self.per_serving
        return basis.total_sugars_g

    @property
    def headline_teaspoons(self) -> float | None:
        return sugars.teaspoons(self.headline_sugar_g)


def analyze(product: Product, goal: str = "balanced", diets: list[str] | None = None) -> Analysis:
    diets = diets or []
    notes: list[str] = []

    container = normalize.per_container(product)
    hundred = normalize.per_100g(product)
    notes.extend(normalize.analyze_servings(product))

    check = normalize.macro_check(product.per_serving)
    if check.message:
        notes.append(check.message)

    sugar_basis = (container or product.per_serving).total_sugars_g
    reading = sugars.read_sugars(product.ingredients_text, sugar_basis)
    if (line := sugars.describe(reading)):
        notes.append(line)

    found = add.find_additives(product.ingredients_text)
    flags = diet.check(product.ingredients_text, diets) if diets else []

    if reading.alcohols:
        flags.append(Flag(
            "caution", "Sugar alcohols",
            f"Contains {', '.join(reading.alcohols)} — not counted as sugar, but a "
            "common cause of digestive upset.",
        ))

    return Analysis(
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
