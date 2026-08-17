# NutriSnap: Project Documentation

**Week 1, Path B (build your own vibe-coded app)**
Repository: https://github.com/gpallavi704/nutrisnap
Live: https://nutrisnap-nu-seven.vercel.app

---

## 1. Problem statement

Everything a shopper needs is already printed on a food package. It is arranged
so that no single number tells the truth.

Sugar is split across six names so that none of them reaches the top of the
ingredient list. Quantities are declared per serving when nobody eats one
serving: a 20 oz bottle that says "26 g of sugar" is 2.5 servings, so the real
figure is 65 g, about sixteen teaspoons. Allergens hide behind derivatives that
do not look like what they are, because casein is milk, carmine is insects and
isinglass is fish.

NutriSnap reads a label, puts the arithmetic back together, and says what it
found in plain language.

**Two ways in:**
- **Scan** a product with a phone camera or an uploaded photo
- **Upload a CSV** shopping list and rank the whole lot against one goal

## 2. Datasets and data sources

| Source | Licence | Used for |
|---|---|---|
| **Open Food Facts** | ODbL (data), CC-BY-SA (images) | Barcode lookups, ingredient text, nutrition, product photographs |
| `data/pantry.csv` | Built for this project | 30 real products across 10 categories, the CSV demo dataset |
| `data/showcase.json` | Derived | 21 products with photographs and pre-computed scores for the landing page |
| **UK FSA front-of-pack bands** | Published standard | Scoring thresholds for sugar, saturated fat, salt |

The pantry CSV was assembled by querying the Open Food Facts search API across
ten categories and keeping only products with a complete ingredient list, a
declared serving and calorie data.

Retailer sites such as Amazon and Target were considered as an image source and
rejected: their terms prohibit automated scraping, the photographs are
copyrighted, and crucially they carry **no ground truth**, so every product
would have to be hand-labelled. Open Food Facts ships the answer key with the
photo.

## 3. Stack

- **Backend**: FastAPI, deployed as a Python serverless function on Vercel
- **Frontend**: one HTML file, vanilla JS, no build step
- **Vision**: Groq, `qwen/qwen3.6-27b`
- **Data**: Open Food Facts REST API
- **Package management**: uv
- **Testing**: pytest, 59 tests over the rules engine

### The architectural decision that shaped everything

**The model reads. The code decides.**

The vision model is only ever asked to transcribe what is printed. Every
judgement (sugar recombination, serving normalization, allergen matching,
scoring) is deterministic Python in `core/`, which has no network access and no
clock. The same product always produces the same verdict, and the reasoning can
be audited rather than trusted.

`core/` never imports from `services/` or `api/`, which is what makes it
testable without mocking a network.

## 4. Prompts used, and what each one changed

This is the actual sequence, not a tidied version.

**"Which one will be more useful for more public? I'm targeting more audience, impactful and creative."**
Forced a comparison of three concepts by reach and by whether they could be
grounded in verifiable data. Restaurant menus reach more people; grocery labels
can be checked against a database. Chose the one that could be proven correct.

**"What about grocery store item labels? Can it get nutritional facts from a picture?"**
Established the two-path design: barcode for exactness, vision as fallback.

**"Let's discuss the infrastructure first."**
Deciding this before writing code avoided rework. Three decisions came out of
it: no database (the tray lives in browser state), stateless backend, and
barcode decoding moved into the browser once Vercel was chosen, because OpenCV
would have exceeded the function size limit.

**"I am not comfortable using my Gemini keys. What other alternatives?"**
Rather than assuming, the available Groq models were probed with a test image.
`qwen/qwen3.6-27b` turned out to accept images and read all nine panel fields
correctly at temperature 0, in one second. This removed an entire vendor
dependency: one provider, one key, one secret to protect.

**"Why don't we do this: we will upload CSV and also provide real phone scan."**
Produced batch mode. This also closed a gap against the week's stated learning
outcomes, which name CSV datasets, charts, filters and tables.

**"I uploaded a Barebells picture and I find it confusing."**
The most productive prompt of the project. See section 6.

**"What does this score mean? Should we put a small summary in simple language?"**
Produced the plain-language verdict at the top of every card, and the
realisation that the score needed to be labelled as *fit against a chosen goal*
rather than a health score.

**"I need a nice UI", then "I am talking about the landing page", then "see nutrition.gov", then "you just added colors, I asked for illustrative images."**
Four prompts for one outcome, because the first three answers solved the wrong
problem. See section 7.

## 5. Iterations

| # | What changed | Why |
|---|---|---|
| 1 | Core rules engine + tests | Built first, with no UI, because it is the part that has to be right |
| 2 | Open Food Facts + Groq vision | Two data paths, barcode preferred |
| 3 | FastAPI + single-page frontend | Chosen over Streamlit for design control |
| 4 | Nutrition Facts panel per card | Cards showed a score but no calories, sodium or protein |
| 5 | 16 allergens + cross-contamination | Requested mid-build; lactose intolerance separated from milk allergy |
| 6 | Batch CSV mode | Turned a scanner into a data application |
| 7 | Plain-language summary | The card had six flags and no conclusion |
| 8 | Landing page, background, illustrations | Four rounds, see section 7 |

## 6. Bugs, and how they were found

**Every bug that mattered was found by running the app against real products.
None came from reading the code.**

