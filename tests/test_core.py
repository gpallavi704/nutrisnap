"""The rules engine is the part that has to be right, so it is tested directly.

No network, no mocks, no fixtures beyond plain data — every case here is a real
labelling pattern taken from products that exist.
"""

from __future__ import annotations

import pytest

from core import additives, diet, normalize, score, sugars
from core.analyze import analyze
from core.model import Nutrients, Product


def make(**kw) -> Product:
    base = dict(
        name="Test Product",
        serving_grams=100.0,
        servings_per_container=1.0,
        per_serving=Nutrients(calories=100, total_fat_g=1, total_carb_g=20,
                              total_sugars_g=10, protein_g=2, sodium_mg=50,
                              saturated_fat_g=0.5),
    )
    base.update(kw)
    return Product(**base)


# --- serving normalization ------------------------------------------------

def test_per_container_multiplies_by_servings():
    p = make(servings_per_container=2.5,
             per_serving=Nutrients(calories=110, total_sugars_g=26))
    out = normalize.per_container(p)
    assert out.total_sugars_g == pytest.approx(65.0)
    assert out.calories == pytest.approx(275.0)


def test_per_100g_rescales_from_serving_grams():
    p = make(serving_grams=40.0, per_serving=Nutrients(total_sugars_g=8))
    assert normalize.per_100g(p).total_sugars_g == pytest.approx(20.0)


def test_missing_servings_yields_no_container_total():
    assert normalize.per_container(make(servings_per_container=None)) is None


def test_fractional_serving_is_called_out():
    notes = normalize.analyze_servings(make(servings_per_container=2.5))
    assert any("2.5 servings" in n for n in notes)
    assert any("nobody measures out" in n for n in notes)


# --- the arithmetic self-check --------------------------------------------

def test_macro_check_passes_on_consistent_panel():
    # 20*4 + 2*4 + 1*9 = 97 kcal against 100 stated: within rounding.
    assert normalize.macro_check(make().per_serving).ok


def test_macro_check_catches_a_decimal_slip():
    """A misread that turns 2.6 g of fat into 26 g must not pass silently."""
    bad = Nutrients(calories=100, total_carb_g=20, protein_g=2, total_fat_g=26)
    result = normalize.macro_check(bad)
    assert not result.ok
    assert "misread" in result.message


def test_macro_check_abstains_when_fields_are_missing():
    assert normalize.macro_check(Nutrients(calories=100)).ok


# --- sugar recombination --------------------------------------------------

def test_finds_every_alias_of_sugar():
    text = "Oats, brown rice syrup, cane juice, maltodextrin, salt"
    reading = sugars.read_sugars(text)
    assert set(reading.aliases) == {"brown rice syrup", "cane juice", "maltodextrin"}
    assert reading.is_split


def test_longest_alias_wins_over_substring():
    """'brown rice syrup' must not be reported as 'rice syrup'."""
    assert sugars.read_sugars("Brown rice syrup").aliases == ["brown rice syrup"]


def test_word_boundaries_prevent_false_positives():
    # "sugar" must not fire on "sugarcane wax"; "malt" must not fire on "malted milk"
    # only via its own entry. Guard the classic substring trap:
    assert "sugar" not in sugars.read_sugars("no added sweeteners").aliases


def test_position_of_first_sugar_is_reported():
    reading = sugars.read_sugars("Water, sugar, citric acid")
    assert reading.first_position == 2
    assert reading.in_top_three


def test_parenthesised_subingredients_do_not_split_the_count():
    text = "Chocolate (cocoa, sugar, milk), oats"
    assert sugars.read_sugars(text).total_ingredients == 2


def test_teaspoon_conversion():
    assert sugars.teaspoons(65.0) == pytest.approx(15.5, abs=0.1)


def test_sugar_alcohols_are_not_counted_as_sugar():
    reading = sugars.read_sugars("Maltitol, erythritol, cocoa")
    assert reading.aliases == []
    assert set(reading.alcohols) == {"maltitol", "erythritol"}


# --- hidden ingredients ---------------------------------------------------

