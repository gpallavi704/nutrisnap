# Build prompt

Paste the block below into an AI coding assistant to rebuild this application
from scratch. It is written as a specification rather than a description,
because the traps in section 7 are what separate a working version from one
that quietly reports wrong numbers.

---

## The prompt

Build a web application called **NutriSnap** that reads a grocery food label and
tells the user what the arithmetic actually says.

### 1. The problem it solves

Everything a shopper needs is printed on the package, arranged so that no single
number tells the truth. Sugar is split across many names so none of them reaches
the top of the ingredient list. Quantities are declared per serving when nobody
eats one serving: a 20 oz bottle stating "26 g sugar" is 2.5 servings, so the
real figure is 65 g. Allergens hide behind derivatives that do not look like what
they are, because casein is milk, carmine is insects, isinglass is fish.

The app puts that back together and says what it found in plain language.

### 2. The one architectural rule

**The model reads. The code decides.**

A vision model is used only to transcribe what is printed on a label. Every
judgement (sugar recombination, serving normalisation, allergen matching,
scoring, the written summary) must be deterministic Python with no network
access and no clock, so that the same product always produces the same verdict
and any wrong number can be traced to a line of code.

Put that logic in a `core/` package that never imports from the API or service
layers. It must be unit-testable without mocking a network.

### 3. Stack

- FastAPI backend, deployable as a serverless function
- One static HTML page, vanilla JS, no build step
- `uv` for packaging, `pytest` for tests
- A vision-capable LLM for the photo path only
- Open Food Facts for barcode lookups (free, no API key)

### 4. Two ways in

**Scan one product.** Decode the barcode *in the browser* using the
`BarcodeDetector` API. If a barcode is found, send only the digits and look the
product up in Open Food Facts, which is exact. If there is no barcode, downscale
the image to about 1100px in the browser and send it to the vision model for
transcription. Ask the model for strict JSON, tell it to copy numbers exactly and
to return null rather than estimate.

**Upload a CSV shopping list.** Parse tolerantly: accept any column named like a
barcode, otherwise the first field shaped like one, and cope with a missing
header row. Analyse the whole list, then show summary tiles, a ranking chart, a
sortable and filterable table, and a CSV export.

### 5. The rules engine

**Serving normaliser.** Convert every product to per-container and per-100g, so
two products of different sizes are comparable.

**Sugar recombiner.** Match roughly 65 sweetener aliases (dextrose, maltodextrin,
evaporated cane juice, brown rice syrup, agave, barley malt, fruit juice
concentrate and so on), sum them, and report the total in grams and teaspoons at
4.2 g per teaspoon. Track sugar alcohols separately, since they are not sugars
but do cause digestive problems. Report the position of the first sweetener in
the ingredient list.

**Additive classifier.** Detect E-numbers and classify them by their numeric
range, which is a real standard: 100-199 colouring, 200-299 preservative,
300-399 antioxidant, 400-499 thickener, 600-699 flavour enhancer. Also match
named additives. Report the shape ("9 additives, 3 of them colourings") rather
than the list.

**Hidden ingredient rules.** For vegan, vegetarian, gluten-free and dairy-free,
match derivatives, not just obvious words: casein, caseinate, whey, gelatin,
carmine, cochineal, shellac, isinglass, lard, tallow, rennet, L-cysteine, malt,
semolina, spelt, brewer's yeast.

**Allergens.** Cover the US big nine (peanut, tree nut, soy, egg, fish,
shellfish, sesame, milk, wheat) plus the extra EU declarables (molluscs,
mustard, celery, lupin, sulphites). Treat **lactose intolerance as a different
condition from milk allergy**: butter and ghee are dairy but effectively
lactose-free, and conflating them serves neither person.

**Macro sanity check.** Verify that calories ≈ 4·carbs + 4·protein + 9·fat within
about 25%. This is how an OCR misread announces itself: a decimal slip that turns
2.6 g into 26 g breaks the arithmetic. Flag the reading instead of reporting it.

**Goal scoring.** Score 0-100 against a chosen goal (cut sugar, more protein,
less sodium, less processed, balanced) using the published UK FSA front-of-pack
thresholds rather than invented numbers. Always expose the component subscores.
The score is a *fit against the chosen goal*, not a health score, and the UI must
say so.

**Plain summary.** Two or three sentences at the top of each result: what the
diet and allergen checks concluded, what the number means and why, and the sugar
figure when it is worth mentioning. Generate this with rules, not a model. It
describes figures the app just computed, so a model can add nothing except the
risk of contradicting the panel directly above it.

