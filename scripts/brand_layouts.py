"""
brand_layouts.py

Aelyx editorial post renderer. The LLM never draws: it fills the text fields a
layout asks for, and this module renders the SVG from fixed brand tokens
(Bumblebee palette, Bodoni Moda / Inter Tight / IBM Plex Mono, Aelyx logo).
Canvas is 1080x1350 (4:5) so the same art works on LinkedIn and Instagram.

Fonts: SVGs carry an <!--AELYX_FONTS--> marker; the dashboard (and any
renderer) swaps it for docs/data/fonts.css. Widths are measured from the real
font files in scripts/fonts so wrapping and highlights fit exactly.
"""

import math
import random
import re
from pathlib import Path

from fontTools.ttLib import TTFont

W, H, M = 1080, 1350, 72
SAFE_BOTTOM = H - M - 60  # content must end above the footer rule
FONT_DIR = Path(__file__).parent / "fonts"

PAPER, INK, BEE, SAND = "#F5F1E6", "#0B0B0B", "#FFC800", "#E6DFC8"
SIDE = "#CFC7AE"  # muted warm grey for iso side faces

# bg, fg, accent. hl = light canvas where the emphasis word sits on a highlight block.
THEMES = {
    "paper": dict(bg=PAPER, fg=INK, acc=BEE, hl=True),
    "ink": dict(bg=INK, fg=PAPER, acc=BEE, hl=False),
    "bee": dict(bg=BEE, fg=INK, acc=INK, hl=True),
    "sand": dict(bg=SAND, fg=INK, acc=BEE, hl=True),
}

CSS_FONT = {
    "serif": 'font-family="Bodoni Moda,Georgia,serif" font-weight="500"',
    "serif_i": 'font-family="Bodoni Moda,Georgia,serif" font-style="italic" font-weight="500"',
    "sans": 'font-family="Inter Tight,Arial,sans-serif" font-weight="500"',
    "sansb": 'font-family="Inter Tight,Arial,sans-serif" font-weight="800"',
    "mono": 'font-family="IBM Plex Mono,Consolas,monospace" font-weight="500"',
}

_fonts = {}


def _font(key):
    if key not in _fonts:
        f = TTFont(FONT_DIR / f"{key}.woff")
        _fonts[key] = (f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm)
    return _fonts[key]


def tw(s, key, size, ls=0):
    cmap, hmtx, upm = _font(key)
    total = sum(hmtx[cmap.get(ord(c), cmap.get(32))][0] for c in s)
    return total / upm * size + ls * len(s)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def txt(x, y, s, size, key, fill, anchor="start", ls=0, extra=""):
    ls_attr = f' letter-spacing="{ls}"' if ls else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" {CSS_FONT[key]} fill="{fill}" '
            f'text-anchor="{anchor}"{ls_attr} {extra}>{esc(s)}</text>')


def wrap(s, key, size, maxw, ls=0):
    lines, cur = [], ""
    for w in str(s).split():
        trial = f"{cur} {w}".strip()
        if cur and tw(trial, key, size, ls) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def mono(x, y, s, T, size=20, anchor="start", fill=None):
    return txt(x, y, str(s).upper(), size, "mono", fill or T["fg"], anchor, ls=2.5)


def rich(text, size, maxw, T, x, y, lh=1.02):
    """Serif headline with *emphasis* words (italic + highlight). y = top of block.
    Returns (svg, height)."""
    words = []  # (word, em)
    for m in re.finditer(r"\*([^*]+)\*|(\S+)", str(text)):
        if m.group(1):
            words += [(w, True) for w in m.group(1).split()]
        else:
            words.append((m.group(2), False))
    key = lambda em: "serif_i" if em else "serif"
    lines, cur, curw = [], [], 0
    sp = tw(" ", "serif", size)
    for w, em in words:
        ww = tw(w, key(em), size)
        if cur and curw + sp + ww > maxw:
            lines.append(cur)
            cur, curw = [], 0
        curw += (sp if cur else 0) + ww
        cur.append((w, em, ww))
    if cur:
        lines.append(cur)
    out = []
    for i, ln in enumerate(lines):
        base = y + size * 0.85 + i * size * lh
        cx = x
        for w, em, ww in ln:
            if em and T["hl"]:
                out.append(f'<rect x="{cx - 8:.1f}" y="{base - size * 0.78:.1f}" width="{ww + 16:.1f}" '
                           f'height="{size * 0.98:.1f}" fill="{T["acc"]}"/>')
            fill = (T["bg"] if em and T["hl"] and T["acc"] == INK else T["fg"] if T["hl"] else T["acc"]) if em else T["fg"]
            out.append(txt(cx, base, w, size, key(em), fill))
            cx += ww + sp
    return "".join(out), len(lines) * size * lh, max((sum(w[2] for w in l) + sp * (len(l) - 1) for l in lines), default=0)