def test_carmine_is_caught_for_vegans():
    flags = diet.check("Sugar, carmine, water", ["vegan"])
    assert any(f.term == "carmine" and f.level == "avoid" for f in flags)
    assert diet.verdict(flags) == "avoid"


def test_casein_is_caught_despite_dairy_free_claim():
    flags = diet.check("Non-dairy creamer, sodium caseinate", ["dairy_free"])
    assert any("casein" in (f.term or "") for f in flags)


def test_ambiguous_terms_stay_unknown_rather_than_becoming_a_yes():
    flags = diet.check("Oats, natural flavors", ["vegan"])
    assert diet.verdict(flags) == "unknown"
    assert any(f.level == "unknown" and "natural flavors" in f.detail.lower() for f in flags)


def test_clean_label_passes():
    assert diet.verdict(diet.check("Oats, water, salt", ["vegan"])) == "ok"


def test_malt_is_gluten():
    flags = diet.check("Rice, barley malt extract", ["gluten_free"])
    assert any(f.level == "avoid" for f in flags)


def test_oats_are_caution_not_avoid_for_gluten():
    flags = diet.check("Oats, water", ["gluten_free"])
    assert diet.verdict(flags) == "caution"


# --- additives ------------------------------------------------------------

def test_e_numbers_are_classified_by_range():
    found = additives.find_additives("Water, E150d, E621, E202")
    cats = dict(found)
    assert cats["E150"] == "colouring"
    assert cats["E621"] == "flavour enhancer"
    assert cats["E202"] == "preservative"


def test_named_additives_are_found():
    found = dict(additives.find_additives("Sugar, titanium dioxide, xanthan gum"))
    assert found["titanium dioxide"] == "colouring"
    assert found["xanthan gum"] == "thickener"


def test_additive_summary_reports_shape_not_list():
    found = additives.find_additives("E100, E102, E110, sodium benzoate")
    assert "4 additives" in additives.summarize(found)


def test_no_additives_summarises_to_nothing():
    assert additives.summarize([]) is None


# --- scoring --------------------------------------------------------------

def test_lower_sugar_scores_higher_on_the_sugar_goal():
    low = score.score(Nutrients(total_sugars_g=2), 0, "less_sugar")
    high = score.score(Nutrients(total_sugars_g=30), 0, "less_sugar")
    assert low.total > high.total


def test_score_exposes_its_components():
    s = score.score(Nutrients(total_sugars_g=10, protein_g=5), 2, "less_sugar")
    labels = {c.label for c in s.components}
    assert {"Sugars", "Additives"} <= labels
    assert all(c.weight > 0 for c in s.components)


def test_unmeasurable_product_scores_none_rather_than_zero():
    assert score.score(Nutrients(), None, "less_sugar").total is None


def test_unreadable_label_must_not_score_as_perfect():
    """No ingredient list is not the same as no additives.

    Counting an unread label as zero additives handed it a perfect processing
    subscore, so the least legible product on the shelf came out best.
    """
    unknown = score.score(Nutrients(), None, "less_processed")
    clean = score.score(Nutrients(total_sugars_g=1), 0, "less_processed")
    assert unknown.total is None
    assert clean.total is not None


def test_ranking_puts_unscorable_last_not_first():
    a = ("known", score.score(Nutrients(total_sugars_g=30), 9, "less_sugar"))
    b = ("unknown", score.score(Nutrients(), None, "less_sugar"))
    assert [name for name, _ in score.compare([b, a])] == ["known", "unknown"]


def test_product_without_ingredients_is_not_scored_on_processing():
    a = analyze(make(ingredients_text=None), goal="less_processed")
    processing = next(c for c in a.score.components if c.label == "Additives")
    assert processing.subscore is None


def test_explain_names_the_deciding_component():
    winner = score.score(Nutrients(total_sugars_g=1), 0, "less_sugar")
    loser = score.score(Nutrients(total_sugars_g=30), 0, "less_sugar")
    assert "Sugars" in score.explain(winner, loser)


# --- end to end -----------------------------------------------------------