### 6. Honesty rules, non-negotiable

- **Never claim safety.** Report "nothing matching was found", which is a claim
  about a text string, not about a food.
- **Never round uncertainty into a yes.** "Natural flavors", "mono- and
  diglycerides" and "lecithin" can be plant or animal derived and the label will
  never say which. They stay permanently amber.
- **Missing data is not good data.** A product whose label could not be read gets
  no score at all. Require at least half the goal's weighting to be measurable
  before producing a number.
- **A false alarm has a cost.** Over-warning teaches users to ignore warnings.

### 7. Traps that will produce wrong output if ignored

Each of these was a real defect. Handle them explicitly.

1. **"May contain" is not an ingredient.** Split precautionary wording off the
   end of the ingredient text *before* any matching, and surface it only as a
   cross-contamination caution. Otherwise a label reading "MAY CONTAIN PEANUT"
   is reported as peanut being a confirmed ingredient.

2. **Negation before allergen matching.** "Peanut butter" is not dairy, "coconut
   milk" is not dairy, "nutmeg" is not a tree nut. Check the preceding word.

3. **Longest match wins.** "Brown rice syrup" must not be reported as "rice
   syrup". Sort terms by length before building the matcher, and use word
   boundaries.

4. **Drinks need their own scoring bands.** Beverages are mostly water, so per
   100 ml a full-sugar cola looks mild on food thresholds and scores well. Use
   the separate FSA beverage bands, roughly halved.

5. **A multipack is not a serving occasion.** A 30-bar box reporting "42
   teaspoons per package" is true and useless. Above about four servings, fall
   back to per-serving and say how many the box holds.

6. **Absence of evidence is not evidence.** Zero *detected* additives on a label
   you could not read is not zero *actual* additives. An unreadable product
   scored 100/100 until this was fixed.

7. **Open Food Facts stores sodium and salt in grams**, while US panels print
   milligrams. Also validate: one real product stores sodium as `3.38e-07 g`.
   Treat sub-milligram values as a contributor error.

8. **Distinguish "not in the database" from "could not reach the database".**
   Rapid batch lookups get throttled, and recording every 503 as a miss produced
   a 47% "coverage" statistic that was really a rate limit. Retry with backoff,
   share one connection, and report the two cases separately.

9. **Ingredient text comes back in the product's own language.** Prefer the
   English field, or an English-only rules engine will silently match nothing.

10. **Many products declare no serving size.** Fall back to the per-100g column
    and label it honestly. Do not print "per serving" for a figure that is per
    100 g.

### 8. API

- `POST /api/analyze` — `{barcode?, image?, goal, diets[], allergens[]}`, barcode
  preferred, vision as fallback
- `POST /api/batch` — a list of barcodes, returns products plus a summary with
  coverage, median score and flagged count
- `GET /api/health` — reports whether vision is configured, and serves the goal,
  diet and allergen vocabularies so the front end has one source of truth

Degrade honestly: if no model key is configured, the barcode and CSV paths must
still work completely, and the app should say why the photo path is unavailable.

### 9. Interface

A landing page that makes the argument before asking for anything: a headline, a
worked example of the 26 g versus 65 g bottle with the sugar drawn as cubes, and
a grid of already-scored real products.

Each result card shows the plain summary, a score dial, the sugar reveal as
drawn cubes, a real FDA-style Nutrition Facts panel with a
serving/package/per-100g switch, the flags, and a collapsible ingredient list
**with the matched sugars, allergens and unknowns highlighted in place**. That
highlight is the most persuasive element in the app: it shows the splitting
rather than asserting it.

Collapse passing checks into one line. Four green "nothing found" rows will
drown the one red row that matters.

Reserve green, amber and red for verdicts only. If you want colour elsewhere,
colour the categories.

Measure contrast rather than eyeballing it. Every text pair should clear WCAG AA,
and check the warning colour first, because it carries the allergen text.

### 10. Tests

Unit-test the rules engine directly, with no mocks. At minimum cover: the 2.5
serving bottle producing 65 g, the macro check catching a decimal slip, longest
alias matching, peanut butter not flagging dairy, "may contain" not reading as an
ingredient, the multipack fallback, an unreadable label scoring None rather than
100, and beverage bands scoring a cola below a food equivalent.

Aim for roughly 60 tests. They should run in under a second, because none of them
touch a network.