def fit_rich(text, maxw, maxh, T, x, y, smax=130, smin=44, lh=1.02):
    for size in range(smax, smin - 1, -4):
        svg, h, w = rich(text, size, maxw, T, x, y, lh)
        if h <= maxh and w <= maxw:
            return svg, h
    return svg, h


def fit_one_line(s, key, maxw, smax, smin=40, ls=0):
    size = smax
    while size > smin and tw(s, key, size, ls) > maxw:
        size -= 4
    return size


# ---------- logo + brand assets ----------
# Vertices traced from the original Aelyx logo file (2000px artboard, mark spans 442..1579).
LOGO_POLYS = [
    [(499, 637), (693, 442), (1248, 442), (1276, 462), (1280, 492), (1082, 683), (536, 683), (509, 670)],
    [(442, 1055), (618, 865), (647, 857), (682, 890), (681, 1092), (510, 1270), (477, 1281), (442, 1247)],
    [(1339, 934), (1518, 745), (1556, 742), (1579, 773), (1579, 1328), (1403, 1513), (1362, 1518), (1339, 1490)],
    [(741, 1538), (926, 1342), (1131, 1339), (1165, 1368), (1157, 1404), (980, 1576), (775, 1579)],
    [(872, 896), (894, 872), (1142, 879), (1151, 1128), (1128, 1151), (882, 1145)],  # centre square
]
LOGO_MIN, LOGO_SPAN, LOGO_MID = 442, 1137, (1010.5, 1010.5)


def _poly(pts, fill):
    d = " ".join(f"{x},{y}" for x, y in pts)
    return f'<polygon points="{d}" fill="{fill}" stroke="{fill}" stroke-width="10" stroke-linejoin="round"/>'


def logo(x, y, size, fill):
    s = size / LOGO_SPAN
    parts = "".join(_poly(p, fill) for p in LOGO_POLYS)
    return f'<g transform="translate({x - LOGO_MIN * s:.2f},{y - LOGO_MIN * s:.2f}) scale({s:.5f})">{parts}</g>'


def shards(cx, cy, size, rng, fills, explode=0.3):
    """The real logo with its pieces nudged apart (explode 0 = intact). Deterministic offsets
    so the mark stays recognisable; rng only picks which way the pieces drift."""
    s = size / LOGO_SPAN
    out = []
    for i, pts in enumerate(LOGO_POLYS):
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        dx, dy = (mx - LOGO_MID[0]) * explode, (my - LOGO_MID[1]) * explode
        out.append(f'<g transform="translate({cx + dx * s:.1f},{cy + dy * s:.1f}) scale({s:.5f}) '
                   f'translate({-LOGO_MID[0]},{-LOGO_MID[1]})">{_poly(pts, fills[i % len(fills)])}</g>')
    return "".join(out)


def iso_slab(cx, cy, w, t, top, left, right, stroke):
    q = w / 4
    return (f'<g stroke="{stroke}" stroke-width="4" stroke-linejoin="round">'
            f'<polygon points="{cx - w / 2},{cy} {cx},{cy + q} {cx},{cy + q + t} {cx - w / 2},{cy + t}" fill="{left}"/>'
            f'<polygon points="{cx},{cy + q} {cx + w / 2},{cy} {cx + w / 2},{cy + t} {cx},{cy + q + t}" fill="{right}"/>'
            f'<polygon points="{cx},{cy - q} {cx + w / 2},{cy} {cx},{cy + q} {cx - w / 2},{cy}" fill="{top}"/></g>')


def chrome(T, tag, top=None, bot=None, footer=""):
    top, bot = top or T["fg"], bot or T["fg"]
    return (logo(M, M - 6, 62, top) + mono(W - M, M + 38, tag, T, 20, "end", top)
            + f'<rect x="{M}" y="{H - M - 36}" width="{W - 2 * M}" height="2" fill="{bot}"/>'
            + mono(M, H - M, footer, T, 18, "start", bot) + mono(W - M, H - M, "aelyx.ai", T, 18, "end", bot))


