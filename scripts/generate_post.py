"""
generate_post.py

Calls the active LLM provider (Anthropic, OpenAI, or Gemini — set via the
LLM_PROVIDER env var) to generate one or more LinkedIn posts (copy + image
spec) for Aelyx, using forced rotation through content angles, hook styles,
and visual styles so output doesn't converge into a template — then renders
each image as SVG and writes everything into the dashboard queue.

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

ROOT = Path(__file__).parent.parent
SOURCE_MATERIAL_PATH = ROOT / "data" / "source_material.md"
QUEUE_PATH = ROOT / "dashboard" / "data" / "queue.json"

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
    system_prompt = """You are a senior brand designer creating LinkedIn post graphics for a \
sophisticated B2B AI company. You produce clean, professional, eye-catching SVG graphics — \
never generic stock charts, never cliché "AI brain/circuit" imagery, never default Bootstrap-blue \
color schemes. Each design should feel intentional and specific to its content, the way a real \
design agency would approach a one-off social post — not a templated dashboard widget.

Respond with ONLY raw SVG code, starting with <svg and ending with </svg>. No markdown fences, \
no explanation. Canvas should be viewBox="0 0 1200 1200" (square, LinkedIn-optimized). Use a \
considered color palette appropriate to the content's mood — choose it fresh each time rather \
than defaulting to blue/white. Typography should be confident and large. Keep it print-quality clean."""

    user_prompt = f"""Visual approach for this post: {VISUAL_STYLE_DESCRIPTIONS[visual_style]}

Image concept: {image_concept}

Hook line (may be referenced typographically in the design): "{hook_line}"

Design the SVG now."""

    raw = call_llm(system_prompt, user_prompt, max_tokens=4000)
    svg_match = re.search(r"<svg.*?</svg>", raw, re.DOTALL)
    if not svg_match:
        raise ValueError("Model did not return valid SVG")
    return svg_match.group(0)


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

    source_material = SOURCE_MATERIAL_PATH.read_text()
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
