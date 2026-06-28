"""
svg_renderer.py

Turns structured visual content (JSON from the LLM) into clean, on-brand SVG.
The model picks copy and colors; Python owns layout so graphics stay consistent.
"""

import re
from xml.sax.saxutils import escape

CANVAS = 1200
FONT = "Inter, system-ui, -apple-system, sans-serif"
SERIF = "Georgia, 'Times New Roman', serif"

DEFAULT_PALETTE = {
    "background": "#141B17",
    "surface": "#1C2620",
    "accent": "#C9914F",
    "text_primary": "#F0EDE4",
    "text_secondary": "#C9C5B8",
    "muted": "#2A332E",
}

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex(value: str | None, fallback: str) -> str:
    if value and _HEX_RE.match(value.strip()):
        return value.strip()
    return fallback


def _clip(text: str | None, max_len: int, fallback: str = "") -> str:
    text = (text or fallback).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _wrap(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and length + extra > max_chars:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        lines.append(" ".join(current))
    return lines


def _text_block(
    x: float,
    y: float,
    lines: list[str],
    *,
    size: int,
    fill: str,
    weight: str = "500",
    anchor: str = "start",
    line_gap: float = 1.35,
    family: str = FONT,
) -> str:
  parts = []
  for i, line in enumerate(lines):
    dy = 0 if i == 0 else size * line_gap
    parts.append(
      f'<tspan x="{x}" dy="{dy}" font-weight="{weight}">{escape(line)}</tspan>'
    )
  return (
    f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
    f'fill="{fill}" text-anchor="{anchor}">{"".join(parts)}</text>'
  )


def _svg_open(bg: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" '
        f'width="{CANVAS}" height="{CANVAS}">'
        f'<rect width="{CANVAS}" height="{CANVAS}" fill="{bg}"/>'
    )


def _arrow(x1: int, y1: int, x2: int, y2: int, color: str) -> str:
    mid_x = (x1 + x2) // 2
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2 - 18}" y2="{y2}" stroke="{color}" '
        f'stroke-width="3" stroke-linecap="round"/>'
        f'<polygon points="{x2},{y2} {x2 - 16},{y2 - 8} {x2 - 16},{y2 + 8}" fill="{color}"/>'
        f'<circle cx="{mid_x}" cy="{y1}" r="4" fill="{color}" opacity="0.35"/>'
    )


def normalize_spec(visual_style: str, spec: dict, hook_line: str) -> dict:
    palette = {
        "background": _hex(spec.get("background"), DEFAULT_PALETTE["background"]),
        "surface": _hex(spec.get("surface"), DEFAULT_PALETTE["surface"]),
        "accent": _hex(spec.get("accent"), DEFAULT_PALETTE["accent"]),
        "text_primary": _hex(spec.get("text_primary"), DEFAULT_PALETTE["text_primary"]),
        "text_secondary": _hex(spec.get("text_secondary"), DEFAULT_PALETTE["text_secondary"]),
        "muted": _hex(spec.get("muted"), DEFAULT_PALETTE["muted"]),
    }

    if visual_style == "minimal_typographic":
        return {
            **palette,
            "headline": _clip(spec.get("headline") or hook_line, 72),
            "subheadline": _clip(spec.get("subheadline"), 96),
        }

    if visual_style == "diagram_flow":
        steps = spec.get("steps") or []
        cleaned = []
        for step in steps[:4]:
            if isinstance(step, dict):
                cleaned.append({
                    "label": _clip(step.get("label"), 28, "Step"),
                    "detail": _clip(step.get("detail"), 64, ""),
                })
        while len(cleaned) < 3:
            cleaned.append({"label": f"Step {len(cleaned) + 1}", "detail": ""})
        return {
            **palette,
            "title": _clip(spec.get("title"), 48, "How it works"),
            "steps": cleaned[:4],
        }

    if visual_style == "before_after_split":
        return {
            **palette,
            "before_label": _clip(spec.get("before_label"), 20, "Before"),
            "before_text": _clip(spec.get("before_text"), 110, "Manual, slow, error-prone"),
            "after_label": _clip(spec.get("after_label"), 20, "After"),
            "after_text": _clip(spec.get("after_text"), 110, "Automated, fast, reliable"),
        }

    if visual_style == "annotated_screenshot_style":
        callouts = spec.get("callouts") or []
        cleaned = []
        for i, item in enumerate(callouts[:2]):
            if isinstance(item, dict):
                cleaned.append({
                    "label": _clip(item.get("label"), 12, f"{i + 1:02d}"),
                    "text": _clip(item.get("text"), 72, ""),
                })
        while len(cleaned) < 2:
            cleaned.append({"label": f"{len(cleaned) + 1:02d}", "text": ""})
        return {
            **palette,
            "screen_title": _clip(spec.get("screen_title"), 36, "Product view"),
            "callouts": cleaned[:2],
        }

    if visual_style == "data_moment":
        return {
            **palette,
            "hero_number": _clip(spec.get("hero_number"), 16, hook_line.split("|")[0].strip()[:16]),
            "hero_label": _clip(spec.get("hero_label"), 48, ""),
            "context": _clip(spec.get("context"), 96, ""),
        }

    if visual_style == "portrait_style_illustration":
        return {
            **palette,
            "headline": _clip(spec.get("headline") or hook_line, 64),
            "scene_line": _clip(spec.get("scene_line"), 96, ""),
        }

    raise ValueError(f"Unknown visual style: {visual_style}")