# ---------- layouts: each returns (body_svg, chrome_kwargs) ----------
def L_statement(f, T, rng):
    body, h = fit_rich(f.get("headline", ""), W - 2 * M, 800, T, M, 330, smax=150)
    sub = ""
    if f.get("sub"):
        sub = "".join(txt(M, 330 + h + 70 + i * 40, l, 28, "sans", T["fg"]) for i, l in enumerate(wrap(f["sub"], "sans", 28, 760)[:4]))
    return body + sub, {}


def L_bignumber(f, T, rng):
    num = str(f.get("number", "10x"))
    size = fit_one_line(num, "sansb", W - 2 * M, 440, ls=-12)
    out = shards(W - 250, 300, 360, rng, [T["acc"]] * 5, 0.25)
    out += txt(M, 760, num, size, "sansb", T["fg"], ls=-12)
    out += mono(M, 830, f.get("unit_label", ""), T, 22, fill=T["fg"])
    cap, _ = fit_rich(f.get("caption", ""), W - 2 * M - 40, 330, T, M, 880, smax=60, smin=36, lh=1.12)
    return out + cap, {}


def L_beforeafter(f, T, rng):
    top, bot = INK, BEE
    out = f'<rect width="{W}" height="{H}" fill="{bot}"/><polygon points="0,0 {W},0 {W},{H * .5:.0f} 0,{H * .6:.0f}" fill="{top}"/>'
    A = dict(THEMES["ink"])
    B = dict(THEMES["bee"])
    b, _ = fit_rich(f.get("before", ""), W - 2 * M, 380, A, M, 300, smax=92, smin=44)
    a, _ = fit_rich(f.get("after", ""), W - 2 * M, 420, B, M, 800, smax=100, smin=44)
    out += mono(M, 262, f.get("before_label", "Before"), A, 22, fill=BEE) + b
    out += mono(M, 770, f.get("after_label", "After"), B, 22, fill=INK) + a
    return out, dict(top=PAPER, bot=INK)


def L_steps(f, T, rng):
    steps = (f.get("steps") or [])[:5]
    head, h = fit_rich(f.get("headline", ""), W - 2 * M, 330, T, M, 250, smax=100, smin=48)
    out, y0 = head, 250 + h + 50
    rowh = min(130, (H - 200 - y0) / max(len(steps), 1))
    for i, s in enumerate(steps):
        y = y0 + i * rowh
        last = i == len(steps) - 1
        out += f'<rect x="{M}" y="{y:.0f}" width="{W - 2 * M}" height="2" fill="{T["fg"]}"/>'
        if last:
            out += f'<rect x="{M}" y="{y + 2:.0f}" width="{W - 2 * M}" height="{rowh - 2:.0f}" fill="{T["acc"]}"/>'
        c = T["bg"] if last and T["acc"] == INK else T["fg"]
        out += mono(M + 14, y + rowh / 2 + 8, f"0{i + 1}", T, 22, fill=c)
        sz = fit_one_line(s, "sansb", W - 2 * M - 200, 64, 30, ls=-1.5)
        out += txt(M + 130, y + rowh / 2 + sz * 0.35, s, sz, "sansb", c, ls=-1.5)
        out += txt(W - M - 14, y + rowh / 2 + 14, "→" if not last else "●", 40, "sans", c, "end")
    return out, {}


def L_quote(f, T, rng):
    out = txt(M - 10, 560, "“", 560, "serif", T["acc"] if not T["hl"] else T["fg"], extra='opacity="1"')
    q, h = fit_rich(f.get("quote", ""), W - 2 * M, 640, T, M, 520, smax=96, smin=44, lh=1.08)
    out += q + mono(M, 520 + h + 70, f.get("attribution", "Aelyx"), T, 22)
    return out, {}


def L_shards(f, T, rng):
    fills = [T["acc"], T["fg"], T["acc"], T["fg"], T["acc"]]
    out = shards(W / 2, 440, 560, rng, fills, 0.28)
    head, _ = fit_rich(f.get("headline", ""), W - 2 * M, 330, T, M, 900, smax=96, smin=44)
    return out + head, {}


