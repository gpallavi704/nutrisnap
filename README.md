# NutriSnap

**Nothing on the label is false. That's the problem.**

Sugar hides under six different names. Servings are sized so the numbers look
small. NutriSnap adds it back up and tells you what it found.

Scan one product with your camera, or upload a whole shopping list as CSV and
rank the lot.

```bash
uv sync
cp .env.example .env          # add a Groq key for the photo path
uv run uvicorn api.index:app --reload --port 8010
```

Open http://localhost:8010 and press **Try a sample pantry**.

Live demo: **https://nutrisnap-nu-seven.vercel.app**

---

## The problem, in one product

| The bottle says | What you drink |
|---|---|
| Serving size 8 fl oz | The bottle is 2.5 servings |
| Sugars 26 g | **65 g, about 16 teaspoons** |
| Listed as | cane juice, dextrose, maltodextrin |

Three sweeteners instead of one, so none of them reaches the top of the
ingredient list. Nothing here is illegal. It is arranged.

## The architecture

**The model reads. The code decides.**

```
Browser        resize photo · decode barcode locally · hold the tray
   │
   ├─ barcode found → 13 digits ──► Open Food Facts   (exact, verified)
   └─ no barcode    → small image ─► Groq vision      (transcription only)
                            │
                     core/ rules engine (pure Python, no I/O)
                            ▼
                       JSON verdict
```

The model is never asked for an opinion, only to transcribe what is printed.
Every judgement is deterministic Python in `core/`, which has no network access,
no clock, and **59 tests**. The same product always produces the same verdict.

When a barcode resolves, no image is uploaded at all. Only the number.

## What it does

### Reads a label
Camera or file. Barcode first because it is exact; the vision model only handles
products no database knows.

### Analyses a shopping list
Upload a CSV of barcodes and get the whole list scored, ranked, filtered and
charted, then export the analysis. Ships with `data/pantry.csv`, thirty real
products across ten categories.

### The rules engine

| Component | Why it exists |
|---|---|
| **Serving normalizer** | Restates everything per container and per 100 g. Two products are only comparable on one basis |
| **Sugar recombiner** | ~65 aliases summed into one figure, then drawn as teaspoons |
| **Additive classifier** | E-numbers by range plus named additives, reported as a shape rather than a list |
| **Hidden ingredients** | Casein, carmine, isinglass, shellac, L-cysteine, malt. What "contains milk" never tells you |
| **16 allergens** | The US big nine, the extra EU declarables, pork, and lactose intolerance treated separately from milk allergy |
| **Macro sanity check** | Verifies kcal ≈ 4·carb + 4·protein + 9·fat, so an OCR misread fails arithmetic instead of being reported as fact |
| **Goal rubric** | Weighted score against published UK FSA bands, always showing its components |
| **Plain summary** | Two or three sentences saying what it all adds up to |

## Five rules the app will not break

**Never claim safety.** It reports "nothing matching was found", which is a
statement about a text string, not about a food. Only the packaging can tell
someone their food is safe.

**Uncertainty is never rounded into a yes.** "Natural flavors" and
"mono- and diglycerides" can be plant or animal derived and the label will never
say which. They stay amber permanently.

**"May contain" is not an ingredient.** Precautionary wording is split off
before any matching and only ever surfaces as a cross-contamination caution.
Telling an allergic person that a warning is a certainty is how they learn to
stop reading warnings.

**Missing data is not good data.** A product whose label could not be read gets
no score at all, rather than a flattering one.

**A false alarm has a cost too.** Peanut butter is not dairy and coconut milk is
not dairy. Negation lists keep the flags worth reading.

## What works where

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

## Rebuilding this from scratch

`BUILD_PROMPT.md` is a specification you can paste into an AI coding assistant to
recreate the app. The useful part is section 7, which encodes ten real defects as
requirements: precautionary "may contain" wording being read as an ingredient,
peanut butter matching as dairy, beverages flattering themselves on food scoring
bands, and a coverage statistic that was really a rate limit.

## Configuration

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Photo reading. **Barcode and CSV paths work without it** |
| `GROQ_VISION_MODEL` | Default `qwen/qwen3.6-27b`, must be vision-capable |

## Layout

```
core/       the rules engine, pure functions, no I/O, 59 tests
services/   Open Food Facts client and Groq vision client
api/        FastAPI: /api/analyze, /api/batch, /api/showcase, /api/health
web/        single page, no build step
data/       pantry.csv and showcase.json
tests/      the rules engine under test
```

`core/` never imports from `services/` or `api/`. That is what makes the
judgement layer testable without mocking a network.

## Deploying

Configured for Vercel. Import the repo and set `GROQ_API_KEY` in the project's
environment variables, never in the repo.

`requirements.txt` is committed because Vercel does not read `uv.lock`.
Regenerate it when dependencies change:

```bash
uv export --format requirements-txt --no-hashes --no-emit-project --no-dev -o requirements.txt
```

Barcode decoding runs in the browser via `BarcodeDetector`, which keeps OpenCV
out of the deployment entirely.

## Design notes

The page is drawn rather than photographed: a colour field in food hues, and 27
hand-drawn food illustrations tiled behind the content as SVG. About 12KB, no
CDN, nothing to license. Product photographs on the landing page come from Open
Food Facts (CC-BY-SA) and are pictures of the exact products being scored, so
the imagery is the data rather than decoration.

Contrast was measured rather than eyeballed. Every text pair clears WCAG AA,
including over the strongest part of the background.

## Limitations

- Open Food Facts is community-maintained. Coverage is best in Europe, thinner
  for small US brands, and entries are occasionally wrong. One product's sodium
  was stored as `3.38e-07 g`. The source of every number is shown.
- The photo path is only as good as the photo. The macro check catches
  arithmetic-breaking misreads, not plausible ones.
- `BarcodeDetector` is unavailable in Safari, which falls back to the vision path.
- English labels only.
- Informational analysis of a label. **Not medical or dietary advice**, and never
  a safety claim about allergens.

Data from Open Food Facts, licensed ODbL. Product images CC-BY-SA.