def _render_minimal_typographic(spec: dict) -> str:
    bg = spec["background"]
    accent = spec["accent"]
    lines = _wrap(spec["headline"], 18)
    sub_lines = _wrap(spec["subheadline"], 28) if spec["subheadline"] else []

    svg = _svg_open(bg)
    svg += f'<rect x="72" y="72" width="8" height="160" fill="{accent}" rx="2"/>'
    svg += _text_block(104, 170, lines, size=74, fill=spec["text_primary"], weight="600", family=SERIF)
    if sub_lines:
        svg += _text_block(104, 170 + len(lines) * 74 * 1.2 + 40, sub_lines, size=30, fill=spec["text_secondary"])
    svg += f'<text x="72" y="{CANVAS - 72}" font-family="{FONT}" font-size="22" fill="{accent}" letter-spacing="0.12em">AELYX</text>'
    svg += "</svg>"
    return svg


def _render_diagram_flow(spec: dict) -> str:
    bg = spec["background"]
    surface = spec["surface"]
    accent = spec["accent"]
    steps = spec["steps"]
    count = len(steps)

    box_w = 230
    gap = 70
    total_w = count * box_w + (count - 1) * gap
    start_x = (CANVAS - total_w) // 2
    y = 470

    svg = _svg_open(bg)
    svg += _text_block(CANVAS // 2, 130, _wrap(spec["title"], 24), size=42, fill=spec["text_primary"],
                       weight="600", anchor="middle", family=SERIF)

    for i, step in enumerate(steps):
        x = start_x + i * (box_w + gap)
        svg += (
            f'<rect x="{x}" y="{y}" width="{box_w}" height="250" rx="16" fill="{surface}" '
            f'stroke="{spec["muted"]}" stroke-width="2"/>'
            f'<rect x="{x}" y="{y}" width="{box_w}" height="8" rx="16" fill="{accent}"/>'
        )
        svg += _text_block(x + 24, y + 58, _wrap(step["label"], 16), size=28, fill=spec["text_primary"], weight="600")
        if step["detail"]:
            svg += _text_block(x + 24, y + 110, _wrap(step["detail"], 22), size=20, fill=spec["text_secondary"])
        if i < count - 1:
            ax1 = x + box_w + 12
            ax2 = x + box_w + gap - 12
            svg += _arrow(ax1, y + 125, ax2, y + 125, accent)

    svg += f'<text x="{CANVAS // 2}" y="{CANVAS - 72}" font-family="{FONT}" font-size="20" '
    svg += f'fill="{spec["text_secondary"]}" text-anchor="middle">{escape(" - ".join(s["label"] for s in steps))}</text>'
    svg += "</svg>"
    return svg


def _render_before_after_split(spec: dict) -> str:
    bg = spec["background"]
    accent = spec["accent"]
    mid = CANVAS // 2

    svg = _svg_open(bg)
    svg += f'<rect x="0" y="0" width="{mid}" height="{CANVAS}" fill="{spec["surface"]}"/>'
    svg += f'<line x1="{mid}" y1="80" x2="{mid}" y2="{CANVAS - 80}" stroke="{spec["muted"]}" stroke-width="2"/>'
    svg += f'<rect x="{mid}" y="0" width="{mid}" height="{CANVAS}" fill="{bg}"/>'
    svg += f'<rect x="{mid + 40}" y="80" width="{mid - 80}" height="{CANVAS - 160}" rx="20" fill="none" stroke="{accent}" stroke-width="3"/>'

    svg += _text_block(72, 150, [spec["before_label"]], size=24, fill=accent, weight="600")
    svg += _text_block(72, 210, _wrap(spec["before_text"], 20), size=34, fill=spec["text_primary"], weight="500", family=SERIF)

    svg += _text_block(mid + 72, 150, [spec["after_label"]], size=24, fill=accent, weight="600")
    svg += _text_block(mid + 72, 210, _wrap(spec["after_text"], 20), size=34, fill=spec["text_primary"], weight="500", family=SERIF)
    svg += "</svg>"
    return svg