def L_isostack(f, T, rng):
    layers = (f.get("layers") or [])[:4]
    n = max(len(layers), 1)
    head, h = fit_rich(f.get("headline", ""), W - 2 * M, 300, T, M, 230, smax=96, smin=44)
    out, cx, base = head, 420, 1020
    gap = 150
    for i, lab in enumerate(layers):
        cy = base - i * gap
        hero = i == n - 1
        top = T["acc"] if hero else T["bg"] if T["bg"] != BEE else PAPER
        out += iso_slab(cx, cy, 520, 70, top, T["fg"], SIDE if T["bg"] != INK else "#2A2A2A", T["fg"])
        out += f'<line x1="{cx + 150}" y1="{cy + 10}" x2="{W - M - 250}" y2="{cy + 10}" stroke="{T["fg"]}" stroke-width="2"/>'
        out += mono(W - M - 238, cy + 16, lab, T, 20)
    return out, {}


def L_flow(f, T, rng):
    inputs = (f.get("inputs") or [])[:4]
    n = max(len(inputs), 1)
    head, h = fit_rich(f.get("headline", ""), W - 2 * M, 300, T, M, 230, smax=88, smin=44)
    out, pw = head, (W - 2 * M - 16 * (n - 1)) / n
    hub = (W / 2, 900)
    for i, s in enumerate(inputs):
        x = M + i * (pw + 16)
        out += f'<path d="M{x + pw / 2:.0f},720 C{x + pw / 2:.0f},800 {hub[0]},780 {hub[0]},{hub[1] - 110}" fill="none" stroke="{T["fg"]}" stroke-width="3"/>'
        out += f'<rect x="{x:.0f}" y="590" width="{pw:.0f}" height="130" rx="65" fill="{T["bg"]}" stroke="{T["fg"]}" stroke-width="3"/>'
        for j, l in enumerate(wrap(s.upper(), "mono", 17, pw - 30, 1.5)[:3]):
            out += txt(x + pw / 2, 650 + j * 22 - (len(wrap(s.upper(), "mono", 17, pw - 30, 1.5)[:3]) - 1) * 11, l, 17, "mono", T["fg"], "middle", 1.5)
    out += f'<circle cx="{hub[0]}" cy="{hub[1]}" r="110" fill="{T["acc"]}" stroke="{T["fg"]}" stroke-width="4"/>'
    out += logo(hub[0] - 55, hub[1] - 55, 110, T["fg"] if T["acc"] == BEE else T["bg"])
    out += f'<line x1="{hub[0]}" y1="{hub[1] + 110}" x2="{hub[0]}" y2="1100" stroke="{T["fg"]}" stroke-width="3"/>'
    out += txt(hub[0], 1150, str(f.get("output", "One system")), fit_one_line(str(f.get("output", "One system")), "serif", W - 2 * M, 72), "serif", T["fg"], "middle")
    return out, {}


def L_chat(f, T, rng):
    head, h = fit_rich(f.get("headline", ""), W - 2 * M, 280, T, M, 220, smax=80, smin=44)
    out, y = head, 220 + h + 40
    out += f'<rect x="150" y="{y:.0f}" width="780" height="{H - 220 - y:.0f}" rx="40" fill="{T["fg"]}" opacity="0.07"/>'
    y += 40
    for m in (f.get("messages") or [])[:5]:
        mine = m.get("from") == "aelyx"
        lines = wrap(m.get("text", ""), "sans", 30, 500)[:4]
        bw = max(tw(l, "sans", 30) for l in lines) + 56 if lines else 120
        bh = len(lines) * 40 + 36
        x = 930 - 30 - bw if mine else 180
        fill = T["acc"] if mine else T["bg"] if T["bg"] != INK else "#1C1C1C"
        tcol = (T["bg"] if T["acc"] == INK else INK) if mine else T["fg"]
        out += f'<rect x="{x:.0f}" y="{y:.0f}" width="{bw:.0f}" height="{bh}" rx="28" fill="{fill}" stroke="{T["fg"]}" stroke-width="2"/>'
        out += "".join(txt(x + 28, y + 24 + 30 * 0.75 + j * 40, l, 30, "sans", tcol) for j, l in enumerate(lines))
        y += bh + 22
    return out, {}


