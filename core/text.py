"""Ingredient-list matching.

Ingredient lists are hostile to naive string matching: they contain nested
parentheses, inconsistent punctuation, and terms that are substrings of other
terms. "Milk" appears inside "buttermilk" and inside "milk thistle"; matching
without word boundaries flags things that aren't there.

Every matcher here compiles one alternation with explicit boundaries, longest
term first so that "brown rice syrup" wins over "rice syrup".
"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace and separators.

    Labels use en-dashes, non-breaking spaces, and accented spellings
    inconsistently. Folding them means one spelling of each term to maintain.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("-", " ").replace("_", " ")
    return _WS.sub(" ", text).strip()


def build_matcher(terms) -> re.Pattern:
    """One compiled pattern matching any term on a word boundary."""
    ordered = sorted({normalize(t) for t in terms if t}, key=len, reverse=True)
    if not ordered:
        return re.compile(r"(?!)")  # matches nothing
    joined = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in ordered)
    return re.compile(rf"(?<![a-z]){joined}(?![a-z])")


def find_terms(text: str, matcher: re.Pattern) -> list[str]:
    """Distinct matches, in the order they appear.

    Order matters on an ingredient list: it is sorted by weight, so a sugar in
    position two says something a sugar in position twelve does not.
    """
    seen, out = set(), []
    for m in matcher.finditer(normalize(text)):
        term = m.group(0)
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out


def split_ingredients(text: str) -> list[str]:
    """Best-effort split into individual ingredients.

    Commas inside parentheses are sub-ingredients of the preceding item, so
    depth is tracked rather than splitting on every comma.
    """
    items, buf, depth = [], [], 0
    for ch in text or "":
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf).strip())
    return [i for i in (x.strip(" .") for x in items) if i]
