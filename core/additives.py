"""Additive detection and classification.

An ingredient list ending in eleven chemical names is unreadable by design. The
useful summary isn't the names — it's "nine additives, three of them colourings",
which is a shape a person can hold in their head while comparing two boxes.

E-numbers are classified by their numeric range, which is a real standard rather
than a guess. Named additives are mapped individually.
"""

from __future__ import annotations

import re

from core.text import build_matcher, find_terms, normalize

# The E-number blocks are allocated by function, so the range identifies the job.
E_RANGES = [
    (100, 199, "colouring"),
    (200, 299, "preservative"),
    (300, 399, "antioxidant / acidity regulator"),
    (400, 499, "thickener / emulsifier"),
    (500, 599, "acidity regulator / anti-caking"),
    (600, 699, "flavour enhancer"),
    (700, 799, "antibiotic"),
    (900, 999, "glazing agent / sweetener"),
    (1000, 1599, "additional chemical"),
]

NAMED = {
    "titanium dioxide": "colouring",
    "caramel color": "colouring",
    "caramel colour": "colouring",
    "annatto": "colouring",
    "red 40": "colouring",
    "allura red": "colouring",
    "yellow 5": "colouring",
    "tartrazine": "colouring",
    "yellow 6": "colouring",
    "blue 1": "colouring",
    "sodium benzoate": "preservative",
    "potassium sorbate": "preservative",
    "sorbic acid": "preservative",
    "calcium propionate": "preservative",
    "sodium nitrite": "preservative",
    "sodium nitrate": "preservative",
    "sulphur dioxide": "preservative",
    "sulfur dioxide": "preservative",
    "bha": "antioxidant",
    "bht": "antioxidant",
    "butylated hydroxyanisole": "antioxidant",
    "butylated hydroxytoluene": "antioxidant",
    "tbhq": "antioxidant",
    "ascorbic acid": "antioxidant",
    "citric acid": "acidity regulator",
    "phosphoric acid": "acidity regulator",
    "carrageenan": "thickener",
    "xanthan gum": "thickener",
    "guar gum": "thickener",
    "gellan gum": "thickener",
    "cellulose gum": "thickener",
    "polysorbate 80": "emulsifier",
    "soy lecithin": "emulsifier",
    "monosodium glutamate": "flavour enhancer",
    "msg": "flavour enhancer",
    "disodium inosinate": "flavour enhancer",
    "disodium guanylate": "flavour enhancer",
    "aspartame": "sweetener",
    "sucralose": "sweetener",
    "acesulfame potassium": "sweetener",
    "saccharin": "sweetener",
    "maltodextrin": "bulking agent",
    "propylene glycol": "humectant",
    "silicon dioxide": "anti-caking",
}

_NAMED = build_matcher(NAMED)
_E_NUMBER = re.compile(r"\be\s?(\d{3,4})[a-z]?\b")


def classify_e_number(code: int) -> str:
    for lo, hi, label in E_RANGES:
        if lo <= code <= hi:
            return label
    return "additive"


def find_additives(ingredients_text: str | None) -> list[tuple[str, str]]:
    """Every additive found, as ``(name, category)``, in order of appearance."""
    if not ingredients_text:
        return []
    text = normalize(ingredients_text)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    for name in find_terms(ingredients_text, _NAMED):
        if name not in seen:
            seen.add(name)
            found.append((name, NAMED[name]))

    for m in _E_NUMBER.finditer(text):
        code = f"e{m.group(1)}"
        if code not in seen:
            seen.add(code)
            found.append((code.upper(), classify_e_number(int(m.group(1)))))

    return found


def summarize(additives: list[tuple[str, str]]) -> str | None:
    """'9 additives, 3 of them colourings' — the shape, not the list."""
    if not additives:
        return None
    n = len(additives)
    if n == 1:
        return f"1 additive ({additives[0][0]}, {additives[0][1]})."

    counts: dict[str, int] = {}
    for _, cat in additives:
        counts[cat] = counts.get(cat, 0) + 1
    top, top_n = max(counts.items(), key=lambda kv: kv[1])
    detail = f", {top_n} of them {'a ' + top if top_n == 1 else top + 's'}" if top_n > 1 else ""
    return f"{n} additives{detail}."