def L_statcards(f, T, rng):
    head, h = fit_rich(f.get("headline", ""), W - 2 * M, 330, T, M, 230, smax=92, smin=44)
    stats = (f.get("stats") or [])[:3]
    out, y0 = head, 230 + h + 40
    ch = min(260, (H - 190 - y0) / max(len(stats), 1) - 16)
    fills = [(INK, PAPER), (BEE, INK), (PAPER, INK)]
    for i, s in enumerate(stats):
        bg, fg = fills[(i + rng.randint(0, 2)) % 3] if T["bg"] != PAPER else fills[i % 3]
        y = y0 + i * (ch + 16)
        out += f'<rect x="{M}" y="{y:.0f}" width="{W - 2 * M}" height="{ch:.0f}" fill="{bg}" stroke="{INK}" stroke-width="3"/>'
        v = str(s.get("value", ""))
        sz = fit_one_line(v, "sansb", 480, 190, ls=-6)
        out += txt(M + 36, y + ch / 2 + sz * 0.36, v, sz, "sansb", fg, ls=-6)
        for j, l in enumerate(wrap(str(s.get("label", "")).upper(), "mono", 20, 300, 2.5)[:4]):
            out += txt(W - M - 36, y + ch / 2 - 10 + j * 28, l, 20, "mono", fg, "end", 2.5)
    return out, {}


def L_note(f, T, rng):
    items = (f.get("items") or [])[:5]
    out = f'<g transform="rotate(-2.5 {W / 2} 700)"><rect x="{M + 18}" y="268" width="{W - 2 * M}" height="860" fill="{INK}"/>'
    out += f'<rect x="{M}" y="250" width="{W - 2 * M}" height="860" fill="{PAPER}" stroke="{INK}" stroke-width="3"/>'
    out += f'<rect x="{W / 2 - 90}" y="222" width="180" height="56" fill="{BEE}" opacity="0.92"/>'
    tl, th = fit_rich(f.get("title", ""), W - 2 * M - 100, 260, dict(THEMES["paper"]), M + 50, 330, smax=78, smin=40)
    out += tl
    y = 330 + th + 50
    for it in items:
        out += f'<rect x="{M + 50}" y="{y - 26}" width="34" height="34" fill="none" stroke="{INK}" stroke-width="3"/>'
        out += f'<path d="M{M + 56},{y - 8} l10,12 l20,-26" fill="none" stroke="{INK}" stroke-width="5"/>'
        for j, l in enumerate(wrap(it, "sans", 34, W - 2 * M - 220)[:2]):
            out += txt(M + 110, y + j * 42, l, 34, "sans", INK)
        y += 78 + (42 if len(wrap(it, "sans", 34, W - 2 * M - 220)) > 1 else 0)
    return out + "</g>", dict(bot=INK, top=INK)


def L_poster(f, T, rng):
    out = ""
    cols, gap = 36, (W - 2 * M) / 35
    for r in range(22):
        for c in range(cols):
            x, y = M + c * gap, 200 + r * gap
            d = math.hypot(x - W * 0.62, y - 480) / 520
            rad = max(0, (1 - d) * gap * 0.52 + rng.uniform(-1, 1))
            if rad > 1:
                out += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rad:.1f}" fill="{T["fg"] if T["bg"] != BEE else INK}"/>'
    text = str(f.get("headline", "")).replace("*", "").upper()
    size = 140
    while size > 40 and (len(wrap(text, "sansb", size, W - 2 * M, -4)) * size * 0.95 > 250
                         or any(tw(w, "sansb", size, -4) > W - 2 * M for w in text.split())):
        size -= 6
    y = 830 + size * 0.85
    for ln in wrap(text, "sansb", size, W - 2 * M, -4):
        out += txt(M, y, ln, size, "sansb", T["acc"] if T["bg"] == INK else T["fg"], ls=-4)
        y += size * 0.95
    out += mono(M, y + 20, f.get("sub", ""), T, 20)
    return out, {}


def L_marquee(f, T, rng):
    word = str(f.get("word", "SYSTEMS")).upper()
    size = min(fit_one_line(word, "sansb", W - 2 * M, 230, 90, ls=-6), 150)
    out, y, rows = "", 250, 4
    for i in range(rows):
        mid = i == 1
        fill = T["acc"] if mid and T["bg"] != BEE else (T["fg"] if mid else "none")
        out += txt(M, y + size * 0.78, word, size, "sansb", fill, ls=-6, extra=f'stroke="{T["fg"]}" stroke-width="3"')
        y += size * 0.92
    tag, _ = fit_rich(f.get("tagline", ""), W - 2 * M, SAFE_BOTTOM - (y + 40), T, M, y + 40, smax=56, smin=34, lh=1.1)
    return out + tag, {}


