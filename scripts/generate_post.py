"""
generate_post.py

Calls the active LLM provider (Anthropic, OpenAI, or Gemini — set via the
LLM_PROVIDER env var) to generate one or more LinkedIn posts (copy + image
spec) for Aelyx, using forced rotation through content angles, hook styles,
and visual styles so output doesn't converge into a template — then renders
each image as SVG and writes everything into the docs queue.

Run manually:  python scripts/generate_post.py            # generates POSTS_PER_DAY posts
               python scripts/generate_post.py --count 3   # override count for this run
Run by CI:     triggered daily via .github/workflows/daily-post.yml
"""

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

from post_history import load_history, choose_next_post_params, record_post
from llm_provider import call_llm, active_provider_label
from brand_layouts import LAYOUTS, THEMES, PHOTO_LAYOUTS, CAROUSEL_ONLY, LayoutOverflow, render_post, render_carousel
from image_provider import generate_image_data_uri, build_prompt

ROOT = Path(__file__).parent.parent
SOURCE_MATERIAL_PATH = ROOT / "data" / "source_material.md"
QUEUE_PATH = ROOT / "docs" / "data" / "queue.json"

# Default number of posts generated per run. Override per-run with --count,
# or change this default to permanently shift how many posts land per day.
DEFAULT_POSTS_PER_DAY = int(os.environ.get("POSTS_PER_DAY", "1"))

ANGLE_DESCRIPTIONS = {
    "case_study": "A specific client problem, the specific Aelyx solution, and a specific outcome. Name the client if appropriate.",
    "product_education": "Explain what one specific Aelyx product does, framed entirely around the buyer's pain point, not a feature list.",
    "thought_leadership": "A sharp opinion about AI in business, grounded in something Aelyx has actually built or seen — never generic 'AI is changing everything' commentary.",
    "behind_the_build": "A real technical challenge Aelyx solved, written for a technically literate reader. Show the actual difficulty, not just the win.",
    "founder_perspective": "A first-person founder reflection on building an AI company serving both Indian SMBs and the US market.",
}

HOOK_STYLE_DESCRIPTIONS = {
    "contrarian_claim": "Open by pushing back on a common assumption in the space.",
    "specific_number": "Open with one concrete, real figure from the source material.",
    "before_after": "Open by contrasting the old painful state with the new state.",
    "question": "Open with a sharp, specific question — not generic or rhetorical.",
    "scene_setting": "Open by dropping the reader into one real moment (a call, a deployment, a meeting).",
    "blunt_statement": "Open with one short, declarative sentence. No warm-up.",
}



def load_source_material() -> str:
    """
    Source material can come from either:
    - a repo secret (SOURCE_MATERIAL env var) — used when this repo is PUBLIC,
      so client names and case study details aren't visible to anyone browsing
      the repo, since secrets are encrypted and never exposed in logs or files
    - the local data/source_material.md file — used when this repo is PRIVATE,
      or for local testing
    Env var takes priority if both are present.
    """
    env_value = os.environ.get("SOURCE_MATERIAL")
    if env_value:
        return env_value
    if SOURCE_MATERIAL_PATH.exists():
        return SOURCE_MATERIAL_PATH.read_text()
    raise RuntimeError(
        "No source material found. Either set the SOURCE_MATERIAL repo secret "
        "(recommended for public repos) or add data/source_material.md (private repos only)."
    )


def extract_json(text: str) -> dict:
    # Model may wrap JSON in markdown fences despite instructions; strip defensively.
    cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


FORMAT_RULES = {
    "auto": "you decide: single image or carousel, per the carousel rules.",
    "single": "single image only. Use \"visual\".",
    "carousel": "carousel only. Use \"slides\".",
}
LAYOUT_MENU = chr(10).join(f"  - {k}: {v[1]}" for k, v in LAYOUTS.items())


