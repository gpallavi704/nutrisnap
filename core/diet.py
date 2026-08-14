"""Hidden-ingredient rules — what the label says without saying it.

"Milk" is easy; nobody needs software for that. What catches people out are the
derivatives: casein is milk, isinglass is fish, carmine is insects, L-cysteine
is often feathers. None of those words look like what they are.

Three outcomes, and the third one is the important one:

  avoid    the term is definitively excluded by that diet
  caution  usually but not always a problem, worth confirming
  unknown  genuinely undeterminable from the label

Anything in the third bucket stays there. "Natural flavors" can be plant or
animal derived and the package will never say which — guessing would be more
comfortable and less honest.
"""

from __future__ import annotations

from core.allergens import split_precautionary
from core.model import Flag
from core.text import build_matcher, find_terms

# term -> (level, plain-language reason)
VEGAN: dict[str, tuple[str, str]] = {
    "casein": ("avoid", "a milk protein"),
    "caseinate": ("avoid", "a milk protein"),
    "sodium caseinate": ("avoid", "a milk protein"),
    "whey": ("avoid", "a milk by-product"),
    "lactose": ("avoid", "milk sugar"),
    "lactalbumin": ("avoid", "a milk protein"),
    "ghee": ("avoid", "clarified butter"),
    "gelatin": ("avoid", "boiled animal collagen"),
    "gelatine": ("avoid", "boiled animal collagen"),
    "carmine": ("avoid", "red colouring made from crushed cochineal insects"),
    "cochineal": ("avoid", "red colouring made from crushed insects"),
    "shellac": ("avoid", "a resin secreted by lac insects"),
    "isinglass": ("avoid", "made from fish swim bladders"),
    "lard": ("avoid", "pork fat"),
    "tallow": ("avoid", "rendered beef fat"),
    "suet": ("avoid", "raw beef fat"),
    "anchovy": ("avoid", "fish"),
    "rennet": ("avoid", "an enzyme from calf stomach"),
    "albumin": ("avoid", "usually egg white"),
    "honey": ("avoid", "an insect product"),
    "beeswax": ("avoid", "an insect product"),
    "royal jelly": ("avoid", "an insect product"),
    "lanolin": ("avoid", "wool grease"),
    "l cysteine": ("caution", "a dough conditioner, often from feathers or hair"),
    "vitamin d3": ("caution", "usually derived from lanolin (sheep wool)"),
    "bone char": ("avoid", "charred animal bone, used to whiten sugar"),
    "pepsin": ("avoid", "an enzyme from pig stomach"),
    "collagen": ("avoid", "animal connective tissue"),
}

VEGETARIAN: dict[str, tuple[str, str]] = {
    k: v for k, v in VEGAN.items()
    if k in {
        "gelatin", "gelatine", "carmine", "cochineal", "isinglass", "lard",
        "tallow", "suet", "anchovy", "rennet", "pepsin", "collagen", "bone char",
    }
}

GLUTEN: dict[str, tuple[str, str]] = {
    "wheat": ("avoid", "contains gluten"),
    "barley": ("avoid", "contains gluten"),
    "rye": ("avoid", "contains gluten"),
    "malt": ("avoid", "made from barley"),
    "malt extract": ("avoid", "made from barley"),
    "brewers yeast": ("avoid", "a by-product of barley brewing"),
    "semolina": ("avoid", "durum wheat"),
    "durum": ("avoid", "a wheat variety"),
    "spelt": ("avoid", "a wheat variety"),
    "farro": ("avoid", "a wheat variety"),
    "kamut": ("avoid", "a wheat variety"),
    "triticale": ("avoid", "a wheat-rye hybrid"),
    "seitan": ("avoid", "pure wheat gluten"),
    "graham flour": ("avoid", "wheat flour"),
    "couscous": ("avoid", "made from wheat"),
    "oats": ("caution", "gluten-free by nature but very often cross-contaminated"),
}

DAIRY: dict[str, tuple[str, str]] = {
    "milk": ("avoid", "dairy"),
    "cream": ("avoid", "dairy"),
    "butter": ("avoid", "dairy"),
    "cheese": ("avoid", "dairy"),
    "yogurt": ("avoid", "dairy"),
    "casein": ("avoid", "a milk protein"),
    "caseinate": ("avoid", "a milk protein"),
    "whey": ("avoid", "a milk by-product"),
    "lactose": ("avoid", "milk sugar"),
    "ghee": ("avoid", "clarified butter"),
    "curd": ("avoid", "dairy"),
}

# Cannot be resolved from a label, for any diet. These stay amber forever.
AMBIGUOUS: dict[str, str] = {
    "natural flavors": "may be plant or animal derived; the label never specifies",
    "natural flavours": "may be plant or animal derived; the label never specifies",
    "artificial flavors": "source not disclosed",
    "mono and diglycerides": "emulsifier that may come from plant or animal fat",
    "diglycerides": "emulsifier that may come from plant or animal fat",
    "lecithin": "usually soy or sunflower, occasionally egg",
    "enzymes": "may be microbial or animal derived",
    "glycerin": "may be plant or animal derived",
    "glycerol": "may be plant or animal derived",
    "stearic acid": "may be plant or animal derived",
    "magnesium stearate": "may be plant or animal derived",
    "sugar": "may be filtered through bone char in some regions",
    "natural colour": "source not disclosed",
}

DIETS = {
    "vegan": VEGAN,
    "vegetarian": VEGETARIAN,
    "gluten_free": GLUTEN,
    "dairy_free": DAIRY,
}

DIET_LABELS = {
    "vegan": "Vegan",
    "vegetarian": "Vegetarian",
    "gluten_free": "Gluten free",
    "dairy_free": "Dairy free",
}

_MATCHERS = {name: build_matcher(rules) for name, rules in DIETS.items()}
_AMBIGUOUS = build_matcher(AMBIGUOUS)


def check(ingredients_text: str | None, diets: list[str]) -> list[Flag]:
    """Flags for the selected diets, plus anything genuinely undeterminable."""
    if not ingredients_text:
        return [Flag("unknown", "No ingredient list", "Nothing to check against.")]

    # "May contain" is not an ingredient; see allergens.split_precautionary.
    ingredients_text, _ = split_precautionary(ingredients_text)
    flags: list[Flag] = []

    for diet in diets:
        rules = DIETS.get(diet)
        if not rules:
            continue
        label = DIET_LABELS.get(diet, diet)
        hits = find_terms(ingredients_text, _MATCHERS[diet])
        for term in hits:
            level, reason = rules[term]
            flags.append(Flag(
                level=level,
                label=f"{label}: {term}",
                detail=f"{term.title()} is {reason}.",
                term=term,
            ))
        if not hits:
            flags.append(Flag("ok", label, "No excluded ingredients found."))

    if diets:
        for term in find_terms(ingredients_text, _AMBIGUOUS):
            flags.append(Flag(
                level="unknown",
                label=f"Can't tell: {term}",
                detail=f"{term.title()} — {AMBIGUOUS[term]}.",
                term=term,
            ))

    return flags


def verdict(flags: list[Flag]) -> str:
    """Roll flags up, without ever rounding uncertainty into a yes."""
    if any(f.level == "avoid" for f in flags):
        return "avoid"
    if any(f.level == "caution" for f in flags):
        return "caution"
    if any(f.level == "unknown" for f in flags):
        return "unknown"
    return "ok"