def L_cta(f, T, rng):
    """Closing carousel slide: one line, one action."""
    out = shards(W - 230, 330, 300, rng, [T["acc"]] * 5, 0.2)
    head, h = fit_rich(f.get("headline", ""), W - 2 * M, 420, T, M, 520, smax=110, smin=48)
    btn_y = 520 + h + 60
    label = str(f.get("button", "aelyx.ai"))
    bw = min(W - 2 * M, tw(label.upper() + "  >", "mono", 26, 3) + 80)
    fill = T["acc"] if T["bg"] != BEE else INK
    tc = INK if fill == BEE else PAPER
    out += f'<rect x="{M}" y="{btn_y:.0f}" width="{bw:.0f}" height="96" fill="{fill}"/>'
    out += txt(M + 40, btn_y + 60, label.upper() + "  →".replace("\u2192", "->"), 26, "mono", tc, ls=3)
    return out + head, {}


def _img(f, x, y, w, h):
    return (f'<image href="{f["_image"]}" x="{x}" y="{y}" width="{w}" height="{h}" '
            f'preserveAspectRatio="xMidYMid slice"/>') if f.get("_image") else ""


def L_photo_hero(f, T, rng):
    """AI-generated hero object on a flat canvas-coloured field; headline sits in the empty top."""
    head, _ = fit_rich(f.get("headline", ""), W - 2 * M, 380, T, M, 190, smax=118, smin=48)
    return _img(f, 0, 0, W, H) + head, {}


def L_photo_frame(f, T, rng):
    """AI-generated scene as a taped, tilted print on the canvas."""
    head, _ = fit_rich(f.get("headline", ""), W - 2 * M, 200, T, M, 190, smax=96, smin=44)
    out = head + f'<g transform="rotate(-3 {W / 2} 800)"><rect x="{M + 26}" y="452" width="{W - 2 * M - 40}" height="760" fill="{INK}"/>'
    out += f'<rect x="{M + 10}" y="430" width="{W - 2 * M - 40}" height="760" fill="{PAPER}" stroke="{INK}" stroke-width="3"/>'
    out += _img(f, M + 40, 460, W - 2 * M - 100, 640)
    out += f'<rect x="{W / 2 - 100}" y="402" width="200" height="54" fill="{BEE if T["bg"] != BEE else INK}" opacity="0.9"/></g>'
    return out, {}