def generate_post_content(params: dict, source_material: str) -> dict:
    system_prompt = """You are the senior LinkedIn copywriter for Aelyx AI and Intelligence, \
an AI/automation company. You write specific, grounded, confident B2B posts — never generic \
AI hype, never invented statistics. You only use facts present in the source material you're given.

Respond with ONLY a JSON object, no preamble, no markdown fences. Schema:
{
  "hook_line": "the first line of the post — this is what determines if anyone stops scrolling",
  "body": "the full post body, 80-150 words, LinkedIn formatting (short paragraphs, line breaks, no markdown headers)",
  "cta": "one short closing line — a soft call to action, not salesy",
  "client_referenced": "client name if one is referenced, else null",
  "visual": { ...the fields of the assigned visual layout... },   <- for a SINGLE-image post
  "slides": [ {"layout": "<name>", ...that layout's fields}, ... ]   <- for a CAROUSEL post (use INSTEAD of "visual")
}

Carousel rules: choose a carousel when the story has 4+ distinct points, steps, or an arc (problem, approach, result); otherwise a single image. A carousel has 4-8 slides: slide 1 is a scroll-stopping cover built from the hook (layouts: statement, bignumber, poster, quote, marquee or photo_hero), middle slides each carry ONE idea (layouts: steps, isostack, flow, chat, statcards, note, beforeafter, bignumber, quote, statement), and the last slide uses layout "cta". Never use photo layouts after slide 1. Vary layouts between slides; no layout twice in a row."""

    avoid_clients = ", ".join(c for c in params["recent_clients"] if c) or "none yet"
    avoid_hooks = "\n".join(f"- {h}" for h in params["recent_hooks_text"] if h) or "none yet"

    user_prompt = f"""SOURCE MATERIAL:
{source_material}

ASSIGNMENT FOR TODAY'S POST:
- Content angle: {params['angle']} — {ANGLE_DESCRIPTIONS[params['angle']]}
- Hook style: {params['hook_style']} — {HOOK_STYLE_DESCRIPTIONS[params['hook_style']]}
- Visual layout (if single image): {params['visual_style']} — the post image is rendered from the "visual" object. Fill exactly these fields: {LAYOUTS[params['visual_style']][1]}
- FORMAT: {FORMAT_RULES[params['format']]}
- LAYOUT MENU for carousel slides (name: fields):
{LAYOUT_MENU}
  Visual text must be punchy, built from real facts in the source material (never invent numbers), and must not just repeat the hook line word for word.

CONSTRAINTS:
- Do not reference these recently-used clients unless genuinely the best fit: {avoid_clients}
- Do not reuse the phrasing or structure of these recent hook lines:
{avoid_hooks}
- Global professional English. No emojis. No hashtag spam (max 3 relevant hashtags at the very end if natural).
- Ground every claim in the source material. Never invent a number or outcome.

Generate today's post now."""

    raw = call_llm(system_prompt, user_prompt)
    return extract_json(raw)


def pick_theme(history: dict, layout: str) -> str:
    """Random allowed canvas for the layout, never the same as the previous post's."""
    last = history["posts"][-1].get("theme") if history["posts"] else None
    options = [t for t in LAYOUTS[layout][2] if t != last] or LAYOUTS[layout][2]
    return random.choice(options)


FORMAT = "auto"  # set from --format


def _render_safe(layout, fields, theme, seed, hook, history=None, footer=""):
    """Render one image. Photo layouts get a generated image; anything that fails or overflows
    falls back to the plain statement layout so a broken graphic is never shipped."""
    fields = dict(fields)
    try:
        if layout in PHOTO_LAYOUTS:
            fields["_image"] = generate_image_data_uri(
                build_prompt(fields.get("image_prompt", "a yellow typewriter"), layout, THEMES[theme]["bg"]))
        return render_post(layout, fields, theme, seed, footer=footer), layout, theme, fields
    except Exception as e:  # image failure, LayoutOverflow, malformed fields
        print(f"  layout '{layout}' unusable ({e}); falling back to 'statement'", file=sys.stderr)
        fields = {"headline": fields.get("headline") or fields.get("title") or fields.get("quote") or hook}
        theme = pick_theme(history, "statement") if history else "paper"
        return render_post("statement", fields, theme, seed, footer=footer), "statement", theme, fields


