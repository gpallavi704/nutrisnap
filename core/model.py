"""The shapes every other module agrees on.

A ``Product`` is whatever we managed to learn about one item, from either the
Open Food Facts database or a photo of its panel. ``source`` is carried all the
way to the UI on purpose: a number read off a blurry photo and a number from a
verified database entry deserve different amounts of trust, and the user should
be able to see which one they're looking at.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

Source = Literal["openfoodfacts", "vision"]
Level = Literal["ok", "caution", "avoid", "unknown"]

# Sugar is 3.87 kcal/g but every label rounds to 4. A teaspoon of granulated
# sugar is about 4.2 g — the unit people can actually picture.
KCAL_PER_G = {"carb": 4.0, "protein": 4.0, "fat": 9.0}
GRAMS_PER_TSP = 4.2


@dataclass
class Nutrients:
    """One nutrition column. Every field optional — panels vary and photos fail."""

    calories: float | None = None
    total_fat_g: float | None = None
    saturated_fat_g: float | None = None
    sodium_mg: float | None = None
    total_carb_g: float | None = None
    fiber_g: float | None = None
    total_sugars_g: float | None = None
    added_sugars_g: float | None = None
    protein_g: float | None = None

    def scaled(self, factor: float) -> "Nutrients":
        """Same column multiplied through — per serving to per container."""
        return Nutrients(**{
            k: (v * factor if v is not None else None)
            for k, v in self.__dict__.items()
        })

    @property
    def is_empty(self) -> bool:
        return all(v is None for v in self.__dict__.values())


@dataclass
class Flag:
    """One thing worth telling the user, with the evidence that triggered it."""

    level: Level
    label: str
    detail: str
    term: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.level == "avoid"


@dataclass
class Product:
    name: str
    brand: str | None = None
    barcode: str | None = None
    source: Source = "vision"

    serving_size: str | None = None
    serving_grams: float | None = None
    servings_per_container: float | None = None

    per_serving: Nutrients = field(default_factory=Nutrients)
    ingredients_text: str | None = None
    image_url: str | None = None
    is_beverage: bool = False

    # Populated by the analysis pass rather than the data source.
    per_container: Nutrients | None = None
    flags: list[Flag] = field(default_factory=list)
    sugar_aliases: list[str] = field(default_factory=list)
    additives: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def with_analysis(self, **kwargs) -> "Product":
        return replace(self, **kwargs)