def _render_annotated_screenshot(spec: dict) -> str:
    bg = spec["background"]
    surface = spec["surface"]
    accent = spec["accent"]
    frame_x, frame_y, frame_w, frame_h = 140, 180, 920, 620

    svg = _svg_open(bg)
    svg += (
        f'<rect x="{frame_x}" y="{frame_y}" width="{frame_w}" height="{frame_h}" rx="18" '
        f'fill="{surface}" stroke="{spec["muted"]}" stroke-width="2"/>'
        f'<rect x="{frame_x}" y="{frame_y}" width="{frame_w}" height="56" rx="18" fill="{spec["muted"]}"/>'
        f'<circle cx="{frame_x + 34}" cy="{frame_y + 28}" r="7" fill="#B5604A"/>'
        f'<circle cx="{frame_x + 58}" cy="{frame_y + 28}" r="7" fill="{accent}" opacity="0.7"/>'
        f'<circle cx="{frame_x + 82}" cy="{frame_y + 28}" r="7" fill="{spec["text_secondary"]}" opacity="0.5"/>'
    )
    svg += _text_block(CANVAS // 2, frame_y + 36, [spec["screen_title"]], size=24, fill=spec["text_primary"], anchor="middle")

    # Placeholder UI blocks inside the mock screen
    svg += f'<rect x="{frame_x + 48}" y="{frame_y + 100}" width="360" height="28" rx="6" fill="{bg}"/>'
    svg += f'<rect x="{frame_x + 48}" y="{frame_y + 150}" width="520" height="18" rx="4" fill="{bg}" opacity="0.8"/>'
    svg += f'<rect x="{frame_x + 48}" y="{frame_y + 182}" width="460" height="18" rx="4" fill="{bg}" opacity="0.6"/>'

    callout_positions = [(frame_x + 760, frame_y + 180), (frame_x + 700, frame_y + 420)]
    for callout, (cx, cy) in zip(spec["callouts"], callout_positions):
        if not callout["text"]:
            continue
        label_x, label_y = cx - 220, cy - 10
        svg += (
            f'<line x1="{cx - 40}" y1="{cy}" x2="{label_x + 180}" y2="{label_y + 20}" '
            f'stroke="{accent}" stroke-width="2"/>'
            f'<circle cx="{cx - 40}" cy="{cy}" r="10" fill="{accent}"/>'
            f'<rect x="{label_x}" y="{label_y}" width="190" height="92" rx="10" fill="{bg}" stroke="{accent}" stroke-width="2"/>'
        )
        svg += _text_block(label_x + 16, label_y + 30, [callout["label"]], size=16, fill=accent, weight="700")
        svg += _text_block(label_x + 16, label_y + 54, _wrap(callout["text"], 20), size=18, fill=spec["text_primary"])
    svg += "</svg>"
    return svg


def _render_data_moment(spec: dict) -> str:
    bg = spec["background"]
    accent = spec["accent"]

    svg = _svg_open(bg)
    svg += f'<circle cx="{CANVAS // 2}" cy="520" r="280" fill="none" stroke="{accent}" stroke-width="2" opacity="0.25"/>'
    svg += f'<circle cx="{CANVAS // 2}" cy="520" r="220" fill="{spec["surface"]}" opacity="0.55"/>'
    svg += _text_block(CANVAS // 2, 500, [spec["hero_number"]], size=148, fill=accent, weight="700",
                       anchor="middle", family=SERIF)
    if spec["hero_label"]:
        svg += _text_block(CANVAS // 2, 620, _wrap(spec["hero_label"], 28), size=34, fill=spec["text_primary"],
                           anchor="middle", weight="600")
    if spec["context"]:
        svg += _text_block(CANVAS // 2, 900, _wrap(spec["context"], 34), size=26, fill=spec["text_secondary"],
                           anchor="middle")
    svg += "</svg>"
    return svg


def _render_portrait_editorial(spec: dict) -> str:
    bg = spec["background"]
    accent = spec["accent"]

    svg = _svg_open(bg)
    svg += f'<circle cx="980" cy="220" r="180" fill="{accent}" opacity="0.12"/>'
    svg += f'<circle cx="1040" cy="340" r="110" fill="{spec["surface"]}" opacity="0.9"/>'
    svg += f'<rect x="120" y="760" width="420" height="6" fill="{accent}" rx="3"/>'
    svg += _text_block(120, 220, _wrap(spec["headline"], 16), size=58, fill=spec["text_primary"],
                       weight="600", family=SERIF)
    if spec["scene_line"]:
        svg += _text_block(120, 820, _wrap(spec["scene_line"], 30), size=28, fill=spec["text_secondary"])
    svg += f'<text x="120" y="{CANVAS - 72}" font-family="{FONT}" font-size="22" fill="{accent}" letter-spacing="0.12em">AELYX</text>'
    svg += "</svg>"
    return svg


_RENDERERS = {
    "minimal_typographic": _render_minimal_typographic,
    "diagram_flow": _render_diagram_flow,
    "before_after_split": _render_before_after_split,
    "annotated_screenshot_style": _render_annotated_screenshot,
    "data_moment": _render_data_moment,
    "portrait_style_illustration": _render_portrait_editorial,
}


def render_visual(visual_style: str, spec: dict, hook_line: str) -> str:
    normalized = normalize_spec(visual_style, spec, hook_line)
    renderer = _RENDERERS.get(visual_style)
    if renderer is None:
        raise ValueError(f"No renderer for visual style: {visual_style}")
    return renderer(normalized)