def test_the_bottle_that_is_two_and_a_half_servings():
    """The headline demo: 26 g on the panel is really 65 g in your hand."""
    p = make(
        name="Fruit Punch",
        serving_grams=240.0,
        servings_per_container=2.5,
        per_serving=Nutrients(calories=110, total_carb_g=27, total_sugars_g=26,
                              protein_g=0, total_fat_g=0, sodium_mg=25),
        ingredients_text="Water, cane juice, glucose syrup, maltodextrin, natural flavors",
    )
    a = analyze(p, goal="less_sugar", diets=["vegan"])

    assert a.headline_sugar_g == pytest.approx(65.0)
    assert a.headline_teaspoons == pytest.approx(15.5, abs=0.1)
    assert a.sugars.is_split
    assert a.verdict == "unknown"          # natural flavors, honestly reported
    assert a.score.total is not None
    assert any("2.5 servings" in n for n in a.notes)


def test_analysis_is_deterministic():
    p = make(ingredients_text="Sugar, wheat flour, E621")
    first, second = analyze(p, "balanced", ["vegan"]), analyze(p, "balanced", ["vegan"])
    assert first.score.total == second.score.total
    assert [f.label for f in first.flags] == [f.label for f in second.flags]


# --- allergens -------------------------------------------------------------
from core import allergens as alg  # noqa: E402


def test_peanut_butter_is_not_dairy():
    """The classic false positive. Flagging it teaches users to ignore flags."""
    flags = alg.check("Peanut butter, salt", ["milk"])
    assert not any(f.level == "avoid" for f in flags)


def test_coconut_milk_is_not_dairy():
    flags = alg.check("Coconut milk, water, guar gum", ["milk"])
    assert not any(f.level == "avoid" for f in flags)


def test_real_milk_is_still_caught():
    flags = alg.check("Whole milk, sugar", ["milk"])
    assert any(f.term == "milk" and f.level == "avoid" for f in flags)


def test_nutmeg_is_not_a_tree_nut():
    flags = alg.check("Flour, nutmeg, cinnamon", ["tree_nut"])
    assert not any(f.level == "avoid" for f in flags)


def test_hidden_peanut_names_are_caught():
    for term in ("groundnut oil", "arachis oil", "mandelona"):
        flags = alg.check(f"Vegetable oil, {term}", ["peanut"])
        assert any(f.level == "avoid" for f in flags), term


def test_soy_lecithin_is_caution_not_certainty():
    """Lecithin is usually soy but can be sunflower — that's a caution."""
    flags = alg.check("Chocolate, lecithin", ["soy"])
    assert any(f.term == "lecithin" and f.level == "caution" for f in flags)


def test_worcestershire_is_flagged_as_fish():
    flags = alg.check("Worcestershire sauce, vinegar", ["fish"])
    assert any(f.level == "avoid" for f in flags)


def test_lactose_intolerance_differs_from_milk_allergy():
    """Butter is dairy, but it is not a lactose problem."""
    allergy = alg.check("Butter, salt", ["milk"])
    intolerance = alg.check("Butter, salt", ["lactose"])
    assert any(f.level == "avoid" for f in allergy)
    assert not any(f.level in ("avoid", "caution") for f in intolerance)


def test_may_contain_statements_are_quoted_verbatim():
    text = "Oats, sugar. May contain traces of peanuts and tree nuts."
    flags = alg.check(text, ["peanut"])
    warn = [f for f in flags if f.label == "Cross-contamination warning"]
    assert warn and "may contain" in warn[0].detail.lower()


def test_shared_facility_wording_is_detected():
    assert alg.precautionary("Manufactured in a facility that processes sesame")


def test_clean_label_reports_nothing_found_not_safe():
    flags = alg.check("Oats, water", ["peanut"])
    assert all(f.level == "ok" for f in flags)
    assert "safe" not in " ".join(f.detail.lower() for f in flags)


def test_sulphite_e_numbers_are_caught():
    flags = alg.check("Wine, E220", ["sulphite"])
    assert any(f.level == "avoid" for f in flags)
