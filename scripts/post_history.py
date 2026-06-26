"""
post_history.py

Tracks every post the engine has generated: which content angle, which client,
which hook style, and which visual style were used. The generator reads this
before creating a new post so it can actively steer away from repetition
instead of just hoping the model varies things on its own.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

HISTORY_PATH = Path(__file__).parent.parent / "data" / "post_history.json"

ANGLES = [
    "case_study",
    "product_education",
    "thought_leadership",
    "behind_the_build",
    "founder_perspective",
]

HOOK_STYLES = [
    "contrarian_claim",      # "Most CRMs fail because of X. Here's what we do differently."
    "specific_number",       # leads with a concrete figure from real work
    "before_after",          # contrasts the old painful state vs. the new state
    "question",              # opens with a sharp, non-rhetorical question
    "scene_setting",         # drops the reader into a real moment (a call, a meeting)
    "blunt_statement",       # short, declarative, no preamble
]

VISUAL_STYLES = [
    "minimal_typographic",   # text-led, big type, single accent color, lots of negative space
    "diagram_flow",          # a clean process/architecture diagram, not a generic chart
    "before_after_split",    # split-panel visual contrast
    "annotated_screenshot_style",  # mockup-style annotated UI/data callout
    "portrait_style_illustration", # custom illustrative scene, not stock-photo-like
    "data_moment",           # one real number, presented as the hero of the image — not a chart
]


def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {"posts": []}
    with open(HISTORY_PATH, "r") as f:
        return json.load(f)


def save_history(history: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def recent_posts(history: dict, n: int = 10) -> list:
    return history["posts"][-n:]


def pick_least_recently_used(options: list, recent_values: list) -> str:
    """
    Pick the option that appears least often (and least recently) in recent_values.
    This is the actual anti-repetition mechanism — not random chance, a forced rotation.
    """
    counts = {opt: 0 for opt in options}
    for v in recent_values:
        if v in counts:
            counts[v] += 1
    # Sort by count ascending; ties broken by how long ago they last appeared
    min_count = min(counts.values())
    candidates = [opt for opt, c in counts.items() if c == min_count]
    # Among the least-used, prefer the one furthest back in recent_values (or unused entirely)
    def last_used_index(opt):
        for i in range(len(recent_values) - 1, -1, -1):
            if recent_values[i] == opt:
                return i
        return -1  # never used = lowest priority for recency, picked first
    candidates.sort(key=last_used_index)
    return candidates[0]


def choose_next_post_params(history: dict) -> dict:
    recent = recent_posts(history, n=10)
    recent_angles = [p["angle"] for p in recent]
    recent_hooks = [p["hook_style"] for p in recent]
    recent_visuals = [p["visual_style"] for p in recent]
    recent_clients = [p.get("client") for p in recent if p.get("client")]

    angle = pick_least_recently_used(ANGLES, recent_angles)
    hook_style = pick_least_recently_used(HOOK_STYLES, recent_hooks)
    visual_style = pick_least_recently_used(VISUAL_STYLES, recent_visuals)

    return {
        "angle": angle,
        "hook_style": hook_style,
        "visual_style": visual_style,
        "recent_clients": recent_clients,  # passed to generator so it avoids repeating the same client back-to-back
        "recent_hooks_text": [p.get("hook_text", "") for p in recent],  # actual past hook lines, for explicit dedup
    }


def record_post(history: dict, post: dict) -> dict:
    post["timestamp"] = datetime.now(timezone.utc).isoformat()
    history["posts"].append(post)
    save_history(history)
    return history


if __name__ == "__main__":
    h = load_history()
    params = choose_next_post_params(h)
    print(json.dumps(params, indent=2))
