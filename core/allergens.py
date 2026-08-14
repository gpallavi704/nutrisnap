"""Allergen detection — the part where being wrong actually hurts someone.

Two design rules follow from that:

**Never claim safety.** The app reports "no flags found", which is a statement
about what was detected in a text string, not a statement about a food. A label
can be incomplete, an ingredient list can be out of date, and a factory can
change. Only the packaging can tell someone their food is safe.

**Prefer a false alarm to a missed allergen**, but not so far that the warnings
become noise — which is why the negation lists exist. "Peanut butter" contains
no dairy and "coconut milk" contains no dairy; flagging them would teach a user
with a real milk allergy to stop reading the flags.

Covers the US "big nine" plus the extra EU-declarable allergens, and treats
lactose intolerance as distinct from a milk allergy, because they are.
"""

from __future__ import annotations

import re

from core.model import Flag
from core.text import build_matcher, find_terms, normalize

# key -> {term: (level, why)}
PEANUT = {
    "peanut": ("avoid", "a peanut"), "peanuts": ("avoid", "peanuts"),
    "groundnut": ("avoid", "another name for peanut"),
    "arachis": ("avoid", "the botanical name for peanut"),
    "monkey nut": ("avoid", "another name for peanut"),
    "beer nuts": ("avoid", "peanuts"),
    "mandelona": ("avoid", "peanuts flavoured to imitate almonds"),
}

TREE_NUT = {
    "almond": ("avoid", "a tree nut"), "walnut": ("avoid", "a tree nut"),
    "pecan": ("avoid", "a tree nut"), "cashew": ("avoid", "a tree nut"),
    "pistachio": ("avoid", "a tree nut"), "hazelnut": ("avoid", "a tree nut"),
    "filbert": ("avoid", "another name for hazelnut"),
    "macadamia": ("avoid", "a tree nut"), "brazil nut": ("avoid", "a tree nut"),
    "pine nut": ("avoid", "a tree nut"), "chestnut": ("avoid", "a tree nut"),
    "praline": ("avoid", "made with nuts"),
    "marzipan": ("avoid", "made from almonds"),
    "nougat": ("caution", "usually contains nuts"),
    "gianduja": ("avoid", "a hazelnut chocolate"),
    "nut butter": ("avoid", "made from nuts"),
    "coconut": ("caution", "classified as a tree nut by the FDA, though most "
                           "people with tree-nut allergies tolerate it"),
}

SOY = {
    "soy": ("avoid", "soy"), "soya": ("avoid", "soy"),
    "soybean": ("avoid", "soy"), "soybeans": ("avoid", "soy"),
    "edamame": ("avoid", "immature soybeans"),
    "tofu": ("avoid", "made from soy"), "tempeh": ("avoid", "fermented soy"),
    "miso": ("avoid", "usually fermented soy"), "natto": ("avoid", "fermented soy"),
    "tamari": ("avoid", "a soy sauce"), "shoyu": ("avoid", "a soy sauce"),
    "textured vegetable protein": ("avoid", "usually soy"),
    "tvp": ("avoid", "textured vegetable protein, usually soy"),
    "lecithin": ("caution", "usually soy, occasionally sunflower or egg"),
    "e322": ("caution", "lecithin, usually from soy"),
}

EGG = {
    "egg": ("avoid", "egg"), "eggs": ("avoid", "egg"),
    "albumin": ("avoid", "egg white protein"), "albumen": ("avoid", "egg white"),
    "ovalbumin": ("avoid", "an egg protein"), "globulin": ("avoid", "an egg protein"),
    "livetin": ("avoid", "an egg yolk protein"),
    "lysozyme": ("avoid", "derived from egg white"),
    "mayonnaise": ("avoid", "made with egg"), "meringue": ("avoid", "made from egg white"),
    "surimi": ("caution", "often bound with egg white"),
}

FISH = {
    "fish": ("avoid", "fish"), "anchovy": ("avoid", "a fish"),
    "anchovies": ("avoid", "fish"), "worcestershire": ("avoid", "contains anchovy"),
    "fish sauce": ("avoid", "fish"), "isinglass": ("avoid", "from fish swim bladders"),
    "surimi": ("avoid", "processed fish"), "bonito": ("avoid", "a fish"),
    "dashi": ("avoid", "usually a bonito (fish) stock"),
    "caesar dressing": ("avoid", "traditionally contains anchovy"),
    "omega 3": ("caution", "often derived from fish oil"),
}