| Bug | Symptom | Cause |
|---|---|---|
| Silent tool failure | The AI answered "I don't have the data" to every question | Groq returns `arguments: 'null'` for no-argument tools; `json.loads('null')` is `None`, so `fn(**args)` raised and was swallowed |
| Perfect score for an unreadable label | 100/100 | Zero *detectable* additives was treated as zero *actual* additives. Absence of evidence read as evidence of quality |
| Coca-Cola scored 77 for "cut sugar" | Implausible | Drinks are mostly water and look mild per 100 ml on food thresholds. The FSA publishes separate beverage bands; with those it scores 40 |
| Nutella returned nothing | Empty panel | No serving is declared, and the per-100g fallback required one. Ingredients also came back in French |
| Sodium of 0.0002 mg | Absurd value | The database genuinely stores `3.38e-07 g` for that product. A contributor error, now treated as missing |
| "MAY CONTAIN PEANUT" reported as an ingredient | False certainty | The precautionary sentence was being scanned as part of the ingredient list. **The most serious of these:** telling an allergic person a warning is a certainty is how they learn to stop reading warnings |
| A 30-bar box reported 42 teaspoons | True but useless | "Per package" is meaningless for a multipack |
| 47% database coverage | A false statistic | Open Food Facts was throttling 30 rapid lookups and every 503 was recorded as "product not in database". Real coverage is 100% |
| Three WCAG contrast failures | Unreadable small text | Measured rather than eyeballed. The worst offender was the caution colour, which carries allergen warnings |
| "Per serving, split into 12.00 servings" | Self-contradiction | Two clauses written for different cases appearing together |

## 7. The UI iteration, which took four attempts

Worth recording because the failure was instructive.

The request was "make the page look nice, it's plain". The responses were:

1. **SVG category icons** in the results table. Wrong: that screen only appears after loading data.
2. **A landing hero with feature cards.** Still wrong: more content, when the complaint was about the page itself.
3. **Real product photographs in a grid.** Closer, and prompted by being shown nutrition.gov, but still content.
4. **An actual background**: a colour field in food hues, then 27 hand-drawn food illustrations tiled over it.

Only the fourth was what had been asked for, three times. The lesson is not
subtle: *the stated request was "background" every time, and it kept being
answered with "content" because that was the more interesting problem to solve.*

The final background is 27 SVG drawings covering fruit, vegetables, carbs, meat,
protein bars and drinks, inlined as a data URI at about 12KB, at 20% opacity in
light mode and 15% in dark.

## 8. Learnings

**Grounding beats prompting.** The single most valuable design decision was
refusing to let the model make judgements. It transcribes; Python decides. That
is why the app can be unit-tested, why it gives the same answer twice, and why a
wrong number can be traced to a line of code rather than to a prompt.

**Test against reality, early.** Nine of the ten bugs above were invisible in
synthetic tests and obvious within seconds of using real products. Building a
30-product dataset was worth more than any amount of re-reading the code.

**A plausible statistic is more dangerous than an obvious error.** The "47%
coverage" figure looked completely reasonable and would have gone into this
document as a finding. It was a rate limit.

**Correct is not the same as clear.** For the Barebells bar, every number the
app produced was right. It was still confusing, because it said "per serving"
and "split into 12 servings" in the same sentence. With an analysis tool, the
arithmetic being right is the floor, not the achievement.

**Uncertainty is a feature.** "Natural flavors" can be plant or animal derived
and the label will never say which. Guessing would have been more comfortable
and less useful. The amber "can't tell" state is the thing that makes the green
ones trustworthy.

**An AI assistant will happily solve the wrong problem well.** Four attempts at
the background is the clearest example. The fix was for me to state the request
more bluntly, and for the assistant to stop reinterpreting it.

## 9. Deployment, and a deliberate limitation

The deployed site runs **without a Groq key on purpose**. It is public, and a
personal free-tier key would let any visitor spend the daily token budget. So
the hosted build serves everything that needs no model, and the photo path is
enabled only when running locally with a key.

| Feature | Deployed | Local with a key |
|---|---|---|
| Barcode lookup | yes | yes |
| CSV shopping list, ranking, export | yes | yes |
| Allergen and diet flags | yes | yes |
| Sugar recombination, serving maths, scoring | yes | yes |
| Reading a photographed nutrition panel | no, returns a clear message | yes |

Nothing breaks without the key. The photo endpoint returns
`"GROQ_API_KEY is not set, so photo reading is unavailable. Barcode lookup
still works."` and the rest of the app carries on, because the barcode and CSV
paths never touch a model.

Live: https://nutrisnap-nu-seven.vercel.app

## 10. What is not done

- No accuracy evaluation of the vision path against database ground truth. The
  harness is scaffolded but empty; this was the highest-value remaining item.
- The photo path has been tested on a handful of real products, not
  systematically.
- English labels only, and `BarcodeDetector` is unavailable in Safari.

## 11. Reproducing the build

`BUILD_PROMPT.md` in the repository is a single specification prompt that
rebuilds the application from scratch. It carries the ten defects found during
this project forward as explicit requirements, so the next developer inherits
the findings rather than rediscovering them.

## 12. Running it

```bash
git clone https://github.com/gpallavi704/nutrisnap
cd nutrisnap
uv sync
cp .env.example .env     # add a Groq key; barcode and CSV paths work without one
uv run uvicorn api.index:app --reload --port 8010
```

Open http://localhost:8010 and press **Try a sample pantry**.
