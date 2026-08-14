# NutriSnap

Not "does this fit my diet" — **what am I actually eating?**

Scan a grocery label and get the arithmetic it's arranged to obscure: sugars
recombined across every alias, quantities restated per package rather than per
invented serving, additives counted. Scan a second product and they rank against
each other.

```bash
uv sync
cp .env.example .env          # add a Groq key for the photo path
uv run uvicorn api.index:app --reload --port 8000
```

Open http://localhost:8000 and click **Load sample**.

---

## The problem

Everything you need is technically printed on the box. It's arranged so that no
single number tells the truth:

| The bottle says | What you drink |
|---|---|
| Serving size 8 fl oz | The bottle is 2.5 servings |
| Sugars 26 g | **65 g — about 16 teaspoons** |
| Listed as | cane juice, dextrose, maltodextrin |

Three sweeteners rather than one, so none of them reaches the top of the
ingredient list. Nothing here is illegal. It's just arranged.

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

The model is never asked for an opinion — only to transcribe what's printed.
Every judgement is deterministic Python in `core/`, which has no network access,
no clock, and 33 tests. Same product in, same verdict out, every time.

When a barcode resolves, no image is uploaded at all — only the number.

## What the engine does

| Component | Why it exists |
|---|---|
| **Serving normalizer** | Restates everything per container and per 100 g. Two products are only comparable on one basis |
| **Sugar recombiner** | ~65 aliases — dextrose, maltodextrin, evaporated cane juice — summed into one figure |
| **Additive classifier** | E-numbers by range plus named additives → "9 additives, 3 colourings" |
| **Hidden-ingredient rules** | Casein, carmine, isinglass, shellac, L-cysteine, malt. What "milk" doesn't catch |
| **Macro sanity check** | Verifies kcal ≈ 4·carb + 4·protein + 9·fat, so an OCR misread fails arithmetic instead of being reported as fact |
| **Goal rubric** | Weighted score that always shows its components |

### Three honesty rules

**Uncertainty is never rounded into a yes.** "Natural flavors" and
"mono- and diglycerides" can be plant or animal derived and the label will never
say which. They stay amber permanently rather than being guessed.

**Missing data is not good data.** A product whose label couldn't be read
returns no score at all. An earlier version gave Nutella 100/100 because it had
no nutrition data and therefore no detectable additives.

**Drinks are scored on their own scale.** Per 100 ml, a full-sugar cola looks
mild against food thresholds — it scored 77/100 for "cut sugar" until beverage
bands were added. Both scales come from the published UK FSA front-of-pack
bands.

## Layout

```
core/       the rules engine — pure functions, no I/O, fully tested
services/   Open Food Facts client and Groq vision client
api/        FastAPI, one endpoint
web/        single page, no build step
tests/      33 tests over core/
```

`core/` never imports from `services/` or `api/`. That's what makes the
judgement layer testable without mocking a network.

## Configuration

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Photo reading. **Barcode lookup works without it** |
| `GROQ_VISION_MODEL` | Default `qwen/qwen3.6-27b` — must be vision-capable |

## Deploying

Configured for Vercel. Push the repo, import it, and set `GROQ_API_KEY` in the
project's environment variables — never in the repo.

`requirements.txt` is committed because Vercel doesn't read `uv.lock`.
Regenerate it when dependencies change:

```bash
uv export --format requirements-txt --no-hashes --no-emit-project --no-dev -o requirements.txt
```

Barcode decoding runs in the browser via `BarcodeDetector`, which keeps OpenCV
out of the deployment entirely.

## Prior art

Inspired by [Nutritionell](https://www.ischool.berkeley.edu/), a Berkeley MIDS
capstone that turns one photo of a grocery shelf into a scored guide using YOLO
detection and a VLM.

That project solved **breadth** — 100 products in a frame. This one deliberately
takes the other axis: **depth**, one product, arithmetically correct and fully
auditable.

The two can't be combined, and not by choice: a shelf photo shows the front of
the pack, and the nutrition panel faces away from the camera.

## Limitations

- Open Food Facts is community-maintained. Coverage is best in Europe, thinner
  for small US brands, and entries are occasionally wrong. The source of every
  number is shown.
- The photo path is only as good as the photo. The macro check catches
  arithmetic-breaking misreads, not plausible ones.
- English labels only.
- Informational analysis of a label. **Not medical or dietary advice**, and never
  a safety claim about allergens.

Data from Open Food Facts, licensed ODbL.
