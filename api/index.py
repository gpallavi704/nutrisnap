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
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.analyze import Analysis, analyze
from core.diet import DIET_LABELS
from core.score import GOALS
from services import off
from services.vision import VisionUnavailable, read_label

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

app = FastAPI(title="NutriSnap", docs_url="/api/docs")


class AnalyzeRequest(BaseModel):
    barcode: str | None = None
    image: str | None = Field(default=None, description="data:image/... URL")
    goal: str = "balanced"
    diets: list[str] = Field(default_factory=list)


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
        "notes": a.notes,
        "macro_ok": a.macro_ok,
    }


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "vision_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "goals": {k: v["label"] for k, v in GOALS.items()},
        "diets": DIET_LABELS,
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

    return _serialize(analyze(product, goal=req.goal, diets=req.diets))


# Static files last, so /api/* always wins.
if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB / "index.html")
