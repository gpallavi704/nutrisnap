"""Groq vision — the fallback path, for products no database knows.

The model's only job is transcription. It is asked for numbers exactly as
printed and explicitly told to return null rather than estimate, because a
plausible invented figure is far more damaging here than a missing one: the
whole point of the app is that its arithmetic can be trusted.

Everything the model returns is then re-checked by ``core.normalize.macro_check``.
"""

from __future__ import annotations

import json
import os
import re

from groq import Groq

from core.model import Nutrients, Product
from core.normalize import detect_beverage

MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

# Qwen emits a reasoning block before its answer; it must be stripped before
# the JSON can be located.
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

PROMPT = """Transcribe this food label. Return ONLY compact JSON, no prose, no markdown.

{
 "name": string,
 "brand": string|null,
 "serving_size": string|null,
 "serving_grams": number|null,
 "servings_per_container": number|null,
 "calories": number|null,
 "total_fat_g": number|null,
 "saturated_fat_g": number|null,
 "sodium_mg": number|null,
 "total_carb_g": number|null,
 "fiber_g": number|null,
 "total_sugars_g": number|null,
 "added_sugars_g": number|null,
 "protein_g": number|null,
 "ingredients_text": string|null
}

Rules:
- Copy numbers exactly as printed. Do not convert, round or estimate.
- Nutrition values are PER SERVING as shown on the panel.
- serving_grams is the serving in grams or millilitres as a number only.
- sodium must be in milligrams.
- Use null for anything not visible. Never guess a number.
- ingredients_text: copy the ingredient list verbatim, including parentheses.
"""


class VisionUnavailable(RuntimeError):
    """No API key configured, so the UI can explain instead of erroring."""


def _client() -> Groq:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise VisionUnavailable(
            "GROQ_API_KEY is not set, so photo reading is unavailable. "
            "Barcode lookup still works."
        )
    return Groq(api_key=key)


def _extract_json(text: str) -> dict:
    text = _THINK.sub("", text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("the model did not return JSON")
    return json.loads(text[start:end + 1])


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_label(image_data_url: str) -> Product:
    """Read one label photo into a Product. Raises on unusable input."""
    if not image_data_url.startswith("data:image/"):
        raise ValueError("expected a data:image/... URL")

    response = _client().chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=1400,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }],
    )
    data = _extract_json(response.choices[0].message.content)

    return Product(
        name=(data.get("name") or "Scanned product").strip(),
        brand=data.get("brand"),
        source="vision",
        serving_size=data.get("serving_size"),
        serving_grams=_f(data.get("serving_grams")),
        servings_per_container=_f(data.get("servings_per_container")),
        per_serving=Nutrients(
            calories=_f(data.get("calories")),
            total_fat_g=_f(data.get("total_fat_g")),
            saturated_fat_g=_f(data.get("saturated_fat_g")),
            sodium_mg=_f(data.get("sodium_mg")),
            total_carb_g=_f(data.get("total_carb_g")),
            fiber_g=_f(data.get("fiber_g")),
            total_sugars_g=_f(data.get("total_sugars_g")),
            added_sugars_g=_f(data.get("added_sugars_g")),
            protein_g=_f(data.get("protein_g")),
        ),
        ingredients_text=data.get("ingredients_text") or None,
        is_beverage=detect_beverage(data.get("serving_size")),
    )