SHELLFISH = {
    "shrimp": ("avoid", "a crustacean"), "prawn": ("avoid", "a crustacean"),
    "crab": ("avoid", "a crustacean"), "lobster": ("avoid", "a crustacean"),
    "crayfish": ("avoid", "a crustacean"), "krill": ("avoid", "a crustacean"),
    "langoustine": ("avoid", "a crustacean"),
    "glucosamine": ("caution", "commonly made from shellfish shells"),
    "shellfish": ("avoid", "shellfish"),
}

MOLLUSC = {
    "oyster": ("avoid", "a mollusc"), "mussel": ("avoid", "a mollusc"),
    "clam": ("avoid", "a mollusc"), "scallop": ("avoid", "a mollusc"),
    "squid": ("avoid", "a mollusc"), "calamari": ("avoid", "squid"),
    "octopus": ("avoid", "a mollusc"), "snail": ("avoid", "a mollusc"),
    "oyster sauce": ("avoid", "made from oysters"),
}

SESAME = {
    "sesame": ("avoid", "sesame"), "tahini": ("avoid", "sesame paste"),
    "benne": ("avoid", "another name for sesame"),
    "gingelly": ("avoid", "sesame oil"), "sesamol": ("avoid", "from sesame"),
    "halva": ("avoid", "usually made from sesame"),
}

MILK = {
    "milk": ("avoid", "dairy"), "cream": ("avoid", "dairy"),
    "butter": ("avoid", "dairy"), "buttermilk": ("avoid", "dairy"),
    "cheese": ("avoid", "dairy"), "yogurt": ("avoid", "dairy"),
    "yoghurt": ("avoid", "dairy"), "curd": ("avoid", "dairy"),
    "casein": ("avoid", "a milk protein"), "caseinate": ("avoid", "a milk protein"),
    "whey": ("avoid", "a milk by-product"), "lactose": ("avoid", "milk sugar"),
    "lactalbumin": ("avoid", "a milk protein"), "ghee": ("avoid", "clarified butter"),
    "custard": ("avoid", "made with milk"), "paneer": ("avoid", "a fresh cheese"),
}

# Not the same condition as a milk allergy. Lactose is the sugar; hard cheeses
# and butter are very low in it and are usually tolerated, while casein and whey
# are proteins that matter to an allergy and not to intolerance.
LACTOSE = {
    "lactose": ("avoid", "the sugar that isn't tolerated"),
    "milk": ("caution", "contains lactose, though quantity matters"),
    "cream": ("caution", "contains lactose"),
    "whey": ("caution", "whey powder is high in lactose"),
    "milk powder": ("avoid", "concentrated lactose"),
    "milk solids": ("avoid", "concentrated lactose"),
    "condensed milk": ("avoid", "concentrated lactose"),
    "butter": ("ok", "almost no lactose remains in butter"),
    "ghee": ("ok", "clarified, so effectively lactose free"),
}

WHEAT = {
    "wheat": ("avoid", "wheat"), "semolina": ("avoid", "durum wheat"),
    "durum": ("avoid", "a wheat"), "spelt": ("avoid", "a wheat"),
    "farro": ("avoid", "a wheat"), "kamut": ("avoid", "a wheat"),
    "couscous": ("avoid", "made from wheat"), "seitan": ("avoid", "wheat gluten"),
    "graham flour": ("avoid", "wheat flour"), "bulgur": ("avoid", "cracked wheat"),
}

SULPHITE = {
    "sulphite": ("avoid", "a sulphite"), "sulfite": ("avoid", "a sulphite"),
    "sulphur dioxide": ("avoid", "a sulphite"), "sulfur dioxide": ("avoid", "a sulphite"),
    "metabisulphite": ("avoid", "a sulphite"), "metabisulfite": ("avoid", "a sulphite"),
    "e220": ("avoid", "sulphur dioxide"), "e221": ("avoid", "a sulphite"),
    "e222": ("avoid", "a sulphite"), "e223": ("avoid", "a sulphite"),
    "e224": ("avoid", "a sulphite"), "e226": ("avoid", "a sulphite"),
    "e227": ("avoid", "a sulphite"), "e228": ("avoid", "a sulphite"),
}

MUSTARD = {"mustard": ("avoid", "mustard"), "mustard seed": ("avoid", "mustard")}
CELERY = {"celery": ("avoid", "celery"), "celeriac": ("avoid", "celery root"),
          "celery salt": ("avoid", "celery")}
LUPIN = {"lupin": ("avoid", "lupin"), "lupine": ("avoid", "lupin")}

PORK = {
    "pork": ("avoid", "pork"), "bacon": ("avoid", "pork"), "ham": ("avoid", "pork"),
    "lard": ("avoid", "pork fat"), "gelatin": ("caution", "often from pork"),
    "gelatine": ("caution", "often from pork"), "pepsin": ("avoid", "from pig stomach"),
    "prosciutto": ("avoid", "pork"), "chorizo": ("caution", "usually pork"),
}

