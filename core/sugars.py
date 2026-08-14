"""Sugar alias recombination — the project's flagship calculation.

Ingredient lists are ordered by weight, so a manufacturer who wants sugar out of
the first position can split one sweetener into three and drop each below the
flour. Nothing is hidden and nothing is illegal; the information is simply
arranged so that no single line looks alarming.

Recombining them undoes that arrangement. The point is not that sugar is bad —
it's that the list was ordered to stop you noticing how much there is.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.model import GRAMS_PER_TSP
from core.text import build_matcher, find_terms, normalize, split_ingredients

# Sweeteners that count as sugar on a nutrition panel.
SUGAR_ALIASES = [
    "sugar", "sucrose", "glucose", "fructose", "dextrose", "maltose", "lactose",
    "galactose", "high fructose corn syrup", "hfcs", "corn syrup",
    "corn syrup solids", "glucose syrup", "glucose fructose syrup",
    "cane sugar", "cane juice", "evaporated cane juice", "cane juice crystals",
    "raw sugar", "turbinado", "demerara", "muscovado", "brown sugar",
    "powdered sugar", "confectioners sugar", "invert sugar", "inverted sugar",
    "golden syrup", "molasses", "treacle", "honey", "agave", "agave nectar",
    "agave syrup", "maple syrup", "maple sugar", "rice syrup",
    "brown rice syrup", "barley malt", "barley malt syrup", "malt syrup",
    "malt extract", "maltodextrin", "dextrin", "fruit juice concentrate",
    "grape juice concentrate", "apple juice concentrate", "pear juice concentrate",
    "date syrup", "date sugar", "coconut sugar", "coconut nectar", "palm sugar",
    "sorghum syrup", "tapioca syrup", "tapioca starch syrup", "oat syrup",
    "panela", "jaggery", "sucanat", "crystalline fructose", "caramel",
    "carob syrup", "yacon syrup", "beet sugar", "syrup solids",
]

# Not sugars, and not calorie-free either. Worth naming separately because they
# are the usual cause of "sugar free" products that still upset people.
SUGAR_ALCOHOLS = [
    "sorbitol", "xylitol", "erythritol", "maltitol", "mannitol", "isomalt",
    "lactitol", "glycerol syrup", "hydrogenated starch hydrolysate",
]

NON_NUTRITIVE = [
    "aspartame", "sucralose", "acesulfame", "acesulfame potassium", "acesulfame k",
    "saccharin", "neotame", "advantame", "stevia", "steviol glycosides",
    "monk fruit", "luo han guo", "thaumatin",
]

_SUGAR = build_matcher(SUGAR_ALIASES)
_ALCOHOL = build_matcher(SUGAR_ALCOHOLS)
_SWEETENER = build_matcher(NON_NUTRITIVE)


@dataclass
class SugarReading:
    aliases: list[str]
    alcohols: list[str]
    sweeteners: list[str]
    first_position: int | None      # 1-based rank of the earliest sugar
    total_ingredients: int
    grams: float | None             # per whatever basis was passed in
    teaspoons: float | None

    @property
    def is_split(self) -> bool:
        """Three or more distinct sugars is where splitting stops being incidental."""
        return len(self.aliases) >= 3

    @property
    def in_top_three(self) -> bool:
        return self.first_position is not None and self.first_position <= 3


def teaspoons(grams: float | None) -> float | None:
    """Grams of sugar as teaspoons — the only unit anyone can picture."""
    return None if grams is None else grams / GRAMS_PER_TSP


def read_sugars(ingredients_text: str | None, grams: float | None = None) -> SugarReading:
    """Find every sweetener in the list and locate the first one."""
    items = split_ingredients(ingredients_text or "")
    aliases = find_terms(ingredients_text or "", _SUGAR)

    first = None
    for idx, item in enumerate(items, start=1):
        if _SUGAR.search(normalize(item)):
            first = idx
            break

    return SugarReading(
        aliases=aliases,
        alcohols=find_terms(ingredients_text or "", _ALCOHOL),
        sweeteners=find_terms(ingredients_text or "", _SWEETENER),
        first_position=first,
        total_ingredients=len(items),
        grams=grams,
        teaspoons=teaspoons(grams),
    )


def describe(reading: SugarReading) -> str | None:
    """One plain sentence, or None when there is nothing worth saying."""
    if not reading.aliases:
        return None
    n = len(reading.aliases)
    if reading.is_split:
        names = ", ".join(reading.aliases[:4])
        extra = f" and {n - 4} more" if n > 4 else ""
        return (
            f"{n} separate sweeteners are listed ({names}{extra}). Counted as one "
            f"ingredient they would sit much higher up the list."
        )
    if reading.in_top_three:
        return f"{reading.aliases[0].title()} is ingredient #{reading.first_position} by weight."
    return None
