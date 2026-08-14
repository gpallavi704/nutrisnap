"""Goal-weighted scoring, with the arithmetic left visible.

Every score returns its components. A single number nobody can decompose is an
oracle, and an oracle is exactly what this project is arguing against — the
user should be able to see that a product lost on sugar and won on protein
rather than being told to trust a 62.

Thresholds come from the UK FSA front-of-pack traffic-light bands, which are
published and defensible, instead of numbers chosen to make the output look
decisive. Everything is judged per 100 g so that a small bar and a large bottle
can be compared at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.model import Nutrients

# (low = good, high = bad) per 100 g, from the FSA bands.
BANDS = {
    "total_sugars_g": (5.0, 22.5),
    "saturated_fat_g": (1.5, 5.0),
    "total_fat_g": (3.0, 17.5),
    "sodium_mg": (120.0, 600.0),
}

# Drinks are mostly water, so per-100 ml they look mild on a food scale — a
# full-sugar cola scores as comfortably mid-range against food thresholds. The
# FSA publishes separate, roughly halved bands for beverages, and Nutri-Score
# scales drinks separately for the same reason.
BANDS_DRINK = {
    "total_sugars_g": (2.5, 11.25),
    "saturated_fat_g": (0.75, 2.5),
    "total_fat_g": (1.5, 8.75),
    "sodium_mg": (120.0, 600.0),
}
PROTEIN_TARGET = 20.0   # g per 100 g — a genuinely high-protein food
ADDITIVE_CEILING = 10   # at or above this, the processing subscore is zero


@dataclass
class Component:
    label: str
    value: float | None
    unit: str
    subscore: float | None
    weight: float

    @property
    def contribution(self) -> float | None:
        return None if self.subscore is None else self.subscore * self.weight


# A score built from one minor component is not a score. Nutella with no
# nutrition data but a clean additive list scored 100/100 for "cut sugar" until
# this floor existed.
MIN_COVERAGE = 0.5


@dataclass
class Score:
    total: float | None
    components: list[Component]
    goal: str
    basis: str = "per 100 g"
    coverage: float = 0.0
    reason: str | None = None

    @property
    def is_scorable(self) -> bool:
        return self.total is not None


GOALS = {
    "less_sugar": {
        "label": "Cut added sugar",
        "weights": {"sugar": 0.60, "processing": 0.20, "satfat": 0.10, "sodium": 0.10},
    },
    "more_protein": {
        "label": "More protein",
        "weights": {"protein": 0.60, "sugar": 0.20, "processing": 0.10, "satfat": 0.10},
    },
    "less_sodium": {
        "label": "Less sodium",
        "weights": {"sodium": 0.60, "processing": 0.20, "satfat": 0.10, "sugar": 0.10},
    },
    "less_processed": {
        "label": "Less processed",
        "weights": {"processing": 0.60, "sugar": 0.20, "satfat": 0.10, "sodium": 0.10},
    },
    "balanced": {
        "label": "Balanced",
        "weights": {"sugar": 0.25, "satfat": 0.20, "sodium": 0.20,
                    "protein": 0.20, "processing": 0.15},
    },
}


def _lower_is_better(value: float | None, band: tuple[float, float]) -> float | None:
    """100 at or below the 'low' threshold, 0 at or above 'high', linear between."""
    if value is None:
        return None
    low, high = band
    if value <= low:
        return 100.0
    if value >= high:
        return 0.0
    return 100.0 * (high - value) / (high - low)


def _higher_is_better(value: float | None, target: float) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, value / target * 100.0))


def score(n100: Nutrients | None, additive_count: int | None, goal: str = "balanced",
          is_beverage: bool = False) -> Score:
    """Score one product per 100 g against a goal.

    ``additive_count`` is None when there is no ingredient list to count. That is
    not the same as zero: treating "we couldn't read it" as "it contains nothing"
    would let an unreadable label score perfectly.
    """
    spec = GOALS.get(goal, GOALS["balanced"])
    w = spec["weights"]
    n = n100 or Nutrients()
    bands = BANDS_DRINK if is_beverage else BANDS
    basis = "per 100 ml" if is_beverage else "per 100 g"
    unit = "g/100ml" if is_beverage else "g/100g"
    munit = "mg/100ml" if is_beverage else "mg/100g"

    available = {
        "sugar": Component(
            "Sugars", n.total_sugars_g, unit,
            _lower_is_better(n.total_sugars_g, bands["total_sugars_g"]), w.get("sugar", 0)),
        "satfat": Component(
            "Saturated fat", n.saturated_fat_g, unit,
            _lower_is_better(n.saturated_fat_g, bands["saturated_fat_g"]), w.get("satfat", 0)),
        "sodium": Component(
            "Sodium", n.sodium_mg, munit,
            _lower_is_better(n.sodium_mg, bands["sodium_mg"]), w.get("sodium", 0)),
        "protein": Component(
            "Protein", n.protein_g, unit,
            _higher_is_better(n.protein_g, PROTEIN_TARGET), w.get("protein", 0)),
        "processing": Component(
            "Additives",
            None if additive_count is None else float(additive_count), "count",
            None if additive_count is None
            else _lower_is_better(float(additive_count), (0.0, float(ADDITIVE_CEILING))),
            w.get("processing", 0)),
    }

    components = [c for k, c in available.items() if w.get(k, 0) > 0]
    scored = [c for c in components if c.subscore is not None]
    if not scored:
        return Score(None, components, goal, basis, coverage=0.0,
                     reason="No nutrition data could be read for this product.")

    # How much of the goal's definition we could actually measure.
    measured = sum(c.weight for c in scored)
    declared = sum(c.weight for c in components) or 1.0
    coverage = measured / declared

    if coverage < MIN_COVERAGE:
        missing = ", ".join(c.label.lower() for c in components if c.subscore is None)
        return Score(
            None, components, goal, basis, coverage=coverage,
            reason=f"Not enough of this label could be read to score it — missing {missing}.",
        )

    # Re-weight across what was measurable, so a missing field lowers confidence
    # rather than silently dragging the score toward zero.
    total = sum(c.subscore * c.weight for c in scored) / measured

    return Score(round(total, 1), components, goal, basis, coverage=coverage)


def compare(scores: list[tuple[str, Score]]) -> list[tuple[str, Score]]:
    """Rank products best-first. Unscorable products sort last, not zero."""
    return sorted(
        scores,
        key=lambda pair: (pair[1].total is None, -(pair[1].total or 0)),
    )


def explain(winner: Score, runner_up: Score) -> str | None:
    """Name the component that actually decided it."""
    if not (winner.is_scorable and runner_up.is_scorable):
        return None
    gaps = []
    by_label = {c.label: c for c in runner_up.components}
    for c in winner.components:
        other = by_label.get(c.label)
        if other and c.contribution is not None and other.contribution is not None:
            gaps.append((c.contribution - other.contribution, c, other))
    if not gaps:
        return None
    gap, best, other = max(gaps, key=lambda g: g[0])
    if gap <= 0:
        return None
    return (
        f"{best.label} decided it: {best.value:g} {best.unit} against "
        f"{other.value:g} {other.unit}."
    )
