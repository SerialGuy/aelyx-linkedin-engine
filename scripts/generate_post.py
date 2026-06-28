"""
generate_post.py

Calls the active LLM provider (Anthropic, OpenAI, or Gemini — set via the
LLM_PROVIDER env var) to generate one or more LinkedIn posts (copy + image
spec) for Aelyx, using forced rotation through content angles, hook styles,
and visual styles so output doesn't converge into a template — then renders
each image as SVG (via structured templates) and writes everything into the docs queue.

Run manually:  python scripts/generate_post.py            # generates POSTS_PER_DAY posts
               python scripts/generate_post.py --count 3   # override count for this run
Run by CI:     triggered daily via .github/workflows/daily-post.yml
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from post_history import load_history, choose_next_post_params, record_post
from llm_provider import call_llm, active_provider_label
from svg_renderer import render_visual

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

VISUAL_STYLE_DESCRIPTIONS = {
    "minimal_typographic": "Big, confident typography as the entire visual. One accent color. Generous negative space. No icons, no chart junk.",
    "diagram_flow": "A clean, custom process or architecture diagram specific to the content — not a generic flowchart template.",
    "before_after_split": "A split composition contrasting two states (before/after, old way/new way).",
    "annotated_screenshot_style": "A stylized mockup with one or two callout annotations highlighting a specific detail.",
    "portrait_style_illustration": "A custom illustrative scene relevant to the content — not stock-photo-like, not generic AI/robot imagery.",
    "data_moment": "One real number rendered as the hero of the image, large and confident — not a chart, not a graph axis in sight.",
}

VISUAL_SPEC_SCHEMAS = {
    "minimal_typographic": """{
  "background": "#141B17",
  "accent": "#hex accent color",
  "headline": "short punchy headline (max 72 chars)",
  "subheadline": "one supporting line (max 96 chars, optional)"
}""",
    "diagram_flow": """{
  "background": "#141B17",
  "accent": "#hex accent color",
  "title": "diagram title (max 48 chars)",
  "steps": [
    {"label": "step name", "detail": "one short line about this step"},
    {"label": "step name", "detail": "one short line"},
    {"label": "step name", "detail": "one short line"}
  ]
}""",
    "before_after_split": """{
  "background": "#141B17",
  "accent": "#hex accent color",
  "before_label": "Before",
  "before_text": "old painful state in one sentence",
  "after_label": "After",
  "after_text": "new improved state in one sentence"
}""",
    "annotated_screenshot_style": """{
  "background": "#141B17",
  "accent": "#hex accent color",
  "screen_title": "UI or product screen title",
  "callouts": [
    {"label": "01", "text": "first callout explaining a detail"},
    {"label": "02", "text": "second callout"}
  ]
}""",
    "data_moment": """{
  "background": "#141B17",
  "accent": "#hex accent color",
  "hero_number": "the key figure e.g. 8,400",
  "hero_label": "what the number represents",
  "context": "one line of context"
}""",
    "portrait_style_illustration": """{
  "background": "#141B17",
  "accent": "#hex accent color",
  "headline": "editorial headline",
  "scene_line": "one evocative scene-setting line"
}""",
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
  "image_concept": "a one-sentence description of what the accompanying image should show, specific and concrete"
}"""

    avoid_clients = ", ".join(c for c in params["recent_clients"] if c) or "none yet"
    avoid_hooks = "\n".join(f"- {h}" for h in params["recent_hooks_text"] if h) or "none yet"

    user_prompt = f"""SOURCE MATERIAL:
{source_material}

ASSIGNMENT FOR TODAY'S POST:
- Content angle: {params['angle']} — {ANGLE_DESCRIPTIONS[params['angle']]}
- Hook style: {params['hook_style']} — {HOOK_STYLE_DESCRIPTIONS[params['hook_style']]}

CONSTRAINTS:
- Do not reference these recently-used clients unless genuinely the best fit: {avoid_clients}
- Do not reuse the phrasing or structure of these recent hook lines:
{avoid_hooks}
- Global professional English. No emojis. No hashtag spam (max 3 relevant hashtags at the very end if natural).
- Ground every claim in the source material. Never invent a number or outcome.

Generate today's post now."""

    raw = call_llm(system_prompt, user_prompt)
    return extract_json(raw)


def generate_image_svg(image_concept: str, visual_style: str, hook_line: str) -> str:
    """Ask the LLM for structured visual content, then render with fixed templates."""
    system_prompt = """You are a senior brand art director for Aelyx, a B2B AI company.
Your job is to define the CONTENT of a LinkedIn graphic — headlines, labels, steps, colors.
You do NOT write SVG, HTML, or layout code. A separate renderer handles design.

Rules:
- Return ONLY valid JSON matching the schema given. No markdown fences, no commentary.
- Keep every text field short — it must fit cleanly in a fixed layout.
- Pick a cohesive dark-theme palette: deep background (#141B17 or similar), warm accent
  (brass, teal, coral — not default Bootstrap blue), cream/light text.
- Ground all copy in the image concept. No generic AI imagery language.
- Never invent statistics not implied by the concept."""

    user_prompt = f"""Visual style: {visual_style} — {VISUAL_STYLE_DESCRIPTIONS[visual_style]}

Image concept: {image_concept}

Hook line from the post (use as inspiration, do not paste verbatim unless it fits): "{hook_line}"

JSON schema to fill:
{VISUAL_SPEC_SCHEMAS[visual_style]}

Return the completed JSON now."""

    raw = call_llm(system_prompt, user_prompt, max_tokens=1200)
    spec = extract_json(raw)
    return render_visual(visual_style, spec, hook_line)


def generate_one_post(history: dict, source_material: str) -> dict:
    """Generates a single post, recording it into history as it goes so the
    NEXT post generated in the same run also avoids repeating angle/hook/visual
    — rotation is enforced across the whole day's batch, not just within itself."""
    params = choose_next_post_params(history)
    print(f"  -> angle: {params['angle']}, hook: {params['hook_style']}, visual: {params['visual_style']}")

    content = generate_post_content(params, source_material)
    svg = generate_image_svg(content["image_concept"], params["visual_style"], content["hook_line"])

    post_record = {
        "angle": params["angle"],
        "hook_style": params["hook_style"],
        "visual_style": params["visual_style"],
        "client": content.get("client_referenced"),
        "hook_text": content["hook_line"],
        "body": content["body"],
        "cta": content["cta"],
        "image_concept": content["image_concept"],
        "status": "pending_approval",
    }

    post_id = f"post_{len(history['posts']) + 1:04d}"
    post_record["id"] = post_id
    post_record["svg"] = svg

    # Record in history WITHOUT the svg blob (keep history file lean), but do
    # this BEFORE generating the next post in the batch so rotation accounts
    # for everything generated so far today.
    history_record = {k: v for k, v in post_record.items() if k != "svg"}
    record_post(history, history_record)

    return post_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=None,
                         help="Number of posts to generate this run (overrides POSTS_PER_DAY)")
    args = parser.parse_args()
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