def generate_one_post(history: dict, source_material: str) -> dict:
    """Generates a single post, recording it into history as it goes so the
    NEXT post generated in the same run also avoids repeating angle/hook/visual
    — rotation is enforced across the whole day's batch, not just within itself."""
    params = choose_next_post_params(history)
    print(f"  -> angle: {params['angle']}, hook: {params['hook_style']}, visual: {params['visual_style']}")

    params["format"] = FORMAT
    content = generate_post_content(params, source_material)
    post_id = f"post_{len(history['posts']) + 1:04d}"
    hook = content["hook_line"]

    raw_slides = content.get("slides")
    if FORMAT != "single" and isinstance(raw_slides, list) and len(raw_slides) >= 3:
        raw_slides = raw_slides[:8]
        n, slides, themes = len(raw_slides), [], []
        for i, sl in enumerate(raw_slides):
            name = sl.get("layout") if sl.get("layout") in LAYOUTS else "statement"
            if name in PHOTO_LAYOUTS and i > 0:
                name = "statement"  # photos only on the cover: cost and consistency
            fields = {k: v for k, v in sl.items() if k != "layout"}
            prev = themes[-1] if themes else None
            options = [t for t in LAYOUTS[name][2] if t != prev] or LAYOUTS[name][2]
            svg, name, theme, fields = _render_safe(name, fields, random.choice(options), f"{post_id}-{i}", hook,
                                                    footer=f"{i + 1:02d} / {n:02d}")
            slides.append(svg)
            themes.append(theme)
            if i == 0:
                params["visual_style"] = name  # cover layout drives rotation
        carousel_svgs = slides
        layout, theme, visual = "carousel", themes[0], {"slides": raw_slides}
    else:
        carousel_svgs = None
        layout = params["visual_style"]
        theme = pick_theme(history, layout)
        visual = dict(content.get("visual") or {})
        svg, layout, theme, visual = _render_safe(layout, visual, theme, post_id, hook, history)

    post_record = {
        "angle": params["angle"],
        "hook_style": params["hook_style"],
        "visual_style": params["visual_style"],  # what rotation assigned, even if we fell back
        "rendered_layout": layout,
        "format": "carousel" if carousel_svgs else "single",
        "client": content.get("client_referenced"),
        "hook_text": content["hook_line"],
        "body": content["body"],
        "cta": content["cta"],
        "theme": theme,
        "visual": {k: v for k, v in visual.items() if k != "_image"},
        "status": "pending_approval",
    }

    post_record["id"] = post_id
    post_record["svg"] = carousel_svgs[0] if carousel_svgs else svg
    if carousel_svgs:
        post_record["slides"] = carousel_svgs

    # Record in history WITHOUT the svg blob (keep history file lean), but do
    # this BEFORE generating the next post in the batch so rotation accounts
    # for everything generated so far today.
    history_record = {k: v for k, v in post_record.items() if k not in ("svg", "slides")}
    record_post(history, history_record)

    return post_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=None,
                         help="Number of posts to generate this run (overrides POSTS_PER_DAY)")
    parser.add_argument("--format", choices=["auto", "single", "carousel"], default=os.environ.get("POST_FORMAT", "auto"),
                         help="auto lets the model choose per post; or force single image / carousel")
    args = parser.parse_args()
    global FORMAT
    FORMAT = args.format
    count = args.count if args.count is not None else DEFAULT_POSTS_PER_DAY

    required_key = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower().strip()
    key_name = required_key.get(provider)
    if key_name and not os.environ.get(key_name):
        print(f"ERROR: LLM_PROVIDER is '{provider}' but {key_name} is not set", file=sys.stderr)
        sys.exit(1)

    print(f"Using provider: {active_provider_label()}")
    print(f"Generating {count} post(s) for today's queue...")

    source_material = load_source_material()
    history = load_history()

    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    queue = json.loads(QUEUE_PATH.read_text()) if QUEUE_PATH.exists() else []

    generated_ids = []
    for i in range(count):
        print(f"Post {i + 1}/{count}:")
        try:
            post_record = generate_one_post(history, source_material)
        except Exception as e:
            # One failed post in a batch shouldn't take down the rest of the run.
            print(f"  FAILED: {e}", file=sys.stderr)
            continue
        queue.append(post_record)
        generated_ids.append(post_record["id"])

    QUEUE_PATH.write_text(json.dumps(queue, indent=2))

    if generated_ids:
        print(f"Generated {len(generated_ids)} post(s): {', '.join(generated_ids)} — pending approval on dashboard.")
    else:
        print("No posts were generated successfully.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
