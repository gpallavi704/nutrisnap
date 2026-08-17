"""A plain-language verdict, assembled from the same numbers as everything else.

The card was showing a score, a panel, six flags and three notes, and leaving
the reader to work out what it all added up to. This says it in two or three
sentences.

Written by rules rather than by a model on purpose. It is describing figures the
app just computed, so there is nothing for a language model to add except the
risk of describing them wrongly — and a summary that contradicts the panel above
it would undo the whole point of the shared pipeline.
"""

from __future__ import annotations

from core.score import GOALS

BANDS = [
    (80, "an excellent fit"),
    (65, "a good fit"),
    (45, "a middling fit"),
    (25, "a poor fit"),
    (0, "a bad fit"),
]


def _fit(total: float | None) -> str:
    if total is None:
        return "not scorable"
    for floor, phrase in BANDS:
        if total >= floor:
            return phrase
    return "a bad fit"


def _list(items: list[str], limit: int = 3) -> str:
    items = items[:limit + 1]
    if len(items) > limit:
        items = items[:limit] + ["more"]
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def verdict_sentence(analysis) -> str | None:
    """What the chosen diets and allergens actually concluded."""
    flags = analysis.flags
    if not flags:
        return None

    blocked = [f for f in flags if f.level == "avoid"]
    unsure = [f for f in flags if f.level == "unknown" and f.term]
    passed = [f for f in flags if f.level == "ok"]

    if blocked:
        checks = _list(sorted({f.label.split(":")[0] for f in blocked}))
        terms = _list([f.term or f.label for f in blocked])
        sentence = f"Not {checks.lower()} — it contains {terms}."
    elif passed:
        checks = _list(sorted({f.label for f in passed}))
        sentence = f"Nothing was found for {checks.lower()}."
    else:
        sentence = None

    if unsure:
        terms = _list([f.term for f in unsure if f.term])
        if blocked:
            # Already a definite no. "Can't be confirmed either way" would
            # undercut the sentence before it.
            sentence += f" ({terms.capitalize()} can't be traced from the label either.)"
        elif sentence:
            sentence += (f" {terms.capitalize()} can't be traced from the label, "
                         "so it can't be confirmed either way.")
        else:
            sentence = (f"{terms.capitalize()} can't be traced from the label, "
                        "so this can't be confirmed either way.")
    return sentence


def score_sentence(analysis) -> str:
    """What the number means, in words, with the reason attached."""
    s = analysis.score
    goal = GOALS.get(s.goal, {}).get("label", s.goal).lower()

    if s.total is None:
        return s.reason or f"There wasn't enough on the label to judge it for {goal}."

    scored = [c for c in s.components if c.subscore is not None]
    best = max(scored, key=lambda c: c.subscore, default=None)
    worst = min(scored, key=lambda c: c.subscore, default=None)

    text = f"It scores {s.total:.0f} out of 100 for {goal}"
    if best is not None and best.subscore >= 70:
        text += f", helped by {best.label.lower()} at {best.value:.1f} {best.unit}"
    if worst is not None and worst.subscore < 45 and worst is not best:
        text += f"; {worst.label.lower()} is the weak point at {worst.value:.1f} {worst.unit}"
    return text + "."


def sugar_sentence(analysis) -> str | None:
    """Only worth a sentence when there is something to say about it."""
    tsp = analysis.headline_teaspoons
    if tsp is None:
        return None
    if tsp >= 4:
        return (f"That's about {tsp:.0f} teaspoons of sugar per "
                f"{analysis.basis_label}.")
    if analysis.sugars.is_split:
        return (f"Sugar appears under {len(analysis.sugars.aliases)} different "
                "names, which keeps any single one low in the ingredient list.")
    return None


def summarize(analysis) -> str:
    """Two or three sentences a person can act on."""
    parts = [
        verdict_sentence(analysis),
        score_sentence(analysis),
        sugar_sentence(analysis),
    ]
    return " ".join(p for p in parts if p)
