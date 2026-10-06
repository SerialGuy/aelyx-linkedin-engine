"""
image_provider.py

Generates the photographic / 3D asset for the photo layouts. Gemini first (native 4:5),
OpenAI gpt-image as fallback (or set IMAGE_PROVIDER=openai|gemini to force one).
Returns a JPEG data URI sized for the 1080x1350 canvas.
"""

import base64
import io
import os

import requests
from PIL import Image

GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")

STYLE = ("Premium editorial campaign imagery, tactile and slightly surreal, studio lighting, sharp focus. "
         "Colour world: bumblebee yellow #FFC800, near-black #0B0B0B, warm cream #F5F1E6. "
         "Absolutely no text, letters, numbers, logos or watermarks anywhere in the image.")


def _gemini(prompt):
    key = os.environ["GEMINI_API_KEY"]
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent",
        headers={"x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:5"}}},
        timeout=180)
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        data = part.get("inlineData") or part.get("inline_data")
        if data:
            return base64.b64decode(data["data"])
    raise RuntimeError("Gemini returned no image")


def _openai(prompt):
    key = os.environ["OPENAI_API_KEY"]
    r = requests.post("https://api.openai.com/v1/images/generations",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": OPENAI_IMAGE_MODEL, "prompt": prompt, "size": "1024x1536", "n": 1},
                      timeout=240)
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


def generate_image_data_uri(prompt: str) -> str:
    forced = os.environ.get("IMAGE_PROVIDER", "").lower()
    order = [forced] if forced else [p for p, k in (("gemini", "GEMINI_API_KEY"), ("openai", "OPENAI_API_KEY")) if os.environ.get(k)]
    err = RuntimeError("no image API key set (GEMINI_API_KEY or OPENAI_API_KEY)")
    for name in order:
        try:
            raw = {"gemini": _gemini, "openai": _openai}[name](prompt)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            w, h = img.size
            tw = int(h * 4 / 5)  # centre-crop to 4:5
            if w > tw:
                img = img.crop(((w - tw) // 2, 0, (w - tw) // 2 + tw, h))
            img = img.resize((1080, 1350))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=84)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception as e:  # try the next provider
            err = e
    raise RuntimeError(f"No image provider succeeded: {err}")


def build_prompt(object_prompt: str, layout: str, bg_hex: str) -> str:
    if layout == "photo_hero":
        return (f"{object_prompt}. The subject sits in the lower 60% of a vertical 4:5 frame, on a seamless flat "
                f"{bg_hex} studio background; the top 35% of the frame is completely empty flat {bg_hex}. {STYLE}")
    return f"{object_prompt}. Candid editorial photograph, vertical, natural depth of field. {STYLE}"