ALLERGENS: dict[str, dict[str, tuple[str, str]]] = {
    "peanut": PEANUT, "tree_nut": TREE_NUT, "soy": SOY, "egg": EGG,
    "fish": FISH, "shellfish": SHELLFISH, "mollusc": MOLLUSC, "sesame": SESAME,
    "milk": MILK, "lactose": LACTOSE, "wheat": WHEAT, "sulphite": SULPHITE,
    "mustard": MUSTARD, "celery": CELERY, "lupin": LUPIN, "pork": PORK,
}

LABELS = {
    "peanut": "Peanut free", "tree_nut": "Tree nut free", "soy": "Soy free",
    "egg": "Egg free", "fish": "Fish free", "shellfish": "Shellfish free",
    "mollusc": "Mollusc free", "sesame": "Sesame free", "milk": "Milk free",
    "lactose": "Low lactose", "wheat": "Wheat free", "sulphite": "Sulphite free",
    "mustard": "Mustard free", "celery": "Celery free", "lupin": "Lupin free",
    "pork": "No pork",
}

# The word before a term can cancel it entirely. Without this, every jar of
# peanut butter reads as dairy.
NEGATIONS: dict[str, tuple[str, ...]] = {
    "butter": ("peanut", "cocoa", "shea", "almond", "nut", "apple", "cashew",
               "sunflower", "seed", "body", "mango", "coconut"),
    "milk": ("coconut", "almond", "soy", "soya", "oat", "rice", "cashew", "hemp",
             "hazelnut", "macadamia", "pea", "flax", "thistle"),
    "cream": ("coconut", "ice", "non dairy", "nondairy", "tartar", "of tartar",
              "soy", "oat", "almond"),
    "cheese": ("vegan", "plant based", "nut", "cashew"),
    "yogurt": ("coconut", "soy", "almond", "oat", "vegan"),
    "nut butter": (),
    "coconut": (),
}

_MATCHERS = {k: build_matcher(v) for k, v in ALLERGENS.items()}

# "May contain" statements are a separate class of information: not an
# ingredient, but the manufacturer telling you they cannot rule it out.
_PRECAUTIONARY = re.compile(
    r"(may contain|may also contain|manufactured in a facility|made in a facility|"
    r"produced in a facility|shared equipment|shared facility|may be present|"
    r"traces of|packed in a facility)([^.;]*)",
    re.IGNORECASE,
)


def precautionary(text: str | None) -> list[str]:
    """Cross-contamination statements, returned verbatim.

    These are quoted rather than parsed. A 'may contain' warning is the
    manufacturer's own wording about risk, and paraphrasing it would be a worse
    kind of confident.
    """
    if not text:
        return []
    out = []
    for m in _PRECAUTIONARY.finditer(text):
        phrase = " ".join(m.group(0).split())[:160].strip(" ,")
        if phrase and phrase not in out:
            out.append(phrase)
    return out


def split_precautionary(text: str | None) -> tuple[str, str]:
    """Separate the ingredient list from the 'may contain' tail.

    A label ending "MAY CONTAIN PEANUT" is telling you the opposite of what an
    ingredient line means. Scanning it as one string reports peanut as a
    confirmed ingredient, which is both wrong and the kind of wrong that
    persuades someone to distrust every other flag.
    """
    if not text:
        return "", ""
    m = _PRECAUTIONARY.search(text)
    if not m:
        return text, ""
    return text[:m.start()], text[m.start():]


def check(ingredients_text: str | None, selected: list[str]) -> list[Flag]:
    """Allergen flags for the selected sensitivities."""
    if not selected:
        return []
    if not ingredients_text:
        return [Flag("unknown", "No ingredient list",
                     "There is no ingredient text to check for allergens.")]

    declared, warning_tail = split_precautionary(ingredients_text)

    flags: list[Flag] = []
    for key in selected:
        rules = ALLERGENS.get(key)
        if not rules:
            continue
        label = LABELS.get(key, key)
        hits = [t for t in find_terms(declared, _MATCHERS[key], NEGATIONS)
                if rules[t][0] != "ok"]
        for term in hits:
            level, why = rules[term]
            flags.append(Flag(level, f"{label}: {term}",
                              f"{term.title()} — {why}.", term))
        if not hits:
            flags.append(Flag("ok", label, "Nothing matching was found in the list."))

    for phrase in precautionary(ingredients_text):
        flags.append(Flag(
            "caution", "Cross-contamination warning",
            f'The label says: "{phrase}". Whether that matters is your call, not the app\'s.',
        ))

    return flags
