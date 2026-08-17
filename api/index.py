"""HTTP surface. One endpoint does the work; everything else is static.

Kept deliberately thin — all judgement lives in ``core``, which has no idea the
web exists. The API's only jobs are choosing a data source, calling the engine,
and shaping the result for the browser.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.analyze import Analysis, analyze
from core.allergens import LABELS as ALLERGEN_LABELS
from core.diet import DIET_LABELS
from core.score import GOALS
from core.summary import summarize
from services import off
from services.vision import VisionUnavailable, read_label

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

app = FastAPI(title="NutriSnap", docs_url="/api/docs")


class BatchRequest(BaseModel):
    barcodes: list[str] = Field(default_factory=list, max_length=60)
    goal: str = "balanced"
    diets: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    barcode: str | None = None
    image: str | None = Field(default=None, description="data:image/... URL")
    goal: str = "balanced"
    diets: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)


def _serialize(a: Analysis) -> dict:
    """Flatten the analysis into what the page actually renders."""
    p = a.product
    return {
        "product": {
            "name": p.name,
            "brand": p.brand,
            "barcode": p.barcode,
            "source": p.source,
            "serving_size": p.serving_size,
            "servings_per_container": p.servings_per_container,
            "is_beverage": p.is_beverage,
            "image_url": p.image_url,
            "ingredients_text": p.ingredients_text,
        },
        "nutrition": {
            "per_serving": asdict(a.per_serving),
            "per_container": asdict(a.per_container) if a.per_container else None,
            "per_100g": asdict(a.per_100g) if a.per_100g else None,
        },
        "headline": {
            "sugar_g": a.headline_sugar_g,
            "teaspoons": a.headline_teaspoons,
            "basis": "package" if a.per_container else "serving",
            "basis_label": a.basis_label,
        },
        "sugars": {
            "aliases": a.sugars.aliases,
            "alcohols": a.sugars.alcohols,
            "sweeteners": a.sugars.sweeteners,
            "is_split": a.sugars.is_split,
            "first_position": a.sugars.first_position,
        },
        "additives": [{"name": n, "category": c} for n, c in a.additives],
        "additive_summary": a.additive_summary,
        "flags": [asdict(f) for f in a.flags],
        "verdict": a.verdict,
        "score": {
            "total": a.score.total,
            "basis": a.score.basis,
            "coverage": round(a.score.coverage, 2),
            "reason": a.score.reason,
            "goal_label": GOALS.get(a.score.goal, {}).get("label", a.score.goal),
            "components": [
                {"label": c.label, "value": c.value, "unit": c.unit,
                 "subscore": None if c.subscore is None else round(c.subscore, 1),
                 "weight": c.weight}
                for c in a.score.components
            ],
        },
        "summary": summarize(a),
        "notes": a.notes,
        "counterpoint": a.counterpoint,
        "macro_ok": a.macro_ok,
    }


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "vision_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "goals": {k: v["label"] for k, v in GOALS.items()},
        "diets": DIET_LABELS,
        "allergens": ALLERGEN_LABELS,
    }


@app.post("/api/analyze")
async def analyze_endpoint(req: AnalyzeRequest):
    """Barcode first — it's exact. Photo only when there's no barcode."""
    product = None

    if req.barcode:
        product = await off.lookup(req.barcode)

    if product is None and req.image:
        try:
            product = read_label(req.image)
        except VisionUnavailable as exc:
            return JSONResponse({"error": str(exc), "kind": "not_configured"}, status_code=503)
        except Exception as exc:
            return JSONResponse(
                {"error": f"That photo couldn't be read: {exc}", "kind": "unreadable"},
                status_code=422,
            )

    if product is None:
        return JSONResponse(
            {"error": "That barcode isn't in Open Food Facts. Photograph the "
                      "nutrition panel instead and it will be read directly.",
             "kind": "not_found"},
            status_code=404,
        )

    return _serialize(analyze(product, goal=req.goal, diets=req.diets,
                              allergens=req.allergens))


@app.post("/api/batch")
async def batch_endpoint(req: BatchRequest):
    """Analyse a shopping list in one pass.

    Barcode-only by design: a list of sixty products is not sixty photographs,
    and Open Food Facts costs no tokens, so a whole pantry can be scored without
    touching the model at all.
    """
    seen: set[str] = set()
    results, missing, unreachable = [], [], []

    # One connection for the whole list, paced so the public API doesn't
    # throttle us into reporting real products as missing.
    async with httpx.AsyncClient(
        timeout=off.TIMEOUT, headers={"User-Agent": off.UA},
        limits=httpx.Limits(max_connections=4),
    ) as client:
        for code in req.barcodes:
            code = (code or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            try:
                product = await off.lookup(code, client=client)
            except off.LookupFailed:
                unreachable.append(code)
                continue
            if product is None:
                missing.append(code)
                continue
            results.append(_serialize(
                analyze(product, goal=req.goal, diets=req.diets, allergens=req.allergens)
            ))

    scored = [r for r in results if r["score"]["total"] is not None]
    summary = {
        "requested": len(seen),
        "found": len(results),
        "missing": missing,
        "unreachable": unreachable,
        # Coverage is measured against products we actually got an answer about.
        "coverage": (round(len(results) / (len(results) + len(missing)), 3)
                     if (results or missing) else 0),
        "median_score": (
            sorted(r["score"]["total"] for r in scored)[len(scored) // 2]
            if scored else None
        ),
        "total_sugar_g": round(
            sum(r["headline"]["sugar_g"] or 0 for r in results), 1),
        "flagged": sum(
            1 for r in results
            if any(f["level"] == "avoid" for f in r["flags"])),
    }
    return {"summary": summary, "products": results}


@app.get("/api/sample-list")
async def sample_list() -> dict:
    """The shipped pantry CSV, so the demo works with no file to hand."""
    path = ROOT / "data" / "pantry.csv"
    if not path.exists():
        return {"csv": "", "rows": 0}
    text = path.read_text()
    return {"csv": text, "rows": max(0, len(text.strip().splitlines()) - 1)}


# Static files last, so /api/* always wins.
if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB / "index.html")