LAYOUTS = {
    "statement": (L_statement, "headline: 6-14 word statement, wrap ONE key word in *asterisks*; sub: optional 1-2 sentence support (max 25 words)", ["paper", "ink", "bee", "sand"]),
    "bignumber": (L_bignumber, "number: one real figure from the source, e.g. '4x' or '60%' (max 5 chars); unit_label: 2-4 words under it; caption: one sentence of context, one *key word* in asterisks", ["ink", "paper", "bee"]),
    "beforeafter": (L_beforeafter, "before_label: 'Before'; before: old painful state (max 10 words); after_label: 'After'; after: new state (max 10 words, one *key word* in asterisks)", ["ink"]),
    "steps": (L_steps, "headline: short, one *key word* in asterisks; steps: 3-5 short step names (1-3 words each), the last is the outcome", ["paper", "sand", "ink"]),
    "quote": (L_quote, "quote: one sharp sentence, max 18 words, one *key word* in asterisks; attribution: who/what it comes from, e.g. 'Founder note' or 'Client brief'", ["paper", "ink", "sand", "bee"]),
    "shards": (L_shards, "headline: 5-12 words, one *key word* in asterisks", ["paper", "ink", "bee", "sand"]),
    "isostack": (L_isostack, "headline: short, one *key word* in asterisks; layers: 3-4 labels (1-3 words) bottom-to-top of a system stack, the last is the outcome", ["paper", "sand", "ink"]),
    "flow": (L_flow, "headline: short, one *key word* in asterisks; inputs: 3-4 separate tools/channels (1-3 words each); output: the single result (max 4 words)", ["paper", "sand", "ink"]),
    "chat": (L_chat, "headline: short, one *key word* in asterisks; messages: 3-5 objects {from:'customer'|'aelyx', text: max 14 words} showing a real automated conversation", ["paper", "sand", "ink"]),
    "statcards": (L_statcards, "headline: short, one *key word* in asterisks; stats: 2-3 objects {value: real figure max 6 chars, label: max 6 words}", ["paper", "sand", "bee"]),
    "note": (L_note, "title: short, one *key word* in asterisks; items: 3-5 checklist lines (max 8 words each)", ["sand", "bee"]),
    "poster": (L_poster, "headline: 3-7 words (rendered uppercase, huge); sub: max 8 words", ["paper", "ink", "bee"]),
    "photo_hero": (L_photo_hero, "headline: 4-10 words, one *key word* in asterisks; image_prompt: ONE concrete physical object or tableau that metaphorically embodies this post's idea (e.g. a typewriter, a traffic light, a magnifying glass, a vending machine, a switchboard). Describe only the object and its material/mood, no text in the image", ["bee", "paper", "sand", "ink"]),
    "photo_frame": (L_photo_frame, "headline: 4-10 words, one *key word* in asterisks; image_prompt: a real-world scene (workplace, shopfloor, clinic, gym, desk) that embodies the post's idea, described as a candid editorial photo. No text in the image", ["bee", "sand"]),
    "cta": (L_cta, "headline: closing line with one *key word* in asterisks; button: 2-4 word call to action (default aelyx.ai)", ["ink", "bee", "paper"]),
    "marquee": (L_marquee, "word: ONE strong word (max 10 letters) repeated as typographic art, e.g. 'SYSTEMS'; tagline: one sentence, one *key word* in asterisks", ["ink", "paper", "bee"]),
}

TAGS = {"statement": "Perspective", "bignumber": "By the numbers", "beforeafter": "Shift", "steps": "The system", "quote": "Note",
        "shards": "Aelyx", "isostack": "Stack", "flow": "How it works", "chat": "In practice", "statcards": "Results", "note": "Checklist",
        "poster": "Aelyx", "marquee": "Aelyx", "photo_hero": "Aelyx", "photo_frame": "In the field", "cta": "Next step"}


class LayoutOverflow(Exception):
    pass


def check_bounds(body):
    """Raise if any text or card extends past the footer, or text runs off the right edge."""
    for m in re.finditer(r'<text x="([\d.-]+)" y="([\d.-]+)" font-size="([\d.]+)"[^>]*text-anchor="(\w+)"[^>]*>', body):
        x, y, size, anchor = float(m[1]), float(m[2]), float(m[3]), m[4]
        if y + size * 0.25 > SAFE_BOTTOM:
            raise LayoutOverflow(f"text at y={y:.0f} runs into the footer")
        if anchor == "start" and x > W - M + 5:
            raise LayoutOverflow("text starts outside the canvas")
    for m in re.finditer(r'<rect x="[\d.-]+" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', body):
        y, w, h = float(m[1]), float(m[2]), float(m[3])
        if w < W and y > 150 and y + h > SAFE_BOTTOM + 40:
            raise LayoutOverflow(f"block ending at y={y + h:.0f} runs into the footer")


PHOTO_LAYOUTS = {"photo_hero", "photo_frame"}
CAROUSEL_ONLY = {"cta"}  # never picked as a standalone post


def render_post(layout, fields, theme, seed, tag=None, footer=""):
    """Returns a complete 1080x1350 SVG string for the given layout/fields/theme."""
    fn = LAYOUTS[layout][0]
    T = THEMES[theme]
    rng = random.Random(seed)
    body, ck = fn(fields, T, rng)
    check_bounds(body)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'<defs><!--AELYX_FONTS--></defs><rect width="{W}" height="{H}" fill="{T["bg"]}"/>{body}'
            f'{chrome(T, tag or fields.get("tag") or TAGS[layout], ck.get("top"), ck.get("bot"), footer)}</svg>')


def render_carousel(slides, seed):
    """slides: [{layout, fields, theme}] -> list of SVGs with a quiet '02 / 06' pager in the footer."""
    n = len(slides)
    return [render_post(sl["layout"], sl["fields"], sl["theme"], f"{seed}-{i}",
                        footer=f"{i + 1:02d} / {n:02d}" if n > 1 else "") for i, sl in enumerate(slides)]
